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
from typing import Literal

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)

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
    """One turn of plain text. The only shape any code outside this file's
    cluster ever needs to know about a conversation."""

    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class TurnResult:
    """What running one turn produced.

    `new_messages` holds only this turn's user question and assistant answer -
    append it to your running history before the next `run_turn` call. It does
    NOT include the intermediate tool-call/tool-result messages Pydantic AI
    generated internally; `tool_calls` (names only) is the visibility this
    boundary keeps for those, matching what scripts/ask.py already printed.
    """

    answer: str
    new_messages: list[Message]
    tool_calls: list[str]


def _to_model_history(history: list[Message]) -> list[ModelMessage]:
    """Our Message list -> Pydantic AI's message_history kwarg shape."""

    converted: list[ModelMessage] = []
    for message in history:
        if message.role == "user":
            converted.append(ModelRequest(parts=[UserPromptPart(content=message.content)]))
        else:
            converted.append(ModelResponse(parts=[TextPart(content=message.content)]))
    return converted


async def run_turn(history: list[Message], question: str, *, settings: Settings) -> TurnResult:
    """Run one turn of the conversation.

    `history` is never mutated - the caller decides how and whether to grow
    their own list from `new_messages`. `settings` is explicit rather than a
    module-level import so nothing here reaches for global state.
    """

    agent = Agent(
        build_model(settings),
        instructions=INSTRUCTIONS,
        toolsets=[ErpToolset(settings.mcp_base_url)],
    )

    result = await agent.run(question, message_history=_to_model_history(history))

    tool_calls = [
        part.tool_name
        for message in result.new_messages()
        for part in getattr(message, "parts", [])
        if isinstance(part, ToolCallPart)
    ]

    new_messages = [
        Message(role="user", content=question),
        Message(role="assistant", content=result.output),
    ]

    return TurnResult(answer=result.output, new_messages=new_messages, tool_calls=tool_calls)
