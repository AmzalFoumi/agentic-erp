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

  3. Every read and write calls `require_permission(actor, ...)` first, from
     services/guards.py. That helper used to be a private `_require` in this
     file, with a comment saying a third copy should be extracted; gates 27-30
     add five more services, so it was extracted at gate 27. One definition
     means one error message, and one place to change if the check ever grows
     a second clause.

     The bet this convention represented has since paid out: gate 24 replaced
     SystemActor with a real TokenActor whose `can()` is set membership over a
     verified token's scopes, and **not one line of this file changed**,
     because the call sites already existed.

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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.actor import Actor
from core.exceptions import (
    DuplicateError,
    NotFoundError,
    ValidationError,
)
from core.enums import ClientType
from core.models import InventoryLot, Product
from services import lots
from services.guards import require_permission

# --- helpers ---------------------------------------------------------------


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


def _search_filter(stmt, search: str | None):
    """Apply the search predicate, if there is one, and return the statement.

    Extracted the moment a second caller appeared. `list_products` and
    `count_products` must agree on what "matching" means - a total that counts
    rows the list would not return is worse than no total at all, because it
    produces a pagination control that promises a page which comes back empty.
    Sharing the predicate makes them wrong together or right together, which is
    the only guarantee worth having here.
    """
    if not search:
        return stmt

    pattern = f"%{search.strip()}%"
    # `ilike` is Postgres' case-insensitive LIKE. `|` on two SQLAlchemy
    # conditions builds SQL `OR` - it is not Python's bitwise-or here, because
    # the operands are SQLAlchemy expression objects that override the
    # operator. (`or` cannot be overridden, which is why `|` is used.)
    return stmt.where(Product.name.ilike(pattern) | Product.sku.ilike(pattern))


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
    require_permission(actor, "product.read")

    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    # SQLAlchemy 2.0 style: build a `select()` object, then execute it. The 1.x
    # style you will see in older tutorials is `session.query(Product)...`,
    # which still works but is legacy. Use this form.
    stmt = _search_filter(select(Product), search)
    stmt = stmt.order_by(Product.id.desc()).limit(limit).offset(offset)

    # `.scalars()` unwraps each result row into the single entity it holds.
    # Without it you get rows of one-element tuples: `(Product(...),)`.
    return list(session.execute(stmt).scalars().all())


def count_products(
    session: Session,
    actor: Actor,
    *,
    search: str | None = None,
) -> int:
    """Count products matching the same filter `list_products` would apply.

    A sibling function rather than a changed return type on `list_products`,
    and that choice is the point. Making `list_products` return
    `(rows, total)` would force a second COUNT on every caller that does not
    want one - notably the MCP adapter, where an agent listing products has no
    use for a page total and the extra query is pure cost. Two functions let
    each adapter pay only for what it asks for.

    Deliberately no `limit`/`offset`: a total that respected the page window
    would just be `len(rows)`, which the caller already has. The whole reason
    this exists is to describe the set the window is cut from.
    """
    require_permission(actor, "product.read")

    # `select(func.count()).select_from(Product)` rather than
    # `select(func.count(Product.id))` so the predicate in `_search_filter`
    # attaches to the same FROM clause the list query uses.
    stmt = _search_filter(select(func.count()).select_from(Product), search)

    # `.scalar_one()` insists on exactly one row with exactly one column, which
    # a COUNT always returns. It raises rather than silently giving None, so a
    # malformed query fails here instead of becoming a `total` of null.
    return session.execute(stmt).scalar_one()


def get_product(session: Session, actor: Actor, *, product_id: int) -> Product:
    """Return one product by id, or raise NotFoundError.

    `session.get()` is the fast path for primary-key lookup: it checks the
    session's identity map first and only hits the database on a miss.
    """
    require_permission(actor, "product.read")

    product = session.get(Product, product_id)
    if product is None:
        raise NotFoundError(f"No product with id {product_id}.")
    return product


