"""The conversation loop: our own boundary types, one Pydantic AI Agent per turn.

**The isolation rule.** This file, `model_provider.py`, and `mcp_client.py` are the
only three files in agent/ allowed to import `pydantic_ai` or `mcp` — a "runtime
cluster" enforced by agent/pyproject.toml's import-linter contract (Gate 17).
Everything outside this cluster (config.py, scripts/) talks only in `Message` and
`TurnResult`, so a future caller (an HTTP route, a test) never needs to know
Pydantic AI exists.

**Why the caller owns the history instead of this module.** Pydantic AI's own
`agent.run()` is stateless — it takes `message_history` in and gives you
`result.new_messages()` out, and expects YOU to glue them together for the next
call. This mirrors that exactly, with our own `Message` type instead of theirs,
so `store.py` (Gate 18) can save/load a plain list without touching Pydantic AI.
"""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic_ai import (
    Agent,
    DeferredToolRequests,
    DeferredToolResults,
    ToolApproved,
    ToolDenied,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.toolsets import AbstractToolset

from config import Settings
from mcp_client import ErpToolset
from model_provider import build_model

# Short on purpose: the tool descriptions in `backend/mcp_server/server.py`
# already carry the domain detail (see mcp_client.py's docstring on why they
# are passed through whole). The one thing worth stating that no tool
# docstring can: that inventing an answer is worse than admitting a gap.
#
# The "always call a tool first" sentence is load-bearing for Gemma
# specifically — it is documented as reaching for tools less readily than
# Gemini, so without this it falls back to prose from training data.
INSTRUCTIONS = (
    "You answer questions about a supermarket's inventory using the tools "
    "provided. Always call a tool to look up real data before answering - never "
    "answer an inventory question from memory or assumption. Never state a stock "
    "level, price, or product detail you have not read from a tool result; if the "
    "tools cannot answer, say so plainly. Quantities and prices come back as "
    "exact values, so report them as given rather than rounding."
)


@dataclass(frozen=True)
class Message:
    """One turn of plain text, plus whatever provider-opaque bytes came with
    it. The only shape any code outside this file's cluster ever needs to
    know about a conversation.

    provider_data holds a serialized Pydantic AI ModelMessage (e.g. carrying
    Google's function-call signature) when this Message is an assistant
    turn produced by run_turn(); None for user turns and for any assistant
    turn where nothing provider-specific needs preserving. store.py (Gate 18)
    persists these bytes as an opaque bytea column and never parses them -
    only this file (via ModelMessagesTypeAdapter) ever does.
    """

    role: Literal["user", "assistant"]
    content: str
    provider_data: bytes | None = None


@dataclass(frozen=True)
class PendingApproval:
    """One tool call the model wants to make, waiting on a human decision.

    Our own type rather than Pydantic AI's `DeferredToolRequests`, for the same
    reason `Message` is ours rather than `ModelMessage`: Gate 17's contract is
    that a future HTTP route can render an approval prompt without importing
    pydantic_ai.

    `call_id` is Pydantic AI's tool_call_id, passed straight through. Callers
    never construct or interpret one - they echo it back in a decision. It is
    exposed rather than hidden behind a list index because it is what the
    resume path matches on, and inventing a second identifier alongside it
    would create two ways to name the same call.
    """

    tool_name: str
    arguments: dict[str, Any]
    call_id: str


@dataclass(frozen=True)
class TurnResult:
    """What running one turn produced.

    `new_messages` holds only this turn's user question and assistant answer -
    append it to your running history before the next `run_turn` call. It does
    NOT include the intermediate tool-call/tool-result messages Pydantic AI
    generated internally; `tool_calls` (names only) is the visibility this
    boundary keeps for those, matching what scripts/ask.py already printed.

    **Two shapes, one type (Gate 19).** A turn either finished or stopped for
    approval, and `pending` is how you tell: empty means finished and `answer`
    is set; non-empty means stopped, `answer` is None, and `new_messages` is
    empty because a half-finished turn is not conversation history.

    `pending` is a list, not a single value, because one model response can ask
    for several tool calls at once - Gate 15's finding 5, and the reason
    `DeferredToolRequests.approvals` is a list too. A single-value field would
    work until the first parallel batch and then silently drop the rest.

    `resume_state` is the interrupted run's whole message list, serialized.
    Opaque to callers and NOT persisted anywhere: a pending approval currently
    dies with the process, which is acceptable only because nothing but a test
    asks for one yet. Gate 20 puts an HTTP boundary between the pause and the
    decision, and inherits the question of where this lives.
    """

    answer: str | None
    new_messages: list[Message]
    tool_calls: list[str]
    pending: list[PendingApproval]
    resume_state: bytes | None


def _to_model_history(history: list[Message]) -> list[ModelMessage]:
    """Our Message list -> Pydantic AI's message_history kwarg shape.

    An assistant Message with provider_data set is rebuilt from those exact
    bytes via ModelMessagesTypeAdapter, rather than a fresh plain-text
    ModelResponse - this is what carries the model's own reasoning/signature
    data across a reload, instead of losing it the moment a conversation is
    read back from the database.
    """

    converted: list[ModelMessage] = []
    for message in history:
        if message.role == "user":
            converted.append(ModelRequest(parts=[UserPromptPart(content=message.content)]))
        elif message.provider_data is not None:
            converted.extend(ModelMessagesTypeAdapter.validate_json(message.provider_data))
        else:
            converted.append(ModelResponse(parts=[TextPart(content=message.content)]))
    return converted


def _build_agent(
    settings: Settings,
    model: Model | None,
    toolset: AbstractToolset[Any] | None,
) -> Agent[None, Any]:
    """The Agent both public functions run on.

    **`output_type=[str, DeferredToolRequests]` is not optional.** Without
    DeferredToolRequests in the output type, a call to a tool marked
    kind="unapproved" never surfaces as an approval request at all - stated as
    one of two key rules in pydantic_ai's own bundled guidance
    (.agents/skills/building-pydantic-ai-agents/references/TOOLS-ADVANCED.md).
    So `result.output` is now `str | DeferredToolRequests`, which is why the
    callers below branch on its type.

    `model` and `toolset` default to the real ones and exist so tests can
    substitute a FunctionModel and a fake toolset - the whole suite runs with
    no network. Explicit parameters rather than monkeypatching a private
    factory, matching how `settings` is already a parameter here "so nothing
    here reaches for global state", and how backend/ passes `Actor` rather than
    reading ambient request state.
    """

    return Agent(
        model or build_model(settings),
        instructions=INSTRUCTIONS,
        toolsets=[toolset or ErpToolset(settings.mcp_base_url)],
        output_type=[str, DeferredToolRequests],
    )


def _tool_call_names(messages: list[ModelMessage]) -> list[str]:
    """Every tool the model asked for, in order.

    Includes calls that were gated and never executed - the model did ask for
    them, and scripts/ask.py prints this list to show what the model reached
    for. "Asked for" and "ran" are different questions; the second one is
    answered by whether the turn paused.
    """

    return [
        part.tool_name
        for message in messages
        for part in getattr(message, "parts", [])
        if isinstance(part, ToolCallPart)
    ]


def _paused(result: Any, requests: DeferredToolRequests) -> TurnResult:
    """Translate Pydantic AI's approval request into our own boundary type.

    `resume_state` is the run's ENTIRE message list, not just its last message
    the way `Message.provider_data` is. That difference is the one place Gate
    18's design does not carry over: a decision is matched back to its call by
    tool_call_id, which lives on a ToolCallPart in a middle message of the run.
    Serializing only the last message would drop the id and the resume would
    have nothing to match.
    """

    return TurnResult(
        answer=None,
        new_messages=[],
        tool_calls=_tool_call_names(result.new_messages()),
        pending=[
            PendingApproval(
                tool_name=call.tool_name,
                arguments=call.args_as_dict(),
                call_id=call.tool_call_id,
            )
            for call in requests.approvals
        ],
        resume_state=ModelMessagesTypeAdapter.dump_json(result.all_messages()),
    )


def _completed(result: Any, question: str) -> TurnResult:
    """Build the finished-turn result, including what store.py will persist."""

    # The last of Pydantic AI's own new_messages() is the final ModelResponse
    # carrying the answer - serializing just that one message (not the whole
    # turn, which also includes intermediate tool-call/tool-result messages)
    # keeps provider_data minimal: enough to rebuild this one assistant turn
    # on reload, no more.
    provider_data = ModelMessagesTypeAdapter.dump_json([result.new_messages()[-1]])

    return TurnResult(
        answer=result.output,
        new_messages=[
            Message(role="user", content=question),
            Message(role="assistant", content=result.output, provider_data=provider_data),
        ],
        tool_calls=_tool_call_names(result.new_messages()),
        pending=[],
        resume_state=None,
    )


async def run_turn(
    history: list[Message],
    question: str,
    *,
    settings: Settings,
    model: Model | None = None,
    toolset: AbstractToolset[Any] | None = None,
) -> TurnResult:
    """Run one turn of the conversation, stopping if approval is needed.

    `history` is never mutated - the caller decides how and whether to grow
    their own list from `new_messages`. `settings` is explicit rather than a
    module-level import so nothing here reaches for global state.

    Returns either a finished turn or a paused one; see TurnResult. A paused
    turn is continued with `resume_turn`, and there is no timeout on that -
    a pending approval waits until the caller decides or the process ends.
    """

    agent = _build_agent(settings, model, toolset)

    result = await agent.run(question, message_history=_to_model_history(history))

    if isinstance(result.output, DeferredToolRequests):
        return _paused(result, result.output)

    return _completed(result, question)


# What the model is told when a human refuses a tool call. Written here rather
# than taken from the caller: the caller supplies a decision, not the wording -
# one place to change the phrasing, and no way for a caller to accidentally
# tell the model something misleading about why it was stopped.
DENIAL_MESSAGE = "A human reviewed this and did not approve it."


def _pending_call_ids(messages: list[ModelMessage]) -> set[str]:
    """The tool_call_ids in `messages` that are still waiting on a decision.

    **A call is pending if nothing answered it yet** - no ToolReturnPart (it
    ran) and no RetryPromptPart (it was rejected and the model was asked to try
    again). That is the definition rather than a flag on the call itself: there
    is no "unapproved" marker on a serialized ToolCallPart to read. `tool_kind`
    looks like it would serve, but it is a discriminator for typed subclasses
    like 'tool-search' and is None for every ordinary tool call, resolved or
    not - checked against pydantic_ai 2.24.0 rather than assumed.

    Derived from `resume_state` rather than carried alongside it, so resume_turn
    needs only those bytes and cannot be handed a decision map built against a
    different run.
    """

    called: set[str] = set()
    answered: set[str] = set()

    for message in messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolCallPart):
                called.add(part.tool_call_id)
            elif isinstance(part, (ToolReturnPart, RetryPromptPart)):
                if part.tool_call_id is not None:
                    answered.add(part.tool_call_id)

    return called - answered


