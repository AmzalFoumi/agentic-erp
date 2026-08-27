"""The SUPPLIER_REORDER draft type: propose an order, and create it on approval.

### The shape, matching gate 28's spoilage exactly

  scan_reorder()          READS. What to buy today. Changes nothing
  propose_reorder()       STAGES. Writes one ActionDraft row. No order exists
  _create_purchase_order() ACTS. Runs only when a human approves, and is the
                          only function here that creates an order

The agent reaches the first two. It cannot reach the third, and no MCP tool
leads to it.

### Approving creates a DRAFT order, not a sent one

A person still presses send. That is not ceremony: it is the last point at
which someone can look at the whole order before it counts as placed with a
supplier.

### Why the payload is validated twice

Once on the way in, and again on the way out by `drafts.approve_draft`. A
manager may **edit** the payload on the approval screen between those moments,
and the thing that gets applied is the edited version - so the edited version
is what must be checked. Trusting the stored payload at approval time would
mean the schema only ever guarded the agent, never the browser.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from core.actor import Actor
from core.enums import ClientType
from core.exceptions import ValidationError
from core.models import ActionDraft
from services import draft_types, drafts as draft_queue
from services.guards import require_permission
from services.purchasing import orders, reorder, receiving

# A closed name from a closed list, never a function reference. See
# docs/FEATURES-PLAN.md row 1 - a payload naming a function to call is a
# remote-code-execution shape, not a design.
SUPPLIER_REORDER = "SUPPLIER_REORDER"


class ReorderPayloadLine(BaseModel):
    """One product on the proposed order."""

    product_id: int
    quantity: int = Field(..., gt=0)
    unit_cost: Decimal = Field(..., ge=0, max_digits=10, decimal_places=2)


class ReorderPayload(BaseModel):
    """What a SUPPLIER_REORDER draft carries.

    `expected_date` is **indicative only**. `orders.send_order` recomputes it
    from the supplier's lead time at the moment the order is actually placed,
    because the lead time counts from then - a draft approved on Friday and
    sent on Monday must not claim Friday's arrival date. It is carried here so
    the approval screen can show roughly when the stock would land.
    """

    supplier_id: int
    expected_date: date | None = None
    lines: list[ReorderPayloadLine] = Field(..., min_length=1)

    @field_validator("lines")
    @classmethod
    def _one_line_per_product(
        cls, lines: list[ReorderPayloadLine]
    ) -> list[ReorderPayloadLine]:
        """Refuse a payload naming one product twice.

        The handler applies lines in order, so two lines for one product means
        the last one silently wins - and a manager editing the proposal on the
        approval screen is exactly how a duplicate gets in. Gate 28 found the
        identical defect in the markdown payload.
        """
        seen: set[int] = set()
        for line in lines:
            if line.product_id in seen:
                raise ValueError(
                    f"Product {line.product_id} appears more than once."
                )
            seen.add(line.product_id)
        return lines


def propose_reorder(
    session: Session,
    actor: Actor,
    *,
    client: ClientType,
    supplier_id: int,
    reasoning: str | None = None,
) -> ActionDraft:
    """Scan, then stage one supplier's bundle as a draft for a human.

    Returns the created `ActionDraft`. **No order is created.** The draft sits
    in the approvals queue until a human reads it, optionally edits it, and
    approves.

    Raises `ValidationError` when that supplier has nothing to order, rather
    than staging an empty draft. An empty proposal is noise in a queue whose
    entire value is that everything in it needs a decision.

    The `reasoning` a caller supplies is kept as-is - it is the agent's own
    explanation in its own words, and rewriting it would defeat the point of
    showing a human why the machine wants this.
    """
    require_permission(actor, "draft.create")

    report = reorder.scan_reorder(session, actor)
    bundle = next(
        (item for item in report.bundles if item.supplier_id == supplier_id), None
    )
    if bundle is None or not bundle.lines:
        raise ValidationError(
            f"Supplier {supplier_id} has nothing that needs reordering."
        )

    payload = {
        "supplier_id": bundle.supplier_id,
        "expected_date": None,
        "lines": [
            {
                "product_id": line.product_id,
                "quantity": line.quantity,
                "unit_cost": str(line.unit_cost),
            }
            for line in bundle.lines
        ],
    }

    if not reasoning:
        top_ups = sum(1 for line in bundle.lines if line.is_top_up)
        reasoning = (
            f"{len(bundle.lines) - top_ups} product(s) at or below their reorder "
            f"level from {bundle.supplier_name}"
        )
        if top_ups:
            reasoning += (
                f", plus {top_ups} added to reach their "
                f"{bundle.minimum_order_value} minimum order"
            )
        reasoning += f". Lead time {bundle.lead_time_days} day(s)."
        if bundle.below_minimum:
            reasoning += (
                f" ⚠️ Still {bundle.shortfall} below the minimum - there is "
                "nothing else to add."
            )

    return draft_queue.create_draft(
        session,
        actor,
        client=client,
        draft_type=SUPPLIER_REORDER,
        payload=payload,
        reasoning=reasoning,
        # Both left None deliberately. This is spending, not loss: nothing is
        # at risk and nothing is recovered. FEATURES-PLAN.md made both fields
        # nullable for exactly this case, and forcing the order's value into a
        # field named "recovery" would make the approvals screen lie.
        cost_at_risk=None,
        projected_recovery=None,
    )


def _create_purchase_order(
    session: Session,
    actor: Actor,
    client: ClientType,
    payload: ReorderPayload,
    draft: ActionDraft,
) -> None:
    """Turn an approved draft into a purchase order in `draft` status.

    ⚠️ **Does not commit.** `drafts.approve_draft` owns the transaction: it
    marks the draft executed and runs this handler as one unit of business
    work. A commit here would split that in two, and a failure after the split
    would leave a draft marked executed beside an order that no longer exists.

    Runs as the **approving human**, never as the agent - `actor` is whoever
    pressed approve, and `purchasing.write` is checked inside `create_order`.
    """
    orders.create_order(
        session,
        actor,
        client=client,
        supplier_id=payload.supplier_id,
        lines=[
            orders.OrderLineInput(
                product_id=line.product_id,
                quantity=line.quantity,
                unit_cost=line.unit_cost,
            )
            for line in payload.lines
        ],
        source_draft_id=draft.id,
        commit=False,
    )


draft_types.register(
    SUPPLIER_REORDER,
    schema=ReorderPayload,
    handler=_create_purchase_order,
)


# A second closed name from a closed list, exactly like SUPPLIER_REORDER above.
DELIVERY_RECEIPT = "DELIVERY_RECEIPT"


class ReceiptPayloadLine(BaseModel):
    """What arrived for one product on the order."""

    product_id: int
    quantity_received: int = Field(..., ge=0)
    quantity_damaged: int = Field(..., ge=0)
    expiry_date: date
    lot_code: str = Field(..., min_length=1, max_length=64)


class ReceiptPayload(BaseModel):
    """What a DELIVERY_RECEIPT draft carries."""

    order_id: int
    lines: list[ReceiptPayloadLine] = Field(..., min_length=1)

    @field_validator("lines")
    @classmethod
    def _one_line_per_product(
        cls, lines: list[ReceiptPayloadLine]
    ) -> list[ReceiptPayloadLine]:
        """Refuse a payload naming one product twice - the identical defect
        ReorderPayload guards against above, for the identical reason: a
        manager editing the payload on the approval screen is exactly how a
        duplicate gets in."""
        seen: set[int] = set()
        for line in lines:
            if line.product_id in seen:
                raise ValueError(
                    f"Product {line.product_id} appears more than once."
                )
            seen.add(line.product_id)
        return lines


def propose_receipt(
    session: Session,
    actor: Actor,
    *,
    client: ClientType,
    order_id: int,
    lines: list[dict],
    reasoning: str,
) -> ActionDraft:
    """Stage what arrived as a draft for a human. **Writes nothing operational.**

    Unlike propose_reorder, this always requires `reasoning` from the caller
    rather than generating a default - the dock worker's own words are the
    entire reason this feature exists, and losing them in favour of a
    templated string would defeat the point.
    """
    require_permission(actor, "draft.create")

    if not reasoning or not reasoning.strip():
        raise ValidationError("A delivery receipt draft must carry a reason.")

    # Confirms the order exists and is in `sent` before staging - a draft
    # proposing to receive an order that cannot legally be received yet is
    # noise nobody can approve.
    order = orders._get_or_raise(session, order_id)
    if order.status != "sent":
        raise ValidationError(
            f"Purchase order {order_id} is {order.status!r}, not 'sent', "
            "and cannot be received."
        )

    payload = {"order_id": order_id, "lines": lines}
    # Validate here too, before staging - the same reason ReorderPayload is
    # validated inside propose_reorder: an obviously malformed draft should
    # never reach the queue. Pydantic's own ValidationError is translated to
    # ours, same as services/draft_types.py does at approval time - services/
    # never lets a pydantic exception escape to a caller.
    try:
        ReceiptPayload.model_validate(payload)
    except PydanticValidationError as exc:
        raise ValidationError(str(exc)) from exc

    return draft_queue.create_draft(
        session,
        actor,
        client=client,
        draft_type=DELIVERY_RECEIPT,
        payload=payload,
        reasoning=reasoning.strip(),
        cost_at_risk=None,
        projected_recovery=None,
    )


def _apply_delivery_receipt(
    session: Session,
    actor: Actor,
    client: ClientType,
    payload: ReceiptPayload,
    draft: ActionDraft,
) -> None:
    """Runs only when a human approves. Records `source_draft_id` on every
    lot and credit memo this creates, via `receiving._apply_receipt`.

    Does not commit - `drafts.approve_draft` owns the transaction, same
    contract as `_create_purchase_order` above.
    """
    order = orders._get_or_raise(session, payload.order_id)
    receiving._apply_receipt(
        session,
        actor,
        client=client,
        order=order,
        lines=[
            receiving.ReceiptLineInput(
                product_id=line.product_id,
                quantity_received=line.quantity_received,
                quantity_damaged=line.quantity_damaged,
                expiry_date=line.expiry_date,
                lot_code=line.lot_code,
            )
            for line in payload.lines
        ],
        source_draft_id=draft.id,
    )


draft_types.register(
    DELIVERY_RECEIPT,
    schema=ReceiptPayload,
    handler=_apply_delivery_receipt,
)
