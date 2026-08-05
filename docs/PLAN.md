# Supermarket Inventory — build plan

> This is the **permanent, committed** copy of the plan and the **root source of truth**. It is
> updated at the end of every gate to record what was actually built.
>
> It holds what every gate needs and nothing else: the progress table, the context, the rules that
> govern how work proceeds, and the structure as built. Detail lives in three subordinate files —
> where any of them disagrees with this one, **this file wins** and the other is out of date:
>
> | File | Holds | Read when |
> | ---- | ----- | --------- |
> | `docs/BACKEND-PLAN.md` | Gates 0–8 as built, backend decisions and deferrals | Changing backend code |
> | `docs/FRONTEND-PLAN.md` | Gates 9–13, screen and capability inventories, design rationale | Changing frontend code |
> | `docs/AUTH-PLAN.md` | The auth decision, verified provider landscape, the deferral | The auth gate |
> | `docs/AGENT-PLAN.md` | Gates 14-21, the agent flow | Changing Agent Code |
>
> **A decision is recorded once, where it is enforced**; the other files link to it rather than
> restating it. Cross-cutting rules — stop gates, division of labour, verify-against-current-docs —
> are recorded here and referenced there. The progress table below is the single status board for
> the whole project; none of the subordinate files has one.
>
> This file was split out of a single 1,067-line `PLAN.md` on 2026-07-31. Nothing was removed —
> every block moved verbatim into the file that owns it. The reason was cost: 73% of what was
> re-read at the start of every session was finished backend history.

## Progress

