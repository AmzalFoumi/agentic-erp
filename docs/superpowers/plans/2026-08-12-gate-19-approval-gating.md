# Gate 19 — Approval Gating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** the agent stops before running any tool that changes data, and resumes correctly when a human approves or denies — proven by deterministic tests with no network and no live model.

**Architecture:** `agent/mcp_client.py` marks every non-read-only MCP tool `kind="unapproved"` on its `ToolDefinition`, which is how Pydantic AI's own `requires_approval=True` is implemented one layer down. `agent/conversation.py` gains `output_type=[str, DeferredToolRequests]`, translates Pydantic AI's `DeferredToolRequests` into our own `PendingApproval` type at the boundary, and gains a second public function `resume_turn()` that takes a decision map back. Nothing outside the three-file runtime cluster ever sees a Pydantic AI type.

**Tech Stack:** Python 3.12, `pydantic-ai-slim[google]==2.24.0`, `mcp==2.0.0`, `pytest==9.1.1`, `pytest-asyncio==1.4.0`, `import-linter==2.13`.

## Global Constraints

- **The spec is the requirements.** Read `docs/superpowers/specs/2026-08-12-gate-19-approval-gating-design.md` before starting. Where this plan and the spec disagree, the spec wins.
- **The developer runs every command that touches the toolchain or git.** No step in this plan may be executed by an agent: not `pip install`, not `pytest`, not `lint-imports`, not `git add`/`commit`. Write the command, say what output to expect, and hand off. This is `docs/PLAN.md`'s working agreement and it overrides the executing skill's defaults.
- **No agent-run commits.** There is exactly one commit handoff, at the end of the plan, in Task 5.
- `READ_ONLY = frozenset({"list_products", "get_product", "get_product_by_sku"})` — exactly these three names, verbatim.
- Denial message shown to the model: `"A human reviewed this and did not approve it."` — verbatim.
- `pytest==9.1.1` (same pin as `backend/requirements.txt`), `pytest-asyncio==1.4.0`. Both verified live against PyPI on 2026-08-12.
- `asyncio_mode = "auto"` in `agent/pyproject.toml`, so no test needs its own marker.
- **Not in this gate:** persisting `resume_state` (deferred to Gate 20, confirmed by the developer 2026-08-12), any UI, any live-model demo.
- Every new file and every non-obvious line gets a comment explaining *why*, matching the density of the existing `agent/` files. This codebase's comments carry the reasoning; terse code that matches the linter but not the house style will be rejected at review.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `agent/mcp_client.py` | Modify | Add `READ_ONLY`, `tool_kind()`, and wire `kind=` into `get_tools()`. The one place a tool is declared to the model, so the one place gating is decided. |
| `agent/conversation.py` | Modify | Add `PendingApproval`; extend `TurnResult`; add `output_type` and the `model`/`toolset` seams; add `resume_turn()`. Still the only file callers import. |
| `agent/scripts/ask.py` | Modify | Print pending approvals instead of `agent: None`. |
| `agent/tests/__init__.py` | Create | Makes `agent.tests` a package so `lint-imports` can name it. |
| `agent/tests/conftest.py` | Create | `sys.path` fix + shared `Settings`/fake-model helpers. |
| `agent/tests/test_tool_gating.py` | Create | Unit tests for the fail-closed rule. |
| `agent/tests/test_approval.py` | Create | Turn-level tests: pause, approve, deny. |
| `agent/requirements.txt` | Modify | `pytest`, `pytest-asyncio`. |
| `agent/pyproject.toml` | Modify | pytest config + `agent.tests` in the import-linter contract. |
| `docs/PLAN.md`, `docs/AGENT-PLAN.md` | Modify | Gate close-out, plus the `requires_approval=True` correction. |

---

## Task 1: Test infrastructure and the fail-closed gating rule

Test infrastructure is folded in here rather than being its own task: `agent/` has never had tests, and this task's deliverable cannot be verified without them.

**Files:**
- Modify: `agent/requirements.txt` (append at end)
- Modify: `agent/pyproject.toml` (append pytest section; edit the import-linter contract)
- Create: `agent/tests/__init__.py`
- Create: `agent/tests/conftest.py`
- Modify: `agent/mcp_client.py` (add `READ_ONLY` + `tool_kind()` after `_ARGS_VALIDATOR`; add `kind=` inside `get_tools()`)
- Create: `agent/tests/test_tool_gating.py`

**Interfaces:**
- Produces: `agent.mcp_client.READ_ONLY: frozenset[str]` and `agent.mcp_client.tool_kind(name: str) -> Literal["function", "unapproved"]`. Task 2's fake toolset imports `tool_kind`.

- [ ] **Step 1: Add the test dependencies**

Append to `agent/requirements.txt`:

```
# pytest runs the agent's own test suite (Gate 19 — the first tests in agent/).
# Same pin as backend/requirements.txt: one library, two services, no reason
# for them to drift.
pytest==9.1.1

# run_turn is async, so pytest needs a plugin to await a test function at all.
# backend/'s suite never needed this because its services are synchronous.
# asyncio_mode="auto" in pyproject.toml means no test carries its own marker.
pytest-asyncio==1.4.0
```

- [ ] **Step 2: Developer installs them**

Ask the developer to run, from `agent/` with `.venv` activated:

```bash
pip install -r requirements.txt
```

Expect: `Successfully installed pytest-9.1.1 pytest-asyncio-1.4.0` (plus `pluggy`/`iniconfig` if not already present). Everything else reports "already satisfied". If `pytest-asyncio` refuses to install, check the Python version — it requires `>=3.10`.

- [ ] **Step 3: Configure pytest and update the import-linter contract**

Append to `agent/pyproject.toml`:

```toml
[tool.pytest.ini_options]
# Gate 19 added the first tests in agent/. testpaths keeps a bare `pytest`
# from walking .venv/ and alembic/versions/.
testpaths = ["tests"]

# Every test in this suite is async, because run_turn is. "auto" means a test
# function defined with `async def` is awaited without needing its own
# @pytest.mark.asyncio - the marker would be on literally every test, which
# makes it noise rather than information.
asyncio_mode = "auto"
```

Then edit the existing contract's `source_modules` line. It currently reads:

```toml
source_modules = ["agent.config", "agent.scripts"]
```

Leave that line exactly as it is, and add this comment immediately above it:

```toml
# **Gate 19: agent.tests is deliberately NOT listed here**, i.e. it is allowed
# to import pydantic_ai. The tests fake the framework - FunctionModel stands in
# for Gemini, and a fake AbstractToolset stands in for the MCP connection - so a
# test that could not name pydantic_ai could not fake it either. This does not
# weaken the contract: its actual purpose is that a future HTTP route can load
# settings and run a turn without pydantic_ai on its import path, and
# agent.config and agent.scripts, the two modules that carry that property,
# stay forbidden below.
```

- [ ] **Step 4: Create the test package and its conftest**

Create `agent/tests/__init__.py`:

```python
"""The agent service's own tests, added at Gate 19.

This file exists for the same reason agent/__init__.py does: import-linter
2.13 only accepts packages (directories with __init__.py) in root_packages,
so `agent.tests` has to be a real package for the Gate 17 contract in
agent/pyproject.toml to be able to name it at all.
"""
```

Create `agent/tests/conftest.py`:

```python
"""Shared test setup: the import path, and the two fakes every test needs.

**The sys.path line is load-bearing and must come before any agent import.**
agent/ modules are flat and import each other bare (`from config import
settings`), which works for scripts/ because scripts/ask.py inserts agent/ on
sys.path first. Tests need the identical fix, and they need it more urgently:
agent/__init__.py exists (added at Gate 17 for import-linter), so without this
line pytest resolves these tests as `agent.tests.test_approval` from the repo
root, and then `from config import ...` inside conversation.py fails with
ModuleNotFoundError. conftest.py is imported before any test module, which is
what makes this the right place for it.
"""

import sys
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Settings  # noqa: E402  (must follow the sys.path line above)


@pytest.fixture
def settings() -> Settings:
    """A Settings object built in the test, not read from agent/.env.

    Both fields are required by config.py and both are unused by these tests -
    the model and the toolset are injected directly, so nothing here ever
    builds a real GoogleModel or opens a real database connection. Constructing
    our own instance rather than importing config.settings keeps a test from
    depending on which model the developer happens to have configured.

    Note that importing config at all still requires a valid agent/.env,
    because config.py creates a module-level `settings = Settings()` at import
    time. That is a pre-existing property of the module, not something Gate 19
    introduced.
    """
    return Settings(
        gemini_api_key="test-key-not-used",
        database_url="postgresql+psycopg://unused/unused",
    )


def scripted_model(*responses: ModelResponse) -> FunctionModel:
    """A FunctionModel that returns the given responses in order, once each.

    This is how a test decides what the model "thinks" - no network, no Gemini,
    no nondeterminism. `responses` is consumed across every agent.run() call
    made with this same FunctionModel instance, which is what lets one instance
    script a turn that pauses for approval AND the resumed turn that follows it:
    pass the same object to run_turn and then to resume_turn.
    """

    remaining = list(responses)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if not remaining:
            raise AssertionError(
                "The model was called more times than the test scripted responses "
                "for. Either the agent looped unexpectedly, or the test needs "
                "another ModelResponse."
            )
        return remaining.pop(0)

    return FunctionModel(respond)
```

- [ ] **Step 5: Write the failing gating tests**

Create `agent/tests/test_tool_gating.py`:

