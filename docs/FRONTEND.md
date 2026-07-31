# Frontend — build plan

> **Subordinate to `docs/PLAN.md`.** This file is detail under `PLAN.md`'s gates 7–13; where the two
> disagree, **`PLAN.md` wins** and this file is the thing that is out of date. Cross-cutting rules
> (stop gates, division of labour, verify-against-current-docs, the auth decision) live in `PLAN.md`
> and are referenced here, never restated. There is **no progress table here** — `PLAN.md`'s table is
> the single status board for the whole project.

## Why this file exists (2026-07-31)

`PLAN.md` reached 850 lines recording the backend, and it earned that length. The frontend needs the
same treatment — screen inventory, capability inventory, design-system rationale, per-gate outcomes —
but appending it to `PLAN.md` would bury the backend history and make the file unnavigable.

The split rule, decided at Gate 7: **a decision is recorded once, where it is enforced; the other
file links to it.** The auth decision is enforced in `backend/api/deps.py` and
`backend/mcp_server/server.py`, so it stays in `PLAN.md` and this file links to it. The money display
format is enforced in `frontend/DESIGN.md`, so it lives there and this file links to it. Two
drifting accounts of the same decision is the failure mode this rule exists to prevent.

---

## Decision: the frontend is a client, and nothing more (2026-07-31)

The backend's credibility comes from one mechanical rule — `services/` never imports from `api/` or
`mcp_server/`, enforced by `import-linter`, not by good intentions. The frontend gets the equivalent
treatment or it will drift.

**Two rules, both mechanical (ESLint `no-restricted-imports`), landing in Gate 10:**

1. **Only `lib/api/**` may import the generated client or call `fetch`.** Everything else goes
   through that module. This is the frontend restatement of "the UI is a client of the API and
   nothing more".
2. **No `app/api/**` route handlers mirroring FastAPI endpoints.** A Next route handler that proxies
   `/products` to FastAPI is a *third adapter* — the same category of mistake as `services/`
   importing `api/`, and forbidden for the same reason. React Server Components call FastAPI
   directly; Next's own documentation calls the mirror layer an anti-pattern.

**Standing rule: no business logic in `frontend/`.** Any server-side Next code is transport only. The
concrete test: if a rule would give a different answer in the MCP adapter than in the UI, it belongs
in `services/`, not here. `needs_reorder` is the worked example — see Gate 8.

### Data fetching: RSC by default

Server Components are the Next.js App Router default; an `async` page that awaits a `fetch` is the
least-code path. Client-side fetching is what costs extra — a React Query/SWR dependency,
`'use client'` boundaries, hand-rolled loading state, and CORS staying load-bearing.

Reads happen in Server Components. Mutations go through Server Actions. The API base URL is a
server-side value and never reaches the browser.

Note this is **not** an argument from auth. A confidential OAuth client needs *a* trusted server, not
specifically a JavaScript one, and `backend/` is already a server. See "Identity seam" below.

---

## Identity seam: reserved, not implemented (2026-07-31)

Nothing in gates 7–13 implements authentication. No provider is chosen, no login screen is built, no
token is issued or validated. The full reasoning, the verified provider landscape, and the two
conditions that make the deferral expire are recorded in **`PLAN.md`'s "Decision: authentication"
section** — read it there, it is not duplicated here.

What lands in this codebase, at Gate 10:

`frontend/lib/auth/current-user.ts` — a single module returning the current caller, today hardcoding
`"system"` to match the backend's `SystemActor`. All data access goes through it. This mirrors
exactly what `backend/core/actor.py` did for the backend: identity is a parameter, obtained in one
place, so adopting a provider later changes one file rather than every call site.

When auth arrives, this is where the user's token is obtained. **The confidential client that
performs the RFC 8693 token exchange for agent calls will most likely be Python**, alongside the
agent service — not Next. The Next tier stays thin.

### The agent is a remote service, not an in-process loop

