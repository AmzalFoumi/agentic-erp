# **AIsle** - the agentic ERP

An inventory / purchasing system for a supermarket, built so that the **business logic is written
exactly once** and reused by different front doors:

- a **FastAPI** HTTP API, consumed by a Next.js inventory-manager UI
- an **MCP server**, exposing the same operations as tools an AI agent can call
- a **built-in AI assistant** that reaches the ERP only through that MCP server
- real sign-in, backed by a self-hosted OAuth login server (ThunderID)

## The core idea

```
                        ┌──────────────┐
          Next.js UI──▶│  api/        │──┐
                        └──────────────┘  │               ┌─────────────┐      ┌──────────┐
                                          ├─────────────▶│  services/   │────▶│  core/   │──▶ Postgres
                                          │               │ (the logic) │      │ (models) │
                                          │               └─────────────┘      └──────────┘
                    ┌────────────┐   ┌──────────────┐  
   agent panel  ──▶│  agent/    │─▶│ mcp_server/  │
                    └────────────┘   └──────────────┘
```

A service function is just a plain Python function. FastAPI wraps it in an HTTP route; MCP wraps it
in an agent tool. Neither framework owns the logic. The AI agent (`agent/`) is a separate service —
it never touches `services/` directly, only the MCP tools, exactly like any other agent would.

### The one rule

`services/` **must never** import from `api/` or `mcp_server/`, and must never touch web concepts —
no `HTTPException`, no `Request`, no status codes. `core/` and the `agent/` runtime cluster are held
to the same boundary, and it is enforced mechanically by `import-linter` (`lint-imports`), not just
by convention.

Services raise plain Python exceptions from `core/exceptions.py`. Each adapter translates those
into its own dialect (`NotFoundError` → HTTP 404 in the API, → an error message in MCP). The moment
a service raises `HTTPException`, the MCP server can no longer reuse it and the whole design
collapses into an ordinary web app.

## Run it (Aisle in a box - I recommend this for judges) 

The zero-setup way to see everything running together. Needs Docker Desktop running. (or another compatible Docker Host)

**1. Put the settings file in place.** The submission includes a file called `aisle.env`. Copy it
into the box folder and rename it to `.env`:

```bash
cp /path/to/aisle.env deploy/aisle-box/.env
```

