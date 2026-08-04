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
| 10   | Typed client from `/openapi.json`, contract-drift check, capability inventory, identity seam                           | ✅ done on `feat/client/web`; `openapi-fetch` + `openapi-typescript`, `schema.d.ts` generated and committed, `api:types:check` drift gate, two ESLint architecture rules, `getCurrentUser()` seam. Error envelope hand-written — backend debt recorded below |
| 11   | Design tokens — `frontend/DESIGN.md` + `globals.css`, density axis, LKR money format                                   | ✅ done on `feat/client/web`; slots + `data-density` axis + tabular numerals, then real values reconciled in at 12b — Figtree/IBM Plex Mono, accent hue 258, sharp radius, four stock-status tokens |
| 12   | Claude Design — reconcile the generated system, brief, screens. Subgates **12a–12e** in `FRONTEND-PLAN.md`              | 🟡 flow ran design→code, so this gate is a **reconciliation**. **12a** survey and **12b** token reconciliation done — values landed, Gate 11 closed. Next: **12c** the brief. Handed-back project is type `PROJECT_TYPE_PROJECT`, so 12d needs a new design-system project |
| 13   | Handoff — capability audit, extract component kit, wire screens to the API                                             | ⬜ not started                                                                                                                                                                     |

Gates 0–8 are detailed in **`docs/BACKEND-PLAN.md`**, gates 9–13 in **`docs/FRONTEND-PLAN.md`**.
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

---

## Backend debt owed after the frontend gates

Kept here, in the always-read file, because it is work created by one half of the project and paid by
the other — the kind of item that is otherwise only remembered by whoever wrote it.

**Document the error envelope as a Pydantic model (`ErrorResponse`) in `backend/api/`.** Discovered
at Gate 10: `api/errors.py` builds error responses as raw `JSONResponse` dicts, so the
`{error, detail, fields?}` shape never reaches `/openapi.json` and the typed frontend client cannot
generate it. The stopgap is `frontend/src/lib/api/errors.ts` — the one hand-written file in an
otherwise fully generated `src/lib/api`, and therefore the one place the frontend restates the
backend from memory.

**Do it after Gate 13, before further feature work on either side.** The full four-step fix, and the
reason it was not done inside Gate 10, are in `docs/FRONTEND-PLAN.md` under Gate 10. Completion is
unambiguous: `frontend/src/lib/api/errors.ts` gets deleted.

**Add a per-product reorder level (and maximum) to `Product`.** Surfaced at Gate 12a: the design
system defines four stock states — ok, low, out, over — but the API has no threshold field, so "low"
and "over" are currently uncomputable. The imported design papered over this with a hardcoded
`qty <= 12` in a stylesheet, which would apply the same threshold to milk and to rice.

Scope: two nullable integer columns on `Product`, a migration, exposure through the existing
read/update endpoints, and the same field on the MCP tool so the agent can set it. Nullable because
most products will not have one, and a product without a reorder level simply has no low state rather
than a default one.

**This is a real feature, not debt** — it is design running ahead of the API, decided deliberately at
Gate 12 rather than discovered at Gate 13. Until it lands the frontend renders only `stock-ok` and
`stock-out`; the two unused tokens stay defined so the gap is visible in the code rather than
forgotten. Sequence it with the `ErrorResponse` work above, after Gate 13.

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

## Structure — as actually built (refreshed 2026-07-31, Gate 7)

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
└── frontend/        README.md     # pointer only until Gate 9 scaffolds Next.js here
```

Four files exist that the original sketch did not anticipate, each for a reason recorded in
`docs/BACKEND-PLAN.md`: `core/actor.py` (identity as a parameter, so `services/` never learns what a
request is); `api/deps.py` (the DI seam, and the one place a real auth provider will land); and the
matched pair `api/errors.py` / `mcp_server/errors.py` — one vocabulary in `core/exceptions.py`, two
dialects. `pyproject.toml` holds pytest and import-linter config only; dependencies stay in
`requirements.txt` (see the deferred note under Gate 1 in `docs/BACKEND-PLAN.md`).

Note: the original sketch had `services/inventory.py` as the main file. `products.py` is the slice-1
entity because inventory movements need products to exist first; `inventory.py` remains a stub for
stock movements and adjustment history.