```python
"""Which tools need approval - the fail-closed rule, tested directly.

`get_tools()` cannot be called without a live MCP server, so the decision it
makes is extracted into `tool_kind()` and tested here. The turn-level
consequence of that decision - a turn actually pausing - is test_approval.py.
"""

from mcp_client import READ_ONLY, tool_kind


def test_read_tools_are_not_gated() -> None:
    """The three read tools run without approval.

    Gating reads would make the future agent panel unusable and protects
    nothing - see docs/AGENT-PLAN.md's Gate 19 section.
    """
    for name in ("list_products", "get_product", "get_product_by_sku"):
        assert tool_kind(name) == "function", name


def test_mutating_tools_are_gated() -> None:
    """The three tools that change data require approval."""
    for name in ("create_product", "update_product", "adjust_stock"):
        assert tool_kind(name) == "unapproved", name


def test_an_unknown_tool_is_gated() -> None:
    """**The reason the rule is an allowlist of reads, not a denylist of writes.**

    `delete_product` does not exist in backend/mcp_server/server.py today. If
    someone adds it - or any other data-changing tool - it must be gated by
    default, without anyone remembering to come back and edit this file. The
    cost of the allowlist being wrong is one unnecessary approval prompt; the
    cost of a denylist being wrong is a new mutating tool executing with no
    human check and nothing failing to indicate it.
    """
    assert tool_kind("delete_product") == "unapproved"
    assert tool_kind("drop_everything") == "unapproved"


def test_read_only_holds_exactly_the_three_read_tools() -> None:
    """Pins the contents of the allowlist.

    This is the one test that fails if someone widens READ_ONLY, which is the
    only edit that can quietly un-gate a mutating tool.
    """
    assert READ_ONLY == {"list_products", "get_product", "get_product_by_sku"}
```

- [ ] **Step 6: Developer runs the tests to verify they fail**

Ask the developer to run, from `agent/`:

```bash
pytest tests/test_tool_gating.py -v
```

Expect: a collection error, `ImportError: cannot import name 'READ_ONLY' from 'mcp_client'`. If instead every test passes, `mcp_client.py` was edited out of order — check that Step 7 has not already been applied.

- [ ] **Step 7: Add the rule to `mcp_client.py`**

Add to the imports at the top of `agent/mcp_client.py` (`typing` already imports `Any`):

```python
from typing import Any, Literal
```

Insert after the `_ARGS_VALIDATOR` definition, before `normalise_tool_schema`:

```python
# The tools that only read. Everything else - now and in future - requires
# human approval before it runs.
#
# **Why this is an allowlist of reads rather than a denylist of writes.**
# docs/AGENT-PLAN.md's Gate 19 names the three mutating tools, and listing
# those three here would have been the literal reading. It fails in the wrong
# direction: a seventh @mcp.tool() added to backend/mcp_server/server.py would
# default to ungated, execute without approval, and nothing would fail or warn.
# Inverted, a new tool is gated until someone deliberately declares it a read,
# and the worst case is one unnecessary confirmation.
#
# This also supplies the safety property that get_tools()'s existing choice
# needs: it asks tools/list on every run rather than caching, specifically so a
# new backend tool appears without a restart here. A new tool appearing
# automatically is only safe if it is also gated automatically.
READ_ONLY = frozenset({"list_products", "get_product", "get_product_by_sku"})


def tool_kind(name: str) -> Literal["function", "unapproved"]:
    """Whether a tool runs freely or waits for a human.

    **`kind="unapproved"` is how Pydantic AI's own `requires_approval=True`
    works one layer down.** That kwarg belongs to FunctionToolset and the
    @agent.tool decorators, and is not reachable from a hand-written
    AbstractToolset like ours - docs/AGENT-PLAN.md's Gate 19 wording named an
    API surface we do not have. It is not a different mechanism, though:
    pydantic_ai/tools.py:506 sets `kind='unapproved' if self.requires_approval
    else 'function'`, and the run graph reads only tool_def.kind
    (_tool_execution.py:627, result.py:1062). Verified against the installed
    2.24.0 source on 2026-08-12.

    A separate function rather than an inline conditional in get_tools() so the
    rule can be tested without a live MCP server, and so tests/ can gate its
    own fake tools through the same function that gates the real ones.
    """
    return "function" if name in READ_ONLY else "unapproved"
```

Then, inside `get_tools()`, add one line to the `ToolDefinition(...)` construction, immediately after `parameters_json_schema=...`:

```python
                    kind=tool_kind(tool.name),
```

- [ ] **Step 8: Developer runs the tests to verify they pass**

```bash
pytest tests/test_tool_gating.py -v
```

Expect: `4 passed`.

- [ ] **Step 9: Developer verifies the architecture boundary still holds**

From the **repository root** (not `agent/` — `root_packages = ["agent"]` names the `agent/` directory itself as the package, so running from inside it cannot see `agent.*`):

