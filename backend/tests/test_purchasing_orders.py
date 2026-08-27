"""The purchase order state machine, and the one write path for total_value."""

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from core.enums import ClientType, PurchaseOrderStatus
from core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from services.purchasing import orders, suppliers
from tests.test_purchasing_suppliers import WRITER, WRITER_WITH_PRODUCTS, _a_product

TODAY = date(2026, 8, 27)


def _an_order(session, unique_sku, *, quantity=10, unit_cost=Decimal("1.50")):
    supplier = suppliers.create_supplier(
        session,
        WRITER,
        client=ClientType.WEB_UI,
        name=f"Supplier {unique_sku}",
        lead_time_days=3,
    )
    product = _a_product(session, unique_sku)
    order = orders.create_order(
        session,
        WRITER,
        client=ClientType.WEB_UI,
        supplier_id=supplier.id,
        lines=[
            orders.OrderLineInput(
                product_id=product.id, quantity=quantity, unit_cost=unit_cost
            )
        ],
    )
    return supplier, product, order


# --- creation --------------------------------------------------------------


def test_a_new_order_starts_as_a_draft(session, unique_sku):
    _, _, order = _an_order(session, unique_sku)
    assert order.status == PurchaseOrderStatus.DRAFT.value


def test_the_total_is_the_sum_of_the_lines(session, unique_sku):
    _, _, order = _an_order(session, unique_sku, quantity=10, unit_cost=Decimal("1.50"))
    assert order.total_value == Decimal("15.00")


def test_an_order_with_no_lines_is_refused(session):
    supplier = suppliers.create_supplier(
        session, WRITER, client=ClientType.WEB_UI, name="Empty"
    )
    with pytest.raises(ValidationError):
        orders.create_order(
            session,
            WRITER,
            client=ClientType.WEB_UI,
            supplier_id=supplier.id,
            lines=[],
        )


def test_creating_an_order_needs_write(session, unique_sku):
    from tests.test_purchasing_suppliers import READER

    supplier = suppliers.create_supplier(
        session, WRITER, client=ClientType.WEB_UI, name="NoWrite"
    )
    product = _a_product(session, unique_sku)
    with pytest.raises(PermissionDeniedError):
        orders.create_order(
            session,
            READER,
            client=ClientType.WEB_UI,
            supplier_id=supplier.id,
            lines=[
                orders.OrderLineInput(
                    product_id=product.id, quantity=1, unit_cost=Decimal("1.00")
                )
            ],
        )


def test_a_zero_quantity_line_is_refused(session, unique_sku):
    supplier = suppliers.create_supplier(
        session, WRITER, client=ClientType.WEB_UI, name="Zero"
    )
    product = _a_product(session, unique_sku)
    with pytest.raises(ValidationError):
        orders.create_order(
            session,
            WRITER,
            client=ClientType.WEB_UI,
            supplier_id=supplier.id,
            lines=[
                orders.OrderLineInput(
                    product_id=product.id, quantity=0, unit_cost=Decimal("1.00")
                )
            ],
        )


def test_a_duplicate_product_on_two_lines_is_refused(session, unique_sku):
    supplier = suppliers.create_supplier(
        session, WRITER, client=ClientType.WEB_UI, name="Dup"
    )
    product = _a_product(session, unique_sku)
    with pytest.raises(ValidationError):
        orders.create_order(
            session,
            WRITER,
            client=ClientType.WEB_UI,
            supplier_id=supplier.id,
            lines=[
                orders.OrderLineInput(
                    product_id=product.id, quantity=1, unit_cost=Decimal("1.00")
                ),
                orders.OrderLineInput(
                    product_id=product.id, quantity=2, unit_cost=Decimal("1.00")
                ),
            ],
        )


def test_ordering_from_an_unknown_supplier_raises(session, unique_sku):
    product = _a_product(session, unique_sku)
    with pytest.raises(NotFoundError):
        orders.create_order(
            session,
            WRITER,
            client=ClientType.WEB_UI,
            supplier_id=999999,
            lines=[
                orders.OrderLineInput(
                    product_id=product.id, quantity=1, unit_cost=Decimal("1.00")
                )
            ],
        )


def test_ordering_from_a_deactivated_supplier_is_refused(session, unique_sku):
    """Deactivation is how a supplier is retired - it has to actually stop work."""
    supplier, product, _ = _an_order(session, unique_sku)
    suppliers.update_supplier(session, WRITER, supplier_id=supplier.id, is_active=False)
    with pytest.raises(ValidationError):
        orders.create_order(
            session,
            WRITER,
            client=ClientType.WEB_UI,
            supplier_id=supplier.id,
            lines=[
                orders.OrderLineInput(
                    product_id=product.id, quantity=1, unit_cost=Decimal("1.00")
                )
            ],
        )


