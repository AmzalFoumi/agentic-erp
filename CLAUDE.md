# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A supermarket inventory/purchasing system where business logic is written exactly once, in
`backend/services/`, and reused by two front doors: a FastAPI HTTP API (`backend/api/`) for the
Next.js UI, and an MCP server (`backend/mcp_server/`) exposing the same operations as tools for an
AI agent. `docs/PLAN.md` is the permanent **root** source of truth — the progress table and the rules
that govern every gate. Read it before making any non-trivial change, plus whichever detail doc
covers the work; nearly everything you'd otherwise guess wrong is answered there.

**One precedence order.** `PLAN.md` is deliberately short so it can be read every time; the rest are
read when you are working in the area they cover.

| File | Scope | Read when |
|---|---|---|
| `docs/PLAN.md` | Progress table (gates 0–26), stop gates, division of labour, verify-docs rule, structure | **Every gate. Root — wins over all others** |
| `docs/BACKEND-PLAN.md` | Gates 0–8 as built, backend decisions and deferrals | Changing backend code |
| `docs/FRONTEND-PLAN.md` | Gates 9–13, screen and capability inventories, design-system rationale | Changing frontend code |
| `docs/AUTH-PLAN.md` | Gates 22–25: provider decision (**ThunderID, confirmed by the Gate 23 spike**), RFC 8693 delegation, the ID-JAG-later rule, permission mapping | The auth gates |
| `docs/DEPLOY-PLAN.md` | Gate 26: hosting the five services, and the three security gaps gate 25 deferred into it | Deployment work |
| `docs/AGENT-PLAN.md` | Gates 14–21, the Pydantic AI / Gemini decision, the agent's own schema, the localhost stop condition | Changing anything in `agent/` |
| `CLAUDE.md` (this file) | A summary for agent onboarding | Subordinate to all five |
| `frontend/AGENTS.md` (+ `frontend/CLAUDE.md`, which just includes it) | **Build output** — rewritten by `next dev` on every start, not hand-edited. One instruction: read `node_modules/next/dist/docs/` rather than trusting training data about Next.js | Writing Next.js code. Framework-only — says nothing about this project, so it never overrides the five above |

**This file is a summary, never a second opinion.** Where it disagrees with any plan doc, the plan
doc wins and this file is the thing that is out of date. A decision is recorded **once, where it is
enforced** — the other files link to it rather than restating it. Record new decisions in the doc
that owns the area, and update the summary here only if it changes something on this page.

## The one rule

`services/` must never import from `api/` or `mcp_server/`, and must never touch web concepts — no
`HTTPException`, no `Request`, no status codes, no `fastapi`/`starlette`/`mcp`/`uvicorn`/`httpx`
imports. `core/` holds to the same restriction, and both are additionally barred from importing `jwt` (gate
24 — token parsing is the adapter's job). This is enforced mechanically by `import-linter` (config in
`backend/pyproject.toml`, run via `lint-imports` from `backend/`), not just by convention. Gate 24
added a fourth root package, `authn/`, on its own layer between the adapters and `services/`.

Services raise plain exceptions from `core/exceptions.py` (`NotFoundError`, `DuplicateError`,
`ValidationError`, `PermissionDeniedError`, `AuthenticationError`); each adapter translates them into its own dialect
(`api/errors.py` → HTTP status codes, `mcp_server/errors.py` → text a model can read).

## Commands

Per the project's working agreement (see below), **the developer runs these, not the agent** — but
they're listed here for reference and for verifying instructions you give the developer are correct.

**From `backend/`** — the standard `pytest` / `uvicorn` / `alembic` invocations apply; the two that
are *not* guessable:

```bash
lint-imports               # verify the architecture boundary (3 contracts)
python -m mcp_server.server      # run the MCP server over stdio
```

**Frontend commands live in `frontend/CLAUDE.md`** — different working directory, and they only
matter when you're working there.

## Architecture

```
Next.js UI ──▶ api/ ──┐
                       ├──▶ services/ (the logic) ──▶ core/ (models) ──▶ Postgres (Supabase)
AI agent ──▶ mcp_server/ ──┘
```

