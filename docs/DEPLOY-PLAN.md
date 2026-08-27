# DEPLOY-PLAN.md — Gate 26: putting it in front of other people

**Scope: gate 26 only.** `docs/PLAN.md` remains the root source of truth and the progress table;
this file is the detail doc for the deployment gate, the way `BACKEND-PLAN.md` is for gates 0–8 and
`AUTH-PLAN.md` is for gates 22–25.

**Status: in progress on `dev`/`main`, not on a feature branch.** `build/aisle-box` was fully
merged (PR #35) and is a stale pointer kept only for history; do not check it out. Sub-gate table
below. `docs/PLAN.md`'s gate-26 row is the root statement of this status — if the two ever
disagree, that one wins and this line is the one out of date.

**Where this content was before.** Gate 26 was written up inside `AUTH-PLAN.md`, because at the
time it looked like the last of the login gates. It is not: gates 22–25 are about *who you are*,
gate 26 is about *where the code runs*. Splitting it out on 2026-08-26 closes `AUTH-PLAN.md` at
gate 25 and gives the deployment work a doc it can grow into. Everything moved here came as-is;
nothing was reworded to look better than it is.

---

## What this gate actually is — restated 2026-08-26

**Five things to run, not four.** The website, the web API, the MCP server, the AI agent service,
and **the login server**. ThunderID has no hosted option, so we run it ourselves — a real,
recurring cost of the provider decision, recorded in `AUTH-PLAN.md`.

**The gate's target changed on 2026-08-26, and this is the single most important line in the file.**
Aisle is being submitted to the Ascentic AI Launch Pad, deadline **Saturday 29 August 2026, 5pm**.
A deployed public link is explicitly *optional* there and supporting files are allowed. So the
deliverable is **not hosting**. It is a **reusable box**: one folder, one command, five services,
run on the judge's own machine.

That is a smaller gate than hosting, and deliberately so — but it is not a detour. The Dockerfiles
it produces are the same artefacts real hosting needs. Only three things are box-specific: the
Compose file, the pre-seeded identity database, and the shared network namespace. A hosted
deployment swaps the namespace for real DNS and real certificates, which is exactly what closes
gap 2 below for real. **No service code changes to make the box work.**

### Decisions taken by the developer, 2026-08-26

| Question | Answer |
|---|---|
| ERP database | **Shared hosted Supabase** — not a Postgres container |
| Gemini API key | **Judge supplies their own**; the app works without it, only AI chat is off |
| Image distribution | **Built on the judge's machine** by `docker compose up --build` — no registry |
| Credentials | Delivered as a **submission supporting file** (`aisle.env`), never committed |
| Fallback demo mode | **Documented, not built** — see 26f below |

**Recorded concern on the Supabase choice, raised once and overruled — proceeding as asked.** Every
judge writes to the same live data, and the demo needs internet. Reduced without changing the
decision: a **dedicated Postgres role, narrower than the `postgres` owner** (26e), and a revocation
step after judging. Narrower is not *least* privilege and this plan does not claim it is: the role
holds `BYPASSRLS` and full write access to three tables, and every judge shares the one credential,
so any holder can bypass API authorization and reach another judge's data. Accepted knowingly for a
three-day demo on throwaway data; it would not be acceptable for real hosting.
Switching to a local Postgres container later is a one-line `DATABASE_URL` change, no code moves.

---

## Facts established by measurement, not assumption

Recorded so no later session re-derives them.

1. **The login server's certificate is issued for `localhost` and `127.0.0.1` only.**
   `openssl x509` on `deploy/thunderid-server.cert`: `CN=localhost`,
   `SAN: DNS:localhost, IP:127.0.0.1`.
2. **`@thunderid/nextjs` exposes exactly one base-URL setting.** Scanning the SDK's `dist` for
   environment-variable names yields a single `THUNDERID_BASE_URL`, used by both browser redirects
   and server-side token exchange — and `NEXT_PUBLIC_*` is inlined at build time. It cannot be two
   addresses at once.
3. **The repository is public** (`gh repo view` → `"visibility":"PUBLIC"`).
4. **Every ThunderID secret is stored as a PBKDF2 hash, never plaintext** — 600,000 iterations, a
   per-entity random salt, a 32-byte key, confirmed by recomputing a known admin password from its
   stored salt and matching the stored value byte for byte. This is what makes committing the
   seeded database safe. It also removes a technical risk: nothing in those files is encrypted with
   `crypto.key`, so the fresh `crypto.key` generated on the judge's machine cannot break them.
5. **Supabase's free plan permits creating Postgres roles** — plain SQL, no plan gate. Limits that
   do apply: 500 MB database, 5 GB egress, and **projects pause after ~7 days of low activity**.
6. **Next.js `output: "standalone"` is the supported Docker path**, confirmed in the vendored docs
   at `frontend/node_modules/next/dist/docs/`.
7. **A custom Postgres role can sign in through Supabase's session pooler** (26e). Verified with a
   real connection: `current_user = aisle_demo`, port 5432, at
   `aws-0-eu-west-3.pooler.supabase.com`, username `aisle_demo.<project-ref>`.
8. **RLS deny-all applies to every non-owner role.** RLS is on with zero policies on every table.
   The app works today only because `postgres` **owns** the tables and owners bypass RLS. A new
   role reads *zero rows everywhere, with no error* — the worst failure shape there is. Resolved by
   granting `BYPASSRLS`, which PostgreSQL permits only from a superuser or another `BYPASSRLS`
   holder; `postgres` has `rolbypassrls = true`, so it was allowed.

9. **Port 3000 collides silently, not loudly, and it cost most of a debugging session.**
   `next dev` binds `:::3000` (IPv6 wildcard); Docker publishes `127.0.0.1:3000` (IPv4). Both
   binds succeed, no error is printed, and a browser resolving `localhost` tries IPv6 first —
   so it reaches `next dev`. The box then appears to be running while sign-in fails with
   `invalid_client`, because the dev server is exchanging its *own* client secret against the
   box's login server. `[HMR] connected` and `[object Object]` from `ThunderIDClientProvider`
   are the symptoms; `netstat -ano | findstr :3000` showing two listeners is the proof.
   Recorded in `deploy/README.md` and `deploy/aisle-box/README.md`.

---

## The design in one paragraph

Six long-running containers plus two one-shot init containers, in one Compose file with project
name `aisle-box`. **Every container shares a single network namespace**, so the box's internal
addressing is byte-identical to the developer's machine: login server on `localhost:8090`, API on
`localhost:8000`, MCP on `localhost:8001`, agent on `localhost:8002`, website on `localhost:3000`.
Only **3000 and 8090** are published, and only to `127.0.0.1`. The login server starts from a
**pre-configured database committed to the repo**, so the judge never meets the import wizard and
signs in as a ready-made `judge` account. Credentials arrive as a separate file dropped next to the
Compose file.

### Why the shared network namespace

Facts 1 and 2 together mean a conventional service-DNS layout would force one baked-in string to be
two different addresses at once. Sharing a namespace makes `https://localhost:8090` correct for the
browser, for the compiled bundle, for server-side code, and for the `iss` claim simultaneously —
and the TLS hostname then matches, so **certificate verification stays on**.

A dedicated do-nothing **anchor container** (`aisle-net`) owns the namespace rather than the login
server, so restarting the login server does not tear the network out from under the other five.

**This also means the agent never gets a published port.** `agent/app.py`'s `HOST = "127.0.0.1"`
stays exactly as written and the stop condition in `docs/AGENT-PLAN.md` is not tripped. **B1 is
therefore not a blocker for the box** — it stays required before any real hosting.

**Documented alternative if the namespace approach ever misbehaves:** a `socat` TCP forwarder
inside each app container mapping `127.0.0.1:8090 → thunderid:8090`. Same result, one extra binary
per image. Not built.

### How certificate trust is done — the thing that closes gap 2 *inside the box*

Three different mechanisms, because the three runtimes differ, and each was chosen for a reason:

| Container | Mechanism | Why not the others |
|---|---|---|
| `api`, `mcp` | `scripts/with-thunderid-ca.sh` merges the OS certificate bundle with the login server's certificate into `/tmp`, exports `SSL_CERT_FILE`, then `exec`s the real command | `SSL_CERT_FILE` **replaces** the trust list rather than adding to it. Pointing it straight at the one certificate would leave these containers trusting nothing else on the internet — survivable today, and a trap for the first person to add an outward HTTPS call |
| `agent` | `THUNDERID_CA_CERT=/certs/server.cert` | The code already has a purpose-built, *scoped* setting for this. It trusts that one certificate for login-server calls only and leaves every other connection alone — which matters here, because this container also calls Google for the AI model |
| `web` | `NODE_EXTRA_CA_CERTS=/certs/server.cert` | Node **adds** to its existing trust store, so no merging step is needed |

`THUNDERID_VERIFY_TLS` is `"true"` everywhere in the box and `NODE_TLS_REJECT_UNAUTHORIZED` appears
nowhere in it.

### The credential rule

**No plaintext credential is committed to the public repository.** The hashed login-server database
is committed (fact 4 — nothing recoverable in it). Everything plaintext — the box's client secrets,
`THUNDERID_SECRET`, and the database connection string — ships as a **submission supporting file**
named `aisle.env`. Compose already reads a file called `.env` next to the Compose file, so the
judge copies `aisle.env` → `deploy/aisle-box/.env` and pastes their Gemini key into its one blank
line. No mount arguments, no editing beyond that line.

**The one deliberate exception, stated here so this section does not contradict itself.** The
demo account's password (`judge` / `AisleDemo2026!`) *is* written in the repository, in
`deploy/aisle-box/README.md`. That is not a leak and not an oversight: it opens nothing except
a copy of the login server running on the reader's own machine, which they started themselves
and which holds no data of ours. Publishing it is what removes a setup step for the judge. The
rule above is about credentials that open something real — the database, and the box's client
secrets — and those are in `aisle.env` only.

**`AUTH_ENABLED` is not in that file and must never be.** It is hard-wired to `"true"` in
`docker-compose.yml`. One boolean turns identity off across two services at once (see `CLAUDE.md`),
so a deployment must not be able to flip it by editing a text file.

---

## Sub-gates

| # | What | Status |
|---|---|---|
| 0 | Persist the design into the repo before any code | ✅ `a551815` |
| 26a | Box skeleton — Compose stack, deployment config without `oauth.dcr.insecure`, first-run seed fix | ✅ `a36ce82` |
| 26b | Service images — `backend/`, `agent/`, `frontend/` Dockerfiles, `output: "standalone"` | ✅ `1cd3523`, `01f473f` |
| 26c | Identity baked in — pre-built login-server database, `judge` account, pre-commit leak scan | ✅ `95e03bc` |
| 26d | Wiring and TLS trust — the four app services join the namespace, certificates mounted | ✅ verified in a browser 2026-08-26 |
| 26e | Database access for judges — the `aisle_demo` role | ✅ grants verified, password rotated, reached from inside the box |
| 26f | Judge experience — `deploy/aisle-box/README.md`, `.env.example`, and the written-down fallback | ✅ done; `aisle.env` itself is assembled outside the repo |
| 26g | Full dry run from a clean checkout, timed | ✅ 2026-08-26 — 63s build, 4s start, whole demo walked in a browser |
| 26h | Persist the plan — this rewrite, plus `PLAN.md`, `CLAUDE.md`, `deploy/README.md` | ✅ done |
| 26i | B1 — the agent-server's own token verification (optional, not part of the box) | not started |

### 26g — what the dry run actually proved, 2026-08-26

Walked in a real browser against a box rebuilt from nothing (`down -v`, `--no-cache`):

1. Certificate warning appears exactly as the README describes; accepting it works.
2. `judge` / `AisleDemo2026!` signs in and lands on the products list — 24 products, live
   from Supabase through the `aisle_demo` login.
3. The AI panel took "Add 8 units to Sourdough loaf 800g", resolved it to the right SKU, and
   **asked for approval before writing**. Confirming moved stock 274 → 282.
4. **The row is stamped with the judge's own ThunderID id**, `01a03e4b-…`, confirmed against
   `ENTITY` in the seeded database as `judge@aisle.demo` — not the agent's id and not
   `system`. That is gates 22–25 working in the box rather than only in tests.
5. The same change through the ordinary form (−8) put it back to 274, so the dry run left no
   data behind.

Minor, pre-existing, not a box problem: the Adjust-stock field reports `valuemin="0"
valuemax="0"` to assistive technology while accepting negative numbers. A frontend
accessibility nit, unrelated to gate 26.

### 26e — what was actually done, and how to undo it

A dedicated role `aisle_demo` exists on Supabase project `khinbdvubrxqqalejcbp`. The judge never
types it; it is embedded in the `DATABASE_URL` inside `aisle.env`, the containers read it, and the
judge only places the file. Through the session pooler the username is `<role>.<project-ref>`.

It holds `BYPASSRLS` (the developer's explicit choice over per-table policies, so future features
need no policy work), `usage` on `public` and `agent`, full **select/insert/update/delete** on
`products`, `conversations` and `messages`, `usage, select` on their three id sequences, and
matching `alter default privileges` so tables added by future Alembic migrations are covered
automatically without a follow-up grant.

Verified: every positive privilege true, and seven negative checks false — `public.alembic_version`,
`agent.alembic_version`, `auth.users`, `vault.secrets`, `storage.objects`, create-in-`public`, and
create-schema. Supabase's security advisors were **byte-identical before and after** (4 INFO
`rls_enabled_no_policy` lints, no warnings, no errors).