```bash
lint-imports --config agent/pyproject.toml
```

Expect: `Contracts: 1 kept, 0 broken.` A broken contract here means `pydantic_ai` reached `agent.config` or `agent.scripts`, which this task should not have touched.

---

## Task 2: The pause — boundary types and a turn that stops

**Files:**
- Modify: `agent/conversation.py` (imports; add `PendingApproval`; extend `TurnResult`; rewrite `run_turn`)
- Create: `agent/tests/test_approval.py`

**Interfaces:**
- Consumes: `agent.mcp_client.tool_kind` (Task 1) — the test's fake toolset uses it to assign kinds.
- Produces:
  - `PendingApproval(tool_name: str, arguments: dict[str, Any], call_id: str)`, frozen dataclass
  - `TurnResult(answer: str | None, new_messages: list[Message], tool_calls: list[str], pending: list[PendingApproval], resume_state: bytes | None)`, frozen dataclass
  - `async run_turn(history: list[Message], question: str, *, settings: Settings, model: Model | None = None, toolset: AbstractToolset[Any] | None = None) -> TurnResult`

- [ ] **Step 1: Write the failing tests**

Create `agent/tests/test_approval.py`:

```python
"""Gate 19's proof: a turn stops before a data-changing tool runs, and resumes
correctly on both approve and deny.

**No network and no Gemini.** FunctionModel (conftest's `scripted_model`)
decides what the model "says", and RecordingToolset below stands in for the MCP
connection while recording which tools actually executed. Determinism is the
point: a denial cannot be demonstrated against a live model at all, since the
model does not choose whether it is denied.
"""

from typing import Any

import pytest
from pydantic_ai import RunContext, ToolDefinition
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.toolsets import AbstractToolset, ToolsetTool

from conftest import scripted_model
from conversation import Message, PendingApproval, run_turn
# `_ARGS_VALIDATOR` is private to mcp_client, imported here deliberately: the
# fake toolset needs the same "a dict with string keys" validator the real one
# uses, and rebuilding it in the test would be a second copy that could drift.
from mcp_client import _ARGS_VALIDATOR, tool_kind

# The six tools backend/mcp_server/server.py actually exposes. Named here
# rather than fetched, because a test that asked a live server what tools exist
# would not be deterministic.
TOOL_NAMES = (
    "list_products",
    "get_product",
    "get_product_by_sku",
    "create_product",
    "update_product",
    "adjust_stock",
)


class RecordingToolset(AbstractToolset[Any]):
    """A stand-in for ErpToolset that records executions instead of doing them.

    **It gates its tools through mcp_client.tool_kind(), not a copy of the
    rule.** That is what makes these tests evidence about the real gating
    decision rather than about a duplicate of it - if someone widened
    READ_ONLY, these tests would go green and test_tool_gating.py would go red,
    which is the correct division: that file owns the rule, this one owns the
    behaviour built on it.
    """

    def __init__(self) -> None:
        # (tool_name, arguments) for every tool that actually ran. The
        # assertions that matter in this file are about this list: "resumes
        # correctly on approve and deny" is a claim about whether the tool ran,
        # not about whether a string came back.
        self.executed: list[tuple[str, dict[str, Any]]] = []

    @property
    def id(self) -> str | None:
        return "erp"

    async def get_tools(self, ctx: RunContext[Any]) -> dict[str, ToolsetTool[Any]]:
        return {
            name: ToolsetTool(
                toolset=self,
                tool_def=ToolDefinition(
                    name=name,
                    description=f"Fake {name} for tests.",
                    # Deliberately permissive: the real schemas live in
                    # backend/, and this file is testing approval flow, not
                    # argument validation.
                    parameters_json_schema={"type": "object", "properties": {}},
                    kind=tool_kind(name),
                ),
                max_retries=ctx.max_retries,
                args_validator=_ARGS_VALIDATOR,
            )
            for name in TOOL_NAMES
        }

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[Any],
        tool: ToolsetTool[Any],
    ) -> Any:
        self.executed.append((name, tool_args))
        return f"{name} ran with {tool_args}"


async def test_a_read_tool_runs_without_approval(settings) -> None:
    """The control case: nothing about this gate changes a read question.

    Without this test, a bug that gated everything would look identical to a
    passing approval suite.
    """
    model = scripted_model(
        ModelResponse(parts=[ToolCallPart("list_products", {})]),
        ModelResponse(parts=[TextPart("Nine products are low on stock.")]),
    )
    toolset = RecordingToolset()

    result = await run_turn([], "What's low on stock?", settings=settings, model=model, toolset=toolset)

    assert result.answer == "Nine products are low on stock."
    assert result.pending == []
    assert result.resume_state is None
    assert [name for name, _ in toolset.executed] == ["list_products"]
    # A completed turn contributes both halves to history, exactly as before
    # this gate - store.py's contract is unchanged.
    assert [m.role for m in result.new_messages] == ["user", "assistant"]


async def test_a_mutating_tool_pauses_the_turn(settings) -> None:
    """The gate itself: adjust_stock stops before running."""
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
    toolset = RecordingToolset()

    result = await run_turn(
        [], "Set rice stock to 20.", settings=settings, model=model, toolset=toolset
    )

    # The whole point: the tool did NOT run.
    assert toolset.executed == []

    assert result.pending == [
        PendingApproval(
            tool_name="adjust_stock",
            arguments={"sku": "RICE-5KG", "quantity": 20},
            call_id="call-1",
        )
    ]
    # A paused turn has no answer yet. None rather than "" so a caller that
    # forgets to check `pending` prints something obviously wrong instead of
    # something plausibly empty.
    assert result.answer is None
    # A half-finished turn is not conversation history, so nothing is appended
    # until the resume completes it. This is what keeps store.py untouched by
    # this gate.
    assert result.new_messages == []
    assert result.resume_state is not None
```

