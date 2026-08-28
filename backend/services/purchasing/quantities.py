"""How much to buy: target levels, pack rounding, and what a bundle costs.

Pure arithmetic. No session, no actor, no clock, no permissions - the same
shape as `services/pricing.py`, and for the same reason: a purchasing rule you
can check by calling a function with numbers is a rule that stays correct.

### Why this is not in pricing.py

`docs/FEATURES-PLAN.md`'s gate 27 layout table assigns "reorder calculation" to
pricing.py, on the grounds that a markdown and a reorder are both pricing
arithmetic. The reason that rule was written was to stop the **discount ladder**
existing in two places, because a shop that advertises one price and charges
another has a real problem.

There is no ladder here. pricing.py is *what we charge*; this module is *how
much we buy*. They are different domains that happen to both use numbers. The
part of the original rule that mattered still holds: rounding comes from
`pricing.to_money`, so the money rules have exactly one definition.

See docs/superpowers/specs/2026-08-27-gate29-purchasing-design.md, §3.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from decimal import Decimal

from services import pricing

# Order up to twice the reorder level. Not tuned - it is a starting policy that
# says "buy enough that you are not back here tomorrow", and it lives here as a
# named constant so the day someone wants it per-product they change one thing.
REORDER_TARGET_MULTIPLIER = 2


def target_level(reorder_level: int) -> int:
    """The stock level an order aims to reach."""
    return reorder_level * REORDER_TARGET_MULTIPLIER


def packs_needed(shortfall: int, pack_size: int) -> int:
    """Whole packs covering `shortfall`, rounding **up**.

    Rounding down can produce an order that still leaves the product below its
    reorder level, which is an order that did not solve the problem it was
    raised for. Buying one case too many is a cost; buying one case too few is
    the same conversation again next week.
    """
    if pack_size < 1:
        raise ValueError(f"pack_size must be at least 1, got {pack_size}.")
    if shortfall <= 0:
        return 0
    return math.ceil(shortfall / pack_size)


def order_quantity(
    *, quantity_on_hand: int, reorder_level: int, pack_size: int
) -> int:
    """How many units to order for one product, in whole packs.

    ⚠️ The `reorder_level = 0` case. `reorder_level` defaults to 0 and
    `Product.needs_reorder` is `quantity_on_hand <= reorder_level`, so a
    product with no stock and no configured level is genuinely flagged low -
    and `target = 0 * 2 = 0` would order none of it. The bundler would report
    the product as needing reordering and propose buying zero, which is the
    kind of bug that looks like the feature not working at all.

    So: when nothing is on the shelf, order one pack regardless. When something
    is on the shelf and no level is configured, order nothing - the product is
    not low by any definition the shop has given us.
    """
    shortfall = target_level(reorder_level) - quantity_on_hand
    packs = packs_needed(shortfall, pack_size)

    if packs == 0 and quantity_on_hand <= 0:
        packs = 1

    return packs * pack_size


def bundle_value(lines: Iterable[tuple[int, Decimal]]) -> Decimal:
    """What a group of `(quantity, unit_cost)` pairs costs, as money.

    Rounded once at the end rather than per line: rounding each line and then
    summing accumulates the rounding error across every line on the order.
    """
    total = sum(
        (Decimal(quantity) * unit_cost for quantity, unit_cost in lines),
        Decimal("0"),
    )
    return pricing.to_money(total)