**The developer runs the role's SQL, deliberately — this is more than the working agreement.** If
the assistant ran `create role … with login password '…'`, that password would be written into a
tool call and preserved in the session transcript. It is the one credential handed to strangers.
For the same reason the assistant never reads `deploy/aisle-box/.env`; it mounts it into a
throwaway container to test it instead.

**After results are back, this removes the whole grant set and touches nothing of the developer's:**

```sql
drop owned by aisle_demo;   -- drops the grants AND the default-privilege entries
drop role aisle_demo;
```

Also **keep the project awake**: the free plan pauses a project after roughly 7 days of low
activity (fact 5).

### 26f — the fallback, written down and deliberately not built

The developer asked for this to be recorded rather than implemented, and that is the right call.

**What it would be.** A demo mode with `AUTH_ENABLED=false`, so the box runs with no login server
at all: every request becomes the all-powerful `SystemActor`, the way the project worked before
gate 24.

**Why it is not built.** `frontend/src/proxy.ts` is deliberately fail-closed and has no bypass.
Adding one would weaken the single file in this project designed not to have one — to protect
against a risk that has not happened. It would also mean the box demonstrates a version of Aisle
whose most-worked-on feature (delegated identity, gates 22–25) is switched off.

**What it would cost.** A second Compose file, a bypass branch in `proxy.ts` plus tests for it, and
a second dry run. Half a day, most of it in the one file that should not be touched under time
pressure.

