@AGENTS.md

## Commands — note the working directory

These run from `frontend/`, not `backend/`. Available from Gate 9 onward:

```bash
npm run dev                # Next.js dev server -> http://localhost:3000
npm run build              # production build
npx tsc --noEmit           # type check (the frontend's "pytest" half)
npm run lint               # ESLint, incl. the restricted-import architecture rules
npm run api:types          # regenerate src/lib/api/schema.d.ts from FastAPI's /openapi.json
```

Scaffolded at Gate 9 on **Next 16** with the `src/` layout, so source is `frontend/src/...`. Two v16
consequences: Turbopack is the default (no `--turbopack` flag), and `next lint` is removed, so
`npm run lint` calls `eslint` directly. `api:types` and the restricted-import rules land at Gate 10 —
check `docs/PLAN.md`'s progress table before assuming any of the above runs.

## The frontend is a client of the API and nothing more

No business logic, and any server-side Next code is transport only. Two rules enforced by ESLint
`no-restricted-imports`, the frontend's answer to `lint-imports`: only the `src/lib/api` tree may
import the generated client or call `fetch`; and no `app/api` handlers mirroring FastAPI — that
would be a *third adapter*, the same mistake as `services/` importing `api/`. React Server
Components call FastAPI directly. Detail in `docs/FRONTEND-PLAN.md`.

`src/lib/api/schema.d.ts` is **build output — committed but never hand-edited**; regenerate it with
`npm run api:types`.
