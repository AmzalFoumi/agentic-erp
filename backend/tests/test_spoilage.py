"""The spoilage feature: scanning, proposing, and what approval actually does.

The tests that matter most here are not the arithmetic ones - `test_pricing.py`
covers that. They are the ones proving that **no price moves until a human
approves**, and that a payload edited between proposal and approval is checked
again rather than trusted.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from core.actor import TokenActor
from core.enums import ClientType, DraftStatus
from core.exceptions import PermissionDeniedError, ValidationError
from core.models import Product
from services import drafts, lots, products, spoilage

TODAY = date(2026, 8, 27)


def _product_with_lot(session, actor, unique_sku, *, days, quantity=10, **kw):
    product = products.create_product(
        session,
        actor,
        sku=unique_sku,
        name=kw.get("name", "Yoghurt 500g"),
        cost_price=kw.get("cost_price", Decimal("1.00")),
        sell_price=kw.get("sell_price", Decimal("4.00")),
        quantity_on_hand=0,
    )
    lot = lots.receive_lot(
        session,
        actor,
        client=ClientType.WEB_UI,
        product_id=product.id,
        lot_code="DN-1",
        quantity=quantity,
        expiry_date=None if days is None else TODAY + timedelta(days=days),
    )
    return product, lot


def _mine(report, product_id):
    """This test's own items. The database is shared, so other rows exist."""
    return [item for item in report.items if item.product_id == product_id]


# --- scanning --------------------------------------------------------------


def test_a_lot_expiring_tomorrow_is_reported_at_half_price(
    session, actor, unique_sku
):
    product, lot = _product_with_lot(session, actor, unique_sku, days=1)

    report = spoilage.scan_spoilage(session, actor, today=TODAY)
    items = _mine(report, product.id)

    assert len(items) == 1
    assert items[0].discount_percent == 50
    assert items[0].proposed_price == Decimal("2.00")
    assert items[0].current_price == Decimal("4.00")


def test_stock_beyond_the_horizon_is_not_reported(session, actor, unique_sku):
    product, _ = _product_with_lot(session, actor, unique_sku, days=9)
    report = spoilage.scan_spoilage(session, actor, today=TODAY)
    assert _mine(report, product.id) == []


def test_stock_with_no_expiry_date_is_never_reported(session, actor, unique_sku):
    """The backfill's opening stock must never trigger a markdown."""
    product, _ = _product_with_lot(session, actor, unique_sku, days=None)
    report = spoilage.scan_spoilage(session, actor, today=TODAY)
    assert _mine(report, product.id) == []


def test_the_two_money_figures_are_both_reported(session, actor, unique_sku):
    product, _ = _product_with_lot(
        session, actor, unique_sku, days=1, quantity=10,
        cost_price=Decimal("1.00"), sell_price=Decimal("4.00"),
    )
    item = _mine(spoilage.scan_spoilage(session, actor, today=TODAY), product.id)[0]

    assert item.cost_at_risk == Decimal("10.00")       # 10 x 1.00 paid
    assert item.projected_recovery == Decimal("20.00")  # 10 x 2.00 discounted


def test_scanning_changes_nothing(session, actor, unique_sku):
    """Read-only means read-only: no price moves, no draft appears."""
    product, _ = _product_with_lot(session, actor, unique_sku, days=1)
    before = product.sell_price
    pending_before = drafts.count_drafts(session, actor, status=DraftStatus.PENDING)

    spoilage.scan_spoilage(session, actor, today=TODAY)

    session.refresh(product)
    assert product.sell_price == before
    assert drafts.count_drafts(session, actor, status=DraftStatus.PENDING) == pending_before


def test_scanning_needs_lot_read(session, unique_sku, actor):
    limited = TokenActor("nobody", frozenset({"product.read"}))
    with pytest.raises(PermissionDeniedError, match="lot.read"):
        spoilage.scan_spoilage(session, limited, today=TODAY)


# --- proposing -------------------------------------------------------------


def test_proposing_stages_a_draft_and_moves_no_price(session, actor, unique_sku):
    """The single most important test in this file."""
    product, _ = _product_with_lot(session, actor, unique_sku, days=1)
    before = product.sell_price

    draft = spoilage.propose_markdown(
        session, actor, client=ClientType.MCP_AGENT, today=TODAY
    )

    assert draft.status == DraftStatus.PENDING.value
    assert draft.draft_type == spoilage.BATCH_PRICE_MARKDOWN

    session.refresh(product)
    assert product.sell_price == before, "a proposal must not change a price"