`PLAN.md`'s original "Shape A" sketch put the agent loop inside Next.js. **That assumption is
dropped** (see `PLAN.md`'s amended transport decision). The agent is its own implementation, deferred,
and reached over HTTP.

The only thing this plan does about it: `frontend/.env.example` reserves `API_BASE_URL` **and**
`AGENT_BASE_URL` as separate server-side values — no `NEXT_PUBLIC_` prefix, so neither reaches the
browser. Nothing else in the frontend learns how either is reached, and the Gate 12 design brief
reserves an unpopulated region in the app shell so adding a chat surface later is not a layout
rewrite.

---

## Gate 9 — Scaffold

Versions verified against the npm registry **2026-07-31**. Per `PLAN.md`'s standing rule, re-verify
at gate start rather than trusting this table.

| Package | Version |
|---|---|
| Next.js | 16.2.12 |
| React | 19.2.8 |
| Tailwind CSS | 4.3.3 |
| openapi-typescript | 7.13.0 |
| Node / npm (installed) | 22.16.0 / 11.6.2 |

`create-next-app` with App Router, TypeScript, Tailwind, ESLint; then `shadcn init`. Next still needs
a thin `postcss.config.mjs` with `@tailwindcss/postcss` — Tailwind v4's zero-config story is Vite-only.

Note `.gitignore`'s `.env.*` rule swallows any env example not named exactly `.env.example`.

---

## Gate 10 — Typed client and capability inventory

**Typed client.** `openapi-typescript` + `openapi-fetch`, generated from FastAPI's `/openapi.json`
into `frontend/lib/api/schema.d.ts` via `npm run api:types`.

`schema.d.ts` is **build output**: committed, so contract drift shows up as a reviewable diff, but
never hand-edited. If it is wrong, the backend schema is wrong — fix that.

**Contract-drift check — the frontend's `lint-imports` equivalent.** Regenerate types against a
running backend and fail if the committed file differs. This is the mechanism that catches a backend
change silently breaking the UI, and it is the reason the frontend can claim the same kind of
structural guarantee the backend has.

### API capability inventory

Derived mechanically from `/openapi.json`, not from memory. **Both halves matter equally** — the
second exists because an unconstrained design tool will draw plausible, unbuildable affordances.

**Supported today:**

| Endpoint | Notes |
|---|---|
| `GET /products` | `search` (case-insensitive substring over name **or** sku), `limit` 1–200 default 50, `offset` |
| `POST /products` | 201 on success |
| `GET /products/by-sku/{sku}` | SKU is normalised `.strip().upper()` server-side, so lookup is case-insensitive |
| `GET /products/{id}` | |
| `PATCH /products/{id}` | `sku` and `quantity_on_hand` are deliberately not updatable here |
| `POST /products/{id}/adjust-stock` | signed `delta`; zero is rejected; cannot go below zero |
| `GET /health` | |

Sort is fixed to `id DESC` and is not configurable.

**NOT supported — do not design:**

no delete or archive · no sorting UI · no bulk operations · no auth, users, avatars, or sign-out ·
no images or thumbnails · no suppliers, purchase orders, or categories-as-entities · no stock
history · no reason capture on stock adjustment (the field is accepted then discarded — see below) ·
single currency · no multi-warehouse · `category` cannot be cleared once set · **no agent/chat
surface yet**.

Two of these deserve their reasoning recorded, because they will be asked about repeatedly:

- **Delete.** Deleting an inventory row is the wrong feature — it will be referenced by stock history
  that does not exist yet but will. The right feature is soft-delete/archive (`is_active`), which
  needs a migration, a service function, a `list_products` filter, and an MCP tool. That is a real
  backend gate, not something to smuggle into frontend work.
- **Stock adjustment `reason`.** `services/products.py` accepts it and discards it, deliberately.
  Therefore **the adjust-stock form must not have a reason input.** Shipping an input whose value
  goes nowhere is worse than omitting it: it produces users who believe there is an audit trail.
  Capturing it properly means a stock-movement ledger — again, a backend gate.

---

## Gate 11 — Design tokens

Two artifacts with one strict anti-drift rule:

> **`frontend/app/globals.css`'s `@theme` block is the only place a value exists.
> `frontend/DESIGN.md` names tokens and explains rationale but never restates a hex, rem, or ratio.**

Two files that must agree by hand is a drift machine — the same mistake at file level that this
project avoids at the code level.

**Token architecture.** Tailwind v4 CSS-first config: `@theme inline` mapping semantic tokens onto
`:root` / `.dark` custom properties in OKLCH, per current shadcn Tailwind v4 guidance.

**Density is a first-class axis, not a later addition.** `data-density="dense" | "comfortable"` on
`<html>` overrides spacing and row-height tokens, composing with `.dark` exactly as shadcn's theming
already does. Components reference tokens and never hardcode padding. Dense is the default — this is
an operational tool for someone scanning hundreds of rows, not a marketing page — and the toggle is
user-facing. Retrofitting this would mean touching every component, which is why it goes in at
authoring time.

Money and quantity columns use tabular numerals.

**Palette and type are chosen by the developer in the Claude Design UI, not invented by the agent.**
The named failure mode is the generic AI aesthetic — the same gradients and the same rounded cards
every recent site has. Sequence: the agent defines the token *slots*; the developer browses themes
and styles in Claude Design; the chosen values are synced down into `globals.css`.

### Two formatting decisions, recorded once in `DESIGN.md`

**Money — LKR.** ISO 4217 `LKR`, numeric 144, 2 decimal places. Display as `Rs 1,250.00` with `en-LK`
grouping. Cents are effectively out of circulation in Sri Lanka, but the column is `Numeric(10,2)`, so
**display two decimals anyway** — an ERP that hides cents while storing them produces on-screen totals
that do not add up.

> **Hard rule: never use `Intl.NumberFormat` with `style: "currency"` on a `number`.** That requires
> `parseFloat` on the wire string and reintroduces exactly the float64 precision bug the string
> encoding exists to prevent (`18.00` → `17.999999999999996`). Format the string directly or use a
> decimal library. See `PLAN.md`'s money-as-string rationale and `backend/api/schemas.py`'s comment.

**Timestamps** are `TIMESTAMPTZ`. Display timezone and format are decided once in `DESIGN.md`;
otherwise four implementations appear.

Gate 11 ships **primitives only** — shadcn defaults bound to tokens. No domain components
(`MoneyDisplay`, `StockBadge`, `ErrorSurface`) yet: those are opinions about screens that do not
exist, and pre-empting them means reconciling two component kits at Gate 13.

---

## Gate 12 — Claude Design

`/design-sync` requires Claude Code ≥ 2.1.181 (2.1.197 installed at time of writing). It is
**bidirectional** — push sends local tokens and primitives up so generated screens use real
components rather than placeholders; pull brings canvas work back down. Work can therefore continue
in the Claude Design web UI or in Claude Code; neither surface is a dead end.

**The brief's centerpiece is the NOT-SUPPORTED list above**, stated as loudly as the supported half.
Left unconstrained, a design tool will produce page-number pagination, per-row trash icons, sortable
column headers, bulk-select bars, product thumbnails, a supplier column, and a user avatar menu with
sign-out. Most of those look plausible and every one of them is unbuildable today.

Also required in the brief:

- **Fixtures from the real schema** — money as strings, `category` nullable, `created_by` as the
  literal `"system"` (design for that ugly string; it is what `SystemActor` actually writes), ISO
  `TIMESTAMPTZ` timestamps. Not `"Sarah Chen"`.
- **A fixed screen list with allowed affordances per screen**, not "design an inventory app". Open
  briefs produce a Figma-grade app for an API with six endpoints.
- **Mandatory non-happy-path states**: empty list, loading, search-returned-nothing, and one state
  per real error code. Generated designs default to happy-path only, and those states then get
  invented ad hoc during the build.

---

## Gate 13 — Handoff and build

**Capability audit first, before a line of TSX.** Every interactive element in the handoff bundle
maps to a real endpoint, or it is deleted from the design. Anything genuinely wanted becomes a new
backend gate.

Explicitly forbidden: shipping a disabled button with `// TODO: no endpoint yet`. That permanently
moves the design's problems into the codebase, where they stop being visible as design decisions.

Then: extract the domain component kit *from* the generated screens rather than reconciling against a
pre-built one; wire to the typed client; RSC for reads, Server Actions for mutations. Component tests
run against MSW handlers typed from the generated schema, so fixtures cannot drift from the contract
either.

---

## Deferred, as decisions rather than oversights

Soft-delete / archive · a sort parameter · clearing `category` back to NULL · a stock-movement ledger
so adjustment `reason` is stored · **auth provider** (see `PLAN.md`) · **MCP Streamable HTTP transport
and its OAuth resource-server stack** (see `PLAN.md`) · **the agent service itself** · deployment
shape, production origin, and therefore the real `CORS_ORIGINS` and `API_BASE_URL` values.
