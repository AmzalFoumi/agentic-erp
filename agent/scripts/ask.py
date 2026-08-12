"""Gate 17's demo: a real conversation, not a one-shot question.

Proves `conversation.py`'s `run_turn` carries context across turns - ask a
follow-up that only makes sense given the previous answer, and the model
should get it right. Compare Gate 16's `ask.py`, which asked exactly one
question and exited; this loops, holding the growing `history` list itself,
because `run_turn` never keeps it.

**The backend must be running over HTTP** (see check_mcp.py's docstring for
the exact command). Two ways to run this:

    python scripts/ask.py
        # interactive: type a question, see the answer, type a follow-up,
        # Ctrl+C or an empty line to stop.

    python scripts/ask.py "What's low on stock?" "What's the price of the first one?"
        # non-interactive: each argument is one turn, run in order. This is
        # the form to paste output from when demonstrating the gate.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402  (must follow the sys.path line above)
from conversation import Message, run_turn  # noqa: E402


async def _ask(history: list[Message], question: str, *, echo: bool = True) -> list[Message]:
    if echo:
        print(f"  you: {question}")
    result = await run_turn(history, question, settings=settings)

    if result.tool_calls:
        print(f"  === {len(result.tool_calls)} tool call(s): {', '.join(result.tool_calls)} ===")
    else:
        print("  === no tool calls - treat any number in the answer below as invented ===")

    # Gate 19: a turn that asks to change data stops here instead of answering.
    # This script deliberately cannot approve - approve/deny is exercised by
    # agent/tests/test_approval.py, and the real thing gets a UI at Gate 21.
    # Printing the pending calls rather than `answer` (which is None) keeps the
    # script's output honest about what happened.
    if result.pending:
        print("  === stopped for approval - this script cannot approve ===")
        for approval in result.pending:
            print(f"      {approval.tool_name}({approval.arguments})")
        print()
        # new_messages is empty on a paused turn, so history does not grow -
        # the question was asked but the turn never completed.
        return history

    print(f"agent: {result.answer}")
    print()

    return history + result.new_messages


async def main() -> None:
    questions = sys.argv[1:]

    print(f"model: {settings.gemini_model}")
    print(f"tools: {settings.mcp_base_url}")
    print()

    history: list[Message] = []

    if questions:
        for question in questions:
            history = await _ask(history, question)
        return

    while True:
        try:
            question = input("  you: ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not question:
            break

        history = await _ask(history, question, echo=False)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # asyncio.run() intercepts Ctrl+C before main()'s own try/except gets
        # a chance to - it cancels the running task and re-raises here, one
        # level up. Catching it at this outer level is what turns that into
        # a clean exit instead of a CancelledError/KeyboardInterrupt
        # traceback.
        print()
