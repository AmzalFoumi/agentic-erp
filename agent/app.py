"""The agent's own HTTP surface. Loopback only, and that is load-bearing.

Gate 20. Four routes, one of which streams: a browser can hold a conversation
with the agent, and Gate 19's approval pause survives the round trip.

**Why this file is allowed to import pydantic_ai.** Gate 17 established a
"runtime cluster" - the only files in agent/ that may name the framework -
and Gate 17's wording said a future HTTP route would not need to. Gate 20
narrowed that claim rather than quietly keeping it: `pydantic_ai.ui` ships
`VercelAIAdapter`, an implementation of the Vercel AI Data Stream Protocol
that `useChat` from @ai-sdk/react consumes directly, *including native
tool-approval parts* (`ToolApprovalRequested` / `ToolApprovalResponded` in
`pydantic_ai/ui/vercel_ai/request_types.py`). Hand-rolling our own event
types to preserve the claim would have meant reinventing a documented
standard and re-implementing approval on top of it. The adapter takes an
`Agent`, so this file joins the cluster - see agent/pyproject.toml.

**What the protocol buys, concretely.** An approve/deny is not a second
endpoint. In this protocol it is a tool-result part inside the message list the
client posts, which `UIAdapter.deferred_tool_results` extracts on its own
("Deferred tool results extracted from the request, used for tool approval
workflows"). So POST /turns serves both "ask a question" and "resolve an
approval", and `resume_turn`'s decision map never becomes an HTTP concern.

**Who owns the conversation.** The client owns the in-flight wire state; the
database owns the durable record. That is not a preference - `ui/_adapter.py`
concatenates rather than overrides:

    message_history = [*(message_history or []), *frontend_messages]

Passing stored history *and* letting the client post its list would send the
whole conversation to the model twice, which would present as the model going
strange rather than as a wiring bug. So this file passes no `message_history`,
persists through `on_complete`, and serves history back on GET so a reload can
hydrate.
"""

import base64
import json
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.models import Model
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import RequestData

import store
from actor import Actor, SystemActor, UserActor
from config import settings
from conversation import build_agent, decode_state, to_model_history, turn_from_result


class _SanitizingVercelAIAdapter(VercelAIAdapter):
    """Works around a real wire-format gap, not a version we are behind on.

    `ai`/`@ai-sdk/react` v7's `useChat` always stamps an `id` on a resubmitted
    `reasoning` part (so a streamed reasoning part can be updated in place -
    the `reasoning-{id}` case in the AI SDK docs). `pydantic_ai.ui.vercel_ai`'s
    `ReasoningUIPart` request model has no `id` field and forbids extras, so
    that same part 422s the moment a client resubmits history containing one -
    which happens on every approval round-trip, since Gemini reasons before
    every tool call. Confirmed still true on pydantic-ai's `main` as of
    2026-08-13, so this is not a version to bump past; it is a permanent
    tolerance shim until upstream adds the field.
    """

    @classmethod
    def build_run_input(cls, body: bytes) -> RequestData:
        data = json.loads(body)
        for message in data.get("messages", []):
            for part in message.get("parts", []):
                if part.get("type") == "reasoning":
                    part.pop("id", None)
        return super().build_run_input(json.dumps(data).encode())

# 127.0.0.1, not 0.0.0.0, and not a default inherited from uvicorn. Written here
# explicitly so the constraint is a line of code someone has to delete rather
# than a flag someone forgets to pass.
#
# **Gate 25 authenticated this surface, and the binding still stays.** Until
# then nothing here knew *which* human approved a data-changing tool call -
# Gate 19 gave us approval, and approval is not authorization. Now `get_actor`
# below demands a bearer token and the ERP verifies it, so the sentence that
# used to sit here ("there is no authentication on this surface") is no longer
# true.
#
# It is still not enough to open the port. Nothing here rate-limits an
# anonymous caller, ThunderID's certificate is self-signed, and `AUTH_ENABLED`
# is one boolean away from turning all of it off silently. Those are Gate 26's
# list, and this line is deleted there - last, not first. Binding off this
# interface, or putting a tunnel, reverse
# proxy, Docker port publish, or cloud deployment in front of it, makes that
# reachable by anyone who can route to the port.
#
# Per docs/PLAN.md that is not a configuration change: it expires the auth
# deferral, and the login gate lands before any further agent work. The list of
# what counts is in docs/AGENT-PLAN.md under "The stop condition"; it is a list
# rather than a principle because the dangerous version of this mistake is a
# thirty-second convenience, not a decision.
HOST = "127.0.0.1"

