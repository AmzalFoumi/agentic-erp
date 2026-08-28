# Prompt: local Postgres for backend tests (Docker, not hosted Supabase)

Paste this whole thing to the agent as the task.

---

## Context

This is the `agentic-erp` project (repo root has `CLAUDE.md` — read it first,
it's the project's rules). The backend test suite (`backend/tests/`, run with
`pytest` from `backend/`) currently runs every test against the **live hosted
Supabase Postgres** database — there is no local database. This is called out
as a known, deliberate gap in `backend/tests/conftest.py`'s module docstring,
under the heading "Worth revisiting": *"The more thorough answer is a
dedicated test database... (or Docker Postgres locally)... worth it the
moment the suite grows"* — the suite has grown a lot since that was written,
and a full run now takes **~10 minutes** (292 tests, 3-13s each, dominated by
network latency to Supabase), which is too slow for iterating on one change.

Docker is available locally. The goal: **spin up a local, throwaway Postgres
in Docker that the backend test suite can run against instead**, so a full
local run drops from ~10 minutes to a small fraction of that, while keeping
the hosted-Supabase run available for CI / pre-push confidence checks.

## What you need to know about the current test setup

Read `backend/tests/conftest.py` in full before doing anything — it already
explains the current design and its rationale. Summary:

- There is exactly one `session` fixture. Each test runs inside a real DB
  transaction that is **always rolled back** at teardown, using SQLAlchemy
  2.0's `join_transaction_mode="create_savepoint"` — because service
  functions call `session.commit()` themselves (deliberately — see
  `backend/services/products.py` and `CLAUDE.md`'s "services/" section), a
  naive outer transaction would be closed by the first commit. The savepoint
  mode lets each `commit()` inside a test release a SAVEPOINT instead, and
  the outer rollback still undoes everything.
- Because of this, tests never leave data behind, and the suite already
  treats "the database" as disposable per-test — it's just currently pointed
  at a real hosted instance rather than a local one.
- `backend/core/database.py` builds `engine = create_engine(settings.database_url, ...)`.
  `settings.database_url` comes from `backend/core/config.py`, which reads
  `DATABASE_URL` from `backend/.env` (see `backend/.env.example` for the
  format and why it must be `postgresql+psycopg://...`).
- RLS (row-level security) is enabled on every table, deny-all, no policies —
  see `CLAUDE.md`'s "Database" section. Tests currently pass against Supabase
  because they connect as the Postgres superuser (via the connection string
  in `.env`), which bypasses RLS. A local Docker Postgres run the same way
  (a superuser role) will behave the same way — don't try to replicate RLS
  policies locally, that's not what this is for; RLS is a backstop, not
  where business rules live (also `CLAUDE.md`).
- Migrations live in `backend/alembic/versions/`, run via `alembic upgrade
  head` from `backend/` (needs `sqlalchemy.url` supplied — it's deliberately
  NOT set in `alembic.ini`, check how it's currently supplied, likely via env
  var or `alembic/env.py`).

## What to build

1. **A docker-compose file** for a throwaway local Postgres — something like
   `backend/docker-compose.test.yml` (pick the location and name that best
   fits this repo's existing conventions; check if `deploy/aisle-box/` has a
   Postgres-adjacent pattern to match, though that box intentionally runs
   against the *same shared Supabase DB*, not a local one — don't reuse its
   compose file, this is a separate, simpler thing). Plain Postgres image
   (match the major version Supabase runs, if discoverable — check
   `backend/alembic/versions/` or ask if unsure), no extensions beyond what
   migrations need, a fixed port that won't collide with anything else in
   this repo's other compose files (check `deploy/aisle-box/docker-compose*.yml`
   for ports already in use), and no persistent volume — data should not
   need to survive a `docker compose down`.

2. **A documented way to point the test run at it** — an env var is the
   simplest fit given `core/config.py`'s existing pattern (`DATABASE_URL`
   already comes from the environment). Don't hardcode a second database URL
   inside the app config; the cleanest approach is probably a
   `backend/.env.test` (or similar, gitignored like `.env` — check
   `backend/.gitignore`) that a developer copies in, or a documented
   `DATABASE_URL=... pytest` invocation. Whichever you choose, it must be
   **opt-in** — running plain `pytest` with the existing `.env` must keep
   working exactly as today (hitting real Supabase), so nobody's existing
   workflow silently changes.

3. **A migration step against the local DB, documented as recurring, not
   one-time** — because the compose file has no persistent volume (per item 1),
   `docker compose down` throws away all state, so `alembic upgrade head`
   needs to run again every time the container is recreated, not just the
   first time. Document that clearly (in whatever README/doc you add), or
   have the documented startup command run it automatically each time.

4. **Update `backend/tests/conftest.py`'s docstring** to reflect that the
   "Worth revisiting" gap is now closed, briefly, and point to the new doc.
   Don't rewrite the transaction/rollback explanation — that stays accurate
   and unchanged regardless of which Postgres it's pointed at.

5. **A short doc section** (pick the right home — likely
   `docs/BACKEND-PLAN.md`, since `conftest.py`'s docstring already points
   there, or a new `backend/tests/README.md` if that fits better) explaining:
   how to bring the container up, how to point `pytest` at it, how to run
   migrations against it, and how to tear it down. Written for a developer
   who is not deeply familiar with Docker — plain language, the actual
   commands, and what each one does.

## Constraints (read `CLAUDE.md` for the full versions of these)

- **The developer runs all toolchain and Docker commands themselves** — you
  explain what a command does and what to expect, you do not run `docker
  compose up`, `alembic upgrade head`, `pytest`, or any git/gh command. This
  applies throughout, not just at the end.
- **Verify against current docs, not training data**, before pinning a
  Postgres image tag or any Docker Compose syntax — Compose's schema and
  best practices have changed over time (e.g., the top-level `version:` key
  is deprecated in current Compose).
- Do not touch `deploy/aisle-box/` — that's a separate, hand-maintained
  deployment target pointed at the real shared Supabase DB, out of scope
  here entirely.
- Do not change anything about how tests behave against the *real* Supabase
  path — this is strictly additive.
- Follow the existing repo convention of explaining *why*, not just *what*,
  in docstrings/comments — this codebase's comments consistently justify a
  design decision rather than describe the code beneath them (skim a few
  existing files' docstrings, e.g. `backend/tests/conftest.py`,
  `backend/services/purchasing/receiving.py`, for the tone to match).

## Deliverable

A short design/plan presented to the developer before any files are
written — this is a bounded change (existing test infra, no new subsystem),
so per this project's usual workflow, a short in-chat design and an explicit
go-ahead precede implementation. Once approved: the compose file, the env/
doc wiring, the conftest.py docstring update, and the new doc section.
