# Backend — build plan

> **Subordinate to `docs/PLAN.md`.** This file is the detail under `PLAN.md`'s gates 0–8: the
> viability assessment, every backend gate as it was actually built, the decisions taken inside
> those gates, and the deferrals raised along the way. Where this file and `PLAN.md` disagree,
> **`PLAN.md` wins** and this file is the thing that is out of date.
>
> Cross-cutting rules — stop gates, division of labour, verify-against-current-docs — live in
> `PLAN.md` and are referenced here, never restated. The authentication decision lives in
> `docs/AUTH-PLAN.md`. There is **no progress table here**; `PLAN.md`'s table is the single status
> board for the whole project.
>
> Gates 0–8 are all complete. This file is therefore mostly a record of *why*, not a set of
> instructions — read it when changing backend code, not at the start of every session.

---

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


## Gate 0 — Plan, repo, branch, push

**No application code in this gate.**

1. This document, committed at `docs/PLAN.md` (split into `docs/PLAN.md` +
   `docs/BACKEND-PLAN.md` + `docs/FRONTEND-PLAN.md` + `docs/AUTH-PLAN.md` at Gate 8.5).
2. `.gitignore` (Python + Node) and a starter `README.md` describing the services-first
   architecture.
3. Developer runs, with the agent explaining and checking each step:
   - `git add . && git commit -m "docs: initial plan and project scaffolding"` — the first commit
     (the repo had _zero_ commits, so `main` does not exist until this runs)
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

### Deferred: move dependency declaration into `pyproject.toml` (raised 2026-07-30)

`requirements.txt` and `pyproject.toml` currently split the job: the first lists dependencies, the
second holds tool config only (and says so at the top of the file). The question raised was whether
the second could absorb the first. It can, three ways:

1. **A `[project]` table** — the direct `package.json` analogue. It also declares this directory an
   installable package, so it drags in a `[build-system]` table, a build backend choice, and
   `pip install -e .` in place of `pip install -r requirements.txt`.
2. **PEP 735 `[dependency-groups]`** — dependency lists with no `[project]` and no build backend,
   installed with `pip install --group`. The closest Python has to `dependencies` vs
   `devDependencies`.
3. **Leave it.** Current state.

**Deferred, staying on option 3 through Gate 6.** The reasons are ordered by weight:

- **Do not change two things at once.** Gate 6 installs and imports `mcp` for the first time. If
  that import misbehaves, the only new variable should be the SDK — not also how the venv is built.
- `requirements.txt` is what every FastAPI tutorial, Dockerfile example and deploy platform expects.
  Matching the tutorials is worth more than matching best practice while Python is still new here.
- The per-package comments in that file are load-bearing teaching material, including the live
  `mcp==2.0.0` fallback note. They survive a migration, but they are the file's real value.

What deferring costs, stated honestly:

- **No prod/dev split.** `pytest`, `httpx` and `import-linter` sit in the same file a production
  deploy would install. Harmless on a laptop; the first thing to fix when a Dockerfile exists.
- **The `sys.path` hacks stay.** `pythonpath = ["."]` in `pyproject.toml` and `prepend_sys_path = .`
  in `alembic.ini` both exist purely because the project is not installed. Option 1 removes both.

Framing worth keeping: `requirements.txt` with every version pinned by `==` is doing the job of
`package-lock.json`, not `package.json`. It records the resolved set; what `pyproject.toml` adds is
the _declaration_ layer. Python never split those two roles as cleanly as npm did, which is why the
question has three answers rather than one.

**Revisit at:** the deploy gate, when "do not install pytest in production" stops being theoretical.
Check pip's current `--group` support against live docs at that point rather than assuming it.


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

What `require` does **not** do is check _who_ answered. It encrypts to whoever presented a
certificate, without verifying that certificate is Supabase's. An attacker positioned to redirect
the connection (hostile Wi-Fi, DNS poisoning, a compromised network hop) can present their own
self-signed certificate, terminate the TLS session, read the password on the first packet, and proxy
onward to the real database. Everything looks encrypted and works normally. `require` defends the
wire against a passive eavesdropper; it does not defend against an active man-in-the-middle.

**`verify-full`** closes that: the presented certificate must chain to a CA we trust _and_ its
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