| Gate | What                                                                                                                   | Status                                                                                                                                                                             |
| ---- | ---------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0    | Plan, repo, branch, push                                                                                               | ✅ done — commit `4d25463`, pushed to `AmzalFoumi/agentic-erp`, working on `dev`                                                                                                   |
| 1    | Python environment and dependencies                                                                                    | ✅ done — `.venv` at `backend/.venv`, 53 packages installed, `mcp==2.0.0` verified                                                                                                 |
| 2    | Hosted Postgres on Supabase                                                                                            | ✅ done — project `khinbdvubrxqqalejcbp` (eu-west-3), session pooler, `PostgreSQL 17.6` verified from SQLAlchemy; `list_tables` confirms empty `public` schema                     |
| 3    | Models, exceptions, first migration                                                                                    | ✅ done — commit `18545e4`; `products` + `alembic_version` both created and both with RLS enabled, confirmed by `list_tables`; `get_advisors` clean                                |
| 4    | The service layer                                                                                                      | ✅ done — commit `f1da67f`; `services/products.py` (6 functions), 9 tests against the service layer with no HTTP, 3 `import-linter` contracts enforcing the boundary               |
| 5    | Adapter #1: FastAPI                                                                                                    | ✅ done — merged via PR #3; `22 passed` (9 service + 13 API), `lint-imports` 3 contracts kept over 29 files                                                                        |
| 6    | Adapter #2: MCP server                                                                                                 | ✅ done on `feat/mcp/initial`; `31 passed` (9 service + 13 API + 9 MCP), `lint-imports` 3 contracts kept over 37 files, real stdio client attached and `list_products` called live |
| 7    | Docs restructure — persist the frontend plan, `docs/FRONTEND-PLAN.md`, amend two recorded decisions                         | ✅ done — merged to `dev`; docs only, no code                                                                                                                                      |
| 8    | Backend contract closure — `needs_reorder`, `{items,total}`, 422 `fields`, `Literal` error union, settings-driven CORS | ✅ done on `feat/fastapi/contract`; `pytest` green and `lint-imports` 3 contracts kept, both verified by the developer                                                              |
| 8.5  | Docs split — `PLAN.md` reduced to index + shared rules; gates 0–8 to `BACKEND-PLAN.md`, auth to `AUTH-PLAN.md`, `FRONTEND.md` renamed | ✅ done — docs only, no code; every block moved verbatim, nothing removed                                                                                                            |
| 9    | Scaffold Next.js + TypeScript + Tailwind v4 + shadcn/ui in `frontend/`                                                 | ✅ done on `feat/client/web`; next `16.2.12`, react `19.2.4`, tailwindcss `4.3.3`, `src/` layout, shadcn `base-nova` (Base UI, not Radix) — re-scaffolded off a stale-cache v15                                                                                                                                                                     |
| 10   | Typed client from `/openapi.json`, contract-drift check, capability inventory, identity seam                           | ✅ done on `feat/client/web`; `openapi-fetch` + `openapi-typescript`, `schema.d.ts` generated and committed, `api:types:check` drift gate, two ESLint architecture rules, `getCurrentUser()` seam. Its "error envelope is undocumented" finding was **retracted at 12c** — see below |
| 11   | Design tokens — `frontend/DESIGN.md` + `globals.css`, density axis, LKR money format                                   | ✅ done on `feat/client/web`; slots + `data-density` axis + tabular numerals, then real values reconciled in at 12b — Figtree/IBM Plex Mono, accent hue 258, sharp radius, four stock-status tokens |
| 12   | Claude Design — reconcile the generated system, brief, screens. Subgates **12a–12e** in `FRONTEND-PLAN.md`              | ✅ done — **12a** survey, **12b** token reconciliation, **12c** brief done — values landed, Gate 11 closed, two stale records corrected. The brief is a **build artifact, assembled at handoff and never committed**; there is no `docs/DESIGN-BRIEF.md`. **12d**: tokens + fonts pushed back to the design system (`71c6abc`, tokens-only, config in `frontend/.design-sync/`), density axis verified to survive the compile, project created in the org and six screens + agent panel generated (`Inventory.dc.html`), read directly via the DesignSync MCP tool rather than a manual paste-and-review — same review, different mechanism. **12e**: pulled — the read screens are what Gate 13 built from |
| 13   | Handoff — build from the generated screens, extract component kit, wire to the API. Subgates **13a–13h** in `FRONTEND-PLAN.md` | ✅ done — merged to `main` and `dev` at `af3234b`. Order reversed by developer decision 2026-08-05: build first, capability review at 13g. **13a–13f** (shell, list, detail, create/edit, adjust stock, agent panel in its one real state), each committed by the developer. **13g** capability/deviation list written up in `FRONTEND-PLAN.md` — nothing deleted unilaterally. **13h** cleanup done (`dev-tokens/page.tsx` and `src/lib/api/errors.ts` deleted, no importers remained), plus `032c88f` — lint errors resolved, vendor dirs excluded from ESLint, `next-themes` adopted for the light/dark toggle. Frontend gates 9–13 are closed; the agent panel's five unbuilt states wait on the agent service |
| 14   | Agent workstream — write `docs/AGENT-PLAN.md`, record the runtime/model/persistence decisions        | ✅ done — docs only, no code. Runtime **Pydantic AI** over LangGraph (its Python Postgres checkpointer cannot target a non-`public` schema, and `interrupt()` requires a checkpointer) and ADK (2.0 broke the agent API, event model and session schema). Model **Gemini Flash**, free tier — Pro is not free-tier. MCP over **Streamable HTTP bound to `127.0.0.1`**, with the stop condition recorded above. Conversation state in the agent's **own `agent` Postgres schema with its own Alembic**. Resumability deferred; three uncertainty flags carried into Gate 16 |
| 15   | The teaching loop — a bare agent loop, no framework. **Ran; findings kept, code deleted** | ✅ closed 2026-08-06 — built as 15a–15d (`38ac202` for 15a), then **the loop code was deleted by developer decision as not worth maintaining**. What survives: `agent/`'s real infrastructure (own venv, `config.py`, `requirements.txt`, `.env.example`, a second `.gitignore`), one diagnostic at **`agent/scripts/check_mcp.py`** (drives the six MCP tools with no model in the path — the fastest way to tell tool faults from agent faults), and **six findings** written up in `AGENT-PLAN.md` that change gates 16/18/19/21: thought signatures settled (append history as objects, never rebuilt from text; Gate 18 must persist provider-opaque bytes), optional params arrive as `anyOf` and need flattening before Gemini sees them, `FunctionResponse.id` must be echoed or parallel calls mismatch silently, a single response can request **several** tools (so an approval card may show several mutations — unanswered in `FRONTEND-PLAN.md`), and `google-genai` 2.16.0 ships **two** generation APIs with `ai.google.dev` documenting the one we do not use. Also: **async/await arrives here, not Gate 16**, and "under-abstracted" was restated as **flatten the thinking, not the plumbing**. The four comprehension questions move to Gate 16 — the accepted cost of the deletion |
| 16   | Pydantic AI + `MCPToolset` against the running MCP server over Streamable HTTP                        | ⬜ not started — **does not close with any of four flags open**: the Gemini free-tier limits, the `mcp==2.0.0` Streamable HTTP API (the *server* half — a `backend/mcp_server/server.py` change landing in an agent gate, easy to miss), whether `gemini-3.5-flash-lite` chooses tools well enough, and which `google-genai` API surface Pydantic AI's `GoogleModel` drives |
| 17   | The conversation loop with our own boundary types; the `conversation.py` isolation rule + `agent/pyproject.toml` import-linter contract | ⬜ not started |
| 18   | Persistence — `agent/alembic/`, the `agent` schema, RLS. Verification includes confirming backend autogenerate proposes nothing | ⬜ not started |
| 19   | Approval gating on the three mutating tools, at the API level before any UI                          | ⬜ not started |
| 20   | The agent's HTTP surface with SSE streaming, plus the Next proxy route and its ESLint amendment       | ⬜ not started |
| 21   | The frontend panel — build the six unbuilt states specified in `FRONTEND-PLAN.md`                    | ⬜ not started — also revisits the resumability deferral, the first point at which turn duration is observable |