**The trigger that would justify it.** Sign-in failing during the 26g dry run with no time left to
fix it properly. Nothing less.

---

## Which of the three handed-over gaps the box closes

Stated plainly, because "it runs" is not the same as "it is safe to host".

| # | The gap | Does the box close it? |
|---|---|---|
| 1 | Nothing rate-limits a caller who has not signed in | **No.** Still outstanding. The box avoids the consequence by publishing only two ports, both to `127.0.0.1` on the judge's own machine |
| 2 | Self-signed certificate, with two "don't check the certificate" switches to cope | **Inside the box, yes** — see the trust table above. Both switches are off and both stay off. **Not closed for real hosting**, which needs a genuine certificate |
| 3 | The agent-server reads a name off a token without checking the seal (B1) | **No.** The box avoids tripping it by never publishing the agent's port and never removing `HOST = "127.0.0.1"` |

Gaps 1 and 3 remain hard prerequisites before any of this is reachable from another machine.

---

## The three things gate 25 handed over

All three are currently covered by one thing: `agent/app.py`'s `HOST = "127.0.0.1"`, which makes
the agent-server reachable only from the machine it runs on. **None of them survives that binding
coming off, and taking it off is exactly what this gate does.** Do not treat the lock as protection
that can be removed first and cleaned up after.

