# Gate 19 — Approval Gating Design

**Status:** Approved by user 2026-08-12. Feeds a `docs/superpowers/plans/` implementation plan; the
permanent record of *why* remains `docs/AGENT-PLAN.md`'s Gate 19 section (~line 1096) — this doc is
the disposable design scaffold, not a second source of truth.

**Goal:** the agent stops before running any tool that changes data, and resumes correctly when a
human approves or denies. Proven by deterministic tests at the `conversation.py` level, with no UI
and no live model.

**Verified 2026-08-12** against the installed `pydantic-ai-slim==2.24.0` source (not training data):
`ToolDefinition.kind`, `DeferredToolRequests`, `DeferredToolResults`, `ToolApproved`, `ToolDenied`,
and the `.agents/skills/building-pydantic-ai-agents/references/TOOLS-ADVANCED.md` guidance shipped
inside the package. Versions checked live against PyPI: `pytest` 9.1.1, `pytest-asyncio` 1.4.0.

## Correction to AGENT-PLAN.md's stated mechanism

`docs/AGENT-PLAN.md`'s Gate 19 section says "`requires_approval=True` on the three mutating tools."
**That kwarg is not reachable from where our tools are declared.** It belongs to
`FunctionToolset` / `@agent.tool_plain` / `@agent.tool`, and our tools come from the hand-written
`ErpToolset` in `agent/mcp_client.py`, which builds `ToolDefinition` objects itself.

It is not a different mechanism, though — one layer down it is the same thing.
`pydantic_ai/tools.py:506` sets `kind='unapproved' if self.requires_approval else 'function'`, and
the run graph reads only `tool_def.kind` (`_tool_execution.py:627`, `result.py:1062`;
`tools.py:750` treats `('external', 'unapproved')` as the deferred kinds). So the implementation is
`kind="unapproved"` on the `ToolDefinition` built in `get_tools()`.

