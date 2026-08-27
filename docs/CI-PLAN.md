# Continuous integration — the plan

> Subordinate to `docs/PLAN.md`. If anything here disagrees with that file, that
> file is right and this one is out of date.

## Why this exists

The project has two real, working test suites — 59 tests in `backend/tests/` and a
smaller suite in `agent/tests/` — plus two `lint-imports` checks that enforce the
architecture boundary described in `CLAUDE.md`. None of it runs automatically today.
Every check only happens because a human types the command. GitHub's only automated
signals on a pull request are CodeRabbit (an AI reviewer reading the diff) and
CodeQL (a security-pattern scanner) — neither one proves the code actually works.

This matters more right now than it would in general: gate 26 (deployment, see
`docs/DEPLOY-PLAN.md`) is the next work, and it is explicitly about editing
security-sensitive code — the agent-server needs to start verifying passes it
currently trusts blindly, and two `VERIFY_TLS=false` shortcuts need to come out
before anything goes online. That is exactly the kind of change where a quiet
regression is easy to introduce under pressure to "finally ship." Getting the test
suites running automatically first means every gate-26 pull request gets an
automatic "did I just break one of the 59 things already known to work" check from
its very first commit — not a retrofit added partway through the riskiest work this
project has done.

This is a small, contained gate on purpose. It does not touch deployment, does not
add a second Supabase project, and does not add any new secret.

## Progress

| Gate | What                                          | Status |
| ---- | --------------------------------------------- | ------ |
| CI-1 | This document — the written plan              | ✅ done — docs only, no workflow file yet |
| CI-2 | `.github/workflows/ci.yml` built to match this plan | ✅ done — two parallel jobs (`backend`, `agent`), not yet verified green on a real PR |

## Decisions

