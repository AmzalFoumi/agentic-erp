# Frontend

A **Next.js** app for the inventory manager, talking to the FastAPI adapter at `backend/api/`. It is
a client of the API and nothing more — no business rules live here, for the same reason none live in
`backend/api/` or `backend/mcp_server/`.

Nothing is scaffolded yet; that happens at Gate 9. Check `docs/PLAN.md`'s progress table for the
current gate.

## Read these before writing any code here

This file is a **pointer, not a second copy**. Everything that used to be duplicated here is now
recorded once, where it is enforced:

| What | Where |
|---|---|
| Gates 9–13, the API capability inventory, and the **NOT-SUPPORTED list** | `docs/FRONTEND-PLAN.md` |
| Design tokens, density axis, LKR money format, timestamp format | `frontend/DESIGN.md` (from Gate 11) |
| Backend architecture decisions and MCP transport | `docs/BACKEND-PLAN.md` |
| The auth deferral and what ends it | `docs/AUTH-PLAN.md` |
| Live API reference | `uvicorn api.main:app --reload` from `backend/`, then <http://127.0.0.1:8000/docs> |

The **capability inventory** in `docs/FRONTEND-PLAN.md` is the one to read first. It lists what the API
deliberately does *not* support — no delete, no sorting, no reason capture on stock adjustment —
because building against a capability that isn't there is the most likely way to waste a gate.

## The trap that has bitten every layer of this project

**Money arrives as a JSON string, not a number.** `"18.00"`, not `18.00`. This is not an oversight —
`18.00` parsed as float64 is `17.999999999999996`, and a system that prints shelf prices cannot
accept that. Parse with a decimal library, never `parseFloat`, and never hand the value to
`Intl.NumberFormat` with `style: "currency"`.
