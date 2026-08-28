"""DELIVERY_RECEIPT: propose a receipt, approve it, watch it apply."""

from datetime import date
from decimal import Decimal

import pytest

from core.actor import SystemActor
from core.enums import ClientType, PurchaseOrderStatus
from core.exceptions import PermissionDeniedError, ValidationError
from services import drafts as draft_queue
from services import purchasing
from services.purchasing.drafts import DELIVERY_RECEIPT, propose_receipt
from services.purchasing.orders import OrderLineInput
from tests.test_purchasing_suppliers import _Actor


@pytest.fixture
def product(session, unique_sku):
    from services import products

    return products.create_product(
        session,
        SystemActor(),
        sku=unique_sku,
        name="Receiving Draft Test Product",
        unit="unit",
        cost_price=Decimal("1.00"),
        sell_price=Decimal("2.00"),
    )


@pytest.fixture
def sent_order(session, product):
    supplier = purchasing.create_supplier(
        session,
        SystemActor(),
        client=ClientType.SYSTEM,
        name="Draft Receiving Supplier",
        lead_time_days=2,
        minimum_order_value=Decimal("0.00"),
    )
    order = purchasing.create_order(
        session,
        SystemActor(),
        client=ClientType.SYSTEM,
        supplier_id=supplier.id,
        lines=[OrderLineInput(product_id=product.id, quantity=50, unit_cost=Decimal("2.00"))],
    )
    return purchasing.send_order(
        session, SystemActor(), order_id=order.id, today=date(2026, 8, 27)
    )


def test_propose_receipt_creates_a_pending_draft_and_touches_nothing_else(
    session, sent_order, product
):
    draft = propose_receipt(
        session,
        SystemActor(),
        client=ClientType.MCP_AGENT,
        order_id=sent_order.id,
        lines=[
            {
                "product_id": product.id,
                "quantity_received": 40,
                "quantity_damaged": 0,
                "expiry_date": "2026-09-10",
                "lot_code": "DN-DRAFT-1",
            }
        ],
        reasoning="Dock worker said 40 of 50 cases arrived.",
    )
    assert draft.draft_type == DELIVERY_RECEIPT
    assert draft.status == "pending"

    session.refresh(sent_order)
    assert sent_order.status == PurchaseOrderStatus.SENT.value  # unchanged until approved


def test_approving_a_receipt_draft_applies_it_and_records_provenance(
    session, sent_order, product
):
    draft = propose_receipt(
        session,
        SystemActor(),
        client=ClientType.MCP_AGENT,
        order_id=sent_order.id,
        lines=[
            {
                "product_id": product.id,
                "quantity_received": 48,
                "quantity_damaged": 2,
                "expiry_date": "2026-09-10",
                "lot_code": "DN-DRAFT-2",
            }
        ],
        reasoning="Dock worker: 2 crushed, rest fine.",
    )

    approved = draft_queue.approve_draft(
        session, SystemActor(), client=ClientType.WEB_UI, draft_id=draft.id
    )
    assert approved.status == "executed"

    session.refresh(sent_order)
    assert sent_order.status == PurchaseOrderStatus.PARTIALLY_RECEIVED.value

    from core.models import CreditMemo
    from sqlalchemy import select

    memo = session.execute(
        select(CreditMemo).where(CreditMemo.purchase_order_id == sent_order.id)
    ).scalar_one()
    assert memo.source_draft_id == draft.id


def test_an_approver_without_purchasing_write_cannot_apply_a_receipt_draft(
    session, sent_order, product
):
    """draft.decide alone is not enough to get a DELIVERY_RECEIPT applied.

    `_apply_receipt` is the shared core both doors call, and it must check
    `purchasing.write` itself - not just trust the caller to have checked it -
    or an approver holding `draft.decide` and `lot.write` but not
    `purchasing.write` could approve their way into receiving stock. Same
    shape as test_purchasing_drafts.py's
    test_an_approver_without_purchasing_write_is_refused for SUPPLIER_REORDER.
    """
    draft = propose_receipt(
        session,
        SystemActor(),
        client=ClientType.MCP_AGENT,
        order_id=sent_order.id,
        lines=[
            {
                "product_id": product.id,
                "quantity_received": 40,
                "quantity_damaged": 0,
                "expiry_date": "2026-09-10",
                "lot_code": "DN-DRAFT-PERM",
            }
        ],
        reasoning="Dock worker said 40 of 50 cases arrived.",
    )
    decider_only = _Actor("draft.read", "draft.decide", "lot.write")

    with pytest.raises(PermissionDeniedError):
        draft_queue.approve_draft(
            session, decider_only, client=ClientType.WEB_UI, draft_id=draft.id
        )


def test_a_duplicate_product_line_is_refused(session, sent_order, product):
    with pytest.raises(ValidationError):
        propose_receipt(
            session,
            SystemActor(),
            client=ClientType.MCP_AGENT,
            order_id=sent_order.id,
            lines=[
                {
                    "product_id": product.id,
                    "quantity_received": 20,
                    "quantity_damaged": 0,
                    "expiry_date": "2026-09-10",
                    "lot_code": "DN-DUP-1",
                },
                {
                    "product_id": product.id,
                    "quantity_received": 20,
                    "quantity_damaged": 0,
                    "expiry_date": "2026-09-10",
                    "lot_code": "DN-DUP-2",
                },
            ],
            reasoning="Two lines, same product.",
        )