| File                      | Purpose                                                                                                                                                                             |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `core/models.py`          | ORM tables. Slice 1: `Product` (id, sku unique, name, category, unit, cost_price, sell_price, quantity_on_hand, reorder_level, timestamps, `created_by`/`updated_by` audit columns) |
| `core/exceptions.py`      | `NotFoundError`, `DuplicateError`, `ValidationError`, `PermissionDeniedError` — framework-free, the shared error vocabulary both adapters translate from                            |
| `core/actor.py`           | The `Actor` protocol (`id`, `can(permission)`) and a `SystemActor` with full permissions, used until a real auth provider is chosen. See `docs/AUTH-PLAN.md`.                   |
| `alembic.ini`, `alembic/` | Migrations, initialised in `backend/`                                                                                                                                               |

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

Note the trap for later: `BYPASSRLS`/ownership is exactly why this is free _today_. When a real auth
provider arrives and we connect as a lower-privileged role, RLS starts applying to us too, and
policies will have to be written deliberately. Enabling it now means that day is a policy-writing
exercise rather than a discovery that the table was open all along.

### Decision: where authorization is enforced (2026-07-30)

Raised by the user at the start of Gate 3: _"I don't think we should continue connecting as table
owner either. For the app itself, we must prepare to have low-level authorized users. Do we need
database users too? But we are not using Supabase Auth, we planned ThunderID — how would this
conflict?"_

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

| Path                                    | Who validates the token                  | Does the IdP matter?                                                                                                |
| --------------------------------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Browser → **PostgREST** → Postgres      | Supabase, via configured JWT secret/JWKS | **Yes** — needs a Supabase-shaped JWT; this is what the "Third-Party Auth" integrations (Clerk, Auth0, …) exist for |
| Our backend → **SQLAlchemy** → Postgres | **We do**, in `api/`                     | **No** — Supabase never sees the token                                                                              |

