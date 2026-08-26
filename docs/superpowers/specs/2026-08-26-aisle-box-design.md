> **Standing: disposable scaffolding.** This is the design agreed on 2026-08-26 for gate 26,
> committed before any code so it survives a lost session. It is **subordinate to `docs/PLAN.md`
> and `docs/DEPLOY-PLAN.md`** — where it disagrees with them, they are right and this file is the
> stale copy. It is not updated as work proceeds; sub-gate 26h folds the surviving decisions into
> `docs/DEPLOY-PLAN.md`, which is the permanent record.

# Gate 26 — "Aisle in a box"

## Context

Aisle is being submitted to the Ascentic AI Launch Pad on **Saturday 29 August 2026, 5pm**. A
deployed public link is explicitly optional and supporting files are allowed, so the decision taken
is **no hosting** — judges receive a self-contained box they run with one command.

Five services must run together: the Next.js website, the FastAPI web API, the MCP server, the AI
agent service, and **ThunderID** (the login server — it has no hosted option, so we ship it).
There are currently **zero Dockerfiles** in the repo.

Two throwaway spikes are already done; findings are in
`.claude/problems/thunderid-import-aborts-on-first-error.md`:

- ThunderID's export/import wizard is **not shippable to a judge** — eight steps, four hand-pasted
  secrets, and it aborts on the first error while reporting "Valid / 43 of 43".
- Shipping a **pre-configured SQLite database** works. Seeding the volume from already-imported
  `.db` files and running `setup.sh` on top left every role, resource server and permission grant
  intact while still generating that machine's own keys. Console login succeeded end to end.

All work happens on `build/aisle-box`, in a new `deploy/aisle-box/` folder. Nothing that exists
under `deploy/` today is modified, and the live `thunderid-local` volumes are never touched.

### Decisions taken by the developer (2026-08-26)

| Question | Answer |
|---|---|
| ERP database | **Shared hosted Supabase** — not a Postgres container |
| Gemini API key | **Judge supplies their own**; app works without it, only AI chat is off |
| Image distribution | **Built on the judge's machine** by `docker compose up --build` — no registry |
| Credentials | Delivered as a **submission supporting file**, never committed |
| Fallback demo mode | **Documented, not built** |

**Recorded concern on the Supabase choice, raised once and overruled — proceeding as asked.**
Every judge writes to the same live data, and the demo needs internet. Reduced without changing the
decision: a **dedicated least-privilege Postgres role**, and a revocation step after judging.
Switching to a local Postgres container later is a one-line `DATABASE_URL` change, no code moves.

---

## Facts established during planning (verified, not assumed)

1. **The self-signed certificate is issued for `localhost` and `127.0.0.1` only** —
   `openssl x509` on `deploy/thunderid-server.cert`: `CN=localhost`,
   `SAN: DNS:localhost, IP:127.0.0.1`.
2. **`@thunderid/nextjs` exposes exactly one base-URL setting.** Scanning the SDK's dist for env
   names yields a single `THUNDERID_BASE_URL`, used by both browser redirects and server-side token
   exchange — and `NEXT_PUBLIC_*` is inlined at build time. It cannot be two addresses at once.
3. **The repo is public** (`gh repo view` → `"visibility":"PUBLIC"`).
4. **Every ThunderID secret is stored as a PBKDF2 hash, never plaintext.** In `entitydb.db`'s
   `ENTITY.SYSTEM_CREDENTIALS`: `clientSecret`, `flowSecret` and user `password` all carry
   `{"storageAlgo":"PBKDF2","storageAlgoParams":{"Iterations":600000,"KeySize":32,"Salt":"…"}}`.
   `OAUTH_INBOUND_PROFILE.OAUTH_CONFIG` holds no secret at all. **This also removes a technical
   risk:** nothing there is encrypted with `crypto.key`, so `setup.sh` minting a fresh `crypto.key`
   on the judge's machine cannot break client-secret verification.
5. **Supabase free plan permits creating Postgres roles** — plain SQL, no plan gate; the free-plan
   member limit is about organization seats, a different thing. Limits that do apply: 500 MB
   database, 5 GB egress, and **projects pause after ~7 days of low activity**.
6. **Next.js `output: "standalone"` is the supported Docker path**, confirmed in the vendored docs
   at `frontend/node_modules/next/dist/docs/.../05-config/01-next-config-js/output.md`.

---

## The design in one paragraph

