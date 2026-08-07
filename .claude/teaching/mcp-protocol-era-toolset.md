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

- [ ] **2.1** `AbstractToolset`'s contract: `id`, `get_tools`, `call_tool`,
      `__aenter__`/`__aexit__` — what each is for
- [ ] **2.2** Why `ErpToolset.__init__` takes a URL, not a `Client`
- [ ] **2.3** Why `get_tools()` calls `tools/list` on every run instead of
      caching at startup
- [ ] **2.4** `args_validator`: why it validates almost nothing
- [ ] **2.5** `normalise_tool_schema` — why `anyOf: [X, null]` is safe to
      collapse (what carries optionality instead)
- [ ] **2.6** Why `title` is dropped but `default` is kept
- [ ] **2.7** The edge case: why a genuine `str | int` union is left alone
- [ ] **2.8** `call_tool`: why a domain error arrives as `is_error=True`
      content rather than a protocol error, and why that converges with Gemini
- [ ] **2.9** `ModelRetry` vs `ToolFailed` — the nuance we accepted and why
- [ ] **2.10** Why there is no approval check in `call_tool`
- [ ] **2.11** The two traps: `id` being abstract, and `input_schema` vs
      `inputSchema`

## Stage 3 — Broader context

- [ ] **3.1** The `import-linter` contract weakening — what claim was actually
      being protected, and whether it survived
- [ ] **3.2** The cost we took on, and the exit condition that deletes this code
- [ ] **3.3** Why "verify against current docs, not training data" was
      load-bearing here specifically
- [ ] **3.4** What is still untested and why it can't be tested yet