def get_product_by_sku(session: Session, actor: Actor, *, sku: str) -> Product:
    """Return one product by SKU, or raise NotFoundError.

    Exists because the SKU is what a human - or an agent parroting a human -
    actually has. Nobody reads an autoincrement id off a shelf label.
    """
    require_permission(actor, "product.read")

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
    require_permission(actor, "product.create")

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
        # Zero here on purpose, whatever the caller asked for. Opening stock
        # arrives as a LOT below, and `recalculate_on_hand` then sets this
        # field from that lot.
        #
        # ⚠️ Writing `quantity_on_hand=quantity_on_hand` directly - which is
        # what this line used to do - is the second write path the lot design
        # exists to prevent. It left a brand-new product claiming 10 in stock
        # with no lots to back it, so the next stock adjustment recalculated
        # the total from lots and "lost" the opening stock. Caught by
        # test_adjust_stock_moves_the_quantity.
        quantity_on_hand=0,
        reorder_level=reorder_level,
        created_by=actor.id,
        updated_by=actor.id,
    )

    # `add` stages the object; `commit` writes it and ends the transaction.
    session.add(product)
    session.flush()

    if quantity_on_hand > 0:
        # Opening stock, with NO expiry date - the same shape and meaning as
        # the rows the backfill migration created for products that already
        # existed. Unknown expiry is never marked down and is consumed last.
        #
        # Written directly rather than through `lots.receive_lot`, because that
        # function requires `lot.write` and creating a product with an opening
        # count requires `product.create`. Demanding both would break every
        # existing caller for no safety gain: the quantity is one this actor
        # was already authorised to set.
        session.add(
            InventoryLot(
                product_id=product.id,
                lot_code=lots.OPENING_LOT_CODE,
                expiry_date=None,
                quantity=quantity_on_hand,
                cost_price=cost_price,
                created_by=actor.id,
                created_via=ClientType.SYSTEM.value,
            )
        )
        session.flush()
        lots.recalculate_on_hand(session, product)

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
    require_permission(actor, "product.update")

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
    require_permission(actor, "stock.adjust")

    if delta == 0:
        raise ValidationError("Stock adjustment cannot be zero.")

    product = get_product(session, actor, product_id=product_id)

    if delta < 0:
        # Removing stock takes it off real lots, soonest expiry first, and
        # `lots.consume` recalculates the summary. It raises ValidationError
        # with the same "only N in stock" wording this function used to raise
        # itself, so the message a caller sees has not changed.
        lots.consume(session, actor, product_id=product.id, quantity=-delta)
    else:
        # Adding stock without a delivery note. There is no lot code, no
        # expiry date and no supplier - this is the "I counted the shelf and
        # found three more" case, not a delivery.
        #
        # It goes into a single dedicated correction lot per product, with NO
        # expiry date, rather than a new lot per adjustment. Two reasons: a
        # shop that recounts weekly would otherwise accumulate a lot per
        # recount forever, and an undated lot is consumed last, so a
        # correction can never displace real dated stock in the FEFO order.
        #
        # Deliveries with real expiry dates come through `lots.receive_lot`,
        # which is what the receiving screen and the agent both call.
        lot = _correction_lot(session, actor, product=product)
        lot.quantity += delta
        lot.updated_by = actor.id
        session.flush()
        lots.recalculate_on_hand(session, product)

    product.updated_by = actor.id

    session.commit()
    session.refresh(product)
    return product


# The lot_code every unexplained increase lands in. One per product, created
# on first use.
CORRECTION_LOT_CODE = "ADJUSTMENT"


def _correction_lot(session: Session, actor: Actor, *, product: Product) -> InventoryLot:
    """This product's correction lot, created if it does not exist yet.

    Private because nothing outside stock adjustment should be writing to a lot
    with no expiry date and no provenance - a delivery has both, and
    `lots.receive_lot` is the door for those.
    """
    existing = session.execute(
        select(InventoryLot).where(
            InventoryLot.product_id == product.id,
            InventoryLot.lot_code == CORRECTION_LOT_CODE,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    lot = InventoryLot(
        product_id=product.id,
        lot_code=CORRECTION_LOT_CODE,
        expiry_date=None,
        quantity=0,
        cost_price=product.cost_price,
        created_by=actor.id,
        created_via=ClientType.SYSTEM.value,
    )
    session.add(lot)
    session.flush()
    return lot
