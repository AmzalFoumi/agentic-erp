"""Lots, FEFO consumption, and the one rule this whole design rests on.

The rule: `Product.quantity_on_hand` is a summary of the lots, maintained in
exactly one place. Several tests below exist purely to notice if a second write
path ever appears, because a drifted total is invisible until somebody counts
the shelf by hand.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from core.actor import TokenActor
from core.enums import ClientType
from core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from core.models import Product
from services import lots, products

TODAY = date(2026, 8, 27)


def _product(session, actor, unique_sku, **kw) -> Product:
    return products.create_product(
        session,
        actor,
        sku=unique_sku,
        name=kw.get("name", "Test product"),
        cost_price=kw.get("cost_price", Decimal("1.00")),
        sell_price=kw.get("sell_price", Decimal("2.00")),
        quantity_on_hand=kw.get("quantity_on_hand", 0),
    )


# --- the summary -----------------------------------------------------------


def test_receiving_a_lot_raises_the_product_total(session, actor, unique_sku):
    product = _product(session, actor, unique_sku)

    lots.receive_lot(
        session,
        actor,
        client=ClientType.WEB_UI,
        product_id=product.id,
        lot_code="DN-1",
        quantity=12,
    )

    session.refresh(product)
    assert product.quantity_on_hand == 12


def test_the_total_is_the_sum_of_every_lot(session, actor, unique_sku):
    product = _product(session, actor, unique_sku)
    for i, qty in enumerate([5, 7, 3]):
        lots.receive_lot(
            session,
            actor,
            client=ClientType.WEB_UI,
            product_id=product.id,
            lot_code=f"DN-{i}",
            quantity=qty,
        )

    session.refresh(product)
    assert product.quantity_on_hand == 15


def test_recalculate_survives_a_product_with_no_lots(session, actor, unique_sku):
    """SUM over zero rows is NULL in SQL, not 0.

    Without the COALESCE this writes NULL into a NOT NULL column and fails at
    flush time with an error naming the column rather than the cause.
    """
    product = _product(session, actor, unique_sku, quantity_on_hand=0)
    assert lots.recalculate_on_hand(session, product) == 0
    assert product.quantity_on_hand == 0


# --- FEFO ------------------------------------------------------------------


def _three_dated_lots(session, actor, product):
    """Lots expiring in 5, 1 and 3 days, received in that deliberately wrong order."""
    for code, days in [("LATE", 5), ("SOON", 1), ("MID", 3)]:
        lots.receive_lot(
            session,
            actor,
            client=ClientType.WEB_UI,
            product_id=product.id,
            lot_code=code,
            quantity=10,
            expiry_date=TODAY + timedelta(days=days),
        )


def test_consumption_takes_the_soonest_expiring_lot_first(session, actor, unique_sku):
    product = _product(session, actor, unique_sku)
    _three_dated_lots(session, actor, product)

    lots.consume(session, actor, product_id=product.id, quantity=10)
    session.commit()

    by_code = {lot.lot_code: lot.quantity for lot in lots.list_lots(
        session, actor, product_id=product.id, include_empty=True
    )}
    assert by_code["SOON"] == 0
    assert by_code["MID"] == 10
    assert by_code["LATE"] == 10


def test_consumption_spills_into_the_next_lot(session, actor, unique_sku):
    product = _product(session, actor, unique_sku)
    _three_dated_lots(session, actor, product)

    lots.consume(session, actor, product_id=product.id, quantity=15)
    session.commit()

    by_code = {lot.lot_code: lot.quantity for lot in lots.list_lots(
        session, actor, product_id=product.id, include_empty=True
    )}
    assert by_code["SOON"] == 0
    assert by_code["MID"] == 5
    assert by_code["LATE"] == 10


def test_undated_stock_is_consumed_last(session, actor, unique_sku):
    """The backfill's opening stock must not displace real dated stock.

    Taking undated stock first would let dated stock sit on the shelf and
    spoil, which is the opposite of what this feature is for.
    """
    product = _product(session, actor, unique_sku)
    lots.receive_lot(
        session, actor, client=ClientType.WEB_UI, product_id=product.id,
        lot_code="OPENING", quantity=10, expiry_date=None,
    )
    lots.receive_lot(
        session, actor, client=ClientType.WEB_UI, product_id=product.id,
        lot_code="DATED", quantity=10, expiry_date=TODAY + timedelta(days=2),
    )

    lots.consume(session, actor, product_id=product.id, quantity=10)
    session.commit()

    by_code = {lot.lot_code: lot.quantity for lot in lots.list_lots(
        session, actor, product_id=product.id, include_empty=True
    )}
    assert by_code["DATED"] == 0
    assert by_code["OPENING"] == 10


def test_consuming_more_than_exists_is_refused_before_anything_moves(
    session, actor, unique_sku
):
    """Checked up front, not discovered halfway through the loop."""
    product = _product(session, actor, unique_sku)
    _three_dated_lots(session, actor, product)

    with pytest.raises(ValidationError, match="only 30 in stock"):
        lots.consume(session, actor, product_id=product.id, quantity=31)

    remaining = [lot.quantity for lot in lots.list_lots(
        session, actor, product_id=product.id, include_empty=True
    )]
    assert remaining == [10, 10, 10]


# --- adjust_stock still behaves, through a new mechanism -------------------


def test_adjust_stock_keeps_its_contract(session, actor, unique_sku):
    """Same signature, same result. Only the internals changed."""
    product = _product(session, actor, unique_sku)
    lots.receive_lot(
        session, actor, client=ClientType.WEB_UI, product_id=product.id,
        lot_code="DN-1", quantity=20, expiry_date=TODAY + timedelta(days=4),
    )

    updated = products.adjust_stock(session, actor, product_id=product.id, delta=-5)
    assert updated.quantity_on_hand == 15


def test_adjust_stock_still_refuses_to_go_negative(session, actor, unique_sku):
    product = _product(session, actor, unique_sku)
    lots.receive_lot(
        session, actor, client=ClientType.WEB_UI, product_id=product.id,
        lot_code="DN-1", quantity=3,
    )

    with pytest.raises(ValidationError, match="only 3 in stock"):
        products.adjust_stock(session, actor, product_id=product.id, delta=-4)


def test_an_increase_goes_to_one_correction_lot_not_many(session, actor, unique_sku):
    """A shop recounting weekly must not accumulate a lot per recount."""
    product = _product(session, actor, unique_sku)

    products.adjust_stock(session, actor, product_id=product.id, delta=3)
    products.adjust_stock(session, actor, product_id=product.id, delta=4)

    all_lots = lots.list_lots(session, actor, product_id=product.id, include_empty=True)
    assert len(all_lots) == 1
    assert all_lots[0].lot_code == products.CORRECTION_LOT_CODE
    assert all_lots[0].quantity == 7
    # No expiry date, so it is consumed last and never marked down.
    assert all_lots[0].expiry_date is None


# --- expiring_lots ---------------------------------------------------------


def test_expiring_lots_excludes_stock_with_no_expiry_date(session, actor, unique_sku):
    """The rule the backfill migration depends on."""
    product = _product(session, actor, unique_sku)
    lots.receive_lot(
        session, actor, client=ClientType.WEB_UI, product_id=product.id,
        lot_code="OPENING", quantity=10, expiry_date=None,
    )

    found = lots.expiring_lots(session, actor, within_days=2, today=TODAY)
    assert all(lot.product_id != product.id for lot in found)


def test_expiring_lots_includes_already_expired_stock(session, actor, unique_sku):
    """Excluding it would hide the worst stock in the shop."""
    product = _product(session, actor, unique_sku)
    lots.receive_lot(
        session, actor, client=ClientType.WEB_UI, product_id=product.id,
        lot_code="OLD", quantity=4, expiry_date=TODAY - timedelta(days=3),
    )

    found = lots.expiring_lots(session, actor, within_days=2, today=TODAY)
    assert any(lot.product_id == product.id for lot in found)


def test_expiring_lots_ignores_emptied_lots(session, actor, unique_sku):
    product = _product(session, actor, unique_sku)
    lots.receive_lot(
        session, actor, client=ClientType.WEB_UI, product_id=product.id,
        lot_code="GONE", quantity=5, expiry_date=TODAY + timedelta(days=1),
    )
    lots.consume(session, actor, product_id=product.id, quantity=5)
    session.commit()

    found = lots.expiring_lots(session, actor, within_days=2, today=TODAY)
    assert all(lot.product_id != product.id for lot in found)


# --- cost price ------------------------------------------------------------


def test_a_lot_freezes_the_price_actually_paid(session, actor, unique_sku):
    """A later price rise must not rewrite what this delivery cost.

    `cost_at_risk` is only a truthful number if it uses what was paid for the
    stock in question.
    """
    product = _product(session, actor, unique_sku, cost_price=Decimal("1.00"))
    lot = lots.receive_lot(
        session, actor, client=ClientType.WEB_UI, product_id=product.id,
        lot_code="DN-1", quantity=5,
    )
    assert lot.cost_price == Decimal("1.00")

    products.update_product(
        session, actor, product_id=product.id, cost_price=Decimal("9.99")
    )
    session.refresh(lot)
    assert lot.cost_price == Decimal("1.00")


# --- permissions -----------------------------------------------------------


def test_reading_lots_needs_product_read(session, unique_sku, actor):
    product = _product(session, actor, unique_sku)
    limited = TokenActor("nobody", frozenset({"stock.adjust"}))

    with pytest.raises(PermissionDeniedError, match="product.read"):
        lots.list_lots(session, limited, product_id=product.id)


def test_receiving_needs_stock_adjust(session, unique_sku, actor):
    product = _product(session, actor, unique_sku)
    limited = TokenActor("nobody", frozenset({"product.read"}))

    with pytest.raises(PermissionDeniedError, match="stock.adjust"):
        lots.receive_lot(
            session, limited, client=ClientType.WEB_UI, product_id=product.id,
            lot_code="DN-1", quantity=1,
        )


def test_permission_is_checked_before_the_product_is_looked_up(session):
    """A refused caller should not cause a query, and should not learn whether
    the product exists."""
    limited = TokenActor("nobody", frozenset())

    with pytest.raises(PermissionDeniedError):
        lots.list_lots(session, limited, product_id=999_999_999)


# --- validation ------------------------------------------------------------


def test_a_lot_needs_a_positive_quantity(session, actor, unique_sku):
    product = _product(session, actor, unique_sku)
    with pytest.raises(ValidationError):
        lots.receive_lot(
            session, actor, client=ClientType.WEB_UI, product_id=product.id,
            lot_code="DN-1", quantity=0,
        )


def test_a_lot_needs_a_lot_code(session, actor, unique_sku):
    product = _product(session, actor, unique_sku)
    with pytest.raises(ValidationError):
        lots.receive_lot(
            session, actor, client=ClientType.WEB_UI, product_id=product.id,
            lot_code="   ", quantity=1,
        )


def test_receiving_into_a_missing_product_is_not_found(session, actor):
    with pytest.raises(NotFoundError):
        lots.receive_lot(
            session, actor, client=ClientType.WEB_UI, product_id=999_999_999,
            lot_code="DN-1", quantity=1,
        )


# --- the single write path -------------------------------------------------


def test_nothing_but_recalculate_on_hand_assigns_the_summary():
    """A source-level guard on the rule the whole lot design rests on.

    `Product.quantity_on_hand` is a summary of the lots. If a second write path
    appears, the summary drifts from the rows it summarises - and a drifted
    total is invisible until somebody counts the shelf by hand and discovers
    the system has been wrong for a month.

    No runtime test can catch that, because the bug is *another correct-looking
    assignment somewhere else*. So this reads the source and refuses to let one
    appear unnoticed. It is deliberately crude: it will also fire on a harmless
    rename, which costs a minute and buys a rule that cannot rot silently.
    """
    import pathlib
    import re

    services_dir = pathlib.Path(__file__).resolve().parents[1] / "services"

    offenders: list[str] = []
    for path in services_dir.glob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            # An assignment to the attribute, not a comparison or a read.
            if re.search(r"\.quantity_on_hand\s*=(?!=)", line):
                offenders.append(path.name)

    # The file, not the line number: pinning a line makes this fail on any edit
    # above it, which trains people to update the number without reading why.
    assert offenders == ["lots.py"], (
        "quantity_on_hand is assigned somewhere new. It must be written only by "
        "services/lots.py::recalculate_on_hand - every other change to stock "
        "goes through a lot. If you moved that function, update this test's "
        "expected location; if you added a write, remove it.\n"
        f"Found: {offenders}"
    )
