# Supermarket Inventory — build plan

> This is the **permanent, committed** copy of the plan and the source of truth. It is updated at
> the end of every gate to record what was actually built.

## Progress

| Gate | What | Status |
|---|---|---|
| 0 | Plan, repo, branch, push | ✅ done — commit `4d25463`, pushed to `AmzalFoumi/agentic-erp`, working on `dev` |
| 1 | Python environment and dependencies | ✅ done — `.venv` at `backend/.venv`, 53 packages installed, `mcp==2.0.0` verified |
| 2 | Hosted Postgres on Supabase | ✅ done — project `khinbdvubrxqqalejcbp` (eu-west-3), session pooler, `PostgreSQL 17.6` verified from SQLAlchemy; `list_tables` confirms empty `public` schema |
| 3 | Models, exceptions, first migration | ✅ done — commit `18545e4`; `products` + `alembic_version` both created and both with RLS enabled, confirmed by `list_tables`; `get_advisors` clean |
| 4 | The service layer | ✅ done — commit `f1da67f`; `services/products.py` (6 functions), 9 tests against the service layer with no HTTP, 3 `import-linter` contracts enforcing the boundary |
| 5 | Adapter #1: FastAPI | 🟡 files written on `feat/fastapi/initial`, awaiting your `pytest` + `lint-imports` + `uvicorn` run |
| 6 | Adapter #2: MCP server | ⬜ not started |

---

## Context

The repo started as an empty git repo with no commits. The goal is a supermarket inventory system
where the **business logic is written exactly once** and consumed by two different front doors:

- a **FastAPI** HTTP API, for a future Next.js inventory-manager UI
- an **MCP server**, exposing the same operations as tools an AI agent can call

This plan builds that layout and proves the idea works by taking one entity — **products** — all
the way through every layer, so there is a concrete pattern to copy for `inventory`, `suppliers`
and `purchasing`.

The developer is new to Python, so the plan favours the most standard, most-tutorial-compatible
choices (`venv` + `pip`, SQLAlchemy, Alembic) over faster-but-newer tooling (`uv`), and every new
file gets a short comment explaining what it is for.

**Decisions:** hosted Postgres on **Supabase** from day one · skeleton plus one working vertical
slice · backend only, frontend deferred · execution is **gated**.

## Viability assessment

The architecture is sound, and it is the standard way to build this. The reason it works:

> A service function is just a plain Python function. FastAPI can wrap it in an HTTP route;
> MCP can wrap it in an agent tool. Neither framework owns the logic.

**The one rule that makes or breaks it** — `services/` must never import from `api/` or
`mcp_server/`, and must never touch web concepts (no `HTTPException`, no `Request`, no status
codes). Services raise plain Python exceptions; each adapter translates them into its own dialect.
The moment a service raises `HTTPException`, the MCP server can no longer reuse it, and the whole
design collapses into a normal web app. Enforced with a dedicated `core/exceptions.py`.

**Toolchain verified present:** Python 3.12.4, Node 22.16, Docker 29.5, `gh` 2.95 (authenticated as
`AmzalFoumi`), Supabase MCP server (authorized, org `AmzalAgentic` / `echylxpednnurhsivqdv`).
`uv` and `psql` are absent (neither is needed). The **Figma** MCP server is unauthorized and not
needed; **Vercel** is authorized and will matter at deploy time.

**Library note:** in the current MCP Python SDK the server class is `from mcp.server import
MCPServer`. `FastMCP` still works as an alias, but most tutorials online show the old name — this
project uses the current one.

## Decision: authentication (2026-07-29)

**Supabase is used for Postgres only** — not Auth, Storage, or Realtime. The backend connects with
SQLAlchemy over a plain connection string, so the database stays portable (swap the string for Neon
or RDS and nothing else changes).

**The auth provider choice is deferred; the design for it is not.**

