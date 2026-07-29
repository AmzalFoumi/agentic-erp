# Supermarket Inventory

An inventory / purchasing system for a supermarket, built so that the **business logic is written
exactly once** and reused by two different front doors:

- a **FastAPI** HTTP API, consumed by a Next.js inventory-manager UI
- an **MCP server**, exposing the same operations as tools an AI agent can call

## The core idea

```
                 ┌──────────────┐
   Next.js UI ──▶│  api/        │──┐
                 └──────────────┘  │      ┌─────────────┐      ┌──────────┐
                                   ├─────▶│  services/  │─────▶│  core/   │──▶ Postgres
                 ┌──────────────┐  │      │ (the logic) │      │ (models) │
   AI agent ────▶│ mcp_server/  │──┘      └─────────────┘      └──────────┘
                 └──────────────┘
```

A service function is just a plain Python function. FastAPI wraps it in an HTTP route; MCP wraps it
in an agent tool. Neither framework owns the logic.

### The one rule

`services/` **must never** import from `api/` or `mcp_server/`, and must never touch web concepts —
no `HTTPException`, no `Request`, no status codes.

Services raise plain Python exceptions from `core/exceptions.py`. Each adapter translates those
into its own dialect (`NotFoundError` → HTTP 404 in the API, → an error message in MCP). The moment
a service raises `HTTPException`, the MCP server can no longer reuse it and the whole design
collapses into an ordinary web app.

## Layout

| Path                  | What lives here                                            |
| --------------------- | ---------------------------------------------------------- |
| `backend/core/`       | Config, database connection, ORM models, shared exceptions |
| `backend/services/`   | **The business logic.** Framework-free, written once       |
| `backend/api/`        | FastAPI routes — thin adapter, calls `services/`           |
| `backend/mcp_server/` | MCP tools — thin adapter, calls `services/`                |
| `backend/tests/`      | pytest, mostly against `services/` directly                |
| `frontend/`           | Next.js UI (scaffolded in a later pass)                    |
| `docs/PLAN.md`        | The build plan and its stop gates — the source of truth    |

## Stack

Python 3.12 · FastAPI · SQLAlchemy + Alembic · Postgres (hosted on Supabase) · MCP Python SDK ·
Next.js (later)

## Status

Under construction.