def test_a_proposal_records_which_door_it_came_through(session, actor, unique_sku):
    _product_with_lot(session, actor, unique_sku, days=1)
    draft = spoilage.propose_markdown(
        session, actor, client=ClientType.MCP_AGENT, today=TODAY
    )
    assert draft.created_via == ClientType.MCP_AGENT.value


def test_the_agents_own_reasoning_is_kept_verbatim(session, actor, unique_sku):
    _product_with_lot(session, actor, unique_sku, days=1)
    draft = spoilage.propose_markdown(
        session, actor, client=ClientType.MCP_AGENT, today=TODAY,
        reasoning="Half the dairy aisle goes off tomorrow.",
    )
    assert draft.reasoning == "Half the dairy aisle goes off tomorrow."


def test_a_proposal_carries_both_totals_for_the_human(session, actor, unique_sku):
    _product_with_lot(session, actor, unique_sku, days=1)
    draft = spoilage.propose_markdown(
        session, actor, client=ClientType.WEB_UI, today=TODAY
    )
    assert draft.cost_at_risk is not None
    assert draft.projected_recovery is not None


def test_proposing_needs_draft_create(session, unique_sku, actor):
    limited = TokenActor("nobody", frozenset({"lot.read"}))
    with pytest.raises(PermissionDeniedError, match="draft.create"):
        spoilage.propose_markdown(
            session, limited, client=ClientType.MCP_AGENT, today=TODAY
        )


def test_nothing_at_risk_is_refused_rather_than_staged_empty(session, actor):
    """An empty draft is noise in a queue whose value is that everything in it
    needs a decision."""
    far_future = TODAY - timedelta(days=3650)
    with pytest.raises(ValidationError, match="nothing to mark down"):
        spoilage.propose_markdown(
            session, actor, client=ClientType.WEB_UI, today=far_future
        )


# --- approving -------------------------------------------------------------


def test_approving_is_what_finally_moves_the_price(session, actor, unique_sku):
    product, _ = _product_with_lot(session, actor, unique_sku, days=1)
    draft = spoilage.propose_markdown(
        session, actor, client=ClientType.MCP_AGENT, today=TODAY
    )

    drafts.approve_draft(
        session, actor, client=ClientType.WEB_UI, draft_id=draft.id
    )

    session.refresh(product)
    assert product.sell_price == Decimal("2.00")


def test_an_agent_without_draft_decide_cannot_apply_its_own_proposal(
    session, actor, unique_sku
):
    """Layer one of three. The other two are the absent MCP tool and the
    agent's token ceiling - see docs/FEATURES-PLAN.md."""
    product, _ = _product_with_lot(session, actor, unique_sku, days=1)
    draft = spoilage.propose_markdown(
        session, actor, client=ClientType.MCP_AGENT, today=TODAY
    )
    before = product.sell_price

    agent = TokenActor(
        "agent",
        frozenset({"lot.read", "draft.read", "draft.create", "product.update"}),
    )
    with pytest.raises(PermissionDeniedError, match="draft.decide"):
        drafts.approve_draft(
            session, agent, client=ClientType.MCP_AGENT, draft_id=draft.id
        )

    session.refresh(product)
    assert product.sell_price == before, "a refused approval must not move a price"


def test_rejecting_moves_no_price(session, actor, unique_sku):
    product, _ = _product_with_lot(session, actor, unique_sku, days=1)
    draft = spoilage.propose_markdown(
        session, actor, client=ClientType.WEB_UI, today=TODAY
    )
    before = product.sell_price

    drafts.reject_draft(session, actor, client=ClientType.WEB_UI, draft_id=draft.id)

    session.refresh(product)
    assert product.sell_price == before


# --- the edited payload ----------------------------------------------------


def test_a_manager_can_edit_the_price_before_approving(session, actor, unique_sku):
    """The reason the handler re-validates: what gets applied is the edit."""
    product, lot = _product_with_lot(session, actor, unique_sku, days=1)
    draft = spoilage.propose_markdown(
        session, actor, client=ClientType.WEB_UI, today=TODAY
    )

    edited = {
        "lines": [
            {"lot_id": lot.id, "product_id": product.id, "new_price": "3.50"}
        ]
    }
    drafts.approve_draft(
        session, actor, client=ClientType.WEB_UI, draft_id=draft.id, payload=edited
    )

    session.refresh(product)
    assert product.sell_price == Decimal("3.50")


