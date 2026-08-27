"""The Action Draft engine (gate 27).

Three layers are tested here, deliberately in one file because they are one
feature: the shared vocabularies, the ORM model, and the service functions. The
registry that decides what a draft is *allowed* to be has its own file,
tests/test_draft_types.py, because it is the security boundary and deserves to
fail loudly on its own.

Read docs/FEATURES-PLAN.md before changing any of this - in particular decision
1, which explains why this queue coexists with gate 19's in-conversation
approval rather than replacing it.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import BaseModel

from core.actor import TokenActor
from core.enums import ClientType, DraftStatus
from core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from core.models import ActionDraft
from services import draft_types, drafts

# --- the vocabularies ------------------------------------------------------


def test_client_type_values_are_the_stored_strings():
    """The enum members ARE their database values.

    Subclassing `str` means there is no conversion layer between Python and the
    column, and no risk of storing the repr of an enum member instead of its
    value.
    """
    assert ClientType.WEB_UI == "web_ui"
    assert ClientType.MCP_AGENT == "mcp_agent"
    assert ClientType.SYSTEM == "system"


def test_draft_status_values_are_the_stored_strings():
    assert DraftStatus.PENDING == "pending"
    assert DraftStatus.APPROVED == "approved"
    assert DraftStatus.REJECTED == "rejected"
    assert DraftStatus.EXECUTED == "executed"


def test_there_is_no_expired_status():
    """Expiry is computed when a draft is read, never stored.

    Pinned as a test rather than left as a comment because "add EXPIRED to the
    enum" is exactly the reasonable-looking change someone makes later, and the
    reason it is wrong - nothing exists to do the writing - is not visible from
    the enum itself.
    """
    assert not hasattr(DraftStatus, "EXPIRED")


# --- the model -------------------------------------------------------------


def test_draft_defaults_to_pending_and_is_not_expired(session):
    draft = ActionDraft(
        draft_type="TEST_MARK",
        payload={"note": "hello"},
        reasoning="because",
        created_by="pytest",
        created_via=ClientType.WEB_UI,
    )
    session.add(draft)
    session.flush()

    assert draft.id is not None
    assert draft.status == DraftStatus.PENDING
    assert draft.is_expired is False


def test_a_draft_with_a_past_expiry_reports_expired(session):
    draft = ActionDraft(
        draft_type="TEST_MARK",
        payload={},
        reasoning="because",
        created_by="pytest",
        created_via=ClientType.WEB_UI,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    session.add(draft)
    session.flush()

    assert draft.is_expired is True


def test_money_columns_survive_a_round_trip_exactly(session):
    """Numeric(10,2), not float. A cent lost here is a till that does not balance."""
    draft = ActionDraft(
        draft_type="TEST_MARK",
        payload={},
        reasoning="because",
        created_by="pytest",
        created_via=ClientType.WEB_UI,
        cost_at_risk=Decimal("40000.50"),
        projected_recovery=Decimal("12000.25"),
    )
    session.add(draft)
    session.flush()
    session.refresh(draft)

    assert draft.cost_at_risk == Decimal("40000.50")
    assert draft.projected_recovery == Decimal("12000.25")


def test_the_two_money_figures_are_independently_nullable(session):
    """NULL means "not applicable", which is a different fact from 0.00."""
    draft = ActionDraft(
        draft_type="TEST_MARK",
        payload={},
        reasoning="because",
        created_by="pytest",
        created_via=ClientType.WEB_UI,
        cost_at_risk=Decimal("100.00"),
    )
    session.add(draft)
    session.flush()

    assert draft.cost_at_risk == Decimal("100.00")
    assert draft.projected_recovery is None


# --- the service -----------------------------------------------------------


class _MarkPayload(BaseModel):
    product_id: int
    new_price: str


@pytest.fixture
def handler_calls():
    """A registered draft type whose handler records how it was called.

    Recording the call is what lets a test assert the handler ran *as the
    approving manager*, which is the accountability property the whole queue
    exists for and cannot be checked from the draft row alone.
    """
    calls: list[tuple] = []

    def handler(session, actor, client, payload):
        calls.append((actor.id, client, payload.product_id))

    draft_types.register("TEST_MARK", schema=_MarkPayload, handler=handler)
    yield calls
    draft_types._REGISTRY.pop("TEST_MARK", None)


@pytest.fixture
def manager():
    """A human: may read, propose and decide."""
    return TokenActor(
        "manager-1", frozenset({"draft.read", "draft.create", "draft.decide"})
    )


@pytest.fixture
def robot():
    """The agent's real permission set: it may propose, never decide."""
    return TokenActor("robot-1", frozenset({"draft.read", "draft.create"}))