| # | The gap | Where it is | Status |
|---|---|---|---|
| 1 | Nothing rate-limits a caller who has not signed in | `api/`, `agent/`, `mcp_server/` | not started |
| 2 | The login server's certificate is self-signed, and two "don't check the certificate" switches exist to cope: `NODE_TLS_REJECT_UNAUTHORIZED=0` (website) and `THUNDERID_VERIFY_TLS=false` (Python) | `frontend/`, `agent/config.py`, `backend/` | not started — **neither switch may survive to deployment** |
| 3 | The agent-server reads a name off a token **without checking the seal** | `agent/app.py` | not started — full write-up below |

---

## Entry price: the agent-server's own door

**Decided 2026-08-26. Nothing in this section is implemented — it is the record of what was
deferred, why, and what "done" looks like, so this gate does not have to re-derive it.**

### The finding

`agent/app.py` gates conversation ownership on `actor.id`, which comes from `_subject_of()` —
a function that reads the `sub` claim out of the JWT **without checking its signature**. Anyone
who can reach the agent-server can therefore hand-craft a token naming someone else and read that
person's chat history. They cannot *change* any data that way, because `mcp_server/` does verify
what it is given; reading is enough to matter. Raised by CodeRabbit on PR #30.

**What holds it shut today:** `agent/app.py`'s `HOST = "127.0.0.1"`, which is why this is a gate 26
item rather than an open hole — gate 26 is the moment that binding is removed.