def _original_question(messages: list[ModelMessage]) -> str:
    """The user question that started the interrupted turn.

    Needed because `_completed` writes the user half of `new_messages`, and on
    a resume the question came in one process-lifetime earlier. Taken from the
    LAST UserPromptPart in the run rather than the first: `messages` holds the
    prior conversation as well as this turn, and the most recent user prompt is
    this turn's.
    """

    for message in reversed(messages):
        for part in getattr(message, "parts", []):
            if isinstance(part, UserPromptPart):
                return part.content if isinstance(part.content, str) else str(part.content)
    return ""


async def resume_turn(
    history: list[Message],
    resume_state: bytes,
    decisions: dict[str, bool],
    *,
    settings: Settings,
    model: Model | None = None,
    toolset: AbstractToolset[Any] | None = None,
) -> TurnResult:
    """Finish a turn that stopped for approval.

    `resume_state` comes from the paused TurnResult; `decisions` maps each
    PendingApproval's `call_id` to True (approve) or False (deny).

    **`decisions` is dict[str, bool] rather than our own enum** because the
    decision is genuinely two-state, and the wording a denied model sees is
    ours (DENIAL_MESSAGE above), not the caller's to supply.

    Returns a completed TurnResult - `answer` set, `new_messages` holding the
    user question and the assistant reply - so the caller's persistence path is
    identical to a turn that never paused.
    """

    messages = ModelMessagesTypeAdapter.validate_json(resume_state)
    pending = _pending_call_ids(messages)

    # Both checks run before the model is called, so a caller mistake costs
    # nothing and names itself, rather than surfacing as a stuck run.
    if unknown := set(decisions) - pending:
        raise ValueError(
            f"These tool call ids are not pending approval in this turn: "
            f"{sorted(unknown)}. Pending: {sorted(pending)}."
        )
    if unanswered := pending - set(decisions):
        raise ValueError(
            f"These tool calls have no decision: {sorted(unanswered)}. Every "
            f"pending call must be approved or denied - one model response can "
            f"request several at once, and a half-answered batch leaves the "
            f"turn unable to continue."
        )

    results = DeferredToolResults(
        approvals={
            call_id: ToolApproved() if approved else ToolDenied(DENIAL_MESSAGE)
            for call_id, approved in decisions.items()
        }
    )

    agent = _build_agent(settings, model, toolset)

    # `None` as the prompt, not a filler string: the interrupted turn's user
    # question is already inside `messages`, and Agent.run's signature accepts
    # `user_prompt: str | Sequence[UserContent] | None = None`, so "no new user
    # message" is a supported state rather than something to fake. pydantic_ai's
    # own example passes 'Continue'; None says the same thing without adding a
    # turn the person never typed.
    result = await agent.run(None, message_history=messages, deferred_tool_results=results)

    if isinstance(result.output, DeferredToolRequests):
        # The model asked for another gated tool after the first was resolved.
        # Pausing again is correct - the caller loops - and this is why
        # `pending` is a list rather than a bool.
        return _paused(result, result.output)

    return _completed(result, _original_question(messages))