def _make(session, actor, **kw):
    """Create a valid draft, letting any single field be overridden.

    `setdefault` rather than passing the defaults positionally: a test that
    wants to override `reasoning` would otherwise supply it twice and fail with
    a TypeError about a duplicate keyword argument, which says nothing about
    what the test was checking.
    """
    kw.setdefault("reasoning", "milk expires tomorrow")
    kw.setdefault("payload", {"product_id": 1, "new_price": "9.99"})
    return drafts.create_draft(
        session,
        actor,
        client=ClientType.MCP_AGENT,
        draft_type="TEST_MARK",
        **kw,
    )


def test_create_records_who_proposed_and_through_which_door(
    session, robot, handler_calls
):
    draft = _make(session, robot)

    assert draft.status == DraftStatus.PENDING
    assert draft.created_by == "robot-1"
    assert draft.created_via == ClientType.MCP_AGENT
    assert draft.decided_by is None
    assert draft.decided_at is None


def test_create_refuses_an_unknown_draft_type(session, robot):
    with pytest.raises(ValidationError):
        drafts.create_draft(
            session,
            robot,
            client=ClientType.MCP_AGENT,
            draft_type="DROP_EVERYTHING",
            payload={},
            reasoning="trust me",
        )


def test_create_refuses_a_payload_of_the_wrong_shape(session, robot, handler_calls):
    with pytest.raises(ValidationError):
        drafts.create_draft(
            session,
            robot,
            client=ClientType.MCP_AGENT,
            draft_type="TEST_MARK",
            payload={"product_id": "not a number", "new_price": "9.99"},
            reasoning="oops",
        )


def test_create_refuses_an_empty_reason(session, robot, handler_calls):
    """A proposal with no reasoning is a button with no label."""
    with pytest.raises(ValidationError):
        _make(session, robot, reasoning="   ")


def test_create_requires_the_create_permission(session, handler_calls):
    nobody = TokenActor("nobody", frozenset())

    with pytest.raises(PermissionDeniedError):
        _make(session, nobody)


def test_the_agent_cannot_approve_its_own_draft(session, robot, handler_calls):
    """The security property decision 1 in FEATURES-PLAN.md exists to create.

    Checked two ways on purpose: the call is refused, AND the handler did not
    run. A refusal that is only an exception, with the side effect already
    committed, is not a refusal.
    """
    draft = _make(session, robot)

    with pytest.raises(PermissionDeniedError):
        drafts.approve_draft(
            session, robot, client=ClientType.MCP_AGENT, draft_id=draft.id
        )

    session.refresh(draft)
    assert draft.status == DraftStatus.PENDING
    assert handler_calls == []


def test_approve_runs_the_handler_as_the_approving_manager(
    session, robot, manager, handler_calls
):
    """The proposer is the robot; the actor the handler receives is the human."""
    draft = _make(session, robot)

    approved = drafts.approve_draft(
        session, manager, client=ClientType.WEB_UI, draft_id=draft.id
    )

    assert approved.status == DraftStatus.EXECUTED
    assert approved.decided_by == "manager-1"
    assert approved.decided_via == ClientType.WEB_UI
    assert approved.decided_at is not None
    assert handler_calls == [("manager-1", ClientType.WEB_UI, 1)]


def test_approve_revalidates_a_payload_the_manager_edited(
    session, robot, manager, handler_calls
):
    """The second validation - the one that guards the browser."""
    draft = _make(session, robot)

    with pytest.raises(ValidationError):
        drafts.approve_draft(
            session,
            manager,
            client=ClientType.WEB_UI,
            draft_id=draft.id,
            payload={"product_id": "still not a number", "new_price": "9.99"},
        )

    session.refresh(draft)
    assert draft.status == DraftStatus.PENDING
    assert handler_calls == []


