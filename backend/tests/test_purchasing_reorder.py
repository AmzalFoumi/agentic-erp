"""The bundler: who to buy from, how much, and how a short order is topped up."""

from decimal import Decimal

import pytest

from core.enums import ClientType
from services.purchasing import catalog, reorder, suppliers
from tests.test_purchasing_suppliers import (
    READER,
    WRITER,
    WRITER_WITH_PRODUCTS,
    _Actor,
)


def _product(session, sku, *, on_hand, level):
    from services import products

    return products.create_product(
        session,
        WRITER_WITH_PRODUCTS,
        sku=sku,
        name=f"Product {sku}",
        unit="each",
        cost_price=Decimal("1.00"),
        sell_price=Decimal("2.00"),
        quantity_on_hand=on_hand,
        reorder_level=level,
    )


def _supplier(session, name, *, minimum=Decimal("0.00"), lead=2):
    return suppliers.create_supplier(
        session,
        WRITER,
        client=ClientType.WEB_UI,
        name=name,
        lead_time_days=lead,
        minimum_order_value=minimum,
    )


def _link(session, supplier, product, *, cost, pack=1, preferred=False):
    return catalog.link_product(
        session,
        WRITER,
        supplier_id=supplier.id,
        product_id=product.id,
        unit_cost=cost,
        pack_size=pack,
        is_preferred=preferred,
    )


def _bundle_for(report, supplier_id):
    for bundle in report.bundles:
        if bundle.supplier_id == supplier_id:
            return bundle
    raise AssertionError(f"No bundle for supplier {supplier_id}")


# --- permission ------------------------------------------------------------


def test_scanning_needs_read(session):
    from core.exceptions import PermissionDeniedError

    with pytest.raises(PermissionDeniedError):
        reorder.scan_reorder(session, _Actor())


# --- grouping --------------------------------------------------------------


def test_low_products_are_grouped_by_their_supplier(session, unique_sku):
    supplier = _supplier(session, f"S-{unique_sku}")
    low_a = _product(session, f"{unique_sku}-A", on_hand=0, level=10)
    low_b = _product(session, f"{unique_sku}-B", on_hand=1, level=10)
    _link(session, supplier, low_a, cost=Decimal("1.00"))
    _link(session, supplier, low_b, cost=Decimal("2.00"))

    report = reorder.scan_reorder(session, READER)
    bundle = _bundle_for(report, supplier.id)

    assert {line.product_id for line in bundle.lines} == {low_a.id, low_b.id}


def test_a_low_product_nobody_stocks_is_reported_not_dropped(session, unique_sku):
    """'We cannot buy this from anyone' is information the manager needs."""
    orphan = _product(session, f"{unique_sku}-ORPHAN", on_hand=0, level=10)

    report = reorder.scan_reorder(session, READER)

    assert orphan.id in [item["product_id"] for item in report.unsourced]


def test_a_product_that_is_not_low_is_not_ordered(session, unique_sku):
    supplier = _supplier(session, f"S-{unique_sku}")
    plenty = _product(session, f"{unique_sku}-FULL", on_hand=100, level=10)
    _link(session, supplier, plenty, cost=Decimal("1.00"))

    report = reorder.scan_reorder(session, READER)

    for bundle in report.bundles:
        assert plenty.id not in [line.product_id for line in bundle.lines]


# --- choosing between two suppliers ---------------------------------------


def test_the_preferred_supplier_wins_even_when_dearer(session, unique_sku):
    cheap = _supplier(session, f"Cheap-{unique_sku}")
    preferred = _supplier(session, f"Preferred-{unique_sku}")
    product = _product(session, f"{unique_sku}-P", on_hand=0, level=10)
    _link(session, cheap, product, cost=Decimal("1.00"))
    _link(session, preferred, product, cost=Decimal("5.00"), preferred=True)

    report = reorder.scan_reorder(session, READER)

    assert product.id in [
        line.product_id for line in _bundle_for(report, preferred.id).lines
    ]


def test_the_cheaper_supplier_wins_when_neither_is_preferred(session, unique_sku):
    cheap = _supplier(session, f"Cheap-{unique_sku}")
    dear = _supplier(session, f"Dear-{unique_sku}")
    product = _product(session, f"{unique_sku}-C", on_hand=0, level=10)
    _link(session, cheap, product, cost=Decimal("1.00"))
    _link(session, dear, product, cost=Decimal("5.00"))

    report = reorder.scan_reorder(session, READER)

    assert product.id in [
        line.product_id for line in _bundle_for(report, cheap.id).lines
    ]


def test_an_inactive_supplier_is_never_chosen(session, unique_sku):
    gone = _supplier(session, f"Gone-{unique_sku}")
    active = _supplier(session, f"Active-{unique_sku}")
    product = _product(session, f"{unique_sku}-I", on_hand=0, level=10)
    _link(session, gone, product, cost=Decimal("0.10"))
    _link(session, active, product, cost=Decimal("5.00"))
    suppliers.update_supplier(session, WRITER, supplier_id=gone.id, is_active=False)

    report = reorder.scan_reorder(session, READER)

    assert product.id in [
        line.product_id for line in _bundle_for(report, active.id).lines
    ]


