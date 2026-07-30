"""Product operations. The reference implementation every other service copies.

Read this file as the pattern, not just as products code. Five conventions are
established here and every future service function follows them:

  1. `session` is the first parameter, `actor` the second. Neither is fetched
     from a global. A function that reaches for ambient state cannot be reused
     by a second adapter, and cannot be tested without one.

  2. Everything after those two is keyword-only (the bare `*` in the signature).
     `create_product(s, a, "RICE-1", "Rice", "Grains")` is unreadable and
     silently wrong if two arguments swap; `sku=..., name=...` is neither.
     There is no positional-argument-shaped bug in this file by construction.

  3. Writes call `actor.can(...)` first and raise `PermissionDeniedError`.
     Nothing is actually gated today - SystemActor returns True for everything -
     but the call sites exist, so switching on a real auth provider later
     touches core/actor.py and the two adapters, and nothing in here.

  4. Writes stamp `created_by` / `updated_by` from `actor.id`.

  5. Failure is an exception from core/exceptions.py, never a None or a False.
     `get_product` raising NotFoundError rather than returning `Product | None`
     means the caller cannot forget to check - which is the bug you get for
     free with a nullable return, in every language.

### On committing

These functions call `session.commit()` themselves. That is a deliberate
decision and the opposite of what `core.database.get_session` does (it closes
but never commits). The reasoning: a service function *is* the unit of business
work. "Create a product" either happened or it did not; leaving the transaction
open for an adapter to finish would mean each adapter has to remember, and one
of them eventually will not.

The cost is that a caller cannot compose two services into one transaction
("create a product AND a stock movement, both or neither"). When that need
arrives - it will, in purchasing.py - the fix is a small `unit_of_work` helper
that these functions opt into, not scattering commits into the adapters.

Coming from TypeScript: this is the same call you would make about whether a
Nest service method wraps itself in `prisma.$transaction` or expects the caller
to have opened one.
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.actor import Actor
from core.exceptions import (
    DuplicateError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from core.models import Product

# --- helpers ---------------------------------------------------------------


def _require(actor: Actor, permission: str) -> None:
    """Raise PermissionDeniedError unless `actor` holds `permission`.

    A leading underscore marks this as internal to the module - Python's
    convention where TypeScript would use `private` or simply not export.

    Factored out so the permission check reads as one line at the top of each
    write, and so the error message has one definition rather than five.
    """
    if not actor.can(permission):
        raise PermissionDeniedError(
            f"Actor {actor.id!r} is not allowed to perform {permission!r}."
        )


def _normalise_sku(sku: str) -> str:
    """Trim and upper-case an SKU, rejecting an empty one.

    SKUs are matched by humans reading shelf labels, so `rice-1kg` and
    `RICE-1KG` are the same product to everybody except the UNIQUE index.
    Normalising on the way in makes the database constraint agree with the
    human expectation, rather than fighting it.
    """
    cleaned = sku.strip().upper()
    if not cleaned:
        raise ValidationError("SKU cannot be empty.")
    return cleaned


def _check_price(value: Decimal, field: str) -> None:
    """Reject a negative price.

    Note the type hint says Decimal, and Python will not enforce that at
    runtime - hints are documentation the type checker reads, erased at
    execution, much like TypeScript's. The adapters use Pydantic to make the
    type real at the boundary; this function only owns the business rule.
    """
    if value < 0:
        raise ValidationError(f"{field} cannot be negative (got {value}).")


# --- reads -----------------------------------------------------------------


def list_products(
    session: Session,
    actor: Actor,
    *,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Product]:
    """Return products, newest first, optionally filtered by name or SKU.

    `limit` is capped rather than trusted. An adapter asking for a million rows
    is either a bug or an agent that misread its own tool description, and
    either way the answer is the same.
    """
    _require(actor, "product.read")

    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    # SQLAlchemy 2.0 style: build a `select()` object, then execute it. The 1.x
    # style you will see in older tutorials is `session.query(Product)...`,
    # which still works but is legacy. Use this form.
    stmt = select(Product)

    if search:
        pattern = f"%{search.strip()}%"
        # `ilike` is Postgres' case-insensitive LIKE. `|` on two SQLAlchemy
        # conditions builds SQL `OR` - it is not Python's bitwise-or here,
        # because the operands are SQLAlchemy expression objects that override
        # the operator. (`or` cannot be overridden, which is why `|` is used.)
        stmt = stmt.where(Product.name.ilike(pattern) | Product.sku.ilike(pattern))

    stmt = stmt.order_by(Product.id.desc()).limit(limit).offset(offset)

    # `.scalars()` unwraps each result row into the single entity it holds.
    # Without it you get rows of one-element tuples: `(Product(...),)`.
    return list(session.execute(stmt).scalars().all())


def get_product(session: Session, actor: Actor, *, product_id: int) -> Product:
    """Return one product by id, or raise NotFoundError.

    `session.get()` is the fast path for primary-key lookup: it checks the
    session's identity map first and only hits the database on a miss.
    """
    _require(actor, "product.read")

    product = session.get(Product, product_id)
    if product is None:
        raise NotFoundError(f"No product with id {product_id}.")
    return product


def get_product_by_sku(session: Session, actor: Actor, *, sku: str) -> Product:
    """Return one product by SKU, or raise NotFoundError.

    Exists because the SKU is what a human - or an agent parroting a human -
    actually has. Nobody reads an autoincrement id off a shelf label.
    """
    _require(actor, "product.read")

    normalised = _normalise_sku(sku)
    stmt = select(Product).where(Product.sku == normalised)
    product = session.execute(stmt).scalar_one_or_none()
    if product is None:
        raise NotFoundError(f"No product with SKU {normalised!r}.")
    return product


# --- writes ----------------------------------------------------------------


def create_product(
    session: Session,
    actor: Actor,
    *,
    sku: str,
    name: str,
    category: str | None = None,
    unit: str = "piece",
    cost_price: Decimal = Decimal("0.00"),
    sell_price: Decimal = Decimal("0.00"),
    quantity_on_hand: int = 0,
    reorder_level: int = 0,
) -> Product:
    """Create a product. Raises DuplicateError if the SKU is taken.

    Note the duplicate check is done *here*, with a SELECT, even though the
    UNIQUE index on `sku` would also stop it. That is not redundant, it is a
    division of labour:

      the index    guarantees correctness, including against a race between
                   two concurrent requests that both pass the check below
      this check   produces a message a person can act on, instead of a
                   psycopg IntegrityError mentioning `products_sku_key`

    A race would surface as an IntegrityError escaping this function, which the
    adapters currently turn into a 500. That is the honest state of things
    today; the fix when it matters is to catch IntegrityError here and re-raise
    it as DuplicateError. Not doing it yet because untested error paths that
    fire once a year are their own kind of bug.
    """
    _require(actor, "product.create")

    normalised = _normalise_sku(sku)

    if not name.strip():
        raise ValidationError("Product name cannot be empty.")
    if quantity_on_hand < 0:
        raise ValidationError("Opening stock cannot be negative.")
    if reorder_level < 0:
        raise ValidationError("Reorder level cannot be negative.")
    _check_price(cost_price, "cost_price")
    _check_price(sell_price, "sell_price")

    existing = session.execute(
        select(Product.id).where(Product.sku == normalised)
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateError(f"A product with SKU {normalised!r} already exists.")

    product = Product(
        sku=normalised,
        name=name.strip(),
        category=category.strip() if category else None,
        unit=unit.strip() or "piece",
        cost_price=cost_price,
        sell_price=sell_price,
        quantity_on_hand=quantity_on_hand,
        reorder_level=reorder_level,
        created_by=actor.id,
        updated_by=actor.id,
    )

    # `add` stages the object; `commit` writes it and ends the transaction.
    session.add(product)
    session.commit()

    # After a commit, the in-memory object is missing whatever the *database*
    # decided - here the `id` from the sequence and `created_at` from now().
    # `refresh` re-reads the row and fills them in, so the caller gets a
    # complete object rather than one with `id=None`.
    session.refresh(product)
    return product


def update_product(
    session: Session,
    actor: Actor,
    *,
    product_id: int,
    name: str | None = None,
    category: str | None = None,
    unit: str | None = None,
    cost_price: Decimal | None = None,
    sell_price: Decimal | None = None,
    reorder_level: int | None = None,
) -> Product:
    """Update the given fields of a product. Omitted fields are left alone.

    Every parameter defaults to None meaning "not supplied", which is the usual
    Python spelling of a PATCH. It has a known limitation: you cannot use it to
    *clear* `category` back to NULL, because "set it to None" and "do not
    change it" are the same value. If that becomes a real requirement the
    answer is a sentinel object (`UNSET = object()`) rather than more None.

    Two fields are deliberately absent. `sku` is not editable - it is the
    identifier printed on shelf labels, and renaming it silently is how stock
    goes missing; the deliberate path is delete and recreate. And
    `quantity_on_hand` is not editable here: stock moves through `adjust_stock`
    so the reason for the change stays attached to it.
    """
    _require(actor, "product.update")

    product = get_product(session, actor, product_id=product_id)

    if name is not None:
        if not name.strip():
            raise ValidationError("Product name cannot be empty.")
        product.name = name.strip()

    if category is not None:
        product.category = category.strip() or None

    if unit is not None:
        product.unit = unit.strip() or "piece"

    if cost_price is not None:
        _check_price(cost_price, "cost_price")
        product.cost_price = cost_price

    if sell_price is not None:
        _check_price(sell_price, "sell_price")
        product.sell_price = sell_price

    if reorder_level is not None:
        if reorder_level < 0:
            raise ValidationError("Reorder level cannot be negative.")
        product.reorder_level = reorder_level

    product.updated_by = actor.id

    # No `session.add` needed. The object came out of this session, so
    # SQLAlchemy is already tracking it and notices the attribute changes on
    # its own - the "unit of work" pattern. `updated_at` is refreshed by the
    # `onupdate=func.now()` on the model.
    session.commit()
    session.refresh(product)
    return product


def adjust_stock(
    session: Session,
    actor: Actor,
    *,
    product_id: int,
    delta: int,
    reason: str | None = None,
) -> Product:
    """Move stock by `delta` (negative to remove). Never below zero.

    This is the one function in the file that encodes a rule you could not
    guess from the schema, and it is the reason the whole services layer
    exists. Consider what enforcing it in the adapters instead would mean: the
    check written twice, in `api/routes/products.py` and in
    `mcp_server/server.py`, and the day someone fixes an off-by-one in one of
    them, the AI agent and the web UI disagree about how much rice there is.

    `reason` is accepted and currently discarded. That is intentional and
    slightly uncomfortable: there is nowhere to put it until
    `services/inventory.py` exists with a StockMovement table. Taking the
    parameter now means the adapters and their schemas are written once - when
    the ledger lands, this function starts recording what it is already being
    told, and no call site changes.
    """
    _require(actor, "stock.adjust")

    if delta == 0:
        raise ValidationError("Stock adjustment cannot be zero.")

    product = get_product(session, actor, product_id=product_id)

    new_quantity = product.quantity_on_hand + delta
    if new_quantity < 0:
        raise ValidationError(
            f"Cannot remove {abs(delta)} of {product.sku}: only "
            f"{product.quantity_on_hand} in stock."
        )

    product.quantity_on_hand = new_quantity
    product.updated_by = actor.id

    session.commit()
    session.refresh(product)
    return product