Gates 0–8 are detailed in **`docs/BACKEND-PLAN.md`**, gates 9–13 in **`docs/FRONTEND-PLAN.md`**,
gates 14–21 in **`docs/AGENT-PLAN.md`**.
Numbering stays flat deliberately: a parallel `F0…Fn` sequence would mean "which gate are we on" has
two answers and this table would stop being a status board. Gate 8.5 is numbered that way for the
same reason — renumbering 9–13 to slot it in would invalidate every "Gate 11" reference in
`FRONTEND-PLAN.md` for no gain.

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

> **Amended 2026-07-31 (Gate 7): "frontend deferred" no longer holds.** The backend proved the
> two-adapter thesis through Gate 6, so the frontend is now the active work — gates 9–13, detailed in
> `docs/FRONTEND-PLAN.md`. Two things stay deferred and are _not_ part of it: the **auth provider**
> (see `docs/AUTH-PLAN.md`) and the **agent service** itself. The frontend's job in gates
> 9–13 is to leave clean seams for both, not to implement either.
>
> **Amended 2026-08-05 (close of Gate 13): the frontend gates are done**, merged at `af3234b`, and
> both seams were left as specified — `lib/auth/current-user.ts` for auth, `components/shell/agent-panel.tsx`
> visibly unavailable for the agent. The **agent service is now the active work**, and it is the last
> of the three deferrals to be taken up; the auth provider stays deferred behind it, on the reasoning
> in `docs/AUTH-PLAN.md` that agent identity is the hard half and must be shaped first.

## Authentication: deferred, by decision

**No auth provider is chosen, and `SystemActor` is the only `Actor` implementation.** The full
record — why Supabase is used for Postgres only, why agent identity is the hard half, the verified
comparison of ThunderID / Asgardeo / Keycloak / Auth0, and what the deferral costs — is in
**`docs/AUTH-PLAN.md`**. Do not re-research it; read that file.

Only one part of it belongs here, because it gates further feature work rather than describing a
future gate:

**Two conditions make this deferral expire.** Either one triggers the auth gate before further
feature work:

1. The MCP server becomes reachable over HTTP by anything that is not the developer's own machine.
2. A second human user exists.

Until both are false, `SystemActor` is acceptable _only_ because no unauthenticated caller exists.

**From Gate 16, condition 1 stops being hypothetical.** The MCP server gains a Streamable HTTP run
mode so the agent service can reach it. It binds **`127.0.0.1` only**, and that loopback binding is
the entire basis on which the agent runs unauthenticated. Three things trip condition 1 and trigger
the auth gate **before any further agent work**: changing the bind address to `0.0.0.0` or a LAN
address; placing the server behind a tunnel, reverse proxy, or Docker port publish; or any process on
a second machine successfully calling it. Written as a list rather than a principle because the
dangerous version of this is not a decision but a convenience — "I'll just tunnel it to demo from my
phone" is a thirty-second action that exposes a mutating tool surface with no authentication and no
log entry distinguishing the caller from the developer. Full reasoning in **`docs/AGENT-PLAN.md`**.

---

## Backend debt owed after the frontend gates

Kept here, in the always-read file, because it is work created by one half of the project and paid by
the other — the kind of item that is otherwise only remembered by whoever wrote it.

### ~~Document the error envelope as a Pydantic model~~ — **already done. Retracted 2026-08-04**

