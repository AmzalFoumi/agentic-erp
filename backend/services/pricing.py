"""The shop's money arithmetic. Pure functions, no database, no permissions.

### Why this is its own module

The markdown tiers are needed in three places: the spoilage scan that reports
what is at risk, the draft handler that actually moves the prices, and the
screen that previews the numbers before a human approves them. Three inline
copies is three chances for the shop's discount policy to disagree with
itself - and the disagreement would show up as a manager approving "30% off"
and the till charging something else.

So the rule is written once here, and imported. Nothing in this file touches a
`Session` or an `Actor`, which means it can be tested by calling it with
numbers, and read by someone who wants to know the policy without reading any
database code.

### Why the tiers are constants and not settings

They are a *business rule*, and `services/` is where business rules live. A
setting would also walk into a real trap: the demo box declares its environment
in `docker-compose.yml` rather than reading `.env`, so a new setting silently
takes its default there. The box would quietly discount differently from
development, and nothing would say so. A module constant cannot drift that way.

### Everything here is Decimal, never float

`0.1 + 0.2` is not `0.3` in binary floating point. Over a day of supermarket
transactions that drift becomes a till that does not balance, which is why
`products.cost_price` is `Numeric(10, 2)` and comes back from the database as
`decimal.Decimal`. Mixing `Decimal` with `float` in one expression raises
`TypeError`, so the discount *rates* below are Decimals too - written as
`Decimal("0.25")` from a string, because `Decimal(0.25)` from a float would
inherit the very imprecision we are avoiding.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

# Two decimal places, the resolution of every money column in the schema.
_CENTS = Decimal("0.01")

# Sell for at least this, whatever the tier says. A markdown that prices a
# carton at 0.00 is not a discount, it is a giveaway, and it also breaks the
# recovery arithmetic below by making "revenue if we sell it" always zero.
MINIMUM_PRICE = Decimal("0.01")


@dataclass(frozen=True)
class MarkdownTier:
    """One rung of the discount ladder.

    `frozen=True` so a caller cannot reach into the table below and change the
    shop's pricing policy at runtime by accident.
    """

    # Discount applies when the stock expires in this many days or fewer.
    # 0 means "expires today".
    within_days: int

    # The fraction taken OFF the price. 0.25 means the customer pays 75%.
    discount: Decimal

    # What a human sees on the shelf label and in the approval queue.
    label: str


# ⚠️ ORDER IS LOAD-BEARING: most urgent first. `tier_for()` returns the first
# match, so a lot expiring today must be tested before the two-day rung or it
# would get 25% off instead of 70%.
#
# The ladder is deliberately short. Three rungs is a policy a shop manager can
# hold in their head and explain to a customer at the till.
MARKDOWN_TIERS: tuple[MarkdownTier, ...] = (
    MarkdownTier(within_days=0, discount=Decimal("0.70"), label="Expires today"),
    MarkdownTier(within_days=1, discount=Decimal("0.50"), label="Expires tomorrow"),
    MarkdownTier(within_days=2, discount=Decimal("0.25"), label="Expires in 2 days"),
)

# Nothing beyond the last rung is marked down. Named rather than written as
# `MARKDOWN_TIERS[-1].within_days` at three call sites.
MARKDOWN_HORIZON_DAYS: int = max(tier.within_days for tier in MARKDOWN_TIERS)


def days_until(expiry: date, *, today: date) -> int:
    """Whole days from `today` to `expiry`. Negative once it is past.

    `today` is a required keyword argument rather than a call to
    `date.today()` inside this function, and that is a testing decision worth
    keeping: a function that reads the clock itself can only be tested by
    changing the clock. Every caller in `services/` passes the real date; every
    test passes a fixed one.
    """
    return (expiry - today).days


def tier_for(expiry: date, *, today: date) -> MarkdownTier | None:
    """The discount rung `expiry` falls into, or None if it is not close enough.

    Already-expired stock (a negative day count) returns the most urgent rung.
    That is deliberate rather than an oversight: the alternative is returning
    None, which would quietly *exclude* the worst stock in the shop from a
    spoilage report. Whether expired stock may still be sold is a different
    question, and it belongs to whoever writes the handler, not here.
    """
    remaining = days_until(expiry, today=today)
    for tier in MARKDOWN_TIERS:
        if remaining <= tier.within_days:
            return tier
    return None


def to_money(value: Decimal) -> Decimal:
    """Round to the 2 decimal places every money column stores.

    ROUND_HALF_UP, not Python's default ROUND_HALF_EVEN ("banker's rounding").
    Banker's rounding is better for large aggregates, but a shopper who works
    out 2.5p and is charged 2p files a complaint, so shelf prices round the way
    people expect. Applied at the *end* of a calculation, never in the middle -
    rounding twice is how a penny goes missing.
    """
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def discounted_price(sell_price: Decimal, tier: MarkdownTier) -> Decimal:
    """`sell_price` with `tier`'s discount taken off, floored at MINIMUM_PRICE."""
    reduced = to_money(sell_price * (Decimal(1) - tier.discount))
    return max(reduced, MINIMUM_PRICE)


def cost_at_risk(quantity: int, cost_price: Decimal) -> Decimal:
    """What the shop paid for stock that is about to be thrown away.

    This is the "if we do nothing" figure. It is what the shop already spent,
    so it is computed from `cost_price` and never from the sell price - the
    money is gone whether or not anyone would have bought it.
    """
    return to_money(Decimal(quantity) * cost_price)


def projected_recovery(quantity: int, discounted: Decimal) -> Decimal:
    """Revenue if the discounted stock all sells before it expires.

    ⚠️ This is revenue, NOT profit, and NOT `cost_at_risk` minus anything. The
    two figures are shown to a human side by side and deliberately never
    netted into one number, because netting them hides the assumption: this one
    is a forecast that depends on shoppers actually buying, and the other is
    money already spent. A single "you save £X" figure would present a guess
    with the same confidence as a fact.
    """
    return to_money(Decimal(quantity) * discounted)