### Why the original mitigation was rejected

The first proposal was that the agent-server ask `mcp_server/` to verify the token, on the reasoning
that "two verification paths is how one of them ends up weaker". Rechecked against the MCP
authorization specification (2025-11-25 release, re-read 2026-08-26) and **withdrawn**, for two
independent reasons:

1. **It answers the wrong question.** `mcp_server/` validates against *its own* audience,
   `https://mcp.agentic-erp.local`. A "yes, valid" from it says nothing about whether the token was
   minted for the agent-server. Audience checking is per-door by definition and cannot be
   centralised — which is the same argument that produced two audiences at gate 25.
2. **It is the forbidden shape.** Forwarding a received token to another service is *token
   passthrough*: *"an anti-pattern where a server accepts tokens from a client without validating
   that they were issued specifically for that server, subsequently passing them to downstream
   APIs. This practice is strictly forbidden."* The resulting bug class is the confused deputy.

The general rule the spec states, and which this project should follow: **every service that makes
an access-control decision from a token validates that token itself**; a service acting as a client
onward *"must use separate tokens issued by the upstream authorization server rather than passing
through tokens received from the client."* `agent/auth.py`'s RFC 8693 exchange is already exactly
that second half, and is correct as built.

### The rule, stated once

**Anything in the middle of a chain needs both a resource server and a client** — a *door* to
receive tokens, a *badge* to request the next one. Only the two ends are simple: the browser is a
client only, `mcp_server/` is a resource server only.

| Service | Door (resource server) | Badge (client) |
|---|---|---|
| frontend | — (nothing calls into it) | `AIsle Gate` ✅ |
| `api/` | `Agentic ERP API` ✅ | — |
| **`agent/`** | **missing** ❌ | `AIsle Agent` ✅ |
| `mcp_server/` | `Agentic ERP MCP` ✅ | — |

The agent-server is the only service in the middle, and it is missing the half that receives.

### The two pieces of work, in priority order

**B1 — verify the token (this is the security fix).**
`agent/app.py` must check signature, expiry, issuer, and that `aud` is a recognised audience
*before* reading `sub`. Accepting the API's audience (`https://api.agentic-erp.local`) is
acceptable here: the agent-server is a front door of the same application, not an MCP server, so
the spec's strict same-audience requirement is not literally binding on it. This closes the finding
in full — the hole is "an unchecked name is trusted", not "the name on the pass is wrong".

Consequences to accept deliberately when doing it:

- **The "no JWT library in `agent/`" rule is retired.** It was reasoned from "the agent is not an
  authorization decision point — the ERP is", which is false about the agent's *own* conversations.
  A door that makes access decisions must be able to read passes. `agent/actor.py`'s existing
  warning (*"If this id ever starts gating something, it is wrong"*) is the same observation and
  should be rewritten, not deleted, when this lands.
- `_subject_of()` in its current hand-decoding form goes away. The frontend's `subjectOf()` in
  `lib/auth/current-user.ts` may stay — it labels UI, it gates nothing.
- The agent's virtualenv gains `pyjwt[crypto]`. Note that `backend/pyproject.toml`'s two
  `forbidden_modules` lists govern `backend/` only and are unaffected.

**B2 — give the agent-server its own audience (optional).**
Register `Agentic ERP Agent` / `https://agent.agentic-erp.local` (type API, delimiter `.`, **not**
default), and have the frontend obtain a token stamped for it. This narrows the blast radius — an
agent-server token would no longer also open the API — but it requires new token handling in the
frontend's `app/api/agent/[...path]/route.ts`, and it is *not* what closes the finding. Do it with
the deployment work or not at all.

### How to tell when it is done

1. `agent/tests/` contains a test that a **validly-shaped but wrongly-signed** token is refused
   with 401. Today's `test_an_unreadable_token_is_refused_rather_than_labelled` only covers a token
   that cannot be *parsed*, which is a strictly weaker claim, and passing it is not evidence.
