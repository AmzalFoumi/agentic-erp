"""services/purchasing/receiving.py — the shared receiving core."""

from datetime import date
from decimal import Decimal

import pytest

from core.actor import SystemActor
from core.enums import ClientType, CreditMemoReason, PurchaseOrderStatus
from core.exceptions import PermissionDeniedError, ValidationError
from services import purchasing
from services.purchasing.orders import OrderLineInput
from services.purchasing.receiving import ReceiptLineInput, receive_order


@pytest.fixture
def product(session, unique_sku):
    from services import products

    return products.create_product(
        session,
        SystemActor(),
        sku=unique_sku,
        name="Receiving Test Product",
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
        name="Receiving Test Supplier",
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


def test_receiving_everything_ordered_moves_order_to_received(session, sent_order, product):
    result = receive_order(
        session,
        SystemActor(),
        client=ClientType.WEB_UI,
        order_id=sent_order.id,
        lines=[
            ReceiptLineInput(
                product_id=product.id,
                quantity_received=50,
                quantity_damaged=0,
                expiry_date=date(2026, 9, 10),
                lot_code="DN-TEST-1",
            )
        ],
    )
    assert result.status == PurchaseOrderStatus.RECEIVED.value
    line = result.lines[0]
    assert line.quantity_received == 50
    assert line.quantity_damaged == 0


def test_short_shipment_writes_a_credit_memo_and_partial_status(session, sent_order, product):
    result = receive_order(
        session,
        SystemActor(),
        client=ClientType.WEB_UI,
        order_id=sent_order.id,
        lines=[
            ReceiptLineInput(
                product_id=product.id,
                quantity_received=40,
                quantity_damaged=0,
                expiry_date=date(2026, 9, 10),
                lot_code="DN-TEST-2",
            )
        ],
    )
    assert result.status == PurchaseOrderStatus.PARTIALLY_RECEIVED.value

    from core.models import CreditMemo
    from sqlalchemy import select

    memos = session.execute(
        select(CreditMemo).where(CreditMemo.purchase_order_id == result.id)
    ).scalars().all()
    assert len(memos) == 1
    assert memos[0].reason == CreditMemoReason.SHORT_SHIPPED.value
    assert memos[0].amount == Decimal("20.00")  # 10 short * 2.00 unit_cost


def test_damaged_units_are_excluded_from_stock_and_credited(session, sent_order, product):
    result = receive_order(
        session,
        SystemActor(),
        client=ClientType.WEB_UI,
        order_id=sent_order.id,
        lines=[
            ReceiptLineInput(
                product_id=product.id,
                quantity_received=48,
                quantity_damaged=2,
                expiry_date=date(2026, 9, 10),
                lot_code="DN-TEST-3",
            )
        ],
    )
    assert result.status == PurchaseOrderStatus.PARTIALLY_RECEIVED.value
    line = result.lines[0]
    assert line.quantity_received == 48
    assert line.quantity_damaged == 2

    from core.models import CreditMemo
    from sqlalchemy import select

    memos = session.execute(
        select(CreditMemo).where(CreditMemo.purchase_order_id == result.id)
    ).scalars().all()
    assert len(memos) == 1
    assert memos[0].reason == CreditMemoReason.DAMAGED.value
    assert memos[0].amount == Decimal("4.00")  # 2 damaged * 2.00 unit_cost

    session.refresh(product)
    assert product.quantity_on_hand == 48  # damaged units never became stock


def test_received_quantity_above_ordered_is_rejected(session, sent_order, product):
    with pytest.raises(ValidationError):
        receive_order(
            session,
            SystemActor(),
            client=ClientType.WEB_UI,
            order_id=sent_order.id,
            lines=[
                ReceiptLineInput(
                    product_id=product.id,
                    quantity_received=51,
                    quantity_damaged=0,
                    expiry_date=date(2026, 9, 10),
                    lot_code="DN-TEST-4",
                )
            ],
        )


def test_all_units_damaged_produces_no_lot_and_one_damage_credit(
    session, sent_order, product, monkeypatch
):
    from services import lots

    calls = []
    original_receive_lot = lots.receive_lot

    def spy_receive_lot(*args, **kwargs):
        calls.append((args, kwargs))
        return original_receive_lot(*args, **kwargs)

    monkeypatch.setattr(lots, "receive_lot", spy_receive_lot)

    result = receive_order(
        session,
        SystemActor(),
        client=ClientType.WEB_UI,
        order_id=sent_order.id,
        lines=[
            ReceiptLineInput(
                product_id=product.id,
                quantity_received=0,
                quantity_damaged=50,
                expiry_date=date(2026, 9, 10),
                lot_code="DN-TEST-6",
            )
        ],
    )
    assert result.status == PurchaseOrderStatus.PARTIALLY_RECEIVED.value
    line = result.lines[0]
    assert line.quantity_received == 0
    assert line.quantity_damaged == 50

    assert calls == []  # no lot created when there are zero good units

    from core.models import CreditMemo
    from sqlalchemy import select

    memos = session.execute(
        select(CreditMemo).where(CreditMemo.purchase_order_id == result.id)
    ).scalars().all()
    assert len(memos) == 1
    assert memos[0].reason == CreditMemoReason.DAMAGED.value
    assert memos[0].amount == Decimal(50) * Decimal("2.00")

    session.refresh(product)
    assert product.quantity_on_hand == 0  # nothing became stock


def test_receiving_requires_purchasing_write(session, sent_order, product):
    class NoPermActor:
        id = "no-perms"

        def can(self, permission: str) -> bool:
            return False

    with pytest.raises(PermissionDeniedError):
        receive_order(
            session,
            NoPermActor(),
            client=ClientType.WEB_UI,
            order_id=sent_order.id,
            lines=[
                ReceiptLineInput(
                    product_id=product.id,
                    quantity_received=50,
                    quantity_damaged=0,
                    expiry_date=date(2026, 9, 10),
                    lot_code="DN-TEST-5",
                )
            ],
        )