def test_the_same_scan_twice_gives_the_same_answer(session, unique_sku):
    """Determinism, pinned.

    Two suppliers at the same price with no preferred flag must not swap
    places between reads. The approval screen would contradict itself between
    refreshes, with real money on it.
    """
    a = _supplier(session, f"A-{unique_sku}")
    b = _supplier(session, f"B-{unique_sku}")
    product = _product(session, f"{unique_sku}-T", on_hand=0, level=10)
    _link(session, a, product, cost=Decimal("2.00"))
    _link(session, b, product, cost=Decimal("2.00"))

    first = reorder.scan_reorder(session, READER)
    second = reorder.scan_reorder(session, READER)

    assert [bundle.supplier_id for bundle in first.bundles] == [
        bundle.supplier_id for bundle in second.bundles
    ]
    assert [
        (line.product_id, line.quantity)
        for bundle in first.bundles
        for line in bundle.lines
    ] == [
        (line.product_id, line.quantity)
        for bundle in second.bundles
        for line in bundle.lines
    ]


# --- the top-up ------------------------------------------------------------


def test_a_bundle_over_the_minimum_is_left_alone(session, unique_sku):
    supplier = _supplier(session, f"S-{unique_sku}", minimum=Decimal("5.00"))
    product = _product(session, f"{unique_sku}-OK", on_hand=0, level=10)
    _link(session, supplier, product, cost=Decimal("1.00"))  # 20 units * 1.00 = 20.00

    bundle = _bundle_for(reorder.scan_reorder(session, READER), supplier.id)

    assert bundle.below_minimum is False
    assert all(line.is_top_up is False for line in bundle.lines)


def test_a_short_bundle_is_topped_up_with_the_next_product_to_run_low(
    session, unique_sku
):
    """The top-up picks by urgency, not by price.

    `nearly` has 2 units of headroom, `plenty` has 90. The one closest to
    going low is the useful thing to add, and it is the one a manager will
    accept on the order.
    """
    supplier = _supplier(session, f"S-{unique_sku}", minimum=Decimal("100.00"))
    low = _product(session, f"{unique_sku}-LOW", on_hand=0, level=5)
    nearly = _product(session, f"{unique_sku}-NEAR", on_hand=12, level=10)
    plenty = _product(session, f"{unique_sku}-PLENTY", on_hand=100, level=10)
    _link(session, supplier, low, cost=Decimal("1.00"))
    _link(session, supplier, nearly, cost=Decimal("10.00"))
    _link(session, supplier, plenty, cost=Decimal("10.00"))

    bundle = _bundle_for(reorder.scan_reorder(session, READER), supplier.id)
    top_ups = [line.product_id for line in bundle.lines if line.is_top_up]

    assert nearly.id in top_ups
    assert plenty.id not in top_ups


def test_a_bundle_that_cannot_reach_the_minimum_says_so(session, unique_sku):
    """It is never silently proposed as if it were fine.

    A manager who approves an under-minimum order and then sees a delivery
    charge has been misled by the software.
    """
    supplier = _supplier(session, f"S-{unique_sku}", minimum=Decimal("10000.00"))
    only = _product(session, f"{unique_sku}-ONLY", on_hand=0, level=1)
    _link(session, supplier, only, cost=Decimal("1.00"))

    bundle = _bundle_for(reorder.scan_reorder(session, READER), supplier.id)

    assert bundle.below_minimum is True
    assert bundle.shortfall > Decimal("0.00")


def test_the_top_up_respects_pack_size(session, unique_sku):
    supplier = _supplier(session, f"S-{unique_sku}", minimum=Decimal("100.00"))
    low = _product(session, f"{unique_sku}-L", on_hand=0, level=1)
    filler = _product(session, f"{unique_sku}-F", on_hand=11, level=10)
    _link(session, supplier, low, cost=Decimal("1.00"))
    _link(session, supplier, filler, cost=Decimal("5.00"), pack=12)

    bundle = _bundle_for(reorder.scan_reorder(session, READER), supplier.id)
    top_up = next(line for line in bundle.lines if line.product_id == filler.id)

    assert top_up.quantity % 12 == 0


# --- the report ------------------------------------------------------------


def test_the_bundle_value_matches_its_lines(session, unique_sku):
    supplier = _supplier(session, f"S-{unique_sku}")
    a = _product(session, f"{unique_sku}-A", on_hand=0, level=10)
    _link(session, supplier, a, cost=Decimal("1.50"))

    bundle = _bundle_for(reorder.scan_reorder(session, READER), supplier.id)

    assert bundle.bundle_value == sum(line.line_total for line in bundle.lines)


def test_a_report_with_nothing_low_has_no_bundles(session):
    report = reorder.scan_reorder(session, READER)
    for bundle in report.bundles:
        assert bundle.lines
