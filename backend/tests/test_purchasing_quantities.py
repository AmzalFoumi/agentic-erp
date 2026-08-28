"""How much to buy, tested as arithmetic.

No database, no fixtures, no actor - the same payoff as test_pricing.py. A
failure here names a purchasing rule rather than a query.
"""

from decimal import Decimal

import pytest

from services.purchasing import quantities


# --- target level ----------------------------------------------------------


def test_target_is_twice_the_reorder_level():
    assert quantities.target_level(10) == 20


def test_the_multiplier_is_the_one_the_spec_names():
    assert quantities.REORDER_TARGET_MULTIPLIER == 2


# --- pack rounding ---------------------------------------------------------


def test_packs_round_up_never_down():
    """13 units at 12 to a case is two cases, not one.

    Rounding down would produce an order that still leaves the product below
    its reorder level - an order that did not solve the problem it was raised
    for.
    """
    assert quantities.packs_needed(13, 12) == 2


def test_an_exact_multiple_needs_no_extra_pack():
    assert quantities.packs_needed(24, 12) == 2


def test_a_pack_size_of_one_is_the_identity():
    assert quantities.packs_needed(7, 1) == 7


def test_a_pack_size_below_one_is_refused():
    """Zero would divide by zero; negative is nonsense. Both are configuration
    errors, and a loud failure beats an order for -3 cases."""
    with pytest.raises(ValueError):
        quantities.packs_needed(10, 0)


# --- order quantity --------------------------------------------------------


def test_orders_up_to_the_target_rounded_to_whole_packs():
    # target 20, on hand 5 -> shortfall 15 -> 2 packs of 12 -> 24
    assert (
        quantities.order_quantity(quantity_on_hand=5, reorder_level=10, pack_size=12)
        == 24
    )


def test_a_product_at_target_contributes_nothing():
    assert (
        quantities.order_quantity(quantity_on_hand=20, reorder_level=10, pack_size=12)
        == 0
    )


def test_a_product_above_target_contributes_nothing():
    assert (
        quantities.order_quantity(quantity_on_hand=99, reorder_level=10, pack_size=12)
        == 0
    )


def test_an_unconfigured_product_with_no_stock_still_gets_one_pack():
    """The reorder_level = 0 hole, pinned by name.

    reorder_level defaults to 0 and needs_reorder is `on_hand <= reorder_level`,
    so a product with no stock and no configured level IS flagged low - and
    target = 0 * 2 = 0 would order none of it. The bundler would then report a
    product as needing reordering and propose buying zero.

    "There is none on the shelf and nobody set a reorder level" is still a
    reason to buy some.
    """
    assert (
        quantities.order_quantity(quantity_on_hand=0, reorder_level=0, pack_size=12)
        == 12
    )


def test_a_stocked_product_with_no_reorder_level_orders_nothing():
    """The counterpart: on hand 5, level 0 -> not low, nothing to do.

    This is the test that stops the rule above from being 'always order one
    pack'. It only fires when the shelf is actually empty.
    """
    assert (
        quantities.order_quantity(quantity_on_hand=5, reorder_level=0, pack_size=12)
        == 0
    )


def test_a_negative_quantity_on_hand_is_treated_as_empty():
    """Defensive: quantity_on_hand should never be negative in practice, but
    if it ever is, the empty-shelf rule must still fire rather than compute a
    shortfall so large it masks the same bug elsewhere."""
    assert (
        quantities.order_quantity(quantity_on_hand=-3, reorder_level=0, pack_size=12)
        == 12
    )


# --- bundle value ----------------------------------------------------------


def test_bundle_value_sums_quantity_times_cost():
    lines = [(12, Decimal("1.50")), (6, Decimal("2.00"))]
    assert quantities.bundle_value(lines) == Decimal("30.00")


def test_an_empty_bundle_is_zero_not_an_error():
    assert quantities.bundle_value([]) == Decimal("0.00")


def test_bundle_value_is_rounded_through_the_shared_money_rule():
    """0.005 rounds half UP to 0.01, which is what pricing.to_money does.

    Asserting the behaviour rather than the call keeps this a test of the rule
    rather than a test of the implementation - but the rule has exactly one
    definition, in pricing.py, and this is what pins that it is being used.
    """
    assert quantities.bundle_value([(1, Decimal("0.005"))]) == Decimal("0.01")