**2. Optional — add a Google AI key.** Open that `.env` and paste a free key from
[aistudio.google.com/apikey](https://aistudio.google.com/apikey) into the blank `GEMINI_API_KEY=`
line. Leaving it blank is fine: the whole system still works, only the AI-assistant parts stop, and
they tell you so rather than hanging.

**3. Add the Supabase DB URL. Connects to the hosted demo database.**
 `DATABASE_URL=`
 Contact Amzal to get one that connects to a preseeded hosted SUpabase instance

**4. Start it** (first run builds four images and takes 5–10 minutes; later runs take seconds):

```bash
docker compose -f deploy/aisle-box/docker-compose.yml up --build
```

**5. Open [http://localhost:3000](http://localhost:3000) and sign in:**

| Username | Password       |
| -------- | -------------- |
| `judge`  | `AisleDemo2026!` |

That password is published on purpose — it opens nothing except the copy of the login server
running on your own machine.

On first sign-in the browser will warn *"Your connection is not private"*. That is the box's own
login server, which signs its own certificate on first run; click **Advanced → Proceed**. Full
explanation, what's actually running, and troubleshooting: **[`deploy/aisle-box/README.md`](deploy/aisle-box/README.md)**.



## Containers

The box creates **8 containers** - 6 stay running, 2 run once and exit. It builds **4 images**
(`api` and `mcp` share one) and pulls 2 more (`alpine:3.21` for the network holder,
`ghcr.io/thunder-id/thunderid:1.0.0` for the three ThunderID containers).

| Container         | Lifetime                                                    |
| ----------------- | ---------------------------------------------------------- |
| `aisle-net`       | stays running (owns the shared network)                     |
| `thunderid-seed`  | runs once, exits - lays down the pre-made login DB          |
| `thunderid-setup` | runs once, exits - generates the cert, keys, admin password |
| `thunderid`       | stays running                                               |
| `api`             | stays running                                               |
| `mcp`             | stays running                                               |
| `agent`           | stays running                                               |
| `web`             | stays running                                               |

## Develop locally

The box above is for *seeing* the system; this section is for *changing the code*. Each service
runs on its own. Commands are PowerShell-flavoured (Windows); the shell parts are the same
elsewhere.

**Backend API** — from `backend/`:

```bash
Copy-Item .env.example .env      # then fill in DATABASE_URL — see the comments in .env.example
uvicorn api.main:app --reload    # → http://127.0.0.1:8000  (API docs at /docs)
pytest                           # tests, mostly against services/ directly
lint-imports                     # the architecture-boundary check
```

`backend/tests/README.md` describes a disposable local-Postgres option so tests don't touch Supabase.

**MCP server** — from `backend/`:

```bash
python -m mcp_server.server                              # stdio, for manual use
python -m mcp_server.server --transport streamable-http  # → http://127.0.0.1:8001/mcp  (what the agent needs)
```

**AI agent** — from `agent/`, in its own virtual environment:

```bash
Copy-Item .env.example .env      # needs GEMINI_API_KEY (aistudio.google.com/apikey) and DATABASE_URL
python scripts/serve.py          # → http://127.0.0.1:8002  (loopback only — see docs/AGENT-PLAN.md)
```

The default model is Gemma 4 on Google's free tier; `GEMINI_MODEL` switches it. The `127.0.0.1`
binding is deliberate and must not change — `docs/AGENT-PLAN.md` explains why.

**Frontend** — from `frontend/`:

```bash
npm install
npm run dev                      # → http://localhost:3000
```

Other frontend commands are in `frontend/README.md`.

**Local login server (ThunderID)** — only needed for auth-on local work:

```bash
docker compose -f deploy/docker-compose.thunderid.yml up -d
```

⚠️ Never run `down -v` on this stack — it destroys every account and signing key, with no backup.
Shutdown and restart rules are in `deploy/README.md`. For work unrelated to auth, set
`AUTH_ENABLED=false` in the backend and agent `.env` files and skip this entirely.

## Layout

| Path                  | What lives here                                            |
| --------------------- | ---------------------------------------------------------- |
| `backend/core/`       | Config, database connection, ORM models, shared exceptions |
| `backend/services/`   | **The business logic.** Framework-free, written once       |
| `backend/api/`        | FastAPI routes — thin adapter, calls `services/`           |
| `backend/mcp_server/` | MCP tools — thin adapter, calls `services/`                |
| `backend/authn/`      | Token validation (Gate 24) — its own import-linter layer   |
| `backend/tests/`      | pytest, mostly against `services/` directly               |
| `agent/`              | The built-in AI assistant service — an MCP client, loopback only |
| `frontend/`           | Next.js UI — a client of the API, no business logic        |
| `deploy/aisle-box/`   | The one-command "Aisle in a box" demo stack                |
| `docs/PLAN.md`        | Progress table and the rules governing every gate — the root source of truth |
| `docs/BACKEND-PLAN.md`  | Gates 0–8 as built — subordinate to `PLAN.md`            |
| `docs/FRONTEND-PLAN.md` | Gates 9–13 — subordinate to `PLAN.md`                    |
| `docs/AUTH-PLAN.md`     | Gates 22–25: the auth provider decision and delegation — subordinate to `PLAN.md` |
| `docs/AGENT-PLAN.md`    | Gates 14–21: the AI agent's design and its loopback stop condition |
| `docs/DEPLOY-PLAN.md`   | Gate 26: the "Aisle in a box" design                     |
| `docs/FEATURES-PLAN.md` | Gates 27–30: the Action Draft queue, lots, spoilage      |
| `docs/CI-PLAN.md`       | What runs on a pull request                              |

## Stack

Python 3.12 · FastAPI · SQLAlchemy + Alembic · Postgres (hosted on Supabase) · MCP Python SDK ·
Next.js · TypeScript · Tailwind CSS · shadcn/ui · Docker · Pydantic AI · Google Gemini / Gemma
(free tier) · WSO2 ThunderID (self-hosted OAuth)

## Status

All 30 gates in `docs/PLAN.md`'s progress table are done; current work is
post-plan polish on the `feat/final-stretch` branch.

Future roadmap work will come with their own {feature}-PLAN.md file in `docs/`

`docs/PLAN.md`'s progress table is the live status board. Authentication (ThunderID, gates 22–25)
and the AI agent (gates 14–21) are both built and merged — the deferral described in older docs has
ended.