2. A test that an **expired** token is refused.
3. A test that a token carrying an **unrecognised `aud`** is refused.
4. **Read the call path from `get_actor()` to the verifier and confirm the signature check is on
   it.** This condition used to read *"`grep -n "without verifying" agent/app.py` returns
   nothing"*, which was replaced on 2026-08-26 after CodeRabbit pointed out on PR #31 that it is
   satisfiable by editing a comment. A phrase-based check cannot tell a fixed function from a
   reworded one, and a done-condition that passes while the hole is open is worse than no
   condition — it is a green light with nothing behind it. Conditions 1–3 are the real evidence;
   this one is the eyeball pass that catches a verifier that is present but never called.
5. Only then may `HOST = "127.0.0.1"` in `agent/app.py` be reconsidered — and gap (1) above (no
   rate limiting) is still outstanding independently.

### ThunderID-side work required

**For B1: none.** No new resource server, no new permissions, no role changes. B1 uses tokens
ThunderID already issues, checked against the JWKS endpoint it already publishes. The admin MCP
session is *not* needed.

**For B2:** one new resource server, via the Console or the admin MCP — see `AUTH-PLAN.md`,
"Identity-provider side, completed 2026-08-25", for the shape `Agentic ERP MCP` used.

---

## Open decisions this gate must make

None of these are decided. They are listed so the gate starts from a known-empty state rather than
from an assumption.

- **Where each of the five services runs.** They do not have to share a host, and the login server
  probably should not.
- **How the login server's data survives.** The three `thunderid-local_*` Docker volumes are the
  identity store and there is no backup; `deploy/README.md` records the commands that must never be
  run against them. A hosted instance needs a real answer here, not a rule about what not to type.
- **Real certificates**, which is what actually removes the two TLS switches in gap (2).
- **Where secrets live** once `.env` files stop being the mechanism — including `crypto.key`, which
  cannot be regenerated: lose it and encrypted data is unrecoverable.
- **Whether the MCP server's protected-resource discovery/metadata ceremony lands here.** It was
  deferred from gate 25 at the developer's explicit request, with questions still open on it.

---

## What a new feature has to update in the box

Added 2026-08-27, before the project went back to feature work on multiple branches. Everything
below was found by reading `deploy/aisle-box/` against the rest of the tree, not by hitting it in
production. Each one has the same shape: **the feature works perfectly on the developer's machine
and is broken or absent in the box**, because the box is a second, hand-maintained copy of the
configuration. Nothing checks these automatically. This section is the check.

### 1. A new permission is written down in seven places, and drift fails silently

This is the worst of the three, because of *how* it fails. Gate 23 established it and gate 25
restated it: **asking ThunderID for a permission it has never heard of does not produce an error.**
It returns a perfectly valid, correctly-audienced token carrying **no `scope` claim at all**. Every
`actor.can(...)` then returns false, so the symptom is that the whole application answers 403 to a
signed-in user. It looks like a bug in the authorization code. It is a spelling mismatch in a
configuration file.

Adding, renaming or removing a permission means changing all of these together:

| # | Where | What |
|---|---|---|
| 1 | `backend/services/*.py` | `_require(actor, "...")` — the real source of truth, the only one the business logic reads |
| 2 | `frontend/.env.example` **and** the developer's own `frontend/.env` | `NEXT_PUBLIC_THUNDERID_SCOPES` |
| 3 | `deploy/aisle-box/docker-compose.yml` (`web` service, `args:`) | the same string again — a **build** argument, because `NEXT_PUBLIC_*` is compiled into the browser JavaScript, so changing it needs `--build`, not a restart |
| 4 | `agent/config.py` | the `thunderid_scopes` default |
| 5 | `agent/.env.example` | the commented `THUNDERID_SCOPES` line |
| 6 | `deploy/aisle-box/seed-build/aisle-config.yml` | the **resource server** definition *and* the `AIsle Full Access` role — and against **both** resource servers, the API's and the MCP server's, which are separate entries |
| 7 | The developer's own running ThunderID | the same two changes, made in the Console, or nothing works locally either |

Numbers 6 and 7 are the ones that get forgotten, because the first five are in the source tree
where a search finds them. Number 6 additionally requires **rebuilding the shipped seed** —
`prune-config.py`, then `build-seed.py`, then `scan-seed.py` — or the committed `.db` files still
carry the old permission list regardless of what the YAML says.

⚠️ **The seven places are not always filled in identically, and the box's role layout hides that.**
Found on 2026-08-27 while carrying gate 27's permissions in. `AIsle Full Access` is assigned to
**both** the judge user *and* the agent:

