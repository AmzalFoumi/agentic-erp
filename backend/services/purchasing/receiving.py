"""Receiving a sent purchase order: the shared core both doors call.

### The one rule this module exists to enforce

Damaged units never become stock. Only `quantity_received` units become an
InventoryLot; `quantity_damaged` is a separate count out of the same ordered
quantity, and never becomes stock - it is a number on a credit memo only.
This is checked in exactly one place, `_apply_receipt`, so the two public
doors below - a human typing a form, or a manager approving the AI's parse of
what the dock worker said - can never disagree about it.

### Reuses services.lots.receive_lot rather than writing stock twice

`receive_lot` already does the "write a lot, recalculate quantity_on_hand"
work correctly (gate 28). Writing a second lot-creation path here would be
exactly the drift `docs/FEATURES-PLAN.md` decision 3 exists to prevent.

### Received is capped at ordered

Overshipment is out of scope for gate 30 - see the design spec's
"Alternatives considered". A line asking for more than was ordered is
refused before anything is written, not silently truncated.

### Every order line is accounted for, not just the ones in the receipt

The loop below walks `order.lines`, not the caller's receipt lines. A
receipt that leaves out a line on the order is not a no-op for that line -
it means nothing arrived for it, which is a 100% short shipment, and it
must produce a credit memo and a `partially_received` status like any other
shortfall. Before this fix the loop walked the receipt instead, so an order
line missing from the receipt was never examined at all: no credit memo,
and if every *mentioned* line was complete, the order was wrongly marked
fully `received` with no way to correct it (receiving is refused once
status leaves `sent`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from core.actor import Actor
from core.enums import ClientType, CreditMemoReason, PurchaseOrderStatus
from core.exceptions import ValidationError
from core.models import CreditMemo, PurchaseOrder
from services import lots
from services.guards import require_permission
from services.purchasing.orders import _get_or_raise


@dataclass(frozen=True)
class ReceiptLineInput:
    """What arrived for one line on the order.

    Frozen, and deliberately not the ORM model - a caller describing a
    receipt should not be handing us half-built database rows, the same
    reasoning as orders.OrderLineInput.

    `quantity_received` is the count of GOOD units only - it does not
    include `quantity_damaged`. The two are separate counts that both come
    out of the same `quantity_ordered`; their sum must not exceed it.
    """

    product_id: int
    quantity_received: int
    quantity_damaged: int
    expiry_date: date
    lot_code: str


def _find_line(order: PurchaseOrder, product_id: int):
    for line in order.lines:
        if line.product_id == product_id:
            return line
    raise ValidationError(
        f"Product {product_id} is not on purchase order {order.id}."
    )


def validate_receipt_against_order(order: PurchaseOrder, lines) -> None:
    """Order-relative checks shared by both doors: `receive_order` (via
    `_apply_receipt`) and `drafts.propose_receipt`, which stages a
    DELIVERY_RECEIPT draft before any human has approved it. Without this
    running at staging time too, an AI-proposed draft naming a product not on
    the order, or a quantity above what was ordered, could sit in the queue
    looking approvable and then always fail when a manager actually approves
    it.

    Duck-typed on `product_id` / `quantity_received` / `quantity_damaged`
    rather than `ReceiptLineInput` specifically, so `drafts.py`'s pydantic
    `ReceiptPayloadLine` can be checked here too without an import cycle.
    """
    seen: set[int] = set()
    for receipt_line in lines:
        if receipt_line.product_id in seen:
            raise ValidationError(
                f"Product {receipt_line.product_id} appears on this receipt "
                "more than once."
            )
        seen.add(receipt_line.product_id)

        if receipt_line.quantity_received < 0 or receipt_line.quantity_damaged < 0:
            raise ValidationError("Received and damaged quantities cannot be negative.")

        order_line = _find_line(order, receipt_line.product_id)
        total_accounted = receipt_line.quantity_received + receipt_line.quantity_damaged
        if total_accounted > order_line.quantity_ordered:
            raise ValidationError(
                f"Product {receipt_line.product_id}: received "
                f"({receipt_line.quantity_received}) plus damaged "
                f"({receipt_line.quantity_damaged}) exceeds the "
                f"{order_line.quantity_ordered} ordered."
            )


def _apply_receipt(
    session: Session,
    actor: Actor,
    *,
    client: ClientType,
    order: PurchaseOrder,
    lines: list[ReceiptLineInput],
    source_draft_id: int | None = None,
) -> PurchaseOrder:
    """Do the actual work of receiving. Not exported - both public doors below
    call this after their own checks.

    No commit: like every gate 29 core function, the caller (`receive_order`
    directly, or `drafts.approve_draft` via the DELIVERY_RECEIPT handler)
    owns the transaction.

    Checks `purchasing.write` itself rather than trusting the caller to have
    done it: `receive_order` below checks it too (harmless, self-documenting),
    but the draft-approval door only checked `draft.decide` before landing
    here, which meant an approver with `draft.decide` and `stock.adjust` but not
    `purchasing.write` could apply a DELIVERY_RECEIPT draft. Both public doors
    to this function must agree on what it takes to receive an order, and the
    check belongs where it cannot be bypassed.
    """
    require_permission(actor, "purchasing.write")

    if order.status != PurchaseOrderStatus.SENT.value:
        raise ValidationError(
            f"A purchase order that is {order.status!r} cannot be received."
        )

    if not lines:
        raise ValidationError("A receipt must have at least one line.")

    validate_receipt_against_order(order, lines)
    receipt_by_product: dict[int, ReceiptLineInput] = {
        receipt_line.product_id: receipt_line for receipt_line in lines
    }

    fully_received = True

    # Walk every line on the order, not just the ones the caller mentioned -
    # see "Every order line is accounted for" above.
    for order_line in order.lines:
        receipt_line = receipt_by_product.get(order_line.product_id)
        quantity_received = receipt_line.quantity_received if receipt_line else 0
        quantity_damaged = receipt_line.quantity_damaged if receipt_line else 0

        total_accounted = quantity_received + quantity_damaged
        if total_accounted > order_line.quantity_ordered:
            raise ValidationError(
                f"Product {order_line.product_id}: received "
                f"({quantity_received}) plus damaged "
                f"({quantity_damaged}) exceeds the "
                f"{order_line.quantity_ordered} ordered."
            )

        # `quantity_received` is already the count of good units - it does not
        # include `quantity_damaged`. The two are separate counts that both
        # come out of the same ordered quantity, which is exactly what
        # `total_accounted` above checked.
        good_units = quantity_received

        order_line.quantity_received = quantity_received
        order_line.quantity_damaged = quantity_damaged
        order_line.updated_by = actor.id

        if good_units > 0:
            lots.receive_lot(
                session,
                actor,
                client=client,
                product_id=order_line.product_id,
                lot_code=receipt_line.lot_code,
                quantity=good_units,
                cost_price=order_line.unit_cost,
                expiry_date=receipt_line.expiry_date,
                source_draft_id=source_draft_id,
            )

        shortfall = order_line.quantity_ordered - total_accounted
        if shortfall > 0:
            session.add(
                CreditMemo(
                    supplier_id=order.supplier_id,
                    purchase_order_id=order.id,
                    reason=CreditMemoReason.SHORT_SHIPPED.value,
                    amount=Decimal(shortfall) * order_line.unit_cost,
                    created_by=actor.id,
                    created_via=client.value,
                    source_draft_id=source_draft_id,
                )
            )
            fully_received = False

        if quantity_damaged > 0:
            session.add(
                CreditMemo(
                    supplier_id=order.supplier_id,
                    purchase_order_id=order.id,
                    reason=CreditMemoReason.DAMAGED.value,
                    amount=Decimal(quantity_damaged) * order_line.unit_cost,
                    created_by=actor.id,
                    created_via=client.value,
                    source_draft_id=source_draft_id,
                )
            )
            fully_received = False

    order.status = (
        PurchaseOrderStatus.RECEIVED.value
        if fully_received
        else PurchaseOrderStatus.PARTIALLY_RECEIVED.value
    )
    order.updated_by = actor.id

    return order


def receive_order(
    session: Session,
    actor: Actor,
    *,
    client: ClientType,
    order_id: int,
    lines: list[ReceiptLineInput],
) -> PurchaseOrder:
    """The plain-form door. Applies immediately - a human typing these numbers
    already is the review, so this does not go through the draft queue.

    Requires `purchasing.write`, same permission `send_order`/`cancel_order`
    already check - receiving is one more state transition on the same order.
    """
    require_permission(actor, "purchasing.write")

    order = _get_or_raise(session, order_id)
    _apply_receipt(session, actor, client=client, order=order, lines=lines)

    session.commit()
    session.refresh(order)
    return order
