# Running the backend test suite

**Default to the local container below for day-to-day runs.** Measured
2026-08-28: the full suite (295 tests) took ~10 minutes against live Supabase
and 5.53 seconds against the local container — same tests, same assertions,
same rollback-per-test behavior, the only difference is the network hop to
`eu-west-3` on every query. There is no reason to default to the slow path.

Plain `pytest`, with no extra setup, still keeps working exactly as it always
has: it reads `backend/.env` and runs every test against the real, hosted
Supabase project. Keep using that path for the final check before a push (see
"Which one should I actually use?" below) — just not as the everyday default
anymore.

## Why a second database at all

`conftest.py`'s `session` fixture wraps every test in a transaction and rolls
it back unconditionally when the test ends - see that file's docstring for the
full mechanism. That makes it safe to point the suite at more than one
Postgres: whichever one you're pointed at gets the writes for the duration of
one test and none of them afterward. The default is Supabase because that's
the only database this project has ever had. `docker-compose.test.yml`, next
to this README's parent directory (`backend/docker-compose.test.yml`), adds a
local one.

A "container" here is a small, disposable sandboxed copy of a program -
in this case Postgres - that runs on your own machine and can be thrown away
and rebuilt in seconds. Docker Compose is the tool that starts and stops one
from a config file (`docker-compose.test.yml`) instead of a long command line.

## One-time: bring the container up and migrate it

From `backend/`:

```powershell
docker compose -f docker-compose.test.yml up -d --wait
```

`-d` runs it in the background instead of taking over your terminal. `--wait`
makes the command not return until Postgres inside the container is actually
ready to accept connections (checked via the `healthcheck` in the compose
file) - without it, you could run the next command a second too early and see
a confusing connection-refused error.

This container starts **completely empty** - no tables. Apply every migration
to it once, the same way you would to a brand new Supabase project.

`backend/alembic/env.py` reuses this project's own SQLAlchemy engine, which is
always built from `DATABASE_URL` - there is no separate variable Alembic
understands. So for this one command only, set `DATABASE_URL` to the local
container, run the migration, then remove it again in the same line so it
can't linger in your terminal and quietly redirect the next `uvicorn` you
start there:

```powershell
$env:DATABASE_URL="postgresql+psycopg://aisle:aisle@127.0.0.1:5433/aisle_test"; alembic upgrade head; Remove-Item Env:\DATABASE_URL
```

If your terminal is Git Bash, `$env:` doesn't work (see the note below) and
`alembic` silently falls back to `backend/.env`, migrating the real Supabase
project instead of this container. Use this form there instead:

```bash
DATABASE_URL="postgresql+psycopg://aisle:aisle@127.0.0.1:5433/aisle_test" alembic upgrade head
```

## Running tests against it

Tests use a **different** variable, `TEST_DATABASE_URL`, read directly by
`backend/tests/conftest.py` - deliberately not `DATABASE_URL`, the one your
dev server (`uvicorn`) and the command above both read. Two separate names
mean setting one for a test run can never accidentally point a `uvicorn`
you start in the same terminal at the wrong database.

```powershell
$env:TEST_DATABASE_URL="postgresql+psycopg://aisle:aisle@127.0.0.1:5433/aisle_test"
pytest
```

If your terminal is Git Bash rather than PowerShell (the prompt says
`MINGW64` rather than showing a `PS` prefix), PowerShell's `$env:NAME=...`
syntax doesn't work there - Bash reads it as a command to run named
`:TEST_DATABASE_URL=...`, fails, and `pytest` then silently falls back to
Supabase because nothing was actually set. Use one of these instead:

```bash
# Set for the rest of this terminal session:
export TEST_DATABASE_URL="postgresql+psycopg://aisle:aisle@127.0.0.1:5433/aisle_test"
pytest

# Or set for this one command only, forgotten immediately after:
TEST_DATABASE_URL="postgresql+psycopg://aisle:aisle@127.0.0.1:5433/aisle_test" pytest
```

Every test now runs against `127.0.0.1:5433` instead of Supabase. Nothing
about the tests themselves changes - same fixtures, same rollback behavior -
only the address got faster.