Gate 10 recorded that `api/errors.py` returns raw `JSONResponse` dicts, so `{error, detail, fields?}`
never reaches `/openapi.json`, and shipped `frontend/src/lib/api/errors.ts` as a hand-written
stopgap. **That finding was wrong**, and it was wrong when it was written: `ErrorResponse` is
declared in `backend/api/schemas.py`, attached to every route through `_errors(...)` in
`backend/api/routes/products.py`, asserted by `test_api_products.py`, and already present in the
committed `frontend/src/lib/api/schema.d.ts` — `fields` included. All of it landed in Gate 8's commit
`0c8c97e`, two gates before it was reported missing.

The lesson is the standing verify-docs rule turned inward: the claim was carried forward from an
earlier reading of the backend rather than re-checked against the file, which is exactly the mistake
the rule exists to prevent, aimed at our own code instead of a third party's.

**What was actually owed, and it was small and frontend-only:** delete
`frontend/src/lib/api/errors.ts` and use the generated `ErrorResponse` instead. Nothing imported the
stopgap, so it was a deletion, not a migration. No backend gate.

**Done at Gate 13h (2026-08-05).** `errors.ts` is gone; the generated `ErrorResponse` is what
`lib/api-error.ts`'s `mapApiError` and every error-state screen read. This item is closed.

### Stock states: three of four are backed today

`reorder_level` **exists** — a non-nullable integer on `Product`, settable on create and PATCH, and
the backend already ships the computed `needs_reorder` on every product response. An earlier note
here claimed the field was missing and scoped a migration for it; that was wrong for the same reason
as the entry above.

So the mapping is: `stock-out` is `quantity_on_hand == 0`, `stock-low` is `needs_reorder`, `stock-ok`
is neither. **Only `stock-over` has nothing behind it** — that needs a per-product maximum, which
genuinely does not exist.

That one is deferred rather than built: overstock is a real concern for a supermarket, but it is a
second threshold that every product would need populated to be useful, and no screen has yet
demonstrated it is worth the column. The `stock-over` token stays defined and unused, so the gap is
visible in the code rather than forgotten. The revisit was scheduled for after Gate 13, when real
screens could say whether anyone would look at it.

**Checked at the close of Gate 13 (2026-08-05): still deferred.** All six screens shipped and the
13g capability/deviation list does not raise overstock — no screen asked for the threshold while
being built. That is weak evidence rather than a verdict, so the token stays defined and unused and
the question moves to the next gate that touches product data.

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

**The developer runs every command that controls the toolchain or the repository.** The agent
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

### Extended 2026-07-31 (Gate 7): the Node half

The rule above was written when the only toolchain was Python — the opening line said "controls
**Python** itself", now generalised. From Gate 9 the frontend adds a second toolchain, run from
`frontend/`, **not** `backend/`. Same principle, same split:

| Python                      | Node equivalent (run from `frontend/`)         |
| --------------------------- | ---------------------------------------------- |
| venv create / activate      | `npm ci`, `npm install`                        |
| `pip install`, `pip freeze` | `npm install <pkg>`, any lockfile change       |
| `pytest`                    | `npm test`, `npx tsc --noEmit`, `npm run lint` |
| `uvicorn ...`               | `npm run dev`, `npm run build`                 |
| `alembic revision`          | `npm run api:types` (contract codegen)         |
| `git` / `gh`                | unchanged — developer-run                      |

Three cases the original rule does not cover, resolved explicitly because otherwise Gate 9 has no
owner:

- **Generators both run a command and write source.** `create-next-app`, `shadcn add`,
  `openapi-typescript` are all "developer runs commands" _and_ "agent writes files" at once. Rule:
  **the developer runs the generator; the agent edits the generated output afterward.**
- **Generated code is build output, not source.** `frontend/src/lib/api/schema.d.ts` is committed — so
  contract drift shows up as a reviewable diff — but is **never hand-edited** by either party. If it
  is wrong, the backend schema is wrong; fix that and regenerate.
- **Verification needs two servers running.** From Gate 13, checking a screen needs `uvicorn` _and_
  `npm run dev`, and the agent may start neither. Ritual: **the developer starts both and says
  continue; only then may the agent use browser MCP tools** (chrome-devtools / playwright). Without
  this the agent will guess at whether the UI works, which is exactly what those tools exist to avoid.

---

## Standing rule: verify against current docs at every gate

At the start of each gate, fetch current documentation and released versions rather than relying on
the agent's training data. Gate 6 is the proof: the MCP spec and SDK both changed within 24
hours of the work, and five of nine version pins written from memory were wrong before being
checked against PyPI.