Six long-running containers plus two one-shot init containers, in one Compose file with project
name `aisle-box`. **Every container shares a single network namespace**, so the box's internal
addressing is byte-identical to the developer's machine: ThunderID on `localhost:8090`, API on
`localhost:8000`, MCP on `localhost:8001`, agent on `localhost:8002`, website on `localhost:3000`.
Only **3000 and 8090** are published. ThunderID starts from a **pre-configured database committed
to the repo**, so the judge never sees the import wizard and signs in as a ready-made `judge`
account. Credentials arrive as a separate file they drop next to the compose file.

### Why the shared network namespace

Facts 1 and 2 above mean a conventional service-DNS layout would force one baked-in string to be
two different addresses at once. Sharing a namespace makes `https://localhost:8090` correct for the
browser, for the bundle, for server-side code, and for the `iss` claim simultaneously — and the TLS
hostname then matches, so certificate verification can stay **on**.

A dedicated tiny **anchor container** owns the namespace (not ThunderID), so a ThunderID restart
does not tear the network out from under the other five.

**This also means the agent never gets a published port.** `agent/app.py`'s `HOST = "127.0.0.1"`
stays exactly as written and the stop condition in `docs/AGENT-PLAN.md` is not tripped. **B1 is
therefore not a blocker for the box** — it stays required before any real hosting.

**Documented fallback if the namespace approach misbehaves:** a `socat` TCP forwarder inside each
app container mapping `127.0.0.1:8090 → thunderid:8090`. Same result, one extra binary per image.

### The credential rule

**No plaintext credential is committed to the public repo.** The hashed ThunderID database is
committed (fact 4 — nothing recoverable in it). Everything plaintext — box client secrets,
`THUNDERID_SECRET`, and the Supabase connection string — ships as a **submission supporting file**
named `aisle.env`. Compose already reads a file called `.env` next to the compose file, so the
judge copies `aisle.env` → `deploy/aisle-box/.env` and pastes their Gemini key into its one blank
line. No mount arguments, no editing beyond that line.

---

## Sub-gates

Each ends the normal way: stop, explain, list files, hand off. Commits are permitted on this branch
for this work.

### Step 0 (before 26a) — Persist this plan into the repo

Copy this plan file verbatim to **`docs/superpowers/specs/2026-08-26-aisle-box-design.md`** and
commit it as the first commit on `build/aisle-box`, before any code. It survives a lost session and
gives every later sub-gate something to check itself against.

Its standing is explicit in the file's own header: **disposable scaffolding, subordinate to
`docs/PLAN.md` and `docs/DEPLOY-PLAN.md`.** Where it disagrees with them after 26h, they win and
this is the stale copy. It is not updated as work proceeds — 26h folds the surviving decisions into
`DEPLOY-PLAN.md`, which is the permanent record.

### 26a — Box skeleton

New `deploy/aisle-box/`: `docker-compose.yml` (project name `aisle-box`), a copy of
`thunderid-deployment.yaml` **without** the `oauth.dcr.insecure: true` block, and `.env.example`.
Reuses the pinned image and digest from
[deploy/docker-compose.thunderid.yml](deploy/docker-compose.thunderid.yml).

Fixes the bug spike 1 exposed: `thunderid-db-init`'s reseed guard fails on a genuinely fresh
machine, because Docker pre-populates a new named volume from the image at container *creation*.
The box uses a seed step correct on first run; the dev file is left alone.

**Verify:** `docker compose -f deploy/aisle-box/docker-compose.yml up -d` creates `aisle-box_*`
volumes; `docker volume ls` shows `thunderid-local_*` unchanged.

### 26b — Service images

- `backend/Dockerfile` — **one image, two containers.** API and MCP server are the same code tree
  and the same `requirements.txt`; only the command differs (`uvicorn api.main:app` vs
  `python -m mcp_server.server --transport streamable-http`). Two images would duplicate build time
  for nothing.
- `agent/Dockerfile` — separate image; `agent/` has its own venv and `requirements.txt`
  (`pydantic-ai-slim`, `httpx2`), deliberately not shared with the backend.
- `frontend/Dockerfile` — multi-stage on `output: "standalone"`; `NEXT_PUBLIC_*` passed as build
  args because they are inlined at build time.
- One `.dockerignore` per service.
- One-line change to [frontend/next.config.ts](frontend/next.config.ts) adding
  `output: "standalone"`. Does not affect `next dev`.

**Verify:** all three build; `GET /openapi.json` answers from the API container; the MCP container
serves `/mcp`; the agent container starts.

### 26c — Identity baked in

Regenerate the pre-configured ThunderID database **cleanly, at port 8090**, in a throwaway stack —
the spike's copy was rewritten to 8091 with DCR stripped, so it is evidence, not an artefact. It
must contain:

- both resource servers (`https://api.agentic-erp.local`, `https://mcp.agentic-erp.local`), all
  three roles, and the twelve permission grants on `AIsle Full Access`
- **fresh box-only client secrets** — the developer's real secrets never ship
- a **`judge` user with a documented password** and `AIsle Full Access`. Imported users arrive with
  empty credentials, so the password is set through the Console during *our* build run and captured
  into the seed; `setup.sh` only resets `admin`, so it survives. The judge never needs the admin
  account or the Console.
- **pruned:** the developer's personal user and email, `probe`, `Test Agent`,
  `Claude Code (thunderid-mcp)`, and the stale `http://localhost:9999/callback` client. Note that
  removing `Test Agent` also removes a `Product Reader` assignment.

**Self-signup, investigated here.** A self-registered user lands with **no role**, which in Aisle
means every screen 403s — worse than no signup. So registration is **off by default**; if ThunderID
turns out to support auto-assigning a role on registration, enable it as a bonus path. Either way
the `judge` account remains the guaranteed route.

**Pre-commit scan:** run a plaintext/high-entropy scan over the four `.db` files and confirm they
contain only PBKDF2 hashes before they are committed (~800 KB total, under
`deploy/aisle-box/thunderid-seed/`).

**Verify:** fresh volume → seed → `setup.sh` → sign in as `judge` in a browser; confirm an RFC 8693
exchange returns a token with a **non-empty** `scope`. (Gate 23's warning: a `200 OK` with no
`scope` claim means zero permissions, never "allow".)

### 26d — Wiring and TLS trust

Anchor container owns the namespace; all six join it. Publish only `127.0.0.1:3000` and
`127.0.0.1:8090`. Mount the `thunderid-certs` volume read-only into the app containers and point
`NODE_EXTRA_CA_CERTS` (Node) and `SSL_CERT_FILE` (Python/httpx) at it, so `THUNDERID_VERIFY_TLS`
stays `true` and `NODE_TLS_REJECT_UNAUTHORIZED=0` appears nowhere in the box. `AUTH_ENABLED` is
`true` and is not reachable from the judge's `.env`.

**Verify:** browser → `http://localhost:3000` → sign in as `judge` → products list renders with
real data → the AI panel answers a question and completes one approval round-trip.

### 26e — Database access for judges

A Postgres role is simply a database login — a username and password. **The judge never types it.**
It is embedded in a `DATABASE_URL` connection string inside `aisle.env`; the containers read it and
the judge only places the file.

Through Supabase's session pooler the username is `<role>.<project-ref>`, confirmed against
Supabase's own Prisma guide — so for this project:

```
postgresql://aisle_demo.khinbdvubrxqqalejcbp:<password>@aws-<region>.pooler.supabase.com:5432/postgres
```

⚠️ **Known trap, must be resolved first.** RLS is enabled deny-all on every table with no policies.
The current `postgres` login is the table **owner**, and owners bypass RLS — which is the only
reason the app works today. A new non-owner role is **subject** to those deny-all policies and would
read zero rows everywhere. The role therefore needs `BYPASSRLS` (or explicit policies), and it is
not established that Supabase permits granting it. **Resolve this before building anything else in
this sub-gate.**

**Fallback if it cannot be granted:** ship the existing `postgres` connection string in `aisle.env`
— the developer's original choice — and rotate that password immediately after judging. Worse
blast radius, but honest and known, rather than a role that silently returns empty screens.

Confirm the demo dataset is presentable and seed extra products if thin. Write the **revocation
SQL** (or password rotation, on the fallback path) into the README, and note the 7-day inactivity
pause so the project is kept awake until results are back.

**The developer runs the SQL, deliberately — this is not just the working agreement.** If the
assistant ran `create role … with login password '…'`, that password would be written into a tool
call and preserved in the session transcript. It is the one credential handed to strangers, so it
must be generated and typed by the developer. The assistant supplies the statements with a
`<PASTE_A_PASSWORD_HERE>` placeholder; the developer runs them in the Supabase SQL Editor (faster
than the CLI for two statements, and it leaves an audit trail on their side) and puts the finished
connection string straight into `aisle.env`.

**Authorising the Supabase MCP connector is worth doing before this sub-gate, for verification
only.** It is not authorised in this session and cannot be from here (OAuth needs an interactive
session — `/mcp`). Once on, `list_tables` and `get_advisors` confirm the demo role sees exactly the
intended tables and that no new security advisory fired — a check that cannot be done by reading
files. Read-only tools only; the role creation stays with the developer regardless.