`$env:TEST_DATABASE_URL=...` only lasts for the current PowerShell window.
Close it and open a new one, and plain `pytest` goes back to hitting Supabase
automatically, because `conftest.py` falls back to the app's real engine
(built from `DATABASE_URL` in `backend/.env`) whenever `TEST_DATABASE_URL`
isn't set. That's deliberate: nobody's normal workflow should silently change
to a different database.

## Tearing it down

```powershell
docker compose -f docker-compose.test.yml down -v
```

This deletes the container and its data. `docker-compose.test.yml` has no
`volumes:` entry of its own, but the `postgres:17-alpine` image declares one
internally, so Compose still creates an anonymous volume behind the scenes -
`down` alone leaves that volume orphaned on disk; `-v` is what actually
removes it. Either way the next `up` starts from an empty database (a fresh
anonymous volume, or the container's own layer), which means the migration
step above is not optional after a `down`; skipping it shows up as a query
failing on a table that doesn't exist.

## Which one should I actually use?

- **The everyday default — one test file, the whole suite, iterating on a
  change:** the local container. It's the difference between a network round
  trip to `eu-west-3` and a call to `127.0.0.1`, for every one of the ~300
  tests in the suite (10 minutes vs. 5.53 seconds, measured 2026-08-28).
- **Before pushing, or when you want the closest thing to a real check:**
  plain `pytest` against Supabase. It's the same database `backend/`,
  `mcp_server/`, and the deployed box actually share, and CI runs against it
  too (see `docs/CI-PLAN.md`).

## For Claude Code / an agent running these tests

The developer has given a standing exception to the usual "the developer runs
`pytest`/`alembic`, not the agent" rule (`CLAUDE.md`'s working agreement),
**scoped to this one disposable local container only**. Everything else that
rule covers — `alembic` against Supabase, `pip install`, `npm run *`, any
`git`/`gh` command — is unaffected; keep asking the developer for those.

Before running backend tests, work through this in order:

1. **Is the Docker engine running?**
   `docker info` (exits non-zero / errors if the engine itself is down).
   - **No** → don't try to start Docker Desktop or the engine yourself, that's
     an OS-level action outside this container's scope, and don't fall back to
     plain `pytest` either — that would run against live Supabase, which is
     outside the standing exception's scope. Stop and tell the developer Docker
     isn't running; let them choose whether to start it or explicitly ask for
     the Supabase path.
   - **Yes** → continue.

2. **Is the container up and healthy?**
   `docker compose -f docker-compose.test.yml ps` (from `backend/`), or
   `docker ps --filter name=aisle-test-db`.
   - **Not listed / not healthy** → bring it up yourself:
     `docker compose -f docker-compose.test.yml up -d --wait`.

3. **Is it migrated?** A fresh or just-recreated container has no tables —
   there's no volume, so this is lost on every `down`. Check directly:
   `docker exec aisle-test-db-db-1 psql -U aisle -d aisle_test -c "\dt"`.
   - **No relations found** → migrate it yourself, using the Bash form from
     step "One-time: bring the container up and migrate it" above (sets
     `DATABASE_URL` for that single command only).

4. **Run the tests**, using the Bash form (the developer's shell is Git Bash
   — see the note under "Running tests against it" for why the PowerShell
   `$env:` form doesn't work there and fails silently rather than erroring):

   ```bash
   TEST_DATABASE_URL="postgresql+psycopg://aisle:aisle@127.0.0.1:5433/aisle_test" pytest tests/test_whatever.py
   ```

Steps 1–3 are idempotent — safe to run every time without checking history
first. Do this automatically, without asking first, whenever backend tests
need to run; only stop and report to the developer (step 1's "no" branch) or
surface an error if something in steps 2–3 doesn't recover on the first
attempt.

## What this does *not* do

It does not replicate Row Level Security. The local container's `aisle` role
is a superuser, exactly like the connection string tests already use against
Supabase - RLS is bypassed the same way in both places. RLS is a backstop
against a bug bypassing `services/`, not where authorization rules live (see
`CLAUDE.md`), so there's nothing to reproduce locally.

`agent/tests/` does not use either database. Its `conftest.py` builds a fake
`Settings` object and injects fake dependencies directly - see that file's
docstring - so there is no local-Postgres setup for it to need.
