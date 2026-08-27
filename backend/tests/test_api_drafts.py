"""HTTP tests for the draft approval queue.

These test **translation** - that a domain exception becomes the right status
and the right body, that money crosses the wire without losing precision, that
an unauthenticated request is refused. They do not re-test the business rules;
those live in tests/test_drafts.py against the service directly, which is the
entire point of having a service layer.

The one rule that IS re-tested here is the agent's inability to approve, and
deliberately so: it is the security property of the gate, and testing it once
at the service layer would not notice a route that forgot to pass the actor
through.
"""

from decimal import Decimal

import pytest
from pydantic import BaseModel

from core.actor import TokenActor
from core.enums import ClientType, DraftStatus
from services import draft_types, drafts


class _MarkPayload(BaseModel):
    product_id: int


@pytest.fixture
def handler_calls():
    """A registered draft type recording every execution of its handler."""
    calls: list[int] = []

    draft_types.register(
        "TEST_MARK",
        schema=_MarkPayload,
        handler=lambda session, actor, client, payload: calls.append(
            payload.product_id
        ),
    )
    yield calls
    draft_types._REGISTRY.pop("TEST_MARK", None)


@pytest.fixture
def a_draft(session, actor, handler_calls):
    """A pending draft, proposed over MCP the way the agent would."""
    return drafts.create_draft(
        session,
        actor,
        client=ClientType.MCP_AGENT,
        draft_type="TEST_MARK",
        payload={"product_id": 7},
        reasoning="expires tomorrow",
    )


def test_list_returns_items_and_total(client, a_draft):
    response = client.get("/drafts", params={"status": "pending"})

    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert any(d["id"] == a_draft.id for d in body["items"])


def test_an_unknown_status_is_rejected_before_the_service(client):
    """`status` is typed as the enum, so FastAPI refuses a typo with a 422.

    Without the enum this would reach the service, match nothing, and return an
    empty list - a silent wrong answer rather than a loud one.
    """
    response = client.get("/drafts", params={"status": "pendign"})

    assert response.status_code == 422


def test_get_unknown_draft_is_404_with_the_error_envelope(client):
    response = client.get("/drafts/999999999")

    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "NotFoundError"
    assert "detail" in body


def test_approve_executes_and_returns_the_updated_draft(client, a_draft, handler_calls):
    response = client.post(f"/drafts/{a_draft.id}/approve", json={})

    assert response.status_code == 200
    assert response.json()["status"] == DraftStatus.EXECUTED
    assert handler_calls == [7]


def test_approve_records_the_web_ui_as_the_deciding_door(client, a_draft):
    """Proposed over MCP, decided in the browser - the whole point of the queue."""
    body = client.post(f"/drafts/{a_draft.id}/approve", json={}).json()

    assert body["created_via"] == ClientType.MCP_AGENT
    assert body["decided_via"] == ClientType.WEB_UI


def test_an_edited_payload_is_what_runs(client, a_draft, handler_calls):
    """The inline adjuster reaches the handler, not just the stored row."""
    response = client.post(
        f"/drafts/{a_draft.id}/approve", json={"payload": {"product_id": 42}}
    )

    assert response.status_code == 200
    assert handler_calls == [42]


def test_approving_with_a_bad_edited_payload_is_400(client, a_draft, handler_calls):
    """400 and not 422: a payload that fails its draft type's schema is a
    business rule failing, not the request body failing FastAPI's own check."""
    response = client.post(
        f"/drafts/{a_draft.id}/approve",
        json={"payload": {"product_id": "not a number"}},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "ValidationError"
    assert handler_calls == []


def test_approving_twice_is_400_and_runs_the_handler_once(
    client, a_draft, handler_calls
):
    """A double-click must not apply the change twice."""
    client.post(f"/drafts/{a_draft.id}/approve", json={})
    second = client.post(f"/drafts/{a_draft.id}/approve", json={})

    assert second.status_code == 400
    assert handler_calls == [7]


def test_reject_returns_the_rejected_draft_and_runs_nothing(
    client, a_draft, handler_calls
):
    response = client.post(f"/drafts/{a_draft.id}/reject")

    assert response.status_code == 200
    assert response.json()["status"] == DraftStatus.REJECTED
    assert handler_calls == []


def test_money_serialises_as_a_string_not_a_number(client, session, actor, handler_calls):
    """A JSON number here is a float64 and would eventually lose a cent."""
    draft = drafts.create_draft(
        session,
        actor,
        client=ClientType.MCP_AGENT,
        draft_type="TEST_MARK",
        payload={"product_id": 7},
        reasoning="x",
        cost_at_risk=Decimal("40000.50"),
        projected_recovery=Decimal("12000.25"),
    )

    body = client.get(f"/drafts/{draft.id}").json()

    assert body["cost_at_risk"] == "40000.50"
    assert isinstance(body["cost_at_risk"], str)
    assert body["projected_recovery"] == "12000.25"


def test_a_draft_with_no_financial_dimension_reports_null_not_zero(client, a_draft):
    """NULL and 0.00 are different facts and must stay distinguishable."""
    body = client.get(f"/drafts/{a_draft.id}").json()

    assert body["cost_at_risk"] is None
    assert body["projected_recovery"] is None


def test_is_expired_is_on_the_wire(client, a_draft):
    """The frontend renders this; it must never recompute it from expires_at.

    Same reasoning as needs_reorder on products: shipping the answer rather
    than the inputs keeps one definition of the rule.
    """
    body = client.get(f"/drafts/{a_draft.id}").json()

    assert body["is_expired"] is False


def test_an_unauthenticated_request_is_refused(unauthenticated_client):
    response = unauthenticated_client.get("/drafts")

    assert response.status_code == 401


def test_an_actor_without_decide_cannot_approve_over_http(
    client, session, a_draft, handler_calls
):
    """The agent's permission set, exercised through the real route.

    Tested here as well as at the service layer because a route that forgot to
    pass the actor down would still pass every service-level test.
    """
    from api.deps import get_actor
    from api.main import app

    app.dependency_overrides[get_actor] = lambda: TokenActor(
        "robot-1", frozenset({"draft.read", "draft.create"})
    )

    response = client.post(f"/drafts/{a_draft.id}/approve", json={})

    assert response.status_code == 403
    assert response.json()["error"] == "PermissionDeniedError"
    assert handler_calls == []
