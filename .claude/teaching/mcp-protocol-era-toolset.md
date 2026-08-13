# Teaching: the MCP protocol-era problem and our own toolset

Session of 2026-08-06, Gate 16. Files: `agent/mcp_client.py` (new),
`agent/requirements.txt`, `docs/AGENT-PLAN.md`.

Legend: `[ ]` not yet demonstrated · `[~]` partial · `[x]` demonstrated

---

## Stage 1 — The problem

- [x] **1.1** Why `agent/` needs an MCP client at all — answered well
      ("explicit decoupling, one logic, two consumers"). Sharpened: the venv
      split makes the boundary *unforgeable*, and the agent can never hold a
      capability the API doesn't, since it only reaches `@mcp.tool()` surface
- [x] **1.2** What actually failed, mechanically: the dependency chain from
      `pydantic-ai-slim[mcp]` down to `mcp<2.0`
      → taught: each arrow is a hard requirement; installing `mcp` 1.x vs 2.0
      *is* choosing an era, because 2.0 deleted the legacy client machinery
- [x] **1.3** Why this is a *protocol era* problem and not a version-pin
      annoyance — what "legacy" vs "modern" means in MCP terms
      → taught: handshake+session vs per-request `_meta`; user independently
      had the right motivation (stateless deletes session-affinity infra)
- [x] **1.4** What "dual-era server" means, and why it made the problem *more*
      dangerous rather than less — answered correctly
- [x] **1.5** The near-miss — answered correctly; extended to the general
      point that **architectural requirements are invisible to behavioural
      tests**, which is the same reason `import-linter` exists in `backend/`
- [x] **1.6** Why LangGraph looked like the escape hatch and was worse
      → user asked for real research; upstream issue #589 ("Unbounded
      mcp>=1.24.0 breaks at import time") + PR #590 capping `mcp<2.0` in
      release 0.3.2 (2026-08-06) settles it. Lesson landed: **an absent upper
      bound is an untested claim, not a guarantee.** Also clarified LangGraph
      is graph-orchestration vs Pydantic AI's agent-runtime — tool *count* is
      not the axis they differ on.
      ⚠️ ACTION: plan doc still cites 0.3.1/unbounded; update to 0.3.2 + #589
- [x] **1.7** The four options — taught at intern level, incl. Python
      packaging vocabulary (extras, transitive deps, pre-releases). Core idea
      landed and confirmed: **a version cap is a factual claim about code, not
      a policy** — overriding it moves the failure later, not away (#6661:
      `MCPToolset` fails at *import* under SDK v2).

- [x] **1.8** (added during session) **Cap-then-shim is a sequence, not a
      choice.** User initially argued both libraries should have shipped
      compat shims instead of capping. Corrected via the real timeline —
      #6661 issue → #6737 cap → #6738 shim (still open). A shim can't precede
      the release it shims; the cap holds the line and is the cheaper failure
      point. Connected to the project's own `config.py` fail-at-startup rule.
      Re-quizzed and confirmed.

