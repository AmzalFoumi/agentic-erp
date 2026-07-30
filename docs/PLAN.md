# Supermarket Inventory — build plan

> This is the **permanent, committed** copy of the plan and the source of truth. It is updated at
> the end of every gate to record what was actually built.

## Progress

| Gate | What | Status |
|---|---|---|
| 0 | Plan, repo, branch, push | ✅ done — commit `4d25463`, pushed to `AmzalFoumi/agentic-erp`, working on `dev` |
| 1 | Python environment and dependencies | ✅ done — `.venv` at `backend/.venv`, 53 packages installed, `mcp==2.0.0` verified |
| 2 | Hosted Postgres on Supabase | ✅ done — project `khinbdvubrxqqalejcbp` (eu-west-3), session pooler, `PostgreSQL 17.6` verified from SQLAlchemy; `list_tables` confirms empty `public` schema |
| 3 | Models, exceptions, first migration | ⬜ not started |
| 4 | The service layer | ⬜ not started |
| 5 | Adapter #1: FastAPI | ⬜ not started |
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

## Gate 3 — Models, exceptions, first migration

| File | Purpose |
|---|---|
| `core/models.py` | ORM tables. Slice 1: `Product` (id, sku unique, name, category, unit, cost_price, sell_price, quantity_on_hand, reorder_level, timestamps, `created_by`/`updated_by` audit columns) |
| `core/exceptions.py` | `NotFoundError`, `DuplicateError`, `ValidationError`, `PermissionDeniedError` — framework-free, the shared error vocabulary both adapters translate from |
| `core/actor.py` | The `Actor` protocol (`id`, `can(permission)`) and a `SystemActor` with full permissions, used until a real auth provider is chosen. See the auth decision above. |
| `alembic.ini`, `alembic/` | Migrations, initialised in `backend/` |

- Verify: `alembic upgrade head` creates the `products` table; confirmed with the Supabase MCP
  `list_tables`, plus `get_advisors` for security warnings (expect a row-level-security notice —
  noted for later, not fixed in this pass).

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

### Open item for this gate: enforce the module boundary (raised 2026-07-30)

The layering — `api | mcp_server` → `services` → `core` — is currently a promise in prose. One tired
evening adding `from fastapi import HTTPException` to `services/` kills the design silently. This
gate is where `services/` is first written, so it is the right moment to make the rule mechanical.

Proposal, **to be decided at the start of Gate 4, not before**: add `import-linter` (2.13, released
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

Cost: one dependency, ~15 lines of config.

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

## Gate 5 — Adapter #1: FastAPI

- `api/schemas.py` — Pydantic request/response models (`ProductCreate`, `ProductRead`, …); the
  API's public contract, deliberately separate from the ORM models.
- `api/routes/products.py` — an `APIRouter` whose handlers do three things and nothing else: get a
  session, call the service, translate `NotFoundError` → 404 / `DuplicateError` → 409.
- `api/main.py` — `FastAPI()` app, CORS for `localhost:3000`, includes the router, `/health`.
- Verify: `uvicorn api.main:app --reload` → http://127.0.0.1:8000/docs, create a product through
  the interactive Swagger UI and list it back.

## Gate 6 — Adapter #2: MCP server (the proof)

- `mcp_server/server.py` — an `MCPServer("supermarket-inventory")` whose `@mcp.tool()` functions
  call the *same* `services.products` functions. Docstrings become the tool descriptions the AI
  reads. Runs over stdio so it can attach to Claude Desktop / Claude Code.
- This file will contain **zero business rules** — that is the point.
- `frontend/README.md` placeholder noting Next.js is scaffolded in a later pass.
- Verify: `python -m mcp_server.server` starts clean; optionally register it in Claude Code's MCP
  config and ask the agent to "list all products", proving both adapters share one brain.
- Final invariant check: `services/` contains zero references to `fastapi`, `mcp`, or
  `HTTPException`. (If the Gate 4 open item is adopted, `lint-imports` does this automatically.)

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