# --- transitions -----------------------------------------------------------


def test_sending_a_draft_moves_it_to_sent(session, unique_sku):
    _, _, order = _an_order(session, unique_sku)
    sent = orders.send_order(session, WRITER, order_id=order.id, today=TODAY)
    assert sent.status == PurchaseOrderStatus.SENT.value


def test_sending_sets_the_arrival_date_from_the_suppliers_lead_time(
    session, unique_sku
):
    """Computed at send time, not at proposal time.

    The lead time counts from the day the order was actually placed. A draft
    approved on Friday and sent on Monday must not claim Friday's arrival date.
    """
    _, _, order = _an_order(session, unique_sku)  # lead_time_days=3
    sent = orders.send_order(session, WRITER, order_id=order.id, today=TODAY)
    assert sent.expected_date == date(2026, 8, 30)


def test_an_order_cannot_be_sent_twice(session, unique_sku):
    _, _, order = _an_order(session, unique_sku)
    orders.send_order(session, WRITER, order_id=order.id, today=TODAY)
    with pytest.raises(ValidationError):
        orders.send_order(session, WRITER, order_id=order.id, today=TODAY)


def test_a_draft_cannot_be_sent_after_its_supplier_is_deactivated(session, unique_sku):
    """The draft may predate the deactivation. Placing it must still be refused."""
    supplier, _, order = _an_order(session, unique_sku)
    suppliers.update_supplier(session, WRITER, supplier_id=supplier.id, is_active=False)
    with pytest.raises(ValidationError):
        orders.send_order(session, WRITER, order_id=order.id, today=TODAY)


def test_a_draft_for_a_deactivated_supplier_can_still_be_cancelled(session, unique_sku):
    """Refusing to *send* must not strand the order with no way out."""
    supplier, _, order = _an_order(session, unique_sku)
    suppliers.update_supplier(session, WRITER, supplier_id=supplier.id, is_active=False)
    cancelled = orders.cancel_order(session, WRITER, order_id=order.id)
    assert cancelled.status == PurchaseOrderStatus.CANCELLED.value


def test_a_draft_can_be_cancelled(session, unique_sku):
    _, _, order = _an_order(session, unique_sku)
    cancelled = orders.cancel_order(session, WRITER, order_id=order.id)
    assert cancelled.status == PurchaseOrderStatus.CANCELLED.value


def test_a_sent_order_can_be_cancelled(session, unique_sku):
    """A supplier can still be phoned. This is a real transition, not a
    convenience."""
    _, _, order = _an_order(session, unique_sku)
    orders.send_order(session, WRITER, order_id=order.id, today=TODAY)
    cancelled = orders.cancel_order(session, WRITER, order_id=order.id)
    assert cancelled.status == PurchaseOrderStatus.CANCELLED.value


def test_a_cancelled_order_is_terminal(session, unique_sku):
    _, _, order = _an_order(session, unique_sku)
    orders.cancel_order(session, WRITER, order_id=order.id)
    with pytest.raises(ValidationError):
        orders.send_order(session, WRITER, order_id=order.id, today=TODAY)
    with pytest.raises(ValidationError):
        orders.cancel_order(session, WRITER, order_id=order.id)


def test_an_unknown_order_raises(session):
    with pytest.raises(NotFoundError):
        orders.get_order(session, WRITER, order_id=999999)


def test_listing_with_an_unknown_status_raises(session):
    with pytest.raises(ValidationError):
        orders.list_orders(session, WRITER, status="not-a-real-status")


# --- the single write path -------------------------------------------------


def test_total_value_is_assigned_in_exactly_one_place():
    """A source-level guard, like the one gate 28 put on quantity_on_hand.

    total_value is a maintained summary of the lines. No runtime test can catch
    the bug this prevents, because the bug is *another correct-looking
    assignment somewhere else in the tree* - the first symptom is an order
    whose total does not match its own lines, which nobody notices until they
    add up the invoice by hand.
    """
    services_dir = Path(__file__).resolve().parent.parent / "services"
    assignment = re.compile(r"\.total_value\s*=(?!=)")

    offenders = sorted(
        path.relative_to(services_dir).as_posix()
        for path in services_dir.rglob("*.py")
        if assignment.search(path.read_text(encoding="utf-8"))
    )

    assert offenders == ["purchasing/orders.py"], (
        "total_value must be written only by purchasing/orders.py::"
        "_recalculate_total. Found assignments in: " + ", ".join(offenders)
    )