- [x] **1.9** (added) **Our exit condition is live upstream.** PR #6738 widens
      Pydantic AI to `fastmcp-slim<5` with a field-naming compat module —
      i.e. the same snake_case/camelCase trap we hit independently (#6661).
      When it ships, `mcp_client.py` should shrink to an `MCPToolset`.

## Stage 2 — The solution

- [x] **2.1** `AbstractToolset`'s contract — taught; framed as an *extension
      point* and **inversion of control** (contrast with `model_provider.py`,
      where we defined the interface; here the framework does)
- [x] **2.2 / lifecycle** Why the `Client` is built in `__aenter__`, not
      `__init__` — answered correctly: `__init__` can't be `async`, and
      nothing would guarantee the close. Analogy that worked: writing down a
      phone number vs dialling; `with open(...)`.
- [x] **2.3** Why `get_tools()` calls `tools/list` on every run — confirmed
- [x] **2.4** `args_validator`: why it validates almost nothing
      → user raised a strong objection: *"isn't this like frontend validation
      in web dev, an extra layer even though the backend owns the rule?"*
      Answered rather than dismissed: frontend validation buys **human**
      feedback speed, which has no analogue here; and **`get_tools()` already
      IS that layer** — declaring the schema to Gemini is the "publish the
      rules up front" step, so `args_validator` would be a *third* copy.
      Key principle: **duplicated validation is safe when disagreement is
      loud, dangerous when a language model can launder it into a fluent
      wrong answer.**
- [x] **2.5** Why `anyOf: [X, null]` collapses safely — confirmed:
      **`required` already carries optionality**; the null branch was a
      redundant second encoding of the same fact
- [x] **2.6** `title` dropped (duplicate of the field name = tokens +
      distraction), `default` kept (real information the model needs)
- [x] **2.7** Genuine `str | int` left intact — confirmed, with the key
      insight: collapsing it breaks **silently and permanently** (Gemini just
      never sends an int, nothing errors). **A loud 400 beats a silent lie.**
- [x] **2.8** Domain error as `is_error=True` content — confirmed. Extended:
      Gemini reached the same design independently (`"output"`/`"error"` keyed
      dict, finding 4), and this is the **third** translation of
      `core/exceptions.py` after `api/errors.py` and `mcp_server/errors.py`
- [x] **2.9** `ModelRetry` vs `ToolFailed` — taught as a *documented
      compromise*: the error vocabulary isn't distinguishable over the wire,
      so everything is `ModelRetry`, capped by `max_retries`, flagged for
      Gate 19. A known imperfection written down ≠ an oversight.
- [x] **2.10** No approval check in `call_tool` — `DeferredToolRequests` gates
      before the toolset; a check here would be invisible to `store.py` and so
      not persistable. Right idea, wrong altitude.
- [x] **2.11** The two traps: `id` is abstract but undocumented (read the
      installed source, not the docs page); `input_schema`/`is_error`
      (raw SDK) vs `inputSchema`/`isError` (FastMCP types in Pydantic AI's
      own reference code)

## Stage 3 — Broader context

- [x] **3.1** The `import-linter` contract weakening — **required a
      correction.** User first accepted "subclassing is a recognised exception
      to import boundaries" (an invented convention, offered as a distractor).
      Corrected via the parallel-case argument: `mcp_client.py` and `store.py`
      share the identical premise ("I must subclass, so I must import") but
      get opposite verdicts — therefore subclassing is *not* what decides it.
      The only test is **does the protected property survive?** Re-quizzed
      with the `store.py`/`ModelMessage` scenario and answered correctly.
      Extra habit taught: *"recognised by whom, written down where?"*
- [x] **3.2** The cost, and the exit condition (PR #6738) — taught. Code with
      a documented expiry date ≠ code you're stuck with.
- [x] **3.3** Why "verify against current docs" was load-bearing — every
      decision turned on a fact days old, and the plausible-sounding wrong
      answer ("just use `MCPToolset`") is what training data would give.
- [x] **3.4** Still untested: `server.py` remains `transport="stdio"`, so
      `ErpToolset` has never opened a connection. Construction + schema
      normalisation verified; nothing else.

---

## Closed 2026-08-11 — all items demonstrated

**Two ideas the session actually turned on**, both confirmed under quiz:

1. **Architectural requirements are invisible to behavioural tests.** Speaking
   the legacy protocol to a dual-era server behaves identically to speaking the
   modern one. No test distinguishes them, so verification had to be structural
   — dependency graphs, spec text, installed source. Same reason
   `import-linter` exists at all.
2. **A version cap is a factual claim about code, not a policy.** Overriding it
   moves the failure later, not away.

**Two places the user's own reasoning improved the outcome**, worth noting as
strengths rather than gaps: the "isn't this just frontend validation?" objection
(right instinct, and it located the real early layer — `get_tools()`), and the
"should have shipped a shim" argument (right end state, wrong sequencing).

**Follow-up actions generated by this session** (applied to
`docs/AGENT-PLAN.md`): cite langchain-mcp-adapters 0.3.2 + issue #589 as
evidence rather than the weaker 0.3.1-unbounded inference, and record PR #6738
as the live exit condition.