def test_an_edited_payload_is_what_runs_and_what_is_stored(
    session, robot, manager, handler_calls
):
    draft = _make(session, robot)

    drafts.approve_draft(
        session,
        manager,
        client=ClientType.WEB_UI,
        draft_id=draft.id,
        payload={"product_id": 99, "new_price": "1.00"},
    )

    assert handler_calls == [("manager-1", ClientType.WEB_UI, 99)]
    session.refresh(draft)
    assert draft.payload["product_id"] == 99


def test_an_expired_draft_cannot_be_approved(session, robot, manager, handler_calls):
    draft = _make(session, robot, expires_in_hours=0)

    with pytest.raises(ValidationError) as exc:
        drafts.approve_draft(
            session, manager, client=ClientType.WEB_UI, draft_id=draft.id
        )

    assert "expired" in str(exc.value).lower()
    assert handler_calls == []


def test_a_draft_cannot_be_approved_twice(session, robot, manager, handler_calls):
    """Without this the handler would run again on a second click."""
    draft = _make(session, robot)
    drafts.approve_draft(session, manager, client=ClientType.WEB_UI, draft_id=draft.id)

    with pytest.raises(ValidationError):
        drafts.approve_draft(
            session, manager, client=ClientType.WEB_UI, draft_id=draft.id
        )

    assert len(handler_calls) == 1


def test_a_rejected_draft_cannot_then_be_approved(
    session, robot, manager, handler_calls
):
    draft = _make(session, robot)
    drafts.reject_draft(session, manager, client=ClientType.WEB_UI, draft_id=draft.id)

    with pytest.raises(ValidationError):
        drafts.approve_draft(
            session, manager, client=ClientType.WEB_UI, draft_id=draft.id
        )

    assert handler_calls == []


def test_reject_is_terminal_and_runs_nothing(session, robot, manager, handler_calls):
    draft = _make(session, robot)

    rejected = drafts.reject_draft(
        session, manager, client=ClientType.WEB_UI, draft_id=draft.id
    )

    assert rejected.status == DraftStatus.REJECTED
    assert rejected.decided_by == "manager-1"
    assert rejected.decided_via == ClientType.WEB_UI
    assert handler_calls == []


def test_the_agent_cannot_reject_either(session, robot, handler_calls):
    """Rejecting is also a decision. draft.create does not imply it."""
    draft = _make(session, robot)

    with pytest.raises(PermissionDeniedError):
        drafts.reject_draft(
            session, robot, client=ClientType.MCP_AGENT, draft_id=draft.id
        )


def test_get_draft_raises_rather_than_returning_none(session, manager):
    with pytest.raises(NotFoundError):
        drafts.get_draft(session, manager, draft_id=999_999_999)


def test_approving_a_draft_that_does_not_exist_is_not_found(session, manager):
    with pytest.raises(NotFoundError):
        drafts.approve_draft(
            session, manager, client=ClientType.WEB_UI, draft_id=999_999_999
        )


def test_reading_requires_the_read_permission(session, handler_calls):
    nobody = TokenActor("nobody", frozenset())

    with pytest.raises(PermissionDeniedError):
        drafts.list_drafts(session, nobody)


def test_list_filters_by_status_and_the_count_matches(
    session, robot, manager, handler_calls
):
    first = _make(session, robot)
    _make(session, robot)
    drafts.reject_draft(session, manager, client=ClientType.WEB_UI, draft_id=first.id)

    pending = drafts.list_drafts(session, manager, status=DraftStatus.PENDING)
    total = drafts.count_drafts(session, manager, status=DraftStatus.PENDING)

    assert all(d.status == DraftStatus.PENDING for d in pending)
    assert first.id not in [d.id for d in pending]
    assert total == len(pending)


def test_list_returns_newest_first(session, robot, manager, handler_calls):
    older = _make(session, robot)
    newer = _make(session, robot)

    found = drafts.list_drafts(session, manager, status=DraftStatus.PENDING)
    ids = [d.id for d in found]

    assert ids.index(newer.id) < ids.index(older.id)