- **`core/`** — `models.py` (SQLAlchemy ORM), `exceptions.py` (shared error vocabulary), `actor.py`
  (the `Actor` protocol + `SystemActor`), `config.py`, `database.py`.
- **`services/`** — the business logic, framework-free. Convention for every function: `session`
  first, `actor` second, everything else keyword-only; check `actor.can(...)` before any write;
  stamp `created_by`/`updated_by`; raise from `core/exceptions.py` rather than returning `None`.
  Services call `session.commit()` themselves (the service is the unit of business work).
- **`api/`** — FastAPI adapter. Routes contain no business logic — get a session, call the service,
  done. Error translation lives centrally in `api/errors.py` (handler-per-exception-type registered
  on the app), not scattered `try/except` in route handlers.
- **`mcp_server/`** — MCP adapter. `@mcp.tool()` functions call the same `services/` functions;
  docstrings become the tool descriptions an AI model reads, so they matter more here than typical
  code comments. Runs over **stdio for local development**; Streamable HTTP is the deployment target,
  landing with the auth gate because an HTTP MCP server must be a full OAuth resource server. (This
  supersedes an earlier "stdio is permanent" conclusion — see the 2026-07-31 amendment in
  `BACKEND-PLAN.md`.)
- **`frontend/`** — Next.js UI, from Gate 9. **A client of the API and nothing more**; no business
  logic, and never a third adapter. The rules that enforce that, and the frontend commands, are in
  `frontend/CLAUDE.md`, which loads when you work there. Detail in `docs/FRONTEND-PLAN.md`.

### Identity: `Actor`, not ambient request state

Every service function takes an `Actor` (`id`, `can(permission)`) as its second argument instead of
reaching for `request.user` or similar. Identity is a parameter because the moment `services/` knows
what an HTTP request is, the MCP server can no longer reuse it. Each adapter builds its own `Actor`
from whatever it has and passes it down. **As of gate 24 the HTTP side is real**: `api/deps.py`'s
`get_actor()` validates a bearer token via `authn/` and returns a `TokenActor` whose `can()` is set
membership over the token's `scope` claim. Not one service function changed when that landed — the
call sites already existed, which was the entire point of doing this early.

`SystemActor` (grants everything) now survives behind one condition — `AUTH_ENABLED=false`, for
tests and offline work — but in **two** places, and both are live code paths, not leftovers:
`mcp_server/server.py`'s `_actor()` and `agent/app.py`'s `get_actor()` (`agent/app.py:158`). This
line used to say "exactly one place"; that was wrong, found by CodeRabbit on PR #31. It matters
because it means **one boolean turns identity off across two services at once**, which is why gate
26 lists `AUTH_ENABLED` among the things a deployment must not be able to flip
(`docs/DEPLOY-PLAN.md`). What gate 25 did close is the *unconditional* fallback: with auth on,
`mcp_server/server.py` now returns a real `TokenActor` built from a token the SDK verified via
`mcp_server/auth.py`, and raises rather than inventing an identity. `agent/app.py`'s `get_actor()`
is real too on that path. The frontend's third seam,
`frontend/src/lib/auth/current-user.ts`, is **no longer hardcoded** — it reads the real session and
returns `CurrentUser | null`. It has no callers yet; it exists as the seam, not as live code.

**The deferral had two expiry conditions**, also in `PLAN.md`: either the MCP server becomes
HTTP-reachable by anything that is not the developer's own machine, or a second human user exists.
**Condition 1 fired on 2026-08-13** — the goal of hosting all five services *is* that condition — so
auth is now scheduled as gates 22–25 and is a hard prerequisite for deployment (gate 26, `docs/DEPLOY-PLAN.md`). **`docs/AUTH-PLAN.md`
is the whole workstream** — don't re-research the provider question, and read it before touching any
gate from 23 on.

**The trap this file carried from gate 6 is closed (2026-08-25).** `mcp_server/server.py`'s
`_actor()` no longer hardcodes `SystemActor`; `tests/test_mcp_auth.py` fails if it comes back. Two
things about the shape of the fix are worth knowing before touching it:

