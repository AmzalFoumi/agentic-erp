"""The SUPPLIER_REORDER draft type: what it accepts, and what approving it does."""

from decimal import Decimal

import pytest

from core.enums import ClientType, DraftStatus, PurchaseOrderStatus
from core.exceptions import PermissionDeniedError, ValidationError
from services import draft_types, drafts as draft_queue
from services.purchasing import catalog, reorder, suppliers
from services.purchasing import drafts as purchasing_drafts
from tests.test_purchasing_reorder import _link, _product, _supplier
from tests.test_purchasing_suppliers import _Actor

PROPOSER = _Actor("purchasing.read", "draft.create")
APPROVER = _Actor(
    "purchasing.read", "purchasing.write", "draft.read", "draft.decide"
)


def _a_bundle(session, unique_sku):
    supplier = _supplier(session, f"S-{unique_sku}")
    product = _product(session, f"{unique_sku}-X", on_hand=0, level=10)
    _link(session, supplier, product, cost=Decimal("1.50"))
    return supplier, product


# --- registration ----------------------------------------------------------


def test_the_type_is_registered():
    assert purchasing_drafts.SUPPLIER_REORDER in draft_types.registered_types()


# --- the payload schema ----------------------------------------------------


def test_a_payload_needs_at_least_one_line():
    with pytest.raises(ValidationError):
        draft_types.validate_payload(
            purchasing_drafts.SUPPLIER_REORDER,
            {"supplier_id": 1, "expected_date": None, "lines": []},
        )


def test_one_product_cannot_appear_on_two_lines():
    """The same defect gate 28 found in the markdown payload.

    Two lines for one product means the last one silently wins - and a manager
    editing the proposal on the approval screen is exactly how a duplicate
    gets in.
    """
    with pytest.raises(ValidationError):
        draft_types.validate_payload(
            purchasing_drafts.SUPPLIER_REORDER,
            {
                "supplier_id": 1,
                "expected_date": None,
                "lines": [
                    {"product_id": 7, "quantity": 1, "unit_cost": "1.00"},
                    {"product_id": 7, "quantity": 2, "unit_cost": "1.00"},
                ],
            },
        )


def test_a_zero_quantity_line_is_refused():
    with pytest.raises(ValidationError):
        draft_types.validate_payload(
            purchasing_drafts.SUPPLIER_REORDER,
            {
                "supplier_id": 1,
                "expected_date": None,
                "lines": [{"product_id": 7, "quantity": 0, "unit_cost": "1.00"}],
            },
        )


# --- proposing -------------------------------------------------------------


def test_proposing_stages_a_draft_and_creates_no_order(session, unique_sku):
    supplier, _ = _a_bundle(session, unique_sku)

    draft = purchasing_drafts.propose_reorder(
        session,
        PROPOSER,
        client=ClientType.MCP_AGENT,
        supplier_id=supplier.id,
        reasoning="Milk is out and DairyCo deliver Tuesday.",
    )

    assert draft.status == DraftStatus.PENDING.value
    assert draft.draft_type == purchasing_drafts.SUPPLIER_REORDER

    from services.purchasing import orders

    found, total = orders.list_orders(session, APPROVER, supplier_id=supplier.id)
    assert total == 0


def test_proposing_needs_draft_create_not_purchasing_write(session, unique_sku):
    """The agent proposes with read + draft.create and nothing more."""
    supplier, _ = _a_bundle(session, unique_sku)
    no_draft_permission = _Actor("purchasing.read")

    with pytest.raises(PermissionDeniedError):
        purchasing_drafts.propose_reorder(
            session,
            no_draft_permission,
            client=ClientType.MCP_AGENT,
            supplier_id=supplier.id,
        )


def test_proposing_for_a_supplier_with_nothing_low_is_refused(session, unique_sku):
    """An empty proposal is noise in a queue whose whole value is that
    everything in it needs a decision."""
    supplier = _supplier(session, f"Quiet-{unique_sku}")

    with pytest.raises(ValidationError):
        purchasing_drafts.propose_reorder(
            session,
            PROPOSER,
            client=ClientType.MCP_AGENT,
            supplier_id=supplier.id,
        )


# --- approving -------------------------------------------------------------


def test_approving_creates_a_purchase_order_in_draft_not_sent(session, unique_sku):
    """A person still presses send.

    That second step is not ceremony: it is the last point at which someone can
    look at the whole order before it counts as placed.
    """
    supplier, product = _a_bundle(session, unique_sku)
    draft = purchasing_drafts.propose_reorder(
        session,
        PROPOSER,
        client=ClientType.MCP_AGENT,
        supplier_id=supplier.id,
        reasoning="Low.",
    )

    draft_queue.approve_draft(
        session, APPROVER, client=ClientType.WEB_UI, draft_id=draft.id
    )

    from services.purchasing import orders

    found, total = orders.list_orders(session, APPROVER, supplier_id=supplier.id)
    assert total == 1
    assert found[0].status == PurchaseOrderStatus.DRAFT.value
    assert found[0].source_draft_id == draft.id
    assert [line.product_id for line in found[0].lines] == [product.id]


def test_an_approver_without_purchasing_write_is_refused(session, unique_sku):
    supplier, _ = _a_bundle(session, unique_sku)
    draft = purchasing_drafts.propose_reorder(
        session,
        PROPOSER,
        client=ClientType.MCP_AGENT,
        supplier_id=supplier.id,
        reasoning="Low.",
    )
    decider_only = _Actor("draft.read", "draft.decide")

    with pytest.raises(PermissionDeniedError):
        draft_queue.approve_draft(
            session, decider_only, client=ClientType.WEB_UI, draft_id=draft.id
        )