This is the second time owning `get_tools()` has paid for itself — the first was the `anyOf` schema
normalisation (`mcp_client.py`'s docstring, "One thing it buys back"). Behind `MCPToolset` this
would have needed a wrapper toolset rewriting the `kind` of definitions the layer below had just
built.

`AGENT-PLAN.md`'s wording is corrected at gate close, not silently: the plan named an API surface
that does not exist for a hand-written toolset.

## Which tools are gated: fail closed, not open

`AGENT-PLAN.md` names the three mutating tools — `create_product`, `update_product`,
`adjust_stock` — and the three read tools that stay ungated (`list_products`, `get_product`,
`get_product_by_sku`). Gating reads would make the future panel unusable and protects nothing.

**Implemented as an allowlist of reads, not a denylist of writes.** A module-level constant in
`agent/mcp_client.py`:

```python
READ_ONLY = frozenset({"list_products", "get_product", "get_product_by_sku"})
```

Every tool `tools/list` returns that is *not* in that set gets `kind="unapproved"`.

The reason for the inversion: a denylist of three names means a seventh `@mcp.tool()` added to
`backend/mcp_server/server.py` defaults to **ungated**. A newly added mutating tool would execute
without approval and nothing would fail or warn — the failure would be silent and in the direction
that matters. With the allowlist, a new tool is gated by default, and the worst case is one
unnecessary confirmation prompt.

This also fits a choice `get_tools()` already made: it asks `tools/list` on every run rather than
caching at startup, specifically so a new backend tool appears without restarting the agent. The
allowlist is the safety property that choice needs in order to stay safe.

## Boundary types

Gate 17's contract is that nothing outside the runtime cluster
(`conversation.py`, `model_provider.py`, `mcp_client.py`) sees Pydantic AI types. So
`DeferredToolRequests` is translated at the boundary, never returned.

Added to `agent/conversation.py`:

```python
@dataclass(frozen=True)
class PendingApproval:
    """One tool call the model wants to make, waiting on a human decision."""
    tool_name: str
    arguments: dict[str, Any]
    call_id: str
```

`call_id` is Pydantic AI's `tool_call_id`, passed straight through. It is opaque to callers: they
never construct or interpret one, only echo it back in a decision. It is exposed rather than hidden
behind an index because it is what the resume path matches on, and inventing a second identifier
alongside it would create two ways to name the same call.

`TurnResult` gains two fields and one becomes nullable:

```python
@dataclass(frozen=True)
class TurnResult:
    answer: str | None                  # None when the turn stopped for approval
    new_messages: list[Message]         # empty when the turn stopped for approval
    tool_calls: list[str]
    pending: list[PendingApproval]      # empty on a normal turn
    resume_state: bytes | None          # opaque; None unless pending
```

`answer: str | None` rather than an empty string: a paused turn genuinely has no answer, and an
empty string is a value a caller can accidentally print. `None` forces the caller to notice.

**`pending` is a list, not a single value.** Gate 15's finding 5 established that one model response
can emit several tool calls at once, and `DeferredToolRequests.approvals` is a list for exactly that
reason. A single-value field would work until the first parallel batch and then lose calls silently
— which is also the shape Gate 15 recorded as a consequence for Gate 21's approval card.

## `resume_state`, and how it differs from Gate 18's `provider_data`

This is the sharp edge of the gate, and the one place Gate 18's design does not simply carry over.

Gate 18 serializes **only the last message** of a completed turn into `Message.provider_data`
(`conversation.py`, `ModelMessagesTypeAdapter.dump_json([result.new_messages()[-1]])`). That is
deliberate and correct for a finished turn: enough to rebuild the assistant's reply with its
provider-opaque signature, no more.

**Resumption cannot use that.** A decision is matched back to its call by `tool_call_id`, which
lives on a `ToolCallPart` in a *middle* message of the interrupted run. Serializing only the last
message drops that ID, and the resume would have nothing to match. So:

```python
resume_state = ModelMessagesTypeAdapter.dump_json(result.all_messages())
```

Same serialization trick, different scope (the whole run, not one message) and different lifetime
(until the decision arrives, not forever). Both are opaque bytes that only the runtime cluster
parses.

**A paused turn appends nothing to history: `new_messages == []`.** A half-finished turn is not
conversation history, and Gate 18 explicitly scoped resumability out. History grows only when a
turn completes — which, for a gated turn, means after `resume_turn` returns. This keeps `store.py`
untouched by this gate: it still persists only completed turns, exactly as built.

**`resume_state` is not persisted this gate.** It is returned to the caller and lives in memory, so
a pending approval dies with the process. That is correct for a tests-only gate with no UI, and it
is the deliberate boundary of "not in this gate." It stops being acceptable the moment an HTTP
request boundary sits between the pause and the decision, which is Gate 20 — recorded here so that
gate inherits a known question rather than discovering a missing table.

## The resume call

A second public function rather than an overloaded `run_turn`:

```python
async def resume_turn(
    history: list[Message],
    resume_state: bytes,
    decisions: dict[str, bool],
    *,
    settings: Settings,
    model: Model | None = None,
    toolset: AbstractToolset[Any] | None = None,
) -> TurnResult
```

`decisions` maps `call_id -> approve?`. It is `dict[str, bool]` rather than our own enum because the
decision is genuinely two-state, and the *message* a denied model sees is our copy to write, not the
caller's to supply. Internally:

- `True` → `ToolApproved()`
- `False` → `ToolDenied("A human reviewed this and did not approve it.")`

then `agent.run(None, message_history=<rebuilt from resume_state>, deferred_tool_results=results)`,
following the package's own documented pattern (`TOOLS-ADVANCED.md`, "Require Tool Approval").

A `call_id` in `decisions` that is not pending, or a pending call missing from `decisions`, raises
`ValueError` from `conversation.py` before the model is called. `DeferredToolRequests.build_results`
already raises on unknown IDs; the missing-decision case is ours to check, because a silently
half-answered batch is the failure Gate 15's finding 5 warned about.

`resume_turn` returns a normal completed `TurnResult` — `answer` set, `new_messages` holding the
user question and the assistant reply. The caller's persistence path is therefore identical to
Gate 18's, with no special case for "this turn was approved."

Both `run_turn` and `resume_turn` construct their `Agent` with
`output_type=[str, DeferredToolRequests]`. Without `DeferredToolRequests` in the output type,
approvals never surface at all — stated as one of two key rules in the package's own guidance.

**Where the user question lives on resume.** `resume_turn` takes the original `history` and the
`resume_state`; the interrupted turn's user question is already inside `resume_state`, so it is not
passed again. The prompt to `agent.run` is `None` — verified against `agent/__init__.py`'s signature
(`user_prompt: str | Sequence[UserContent] | None = None`), so "no new user message" is a supported
state rather than something to fake. The package's own example passes the filler string
`'Continue'`; `None` says the same thing without adding a turn the user never typed.

## The test seam

Deterministic tests mean **no Gemini and no MCP server** — no network at all. That requires
substituting both halves:

- the model → `pydantic_ai.models.function.FunctionModel`, which scripts exactly what the model
  "decides" per step
- the toolset → a small fake `AbstractToolset` in the test file that records which tools it actually
  executed

So `run_turn` and `resume_turn` take optional `model=None, toolset=None`, defaulting to
`build_model(settings)` and `ErpToolset(settings.mcp_base_url)`.

Explicit injection rather than monkeypatching a private factory, because it matches how this project
already handles exactly this problem: `settings` is a parameter rather than a module import
"so nothing here reaches for global state" (`run_turn`'s docstring), and `Actor` is a parameter
rather than ambient request state throughout `backend/services/`. A monkeypatch would be a
test-only mechanism for a seam the codebase's own style says should be visible in the signature.

## Tests

New `agent/tests/` — the first tests in `agent/`. Adds to `agent/requirements.txt`:

- `pytest==9.1.1` — same pin as `backend/requirements.txt`; one library, two services, no reason to
  drift
- `pytest-asyncio==1.4.0` — `run_turn` is `async`, and `backend/`'s suite never needed this because
  its services are synchronous

`agent/pyproject.toml` gains `[tool.pytest.ini_options]` with `asyncio_mode = "auto"`, so each test
does not need its own marker.

Four tests, `agent/tests/test_approval.py`:

1. **A read tool runs ungated.** `FunctionModel` calls `list_products`, then answers. The fake
   toolset records that `list_products` executed; `pending` is empty and `answer` is set.
2. **A mutating tool pauses.** `FunctionModel` calls `adjust_stock`. Assert: `answer is None`,
   `new_messages == []`, `resume_state is not None`, and `pending` holds exactly one
   `PendingApproval` with `tool_name == "adjust_stock"` and the arguments the model passed. The fake
   toolset records that **nothing executed**.
3. **Approve resumes and the tool runs.** Feed test 2's `resume_state` to `resume_turn` with
   `{call_id: True}`. Assert the fake toolset recorded `adjust_stock` executing with the original
   arguments, `answer` is set, and `new_messages` has the two messages `store.py` expects.
4. **Deny resumes and the tool does not run.** Same, with `{call_id: False}`. Assert the fake
   toolset recorded **no** execution, and that a completed `TurnResult` still comes back.

Tests 3 and 4 are the actual content of the gate. "Resumes correctly on approve and deny" is only
proven by asserting the **side effect** — whether the tool ran — not by checking that some string
came back, which both cases produce.

A fifth check belongs with them but is a unit test rather than a turn: the fail-closed property
itself. `get_tools()` cannot be called without a live MCP client, so the decision is extracted into
a pure function beside `READ_ONLY`:

```python
def tool_kind(name: str) -> Literal["function", "unapproved"]:
    return "function" if name in READ_ONLY else "unapproved"
```

`get_tools()` calls it, and so does the test file's fake toolset — which means the same function
that gates the real tools is the one the approve/deny tests exercise, rather than the tests
asserting against a hand-written duplicate of the rule. Unit tests cover all six real tool names
plus an invented one (`delete_product`), which is the case that matters: a tool nobody has written
yet must come back `"unapproved"`.

## Two mechanical traps the implementation must handle

**Test imports.** `agent/` modules are flat and import each other bare (`from config import
settings`), which works because `scripts/ask.py` does `sys.path.insert(0, <agent dir>)` first. A
test package has the same problem and needs the same fix, in `agent/tests/conftest.py`, before any
test module is imported. It is worse than it looks: `agent/__init__.py` exists (added at Gate 17 so
`lint-imports` could see the tree), so pytest would otherwise resolve the tests as
`agent.tests.test_approval` from the repo root, at which point `from config import ...` inside
`conversation.py` fails.

**Tests build their own `Settings`.** `config.py` creates a module-level `settings = Settings()` at
import time, so importing anything in `agent/` still requires a valid `agent/.env` — a pre-existing
property, not something this gate introduces. Tests construct their own `Settings(...)` instance
rather than using the shared one, so a test never depends on which model or database URL the
developer happens to have configured.

## `scripts/ask.py` must not silently break

`ask.py` prints `result.answer` directly. With `answer: str | None`, asking it to change a price
would print `agent: None` — technically correct, uselessly confusing. It gains a short branch: if
`result.pending` is non-empty, print each pending tool call and state plainly that this script
cannot approve them, pointing at the tests as where approve/deny is exercised. Keeping `ask.py`
honest matters more than keeping it small; it is the script the previous three gates were
demonstrated with.

## `lint-imports`

`agent/tests/` will import `pydantic_ai` (for `FunctionModel`), so it joins the runtime cluster as
an explicitly listed exception in `agent/pyproject.toml`'s contract, with the reason recorded there:
a test that fakes the framework necessarily knows the framework exists. `agent.config` and
`agent.scripts` remain forbidden, unchanged — the contract's actual purpose is that a future HTTP
route can load settings and run a turn without `pydantic_ai` on its import path, and a test package
does not weaken that.

## Not in this gate

- **Any UI.** `AGENT-PLAN.md`'s reasoning stands: a broken interrupt behind a nice card is very hard
  to diagnose, so the interrupt is proven at this level first. Gate 21 builds the card.
- **Persisting pending approvals.** See `resume_state` above; this is a Gate 20 question.
- **A live CLI demo.** Decided 2026-08-12: the pytest suite is the proof for this gate. A live run
  would mostly re-prove "Gemini can call a tool," which Gate 16 already established, and it cannot
  deterministically produce a denial.
- **Approval as authorization.** Already documented as a known, accepted gap in `AGENT-PLAN.md`
  ("Known and accepted gap: approval is not authorization", ~line 274). Approval protects against
  the model acting without a human's say-so; it is not a boundary against an untrusted caller. That
  remains the auth gate's job (`docs/AUTH-PLAN.md`) and is not re-litigated here.
- **The `ModelRetry` vs `ToolFailed` question** that `mcp_client.py`'s `call_tool` docstring defers
  to "revisit at Gate 19 if the model is seen retrying a lookup that cannot succeed." No such
  retrying has been observed, and this gate's tests use a fake toolset that would not surface it.
  Left open, with the note updated to point past this gate rather than at it.