- **Two audiences, not one.** `thunderid_audience` is the HTTP API's; `thunderid_mcp_audience` is
  the MCP server's, a separate ThunderID resource server. The MCP authorization spec requires an MCP
  server to check the token was minted for *itself*, which is unimplementable if both doors share a
  string. `verify_access_token(token, audience=...)` takes it as a parameter.
- **A `200 OK` from ThunderID proves nothing.** Asking token exchange for a permission that does not
  exist returns a valid, correctly-audienced token carrying **no `scope` claim at all**. Every check
  must read the scope that came back; empty means *zero* permissions, never "unspecified, so allow".

**The loopback binding still stays until gate 26.** It is no longer the only thing between this code
and anonymous writes, but nothing rate-limits an unauthenticated caller yet and ThunderID's
certificate is still self-signed. Do not delete `agent/app.py`'s `HOST = "127.0.0.1"` or its test.

### Error handling has two independent translation layers

`core/exceptions.py`'s five errors map differently per adapter — e.g. `ValidationError` → HTTP 400
in `api/` (not 422 — that's reserved for FastAPI's own schema-validation failures) vs. a
`CallToolResult(isError=True)` text message in `mcp_server/` (never a JSON-RPC error code — that
channel is for protocol failures, not domain ones). Every API error response carries `{"error":
..., "detail": ...}` so clients discriminate by body, not status code alone (404 is the one
unavoidable overlap with routing failures).

### Database

Postgres hosted on Supabase, connected via SQLAlchemy/psycopg over the **session pooler**
(`.pooler.supabase.com:5432`), never the transaction pooler or direct endpoint — see
`.env.example` for why. RLS is enabled on every table (deny-all, no policies yet) as a backstop;
**authorization itself is enforced in `services/`**, not in RLS policies — RLS exists so a future
bug or bypass can't read/write silently, not to encode business rules. Tests never touch a separate
test database: `tests/conftest.py`'s `session` fixture wraps each test in a real transaction with a
SAVEPOINT per service-level commit, then rolls back unconditionally.

Money (`cost_price`, `sell_price`, etc.) serializes as a JSON **string**, not a number — deliberate,
to avoid float64 precision loss on `Numeric(10,2)` columns. Don't "fix" this.

## Working agreement (important — read before doing anything)

This project follows a **gated** workflow recorded in `docs/PLAN.md`. Two things apply on every
turn, not just during initial build-out:

1. **The developer runs every command that touches the toolchain or git** — both toolchains: venv
   creation/activation, `pip install`/`pip freeze`, `pytest`, `uvicorn`, `alembic`, plus `npm
   install`/`npm run *`/`npx`, and all `git`/`gh` commands. Explain what a command does and what to
   expect — don't run it yourself. Reading files, searching, `git status`/`git log`, and Supabase MCP
   read tools (`list_tables`, `get_advisors`) are fine to run.
   Three clarifications for the Node half: **generators** (`create-next-app`, `shadcn add`,
   `openapi-typescript`) are developer-run, then the agent edits the output; `src/lib/api/schema.d.ts` is
   **build output — committed but never hand-edited**; and browser MCP tools (chrome-devtools,
   playwright) may only be used **after the developer has started both `uvicorn` and `npm run dev`**
   and said continue.
2. **Verify against current docs/PyPI rather than training data** before pinning a version or citing
   API behavior — this project has already been bitten twice by stale assumptions (MCP spec/SDK
   changed the day before Gate 6; several version pins from memory were wrong before being checked).

When picking up new work: check `docs/PLAN.md`'s progress table for the current gate, and follow the
same stop-gate discipline it describes (explain what changed, list files touched and why, hand off
for a manual commit) unless the user has explicitly asked to move faster. If the work is in
`frontend/`, read `docs/FRONTEND-PLAN.md` too — in particular its **capability inventory**, which lists
what the API deliberately does *not* support (no delete, no sorting, no stock-adjustment reason).
Building against a capability that isn't there is the most likely way to waste a gate.
