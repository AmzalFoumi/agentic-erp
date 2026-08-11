"""Gate 16's "done": one question, answered by calling the real tools.

This is the first time all three pieces run together - `config.py` for settings,
`model_provider.py` for the model, `mcp_client.py` for the tools - and the first
time either of the latter two opens a connection rather than merely constructing.

**Deliberately throwaway.** The real conversation loop is Gate 17
(`conversation.py`), with our own boundary types and a `lint-imports` contract.
This script is a *harness*: it exists to prove the plumbing carries a turn, and
to answer the one question Gate 16 leaves open - whether the chosen model
actually picks the right tool among all six. Nothing should import it.

**The backend must be running over HTTP.** Two terminals:

    # terminal 1, from backend/ with its venv active
    python -m mcp_server.server --transport streamable-http

    # terminal 2, from agent/ with its venv active
    python scripts/ask.py
    python scripts/ask.py "how many bananas are in stock?"

It prints which tools the model chose before printing the answer, because those
are two separate things that can each be wrong. A fluent reply built from no tool
call at all is the failure this script exists to make visible - the model is
perfectly capable of inventing a plausible stock level, and a printed answer
alone would not tell you it had.
"""

import asyncio
import sys
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.messages import ToolCallPart

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402  (must follow the sys.path line above)
from mcp_client import ErpToolset  # noqa: E402
from model_provider import build_model  # noqa: E402

DEFAULT_QUESTION = "What's low on stock?"

# The system prompt. Short on purpose: the tool descriptions in
# `backend/mcp_server/server.py` already carry the domain detail, and repeating
# it here would create a second copy to keep in sync - the same argument that
# keeps business rules out of both adapters.
#
# The one thing worth stating that no tool docstring can: that inventing an
# answer is worse than admitting a gap. A model with tools still guesses when
# guessing feels helpful.
# The "always call a tool first" sentence is not filler. Gemma is documented as
# reaching for tools less readily than Gemini - without being told to prioritise
# them it falls back on training data and answers in prose. Since Gemma is the
# default model, that instruction is load-bearing rather than decorative.
INSTRUCTIONS = (
    "You answer questions about a supermarket's inventory using the tools "
    "provided. Always call a tool to look up real data before answering - never "
    "answer an inventory question from memory or assumption. Never state a stock "
    "level, price, or product detail you have not read from a tool result; if the "
    "tools cannot answer, say so plainly. Quantities and prices come back as "
    "exact values, so report them as given rather than rounding."
)


async def main() -> None:
    question = " ".join(sys.argv[1:]) or DEFAULT_QUESTION

    print(f"model: {settings.gemini_model}")
    print(f"tools: {settings.mcp_base_url}")
    print(f"  you: {question}")
    print()

    # `toolsets=[...]` hands the toolset to the agent, and the agent enters it -
    # which is why `ErpToolset.__aenter__` builds the client rather than
    # `__init__`. Nothing here calls `async with` on the toolset itself.
    agent = Agent(
        build_model(settings),
        instructions=INSTRUCTIONS,
        toolsets=[ErpToolset(settings.mcp_base_url)],
    )

    result = await agent.run(question)

    # Walk the message history for the tool calls the model actually made. This
    # is the part that matters for Gate 16's open question: no calls means the
    # answer below, however confident, came out of the model's head.
    calls = [
        part
        for message in result.all_messages()
        for part in getattr(message, "parts", [])
        if isinstance(part, ToolCallPart)
    ]

    if calls:
        print(f"=== {len(calls)} tool call(s) ===")
        for call in calls:
            print(f"  {call.tool_name}({call.args})")
    else:
        print("=== no tool calls ===")
        print("  The reply below was not grounded in the database. Treat any")
        print("  specific number in it as invented, and check the tool")
        print("  descriptions in mcp_server/server.py before the model.")
    print()

    print("=== answer ===")
    print(result.output)


asyncio.run(main())