We are exclusively on the second path. FastAPI validates the ThunderID token itself, constructs an
`Actor`, and the database learns only `app.current_user_id`. Postgres neither knows nor cares that
ThunderID exists. Nothing to integrate; nothing to conflict. Supabase's Third-Party Auth feature is
for people whose _browser_ talks to PostgREST directly — which, having a real backend, we never do.

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
   deny-all. Any policy added later encodes an _invariant_ ("nothing is readable unless
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
  could never have produced this: it compares _columns_ against the models, RLS is not a column, and
  `alembic_version` is not one of our models. `get_advisors` had flagged it **critical** — reading
  that table leaks only a revision hash, but _writing_ it is a denial-of-service against the
  migration system (clear the row and the next `upgrade` tries to create tables that already exist;
  set a hash that does not exist and Alembic refuses to run at all).

Final state confirmed by `list_tables`: both tables `rls_enabled: true`, advisors clear.

Two lessons worth recording, both from real failures:

- **`prepend_sys_path = .` in `alembic.ini` is not boilerplate.** It was dropped while trimming the
  stock file, and `alembic revision` then failed with `ModuleNotFoundError: No module named 'core'`.
  The familiar rule "Python puts the current directory on `sys.path`" holds for `python` and
  `python -c` — but for an installed **console script** (`.venv/Scripts/alembic.exe`) Python sets
  `sys.path[0]` to the _script's_ directory, not the one you are standing in. Every tool needs its
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
service layer directly" without saying _which database_, and we have exactly one: the live Supabase
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
_without_ an import — a service returning an HTTP status code as a bare integer, say. It enforces
the dependency direction, not taste. The prose rule still stands above it.

**Settled at the same time (2026-07-30): modular monolith, not microservices.** The question was
whether `services/` should become its own process that `api/` and `mcp_server/` call over HTTP. No:
that buys independent scaling and deployment (not needed — one developer, one supermarket) at the
cost of a network hop per call, serialization both ways, auth between our own components, and a
third process that must be running before anything works. The seam stays a _module_ boundary. It is
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

**Decided: domain errors must not share a status code with any framework's own (2026-07-30).**
Raised by the user during Gate 5, and the rule now applies to every exception added from here on.
The codes FastAPI/Starlette generate unprompted are **422** (schema mismatch), **404** (no route),
**405** (wrong method) and **500**. MCP and Supabase are not on that list — MCP is JSON-RPC with its
own numeric codes, and we reach Postgres through SQLAlchemy rather than PostgREST, so neither can
put a status code on one of our responses.

Two consequences, both implemented:

1. **`ValidationError` moved 422 → 400**, and `core/exceptions.py` updated to match. 422 was
   FastAPI's; sharing it put "not enough stock" (a message for the shopkeeper) and "you posted a
   string into an int field" (a client bug) behind one code. 400, 409 and 403 are all untouched by
   the framework. A 422 from this API now means exactly one thing.
2. **404 is the one overlap that cannot be designed away** — a missing product and a mistyped URL
   are both genuinely 404. So the discriminator is the body, not the status line: every error
   response now carries `{"error": ..., "detail": ...}`, including the framework's own. A
   `StarletteHTTPException` handler names them (`RouteNotFound`, `MethodNotAllowed`,
   `NotAuthenticated`), preserving `Allow` and other required headers. The API has exactly one
   error format, and clients switch on `error`, never on the status code alone.

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
  call the _same_ `services.products` functions. Docstrings become the tool descriptions the AI
  reads. Runs over stdio so it can attach to Claude Desktop / Claude Code.
- This file will contain **zero business rules** — that is the point.
- `frontend/README.md` placeholder noting Next.js is scaffolded in a later pass.
- Verify: `python -m mcp_server.server` starts clean; optionally register it in Claude Code's MCP
  config and ask the agent to "list all products", proving both adapters share one brain.
- ~~Final invariant check: `services/` contains zero references to `fastapi`, `mcp`, or
  `HTTPException`.~~ **Superseded in Gate 4:** `lint-imports` enforces this on every run, so the
  manual grep is gone. What remains for this gate is config, not inspection — add `mcp_server` to
  `root_packages` and uncomment the `"api | mcp_server"` layer line in `backend/pyproject.toml`.

### Sub-gates: this gate stops four times, not once (2026-07-30)

Requested by the developer, who has not built an MCP server before. The other five gates stopped
once at the end; this one stops after each sub-step, because the whole gate is unfamiliar ground
rather than a new arrangement of familiar pieces. Same rules at each stop as a full gate — explain,
list files, wait for "continue" — but no commit is required until the gate completes, since a
half-written adapter is not a useful commit.

| Sub-gate | What                                                                                                                                                                 | Why it is its own stop                                                                                                                                                                                          |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 6a       | `mcp_server/__init__.py`, `server.py` with the `MCPServer` object, per-call session handling, and **one** read-only tool (`list_products`)                           | The smallest thing that runs. Everything conceptually new about MCP is here: the decorator, the docstring-as-description, where the session comes from. Adding a second tool teaches nothing the first did not. |
| 6b       | The remaining tools — `get_product`, `get_product_by_sku`, `create_product`, `update_product`, `adjust_stock`                                                        | Repetition of 6a's pattern, so it is a _practice_ step. The new material is writing docstrings for a reader that is a language model rather than a person.                                                      |
| 6c       | Error translation — the MCP dialect of `core/exceptions.py`                                                                                                          | The direct counterpart of `api/errors.py`, and the sub-gate that proves the "one vocabulary, two dialects" claim. Deliberately separated so it can be compared side by side with the HTTP version.              |
| 6d       | Wiring and verification — `pyproject.toml` (`root_packages`, `"api \| mcp_server"`), `frontend/README.md`, `lint-imports`, and attaching the server to a real client | The architecture check and the payoff. `lint-imports` here is what mechanically proves the adapter was written without reaching into `api/`.                                                                    |

**The experiment this gate actually runs.** "The business logic is written once and reused" has so
far been an assertion. Gate 5 only weakly supported it, because `api/` was written while `services/`
was still fresh in mind. The real test: can `mcp_server/server.py` be written **without opening a
single file in `api/`**? The agent will do exactly that and report the outcome honestly either way.

The failure mode has a specific shape worth naming in advance. If writing a tool requires looking at
`ProductCreate` in `api/schemas.py` to know what fields a product takes, then the true contract
drifted into the HTTP adapter and `services/` is not self-describing. The tempting shortcut —
`from api.schemas import ProductCreate` — looks like clean reuse and is not: it makes the agent
adapter depend on the web adapter. Two front doors, one hinge. `lint-imports` fails on it in 6d, but
only _after_ it is written, so not opening `api/` at all is the stronger discipline.

### Transport decision: stdio now, HTTP later with auth (2026-07-30)

The goal is for agents implemented **in the frontend** to reach these tools. A browser cannot spawn
a child process, so stdio cannot serve them — that path needs **Streamable HTTP** transport, giving
the MCP server a real URL.

> **Read with the 2026-07-31 amendment** at the end of "three deployment shapes" below: the agent is
> no longer planned to live in the frontend, and Streamable HTTP is now the deployment target rather
> than a contingency. The analysis in this section is unchanged and still correct — only the
> conclusion about _when_ it applies moved.

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

All of that requires an **authorization server** — precisely the decision that is deferred (see
`docs/AUTH-PLAN.md`). We therefore cannot implement HTTP transport correctly yet.

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

### Who can actually reach this server: three deployment shapes (2026-07-30)

Raised by the developer, whose intent is a product where "a user can either use the UI or the agent
to get things done related to their ERP needs" — and who reasonably asked whether writing an MCP
server means exposing the ERP to every agent everywhere.

**It does not.** `transport="stdio"` means standard input/output — no port, no socket, no URL. The
only way to call it is to be a process on the same machine that spawns `python -m mcp_server.server`
as a child and writes JSON-RPC to its stdin. Today it is _less_ reachable than the FastAPI app,
which at least binds `127.0.0.1:8000`. Publishing an MCP server is a separate, deliberate act — a
`server.json` submitted to a registry, deployed to a public URL. None of that is done here.

Three shapes, of which only the third is genuinely exposed:

| Shape                                              | Who runs the agent                      | Where the MCP server runs      | Reachable from the internet?                             |
| -------------------------------------------------- | --------------------------------------- | ------------------------------ | -------------------------------------------------------- |
| **A — agent inside our backend** ← **the target**  | We do, server-side, behind our own auth | Child process of our own agent | No                                                       |
| B — the user's own client (Claude Desktop, Cursor) | The user                                | On the user's machine          | No, but the client is software we do not control         |
| C — hosted MCP server on a public URL              | Anyone                                  | Our infrastructure             | Yes — needs Streamable HTTP + the full OAuth stack above |

**Shape A is the intended architecture.** Browser → Next.js → FastAPI → `services/`, and in parallel
Browser → Next.js → our agent loop → (stdio) → `mcp_server/server.py` → `services/`. The MCP server
is internal plumbing, never a network endpoint. **stdio is therefore correct permanently for this
shape, not a temporary stand-in** — the HTTP migration noted above is only required if we ever
choose B-at-scale or C.

> **Amended 2026-07-31 (Gate 7): "permanently" was wrong, and Shape A's co-location assumption is
> dropped.** Raised by the developer while planning the frontend: _stdio may cause trouble when we
> deploy._ Correct.
>
> The paragraph above holds only while the agent loop runs **inside the Next.js process**, so a child
> process is always spawnable. That assumption no longer stands — the agent is now planned as its own
> service (in this repo, its own directory), and under any real deployment shape (containers,
> serverless, separate hosts) spawning `python -m mcp_server.server` per caller is a liability:
> process-per-request cost, no horizontal story, and it forces the agent to be co-located with the ERP.
>
> **Revised: stdio for local development; Streamable HTTP is the deployment target.** The code cost is
> still near zero — `mcp.run(transport="stdio")` → `"http"`. What it pulls in is the OAuth
> resource-server stack enumerated in the transport decision above, which is why it lands with the
> auth gate and not before. Also still applies: under HTTP, switch to Supabase's **transaction**
> pooler (6543) with `poolclass=NullPool`.
>
> Consequence already applied in `docs/FRONTEND-PLAN.md`: the frontend must not assume the agent is
> in-process. Both FastAPI and the future agent are remote HTTP services, reached through one
> identity seam, with `API_BASE_URL` and `AGENT_BASE_URL` reserved as separate server-side values.

**The privilege-escalation trap in Shape A — the reason this is written down now.** `_actor()` in
`mcp_server/server.py` currently returns `SystemActor(actor_id="mcp")`, whose `can()` returns `True`
for everything. That is harmless while the only caller is a developer on their own machine. It
becomes a real vulnerability the moment the agent runs server-side on behalf of a logged-in user,
because **the agent must never be more powerful than the user it is acting for**. Otherwise a user
whose role forbids deleting products simply asks the assistant to do it, and the assistant — running
as an omnipotent system actor — complies. The permission check in `services/` passes, correctly, on
an actor that was never the user's.

The fix is a threading problem, not a redesign: the authenticated actor from the web session must be
carried into the agent's MCP calls instead of being fabricated in `_actor()`. Per MCP 2026-07-28
statelessness, identity arrives per request anyway (`_meta`), so there is a natural place to put it.
Cost of deferring is one function; cost of forgetting is an authorization bypass with no log entry
distinguishing it from legitimate use.

**Revisit at:** the auth-provider gate, together with the `token_verifier=`/`auth=` wiring. Until
then `SystemActor` is acceptable _only_ because no un-authenticated caller exists.

### The agent stack is a separate project from this one (2026-07-30)

The developer is undecided on the agent side — possibly Gemini, possibly several small models with a
larger Gemini orchestrator. **That decision does not touch this file, now or later.**

`mcp_server/server.py` contains no reference to Claude, Anthropic, or any model. It speaks JSON-RPC
and publishes a schema generated from type hints. Which model calls it is decided entirely on the
other side of the pipe. For Gemini specifically: read the tool list over MCP, pass it as function
declarations (Gemini's format is JSON Schema, which is what `@mcp.tool()` already emits), forward
returned function calls back over MCP. Most agent frameworks ship that translation.

The seam, stated once: **MCP decides what the machine can do; the agent stack decides who decides.**
Separately swappable. Replacing the model provider changes zero lines here.

One consequence of the multi-model plan worth carrying into 6b: **smaller models are markedly worse
at selecting tools from vague descriptions.** Not an argument against them — an argument that the
docstrings written in 6b matter more under this design than they would with a single large model.

### Gate 6 outcome (2026-07-30)

**The experiment succeeded.** `mcp_server/` was written without opening a single file in `api/`.
Everything came from `services/products.py` and `core/`. That the two adapters nonetheless agree on
serialising money as a decimal string is convergence, not coordination — both hit the same
constraint, and there is only one correct answer to it.

Verified three ways: `31 passed` (9 service, 13 API, 9 MCP); `lint-imports` 3 contracts kept over 37
files with `mcp_server` now in `root_packages` and the top layer read as `"api | mcp_server"`; and a
real `ClientSession` over stdio listed all six tools and called `list_products` against the live
Supabase database.

Four findings worth keeping:

- **MCP has two error channels and only one is ours.** A JSON-RPC error (`MCPError` + numeric code)
  says _the protocol failed_ and goes to the client; `CallToolResult(isError=True)` says _the tool
  could not do the job_ and goes to the model. Domain errors use the second, exclusively. Reaching
  for a JSON-RPC code for "no product with id 5" would repeat the HTTP 422 mistake — borrowing the
  framework's vocabulary for something the framework did not say. The numeric range stays the SDK's.
- **The SDK's default error handling is insufficient in a way that is invisible.** Left alone, every
  exception becomes `f"Error executing tool {name}: {e}"`. A model then cannot distinguish "that
  product does not exist" from "the database is unreachable", and retries against a dead database.
  Worse, `str(e)` on a SQLAlchemy `OperationalError` carries the connection host and user — straight
  into a model's context, the client's logs, and possibly a provider's telemetry.
  `mcp_server/errors.py` is therefore a privacy control as much as a UX one, and it is tested as one.
- **Error messages for a model need a third clause.** What happened, why, and **what to do next**.
  The third is the one that gets skipped and the one that matters: "No product with id 5" leaves a
  model free to try id 6.
- **`functools.wraps` is load-bearing, not manners.** `@mcp.tool()` derives the schema from the
  signature and the description from `__doc__`. A decorator without `wraps` registers six identical
  `wrapper(**kwargs)` tools with no descriptions — a completely broken server that raises no error
  and starts perfectly happily. `test_every_tool_is_registered_with_a_description_and_schema` exists
  solely to catch that.

Deferred out of this gate, unchanged: HTTP transport with the OAuth resource-server stack; threading
the authenticated actor through instead of the hardcoded `SystemActor` (see the privilege note
above); a stock-movement ledger so `adjust_stock`'s `reason` is stored rather than discarded.

---

## Gate 8 — Backend contract closure (2026-07-31)

The last backend gate before a frontend exists, and it is scheduled here for one reason: every
change below alters the API's public shape, and the cost of altering a public shape is proportional
to the number of consumers. Today that number is zero. After Gate 10 it is a generated TypeScript
client plus every screen built on it.

### The four changes, and the argument for each

**1. `needs_reorder` on `ProductRead`.** The `hybrid_property` on `Product` was already exposed by
the MCP adapter and not by the HTTP one — an asymmetry nobody chose. Left alone, the frontend would
compute `quantity_on_hand <= reorder_level` itself, which puts a business rule in a third front
door where neither adapter can see it. The UI and the agent could then disagree about which
products need reordering, and both would be defensible. Shipping the answer rather than the inputs
is what keeps the rule in `core/models.py`.

**2. `{items, total}` on `GET /products`.** The route's own note said this was the moment. A total
costs a second COUNT on every list call; an offset-based control cannot render "page 3 of 12"
without it. Two decisions inside this one:

- **A sibling `count_products` rather than changing `list_products`' return type.** A pair return
  would force the COUNT on the MCP adapter too, where an agent listing products has no use for a
  page total. Two functions let each adapter pay only for what it asks for, and `mcp_server/` needed
  no change at all.
- **A body field, not an `X-Total-Count` header.** `openapi-typescript` generates precise types for
  bodies and near-useless ones for headers, and the frontend's entire contract-safety story rests on
  that generator.

The two functions share `_search_filter`, which is the part that matters. A total counting rows the
list would not return produces a pagination control promising a page that comes back empty — a bug
visible only under a search term. Sharing the predicate makes them wrong together or right together.

**3. A `fields` map on 422.** `detail` stays exactly as it was, so this is purely additive. It is
one flattened sentence, which is right for a log line and useless for a form that must put each
message under its own input. The only route from `detail` to that structure is splitting on `"; "`
and `": "`, which breaks the moment a Pydantic message contains either — and Pydantic's messages are
not written with that constraint in mind. The structure already exists in `exc.errors()`; this stops
throwing it away and asking the client to rebuild it.

**4. `ErrorCode` as a `Literal` union.** `error: str` cannot be exhaustively checked, so a
TypeScript `switch` over it compiles clean while silently missing cases. As a union, adding an error
breaks the frontend build until it is handled — which is the point.

The union is only worth something if it cannot drift from the code that emits the values, so two
tests derive the truth from the source rather than restating it: one walks `DomainError.__subclasses__`
recursively, the other reads `_FRAMEWORK_ERROR_NAMES`. Adding an exception to `core/exceptions.py`
without touching `ErrorCode` now fails the suite. This is the same instinct as `import-linter` — the
guarantee is mechanical or it is decoration.

**Also:** `ErrorResponse` had been declared since Gate 5 and attached to nothing, so it never
reached `/openapi.json` and a generated client would have known the success shape and no failures.
`responses=` on the six routes fixes that; it is declaration only and cannot change what the API
returns. The CORS allowlist moved from a literal in `api/main.py` to `CORS_ORIGINS` in settings,
because a value that must differ between development and production should not require a code edit
to deploy. Note the format trap recorded in `.env.example`: pydantic-settings parses a `list[str]`
from the environment as **JSON**, so a comma-separated string fails at import rather than cleanly.

### Deliberately not done here

No DELETE endpoint — the correct feature is soft-delete/archive, which is a real gate with a
migration and an audit story, not something smuggled into a contract cleanup. No sort parameter. No
way to clear `category` back to NULL. `adjust_stock`'s `reason` is still accepted and discarded;
storing it needs the stock-movement ledger, also deferred.

One stale docstring was corrected in passing: `adjust_stock` claimed a negative-stock refusal
reaches the client as 422. It is 400, and has been since `ValidationError` was moved off 422.

---


## Teaching notes

Delivered at each gate, at the moment the concept first appears rather than all up front: venv &
pip · what a decorator (`@app.get`, `@mcp.tool`) actually does · type hints and why FastAPI and MCP
both use them to generate schemas automatically · ORM model vs Pydantic schema · why the session is
passed in rather than grabbed globally.
