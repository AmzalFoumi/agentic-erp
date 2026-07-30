# Frontend — not built yet

Deliberately empty. This directory is a placeholder so the intended shape of the
project is visible from the repository root rather than only in `docs/PLAN.md`.

## What goes here

A **Next.js** app for the inventory manager, talking to the FastAPI adapter at
`backend/api/`. It is a client of the API and nothing more — no business rules
live here, for the same reason none live in `backend/api/` or
`backend/mcp_server/`.

## What already exists for it to use

The backend is finished for products end to end:

- `GET /products`, `GET /products/{id}`, `GET /products/by-sku/{sku}`
- `POST /products`, `PATCH /products/{id}`, `POST /products/{id}/adjust-stock`
- `GET /health`

Run `uvicorn api.main:app --reload` from `backend/` and read
<http://127.0.0.1:8000/docs>. The OpenAPI document at `/openapi.json` is
generated from the Pydantic schemas, so it can be used to generate a typed
client rather than hand-writing fetch calls.

CORS is already configured for `http://localhost:3000`.

## Two things to know before writing any code here

**Money arrives as a JSON string, not a number.** `"18.00"`, not `18.00`. This
is not an oversight — `18.00` as a JSON number is parsed to float64 as
`17.999999999999996`, and a system that prints shelf prices cannot accept that.
Parse with a decimal library, never `parseFloat`.

**The agent is a separate concern from the UI.** The MCP server at
`backend/mcp_server/` is not called from the browser and has no URL. The
intended architecture is that a server-side agent talks to it over stdio, and
this frontend talks to that agent — the browser never speaks MCP. See the
"three deployment shapes" section of `docs/PLAN.md`, particularly the note about
the agent never being more privileged than the user it acts for.
