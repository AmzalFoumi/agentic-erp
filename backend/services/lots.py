"""Inventory lots: receiving stock, consuming it, and keeping the summary honest.

### The one rule this module exists to enforce

Lots are the source of truth. `Product.quantity_on_hand` is a *summary* of
them, and `recalculate_on_hand()` below is the only function anywhere that
writes it.

Every operation that changes a lot calls it before committing. If a second
write path ever appears, the summary drifts from the rows it summarises - and a
drifted total is invisible until somebody counts the shelf by hand and finds
the system was wrong for a month.

### FEFO: first-expiring, first-out

When stock is removed, it comes off the lot that expires soonest. That is what
a shop actually does, and it is why the rule lives here rather than in an
adapter: no two callers may disagree about which carton left the building.

Lots with no expiry date are consumed **last**, after every dated lot. They are
the "was already on the shelf before we tracked this" stock created by the
backfill migration, and taking them first would let real, dated stock sit and
spoil while undated stock churned.

### What this module does NOT do

It does not decide prices and it does not know what spoilage is. `pricing.py`
holds the money arithmetic and `spoilage.py` holds the feature. This module
knows about quantities, expiry dates and who moved what.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.actor import Actor
from core.enums import ClientType
from core.exceptions import NotFoundError, ValidationError
from core.models import InventoryLot, Product
from services.guards import require_permission

# The lot_code the backfill migration used. Named here so that code and
# migration cannot drift apart on a magic string.
OPENING_LOT_CODE = "OPENING"


def _get_product_or_raise(session: Session, product_id: int) -> Product:
    """The product, or NotFoundError.

    Private, and deliberately not routed through `products.get_product`: that
    function performs its own `product.read` permission check, and a caller who
    already holds `lot.write` should not additionally need `product.read` to
    receive a delivery. Permissions are checked once, by the public function
    the caller actually called.
    """
    product = session.get(Product, product_id)
    if product is None:
        raise NotFoundError(f"Product {product_id} does not exist.")
    return product


def recalculate_on_hand(session: Session, product: Product) -> int:
    """Reset `product.quantity_on_hand` to the sum of its lots. Returns the sum.

    ⚠️ **THE SINGLE WRITE PATH.** Nothing else in the codebase may assign to
    `quantity_on_hand`. If you are about to, call this instead.

    It does not commit, and it does not check permissions. It is a step inside
    somebody else's unit of work - the caller has already checked the
    permission for the operation it is part of, and the caller decides when the
    transaction ends. A commit here would split one business action into two.

    `COALESCE(SUM(...), 0)` because SUM over zero rows is NULL in SQL, not 0.
    Without it, removing a product's last lot would write NULL into a NOT NULL
    column and fail at flush time with an error naming the column rather than
    the cause.
    """
    total = session.execute(
        select(func.coalesce(func.sum(InventoryLot.quantity), 0)).where(
            InventoryLot.product_id == product.id
        )
    ).scalar_one()

    product.quantity_on_hand = int(total)
    return int(total)


def list_lots(
    session: Session,
    actor: Actor,
    *,
    product_id: int,
    include_empty: bool = False,
) -> list[InventoryLot]:
    """A product's lots, soonest expiry first.

    `include_empty=False` by default because a lot emptied by FEFO consumption
    is history, not stock, and a shelf-level view asking "what have we got"
    should not be padded with zeros. History is still there for anything that
    asks for it.

    The ordering puts undated lots last, matching the consumption order in
    `consume()`. Two views that claim to show the same lots in the same order
    should agree, and the cheapest way to guarantee that is to write the
    ordering once.
    """
    require_permission(actor, "lot.read")
    _get_product_or_raise(session, product_id)

    statement = select(InventoryLot).where(InventoryLot.product_id == product_id)
    if not include_empty:
        statement = statement.where(InventoryLot.quantity > 0)

    # `nulls_last()` is explicit on purpose. Postgres sorts NULLs last in ASC
    # by default, but that is a dialect default rather than a promise, and this
    # ordering is a business rule ("undated stock is used last") that should
    # not quietly depend on one.
    statement = statement.order_by(
        InventoryLot.expiry_date.asc().nulls_last(), InventoryLot.id.asc()
    )
    return list(session.execute(statement).scalars())


def receive_lot(
    session: Session,
    actor: Actor,
    *,
    client: ClientType,
    product_id: int,
    lot_code: str,
    quantity: int,
    cost_price: Decimal | None = None,
    expiry_date: date | None = None,
    source_draft_id: int | None = None,
) -> InventoryLot:
    """Book a delivery in as a new lot, and update the product's total.

    `cost_price` defaults to the product's current cost price when the caller
    does not know it. It is then **frozen on the lot**: when the supplier
    raises their price next month, this lot still records what was actually
    paid, which is the only thing that makes "cost at risk" a truthful number.

    `expiry_date` is optional, and None genuinely means "unknown" rather than
    "never expires". The spoilage scan skips those lots rather than guessing.

    A past expiry date is accepted. It looks like a mistake and is sometimes
    real - stock is occasionally booked in days after it physically arrived,
    and refusing it would leave the shop unable to record what is on its own
    shelf. The spoilage report is where already-expired stock gets noticed.
    """
    require_permission(actor, "lot.write")

    if quantity <= 0:
        raise ValidationError("A received lot must have a positive quantity.")

    lot_code = lot_code.strip()
    if not lot_code:
        raise ValidationError("A received lot must have a lot code.")

    product = _get_product_or_raise(session, product_id)

    if cost_price is None:
        cost_price = product.cost_price
    if cost_price < 0:
        raise ValidationError("Cost price cannot be negative.")

    lot = InventoryLot(
        product_id=product.id,
        lot_code=lot_code,
        expiry_date=expiry_date,
        quantity=quantity,
        cost_price=cost_price,
        created_by=actor.id,
        created_via=client.value,
        source_draft_id=source_draft_id,
    )
    session.add(lot)

    # Flush before recalculating: the new lot has no id yet and, more to the
    # point, is not visible to the SUM query until it reaches the database.
    # Without this the product's total would be short by exactly this delivery.
    session.flush()

    recalculate_on_hand(session, product)
    product.updated_by = actor.id

    session.commit()
    session.refresh(lot)
    return lot


def consume(
    session: Session,
    actor: Actor,
    *,
    product_id: int,
    quantity: int,
) -> list[InventoryLot]:
    """Take `quantity` off a product's lots, soonest expiry first.

    Returns the lots that were touched, so a caller can report what actually
    left rather than only how much.

    ⚠️ **No permission check, and no commit.** This is an internal step called
    by whoever already checked the permission for the operation it belongs to -
    today that is `products.adjust_stock` holding `stock.adjust`. Adding a
    check here would mean an operator needed two permissions to do one thing,
    and would put the decision in two places.

    It is not exported through any adapter for the same reason.
    """
    if quantity <= 0:
        raise ValidationError("Consumed quantity must be positive.")

    product = _get_product_or_raise(session, product_id)

    # Ordering identical to `list_lots`, deliberately: dated stock first,
    # soonest first, undated last.
    lots = list(
        session.execute(
            select(InventoryLot)
            .where(InventoryLot.product_id == product_id, InventoryLot.quantity > 0)
            .order_by(InventoryLot.expiry_date.asc().nulls_last(), InventoryLot.id.asc())
        ).scalars()
    )

    available = sum(lot.quantity for lot in lots)
    if available < quantity:
        # Checked up front rather than discovered halfway through the loop.
        # A partial consumption would leave the earliest lots emptied and the
        # caller's transaction rolled back - correct, but only because of the
        # rollback, which is a fragile thing to rely on.
        raise ValidationError(
            f"Cannot remove {quantity} of {product.sku}: only {available} in stock."
        )

    remaining = quantity
    touched: list[InventoryLot] = []
    for lot in lots:
        if remaining == 0:
            break
        taken = min(lot.quantity, remaining)
        lot.quantity -= taken
        lot.updated_by = actor.id
        remaining -= taken
        touched.append(lot)

    session.flush()
    recalculate_on_hand(session, product)
    product.updated_by = actor.id
    return touched


def expiring_lots(
    session: Session,
    actor: Actor,
    *,
    within_days: int,
    today: date,
) -> list[InventoryLot]:
    """Lots holding stock that expires within `within_days` of `today`.

    ⚠️ Lots with **no expiry date are excluded**, by the `IS NOT NULL` that the
    `<=` comparison performs implicitly in SQL. That is the rule the backfill
    migration depends on: stock that predates expiry tracking must never
    trigger a markdown, because nobody knows when it goes off.

    Already-expired lots ARE included - a negative day count is still `<=` the
    cutoff. Excluding them would hide the worst stock in the shop from the
    report whose entire job is to find it.

    `today` is passed in rather than read from the clock so that the whole
    feature can be tested at a fixed point in time. See `pricing.days_until`.
    """
    require_permission(actor, "lot.read")

    if within_days < 0:
        raise ValidationError("within_days cannot be negative.")

    cutoff = date.fromordinal(today.toordinal() + within_days)

    return list(
        session.execute(
            select(InventoryLot)
            .where(
                InventoryLot.quantity > 0,
                InventoryLot.expiry_date <= cutoff,
            )
            .order_by(InventoryLot.expiry_date.asc(), InventoryLot.id.asc())
        ).scalars()
    )