```yaml
assignments:
  - id: __JUDGE_USER_ID__
    type: user
  - id: 01a038f2-baa4-7a5a-a21c-b87124977fb8
    type: agent
```

So one role serves two very different principals, and every permission added to it is added to
both. That was harmless while every permission was one the agent legitimately holds. It stops being
harmless the moment a feature has a permission that is **deliberately human-only** — gate 27's
`draft.decide` is the first, and gates 29–30 will add more.

**Gate 28 added a second, for a different reason.** `lot.write` books a delivery in, and the
agent deliberately does not hold it: receiving stock is a physical event a person witnesses, and
an agent that could invent stock could invent a spoilage problem and then propose the solution
to it. `lot.read` it does hold. So the running total of permissions the box's seed must
reproduce is:

| Permission | Human role | Agent role |
|---|---|---|
| `draft.read`, `draft.create` | yes | yes |
| `draft.decide` | yes | **no** |
| `lot.read` | yes | yes |
| `lot.write` | yes | **no** |


A permission that must not reach the agent needs the agent moved to its own role first. Putting it
in `AIsle Full Access` grants it to the agent, silently, with every test in the repository still
green — because the tests prove the *code* refuses an actor without the permission, and this hands
the agent the permission.

⚠️ **The `.db` files are the artefact, not `aisle-config.yml`.** The YAML is an input to a build
step. Editing it alone changes nothing about what a judge runs.

### 2. The box never runs a database migration

`docker-compose.yml` starts `uvicorn` directly. There is no `alembic upgrade head` anywhere in
`deploy/`, and that is deliberate — the box points at the **shared hosted Supabase database**, which
is already migrated, and letting six containers on six judges' machines race to migrate a shared
database would be worse than not migrating at all.

The consequence for feature work: **a new migration is not applied by anything the judge runs.** If
a feature adds one, the developer must apply it to Supabase by hand before anyone runs the box, or
the box starts cleanly and then fails at the first query against the new column.

CI does not cover this either, in the direction that matters. `.github/workflows/ci.yml` runs
`alembic upgrade head` against a throwaway Postgres, which proves the migration *applies*. It says
nothing about whether the shared Supabase database has had it applied.

### 3. A new setting has to be added to the compose file by hand

`backend/`, `agent/` and `frontend/` each read settings from their own `.env`, which the box does
not use — the box declares every value in `docker-compose.yml` instead, per container. A setting
added to `backend/core/config.py` with a default will therefore take its **default** inside the box,
silently, while working correctly on the developer's machine where `.env` supplies it.

A new setting needs: the service's own `.env.example`, the matching `environment:` block for **each
container that needs it** (remember `api` and `mcp` are the same image and need it twice), and — if
a judge has to supply the value — a line in `deploy/aisle-box/.env.example` and in the `aisle.env`
handed over with the submission.

⚠️ **A `NEXT_PUBLIC_*` setting is the exception, and it fails silently in the usual way.** It is
compiled into the browser JavaScript at build time, so it belongs in the `web` service's `args:`
block, **not** `environment:` — an `environment:` entry for one is accepted, changes nothing, and
leaves the bundle carrying the old value. Changing it also needs `--build`; a restart will not do
it. Same rule as row 3 of the permission table above, for the same reason.

Two rules that do not bend:

- **`AUTH_ENABLED` is hard-wired `"true"` in the compose file and must never be read from the
  judge's `.env`.** One boolean turns identity off across two services at once.
- **A secret never becomes a `NEXT_PUBLIC_*` variable.** That prefix means "compile this into every
  visitor's browser".

### A correction to this plan's own account of the seed

The design spec says removing `Test Agent` "also removes a `Product Reader` assignment". In the seed
as actually built, `Product Reader` is assigned to `__JUDGE_USER_ID__` — because
`prune-config.py` replaces the developer's user id with the judge placeholder everywhere it appears,
including inside role assignments, while `strip_references()` only deletes assignments pointing at
the three dropped documents. So the developer's assignment was redirected, not dropped.

No security consequence today: `Product Reader` in the shipped configuration grants the same six
permissions as `AIsle Full Access` (against one resource server rather than two), and the judge
already holds the latter. It is recorded because the claim above is otherwise false, and because
anyone who later narrows `Product Reader` to genuinely read-only — intending it as a demonstration
of least privilege — would be quietly handing it to the judge as well.