**Test database: a throwaway Postgres container inside the CI run, not the real
Supabase project.** Backend tests currently run against the live Supabase database
(there is no local Postgres today — see `backend/tests/conftest.py`'s own docstring),
made safe by wrapping every test in a transaction that is always rolled back, via
SQLAlchemy's `join_transaction_mode="create_savepoint"`. That isolation trick works
identically against any Postgres, not just Supabase's. So CI runs a `postgres:17`
service container that exists only for the length of one workflow run, builds the
schema fresh with `alembic upgrade head`, and throws the whole thing away afterward.
**Consequence worth naming:** this tests against plain Postgres, not Supabase's
row-level-security behaviour specifically — acceptable because, per `CLAUDE.md`,
authorization is enforced in `services/`, not in RLS policies; RLS is a deny-all
backstop, not where the business rules live. If a future bug is specifically about
RLS policy behaviour, this CI setup would not catch it — noted here so that gap is
a known trade-off, not a surprise. `conftest.py`'s own docstring already flags "a
dedicated test database... worth it the moment the suite grows" — that moment
arrived; this is that dedicated database, just ephemeral rather than a second
permanent Supabase project.

**Trigger: `pull_request`, plus `push` to `main` and `dev`.** Pull requests are
where a merge can actually be blocked once the check is marked required (a
follow-up, see below); the two branch pushes are a safety net in case anything
ever lands outside a PR.

**Scope: backend tests, agent tests, both `lint-imports` contracts. No frontend.**
The frontend has zero test files today (confirmed by search) — there is nothing to
run yet. Adding empty test infrastructure now would cost setup effort for no
coverage; it becomes worth doing once frontend tests exist.

**No ThunderID container in CI.** `backend/tests/test_auth.py` and the agent's own
auth tests are built to run with no ThunderID and no network — they mint their own
throwaway key pairs to test token verification, rather than talking to a real login
server. Confirmed by reading both suites before writing this plan. CI needs nothing
extra for this.

**No real secrets required.** The agent's `config.py` builds a module-level
`Settings()` the moment it is imported, so `agent/.env` must exist just for tests
to import successfully — but the `settings` fixture in `agent/tests/conftest.py`
constructs its own `Settings(...)` with dummy values and never reads the real file.
So CI writes a throwaway `.env` with fake values (`GEMINI_API_KEY=ci-dummy`, a
syntactically valid but fake `DATABASE_URL`) — no GitHub Actions secret needed on
the agent side. The backend's `DATABASE_URL` does need to be real, but it points at
the CI-local Postgres container, which is also not sensitive — its credentials
exist only inside that one throwaway run.

## Three traps, carried over so a future session doesn't rediscover them

1. **The two `lint-imports` invocations are not interchangeable.** Backend's runs
   from `backend/` with no flags. The agent's runs from the **repo root** with
   `--config agent/pyproject.toml` — neither obvious guess works, and
   `agent/pyproject.toml`'s own comments explain both failure messages you'd hit
   getting there.
2. **Backend tests need the Postgres container; agent tests do not** — but the
   agent job still needs `agent/.env` to exist (dummy values are fine), purely so
   `config.py` doesn't crash on import.
3. **`AUTH_ENABLED` must stay unset (defaults to `true`, i.e. closed) in CI, in
   both `backend/.env` and `agent/.env`.** Setting it `false` grants
   `SystemActor`-level access to every caller — meant only for a developer's own
   machine, never anywhere reachable by anything else. If a test is red in CI, the
   fix is never this switch.

## Job design (built in gate CI-2)

Two jobs, run in parallel, both on Python **3.12** (matching both local `.venv`s —
confirmed 3.12.4 in `backend/.venv/pyvenv.cfg` and `agent/.venv/pyvenv.cfg`, no
`.python-version` file existed to check instead):

**`backend` job**
- `services:` block runs `postgres:17`, exposed on 5432, throwaway credentials.
- Checkout → set up Python 3.12 → `pip install -r backend/requirements.txt`.
- Write `DATABASE_URL` pointing at the service container (`localhost:5432`).
- `alembic upgrade head` from `backend/` to build the schema.
- `pytest` from `backend/`.
- `lint-imports` from `backend/`.

**`agent` job**
- No service container.
- Checkout → set up Python 3.12 → `pip install -r agent/requirements.txt`.
- Write a dummy `agent/.env` (fake `GEMINI_API_KEY`, fake but valid-shaped
  `DATABASE_URL`).
- `pytest` from `agent/`.
- `lint-imports --config agent/pyproject.toml` from the **repo root**.

## `.github/workflows/docker-build.yml` — a separate file, on purpose

Added after CI-2, once `deploy/aisle-box/` (the submission judges actually run) existed to
have an opinion about. Builds the three Aisle Box images (backend, agent, frontend) on
every PR to `main` and discards them — proves each Dockerfile still **builds**, nothing
more. It never starts a container, so it says nothing about whether the image runs. Kept in its own file rather than folded into `ci.yml` so a slow or
flaky Docker build never blocks or muddies the fast test signal; each file's failure now
has one obvious meaning.

Deliberately does NOT build/boot the full `docker compose` stack (Option B, considered and
rejected for automatic PR checks) — that needs real secrets and takes much longer for a
check that would only run once per PR. A full stack boot-test is a manual pre-submission
rehearsal, not a CI job.

## The other automatic signal: CodeRabbit

Written up 2026-08-27, when the repository got a `.coderabbit.yaml` for the first time.
CI proves the code still works; CodeRabbit reads the diff and argues with it. Both run on
every pull request, and neither is a substitute for the other.

**Branch flow, because one setting depends on it.** Work happens on a feature branch, which
opens a pull request into `dev`; `dev` opens a pull request into `main`. Until 2026-08-27
CodeRabbit reviewed only pull requests into the **default** branch — so every feature branch
was silently skipped and had to be started by hand with an `@coderabbitai review` comment.
`reviews.auto_review.base_branches: ["dev"]` in `.coderabbit.yaml` is what fixed it. The key
lists branches to review *in addition to* the default branch, so `main` is still covered.
**If a new long-lived integration branch is ever added, it has to go in that list or it gets
no reviews and nothing says so.**

**Read `.coderabbit.yaml` before changing it.** Its header carries the one non-obvious fact:
CodeRabbit does not merge configuration sources by default, so a repository file becomes the
single source and every key it omits falls through to the vendor's **schema defaults**, not
to the Organization UI. This account enables roughly sixty linters, the knowledge base and
the finishing touches in that UI, all of which a normally-written file would have switched
off. `inheritance: true` is the line that prevents it.

**There is a rate limit, and multi-branch work is exactly what hits it.** The plan allows a
fixed number of included reviews per hour — observed as **10/hour**, reported in the footer
of every review ("4 remain after this review"). Opening six pull requests at once, which is
what parallel branch work tends to produce, spends most of an hour's allowance in a minute.
Stagger them, or expect later ones to wait.

**The plan is Pro Plus and it is free here, permanently, because the repository is public.**
Confirmed on the run configuration of every review. It does not depend on a trial, and a
trial expiring does not change it. It *would* change if the repository were ever made
private.

**Useful comment commands:** `@coderabbitai configuration` prints the fully resolved settings
annotated with which layer supplied each value — the fastest way to check the file is doing
what it looks like it does. `@coderabbitai review` is incremental; `full review` discards
previous findings and redoes them; `summary` regenerates the description only.

**Two things about its output.** An offer labelled "Coding task started" is a proposal held on
CodeRabbit's own site — it does not push a branch or a commit, and ignoring it is safe.
And its findings are a starting point, not a verdict: on PR #37 it reported a same-day
verification date as being "in the future". **Check each finding against the actual code
before acting on it**, which is the same rule this project applies to everything else.

## Deliberately deferred, not forgotten

Marking the CI check as **required** for merge (GitHub branch protection) is not
part of this gate — it's a one-click setting in the GitHub UI, not a file change,
and it's a natural follow-up once the workflow has gone green a few times and is
trusted. Noted here so it doesn't get lost.
