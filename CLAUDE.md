# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A supermarket inventory/purchasing system where business logic is written exactly once, in
`backend/services/`, and reused by two front doors: a FastAPI HTTP API (`backend/api/`) for the
future Next.js UI, and an MCP server (`backend/mcp_server/`) exposing the same operations as tools
for an AI agent. `docs/PLAN.md` is the permanent source of truth — the full build history, every
architectural decision and why it was made, and the current gate status. Read it before making any
non-trivial change; it is long but nearly everything you'd otherwise guess wrong is answered there.

**This file is a summary of `docs/PLAN.md`, never a second opinion.** Where the two disagree,
`PLAN.md` wins and this file is the thing that is out of date. Record decisions there; update the
summary here only if a decision changes something on this page.

## The one rule

`services/` must never import from `api/` or `mcp_server/`, and must never touch web concepts — no
`HTTPException`, no `Request`, no status codes, no `fastapi`/`starlette`/`mcp`/`uvicorn`/`httpx`
imports. `core/` holds to the same restriction. This is enforced mechanically by `import-linter`
(config in `backend/pyproject.toml`, run via `lint-imports` from `backend/`), not just by convention.

Services raise plain exceptions from `core/exceptions.py` (`NotFoundError`, `DuplicateError`,
`ValidationError`, `PermissionDeniedError`); each adapter translates them into its own dialect
(`api/errors.py` → HTTP status codes, `mcp_server/errors.py` → text a model can read).

## Commands

All commands run from `backend/`. Per the project's working agreement (see below), **the developer
runs these, not the agent** — but they're listed here for reference and for verifying instructions
you give the developer are correct.

```bash
pytest                    # run the full suite
pytest tests/test_products.py -k duplicate   # a single test
lint-imports               # verify the architecture boundary (3 contracts)
uvicorn api.main:app --reload    # FastAPI dev server -> http://127.0.0.1:8000/docs
python -m mcp_server.server      # run the MCP server over stdio
alembic revision --autogenerate -m "..."   # new migration
alembic upgrade head                        # apply migrations
```

No frontend exists yet (`frontend/` is a placeholder).

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
  code comments. Runs over stdio (see "Auth and identity" below for why, and why that's permanent
  for this project's intended shape, not temporary).

### Identity: `Actor`, not ambient request state

Every service function takes an `Actor` (`id`, `can(permission)`) as its second argument instead of
reaching for `request.user` or similar. Identity is a parameter because the moment `services/` knows
what an HTTP request is, the MCP server can no longer reuse it. Each adapter builds its own `Actor`
from whatever it has and passes it down — eventually a validated bearer token in `api/deps.py`'s
`get_actor()`, and per-call `_meta` on the MCP side. Neither does that yet: `SystemActor` (grants
everything) is the only implementation today, returned by both adapters, because no auth provider is
wired in (deliberately deferred, see `docs/PLAN.md`). The two functions above are the seams where
that lands, and nothing below them changes when it does.

**Known trap, not yet fixed:** `mcp_server/server.py`'s `_actor()` currently hardcodes `SystemActor`.
That's fine only because no unauthenticated caller exists yet. The moment an agent runs server-side
on behalf of a logged-in user, the authenticated actor must be threaded through instead — otherwise
the agent is more powerful than the user it's acting for.

### Error handling has two independent translation layers

`core/exceptions.py`'s four errors map differently per adapter — e.g. `ValidationError` → HTTP 400
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

1. **The developer runs every command that touches the toolchain or git**: venv creation/activation,
   `pip install`/`pip freeze`, `pytest`, `uvicorn`, `alembic`, and all `git`/`gh` commands. Explain
   what a command does and what to expect — don't run it yourself. Reading files, searching, `git
   status`/`git log`, and Supabase MCP read tools (`list_tables`, `get_advisors`) are fine to run.
2. **Verify against current docs/PyPI rather than training data** before pinning a version or citing
   API behavior — this project has already been bitten twice by stale assumptions (MCP spec/SDK
   changed the day before Gate 6; several version pins from memory were wrong before being checked).

When picking up new work: check `docs/PLAN.md`'s progress table for the current gate, and follow the
same stop-gate discipline it describes (explain what changed, list files touched and why, hand off
for a manual commit) unless the user has explicitly asked to move faster.
