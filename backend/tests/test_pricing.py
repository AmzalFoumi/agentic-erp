"""The shop's discount policy, tested as arithmetic.

No database, no fixtures, no actor. That is the payoff of keeping the money
rules in a module that imports none of those: the shop's pricing policy can be
checked by calling functions with numbers, and a failure here names a rule
rather than a query.
"""

from datetime import date
from decimal import Decimal

import pytest

from services import pricing

TODAY = date(2026, 8, 27)


# --- the ladder ------------------------------------------------------------


@pytest.mark.parametrize(
    ("expiry", "expected_discount"),
    [
        (date(2026, 8, 27), Decimal("0.70")),  # today
        (date(2026, 8, 28), Decimal("0.50")),  # tomorrow
        (date(2026, 8, 29), Decimal("0.25")),  # in 2 days
    ],
)
def test_each_rung_of_the_ladder(expiry, expected_discount):
    tier = pricing.tier_for(expiry, today=TODAY)
    assert tier is not None
    assert tier.discount == expected_discount


def test_stock_beyond_the_horizon_is_not_marked_down():
    """Three days out is one day past the last rung."""
    assert pricing.tier_for(date(2026, 8, 30), today=TODAY) is None


def test_already_expired_stock_gets_the_most_urgent_rung():
    """Not None, and this is the point of the test.

    Returning None for expired stock would quietly exclude the worst stock in
    the shop from the report whose whole job is to find it.
    """
    tier = pricing.tier_for(date(2026, 8, 20), today=TODAY)
    assert tier is not None
    assert tier.discount == Decimal("0.70")


def test_the_ladder_is_ordered_most_urgent_first():
    """Ordering is load-bearing: tier_for returns the first match.

    If the tuple were sorted the other way, a lot expiring today would match
    the 2-day rung first and get 25% off instead of 70%.
    """
    days = [tier.within_days for tier in pricing.MARKDOWN_TIERS]
    assert days == sorted(days)


def test_the_horizon_matches_the_last_rung():
    assert pricing.MARKDOWN_HORIZON_DAYS == max(
        tier.within_days for tier in pricing.MARKDOWN_TIERS
    )


# --- rounding --------------------------------------------------------------


def test_money_rounds_half_up_not_bankers():
    """Python's default would round 2.5 to 2, which shoppers complain about."""
    assert pricing.to_money(Decimal("0.025")) == Decimal("0.03")
    assert pricing.to_money(Decimal("0.035")) == Decimal("0.04")


def test_discounted_price_is_rounded_to_cents():
    tier = pricing.MARKDOWN_TIERS[2]  # 25% off
    # 3.99 * 0.75 = 2.9925 -> 2.99
    assert pricing.discounted_price(Decimal("3.99"), tier) == Decimal("2.99")


def test_a_discount_never_prices_below_the_floor():
    """70% off a penny is not free."""
    tier = pricing.MARKDOWN_TIERS[0]  # 70% off
    assert pricing.discounted_price(Decimal("0.01"), tier) == pricing.MINIMUM_PRICE


# --- the two figures -------------------------------------------------------


def test_cost_at_risk_uses_what_was_paid():
    assert pricing.cost_at_risk(12, Decimal("1.25")) == Decimal("15.00")


def test_projected_recovery_uses_the_discounted_price():
    assert pricing.projected_recovery(12, Decimal("0.99")) == Decimal("11.88")


def test_the_two_figures_are_independent():
    """Neither is derived from the other, and nothing here nets them.

    This test exists to pin a design decision rather than a calculation: the
    day someone adds a `net_saving()` helper, the reasoning for not having one
    is written down right here.
    """
    quantity, cost, discounted = 10, Decimal("2.00"), Decimal("1.00")
    at_risk = pricing.cost_at_risk(quantity, cost)
    recovery = pricing.projected_recovery(quantity, discounted)

    assert at_risk == Decimal("20.00")
    assert recovery == Decimal("10.00")
    # Deliberately NOT asserting anything about at_risk - recovery.


# --- dates -----------------------------------------------------------------


def test_days_until_counts_whole_days():
    assert pricing.days_until(date(2026, 8, 29), today=TODAY) == 2
    assert pricing.days_until(TODAY, today=TODAY) == 0
    assert pricing.days_until(date(2026, 8, 25), today=TODAY) == -2


def test_nothing_here_reads_the_clock():
    """Every date-aware function takes `today` as a required argument.

    A function that reads the clock itself can only be tested by changing the
    clock, and a spoilage feature is entirely made of date arithmetic.
    """
    with pytest.raises(TypeError):
        pricing.days_until(date(2026, 8, 29))  # type: ignore[call-arg]


def test_tiers_cannot_be_edited_at_runtime():
    """frozen=True, so the shop's policy cannot be changed by accident."""
    with pytest.raises(Exception):
        pricing.MARKDOWN_TIERS[0].discount = Decimal("0.99")  # type: ignore[misc]
