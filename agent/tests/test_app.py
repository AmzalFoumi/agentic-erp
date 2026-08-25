"""Gate 20's proof: the HTTP surface streams, and it does not weaken Gate 19.

**No network, no Gemini, no Postgres.** The model and toolset come from the same
stand-ins Gate 19 built (`scripted_model`, `RecordingToolset`), injected through
`app.get_runtime`; the database is a `FakeStore` recording what would have been
written. So these tests are about the *routes*, and a failure here is a failure
in app.py rather than in something it depends on.

The assertion that matters most is the same one as in test_approval.py:
`RecordingToolset.executed`. A version of this service that streamed beautifully
while quietly running a write tool without approval would pass every
looks-right assertion and be the worst bug in the project.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.ui.vercel_ai import VercelAIAdapter

import app as app_module
from actor import SystemActor, UserActor
from app import HOST, PORT, SDK_VERSION, Runtime, app, get_runtime
from conversation import Message, decode_state

from .fakes import scripted_model
from .test_approval import RecordingToolset

CONVERSATION_ID = 7


class FakeStore:
    """Records what store.py would have written. See this module's docstring.

    Deliberately not a Mock: the approve/deny tests need `load_pending` to hand
    back the exact bytes `save_pending` was given, because that round trip is
    how a real browser gets the approval card after a reload. A Mock would
    return a sentinel and the test would prove nothing about the round trip.
    """

    def __init__(self) -> None:
        self.appended: list[Message] = []
        self.pending: bytes | None = None
        self.cleared = 0
        self.started_by: str | None = None
        self.owner: str | None = None

    def start_conversation(
        self, *, title: str | None = None, started_by: str = "system"
    ) -> int:
        self.started_by = started_by
        return CONVERSATION_ID

    def conversation_exists(
        self, conversation_id: int, *, actor_id: str | None = None
    ) -> bool:
        """Gate 25 added the ownership check; this double mirrors its signature.

        `owner` defaults to None meaning "belongs to whoever asks", so the
        existing tests - which are about routing and streaming, not ownership -
        are unaffected. `test_a_conversation_belonging_to_someone_else_is_a_404`
        sets it.
        """
        if conversation_id != CONVERSATION_ID:
            return False
        if actor_id is not None and self.owner is not None:
            return actor_id == self.owner
        return True

    def append_message(self, conversation_id: int, message: Message) -> None:
        assert conversation_id == CONVERSATION_ID
        self.appended.append(message)

    def load_history(self, conversation_id: int) -> list[Message]:
        return list(self.appended)

    def save_pending(self, conversation_id: int, resume_state: bytes) -> None:
        self.pending = resume_state

    def clear_pending(self, conversation_id: int) -> None:
        self.cleared += 1
        self.pending = None

    def load_pending(self, conversation_id: int) -> tuple[bytes, Any] | None:
        if self.pending is None:
            return None
        from datetime import datetime, timezone

        return self.pending, datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def fake_store(monkeypatch: pytest.MonkeyPatch) -> FakeStore:
    """Replace every store function app.py calls, and only those.

    Patched on `app_module.store` rather than on the store module itself so a
    missed function shows up as an AttributeError naming it, instead of quietly
    reaching the real database.
    """
    fake = FakeStore()
    monkeypatch.setattr(app_module, "store", fake)
    return fake


@pytest.fixture(autouse=True)
def _auth_off(monkeypatch: pytest.MonkeyPatch):
    """Gate 25 default for this file: authentication off, overrides cleared.

    Most tests here are about routing, streaming and approval - not about who is
    asking - and requiring a signed token in each would be noise. The tests that
    ARE about identity turn it back on explicitly.

    Autouse, and it clears `dependency_overrides` on the way out, so these tests
    stay order-independent. Overrides live on the module-level `app` object and
    would otherwise leak from whichever test ran last, which makes a failure
    depend on collection order - the worst kind to debug.
    """
    monkeypatch.setattr(app_module.settings, "auth_enabled", False)
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def toolset() -> RecordingToolset:
    return RecordingToolset()


def _client(model: Any, toolset: RecordingToolset) -> TestClient:
    """A TestClient whose turns run against the given stand-ins.

    `dependency_overrides` is FastAPI's own seam for this, which is why
    `get_runtime` exists at all - see app.Runtime.
    """
    app.dependency_overrides[get_runtime] = lambda: Runtime(
        model=model, toolset=toolset
    )
    # Gate 25: these tests are about routing, streaming and approval, not about
    # who is asking - so they supply an identity rather than a token. The same
    # `dependency_overrides` seam, used for the same reason as `get_runtime`
    # above: the alternative is minting a signed JWT in every test of a file
    # that has nothing to do with signatures.
    #
    # What `get_actor` does with a real header, and that it refuses a request
    # without one, is asserted in `test_requires_a_bearer_token_when_auth_is_on`
    # below - which is where that belongs.
    app.dependency_overrides[app_module.get_actor] = lambda: SystemActor()
    return TestClient(app)


def _submit(text: str) -> dict[str, Any]:
    """The request body a Vercel AI client posts for a new question.

    Written out rather than generated because it is the wire contract: if
    @ai-sdk/react changes shape, this literal is what fails, in one place, with
    the diff visible.
    """
    return {
        "trigger": "submit-message",
        "id": "chat-under-test",
        "messages": [
            {"id": "m1", "role": "user", "parts": [{"type": "text", "text": text}]}
        ],
    }


def _respond_to_approval(pending_state: bytes, *, approved: bool) -> dict[str, Any]:
    """The request body a client posts to approve or deny.

    **Built from the paused run's own dumped messages, not hand-written.** That
    is the realistic path - the browser renders what `GET /conversations/{id}`
    gave it and posts it back with one part's state flipped - and it means this
    helper does not have to invent an approval `id`, which is opaque and
    generated by the adapter.

    `sdk_version` matches app.SDK_VERSION deliberately: below 6 there is no
    `approval-requested` part to flip at all, and the assertion below says so.
    """
    messages = [
        message.model_dump(by_alias=True, exclude_none=True)
        for message in VercelAIAdapter.dump_messages(
            decode_state(pending_state), sdk_version=SDK_VERSION
        )
    ]

    flipped = 0
    for message in messages:
        for part in message.get("parts", []):
            if part.get("state") == "approval-requested":
                part["state"] = "approval-responded"
                part["approval"] = {"id": part["approval"]["id"], "approved": approved}
                flipped += 1

    # A body with nothing flipped would resume with no decision and the test
    # would fail somewhere confusing. Fail here, naming the reason.
    assert flipped == 1, f"expected exactly one approval-requested part, found {flipped}"

    return {"trigger": "submit-message", "id": "chat-under-test", "messages": messages}


def _turn(client: TestClient, body: dict[str, Any]) -> str:
    """POST one turn and return the whole streamed body as text."""
    response = client.post(f"/conversations/{CONVERSATION_ID}/turns", json=body)
    assert response.status_code == 200, response.text
    return response.text


def test_health_reports_the_configured_model(fake_store: FakeStore) -> None:
    """The one route with no model, no tools, and no database behind it."""
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    # The resolved ID, not the alias - see app.health's docstring.
    assert response.json()["model"]


def test_creating_a_conversation_returns_its_id(fake_store: FakeStore) -> None:
    response = TestClient(app).post("/conversations")

    assert response.status_code == 200
    assert response.json() == {"conversation_id": CONVERSATION_ID}


def test_a_read_question_streams_and_persists(
    fake_store: FakeStore, toolset: RecordingToolset
) -> None:
    """The control case: an ordinary question, end to end over HTTP.

    Without this, a bug that broke every turn would look identical to a passing
    approval suite.
    """
    model = scripted_model(
        ModelResponse(parts=[ToolCallPart("list_products", {})]),
        ModelResponse(parts=[TextPart("Nine products are low on stock.")]),
    )

    body = _turn(_client(model, toolset), _submit("What's low on stock?"))

    assert "Nine products are low on stock." in body
    assert [name for name, _ in toolset.executed] == ["list_products"]
    # on_complete persisted both halves, exactly as run_turn's caller would.
    assert [m.role for m in fake_store.appended] == ["user", "assistant"]
    assert fake_store.appended[0].content == "What's low on stock?"
    assert fake_store.pending is None


def test_a_mutating_question_pauses_over_http(
    fake_store: FakeStore, toolset: RecordingToolset
) -> None:
    """**The gate survives the HTTP boundary.** The tool does not run.

    And the pause is durable: `save_pending` got the bytes, so a browser that
    reloads can still be shown what it is being asked to approve. Gate 19 held
    this in memory only and deliberately left it to this gate.
    """
    model = scripted_model(
        ModelResponse(
            parts=[
                ToolCallPart(
                    "adjust_stock",
                    {"sku": "RICE-5KG", "quantity": 20},
                    tool_call_id="call-1",
                )
            ]
        ),
    )

    _turn(_client(model, toolset), _submit("Set rice stock to 20."))

    assert toolset.executed == []
    assert fake_store.pending is not None
    # A half-finished turn is not conversation history.
    assert fake_store.appended == []


def _pause(fake_store: FakeStore, toolset: RecordingToolset) -> tuple[TestClient, bytes]:
    """Drive a turn to the paused state over HTTP and hand back the pieces.

    The same scripted model instance serves both requests, so the second
    scripted response is what the model says after the decision arrives -
    matching test_approval.py's `_pause_on_adjust_stock`.
    """
    model = scripted_model(
        ModelResponse(
            parts=[
                ToolCallPart(
                    "adjust_stock",
                    {"sku": "RICE-5KG", "quantity": 20},
                    tool_call_id="call-1",
                )
            ]
        ),
        ModelResponse(parts=[TextPart("Done.")]),
    )
    client = _client(model, toolset)
    _turn(client, _submit("Set rice stock to 20."))

    assert fake_store.pending is not None
    return client, fake_store.pending


def test_approving_over_http_runs_the_tool(
    fake_store: FakeStore, toolset: RecordingToolset
) -> None:
    """Approve: the tool executes, with the original arguments.

    Asserting on `executed` rather than on the streamed text is the point. A
    resume that streamed "Done." without running the tool would pass a
    text-only assertion and be completely broken.
    """
    client, pending_state = _pause(fake_store, toolset)

    _turn(client, _respond_to_approval(pending_state, approved=True))

    assert toolset.executed == [("adjust_stock", {"sku": "RICE-5KG", "quantity": 20})]
    # A resumed turn is a completed turn: both halves persisted, park cleared.
    assert [m.role for m in fake_store.appended] == ["user", "assistant"]
    assert fake_store.appended[0].content == "Set rice stock to 20."
    assert fake_store.cleared == 1
    assert fake_store.pending is None


def test_denying_over_http_does_not_run_the_tool(
    fake_store: FakeStore, toolset: RecordingToolset
) -> None:
    """Deny: the tool never runs, and the turn still finishes.

    Both halves matter. A denial that left the turn parked forever would be as
    broken as one that ran the tool - and it would leave a row in the database
    saying a human still owes an answer they already gave.
    """
    client, pending_state = _pause(fake_store, toolset)

    _turn(client, _respond_to_approval(pending_state, approved=False))

    assert toolset.executed == []
    assert fake_store.cleared == 1
    assert fake_store.pending is None


def test_reload_of_a_parked_conversation_shows_the_approval(
    fake_store: FakeStore, toolset: RecordingToolset
) -> None:
    """GET returns the parked turn, which is what re-renders the approval card.

    This is the whole reason `pending_state` is a column rather than a variable:
    the answer to "what am I being asked to approve" has to outlive the request
    that asked it.
    """
    client, _ = _pause(fake_store, toolset)

    response = client.get(f"/conversations/{CONVERSATION_ID}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["pending_since"] is not None
    states = [
        part.get("state")
        for message in payload["messages"]
        for part in message.get("parts", [])
    ]
    assert "approval-requested" in states


def test_an_unknown_conversation_is_a_404(fake_store: FakeStore) -> None:
    """An empty conversation and a typo'd id are different things.

    Both give `load_history` an empty list, so without the explicit existence
    check a wrong id would look like a working blank chat and then fail later on
    a foreign key.
    """
    response = TestClient(app).get("/conversations/999")

    assert response.status_code == 404


def test_the_service_binds_to_loopback() -> None:
    """**The auth deferral, as an assertion.**

    Cheap, and it is the point: per docs/PLAN.md, making this surface reachable
    off-machine expires the auth deferral and the login gate must land first. A
    constant nobody tests is a constant somebody edits during a debugging
    session at midnight. See app.HOST's comment.
    """
    assert HOST == "127.0.0.1"
    # Not 8000 (FastAPI) and not 8001 (its MCP server).
    assert PORT == 8002


# ---------------------------------------------------------------------------
# Gate 25: who is asking
# ---------------------------------------------------------------------------


def test_requires_a_bearer_token_when_auth_is_on(monkeypatch):
    """No token, no turn - and a well-formed 401 rather than a bare status.

    The route this guards will run a data-changing tool against the ERP if a
    human approves it. Until gate 25 nothing here knew *which* human: Gate 19
    gave us approval, and approval is not authorization.
    """
    monkeypatch.setattr(app_module.settings, "auth_enabled", True)

    response = TestClient(app).post(
        f"/conversations/{CONVERSATION_ID}/turns", json={"messages": []}
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_a_bearer_token_becomes_an_actor_carrying_it(monkeypatch):
    """The token travels; the `sub` is read for a label only.

    ⚠️ Note what is NOT asserted: that the token is valid. The agent holds no
    signing keys and deliberately does not verify - `backend/mcp_server/` does,
    against ThunderID's published keys. So an unsigned token like the one below
    is accepted *here* and refused at the first tool call, which is the design
    and not a hole. See the docstring on `app.get_actor`.
    """
    import base64
    import json as _json

    def _segment(payload: dict) -> str:
        raw = _json.dumps(payload).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    token = f"header.{_segment({'sub': 'user-42'})}.signature"

    monkeypatch.setattr(app_module.settings, "auth_enabled", True)

    class _Request:
        headers = {"authorization": f"Bearer {token}"}

    actor = app_module.get_actor(_Request())  # type: ignore[arg-type]

    assert isinstance(actor, UserActor)
    assert actor.id == "user-42"
    assert actor.token == token
    # The credential must never land in a log line or a pytest failure.
    assert token not in repr(actor)


def test_an_unreadable_token_is_labelled_rather_than_fatal(monkeypatch):
    """`sub` is a label, so a malformed token must not become a 500.

    The ERP still gets the last word: the token travels unchanged and is
    refused there. Turning an unreadable label into a crash would mean the
    agent deciding something it has no information to decide.
    """
    monkeypatch.setattr(app_module.settings, "auth_enabled", True)

    class _Request:
        headers = {"authorization": "Bearer not-a-jwt"}

    actor = app_module.get_actor(_Request())  # type: ignore[arg-type]

    assert actor.id == "unknown"
    assert actor.token == "not-a-jwt"


def test_a_new_conversation_records_who_started_it(fake_store, monkeypatch):
    """Half one of the inherited defect: conversations now have an owner.

    The column existed since gate 17 and was never filled in. Nothing could
    check ownership while every row said "system".
    """
    monkeypatch.setattr(app_module.settings, "auth_enabled", False)
    app.dependency_overrides[app_module.get_actor] = lambda: SystemActor("user-7")

    response = TestClient(app).post("/conversations")

    assert response.status_code == 200
    assert fake_store.started_by == "user-7"


def test_a_conversation_belonging_to_someone_else_is_a_404(fake_store, monkeypatch):
    """⚠️ Half two, and the reason this was a write-safety problem.

    Conversation ids are sequential integers. Before this, changing a number in
    the URL opened someone else's conversation - and posting a turn to it ran
    the agent against their history, which is how a product got created nobody
    asked for during gate 24's verification.

    404 rather than 403 on purpose: a 403 would confirm the conversation exists
    and belongs to someone, which hands out a map of which ids are real.
    """
    monkeypatch.setattr(app_module.settings, "auth_enabled", True)
    fake_store.owner = "someone-else"
    app.dependency_overrides[app_module.get_actor] = lambda: SystemActor("intruder")

    client = TestClient(app)

    assert client.get(f"/conversations/{CONVERSATION_ID}").status_code == 404
    assert (
        client.post(f"/conversations/{CONVERSATION_ID}/turns", json={"messages": []})
    ).status_code == 404
    # The write path is the one that matters: nothing was run, so nothing was
    # appended and no turn was parked.
    assert fake_store.appended == []
    assert fake_store.pending is None