**Verify:** the demo role can read and write `products` and the agent schema, and is refused
everywhere else.

### 26f — Judge experience, and the documented fallback

`deploy/aisle-box/README.md`: numbered steps, the one certificate warning explained plainly, what
works without a Gemini key, and how to stop the box. `.env.example` documents every key with values
blanked, so the repo shows the shape without leaking anything.

**Also here — write the fallback down without building it**, as requested. Record in
`docs/DEPLOY-PLAN.md`: what an `AUTH_ENABLED=false` demo mode would be, that it is **not built**,
why (`frontend/src/proxy.ts` is deliberately fail-closed and has no bypass — adding one weakens the
single file designed not to have one), what it would cost, and the trigger that would justify it
(login failing in the Friday dry run with no time to fix it).

### 26g — Full dry run

From a clean checkout of this branch: `docker compose up --build`, timed. Walk the whole demo in a
browser. Record what breaks and how long a first run really takes, so the README's promise matches
reality.

### 26h — Persist the plan and close out

**The sub-gate that writes everything down**, per the explicit request:

- Rewrite `docs/DEPLOY-PLAN.md` to carry gate 26 with sub-gates **26a–26i** and the box design,
  keeping the existing B1/B2 write-up and the three handed-over gaps intact — nothing deleted or
  reworded to look better than it is.
- State plainly which gaps the box closes: gap 2 (TLS switches) is closed **inside the box**; gap 1
  (no rate limiting) and gap 3 (B1) are **not**, and remain required before real hosting. Record
  that the box avoids tripping them by never publishing the agent's port.
- Record facts 1–6 above, so the next session does not re-derive them.
- Update the gate-26 row in `docs/PLAN.md`, the `deploy/` entry in its file-structure snapshot, and
  the one-line pointer in `CLAUDE.md`.
- Add a note to `deploy/README.md` that a second stack now exists and the port collision means the
  dev ThunderID must be **stopped** (never `down -v`) while the box runs.

### 26i — B1, if time allows (optional, not part of the box)

Verify signature, expiry, issuer and audience in `agent/app.py` before reading `sub`, with the three
tests `docs/DEPLOY-PLAN.md` already specifies. Not required for the box. Required before the agent
is ever reachable from another machine.

---

## Files

**New:** `docs/superpowers/specs/2026-08-26-aisle-box-design.md` (this plan, committed first) ·
`deploy/aisle-box/docker-compose.yml`, `thunderid-deployment.yaml`, `.env.example`,
`README.md`, `thunderid-seed/*.db` · `backend/Dockerfile` + `.dockerignore` ·
`agent/Dockerfile` + `.dockerignore` · `frontend/Dockerfile` + `.dockerignore`

**Modified:** `frontend/next.config.ts` (one line) · `docs/DEPLOY-PLAN.md` · `docs/PLAN.md` ·
`CLAUDE.md` · `deploy/README.md`

**Delivered outside the repo:** `aisle.env` — the filled credential file, attached to the
submission as a supporting file.

**Untouched:** all of `backend/`, `agent/` and `frontend/src/` source; the existing
`deploy/docker-compose.thunderid.yml` and `deploy/thunderid-deployment.yaml`.

---

## Safety

- Everything on `build/aisle-box`.
- Project name `aisle-box`, volumes `aisle-box_*`. `docker compose down -v` is run only against the
  box or a throwaway spike stack — **never** against `deploy/docker-compose.thunderid.yml`.
- `oauth.dcr.insecure: true` does not ship.
- Nothing binds beyond `127.0.0.1`. The agent and MCP server get no published port at all.
- No plaintext credential is committed. The developer's personal account, email and real client
  secrets do not ship.
- **Port collision is real:** the box wants 8090 and 3000, which the dev ThunderID and
  `npm run dev` already hold. Stop them (`stop`, not `down`) before running the box.

## Does this block deploying later?

No. The Dockerfiles are the same artefacts a real deployment needs. Only the Compose file, the
seeded identity database and the shared namespace are box-specific — a hosted deployment swaps the
namespace for real DNS and real certificates, which is exactly what closes gap 2 for real. No
service code changes to make the box work.

## Verification, end to end

1. `docker volume ls` before and after — `thunderid-local_*` byte-identical.
2. `docker compose -f deploy/aisle-box/docker-compose.yml up --build` from a clean checkout.
3. Browser: sign in as `judge`, list products, open one, adjust stock.
4. AI panel: ask a question, trigger an approval, confirm it, verify the number moved in the DB.
5. `backend/` and `agent/` suites plus `lint-imports` still green — no service code changed, so any
   failure is a real regression.