Human auth and agent auth are different problems. Human auth is commoditized (Supabase Auth, Clerk,
Auth0). Agent auth — an AI acting *on behalf of* a person, with a subset of their permissions and a
clear accountability trail — is unsettled and actively churning. **WSO2 ThunderID**
(<https://github.com/asgardeo/thunder>, announced May 2026) targets exactly that, with RBAC spanning
humans, agents and workloads, and is being contributed to the OpenWallet Foundation. It is also two
months old with no GA declaration, which makes it a poor first dependency for this project today.

Also note: while the MCP server runs over **stdio locally**, the agent runs as the developer and
there is no auth question to answer. It only appears when the MCP server goes remote.

**What we do now, from Gate 3/4 onward:**

- Every service function takes an `actor` as its second argument, after `session`.
- `core/exceptions.py` includes `PermissionDeniedError`.
- Permission checks live in `services/` (`actor.can("inventory:adjust")`), never in the adapters.
- Models carry `created_by` / `updated_by` audit columns.
- A `SystemActor` with full permissions is used until a real provider is wired in.

Services never learn *how* someone authenticated — only who they are and what they may do. FastAPI
will derive the `Actor` from a JWT; MCP will derive it from its session context. Both hand the
service the same object, so adopting a provider later is a change to two adapter files rather than
a rewrite. The audit columns are wanted regardless — an ERP needs "who adjusted this stock?".

**Re-evaluate ThunderID in ~6 months** (around Q1 2027), once it has a GA release, if agent-identity
governance becomes central. Otherwise Supabase Auth is the pragmatic default, since the project is
already provisioned and it integrates with Postgres row-level security.

---

## How execution works: stop gates

Work proceeds in **gated stages**. At the end of every gate the agent will:

1. **Stop.** No further file changes.
2. **Explain** what was built, in plain language, with the Python concepts introduced.
3. **List every file created or changed, and why** each one exists.
4. **Re-evaluate the remaining plan** against what was actually learned — stating explicitly if
   something should change, be dropped, or be reordered, and updating this document if so.
5. **Hand over for a manual `git commit`.** The agent shows the suggested command; the developer
   runs it. The agent does not commit.
6. **Wait for "continue."** Nothing resumes until then.

## Division of labour: who runs what

**The developer runs every command that controls Python itself or the repository.** The agent
explains each command — what it does, what output to expect, what a failure looks like — and then
waits. Learning the toolchain by typing it is the point.

Developer-run (agent explains, never executes):

- **Environment:** creating and activating the virtualenv, `deactivate`
- **Packages:** `pip install`, `pip uninstall`, `pip freeze`, `pip list`, any dependency change
- **Running the app:** `uvicorn ...`, `python -m mcp_server.server`, `pytest`
- **Migrations:** `alembic revision`, `alembic upgrade head`
- **Git:** `add`, `commit`, `push`, `checkout` — and any `gh` command

Agent-run:

- Writing and editing files
- Read-only inspection (`git status`, `git log`, reading files, searching)
- Supabase MCP tools (creating the project, `list_tables`, `execute_sql`, `get_advisors`)

If a command fails, the developer pastes the output and the agent diagnoses it.

---

## Gate 0 — Plan, repo, branch, push

**No application code in this gate.**

1. This document, committed at `docs/PLAN.md`.
2. `.gitignore` (Python + Node) and a starter `README.md` describing the services-first
   architecture.
3. Developer runs, with the agent explaining and checking each step:
   - `git add . && git commit -m "docs: initial plan and project scaffolding"` — the first commit
     (the repo had *zero* commits, so `main` does not exist until this runs)
   - `gh repo create agentic-erp --private --source=. --remote=origin`
   - `git push -u origin main`
   - `git checkout -b dev` then `git push -u origin dev` — the working branch; `main` stays clean
4. Verify with `gh repo view --web` and `git status`.

**All subsequent gates commit on `dev`, not `main`.**

## Gate 1 — Python environment and dependencies

- Agent writes `backend/requirements.txt`: `fastapi`, `uvicorn[standard]`, `sqlalchemy`,
  `psycopg[binary]`, `pydantic-settings`, `alembic`, `mcp`, `pytest`, `httpx` — with a comment
  explaining what each package is for.
- **Developer runs** the venv creation, activation, and `pip install -r requirements.txt`.
- **Concept taught:** what a venv is, how to activate it on Windows (PowerShell vs Git Bash differ),
  what `requirements.txt` is for, and pinned vs unpinned versions.
- Verify (developer runs): `pip list` shows the packages; `python -c "import fastapi, mcp"` exits
  silently.

### Outcome (2026-07-29)

All versions were checked against PyPI on the day and pinned exactly: `fastapi==0.141.0`,
`uvicorn[standard]==0.52.0`, `sqlalchemy==2.0.51`, `psycopg[binary]==3.3.4`, `alembic==1.18.5`,
`pydantic-settings==2.14.2`, `mcp==2.0.0`, `pytest==9.1.1`, `httpx==0.28.1`. Install was clean;
53 packages total. `from mcp.server import MCPServer` confirmed against the installed 2.0.0.

**MCP 2.0 note.** The 2026-07-28 MCP specification was finalised the day before this gate, and
`mcp` 2.0.0 shipped with it — a major SDK rework. The spec removes the `initialize` handshake and
protocol-level sessions (the `Mcp-Session-Id` header), making the protocol stateless so servers can
sit behind a load balancer without sticky routing; it also adds Multi Round-Trip Requests, letting
a tool ask the user a question mid-call. None of this changes our design: we run over **stdio**,
which never had transport sessions, and our state was always in Postgres. It matters if we later
host the MCP server over HTTP.

We took the one-day-old major version deliberately. Unlike the ThunderID decision, the blast radius
is tiny — `mcp` is imported by exactly one file (Gate 6) and the fallback is a one-line re-pin to
`mcp==1.29.0`. Note that `mcp` 2.0 depends on `httpx2`, so both `httpx` and `httpx2` are installed;
they are different packages, not a conflict.

## Standing rule: verify against current docs at every gate

At the start of each gate, fetch current documentation and released versions rather than relying on
the agent's training data. This gate is the proof: the MCP spec and SDK both changed within 24
hours of the work, and five of nine version pins written from memory were wrong before being
checked against PyPI.

## Gate 2 — Hosted Postgres on Supabase

- Agent runs `get_cost` → `confirm_cost` → creates the project via the Supabase MCP server. If the
  cost check reports anything other than $0, stop and ask first.
- Developer retrieves the **database password** from the Supabase dashboard (MCP does not expose
  it) and puts the connection string into `backend/.env`.
- `backend/.env.example` committed as the template; `backend/.env` gitignored. The URL must start
  `postgresql+psycopg://` for SQLAlchemy and needs `?sslmode=require`. Prefer the **session
  pooler** connection string.
- `core/config.py` (`Settings` via pydantic-settings) and `core/database.py` (`engine`,
  `SessionLocal`, `Base`, `get_session()`).
- Verify: a script opens a connection and prints the Postgres server version; cross-checked from
  the Supabase side with `list_tables`.

### Outcome (2026-07-29)

Supabase project **`agentic-erp`** created via MCP — ref `khinbdvubrxqqalejcbp`, org `AmzalAgentic`,
region **eu-west-3** (Paris, nearest available to Morocco), status `ACTIVE_HEALTHY`. `get_cost`
returned **$0/month**; free tier, so no confirmation escalation was needed.

Docs verified on the day (Supabase "Connect to your database" + "Using SQLAlchemy with Supabase",
pydantic-settings `SettingsConfigDict`). Two points confirmed rather than assumed:

- The **session pooler** (`*.pooler.supabase.com`, port **5432**) is the right choice. The direct
  endpoint is IPv6-only on the free plan; the session pooler is IPv4 on every tier. Transaction mode
  (port 6543) is the wrong one here — it does not support prepared statements, which SQLAlchemy uses
  by default, and would need `poolclass=NullPool`.
- SQLAlchemy requires the scheme `postgresql://`, not the `postgres://` the dashboard hands you;
  we additionally use `postgresql+psycopg://` to select psycopg 3 over the default psycopg2.

Engine tuned for the free tier: `pool_pre_ping=True` (the pooler drops idle connections; without
this the first query after a quiet spell fails), `pool_size=5`, `max_overflow=5`, `pool_recycle=1800`.

`get_session()` deliberately does **not** commit. Committing expresses business intent, so it
belongs to `services/`, not to connection plumbing.

### Deferred: tighten TLS to `verify-full` before production (raised 2026-07-30)

`sslmode` is a **libpq** parameter — it belongs to the Postgres C client, not to SQLAlchemy, which
is why it rides in the connection string's query part and gets passed through verbatim. Its values,
weakest to strongest: `disable` · `prefer` (libpq's default) · `require` · `verify-ca` ·
`verify-full`.

We currently set **`require`**. What that actually buys is not encryption — Supabase negotiates TLS
under `prefer` anyway — it is the removal of the **silent fallback**. Under `prefer`, a network that
blocks or strips TLS yields a plaintext connection with no error and no warning. Under `require`
that connection fails loudly. Fail-closed, not fail-open.

What `require` does **not** do is check *who* answered. It encrypts to whoever presented a
certificate, without verifying that certificate is Supabase's. An attacker positioned to redirect
the connection (hostile Wi-Fi, DNS poisoning, a compromised network hop) can present their own
self-signed certificate, terminate the TLS session, read the password on the first packet, and proxy
onward to the real database. Everything looks encrypted and works normally. `require` defends the
wire against a passive eavesdropper; it does not defend against an active man-in-the-middle.

**`verify-full`** closes that: the presented certificate must chain to a CA we trust *and* its
subject must match the hostname we asked for. An attacker cannot satisfy that without a certificate
issued for `*.pooler.supabase.com` by a trusted CA. (`verify-ca` does the chain check but not the
hostname check, so it still permits any Supabase-issued certificate to impersonate any other —
skip it and go straight to `verify-full`.)

The cost is one operational step: Supabase's CA certificate must exist as a file on disk on every
machine that connects, downloaded from the dashboard (Settings → Database → SSL Configuration),
committed as an asset or shipped in the deployment image, and pointed at with `sslrootcert`:

```
DATABASE_URL=postgresql+psycopg://...?sslmode=verify-full&sslrootcert=/path/to/prod-ca-2021.crt
```

**Deferred, not dismissed.** Today the only client is a laptop on a trusted network talking to a
database with no real data in it, so the certificate-distribution overhead buys nothing. The moment
either becomes untrue — real supermarket data lands, or the backend deploys anywhere shared — this
becomes required, and it is a two-field change to `DATABASE_URL` plus a file. Revisit at deploy
time, alongside the auth-provider decision.

## Gate 3 — Models, exceptions, first migration

| File | Purpose |
|---|---|
| `core/models.py` | ORM tables. Slice 1: `Product` (id, sku unique, name, category, unit, cost_price, sell_price, quantity_on_hand, reorder_level, timestamps, `created_by`/`updated_by` audit columns) |
| `core/exceptions.py` | `NotFoundError`, `DuplicateError`, `ValidationError`, `PermissionDeniedError` — framework-free, the shared error vocabulary both adapters translate from |
| `core/actor.py` | The `Actor` protocol (`id`, `can(permission)`) and a `SystemActor` with full permissions, used until a real auth provider is chosen. See the auth decision above. |
| `alembic.ini`, `alembic/` | Migrations, initialised in `backend/` |

- Verify: `alembic upgrade head` creates the `products` table; confirmed with the Supabase MCP
  `list_tables`, plus `get_advisors` for security warnings.

### Amended 2026-07-30: fix the RLS advisor rather than noting it

This bullet previously read "expect a row-level-security notice — noted for later, not fixed in this
pass." That was the wrong call, and it is cheap to correct now.

Supabase runs **PostgREST**, which automatically publishes every table in the `public` schema as a
REST endpoint at the project URL, reachable by anyone holding the publishable ("anon") key — a key
designed to ship in browser JavaScript, i.e. effectively public. The gate that stops an anonymous
caller reading a table through that endpoint is **row-level security**. A table with RLS disabled
has no gate. Alembic creates tables with RLS disabled, because that is plain Postgres's default and
Alembic knows nothing about Supabase.

We do not use PostgREST — we connect via SQLAlchemy as the `postgres` role over the pooler — but the
endpoint exists whether or not we use it. The exposure is real.

The fix is one statement per table, added to the migration:

```sql
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
```

With RLS enabled and **no policies defined**, the default is deny-all: PostgREST's anonymous role
sees zero rows. Our own connection is unaffected, because a table's owner bypasses RLS. So this
costs us nothing functionally and closes the hole completely.

Note the trap for later: `BYPASSRLS`/ownership is exactly why this is free *today*. When a real auth
provider arrives and we connect as a lower-privileged role, RLS starts applying to us too, and
policies will have to be written deliberately. Enabling it now means that day is a policy-writing
exercise rather than a discovery that the table was open all along.

### Decision: where authorization is enforced (2026-07-30)

Raised by the user at the start of Gate 3: *"I don't think we should continue connecting as table
owner either. For the app itself, we must prepare to have low-level authorized users. Do we need
database users too? But we are not using Supabase Auth, we planned ThunderID — how would this
conflict?"*

**Database users are not the mechanism, and there is no conflict with ThunderID.**

Postgres roles are cluster-level objects in `pg_authid`, designed for a handful of operators, not
for application end-users. One role per staff member would mean DDL for every hire, DDL for every
password reset, and a connection pool that is barely reusable (a pooled connection is only shareable
between requests using the same role). Nobody builds it that way.

The standard pattern — the one Supabase itself uses internally — is **one low-privilege role for the
whole application, plus the current user's identity carried per transaction in a session variable
that RLS policies read**. PostgREST connects as `authenticator`, switches to `anon` or
`authenticated`, and sets `request.jwt.claims` per request; `auth.uid()` is literally
`current_setting('request.jwt.claim.sub')`. The generic form, from the Supabase docs for external
auth providers:

```sql
set app.current_user_id = '<current-user-id>';   -- SET LOCAL, inside our transaction

create policy "..." on products for select
  using (owner_id = current_setting('app.current_user_id')::bigint);
```

**Why ThunderID does not conflict.** Two distinct paths into the database exist, and only one cares
who issued the JWT:

| Path | Who validates the token | Does the IdP matter? |
|---|---|---|
| Browser → **PostgREST** → Postgres | Supabase, via configured JWT secret/JWKS | **Yes** — needs a Supabase-shaped JWT; this is what the "Third-Party Auth" integrations (Clerk, Auth0, …) exist for |
| Our backend → **SQLAlchemy** → Postgres | **We do**, in `api/` | **No** — Supabase never sees the token |

We are exclusively on the second path. FastAPI validates the ThunderID token itself, constructs an
`Actor`, and the database learns only `app.current_user_id`. Postgres neither knows nor cares that
ThunderID exists. Nothing to integrate; nothing to conflict. Supabase's Third-Party Auth feature is
for people whose *browser* talks to PostgREST directly — which, having a real backend, we never do.

**Where the rules themselves live.** Two enforcement points are available, and the trap is putting
the same rules in both, where they drift apart in two languages and disagreements surface as
silently-missing rows rather than errors.

- `services/` — arbitrary Python, testable with plain pytest, explicit errors, shared by both
  adapters.
- RLS — unbypassable by any code path (a future script, a bad migration, a SQL-injection bug), but
  policies are SQL expressions: awkward beyond row-ownership, near-untestable, and the failure mode
  is silence.

**Decided:**

1. **`services/` is the single source of truth for authorization.** It is the layer both adapters
   share and the layer we can test. Rules are written there, once.
2. **RLS is a backstop, not a duplicate.** Enabled everywhere from the first migration, starting
   deny-all. Any policy added later encodes an *invariant* ("nothing is readable unless
   `app.current_user_id` is set"), never a business rule ("cashiers may not edit `sell_price`" —
   that belongs in `services/`).
3. **Dropping owner privileges is deferred to deploy time, deliberately.** It has three parts: a
   non-owner application role, the policies themselves, and `SET LOCAL` wiring. The policies cannot
   be written until the permission model exists, which is the deferred auth decision. What Gate 3
   does is make that day cheap — RLS already on, `Actor` already carrying identity, and
   `get_session()` kept as the single chokepoint through which every session in the application is
   created, which is exactly where the `SET LOCAL` goes.

Source: Supabase docs — "RLS with custom/third-party auth" and "Third-Party Auth: Clerk", read
2026-07-30.

### Outcome (2026-07-30)

Four files written: `core/models.py` (`Product`), `core/exceptions.py`, `core/actor.py`,
`alembic.ini` + `alembic/`. Two migrations applied:

- `068702c8e737` — creates `products`, then `ALTER TABLE products ENABLE ROW LEVEL SECURITY`.
- `a1c4e7b2f019` — hand-written, enables RLS on Alembic's own `alembic_version` table. Autogenerate
  could never have produced this: it compares *columns* against the models, RLS is not a column, and
  `alembic_version` is not one of our models. `get_advisors` had flagged it **critical** — reading
  that table leaks only a revision hash, but *writing* it is a denial-of-service against the
  migration system (clear the row and the next `upgrade` tries to create tables that already exist;
  set a hash that does not exist and Alembic refuses to run at all).

Final state confirmed by `list_tables`: both tables `rls_enabled: true`, advisors clear.

Two lessons worth recording, both from real failures:

- **`prepend_sys_path = .` in `alembic.ini` is not boilerplate.** It was dropped while trimming the
  stock file, and `alembic revision` then failed with `ModuleNotFoundError: No module named 'core'`.
  The familiar rule "Python puts the current directory on `sys.path`" holds for `python` and
  `python -c` — but for an installed **console script** (`.venv/Scripts/alembic.exe`) Python sets
  `sys.path[0]` to the *script's* directory, not the one you are standing in. Every tool needs its
  own fix for this: Alembic → `prepend_sys_path`; pytest → `pythonpath` in `pyproject.toml`
  (Gate 4); `uvicorn` is fine because it is invoked as `uvicorn api.main:app` from `backend/`.
- **`primary_key=True` on a `Mapped[int]` emits SERIAL, not IDENTITY.** A code comment claimed the
  latter; the live schema showed `nextval('products_id_seq'::regclass)`. Opting into the newer
  standard-SQL form would mean `mapped_column(Identity(), primary_key=True)`. SERIAL is fine here.

## Gate 4 — The service layer (the important part)

- `services/products.py`: `list_products`, `get_product`, `create_product`, `update_product`,
  `adjust_stock`. Every function takes a SQLAlchemy `Session` first and an `Actor` second, uses type
  hints, and raises from `core/exceptions.py`. Real rules live here — `adjust_stock` refuses to
  drive quantity negative; `create_product` rejects a duplicate SKU; writes check
  `actor.can(...)` and stamp `created_by`/`updated_by`.
- `services/inventory.py`, `suppliers.py`, `purchasing.py`: docstring + TODO, so the structure is
  visible.
- `tests/test_products.py`: pytest against the service layer directly (no HTTP), covering the
  duplicate-SKU and negative-stock rules.
- Verify: `pytest` passes.

### Added to this gate: tests must not pollute the live database (raised 2026-07-30)

Identified when re-evaluating the plan at the Gate 3 boundary. The plan says "pytest against the
service layer directly" without saying *which database*, and we have exactly one: the live Supabase
project. A naive test that calls `create_product` leaves that row behind permanently. Run the suite
twice and the duplicate-SKU test starts failing against its own leftovers — a test that passes once
and never again is worse than no test.

The fix is a `conftest.py` fixture that opens a connection, begins a transaction, binds the session
to it, yields, and **rolls back unconditionally** in teardown. The test sees its own writes; the
database keeps none of them. (Same trick as wrapping each Jest test in a Prisma `$transaction` that
always throws.) A dedicated test database would be the more thorough answer and is worth revisiting
if the suite grows; rollback is the right cost/benefit today.

Also in this gate: `backend/pyproject.toml`, which settles pytest's import path via `pythonpath`
— the same `sys.path` problem that broke Alembic in Gate 3, needing a different fix per tool.

### Decided: enforce the module boundary with import-linter (raised and adopted 2026-07-30)

The layering — `api | mcp_server` → `services` → `core` — is currently a promise in prose. One tired
evening adding `from fastapi import HTTPException` to `services/` kills the design silently. This
gate is where `services/` is first written, so it is the right moment to make the rule mechanical.

**Adopted at the start of Gate 4.** Add `import-linter` (2.13, released
2026-07-03, supports Python 3.10–3.14 — verified on PyPI 2026-07-30) plus two contracts in
`pyproject.toml`:

```toml
[tool.importlinter]
root_packages = ["core", "services", "api", "mcp_server"]

[[tool.importlinter.contracts]]
name = "Layers point downward only"
type = "layers"
layers = ["api | mcp_server", "services", "core"]   # `|` = siblings, independent of each other

[[tool.importlinter.contracts]]
name = "Services stay framework-free"
type = "forbidden"
source_modules = ["services"]
forbidden_modules = ["fastapi", "mcp", "starlette"]
```

`lint-imports` then runs alongside `pytest`. This automates the "final invariant check" currently
sitting at the end of Gate 6, turning it from a one-off manual grep into a build failure.

Cost: one dependency, ~15 lines of config. This also **replaces** the manual "final invariant check"
listed at the end of Gate 6 — that grep becomes a build failure instead of a thing to remember.

Note on scope: `import-linter` reads `import` statements statically. It cannot catch a rule broken
*without* an import — a service returning an HTTP status code as a bare integer, say. It enforces
the dependency direction, not taste. The prose rule still stands above it.

**Settled at the same time (2026-07-30): modular monolith, not microservices.** The question was
whether `services/` should become its own process that `api/` and `mcp_server/` call over HTTP. No:
that buys independent scaling and deployment (not needed — one developer, one supermarket) at the
cost of a network hop per call, serialization both ways, auth between our own components, and a
third process that must be running before anything works. The seam stays a *module* boundary. It is
still a real seam — if we ever outgrow the monolith, `services/` is exactly where the cut goes.

**Also settled: the database is deliberately NOT swappable.** Making it so means a repository
pattern (abstract interface in `core/`, SQLAlchemy implementation behind it, services depending only
on the interface). That is real indirection bought to enable switching off Postgres, which will never
happen. SQLAlchemy already abstracts the SQL dialect; that is where abstraction stops.

### Outcome (2026-07-30)

Written: `services/{__init__,products,inventory,suppliers,purchasing}.py`, `tests/conftest.py`,
`tests/test_products.py`, `backend/pyproject.toml`. Deleted the now-obsolete
`alembic/versions/.gitkeep`. Added `import-linter==2.13` to requirements.txt (verified on PyPI
2026-07-30; released 2026-07-03, requires Python ≥3.10).

`services/products.py` holds the five functions plus `get_product_by_sku` — added because an SKU is
what a human or an agent actually has; nobody reads an autoincrement id off a shelf label. Five
conventions are established there for every future service to copy: `session` first and `actor`
second, everything after them keyword-only, `actor.can(...)` before every write, `actor.id` into the
audit columns, and failure as an exception rather than a `None` the caller can forget to check.

**Services commit; `get_session()` still does not.** A service function is the unit of business
work, so it owns the commit — otherwise both adapters have to remember, and one of them eventually
will not. The known cost: two services cannot yet be composed into one transaction. That need
arrives in `purchasing.py`, and the answer then is a small `unit_of_work` helper, not commits
scattered into the adapters.

**The test-isolation fix that the draft plan got wrong.** A plain outer transaction would have been
ended by the first `session.commit()` inside a service. The working version is SQLAlchemy 2.0's
`Session(bind=connection, join_transaction_mode="create_savepoint")`: each service commit releases a
SAVEPOINT rather than committing for real, and the fixture's unconditional outer `rollback()` still
discards everything. Constraints and defaults behave exactly as in production; nothing survives.

**Two corrections to the import-linter config drafted above.** First, `include_external_packages =
true` is required — without it the graph contains only our own code, so a rule naming `fastapi`
matches nothing and passes because the linter never looked, which is the worst possible failure mode
for a guard rail. Second, `root_packages` cannot name `api` or `mcp_server` yet; a package that is
not on disk makes `lint-imports` fail to start. Both are listed with the layer line commented out,
to be uncommented in Gates 5 and 6. A third contract was added beyond the two proposed: `core` is
held framework-free too, on the grounds that both adapters import it, so a web dependency there
would be worse than one in `services`.

`backend/pyproject.toml` deliberately has no `[project]` table. Dependencies stay in
`requirements.txt` — the simpler, more tutorial-compatible route for an application rather than a
library meant for publishing. The file is tool config only.

## Gate 5 — Adapter #1: FastAPI

- `api/schemas.py` — Pydantic request/response models (`ProductCreate`, `ProductRead`, …); the
  API's public contract, deliberately separate from the ORM models.
- `api/routes/products.py` — an `APIRouter` whose handlers do three things and nothing else: get a
  session, call the service, translate `NotFoundError` → 404 / `DuplicateError` → 409.
- `api/main.py` — `FastAPI()` app, CORS for `localhost:3000`, includes the router, `/health`.
- `backend/pyproject.toml` — add `"api"` to `root_packages` and uncomment the `"api | mcp_server"`
  layer line (left commented in Gate 4 because naming a package that is not on disk makes
  `lint-imports` fail to start). Until this is done the new adapter is outside the contracts
  entirely, so the boundary it is meant to prove is not actually being checked.
- Verify: `uvicorn api.main:app --reload` → http://127.0.0.1:8000/docs, create a product through
  the interactive Swagger UI and list it back; `lint-imports` still reports 3 contracts kept.

### Outcome (2026-07-30)

Written: `api/{__init__,deps,errors,schemas,main}.py`, `api/routes/{__init__,products}.py`,
`tests/test_api_products.py`, plus a `client` fixture in `tests/conftest.py`. `pyproject.toml`
gained `"api"` in `root_packages` and an `"api"` layer above `services`.

**Error translation moved out of the handlers.** The plan said each handler would catch
`NotFoundError` and raise a 404. That is what tutorials show, and it is how the mapping drifts —
one rule written twelve times eventually gets written wrong once, and a missing row starts
returning a 500. Instead `api/errors.py` registers handlers on the app, driven by a dict, and the
route functions contain no `try`, no `if`, and no status codes. It also made the routes short
enough that "this file contains no business logic" is verifiable by looking rather than by trusting.

**The 422 collision, and how it was resolved.** `core/exceptions.py` maps domain `ValidationError`
to 422, but FastAPI already uses 422 for request-shape failures. Two very different things — "not
enough stock", which a shopkeeper should read, and "you posted a string into an int field", which is
a client bug — would arrive indistinguishable. Rather than diverge from the committed contract in
`core/exceptions.py`, both were given the same envelope with an `error` field naming the exception
class (`"ValidationError"` vs `"RequestValidationError"`), and FastAPI's built-in 422 body is
reshaped to match. The frontend switches on `error`, and gets exactly one error format to handle.

**Money crosses the wire as a string.** Verified against live Pydantic docs: v2 serialises `Decimal`
to JSON as a string by default. That initially looks like a bug and is the correct behaviour —
JavaScript numbers are float64, the precise representation `Numeric(10,2)` exists to avoid, so
emitting `18.00` as a JSON number would hand the frontend back the rounding drift the column was
chosen to prevent. Left as-is, asserted in a test, and documented so nobody "fixes" it.

**Two auth seams put in place while they are still free.** `deps.get_actor` currently returns a
`SystemActor(actor_id="api")`; when an auth provider lands, that one function reads the token and
nothing else changes, because every handler and every service already takes an `Actor`. And
`PermissionDeniedError` maps to 403, never 401 — by the time a service raises it, authentication has
already succeeded. Retrofitting either later would mean touching every signature in the codebase.

**Added beyond the plan: `tests/test_api_products.py` (11 tests).** Deliberately thin — it asserts
only what the adapter is responsible for (routing, status codes, the error envelope, `exclude_unset`
on PATCH), not the business rules, which `test_products.py` already covers. Re-testing rules here
would imply they live at the HTTP layer. The `client` fixture overrides `get_db` with the same
savepoint-bound session the service tests use, so HTTP tests roll back too — which is the payoff for
injecting the session rather than grabbing it inside handlers.

**No `lifespan`.** Current FastAPI replaces the deprecated `@app.on_event("startup")` with a
`lifespan` context manager, but there is nothing to start: the engine is created at import time and
its pool connects lazily. An empty lifespan added for appearances would be noise. `/health` runs a
real `SELECT 1` for the same reason — a hardcoded `{"status": "ok"}` proves only that the process
that answered is running.

## Gate 6 — Adapter #2: MCP server (the proof)

- `mcp_server/server.py` — an `MCPServer("supermarket-inventory")` whose `@mcp.tool()` functions
  call the *same* `services.products` functions. Docstrings become the tool descriptions the AI
  reads. Runs over stdio so it can attach to Claude Desktop / Claude Code.
- This file will contain **zero business rules** — that is the point.
- `frontend/README.md` placeholder noting Next.js is scaffolded in a later pass.
- Verify: `python -m mcp_server.server` starts clean; optionally register it in Claude Code's MCP
  config and ask the agent to "list all products", proving both adapters share one brain.
- ~~Final invariant check: `services/` contains zero references to `fastapi`, `mcp`, or
  `HTTPException`.~~ **Superseded in Gate 4:** `lint-imports` enforces this on every run, so the
  manual grep is gone. What remains for this gate is config, not inspection — add `mcp_server` to
  `root_packages` and uncomment the `"api | mcp_server"` layer line in `backend/pyproject.toml`.

### Transport decision: stdio now, HTTP later with auth (2026-07-30)

The goal is for agents implemented **in the frontend** to reach these tools. A browser cannot spawn
a child process, so stdio cannot serve them — that path needs **Streamable HTTP** transport, giving
the MCP server a real URL.

That URL pulls in the whole authorization stack. Per MCP 2026-07-28, an HTTP MCP server acts as an
OAuth **resource server** and MUST:

- answer unauthenticated requests with `401` + `WWW-Authenticate` pointing at its **Protected
  Resource Metadata** (RFC 9728), and publish that document naming its trusted authorization servers
- **validate the token audience on every request**, rejecting tokens not issued for this server
- **never forward the caller's token upstream** — obtain fresh credentials for any onward hop
  (confused-deputy defence)

Clients must use OAuth 2.1 authorization code flow with mandatory PKCE/S256 (RFC 7636) and the
`resource=` parameter (RFC 8707) binding the token to this server, and validate `iss` in the
authorization response (RFC 9207, hardened in 2026-07-28).

All of that requires an **authorization server** — precisely the decision deferred above (see
"Decision: authentication"). We therefore cannot implement HTTP transport correctly yet.

**Conclusion: Gate 6 stays on stdio, unchanged.** HTTP transport is added later, together with the
auth provider decision. The cost of deferring is near zero because transport is the last line of the
file — `mcp.run(transport="stdio")` becomes `mcp.run(transport="http")`. Tools, docstrings and
service calls are identical either way. Stdio is exempt from the authorization requirements in
practice: a client that can spawn the process already has local filesystem access, so there is no
network attacker in the threat model.

Two consequences to carry forward:

- **The `actor` abstraction is now load-bearing, not speculative.** MCP 2026-07-28 removed the
  `initialize` handshake and protocol-level sessions; client context moved into per-request `_meta`,
  and any state that must survive a request has to be passed explicitly. "Who is asking" therefore
  arrives with each call rather than being remembered — which is exactly what `core/actor.py` models.
- **Connection budget changes under HTTP.** Stdio runs one MCP process per client, each with its own
  engine (~10 connections at burst). Multiple HTTP replicas multiply that. At that point switch to
  Supabase's **transaction** pooler (port 6543) with `poolclass=NullPool`, letting the pooler do the
  pooling instead of the app. Not a problem today; it is why `.env.example` documents both modes.

Sources: aaif.io — "The anatomy of MCP authorization" and "Migrate sessions to stateless requests
with MCP 2026-07-28", both read 2026-07-30.

---

## Target structure

```
agentic-erp/
├── .gitignore, README.md
├── docs/PLAN.md
├── backend/
│   ├── .env.example, requirements.txt, alembic.ini, alembic/
│   ├── core/        config.py  database.py  models.py  exceptions.py
│   ├── services/    products.py  inventory.py  suppliers.py  purchasing.py
│   ├── api/         main.py  schemas.py  routes/products.py
│   ├── mcp_server/  server.py
│   └── tests/       test_products.py
└── frontend/        README.md
```

Note: the original sketch had `services/inventory.py` as the main file. `products.py` is added as
the slice-1 entity because inventory movements need products to exist first; `inventory.py` remains
a stub for stock movements and adjustment history.

## Teaching notes

Delivered at each gate, at the moment the concept first appears rather than all up front: venv &
pip · what a decorator (`@app.get`, `@mcp.tool`) actually does · type hints and why FastAPI and MCP
both use them to generate schemas automatically · ORM model vs Pydantic schema · why the session is
passed in rather than grabbed globally.
