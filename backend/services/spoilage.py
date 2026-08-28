"""Spoilage: find stock about to expire, and propose a markdown a human approves.

### The shape of the feature

Three things happen, and keeping them separate is the whole design:

  scan_spoilage()      READS. Reports what is at risk and what a markdown
                       would recover. Changes nothing at all.
  propose_markdown()   STAGES. Writes one ActionDraft row. Still changes no
                       price - the draft sits in a queue.
  _apply_markdown()    ACTS. Runs only when a human approves the draft, and
                       is the only function here that writes a price.

The AI agent can reach the first two. It cannot reach the third, and there is
no MCP tool that leads to it. See docs/FEATURES-PLAN.md, "The three layers
keeping the agent out of its own approvals".

### Why the payload is re-validated at approval time

`propose_markdown` validates the payload on the way in, and the handler
receives it validated again on the way out. That is not belt-and-braces: a
manager may **edit** the payload on the approval screen between those two
moments. The thing that gets applied is the edited version, so the edited
version is what must be checked.

### Where the numbers come from

Nothing in this file does money arithmetic. Discount tiers, rounding, cost at
risk and projected recovery all live in `services/pricing.py`, because the
approval screen previews the same figures and two copies of a discount ladder
is how a shop ends up advertising one price and charging another.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from core.actor import Actor
from core.enums import ClientType
from core.exceptions import ValidationError
from core.models import ActionDraft, InventoryLot, Product
from services import draft_types, drafts, lots, pricing
from services.guards import require_permission

# The one draft type this gate registers. A closed name, never a function
# reference - a draft says WHAT it wants, and the handler below decides how.
BATCH_PRICE_MARKDOWN = "BATCH_PRICE_MARKDOWN"


# --------------------------------------------------------------------------
# What a scan returns
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SpoilageItem:
    """One lot at risk, with the markdown that would apply to it.

    A frozen dataclass rather than a dict so that a typo in a field name is a
    crash at the point of the typo, and so the adapters have something with a
    known shape to translate. It is deliberately NOT an ORM model: nothing here
    is stored, it is computed on demand from lots that are.
    """

    lot_id: int
    product_id: int
    sku: str
    product_name: str
    lot_code: str
    expiry_date: date
    days_remaining: int
    quantity: int

    current_price: Decimal
    proposed_price: Decimal
    discount_percent: int
    tier_label: str

    cost_at_risk: Decimal
    projected_recovery: Decimal


@dataclass(frozen=True)
class SpoilageReport:
    """Every at-risk lot, plus the two totals a human decides on.

    ⚠️ `total_cost_at_risk` and `total_projected_recovery` are **never netted
    into one number**, here or on any screen. One is money already spent; the
    other is a forecast that depends on shoppers actually buying. A single
    "you save £X" figure would present a guess with the confidence of a fact.
    """

    items: tuple[SpoilageItem, ...]
    total_cost_at_risk: Decimal
    total_projected_recovery: Decimal
    scanned_on: date
    within_days: int


# --------------------------------------------------------------------------
# The draft payload
# --------------------------------------------------------------------------


class MarkdownLine(BaseModel):
    """One price change inside a markdown proposal.

    `model_config` is left at Pydantic's default, which **ignores** unknown
    fields rather than rejecting them. That is a deliberate choice for a
    payload that round-trips through a screen: a UI that adds a display-only
    field to its copy of the object should not make the whole draft
    unapprovable.
    """

    lot_id: int = Field(gt=0)
    product_id: int = Field(gt=0)

    # `gt=0` rather than `ge=0`: a proposed price of zero is a giveaway, not a
    # markdown, and `pricing.MINIMUM_PRICE` already floors the generated value.
    # This bound is what stops an EDITED payload going below it.
    new_price: Decimal = Field(gt=0)


class MarkdownPayload(BaseModel):
    """The whole proposal: a list of price changes, and nothing else.

    Note what is absent. No table name, no column name, no function name, no
    SQL. The payload describes a *business intent* and the handler below is the
    only thing that knows how to carry it out - which is why an edited payload
    can be trusted enough to apply.
    """

    lines: list[MarkdownLine] = Field(min_length=1)

    @field_validator("lines")
    @classmethod
    def _one_line_per_product(cls, lines: list[MarkdownLine]) -> list[MarkdownLine]:
        """Refuse a payload that prices the same product twice.

        ⚠️ `_lines_for()` already collapses to one line per product, so a
        generated payload can never trip this. An **edited** one can, and that
        is the whole point: the handler applies lines in order, so a duplicate
        would let the last entry silently decide the price while the manager
        reads the first one on screen.

        The same class of bug already bit once, between the scan and the
        payload. Catching it in the schema means it is refused before any
        price moves, rather than depending on the handler looping carefully.
        """
        seen: set[int] = set()
        duplicated: list[int] = []
        for line in lines:
            if line.product_id in seen:
                duplicated.append(line.product_id)
            seen.add(line.product_id)

        if duplicated:
            raise ValueError(
                "A product may only appear once; a shelf has one price. "
                f"Duplicated: {sorted(set(duplicated))}."
            )
        return lines


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def scan_spoilage(
    session: Session,
    actor: Actor,
    *,
    today: date,
    within_days: int = pricing.MARKDOWN_HORIZON_DAYS,
) -> SpoilageReport:
    """What is about to expire, and what marking it down would recover.

    Read-only. Runs no writes and stages nothing, so it is safe for the agent
    to call freely while it is thinking.

    `today` is a required argument rather than a call to `date.today()`. Every
    adapter passes the real date; every test passes a fixed one, which is what
    makes a date-driven feature testable at all.

    Lots with no expiry date never appear here - `lots.expiring_lots` excludes
    them - so stock that predates expiry tracking can never be marked down.
    """
    require_permission(actor, "lot.read")

    at_risk = lots.expiring_lots(
        session, actor, within_days=within_days, today=today
    )

    items: list[SpoilageItem] = []
    for lot in at_risk:
        # `expiry_date` cannot be None here: expiring_lots filters on a `<=`
        # comparison, which excludes NULL in SQL. Asserted rather than assumed
        # so a future change to that query fails loudly instead of producing a
        # TypeError several frames away.
        assert lot.expiry_date is not None

        tier = pricing.tier_for(lot.expiry_date, today=today)
        if tier is None:
            # Reachable when a caller passes a `within_days` wider than the
            # discount ladder: the lot is at risk but no rung applies to it
            # yet. It is genuinely not actionable, so it is left out rather
            # than shown with a zero discount a manager might approve.
            continue

        product = session.get(Product, lot.product_id)
        if product is None:
            continue

        proposed = pricing.discounted_price(product.sell_price, tier)
        items.append(
            SpoilageItem(
                lot_id=lot.id,
                product_id=product.id,
                sku=product.sku,
                product_name=product.name,
                lot_code=lot.lot_code,
                expiry_date=lot.expiry_date,
                days_remaining=pricing.days_until(lot.expiry_date, today=today),
                quantity=lot.quantity,
                current_price=product.sell_price,
                proposed_price=proposed,
                discount_percent=int(tier.discount * 100),
                tier_label=tier.label,
                cost_at_risk=pricing.cost_at_risk(lot.quantity, lot.cost_price),
                projected_recovery=pricing.projected_recovery(lot.quantity, proposed),
            )
        )

    return SpoilageReport(
        items=tuple(items),
        total_cost_at_risk=pricing.to_money(
            sum((item.cost_at_risk for item in items), Decimal("0.00"))
        ),
        total_projected_recovery=pricing.to_money(
            sum((item.projected_recovery for item in items), Decimal("0.00"))
        ),
        scanned_on=today,
        within_days=within_days,
    )


# --------------------------------------------------------------------------
# Staging
# --------------------------------------------------------------------------


def propose_markdown(
    session: Session,
    actor: Actor,
    *,
    client: ClientType,
    today: date,
    within_days: int = pricing.MARKDOWN_HORIZON_DAYS,
    reasoning: str | None = None,
):
    """Scan, then stage the whole result as one draft for a human to approve.

    Returns the created `ActionDraft`. **No price moves.** The draft sits in
    `/approvals` until a human reads it, optionally edits it, and approves.

    Raises ValidationError when there is nothing at risk, rather than staging
    an empty draft. An empty proposal is noise in a queue whose entire value is
    that everything in it needs a decision.

    The `reasoning` a caller supplies is kept as-is when given - it is the
    agent's own explanation, in its own words, and rewriting it would defeat
    the point of showing a human why the machine wants this.
    """
    require_permission(actor, "draft.create")

    report = scan_spoilage(session, actor, today=today, within_days=within_days)
    if not report.items:
        raise ValidationError(
            f"Nothing expires within {within_days} day(s), so there is nothing to mark down."
        )

    payload = MarkdownPayload(lines=_lines_for(report))

    return drafts.create_draft(
        session,
        actor,
        client=client,
        draft_type=BATCH_PRICE_MARKDOWN,
        # `mode="json"` so Decimals become strings rather than Decimal objects.
        # The column is JSONB and psycopg cannot serialise a Decimal into it -
        # and a string is also how money crosses every other boundary in this
        # system, for the float-precision reason in `pricing.py`.
        payload=payload.model_dump(mode="json"),
        reasoning=reasoning or _default_reasoning(report),
        cost_at_risk=report.total_cost_at_risk,
        projected_recovery=report.total_projected_recovery,
    )


def _lines_for(report: SpoilageReport) -> list[MarkdownLine]:
    """One price change per PRODUCT, at the deepest discount any of its lots earns.

    ⚠️ This function exists because of a mismatch that is easy to miss: the
    report has one row per **lot**, but `sell_price` lives on the **product**.
    A shelf has one price label, so two lots of the same bread - one expiring
    today at 70% off, one tomorrow at 50% - cannot carry different prices.

    Without this, the payload would hold two lines for the same product and the
    handler would apply them in order, so the LAST one would win. The report is
    ordered soonest-expiry-first, which means the last line is the *least*
    urgent - the 70%-off bread would end up marked down only 50%, quietly, and
    the most urgent stock would be the least discounted.

    The deepest discount is the right answer rather than an arbitrary
    tie-break: stock is sold soonest-expiry-first, so the next carton off the
    shelf is the one from the most urgent lot. Pricing for that lot prices what
    the customer is actually about to buy.

    `lot_id` names the lot that justified the price, which is what the approval
    screen shows the manager and what `_apply_markdown` re-checks.
    """
    best: dict[int, SpoilageItem] = {}
    for item in report.items:
        current = best.get(item.product_id)
        if current is None or item.proposed_price < current.proposed_price:
            best[item.product_id] = item

    return [
        MarkdownLine(
            lot_id=item.lot_id,
            product_id=item.product_id,
            new_price=item.proposed_price,
        )
        for item in best.values()
    ]


def _default_reasoning(report: SpoilageReport) -> str:
    """A plain-English explanation for when the caller supplies none.

    Written for the manager reading the queue, not for a developer reading a
    log: it says what is at stake and what happens if they do nothing, in the
    order a person asks those questions.
    """
    count = len(report.items)
    soonest = min(item.days_remaining for item in report.items)
    when = "today" if soonest <= 0 else f"in {soonest} day(s)"
    return (
        f"{count} lot(s) expire within {report.within_days} day(s), the soonest {when}. "
        f"Together they cost {report.total_cost_at_risk} to buy and will be thrown away "
        f"if they do not sell. Marking them down as proposed would bring in "
        f"{report.total_projected_recovery} if the discounted stock all sells."
    )


# --------------------------------------------------------------------------
# Acting - runs only after a human approves
# --------------------------------------------------------------------------


def _apply_markdown(
    session: Session,
    actor: Actor,
    client: ClientType,
    payload: BaseModel,
    draft: ActionDraft,
) -> None:
    """Move the prices. Called by `drafts.approve_draft`, never directly.

    `actor` is the **approving human**, not the agent that proposed - so the
    `updated_by` stamped on every product names who authorised the change,
    which is the question an audit actually asks.

    ⚠️ It does not commit. `approve_draft` owns the transaction, so the price
    changes and the draft's status change land together or not at all. A commit
    here would allow prices to move while the draft still reads "pending".

    Every line is re-checked against the database even though it was checked
    when proposed, because the payload may have been edited in between. The
    lot could have sold out, or been consumed, or belong to another product
    entirely.

    `draft` is unused here. A markdown changes prices on `products`, which
    carries no source_draft_id column - there is nowhere to record it. The
    parameter is part of the handler contract because gate 29's purchase
    orders and gate 30's received lots both do have somewhere to put it.
    """
    require_permission(actor, "product.update")

    assert isinstance(payload, MarkdownPayload)

    for line in payload.lines:
        lot = session.get(InventoryLot, line.lot_id)
        if lot is None:
            raise ValidationError(f"Lot {line.lot_id} no longer exists.")
        if lot.product_id != line.product_id:
            # An edited payload that moved a price onto the wrong product.
            # Refuse the whole draft rather than apply the lines that happen to
            # line up - a half-applied markdown is worse than none.
            raise ValidationError(
                f"Lot {line.lot_id} does not belong to product {line.product_id}."
            )

        product = session.get(Product, line.product_id)
        if product is None:
            raise ValidationError(f"Product {line.product_id} no longer exists.")

        product.sell_price = pricing.to_money(line.new_price)
        product.updated_by = actor.id


# ⚠️ Registration happens as a side effect of importing this module, so
# something must import it at startup or the draft type silently does not
# exist - and an unknown draft type is refused, which would make the feature
# look broken rather than absent. `services/__init__.py` does that import, so
# the type exists wherever the service layer is used at all.
draft_types.register(
    BATCH_PRICE_MARKDOWN,
    schema=MarkdownPayload,
    handler=_apply_markdown,
)
