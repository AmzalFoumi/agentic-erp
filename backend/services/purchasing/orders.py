"""Purchase orders: create, send, cancel - and the rule about what may follow what.

### The state machine lives here and only here

    draft ──▶ sent ──▶ partially_received ──▶ received
      │         │
      └────▶ cancelled ◀────┘

`partially_received` and `received` are declared and unreachable until gate 30.

This is in `services/` rather than in an adapter because there are two adapters
and an adapter cannot be trusted to enforce a legal transition - there will be
two implementations of the rule and they will drift. A shop where the website
and the agent disagree about whether an order can be cancelled is a shop that
cancels an order twice.

### Lines are frozen once the order leaves `draft`

Gate 30 compares what arrived against what was ordered. An editable sent order
makes that comparison meaningless, so there is deliberately no function here
that edits the lines of a sent order.

### `total_value` has exactly one write path

`_recalculate_total` below. Nothing else in `services/` may assign to it, and
`tests/test_purchasing_orders.py` fails if anything does. Same rule and same
protection as `Product.quantity_on_hand` in gate 28.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from core.actor import Actor
from core.enums import ClientType, PurchaseOrderStatus
from core.exceptions import NotFoundError, ValidationError
from core.models import Product, PurchaseOrder, PurchaseOrderLine
from services.guards import require_permission
from services.purchasing import _repository as repo

# What may follow what. A dict rather than a chain of ifs, so the whole rule is
# one thing you can read - and so a new state is one entry rather than a hunt
# through branches.
LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    PurchaseOrderStatus.DRAFT.value: frozenset(
        {PurchaseOrderStatus.SENT.value, PurchaseOrderStatus.CANCELLED.value}
    ),
    PurchaseOrderStatus.SENT.value: frozenset(
        {
            PurchaseOrderStatus.PARTIALLY_RECEIVED.value,
            PurchaseOrderStatus.RECEIVED.value,
            PurchaseOrderStatus.CANCELLED.value,
        }
    ),
    PurchaseOrderStatus.PARTIALLY_RECEIVED.value: frozenset(
        {PurchaseOrderStatus.RECEIVED.value}
    ),
    PurchaseOrderStatus.RECEIVED.value: frozenset(),
    PurchaseOrderStatus.CANCELLED.value: frozenset(),
}


@dataclass(frozen=True)
class OrderLineInput:
    """One line a caller wants on a new order.

    Frozen, and deliberately not the ORM model: a caller describing an order
    should not be handing us half-built database rows. `unit_cost` is supplied
    by the caller rather than read from the supplier link, because the price
    that goes on the order is the price that was agreed - which may be the one
    a manager typed on the approval screen.
    """

    product_id: int
    quantity: int
    unit_cost: Decimal


def _get_or_raise(session: Session, order_id: int) -> PurchaseOrder:
    order = repo.get_order(session, order_id)
    if order is None:
        raise NotFoundError(f"Purchase order {order_id} does not exist.")
    return order


def _require_transition(order: PurchaseOrder, to_status: str) -> None:
    """Refuse an illegal move, naming both ends so the message is actionable."""
    allowed = LEGAL_TRANSITIONS.get(order.status, frozenset())
    if to_status not in allowed:
        raise ValidationError(
            f"A purchase order that is {order.status!r} cannot become "
            f"{to_status!r}."
        )


def _recalculate_total(session: Session, order: PurchaseOrder) -> Decimal:
    """Reset `order.total_value` to the sum of its lines. Returns the sum.

    ⚠️ **THE SINGLE WRITE PATH.** Nothing else may assign to `total_value`. If
    you are about to, call this instead.

    No commit and no permission check: it is a step inside somebody else's unit
    of work, exactly like `lots.recalculate_on_hand`.
    """
    total = repo.sum_line_values(session, order.id)
    order.total_value = Decimal(total)
    return Decimal(total)


def create_order(
    session: Session,
    actor: Actor,
    *,
    client: ClientType,
    supplier_id: int,
    lines: Sequence[OrderLineInput],
    notes: str | None = None,
    source_draft_id: int | None = None,
    commit: bool = True,
) -> PurchaseOrder:
    """Raise a new order in `draft`.

    `commit=False` exists for one caller: the draft handler in `drafts.py`,
    which runs inside `drafts.approve_draft`'s transaction. That function owns
    the transaction - committing here would split one business action into two,
    and a failure after the split would leave a draft marked executed beside an
    order that no longer exists.
    """
    require_permission(actor, "purchasing.write")

    if not lines:
        raise ValidationError("A purchase order must have at least one line.")

    supplier = repo.get_supplier(session, supplier_id)
    if supplier is None:
        raise NotFoundError(f"Supplier {supplier_id} does not exist.")
    if not supplier.is_active:
        raise ValidationError(f"Supplier {supplier_id} is no longer active.")

    seen: set[int] = set()
    for line in lines:
        if line.quantity <= 0:
            raise ValidationError("Every order line must have a positive quantity.")
        if line.unit_cost < 0:
            raise ValidationError("A unit cost cannot be negative.")
        if line.product_id in seen:
            raise ValidationError(
                f"Product {line.product_id} appears on this order more than once."
            )
        seen.add(line.product_id)
        if session.get(Product, line.product_id) is None:
            raise NotFoundError(f"Product {line.product_id} does not exist.")

    order = PurchaseOrder(
        supplier_id=supplier_id,
        status=PurchaseOrderStatus.DRAFT.value,
        notes=notes,
        source_draft_id=source_draft_id,
        created_by=actor.id,
        created_via=client.value,
    )
    session.add(order)
    # Flush so the order has an id for its lines to point at.
    session.flush()

    for line in lines:
        session.add(
            PurchaseOrderLine(
                purchase_order_id=order.id,
                product_id=line.product_id,
                quantity_ordered=line.quantity,
                unit_cost=line.unit_cost,
                created_by=actor.id,
            )
        )

    # Flush again: the lines are not visible to the SUM query until they reach
    # the database, so without this the total would be zero on every new order.
    session.flush()
    _recalculate_total(session, order)

    if commit:
        session.commit()
        session.refresh(order)
    return order


def send_order(
    session: Session, actor: Actor, *, order_id: int, today: date
) -> PurchaseOrder:
    """Place the order with the supplier. Freezes the lines.

    `expected_date` is computed **here**, not when the order was proposed: the
    lead time counts from the day the order was actually placed. A draft
    approved on Friday and sent on Monday must not claim Friday's arrival date.

    `today` is a parameter rather than a call to `date.today()` for the reason
    every date in this codebase is - a service that reads the clock can only be
    tested by changing the clock.
    """
    require_permission(actor, "purchasing.write")

    order = _get_or_raise(session, order_id)
    _require_transition(order, PurchaseOrderStatus.SENT.value)

    supplier = repo.get_supplier(session, order.supplier_id)
    if supplier is None:  # pragma: no cover - the FK makes this unreachable
        raise NotFoundError(f"Supplier {order.supplier_id} does not exist.")
    # Checked again here, not only in `create_order`: deactivation is how a
    # supplier is retired, and a draft raised before that happened must not
    # still be placeable afterwards. Cancelling it stays legal.
    if not supplier.is_active:
        raise ValidationError(f"Supplier {order.supplier_id} is no longer active.")

    order.status = PurchaseOrderStatus.SENT.value
    order.expected_date = today + timedelta(days=supplier.lead_time_days)
    order.updated_by = actor.id

    session.commit()
    session.refresh(order)
    return order


def cancel_order(session: Session, actor: Actor, *, order_id: int) -> PurchaseOrder:
    """Abandon an order. Legal from `draft` and from `sent` - a supplier can
    still be phoned."""
    require_permission(actor, "purchasing.write")

    order = _get_or_raise(session, order_id)
    _require_transition(order, PurchaseOrderStatus.CANCELLED.value)

    order.status = PurchaseOrderStatus.CANCELLED.value
    order.updated_by = actor.id

    session.commit()
    session.refresh(order)
    return order


def get_order(session: Session, actor: Actor, *, order_id: int) -> PurchaseOrder:
    require_permission(actor, "purchasing.read")
    return _get_or_raise(session, order_id)


def list_orders(
    session: Session,
    actor: Actor,
    *,
    status: str | None = None,
    supplier_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[PurchaseOrder], int]:
    """A page of orders, newest first, with the total matching the filters."""
    require_permission(actor, "purchasing.read")

    if status is not None and status not in LEGAL_TRANSITIONS:
        raise ValidationError(f"{status!r} is not a purchase order status.")

    return repo.list_orders(
        session,
        status=status,
        supplier_id=supplier_id,
        limit=limit,
        offset=offset,
    )