def test_an_edited_payload_cannot_price_a_lot_onto_another_product(
    session, actor, unique_sku
):
    """The check that makes an editable payload safe to apply."""
    product, lot = _product_with_lot(session, actor, unique_sku, days=1)
    other = products.create_product(
        session, actor, sku=unique_sku + "-B", name="Other",
        cost_price=Decimal("1.00"), sell_price=Decimal("9.99"),
    )
    draft = spoilage.propose_markdown(
        session, actor, client=ClientType.WEB_UI, today=TODAY
    )

    tampered = {
        "lines": [
            {"lot_id": lot.id, "product_id": other.id, "new_price": "0.01"}
        ]
    }
    with pytest.raises(ValidationError, match="does not belong to product"):
        drafts.approve_draft(
            session, actor, client=ClientType.WEB_UI,
            draft_id=draft.id, payload=tampered,
        )

    session.refresh(other)
    assert other.sell_price == Decimal("9.99")


def test_an_edited_payload_cannot_price_at_zero(session, actor, unique_sku):
    """`gt=0` on the schema. A giveaway is not a markdown."""
    product, lot = _product_with_lot(session, actor, unique_sku, days=1)
    draft = spoilage.propose_markdown(
        session, actor, client=ClientType.WEB_UI, today=TODAY
    )

    with pytest.raises(ValidationError):
        drafts.approve_draft(
            session, actor, client=ClientType.WEB_UI, draft_id=draft.id,
            payload={"lines": [
                {"lot_id": lot.id, "product_id": product.id, "new_price": "0"}
            ]},
        )


def test_an_empty_edited_payload_is_refused(session, actor, unique_sku):
    """`min_length=1`. Approving nothing is not a decision."""
    _product_with_lot(session, actor, unique_sku, days=1)
    draft = spoilage.propose_markdown(
        session, actor, client=ClientType.WEB_UI, today=TODAY
    )
    with pytest.raises(ValidationError):
        drafts.approve_draft(
            session, actor, client=ClientType.WEB_UI,
            draft_id=draft.id, payload={"lines": []},
        )


# --- registration ----------------------------------------------------------


def test_the_draft_type_is_registered_by_importing_the_service_package():
    """If this fails, `services/__init__.py` stopped importing spoilage and the
    feature is silently absent rather than broken."""
    from services import draft_types

    assert spoilage.BATCH_PRICE_MARKDOWN in draft_types.registered_types()


# --- two lots, one shelf price ---------------------------------------------


def test_two_lots_of_one_product_are_priced_at_the_deepest_discount(
    session, actor, unique_sku
):
    """A shelf has one price label, so two lots cannot carry two prices.

    ⚠️ The failure this pins is silent and backwards. The report is ordered
    soonest-expiry-first, so without deduplication the payload would carry two
    lines for one product and the handler would apply them in order - the LAST
    one winning. The last line is the *least* urgent, so bread expiring today
    would end up discounted 50% instead of 70%, and the most urgent stock in
    the shop would be the least marked down.
    """
    product = products.create_product(
        session, actor, sku=unique_sku, name="Sourdough",
        cost_price=Decimal("1.00"), sell_price=Decimal("400.00"),
    )
    # Expiring today -> 70% off -> 120.00
    lots.receive_lot(
        session, actor, client=ClientType.WEB_UI, product_id=product.id,
        lot_code="TODAY", quantity=40, expiry_date=TODAY,
    )
    # Expiring tomorrow -> 50% off -> 200.00
    lots.receive_lot(
        session, actor, client=ClientType.WEB_UI, product_id=product.id,
        lot_code="TOMORROW", quantity=60, expiry_date=TODAY + timedelta(days=1),
    )

    report = spoilage.scan_spoilage(session, actor, today=TODAY)
    # The REPORT still shows both lots - a manager wants to see the whole
    # picture, and the two lots have genuinely different amounts at risk.
    assert len(_mine(report, product.id)) == 2

    draft = spoilage.propose_markdown(
        session, actor, client=ClientType.WEB_UI, today=TODAY
    )
    lines = [
        line for line in draft.payload["lines"] if line["product_id"] == product.id
    ]
    assert len(lines) == 1, "one product must get one price change"
    assert Decimal(lines[0]["new_price"]) == Decimal("120.00")

    drafts.approve_draft(
        session, actor, client=ClientType.WEB_UI, draft_id=draft.id
    )
    session.refresh(product)
    assert product.sell_price == Decimal("120.00")