Note the `from conftest import scripted_model` line: `scripted_model` is a plain helper function in `conftest.py`, not a fixture, so it is imported rather than requested as an argument. `settings` *is* a fixture, so it arrives as a parameter. Both live in `conftest.py` because Task 3's tests need them too.

- [ ] **Step 2: Developer runs the tests to verify they fail**

```bash
pytest tests/test_approval.py -v
```

Expect: a collection error, `ImportError: cannot import name 'PendingApproval' from 'conversation'`.

- [ ] **Step 3: Add the boundary types to `conversation.py`**

Change the imports. `from typing import Literal` becomes:

```python
from typing import Any, Literal
```

Add to the `pydantic_ai` imports:

```python
from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.models import Model
from pydantic_ai.toolsets import AbstractToolset
```

Add `PendingApproval` immediately after the `Message` dataclass:

```python
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
```

Replace the `TurnResult` dataclass entirely:

```python
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
```

- [ ] **Step 4: Rewrite `run_turn`**

Replace the whole of `run_turn` with:

```python
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
```

Note: `ModelMessage` is already imported in this file; no import change is needed for `_tool_call_names`.

- [ ] **Step 5: Developer runs the tests to verify they pass**

```bash
pytest tests/ -v
```

Expect: `6 passed` (4 from `test_tool_gating.py`, 2 from `test_approval.py`).

If `test_a_mutating_tool_pauses_the_turn` fails with `toolset.executed == [("adjust_stock", ...)]` — the tool ran — then `kind=tool_kind(tool.name)` did not reach the `ToolDefinition`. Check `RecordingToolset.get_tools`, not `conversation.py`.

---

## Task 3: The resume — approve and deny

**Files:**
- Modify: `agent/conversation.py` (add `resume_turn` after `run_turn`)
- Modify: `agent/tests/test_approval.py` (append three tests)

