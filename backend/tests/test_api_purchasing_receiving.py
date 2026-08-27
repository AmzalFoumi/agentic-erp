"""HTTP surface for gate 30 receiving. Translation only - the rules are
tested in services (tests/test_purchasing_receiving.py and
tests/test_purchasing_receiving_drafts.py)."""

from datetime import date
from decimal import Decimal

import pytest

from core.actor import SystemActor
from core.enums import ClientType
from services import purchasing
from services.purchasing.orders import OrderLineInput


@pytest.fixture
def product(session, unique_sku):
    from services import products

    return products.create_product(
        session,
        SystemActor(),
        sku=unique_sku,
        name="API Receiving Test Product",
        unit="unit",
        cost_price=Decimal("1.00"),
        sell_price=Decimal("2.00"),
    )


@pytest.fixture
def sent_order_id(session, product):
    supplier = purchasing.create_supplier(
        session,
        SystemActor(),
        client=ClientType.SYSTEM,
        name="API Receiving Supplier",
        lead_time_days=1,
        minimum_order_value=Decimal("0.00"),
    )
    order = purchasing.create_order(
        session,
        SystemActor(),
        client=ClientType.SYSTEM,
        supplier_id=supplier.id,
        lines=[OrderLineInput(product_id=product.id, quantity=10, unit_cost=Decimal("5.00"))],
    )
    sent = purchasing.send_order(session, SystemActor(), order_id=order.id, today=date(2026, 8, 27))
    session.commit()
    return sent.id


def test_receive_endpoint_applies_immediately(client, sent_order_id, product):
    response = client.post(
        f"/purchase-orders/{sent_order_id}/receive",
        json={
            "lines": [
                {
                    "product_id": product.id,
                    "quantity_received": 10,
                    "quantity_damaged": 0,
                    "expiry_date": "2026-09-15",
                    "lot_code": "DN-API-1",
                }
            ]
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "received"
    assert body["lines"][0]["quantity_received"] == 10


def test_receipt_draft_endpoint_stages_without_applying(client, sent_order_id, product):
    response = client.post(
        f"/purchase-orders/{sent_order_id}/receipt-drafts",
        json={
            "lines": [
                {
                    "product_id": product.id,
                    "quantity_received": 8,
                    "quantity_damaged": 0,
                    "expiry_date": "2026-09-15",
                    "lot_code": "DN-API-2",
                }
            ],
            "reasoning": "Dock worker said 8 of 10.",
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "pending"


def test_order_detail_includes_credit_memos_from_a_short_shipment(client, sent_order_id, product):
    receive_response = client.post(
        f"/purchase-orders/{sent_order_id}/receive",
        json={
            "lines": [
                {
                    "product_id": product.id,
                    "quantity_received": 7,
                    "quantity_damaged": 0,
                    "expiry_date": "2026-09-15",
                    "lot_code": "DN-API-4",
                }
            ]
        },
    )
    assert receive_response.status_code == 200

    detail_response = client.get(f"/purchase-orders/{sent_order_id}")
    assert detail_response.status_code == 200
    body = detail_response.json()
    assert len(body["credit_memos"]) == 1
    memo = body["credit_memos"][0]
    assert memo["reason"] == "short_shipped"
    assert memo["amount"] == "15.00"  # 3 short * 5.00 unit_cost


def test_an_unknown_order_is_not_found(client, product):
    response = client.post(
        "/purchase-orders/999999/receive",
        json={
            "lines": [
                {
                    "product_id": product.id,
                    "quantity_received": 1,
                    "quantity_damaged": 0,
                    "expiry_date": "2026-09-15",
                    "lot_code": "DN-API-3",
                }
            ]
        },
    )
    assert response.status_code == 404
    assert "error" in response.json()