---

## Structure — as actually built (refreshed 2026-08-05 at close of Gate 13; `agent/` added 2026-08-06 at Gate 15a)

```
agentic-erp/
├── .gitignore, README.md
├── .editorconfig, .gitattributes, .prettierrc, .prettierignore
├── CLAUDE.md                      # agent onboarding; a summary of these docs, not a rival to them
├── docs/PLAN.md                   # the root source of truth: gates, shared rules, structure
├── docs/BACKEND-PLAN.md           # gates 0-8 as built; subordinate to PLAN.md
├── docs/FRONTEND-PLAN.md          # gates 9-13; subordinate to PLAN.md
├── docs/AUTH-PLAN.md              # the auth decision and deferral; subordinate to PLAN.md
├── backend/
│   ├── .env (gitignored), .env.example, requirements.txt, pyproject.toml
│   ├── alembic.ini, alembic/versions/   # 2 migrations: create products, RLS on alembic_version
│   ├── core/        config.py  database.py  models.py  exceptions.py  actor.py
│   ├── services/    products.py  +  inventory.py  suppliers.py  purchasing.py (stubs)
│   ├── api/         main.py  schemas.py  deps.py  errors.py  routes/products.py
│   ├── mcp_server/  server.py  errors.py
│   └── tests/       conftest.py  test_products.py  test_api_products.py  test_mcp_products.py
├── agent/                          # the agent service — started Gate 15a, its OWN venv
│   ├── .env (gitignored), .env.example, .gitignore, requirements.txt
│   │                               # second .gitignore is deliberate: two layers must both
│   │                               # fail before an API key escapes
│   ├── config.py                   # BaseSettings, mirrors backend/core/config.py. A COPY,
│   │                               # not an import — importing backend/ would cross the
│   │                               # venv boundary the MCP-only rule exists to hold
│   └── scripts/check_mcp.py        # diagnostic: drives the MCP tools with NO model in the
│                                    # path. Gate 15's loop code was deleted; this survived
└── frontend/                       # Next.js 16, src/ layout — scaffolded Gate 9, built out 9-13
    ├── .env.example, package.json, next.config.ts, eslint.config.mjs, components.json
    ├── DESIGN.md                   # the token contract; THIRD-PARTY.md, AGENTS.md, CLAUDE.md alongside
    ├── .design-sync/               # Claude Design push config (tokens + fonts only)
    └── src/
        ├── app/         layout.tsx  globals.css  products/{list,[id],[id]/edit,[id]/adjust-stock,new}
        │                            # each route: page.tsx + actions.ts + _components/ for its own parts
        ├── components/  ui/        # shadcn primitives, developer-generated
        │                domain/    # extracted from the built screens: stock-badge, money-display,
        │                           # form-field, api-error-state
        │                shell/     # nav, density-toggle, theme-toggle/-provider, agent-panel
        └── lib/         api/client.ts  api/schema.d.ts (generated, never hand-edited)
                         api-error.ts  format.ts  auth/current-user.ts (the identity seam)
```

Four files exist that the original sketch did not anticipate, each for a reason recorded in
`docs/BACKEND-PLAN.md`: `core/actor.py` (identity as a parameter, so `services/` never learns what a
request is); `api/deps.py` (the DI seam, and the one place a real auth provider will land); and the
matched pair `api/errors.py` / `mcp_server/errors.py` — one vocabulary in `core/exceptions.py`, two
dialects. `pyproject.toml` holds pytest and import-linter config only; dependencies stay in
`requirements.txt` (see the deferred note under Gate 1 in `docs/BACKEND-PLAN.md`).

On the frontend side, three directories carry the rules rather than just the code. `components/ui/`
is generated and treated as vendor — excluded from ESLint since `032c88f`. `components/domain/` was
extracted _from_ the built screens rather than designed ahead of them, per Gate 13. And `lib/api/` is
the only tree permitted to import the generated client or call `fetch`, which is the frontend's
equivalent of `lint-imports` and is enforced by ESLint `no-restricted-imports`. `lib/auth/current-user.ts`
is the third identity seam, hardcoded to `"system"` to match `SystemActor` — see `docs/AUTH-PLAN.md`.

Note: the original sketch had `services/inventory.py` as the main file. `products.py` is the slice-1
entity because inventory movements need products to exist first; `inventory.py` remains a stub for
stock movements and adjustment history.