**Interfaces:**
- Consumes: `run_turn`, `TurnResult`, `PendingApproval` (Task 2); `RecordingToolset`, `scripted_model` (Task 2's test file and `conftest.py`).
- Produces: `async resume_turn(history: list[Message], resume_state: bytes, decisions: dict[str, bool], *, settings: Settings, model: Model | None = None, toolset: AbstractToolset[Any] | None = None) -> TurnResult`

- [ ] **Step 1: Write the failing tests**

Append to `agent/tests/test_approval.py`. Add `resume_turn` to the `conversation` import line first, so it reads:

```python
from conversation import Message, PendingApproval, resume_turn, run_turn
```

Then append:

```python
async def _pause_on_adjust_stock(settings) -> tuple[Any, RecordingToolset, Any]:
    """Drive a turn to the paused state, and hand back the pieces to resume it.

    The same FunctionModel instance is returned alongside the paused result
    because `scripted_model` consumes its responses across every run made with
    it - so the third scripted response below is what the model says AFTER the
    decision arrives.
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
    toolset = RecordingToolset()
    paused = await run_turn(
        [], "Set rice stock to 20.", settings=settings, model=model, toolset=toolset
    )
    assert paused.resume_state is not None
    return paused, toolset, model


async def test_approving_runs_the_tool(settings) -> None:
    """**Approve: the tool actually executes, with the original arguments.**

    Asserting on `toolset.executed` rather than on the answer string is the
    whole point. A resume that returned nice text without running the tool
    would pass an answer-only assertion and be completely broken.
    """
    paused, toolset, model = await _pause_on_adjust_stock(settings)

    result = await resume_turn(
        [],
        paused.resume_state,
        {"call-1": True},
        settings=settings,
        model=model,
        toolset=toolset,
    )

    assert toolset.executed == [("adjust_stock", {"sku": "RICE-5KG", "quantity": 20})]
    assert result.answer == "Done."
    assert result.pending == []
    assert result.resume_state is None
    # A resumed turn is a completed turn, so store.py persists it exactly like
    # any other - no special case for "this one was approved".
    assert [m.role for m in result.new_messages] == ["user", "assistant"]


async def test_denying_does_not_run_the_tool(settings) -> None:
    """**Deny: the tool never executes, and the turn still completes.**

    Both halves matter. A denial that left the turn stuck would be as broken as
    one that ran the tool anyway - the model needs to be told it was refused so
    it can reply to the person.
    """
    paused, toolset, model = await _pause_on_adjust_stock(settings)

    result = await resume_turn(
        [],
        paused.resume_state,
        {"call-1": False},
        settings=settings,
        model=model,
        toolset=toolset,
    )

    assert toolset.executed == []
    assert result.answer == "Done."
    assert result.pending == []


async def test_an_unknown_or_missing_decision_is_rejected(settings) -> None:
    """Both halves of the decision map are checked before the model is called.

    An unknown id means the caller is answering a call that was never pending -
    a bug worth surfacing rather than ignoring. A missing id means a call was
    left unanswered, which is exactly the parallel-batch failure Gate 15's
    finding 5 warned about: a batch that half-resolves would leave the run
    stuck with no indication why.
    """
    paused, toolset, model = await _pause_on_adjust_stock(settings)

    with pytest.raises(ValueError, match="not pending"):
        await resume_turn(
            [],
            paused.resume_state,
            {"call-1": True, "call-does-not-exist": True},
            settings=settings,
            model=model,
            toolset=toolset,
        )

    with pytest.raises(ValueError, match="no decision"):
        await resume_turn(
            [], paused.resume_state, {}, settings=settings, model=model, toolset=toolset
        )

    # Neither rejection reached the tool or the model.
    assert toolset.executed == []
```

`pytest` and `Any` are already imported at the top of this file from Task 2 — no import changes are needed here beyond adding `resume_turn` to the `conversation` line above.

- [ ] **Step 2: Developer runs the tests to verify they fail**

```bash
pytest tests/test_approval.py -v
```

Expect: `ImportError: cannot import name 'resume_turn' from 'conversation'`.

- [ ] **Step 3: Add `resume_turn`**

Add to `conversation.py`'s `pydantic_ai` imports:

```python
from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults, ToolApproved, ToolDenied
```

Append after `run_turn`:

```python
# What the model is told when a human refuses a tool call. Written here rather
# than taken from the caller: the caller supplies a decision, not the wording -
# one place to change the phrasing, and no way for a caller to accidentally
# tell the model something misleading about why it was stopped.
DENIAL_MESSAGE = "A human reviewed this and did not approve it."


def _pending_call_ids(messages: list[ModelMessage]) -> set[str]:
    """The tool_call_ids in `messages` that are still waiting on a decision.

    Read back out of the serialized run rather than carried alongside it, so
    resume_turn needs only `resume_state` and cannot be handed a decision map
    that was built against a different run.
    """

    return {
        part.tool_call_id
        for message in messages
        for part in getattr(message, "parts", [])
        if isinstance(part, ToolCallPart) and part.tool_kind is None
    }


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
```

- [ ] **Step 4: Developer runs the tests to verify they pass**

```bash
pytest tests/ -v
```

Expect: `9 passed`.

If `test_an_unknown_or_missing_decision_is_rejected` fails because `_pending_call_ids` returned an empty set, the `part.tool_kind is None` filter is wrong for this version — print the parts of the deserialized run and check what discriminates an unresolved call. The fallback that is guaranteed correct is to compare against ids that have no matching `ToolReturnPart`:

```python
    returned = {
        part.tool_call_id
        for message in messages
        for part in getattr(message, "parts", [])
        if isinstance(part, ToolReturnPart)
    }
    called = {
        part.tool_call_id
        for message in messages
        for part in getattr(message, "parts", [])
        if isinstance(part, ToolCallPart)
    }
    return called - returned
```

Use whichever passes, and delete the other. Add `ToolReturnPart` to the `pydantic_ai.messages` imports if you take the fallback.

- [ ] **Step 5: Developer re-verifies the architecture boundary**

From the **repository root**:

```bash
lint-imports --config agent/pyproject.toml
```

Expect: `Contracts: 1 kept, 0 broken.`

---

## Task 4: Keep `scripts/ask.py` honest

**Files:**
- Modify: `agent/scripts/ask.py` (the `_ask` function)

**Interfaces:**
- Consumes: `TurnResult.pending`, `TurnResult.answer` (Task 2).

- [ ] **Step 1: Handle the paused case**

`ask.py` prints `result.answer` directly, so after Task 2 a question like "set the price of rice to 250" prints `agent: None` — correct and useless. In `_ask`, replace:

```python
    print(f"agent: {result.answer}")
    print()

    return history + result.new_messages
```

with:

```python
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
```

- [ ] **Step 2: Developer confirms the read path is unchanged**

This step needs the backend running over HTTP. Ask the developer to start it in one terminal:

```bash
python -m mcp_server.server --http
```

(from `backend/` — check `agent/scripts/check_mcp.py`'s docstring for the exact flag if this differs.)

Then in another, from `agent/`:

```bash
python scripts/ask.py "What's low on stock?"
```

Expect: unchanged Gate 17 behaviour — a tool-call line, then a real answer listing understocked products. This confirms gating did not accidentally catch a read tool against the live server, which the fake toolset cannot prove.

**If the developer would rather skip the live run**, that is acceptable: `test_a_read_tool_runs_without_approval` covers the same property against a fake, and this gate's agreed proof is the test suite. Note the skip rather than claiming the run happened.

---

## Task 5: Close the gate in the docs

**Files:**
- Modify: `docs/AGENT-PLAN.md` (the Gate 19 section, ~line 1096)
- Modify: `docs/PLAN.md` (progress table, row 19)

- [ ] **Step 1: Write the Gate 19 close-out in `AGENT-PLAN.md`**

Append to the existing Gate 19 section, after "**Not in this gate:** the UI for it...". Two things must appear, because both are corrections rather than summaries:

```markdown
**Gate closed 2026-08-12.**

**Correction to this section's own wording.** It said `requires_approval=True` on the three
mutating tools. That kwarg belongs to `FunctionToolset` and the `@agent.tool` decorators, and is
not reachable from a hand-written `AbstractToolset` — which `mcp_client.py` is, for the
dependency reasons recorded at Gate 16. It is the same mechanism one layer down:
`pydantic_ai/tools.py:506` implements it as `kind='unapproved'` on the `ToolDefinition`, and the
run graph reads only `tool_def.kind`. So `get_tools()` sets `kind=` directly. Recorded rather
than quietly fixed, because the plan named an API surface this project cannot use, and the second
time `get_tools()` being ours has paid for itself is worth noticing — the first was the `anyOf`
schema normalisation.

**The gating rule is an allowlist of reads, not a denylist of writes.** `READ_ONLY` holds
`list_products`, `get_product`, `get_product_by_sku`; everything else is gated. This inverts what
this section originally described, deliberately: a denylist of the three mutating tools means a
seventh `@mcp.tool()` added to the backend defaults to *ungated* and executes with no human check,
with nothing failing to indicate it. Inverted, the worst case is one unnecessary confirmation.
This also supplies the safety property that `get_tools()`'s existing no-caching choice needs — a
new backend tool appearing automatically is only safe if it is gated automatically.

`conversation.py` gained `PendingApproval` (`tool_name`, `arguments`, `call_id`), two fields on
`TurnResult` (`pending`, `resume_state`) with `answer` becoming `str | None`, and `resume_turn()`
as a second public function. A paused turn appends nothing to history — a half-finished turn is
not conversation history — so `store.py` was not touched by this gate at all.

**The one place Gate 18's design did not carry over.** `Message.provider_data` serializes only a
completed turn's last message. A resume cannot use that: the decision is matched back by
`tool_call_id`, which lives on a `ToolCallPart` in a *middle* message of the run. So
`resume_state` is the whole run serialized — same `ModelMessagesTypeAdapter` trick, different
scope and different lifetime.

**`resume_state` is not persisted, by decision (developer, 2026-08-12).** A pending approval lives
in memory and dies with the process. This is acceptable only because nothing but a test asks for
one yet, and it is not a storage problem — writing the bytes to a table would be trivial. It is
deferred because the questions that come *with* persisting it have no answers yet: who expires
abandoned approvals, whether a stale approval that would overwrite a newer change is still valid,
and how sensitive a stored "when approved, write this" row is before a login system exists. **Gate
20 inherits this**, since that is where an HTTP boundary first sits between the pause and the
decision.

**Proven by tests, not a live demo (developer's call, 2026-08-12).** `agent/tests/` is the first
test suite in `agent/`: nine tests, no network, `FunctionModel` for the model and a recording fake
toolset for MCP. The two that carry the gate assert on **whether the tool ran**, not on the answer
string — a resume that returned plausible text without executing the tool would pass an
answer-only assertion and be entirely broken. A live demo was declined because it would mostly
re-prove Gate 16's result, and because a denial cannot be demonstrated against a live model at
all: the model does not choose whether it is refused.

`agent.tests` is exempt from the Gate 17 `lint-imports` contract, reasoned in
`agent/pyproject.toml`: a test that fakes the framework cannot avoid naming it. `agent.config` and
`agent.scripts` stay forbidden, which is where the contract's real value is.

**Still open, moved past this gate rather than closed at it:** `mcp_client.py`'s `call_tool`
docstring deferred the `ModelRetry` vs `ToolFailed` question to "revisit at Gate 19 if the model is
seen retrying a lookup that cannot succeed." No such retrying has been observed, and this gate's
fake toolset would not surface it. The note now points past Gate 19.
```

- [ ] **Step 2: Update the progress table in `PLAN.md`**

Replace row 19 (currently `| 19 | Requiring human approval... | ⬜ not started |`) with:

```markdown
| 19   | Requiring human approval before the AI agent can run any of its three actions that change data, enforced at the API level before any UI exists for it                          | ✅ done 2026-08-12 — the agent now stops and asks before it changes anything, and correctly carries on whether the answer is yes or no. Built to fail safe: rather than listing the three actions that need permission, we listed the three that are safe, so any *new* action someone adds later needs permission automatically instead of slipping through unnoticed. This is also the first stage with an automated test suite for the AI agent itself — nine tests that run without the internet or the real AI model, using stand-ins for both, so the yes-and-no behaviour can be checked in seconds and a refusal can be tested at all (a real AI model can't be asked to be refused). Two honest limits recorded: a pending question is held in memory only, so it's lost if the program restarts — deliberately left until stage 20, when there's a real server for it to matter on — and there's still no screen for any of this; that's stage 21. Also corrected a wrong detail in the stage's own plan: it named a feature of the AI library that isn't available the way we've built ours, though the underlying mechanism is the same one level down |
```

- [ ] **Step 3: Update the file-structure section in `PLAN.md`**

In the `agent/` block of the project file structure, add after the `scripts/check_mcp.py` entry:

```
│   ├── store.py  models.py  database.py  alembic/   # stage 18: saving conversations
│   ├── tests/                      # stage 19: the agent's own test suite. Runs with no
│   │                               # internet and no real AI model - stand-ins for both,
│   │                               # so approve/deny is checked in seconds
│   └── scripts/ask.py  check_mcp.py  verify_store.py
```

Replace the existing `scripts/check_mcp.py` line rather than duplicating it, and update the section's "last refreshed" date to note stage 19.

- [ ] **Step 4: Developer runs the full check, then commits**

The single commit handoff for this whole plan. Ask the developer to run, from `agent/`:

```bash
pytest -v
```

Expect: `9 passed`.

Then from the **repository root**:

```bash
lint-imports --config agent/pyproject.toml
```

Expect: `Contracts: 1 kept, 0 broken.`

Then, once both are green:

```bash
git add agent/ docs/PLAN.md docs/AGENT-PLAN.md docs/superpowers/
git status
```

Ask them to check `git status` output before committing — in particular that `agent/.env` is **not** staged (it holds the Gemini API key; `agent/.gitignore` should already exclude it, but this is the moment to confirm).

```bash
git commit -m "feat(agent): Gate 19 — approval gating on data-changing tools

Tools that change data now stop for human approval before running, and a
turn resumes correctly on both approve and deny.

Gated by an allowlist of read-only tools rather than a denylist of the three
mutating ones, so a tool added later is gated by default instead of silently
ungated. requires_approval=True is not reachable from a hand-written
AbstractToolset; kind=\"unapproved\" on the ToolDefinition is the same
mechanism one layer down.

First test suite in agent/: nine tests, no network and no live model, asserting
on whether the tool actually ran rather than on the answer text.

Pending approvals are held in memory only - persisting them is deferred to
Gate 20, where an HTTP boundary first makes it matter."
```

---

## Self-review notes

Checked against the spec, 2026-08-12:

- **Spec coverage.** Every section has a task: the `requires_approval` correction (Task 1 Step 7, Task 5 Step 1), fail-closed allowlist (Task 1), boundary types (Task 2 Step 3), `resume_state` vs `provider_data` (Task 2 Step 4 `_paused`), the resume call and its `ValueError` guards (Task 3), the test seam (Task 2 Step 3 `_build_agent`), all five test groups (Tasks 1–3), the two mechanical traps (Task 1 Step 4 conftest), `ask.py` (Task 4), and the docs close-out (Task 5).
- **One deliberate addition not in the spec:** `_original_question()`. The spec did not say where the user half of `new_messages` comes from on a resume, and `_completed` needs it. Reading the last `UserPromptPart` back out of `resume_state` is the answer that requires no extra parameter.
- **One known-uncertain line, flagged in place:** the `part.tool_kind is None` filter in `_pending_call_ids`. Task 3 Step 4 carries the exact fallback if it does not hold in 2.24.0, rather than leaving the implementer to invent one.
- **Type consistency.** `PendingApproval(tool_name, arguments, call_id)`, `TurnResult(answer, new_messages, tool_calls, pending, resume_state)`, `tool_kind(name)`, `READ_ONLY`, `DENIAL_MESSAGE`, `resume_turn(history, resume_state, decisions, *, settings, model, toolset)` — used identically in every task and in both test files.
