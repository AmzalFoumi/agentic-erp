# Gate 17 — Conversation Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the throwaway one-shot `scripts/ask.py` with a real conversation loop (`conversation.py`) that carries context across turns using our own boundary types, and make the isolation rule ("only conversation.py speaks Pydantic AI") mechanically enforced via `lint-imports`.

**Architecture:** `conversation.py` exposes one function, `run_turn(history, question) -> TurnResult`, built on our own `Message`/`TurnResult` dataclasses. The caller (the rewritten `ask.py` for now, an HTTP route from Gate 20) owns the growing `list[Message]` and passes the whole thing back in on every call — the same pattern Pydantic AI itself uses internally (`agent.run(message_history=...)`), just with our own types so nothing downstream needs to know Pydantic AI exists. `conversation.py`, `model_provider.py`, and `mcp_client.py` form one "runtime cluster" that is allowed to import `pydantic_ai`/`mcp`; everything else (`config.py`, `scripts/`) is not, and that boundary is checked by `import-linter`, mirroring `backend/pyproject.toml`'s existing contract.

**Tech Stack:** Python 3, `pydantic_ai` (already a dependency), `import-linter` (new dev dependency for `agent/`, mirroring the backend's).

## Global Constraints

- **`services`-style boundary for `agent/`:** only `conversation.py`, `model_provider.py`, `mcp_client.py` may import `pydantic_ai` or `mcp`. Verified copied from `docs/AGENT-PLAN.md`'s Gate 17 section (design agreed 2026-08-11).
- **The developer runs every command that touches the toolchain** — `pip install`, `python scripts/...`, `lint-imports`. The agent writes code and states exactly what command to run and what output to expect; it does not run agent/'s venv itself. (Working agreement, `CLAUDE.md`.)
- **No new persistence, no HTTP, no approval gating in this gate.** History lives only in the caller's in-memory list for the duration of one script run. (`docs/AGENT-PLAN.md`, Gate 17, "Not in this gate".)
- **Money/DB/services/core are untouched** — this gate never leaves `agent/`.

---

### Task 1: `conversation.py` — boundary types and `run_turn`

**Files:**
- Create: `agent/conversation.py`
- Modify: `agent/scripts/ask.py` (rewritten to loop questions through `run_turn`, replacing its current single-shot `Agent(...).run()` call)

**Interfaces:**
- Consumes: `settings` from `agent/config.py` (`config.Settings`, specifically `.gemini_model`/`.mcp_base_url` indirectly via the two functions below); `build_model(settings) -> pydantic_ai.models.Model` from `agent/model_provider.py`; `ErpToolset(base_url: str)` from `agent/mcp_client.py`, an `AbstractToolset` that must be entered as an async context manager (`async with ErpToolset(url) as toolset:`) before use.
- Produces (for later gates and for `ask.py`):
  - `Message` — `@dataclass(frozen=True)` with `role: Literal["user", "assistant"]` and `content: str`.
  - `TurnResult` — `@dataclass(frozen=True)` with `answer: str`, `new_messages: list[Message]`, `tool_calls: list[str]` (tool names only, in call order).
  - `async def run_turn(history: list[Message], question: str, *, settings: Settings) -> TurnResult` — the one public function. `settings` is keyword-only and explicit (not read from a module-global `config.settings`) so a test or a future caller can pass a different `Settings` without monkeypatching a module.

**Design notes for the implementer:**

- `agent.run()` wants Pydantic AI's own message history format (a list of `ModelRequest`/`ModelResponse` objects, from `pydantic_ai.messages`), not our `Message` list. `run_turn` must convert:
  - **Our `Message` list → Pydantic AI's `message_history` kwarg.** Build this by running the agent with an *empty* history and then, for any *prior* turns, reconstructing `ModelRequest(parts=[UserPromptPart(content=...)])` for `role == "user"` and `ModelResponse(parts=[TextPart(content=...)])` for `role == "assistant"`. Import both from `pydantic_ai.messages`.
  - **Pydantic AI's result → our `TurnResult`.** After `result = await agent.run(question, message_history=converted_history)`:
    - `answer = result.output`
    - `tool_calls = [part.tool_name for message in result.new_messages() for part in getattr(message, "parts", []) if isinstance(part, ToolCallPart)]` (same walk `ask.py` already does today — copy it here, not there).
    - `new_messages`: convert `result.new_messages()` (the messages *this turn* added, not the whole history) back into our `Message` type — one `Message(role="user", content=question)` plus one `Message(role="assistant", content=result.output)`. Do **not** try to round-trip every intermediate tool-call message into a `Message` — our type only distinguishes user/assistant text, and tool call/response detail is not something any consumer needs yet (that's what `tool_calls` is for). This is a deliberate simplification: the full Pydantic AI message objects are richer than our boundary type, and Gate 17 does not need that richness to survive the round-trip, only the text and who-said-it.
  - The `Agent` is constructed fresh inside `run_turn` on every call (same `Agent(build_model(settings), instructions=INSTRUCTIONS, toolsets=[ErpToolset(settings.mcp_base_url)])` shape `ask.py` uses today), and `ErpToolset` must be entered via `async with` around the `agent.run()` call, since `ask.py` currently relies on `Agent` entering the toolset itself when you pass `toolsets=[...]` — keep that same mechanism (do not manually call `__aenter__`).
  - Move the `INSTRUCTIONS` constant from `ask.py` into `conversation.py` — it is behavior of the agent, not of the demo script.

- [ ] **Step 1: Write `agent/conversation.py`**

```python
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
```

- [ ] **Step 2: Rewrite `agent/scripts/ask.py` to loop through `run_turn`**

Replace the whole file with:

```python
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

DEFAULT_QUESTIONS = ["What's low on stock?"]


async def _ask(history: list[Message], question: str) -> list[Message]:
    print(f"  you: {question}")
    result = await run_turn(history, question, settings=settings)

    if result.tool_calls:
        print(f"  === {len(result.tool_calls)} tool call(s): {', '.join(result.tool_calls)} ===")
    else:
        print("  === no tool calls - treat any number in the answer below as invented ===")

    print(f"agent: {result.answer}")
    print()

    return history + result.new_messages


async def main() -> None:
    questions = sys.argv[1:] or DEFAULT_QUESTIONS

    print(f"model: {settings.gemini_model}")
    print(f"tools: {settings.mcp_base_url}")
    print()

    history: list[Message] = []
    for question in questions:
        history = await _ask(history, question)


asyncio.run(main())
```

- [ ] **Step 3: Ask the developer to run it and confirm context carries over**

Tell the developer (do not run this yourself — `agent/`'s venv is theirs to drive):

> With the backend running over HTTP in one terminal (`python -m mcp_server.server --transport streamable-http` from `backend/`), run from `agent/` with its venv active:
>
> ```
> python scripts/ask.py "What's low on stock?" "What is the SKU of the first one you listed?"
> ```
>
> Expected: the first answer lists low-stock products by name; the second answer names a specific SKU that matches one of the products from the first answer (not "I don't know which product you mean" and not a SKU invented from nowhere). If the second answer asks you to clarify which product, or the SKU it gives doesn't match anything in the first list, that means `history` isn't actually reaching the model — check that `_to_model_history` is being passed to `agent.run()` and that `ask.py` is reassigning `history = await _ask(...)` (not discarding the return value).

- [ ] **Step 4: Commit**

```bash
git add agent/conversation.py agent/scripts/ask.py
git commit -m "$(cat <<'EOF'
feat(agent): Gate 17 - conversation.py carries context across turns

run_turn(history, question) replaces the one-shot Agent.run() in ask.py, using
our own Message/TurnResult dataclasses so nothing outside conversation.py,
model_provider.py, and mcp_client.py needs to know Pydantic AI exists. History
is owned by the caller, mirroring how agent.run(message_history=...) already
works underneath.
EOF
)"
```

---

### Task 2: `agent/pyproject.toml` — make the isolation rule mechanical

**Files:**
- Create: `agent/pyproject.toml`
- Create: `agent/scripts/__init__.py` (empty — see note below)
- Modify: `agent/model_provider.py:10-17` (fix a docstring inaccuracy found while writing this contract — see Step 1)

**Interfaces:**
- Consumes: nothing from Task 1's code; reads the finished file layout (`config.py`, `conversation.py`, `model_provider.py`, `mcp_client.py`, `scripts/ask.py`, `scripts/check_mcp.py`) to know what to list.
- Produces: a `lint-imports`-checkable contract. No Python symbols — this task's deliverable is config plus one doc fix.

**Design notes for the implementer:**

- `import-linter` needs modules to be importable/discoverable as packages. `agent/`'s `.py` files are flat modules (no top-level `agent` package — everything does `from config import settings`, relying on `sys.path` tricks), same as the backend. `agent/scripts/` currently has no `__init__.py`, so it is only an implicit namespace package; add an empty `agent/scripts/__init__.py` so `import-linter` can resolve `scripts.ask` and `scripts.check_mcp` as real submodules of a real package `scripts`.
- **The actual contract, and why it's narrower than one line in `model_provider.py` currently claims.** While writing this contract you will find that `model_provider.py`'s docstring (lines 10-17) says: *"the enforced `lint-imports` contract (Gate 17) forbids `pydantic_ai` in store.py/app.py/mcp_client.py, not here."* This is wrong about `mcp_client.py`: `mcp_client.py` already imports `pydantic_ai` (`ModelRetry`, `RunContext`, `ToolDefinition`, `AbstractToolset`, `ToolsetTool`) because `ErpToolset` directly implements Pydantic AI's `AbstractToolset` protocol — it cannot not import it. `mcp_client.py` is part of the same allowed cluster as `conversation.py` and `model_provider.py`, not one of the forbidden files. Fix that sentence as part of this task (Step 1 below) before writing the contract, so the code comment and the enforced contract agree.
- The forbidden set is **`config.py` and everything under `scripts/`** — those must never import `pydantic_ai`. Do **not** also forbid `mcp` in `scripts/`: `check_mcp.py` deliberately imports `mcp.client.Client` directly, on purpose, as a diagnostic that bypasses the agent runtime entirely (its own docstring: *"connects to the backend's MCP server... with no Gemini, no Pydantic AI, and no agent code in the path"*) — forbidding `mcp` there would break a script that is correct as written.
- `store.py` and `app.py` don't exist yet (Gates 18/20) — don't add them to `source_modules` now; a rule naming a module that isn't on disk makes `lint-imports` fail to start, exactly the trap `backend/pyproject.toml`'s comment on `root_packages` already warns about. Add them to this contract in the gate that creates them.

- [ ] **Step 1: Fix `model_provider.py`'s docstring**

In `agent/model_provider.py`, replace:

```
the enforced
`lint-imports` contract (Gate 17) forbids `pydantic_ai` in store.py/app.py/
mcp_client.py, not here.
```

with:

```
the enforced
`lint-imports` contract (Gate 17) forbids `pydantic_ai` in config.py and
scripts/, not here. `mcp_client.py` is grouped in the same allowed cluster -
it implements Pydantic AI's `AbstractToolset` directly and cannot avoid the
import.
```

- [ ] **Step 2: Create `agent/scripts/__init__.py`**

Empty file (0 bytes) — just makes `scripts` a real package so `import-linter` can see `scripts.ask` and `scripts.check_mcp`.

- [ ] **Step 3: Write `agent/pyproject.toml`**

```toml
# Tool configuration for the agent service. Mirrors backend/pyproject.toml's
# import-linter section - same tool, same reasoning, a narrower boundary.
#
# No [project] table, same as the backend: dependencies stay in
# requirements.txt; this file is config only.

[tool.importlinter]
# Every top-level module gets listed, same as backend/pyproject.toml's
# root_packages comment explains: a module not named here is invisible to
# the graph, and a rule naming one that is also not on disk makes
# lint-imports fail to start rather than skip it. store.py and app.py
# (Gates 18, 20) get added here when they exist, not before.
root_packages = ["config", "conversation", "model_provider", "mcp_client", "scripts"]

# Needed for the forbidden-modules contract below to see pydantic_ai at all -
# by default the graph contains only our own code.
include_external_packages = true

[[tool.importlinter.contracts]]
name = "Only the runtime cluster speaks Pydantic AI"
type = "forbidden"
# conversation.py, model_provider.py, and mcp_client.py are the allowed
# cluster (see conversation.py's module docstring) and are deliberately
# absent from source_modules below. config.py and scripts/ are the two
# places that must stay ignorant of Pydantic AI - config.py because it is
# read by every future caller (a store, an HTTP route) that should never
# need pydantic_ai on its import path to load settings; scripts/ because
# ask.py talking to conversation.py in plain Message/TurnResult terms is
# the whole point of Gate 17.
source_modules = ["config", "scripts"]
forbidden_modules = ["pydantic_ai"]
```

- [ ] **Step 4: Ask the developer to install `import-linter` and run it**

Tell the developer:

> `import-linter` isn't in `agent/requirements.txt` yet (the backend already depends on it the same way). From `agent/` with its venv active:
>
> ```
> pip install import-linter
> pip freeze > requirements.txt
> lint-imports
> ```
>
> Expected: `Contracts: 1 kept, 0 broken.` If it reports the contract broken, it will name the file and the forbidden import — that means either `scripts/ask.py` still imports `pydantic_ai` directly (Task 1, Step 2 wasn't picked up) or `config.py` gained an import it shouldn't have.

- [ ] **Step 5: Commit**

```bash
git add agent/pyproject.toml agent/scripts/__init__.py agent/model_provider.py agent/requirements.txt
git commit -m "$(cat <<'EOF'
feat(agent): Gate 17 - lint-imports contract for the pydantic_ai boundary

Mirrors backend/pyproject.toml's import-linter setup. config.py and scripts/
are forbidden from importing pydantic_ai; conversation.py, model_provider.py,
and mcp_client.py are the allowed runtime cluster. Also fixes a stale claim in
model_provider.py's docstring that mcp_client.py was one of the forbidden
files - it isn't, and can't be, since it implements AbstractToolset directly.
EOF
)"
```

---

## Self-Review

**Spec coverage:** `conversation.py` with our dataclasses (Task 1) ✓; `agent/pyproject.toml` with its `lint-imports` contract (Task 2) ✓; "done looks like: `lint-imports` kept + conversation.py is the file that would break if pydantic_ai vanished" — covered by Task 2 Step 4's verification, with the caveat (now stated explicitly in the contract's comments) that `model_provider.py`/`mcp_client.py` share that exposure by design, which is truer to the actual architecture than the plan-doc's one-line summary. "Not in this gate: database or network beyond MCP" — nothing in either task touches either.

**Placeholder scan:** no TBD/TODO; every step has complete, copy-pasteable code or an exact command with expected output.

**Type consistency:** `Message(role, content)` and `TurnResult(answer, new_messages, tool_calls)` are defined once in Task 1 and used identically in `ask.py`'s rewrite in the same task; Task 2 introduces no new Python symbols, only config.