# 8000 is the FastAPI backend, 8001 is its MCP server, so the agent takes 8002.
PORT = 8002

app = FastAPI(
    title="Agentic ERP - agent service",
    description=(
        "The AI agent's own HTTP surface. Loopback only; see app.py's HOST "
        "comment before changing where this binds."
    ),
)


def get_actor(request: Request) -> Actor:
    """Who is asking. **The seam where real authentication landed, at gate 25.**

    Deliberately the same shape as `backend/api/deps.py`'s `get_actor()`. The
    bet that shape represented has paid out: the body changed and nothing else
    in `agent/` did, because every call site already took an `Actor`.

    The token arrives in the `Authorization` header, forwarded by the Next.js
    route at `frontend/src/app/api/agent/[...path]/route.ts` from the browser's
    session.

    **This function does not verify the token, and that is deliberate.** The
    agent holds no signing keys and has no JWKS client; it treats the token as
    an opaque credential and lets the MCP server - which does verify, against
    ThunderID's published keys - be the judge. Adding a second verification path
    here would be two chances to get it right and two chances to get it wrong.
    An invalid token therefore does not fail here; it fails at the first tool
    call, as a refusal from the ERP.

    **One narrow exception, and it is not verification.** A token whose payload
    cannot be decoded at all is refused here with a 401. That is a question
    about the token's *shape*, answerable without any key - "is this even a
    JWT" rather than "did ThunderID sign this". It is refused rather than
    labelled because `_owns` gates on the subject, and a token with no readable
    subject has no identity to gate on. See `_subject_of`.

    `auth_enabled=False` restores the pre-gate-25 behaviour of handing out a
    SystemActor. That is for the test suite and for local work unrelated to
    auth; it must never be set in a deployed environment, and it defaults to
    True so that a missing setting fails closed.
    """
    if not settings.auth_enabled:
        return SystemActor()

    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        # 401, not 403: the difference is "we do not know who you are" versus
        # "we know, and no". `WWW-Authenticate` is what makes it a well-formed
        # 401 rather than a bare status code.
        raise HTTPException(
            status_code=401,
            detail="This request carries no bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    subject = _subject_of(token)
    if subject is None:
        # A token whose `sub` cannot be read is refused rather than labelled.
        # This used to fall back to the literal string "unknown", which was
        # harmless while the id only labelled a log line and became a defect at
        # gate 25 when `_owns` started gating on it: every undecodable token
        # shared one owner value, so those callers could read each other's
        # conversations. Raised by CodeRabbit on PR #30.
        raise HTTPException(
            status_code=401,
            detail="This bearer token could not be read.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UserActor(token, actor_id=subject)


def _subject_of(token: str) -> str | None:
    """Read the `sub` claim out of a JWT **without verifying it**.

    Safe here only because of what the value is allowed to do: label a log line.
    See the warning on `UserActor` - and note the frontend's `subjectOf()` in
    `lib/auth/current-user.ts` does exactly this, for exactly this reason.

    Hand-decoded rather than reaching for a JWT library, which would put one in
    the agent's virtualenv and invite someone to conclude that verification
    belongs here.

    Returns `None` when there is no readable `sub`, and the caller turns that
    into a 401. It must not invent a placeholder: a shared placeholder is a
    shared identity, and `_owns` gates on this value.
    """
    try:
        payload = token.split(".")[1]
        # base64url needs its padding restored; Python's decoder is strict
        # about it where the JWT spec strips it.
        padded = payload + "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded))
        subject = claims.get("sub")
        return subject if isinstance(subject, str) and subject else None
    except Exception:
        return None


def _owns(conversation_id: int, actor: Actor) -> bool:
    """Does this conversation exist and belong to `actor`?

    `actor_id=None` when authentication is off, which means "do not check" -
    the pre-gate-25 behaviour, for the test suite and offline work.
    """
    actor_id = actor.id if settings.auth_enabled else None
    return store.conversation_exists(conversation_id, actor_id=actor_id)


def _require_own(conversation_id: int, actor: Actor) -> None:
    """404 unless this conversation exists and belongs to `actor`.

    404 rather than 403 deliberately. Conversation ids are sequential integers,
    so a 403 would confirm that id 41 exists and belongs to someone else, which
    hands out both a count and a map. "No such conversation" is the only answer
    that reveals nothing.
    """
    if not _owns(conversation_id, actor):
        raise HTTPException(
            status_code=404, detail=f"No conversation {conversation_id}"
        )


@dataclass
class Runtime:
    """The model and toolset a request runs against.

    Both default to None, meaning "build the real ones" - see
    conversation.build_agent. They exist as an injectable dependency so
    tests/test_app.py can substitute a FunctionModel and a recording toolset and
    exercise these routes with no network and no Gemini, exactly as Gate 19's
    tests do for `run_turn`. A dependency rather than monkeypatching, matching
    the `model=`/`toolset=` parameters conversation.py already carries.
    """

    model: Model | None = None
    toolset: AbstractToolset[Any] | None = None


def get_runtime() -> Runtime:
    """The real model and MCP toolset. Overridden in tests."""
    return Runtime()


# **Load-bearing, and the default is wrong for us.** VercelAIAdapter defaults
# `sdk_version=5` for backwards compatibility, and every approval feature this
# gate depends on is gated behind `>= 6`:
#
#   - `deferred_tool_results` returns None outright when sdk_version < 6
#     (_adapter.py:275-276), so an approval posted by the client is silently
#     dropped and the resumed run pauses again forever;
#   - `dump_messages` emits a resultless tool call as `state='input-available'`
#     instead of `'approval-requested'`, so a reloaded browser shows a tool
#     "running" with no approve/deny buttons.
#
# Neither failure raises - both just quietly do the wrong thing, which is why
# this constant exists once and three call sites read it rather than each
# passing a literal. Caught by tests/test_app.py, not by review.
#
# 7 rather than 6: the two emit the same wire (v7's data-stream protocol equals
# v6's), and the adapter's own docstring says to pass the client's real SDK
# major. `ai` 7.0.64 / `@ai-sdk/react` 4.0.67 are current as of 2026-08-13, so 7
# is what Gate 21 will install. **This is a floor on the frontend**: the panel
# cannot be built against AI SDK v5.
SDK_VERSION = 7


@app.get("/health")
def health() -> dict[str, str]:
    """Is the service up, and which model is it configured to call?

    The model is included because "up" is rarely the question anyone actually
    has - `gemini_model` is a setting that resolves through an alias table, so
    seeing the resolved ID is how you confirm .env said what you meant.
    """
    return {"status": "ok", "model": settings.gemini_model}


@app.post("/conversations")
def create_conversation(actor: Actor = Depends(get_actor)) -> dict[str, int]:
    """Start a conversation and return its id.

    Separate from the first turn on purpose: the id is what the browser puts in
    its URL, so it has to exist before anything streams. A turn that created its
    own conversation would mean the client learns the id at the end of a stream,
    which is exactly when a reload is most likely to lose it.
    """
    # Gate 25: the conversation is stamped with who started it, and every
    # route below checks that stamp. Before this, ids were sequential integers
    # with no owner - so changing a number in the URL opened someone else's
    # conversation, and posting a turn to it let the agent act on their history.
    return {"conversation_id": store.start_conversation(started_by=actor.id)}


@app.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: int, actor: Actor = Depends(get_actor)
) -> dict[str, Any]:
    """Everything a reloaded browser needs to carry on.

    Messages come back in the same wire format the streaming route emits -
    `VercelAIAdapter.dump_messages` - so one class both reads and writes the
    protocol and there is no second encoding to drift.

    **If a turn is parked awaiting approval, those messages are returned instead
    of the stored history**, because the parked bytes are the whole interrupted
    run: they contain this turn's question *and* the tool call waiting on a
    decision, which is what makes the approval card re-render after a reload.
    `pending_since` comes back alongside so the UI can show how stale it is.
    Nothing expires it automatically - see store.save_pending.
    """
    # Ownership first, before anything is read. A conversation belonging to
    # someone else must be indistinguishable from one that does not exist - see
    # store.conversation_exists - so this is a 404 rather than a 403.
    _require_own(conversation_id, actor)

    pending = store.load_pending(conversation_id)

    if pending is not None:
        state, since = pending
        return {
            "messages": VercelAIAdapter.dump_messages(
                decode_state(state), sdk_version=SDK_VERSION
            ),
            "pending_since": since.isoformat(),
        }

    # An unknown id and an empty conversation are indistinguishable here, since
    # `load_history` returns [] for both. That distinction is already made by
    # `_require_own` above, which 404s a conversation that does not exist as
    # well as one belonging to someone else - so an empty history at this point
    # is a real conversation nobody has spoken in yet, and returning it is
    # correct. The second `_owns` check that used to stand here was unreachable
    # and repeated the query; removed on CodeRabbit's finding, PR #30.
    history = store.load_history(conversation_id)

    return {
        "messages": VercelAIAdapter.dump_messages(
            to_model_history(history), sdk_version=SDK_VERSION
        ),
        "pending_since": None,
    }


@app.post("/conversations/{conversation_id}/turns")
async def run_turn_endpoint(
    conversation_id: int,
    request: Request,
    actor: Actor = Depends(get_actor),
    runtime: Runtime = Depends(get_runtime),
) -> Any:
    """Stream one turn. Also how an approval decision arrives.

    One endpoint for both because in this protocol they are the same request
    with a different message list - see this module's docstring. The client's
    posted messages are the history; nothing stored is passed in.
    """

    # The write-safety half of the same defect. GET leaking another person's
    # history is bad; POST is worse - it runs the agent against that history and
    # can create or change real inventory. Checked here as well as on GET,
    # because a client that never called GET can still post.
    _require_own(conversation_id, actor)

    agent = build_agent(
        settings, actor=actor, model=runtime.model, toolset=runtime.toolset
    )

    async def on_complete(result: AgentRunResult[Any]) -> None:
        """Persist whatever the run turned out to be.

        **A pause is a completed run**, whose `output` is a
        `DeferredToolRequests` rather than a string - which is why one callback
        covers both cases instead of needing a second hook that does not exist.
        `turn_from_result` makes that decision, in conversation.py, so it is
        made in one place.

        A paused turn appends nothing to `messages`: Gate 19's invariant is that
        a half-finished turn is not conversation history. A completed turn
        appends both halves and clears the park, on approve and on deny alike -
        both are decisions.

        These are synchronous database calls inside an async callback, so they
        block the event loop for their duration. Acceptable here and stated
        rather than hidden: this is a single-user service on loopback, and two
        short writes at the end of a turn that already took seconds of model
        time is not the bottleneck. It would need revisiting before this ever
        serves concurrent users - which cannot happen before the auth gate.
        """
        turn = turn_from_result(result)

        if turn.pending:
            assert turn.resume_state is not None  # guaranteed by TurnResult
            store.save_pending(conversation_id, turn.resume_state)
            return

        for message in turn.new_messages:
            store.append_message(conversation_id, message)
        store.clear_pending(conversation_id)

    return await _SanitizingVercelAIAdapter.dispatch_request(
        request,
        agent=agent,
        sdk_version=SDK_VERSION,
        # No `message_history`: the client owns the wire state. Passing stored
        # history here would concatenate, not override - see the module
        # docstring - and the model would see every turn twice.
        on_complete=on_complete,
    )
