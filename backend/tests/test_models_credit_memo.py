"""The credit_memos table exists with the shape gate 30 needs."""

from decimal import Decimal

import pytest

from core.enums import ClientType, CreditMemoReason, CreditMemoStatus
from core.models import CreditMemo
from services.purchasing import orders, suppliers


class _Actor:
    def __init__(self, *perms: str) -> None:
        self.id = "tester"
        self._perms = set(perms)

    def can(self, permission: str) -> bool:
        return permission in self._perms


WRITER = _Actor("purchasing.read", "purchasing.write")


@pytest.fixture
def supplier(session, unique_sku):
    return suppliers.create_supplier(
        session,
        WRITER,
        client=ClientType.WEB_UI,
        name=f"Credit Memo Supplier {unique_sku}",
        lead_time_days=3,
    )


@pytest.fixture
def purchase_order(session, supplier, unique_sku):
    from tests.test_purchasing_suppliers import _a_product

    product = _a_product(session, unique_sku)
    return orders.create_order(
        session,
        WRITER,
        client=ClientType.WEB_UI,
        supplier_id=supplier.id,
        lines=[
            orders.OrderLineInput(
                product_id=product.id, quantity=10, unit_cost=Decimal("1.50")
            )
        ],
    )


def test_credit_memo_round_trips(session, supplier, purchase_order):
    memo = CreditMemo(
        supplier_id=supplier.id,
        purchase_order_id=purchase_order.id,
        reason=CreditMemoReason.SHORT_SHIPPED.value,
        amount=Decimal("120.50"),
        created_by="tester",
        created_via="system",
    )
    session.add(memo)
    session.commit()
    session.refresh(memo)

    assert memo.id is not None
    assert memo.status == CreditMemoStatus.OPEN.value
    assert memo.source_draft_id is None
