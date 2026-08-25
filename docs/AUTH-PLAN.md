# Authentication — the decision, the mechanism, and the four gates

> **Subordinate to `docs/PLAN.md`.** This file holds the authentication and agent-identity
> workstream in full: the provider position, the delegation mechanism the design rests on, how the
> permission vocabulary maps onto it, and what each of Gates 22–26 has to do. Where this file and
> `PLAN.md` disagree, **`PLAN.md` wins** and this file is the thing that is out of date.
>
> It is split out because it is read at exactly one stretch of the project — the auth gates — while
> the decisions it records constrain `backend/`, `agent/` and `frontend/` alike, so filing it under
> any one of them would hide it from the other two. `PLAN.md` keeps only the gate rows and the
> expiry trigger, because those gate further feature work and must sit in the file that is always
> read.
>
> **Rewritten in place on 2026-08-14 (Gate 22).** This document previously carried a 2026-07-29
> decision plus three dated amendments that had to be read in reverse order, and its provider
> comparison had gone stale in ways that changed the work. Everything below is current and reads
> forwards. Nothing was silently dropped: the superseded comparison is preserved, compressed, under
> "What we considered and rejected". The reasoning behind every decision is kept; only the
> read-the-amendments-backwards structure is gone.
>
> **Updated 2026-08-18 (Gate 23).** The spike ran and passed. Findings were written *into* the
> sections they correct rather than appended as an amendment, to preserve the read-forwards
> property above. Three documented behaviours turned out to be wrong and are corrected in place —
> the most important being that over-requesting scope is silently narrowed rather than rejected.
> Every verified claim is now marked as such.
>
> **Re-verified 2026-08-18, before Gate 24 starts.** A full pass over the vendor's current docs,
> their SDK index, their release feed and PyPI. **No decision in this file changed** — the provider,
> the mechanism, the rejection of their Python MCP guide and the keep-vendor-libraries-out-of-Python
> rule all survived contact with current documentation. What changed is detail: the install options
> are now enumerated (there are four, including a Windows binary), the Gate 26 hardening list was
> materially incomplete, and the Gate 24 environment variables are now known rather than guessed.
> Corrections are written in place as before.

---

## Status in one paragraph

The deferral has expired and the work is **partly built**: Gate 22 (this plan), Gate 23 (the spike)
and **Gate 24 (people signing in) are done** — a real person signs in through ThunderID's hosted
page and the web API validates their token on every request. Gate 25 (the agent acting for that
person) and Gate 26 (hosting) are not started. **ThunderID is the chosen provider — the Gate 23
spike passed on 2026-08-18, so this is no longer provisional.** The delegation mechanism is **OAuth
2.0 Token Exchange (RFC 8693)**, proven against a live server to downscope correctly and to refuse
to hand back more authority than the incoming token carried. **ID-JAG is deliberately left open** as
a later switch, and — this is the finding that most changes the shape of the work — leaving it open
costs one function parameter, because ID-JAG is a value of `requested_token_type` on the same
endpoint, not a rival architecture. No application code has been written yet.

---

## Why this is happening now

Two conditions were written down long ago as expiring the deferral, and either one triggers the auth
gates before further feature work. They are listed in **`PLAN.md`**, which owns them — it is the file
read every gate, and the conditions are a rule for *stopping other work*, so they belong there rather
than here.

**Condition 1 has fired:** the stated goal is to host the frontend, the API backend, the MCP server
and the agent, and a hosted MCP server is by definition reachable by something other than the
developer's own machine.

So the ordering is fixed, and it is not a preference:

> **The auth gates are a hard prerequisite for deployment.** Not a nice-to-have that follows it.

Deploying first is not a "ship it and add auth after" trade-off, which is how it usually gets
rationalised. `mcp_server/server.py`'s `_actor()` returns `SystemActor`, and `services/` grants
`SystemActor` everything — so a publicly reachable MCP server on today's code gives **anonymous
callers full write access to inventory**, with every row stamped `created_by="mcp"` and nothing
distinguishing those writes from legitimate ones. There is no partial version of this to ship.

Gate 20 anticipated this: `agent/app.py` binds to `127.0.0.1` with a test that fails if that
changes, and `AGENT-PLAN.md` records the intended order as **local → auth → deploy**. That test is
the thing currently standing between this code and anonymous write access, and it is deleted in
**Gate 26 and not before**.

---

## The design, and why an identity server is required

Human auth and agent auth are different problems. Human auth is commoditized. Agent auth — an AI
acting *on behalf of* a person, with a subset of their permissions and a clear accountability trail
— is the hard half, and it is the half this project is actually organised around.

**An identity server is required.** The standards-based mechanism for "the agent may only do what
the user may do" is **RFC 8693 token exchange**: the agent presents the user's token as
`subject_token` and receives a *derived, narrower* token carrying both the user's identity and the
agent's. Issuing that token is by definition an authorization server's job. The alternatives —
forwarding the user's raw token, or running the agent as a service account — are precisely the
confused-deputy and privilege-escalation failures documented under "three deployment shapes" in
`docs/BACKEND-PLAN.md` (Gate 6). MCP assumes this too: an HTTP MCP server is an OAuth resource
server that must never forward the caller's token upstream.

### What was already built for this, years ahead of needing it

From Gates 3–4 onward, and unchanged by anything below:

- Every service function takes an `actor` as its second argument, after `session`.
- Permission checks live in `services/` (`actor.can("stock.adjust")`), never in the adapters.
- `core/exceptions.py` includes `PermissionDeniedError`.
- Models carry `created_by` / `updated_by` audit columns.
- A `SystemActor` granting everything stands in until a real provider is wired in.

Services never learn *how* someone authenticated — only who they are and what they may do. That is
why adopting a provider is a change to a handful of seam functions rather than a rewrite. The audit
columns are wanted regardless; an ERP needs "who adjusted this stock?".

---

## The mechanism, verified against ThunderID's live docs (2026-08-13/14)

### Token exchange

| Aspect | Behavior |
| --- | --- |
| Endpoint / grant | `POST /oauth2/token`, `grant_type=urn:ietf:params:oauth:grant-type:token-exchange` |
| `subject_token` / `subject_token_type` | Required. Input types accepted: `access_token`, `refresh_token`, `id_token`, `jwt` |
| `scope` | **Downscoping allowed; widening is silently narrowed, not rejected.** The docs say `invalid_scope`; Gate 23 found otherwise — see "What the spike found". Final scopes must also be permissions on the target resource server *and* authorized for the issuing app or agent |
| `resource` | RFC 8707 resource indicator. The issued token is bound to exactly this resource server. **Verified at Gate 23** |
| `audience` | Accepted for RFC 8693 compatibility but **does not determine the `aud` claim** — use `resource`. **Verified at Gate 23: a bogus `audience` was silently ignored** |
| `actor_token` / `actor_token_type` | Optional; supplies the acting party in a delegation chain. `actor_token_type` is required when `actor_token` is given |
| `requested_token_type` | `access_token`, `jwt`, **`id-jag`**. `id_token` and `refresh_token` outputs are not supported |

The scope row is the whole design in one line: **"the agent may only do what the user may do" is
enforced by the issuer, not by us.** An inventory-only agent is an agent authorized for a narrower
permission set, exchanged against a token that cannot widen it.

Two traps recorded because each costs a debugging session if unknown. **Both are now confirmed
against a live server** (Gate 23):

- **`audience` is a decoy.** Setting it and expecting the token's `aud` to follow will silently
  fail. `resource` is the parameter that works. Confirmed: passing
  `audience=https://should-not-be-aud.example` alongside a correct `resource` produced a token whose
  `aud` was the `resource` value, with no error and no warning.
- **The `act` claim never appears on its own.** Confirmed absent from both a client-credentials
  token and an exchanged token when no `actor_token` was supplied. So a delegation chain that omits
  `actor_token` produces a token that is correctly downscoped but **does not record who narrowed
  it**. If Gate 25 wants "agent X acting for user Y" legible in the token itself, it must pass
  `actor_token` explicitly — it is not free.

### ID-JAG is a parameter, not a second architecture

This supersedes an earlier framing in which RFC 8693 and ID-JAG were rival mechanisms to choose
between. They are not. ID-JAG is a value of `requested_token_type` on the **same endpoint, same
grant type, same request** — see the table above.

It gets better: **both halves of the ID-JAG flow already ship in the `mcp==2.0.0` this project
already pins.** Verified against the installed source in both virtualenvs on 2026-08-14 — nothing to
install, nothing to upgrade:

| Side | What exists today | Where |
| --- | --- | --- |
| Server | `AuthSettings.identity_assertion_enabled` — "Advertise and accept the SEP-990 Identity Assertion Authorization Grant (the RFC 7523 jwt-bearer grant carrying an ID-JAG) at the token endpoint" | `mcp/server/auth/settings.py` |
| Client | `IdentityAssertionOAuthProvider`, a complete `httpx2.Auth` for the SEP-990 flow, taking an `assertion_provider` callback | `mcp/client/auth/extensions/identity_assertion.py` |
| Both | `AccessToken.claims` documented as carrying `act` | `mcp/server/auth/provider.py` |

So the ID-JAG path is a flag on one side and a different `httpx2.Auth` on the other.

**The rule that keeps it open**, stated once and enforced in one place per side:

> **Never hardcode the grant type or the requested token type.** Both are parameters of a single
> function per side. Everything above those functions sees an `Actor` or an `httpx2.Auth` and knows
> nothing about which OAuth mechanism produced it.

- **Agent side:** `agent/auth.py` (new at Gate 25) exposes
  `get_scoped_token(user_token, *, resource, scopes, requested_token_type=...)`, defaulting to
  `access_token`. Switching to ID-JAG later means passing `...:id-jag` and swapping in the SDK's
  `IdentityAssertionOAuthProvider`. Agent-to-agent means supplying `actor_token`, which the same
  function already accepts.
- **Backend side:** `AuthSettings(...)` gains `identity_assertion_enabled=True` when needed. The
  `TokenVerifier` validates a JWT and does not care how it was minted.

**Deliberate non-goal: do not build an ID-JAG code path now.** It is a parameter and a flag over
machinery that already ships. Building it before a real cross-domain use case exists would be
speculative work against a draft spec, with no second party to test against. What is required now is
only that nothing *blocks* it.

When would it actually be needed? When the other side of the hop is not ours: an outside MCP server
under someone else's identity provider, or an outside agent acting for its own user against ours.
Agents that are all ours, calling servers that are all ours, stay in a single trust domain, which is
exactly what RFC 8693 is for.

### Agents are first-class identities, which is what makes "more agents later" cheap

From ThunderID's agent guide: an agent is "a machine identity for autonomous software, such as an AI
assistant, a background worker, or a scheduled job," each with "its own identifier, owner,
credentials, attributes, and lifecycle," holding "scoped access through roles and groups, so an
agent reaches only what its work needs."

Three operating modes are supported natively, which is the full set this project needs:

1. **Agent token** — the agent acts autonomously, as itself.
2. **User delegation** — the agent acts on behalf of a user. *This is the one Gate 25 builds.*
3. **Agent-to-agent** — authority delegated from one agent to another.

Two constraints from the agent-authentication guide: agents are **confidential clients**, using
either `client_secret` or `private_key_jwt`; and an agent **cannot** use
`tokenEndpointAuthMethod: none`, which would mark it a public client, block `client_credentials`,
and limit it to user-delegated flows.

Consequence for this project: adding a second agent later is **a registration plus a role**, not a
design change. A second agent is a new identity with its own narrower permission set, exchanging
against the same endpoint through the same `get_scoped_token`.

### Permission strings already match — if the delimiter is set at creation

ThunderID builds hierarchical permissions as `{resource-handle}{delimiter}{action-handle}`. The
delimiter **defaults to `:`**, accepts characters from `a-z A-Z 0-9 . _ : - /`, and **cannot be
changed after creation**.

Our permission vocabulary is already dotted — these are the exact strings `services/` passes to
`actor.can()` today:

| Permission | Resource handle | Action handle |
| --- | --- | --- |
| `product.read` | `product` | `read` |
| `product.create` | `product` | `create` |
| `product.update` | `product` | `update` |
| `stock.adjust` | `stock` | `adjust` |

So registering the backend as a resource server with **`delimiter: "."`** makes ThunderID's
permission strings *identical* to the ones already in the code, and `TokenActor.can()` becomes a set
membership test with nothing to translate. Accepting the `:` default would mean either rewriting
every `can()` call site or maintaining a mapping table forever — and the field cannot be corrected
afterwards, only deleted and re-registered.

Permission strings are **not** prefixed by the resource server. The server is identified by its
`identifier`, which becomes the token's `aud`.

**One correction to an easy assumption:** `product.read` is checked on reads too — four call sites
in `services/products.py`. A read-only agent still needs a scope. "Read-only tools need no
permission" is false here.

### What the MCP authorization spec actually requires

The requirements on a hosted `mcp_server/` are **resource-server** requirements, and the list is
shorter than "MCP needs the full OAuth stack" implies:

- It is an **OAuth 2.1 resource server**, and nothing more.
- It **MUST** serve `/.well-known/oauth-protected-resource` (RFC 9728) naming its authorization server.
- It **MUST** validate that the token's audience is **itself** (RFC 8707).
- It **MUST NOT** accept or forward tokens issued for anything else — no passthrough.
- Failures are `401` with `WWW-Authenticate`, or `403` with `insufficient_scope`.
- Clients must validate the `iss` parameter (RFC 9207).
- **RFC 7591 Dynamic Client Registration is deprecated**, in favour of Client ID Metadata Documents.
- **stdio transports SHOULD NOT follow this spec** — which independently confirms that the local
  stdio setup is correct rather than merely unaudited.

Note what is *absent*: **RFC 8693 is not required by MCP.** Token exchange is our answer to the
delegation problem, not the protocol's demand. That is precisely why the ID-JAG option stays open.

**One divergence recorded deliberately, not to be fixed.** ThunderID's MCP guide says the MCP server
should check scope at the tool boundary, before a tool handler runs. This project checks in
`services/` via `actor.can(...)`. **Keep it that way.** The MCP layer answers "may you reach this
server at all"; `services/` answers "may you adjust stock". `mcp==2.0.0`'s `required_scopes` is a
single server-wide list with no per-tool equivalent anyway, and per-operation authorization belongs
where this project decided it belongs. Do not try to move the second check up.

---

## What this costs to run

Stated plainly so the trade is visible rather than discovered later.

**There is no hosted ThunderID.** No SaaS tier, no cloud sandbox, no demo instance — self-hosting is
the whole offering. Adopting it means:

- a **fifth deployed service**, with its own container, persistent datastore, TLS and backups;
- **pinning an exact tag** — six releases in four weeks; 1.0.0 is out, but that cadence has not
  yet slowed and the release is too new to have been proven in the field;
- owning the upgrade path when a young 1.0 makes a breaking change.

Five services and a four-week-old identity provider is meaningfully more operational surface than
four services. That is the real cost of "free licence", and Keycloak carries the same cost — it
simply carries it with years of production use behind it.

**Release status, checked 2026-08-18:** the instance running for Gate 23 reports **`v1.0.0`** in the
console footer — the rc has been superseded by a GA-numbered release. That removes the single
largest objection recorded below ("is a pre-GA server acceptable as the identity provider?"). The
version pin must be updated accordingly, and the churn concern is *reduced, not gone* — a 1.0.0 four
weeks after first alpha has not yet been proven in the field.

**Previous status, checked 2026-08-13:** `v1.0.0-rc`, published 2026-08-13. The cadence is
alpha (07-21) → alpha2 (07-28) → beta (08-04) → beta2 (08-07) → rc (08-13). Still no GA. The rc notes
add MCP client authentication workflows, restore the delegated-mode toggle for agents, enable
refresh-token rotation by default, and add an authorization and credential-state check on the refresh
grant. One flagged risk: removal of "Subject Attribute from API layer" may affect integrations.

### No Python SDK — and this is not a problem

ThunderID ships 17 SDKs — React, Next.js, Express, Vue, Nuxt, Node, vanilla JS, core JavaScript,
React Router, TanStack Router, Spring Security, iOS, Android, Flutter, plus Claude/Codex agent
tooling and `@thunderid/skills` (all three Beta). **There is still no Python SDK** — re-checked
2026-08-18, where Python remains on the "Coming Soon" list alongside Go, Angular, Auth.js, Better
Auth, Passport and React Native. It does not matter, because of which OAuth role each half of this
system plays:

| Component | OAuth role | What it needs |
| --- | --- | --- |
| `frontend/` (Next.js) | **Client** | Runs the login redirect, holds the client secret, manages the session. This is where an SDK earns its keep — `@thunderid/nextjs` exists |
| `backend/api/` | **Resource server** | Only validates an incoming JWT against the JWKS endpoint. ~40 lines of `pyjwt[crypto]` |
| `backend/mcp_server/` | **Resource server** | Same. Note `mcp==2.0.0`'s `TokenVerifier` is an *interface we implement*, not a working verifier — see below |
| `agent/` | **Client** | One `POST` to the token endpoint. `agent/auth.py`, no vendor library |

So **no vendor library enters `backend/` or `agent/` at all.** That is worth protecting deliberately:
it keeps the provider swappable the same way SQLAlchemy keeps Supabase swappable, which matters more
than usual given how young this provider is. If adopting a provider ever requires a vendor import below
`api/` or `mcp_server/`, that is a signal the integration is being done wrong.

Corollary for the import contracts: any JWT library added to `backend/requirements.txt` must also be
added to **both** `forbidden_modules` lists in `backend/pyproject.toml`, or `services/` could import
it and the boundary that makes this whole design work would quietly weaken.

### Where ThunderID lives — not in this repository

Recorded because it is the question a newcomer to auth asks first, and the wrong answer creates mess
that is annoying to undo. **Treat ThunderID exactly like Postgres.** Supabase's source is not
vendored into `backend/`; neither is this. What belongs in the repo is only a compose file under
`deploy/`, environment variables (issuer URL, client ID, client secret), and the generic OIDC
validation code described above.

### The four install options, and why this project uses Compose

Enumerated 2026-08-18 from the vendor's getting-started page, because the earlier revision of this
section discussed only `npx` and Compose and left the impression those were the only choices.

| Path | How | Platforms |
| --- | --- | --- |
| **Release binary** | download `thunderid-<version>-<os>-<arch>.zip`, run `./setup.sh` + `./start.sh`, or **`.\setup.ps1` + `.\start.ps1` on Windows** | Windows x64, macOS arm64/x64, Linux arm64/x64 |
| **Docker Compose** | vendor's is `docker compose -f oci://ghcr.io/thunder-id/thunderid-quick-start:latest up`; **ours is `deploy/docker-compose.thunderid.yml`, pinned** | any |
| **Docker, two-step** | one-time `docker run --rm … ./setup.sh`, then `docker run -d …` | any |
| **Helm / Kubernetes** | requires PostgreSQL first; the vendor's production recommendation | clusters |

A **`thunderid-1.0.0-win-x64.zip`** ships on the v1.0.0 release, so a native Windows install is a
genuine option on this developer's machine and not a workaround. **Compose is still preferred**, for
one reason that outlives the convenience argument: Gate 26 deploys containers, and a local setup that
is already a container is one fewer difference between "works locally" and "works deployed". The
native binary's advantage — setup runs once, explicitly — has now been obtained on the Compose path
too (see below), so it no longer distinguishes the two.

⚠️ **The `npx` install path is no longer documented by the vendor.** The earlier warning here —
`npx thunderid --install-dir . …` writes a datastore into the current directory, so never run it
inside the repository — is retained because the command still works and older third-party guides
still recommend it. But it is absent from the current getting-started page, so it should not be
chosen fresh.

**Install reference, as built at Gate 23 and restructured 2026-08-18:**
`deploy/docker-compose.thunderid.yml` in this repo, pinned to image **tag** `1.0.0` — deliberately a
tag and not the digest; see "Tag pin vs digest pin" below. Data lives in Docker
**named volumes**, not the working directory, so the `npx` trap does not apply here. Server at
`https://localhost:8090`, console at `/console`, **self-signed certificate** — accept it in a browser
once before any client will talk to it. The admin password is *not* `admin`/`admin` on this path: it
is generated by `thunderid-setup` and printed in that container's logs.

**Two commands, and the order matters** — this replaces the single `up` the file used to take:

```bash
# ONCE per machine (or after `down -v`). Prints the admin password — capture it.
# No --abort-on-container-exit: that flag kills the stack when db-init exits, which it does
# first and by design, and can cut setup off mid-way. Both containers exit on their own.
# `thunderid-setup` must be named: a bare `up` also starts every profile-less service, and
# the main `thunderid` server is profile-less, so it would boot against an unseeded database.
docker compose -f deploy/docker-compose.thunderid.yml --profile init up thunderid-setup

# EVERY time after that. Safe to repeat; does not touch key material.
docker compose -f deploy/docker-compose.thunderid.yml up -d
```

Step 1 is now **safe to run by mistake**: `thunderid-db-init` refuses on a non-empty volume rather
than copying the image's empty seed databases over the identity store, which is what it used to do.
A refusal with `REFUSING TO RESEED` is the correct outcome on a machine that is already set up — it
is not an error to work around, and specifically not one to resolve with `down -v`.

**Verified against a live Docker daemon 2026-08-25.** Running step 1 on the already-set-up machine
refused and exited 1 without copying anything. Two side effects worth knowing so they are not
mistaken for damage: Compose *recreated* the `thunderid-db-init` and `thunderid-setup` **container
objects** (containers, not volumes — the identity store was never opened), and `thunderid-setup`
never executed at all because it depends on `db-init`, which failed first. The running `thunderid`
server was untouched and stayed up throughout. Both are exactly what should happen.

**Tag pin vs digest pin — decided 2026-08-25, keep the tag.** Review (CodeRabbit, PR #28) asked for
the three `image:` lines to name the recorded digest
(`sha256:12b7348b…`) instead of `1.0.0`. Declined deliberately, and the distinction is worth having
written down because it is not a style preference:

| | What it means | What it costs |
|---|---|---|
| **Tag** `:1.0.0` | "whatever image carries that label today" — the vendor can move it | We receive their patches automatically; we cannot detect that the image changed |
| **Digest** `@sha256:…` | "this exact image, or fail" — cannot be moved by anyone | Provably the validated bytes; patches never arrive until a human edits the file |

**We keep the tag because we want vendor patches to a version already validated**, and because
nothing here is internet-reachable: the port is loopback-bound and the file is local-only. The
accepted risk, stated plainly rather than hidden: a patched `1.0.0` and a tampered `1.0.0` are
indistinguishable from inside this repo.

**This flips at Gate 26.** Anything reachable from the internet should be digest-pinned, with
upgrades performed as a deliberate, recorded edit — the whole argument for the tag ("patches arrive
without us noticing") is an argument *against* it once the thing is exposed. Added to the Gate 26
requirements below.

**The digest is the documented fallback.** If the image ever appears to have changed under us,
compare what the tag resolves to against the recorded value:

```bash
docker buildx imagetools inspect ghcr.io/thunder-id/thunderid:1.0.0    # what the registry serves now
docker image inspect --format '{{index .RepoDigests 0}}' \
  ghcr.io/thunder-id/thunderid:1.0.0                                   # what this machine pulled
```

If they differ and the release notes do not explain it, swap all three `image:` lines to
`@sha256:12b7348b6727b756b8155c5157804bc05ef5d0ffa5f42bc6307747bd18425a36` — the exact image Gate 23
validated — keep the tag in a comment for readability, and record what prompted the switch here.

**Why this changed.** Gate 23 recorded "stopping and starting the stack re-runs setup, and every
previously issued token stops verifying" as a property of ThunderID. It is not — it was a property of
*our compose file*. Setup was listed as an ordinary service, and `compose up` recreates one-shot
containers rather than reusing exited ones. The vendor's own Docker path runs `setup.sh` as a
one-time `docker run --rm` and starts the server separately. Both init steps now sit behind a
`profiles: ["init"]` guard, which Compose does not start unless `--profile init` is passed, and the
server's `depends_on` for setup is gone. Restarting the stack is now safe, which matters more in
Gate 24 than it did in Gate 23 — real user sessions will span work sessions. The underlying
non-idempotency is real and vendor-documented ("Setup is not idempotent—rerunning it regenerates all
keys"); it is simply no longer triggered by ordinary use.

---

## The gates

Gate numbering and status live in `docs/PLAN.md`'s progress table, which is the single status board
for the project. What follows is what each gate has to *do*; whether it is done is recorded there,
not here.

Each gate ends with the project's standard stop gate: stop, explain in plain language, list every
file changed and why, re-check the rest of the plan, hand off for the developer to commit manually,
wait for "continue".

### Gate 22 — this document

Docs only, no code. Rewrite this file against current documentation, split the old single auth gate
into four, and record the new gates in `PLAN.md` before any work starts against them. Exists so the
plan survives a lost session and so the numbering is not backfilled afterwards.

### Gate 23 — the spike ✅ **PASSED, 2026-08-18**

**The spike passed. ThunderID stops being provisional and is the chosen provider.** Keycloak is no
longer the fallback-in-waiting; it returns to the rejected list.

Everything below was run against a live ThunderID `v1.0.0` on `https://localhost:8090`. Nothing was
merged into the application — the verifier script was written to a scratch directory and deleted.

#### What was set up

| Thing | Value |
| --- | --- |
| Resource server | `Agentic ERP API`, type **API** |
| Identifier (becomes `aud`) | `https://api.agentic-erp.local` |
| Delimiter | `.` — set at creation, immutable, matches `services/` exactly |
| Resources / actions | `product` → `read`, `create`, `update`; `stock` → `adjust` |
| Agent | `Test Agent`, confidential, `client_secret_basic` |
| Grants enabled | `client_credentials`, `authorization_code`, token exchange |
| Permissions granted via | a **role** (`Product Reader`) assigned to the agent — not attached to the agent directly |

#### What the spike found

Five results, in plain terms.

**1. It works.** A token request came back with exactly the permission asked for
(`scope: "product.read"`), stamped for the right service (`aud: https://api.agentic-erp.local`), and
a verifier built on `mcp==2.0.0`'s interface accepted it. That was the gate's exit condition and it
is met.

**2. Bad tokens are rejected properly.** A token meant for a different service was refused
(`InvalidAudienceError`), and a token with a tampered signature was refused
(`InvalidSignatureError`). Both matter: the first is the check the MCP spec *requires*, and the
second confirms the signature check is real rather than decorative.

**3. An agent cannot give itself more power than it was handed — this is the important one.**
The test that matters for Gate 25: the agent's role grants it all six permissions including
`stock.adjust`. We handed the exchange a token carrying only `product.read` and asked for
`product.read stock.adjust`. **ThunderID returned only `product.read`.** It refused to hand back
more authority than the incoming token carried, *even though the agent itself was allowed that
much*. That is precisely the "the agent may only do what the user may do" guarantee this whole
design rests on, and it is now proven rather than assumed.

**4. Asking for too much does not produce an error — it quietly gives you less.** ⚠️ **This
contradicts the documented behaviour and is the finding most likely to cause a bug later.** The docs
say over-asking is rejected with `invalid_scope`. It is not. The server answers `200 OK` and simply
returns a smaller `scope` than requested. A separate test asking for a permission that does not
exist at all (`admin.delete`) was worse: it returned a valid token with the scope field **missing
entirely**, rather than any error.

> **Rule for Gate 25:** always read the `scope` that came *back*. Never assume that "no error" means
> "I got what I asked for", and never treat a missing scope as harmless — it is indistinguishable
> from a request that was silently gutted.

**5. Nothing records who delegated to whom unless you ask.** The `act` claim was absent everywhere
we did not explicitly supply an `actor_token`. Downscoping is enforced; the *audit trail* of who
narrowed it is not automatic. Noted for Gate 25 — our own `created_by` / `updated_by` columns carry
the accountability we actually need, so this is a "know it" rather than a "fix it".

#### One correction that creates real work: the SDK ships no verifier

`mcp==2.0.0`'s `TokenVerifier` is a **Protocol** — an interface with a single `verify_token` method
and no implementation behind it. The only concrete class in the package is `ProviderTokenVerifier`,
which just delegates elsewhere. Its docstring points at an `IntrospectionTokenVerifier` as the
"dedicated implementation" to prefer — **that class does not exist in the installed package.**

Checked against current sources on 2026-08-18: `mcp` 2.0.0 (2026-07-28) is still the latest release,
and [the official SDK docs](https://py.sdk.modelcontextprotocol.io/run/authorization/) confirm the
SDK ships no concrete verifier. `IntrospectionTokenVerifier` exists only as sample code in the SDK
repository's `examples/` folder, and it is introspection-based — it calls the identity server on
every single request — rather than checking the signature locally. Not what we want.

Two things follow:

- **Gate 25 writes the verifier.** Roughly 55 lines, and the whole shape is: fetch the signing keys
  from `/oauth2/jwks`, look up the one matching the token's `kid`, check the signature, check `aud`
  and `iss` and expiry, and return an `AccessToken` with `scopes` split out of the `scope` claim.
  `jwt.PyJWK` consumes a JWKS entry directly, so key handling is two lines. This was already
  budgeted ("~40 lines"), so it is a confirmation rather than a surprise — but it is *code we own*,
  not configuration.
- **The self-signed certificate will bite.** The spike had to disable TLS verification to fetch the
  JWKS at all. That is acceptable in a throwaway script and **not** acceptable in Gate 25 — the
  deployed ThunderID needs a real certificate, or its CA must be trusted explicitly. Do not carry
  the `verify=False` shortcut forward.
- **Do not reach for FastMCP's `JWTVerifier`.** Searching for this problem surfaces a ready-made
  `JWTVerifier` with exactly the JWKS support we want. It belongs to **FastMCP** (`jlowin/fastmcp`),
  a different third-party package, not the official SDK. Adopting it means a new dependency and a
  different server framework — and per the note at the end of this file, FastMCP's own pins would
  drag `mcp` back below 2.0. Rejected for the same reason recorded there.

`pyjwt 2.13.0` and `cryptography` are **already installed** in `backend/.venv` as transitive
dependencies, so no new package is needed — but `jwt` must still be added to **both**
`forbidden_modules` lists in `backend/pyproject.toml` before `api/` imports it, or `services/` could
import it too and the boundary quietly weakens.

#### Traps found in the console, worth knowing before Gate 24

- **Permissions are granted through a *role*, not directly on the agent.** The agent's Access tab
  only lists groups and roles. Create a role, attach the resource-server permissions to it, then
  assign the role to the agent. A token minted before that step succeeds but carries **no scope at
  all** — which, per finding 4, looks identical to a request that was silently narrowed.
- **`client_secret_basic` vs `client_secret_post` is not interchangeable.** The agent is configured
  for exactly one, and using the other fails with `unauthorized_client` — a message that reads like
  a permissions problem when it is really a "you sent the password in the wrong envelope" problem.
  This agent uses **`client_secret_basic`** (credentials in the `Authorization` header).
- **Turning on Delegated mode force-enables `authorization_code`**, which then demands at least one
  redirect URI before the form will save, and cannot be unticked. Supply the frontend's eventual
  callback URL and move on.
- **The ThunderID stack's setup step is not idempotent.** Stopping and starting the containers
  re-runs it, which regenerates the admin console password and the JWT signing keys. Registrations
  in the database survive; **every previously issued token stops verifying.** See
  `.claude/problems/thunderid-mcp-access.md` for the full note. (its gitignored)

#### The compose file, and the pin that was missing

`deploy/docker-compose.thunderid.yml` is committed, adapted from ThunderID's official quick-start
with **one deliberate change: the image is pinned instead of floating on `latest`.**

That change is not housekeeping. The upstream quick-start uses `:latest` for all three containers,
and that is exactly how this project's ThunderID moved from `v1.0.0-rc` to `1.0.0` between two
sessions with nobody upgrading anything. It happened to be a harmless move; the next one might not
be, and for the component holding the entire login system an unannounced upgrade is not acceptable.

⚠️ **The image tag has no leading `v`.** The git tag is `v1.0.0`; the image tag is `1.0.0`.
`ghcr.io/thunder-id/thunderid:v1.0.0` is a 404. Verified against the registry — this is the kind of
detail that costs twenty minutes to a "why won't it start".

Pinned version: **`1.0.0`**, released 2026-08-15, digest
`sha256:12b7348b6727b756b8155c5157804bc05ef5d0ffa5f42bc6307747bd18425a36`.

The compose file carries the self-signed-certificate and non-idempotent-setup warnings inline, so
they are read at the moment someone starts the stack rather than only here.

### Gate 24 — human auth end-to-end

**Verified against the vendor's current Next.js guide on 2026-08-18**, so the names below are copied
rather than guessed. Fetch `.../connect-your-application/nextjs.md` (the `.md` suffix serves the raw
markdown) at the start of the gate rather than trusting this table — the vendor's own integration
skill was rewritten to do exactly that, which is a strong hint the details move.

- `frontend/`: `@thunderid/nextjs`, `ThunderIDProvider` — imported from the **`/server` subpath** —
  in `src/app/layout.tsx`, the proxy with `thunderIDProxy` + `createRouteMatcher` over the product
  routes, sign-in UI in the existing `components/shell/` built from `SignedIn`, `SignedOut`,
  `SignInButton`, `UserDropdown`, plus `SignIn` for the embedded approach.

  ⚠️ **Corrected while building: the proxy file is `frontend/src/proxy.ts`, not `proxy.ts` at the
  project root.** Two things moved at once and both are easy to get wrong. Next 16 deprecated the
  `middleware` file convention and renamed it to `proxy`; and the file must sit *at the same level
  as `app`*, which in this project's `src/` layout is `src/`. "Project root" is right only for an
  app without `src/`. Source: `node_modules/next/dist/docs/.../file-conventions/proxy.md`. A proxy
  in the wrong place is not an error — it is simply never invoked, so every route silently stays
  public.

  **Decided while building: there is no `/signup` route and no `NEXT_PUBLIC_THUNDERID_SIGN_UP_URL`**,
  though the vendor's quickstart creates both and lists the variable as required. Aisle is a
  supermarket's internal system: accounts are created by an administrator in the Console, and a
  self-service registration form on a login page anyone can reach would let a stranger create an
  account against live inventory. The **Sign-Up and Recovery flows are switched off on the
  application's Flows tab** to match — the toggle and the missing route have to agree, or one of
  them is a lie. (Recovery is off for a second, duller reason as well: there is no mail server.)

  **Also decided while building: the app shell renders inside `<SignedIn>`, and `/signin` renders
  bare.** Not a cosmetic choice. `AgentPanel` starts a conversation against `/api/agent` on mount,
  and that route is protected, so mounting the shell on the sign-in page would fire a request that
  gets redirected straight back to the sign-in page. `ThemeProvider` stays above the split so the
  sign-in screen still themes correctly.
- **Environment variables**, confirmed spellings. **⚠️ This block is the embedded-mode set and is
  superseded** — four of these are wrong or dead now that the app was re-registered in redirect
  mode. `THUNDERID_FLOW_SECRET` no longer exists on a Gate application, and
  `NEXT_PUBLIC_THUNDERID_AFTER_SIGN_IN_URL` must be left **unset**, not pointed at `/products`. Read
  the "⚡ Superseded — the AIsle Gate application" and "⚠️ Corrected — AFTER_SIGN_IN_URL is the
  redirect_uri" blocks below before copying anything from here; `frontend/.env.example` is the
  living version.

  ```dotenv
  NEXT_PUBLIC_THUNDERID_BASE_URL=https://localhost:8090
  NEXT_PUBLIC_THUNDERID_APPLICATION_ID=<Console → General → Quick Copy>
  THUNDERID_FLOW_SECRET=<shown once at creation; regenerate from the Credentials tab>
  NEXT_PUBLIC_THUNDERID_SIGN_IN_URL=/signin
  NEXT_PUBLIC_THUNDERID_SIGN_UP_URL=/signup
  THUNDERID_SECRET=<openssl rand -base64 32>
  NODE_TLS_REJECT_UNAUTHORIZED=0    # local only — see below
  ```

  Note this is **two values from the Console, not one**: Application ID *and* Flow Secret. The
  Application ID is distinct from the Client ID and they are easy to confuse. The Flow Secret is
  displayed once.

  **Re-verified 2026-08-23 against two independent vendor sources, and the installed skill is the
  one that is wrong.** `thunderid-integrate-nextjs` v0.2.0 step 4 gives the embedded block as
  `THUNDERID_CLIENT_SECRET`. Both live sources say `THUNDERID_FLOW_SECRET`:

  - the **v1.0.0 Console itself**, via the "Integrate with a coding agent → Copy prompt" button on
    the application's Overview tab, which emits the env list and adds: *"THUNDERID_FLOW_SECRET is a
    separate credential from an OAuth2 client secret; it authenticates this app when the native
    (embedded) flow starts and is sent in the `Flow-Secret` request header, never in the client
    secret's place"*;
  - the docs site at `/docs/v1.0.x/getting-started/connect-your-application/nextjs/`, whose `.env`
    block for custom-UI mode contains **no client secret at all**.

  So this is not two names for one value — **it is a different credential from the OAuth client
  secret**, carried in its own header, and the embedded flow does not use a client secret. Do not
  "fix" this to `CLIENT_SECRET`; that mistake was made and reverted on 2026-08-23.

  The Console's **Copy prompt** button is the highest-value source here: it is generated by the
  running server, so it cannot drift from the deployed version the way a cached skill can. **Prefer
  it over the skill for anything ThunderID.**

  ⚠️ **Found while building, then resolved as a limitation: sessions do not refresh.** `NEXT_PUBLIC_THUNDERID_CLIENT_ID` and `THUNDERID_CLIENT_SECRET` are absent
  from both the docs block and the Console's Copy prompt, because neither is used to *sign in* —
  the Flow Secret does that. They are what keeps a user signed in. `thunderIDProxy` refreshes the
  access token before expiry, and its own doc comment says: *"Token refresh requires baseUrl,
  clientId, and clientSecret... If none are available the refresh step is skipped silently."*
  Skipped silently, and then the session cookie is cleared — so without them everything works for
  about an hour and then signs the user out mid-task with nothing logged. This also explains the
  oddity noted on 2026-08-23 that the SDK types `clientSecret` as required while `flowSecret` is
  optional: they are **four independent config fields with no fallback between them**
  (`utils/decorateConfigWithNextEnv.js`), so the Application ID is not reused as `clientId` and the
  Flow Secret is not reused as `clientSecret`.

  **And a Next.js application in the v1.0.0 Console never issues that pair.** Checked all five tabs
  on 2026-08-23: Credentials shows the Application ID and the Flow Secret only; Overview shows the
  Application ID, Organization Unit ID and handle; there is no General tab, which is where the docs
  say a Client ID would appear for an OAuth 2.0 application. The Console's **"Regenerate Client
  Secret"** button sits over the *Flow Secret* field — the fourth instance of this vendor using two
  names for one thing, and it is why the client-secret question keeps reopening. It is not a second
  credential.

  **So the refresh path cannot run, by construction.** ⚠️ **True only of the embedded-mode app
  described above, which no longer exists — see the ⚡ Superseded block immediately below, and the
  2026-08-25 re-read confirming `refresh_token` is enabled with an 86400 s window. Nothing in this
  paragraph, including the "Gate 26 must resolve it" instruction, is current.** A session works
  until the access token
  expires, at which point `thunderIDProxy` clears the session cookie and the user lands back on
  `/signin`. That is the expected behaviour of this configuration, not a bug to hunt. Acceptable
  locally; **Gate 26 must resolve it** — most likely by registering a proper OAuth application
  alongside this one, or by raising the access-token lifetime. Do not "fix" it by pasting the Flow
  Secret into `THUNDERID_CLIENT_SECRET`: the client id would still be missing, and
  `hasRefreshConfig` needs all three.

  ---

  #### ⚡ Superseded 2026-08-23 — the `AIsle Gate` application (redirect mode)

  The limitation above was resolved the way the Gate 26 note predicted, but earlier: **a second
  application, `AIsle Gate`, was created with Sign-In Approach = redirect ("Gate") instead of
  "Bring Your Own UI".** That application *is* a real OAuth confidential client, so `clientId` and
  `clientSecret` exist and `hasRefreshConfig` is satisfied. Everything above stays on the page as
  the record of why embedded mode was abandoned; **the configuration below is the live one.**

  The sign-in approach is chosen at creation and cannot be changed afterwards — that is why a new
  application was needed rather than an edit. The old `AIsle Web` application stays registered until
  the new one has signed a real user in; then it is deleted.

  **What each Console tab holds for `AIsle Gate`** (v1.0.0, recorded 2026-08-23 from the Console):

  | Tab | Contents |
  |---|---|
  | **Overview** | Application details: **Application ID** `01a02dcc-300a-7bc5-…` (full value in the Console), **Client ID** `vAf_zSFT1qj4733Xy3jgQw` — the field the old app showed as `-`, Organization Unit ID `01900000-0000-7000-8000-000000000001`, handle `default`. Also a live **Preview** of the hosted sign-in screen, a flow summary, and the **"Integrate with a coding agent → Copy prompt"** button. "Useful Endpoints" still lists the *flow execution / flow metadata / passkey registration* endpoints — those are for custom UI and are **not used in this mode**; their presence is not an instruction. |
  | **Access** | Allowed User Types = `Person`. Application URL (homepage) — blank, optional. |
  | **Credentials** | **Client ID** (public identifier) and **Client Secret** (masked, with "Regenerate Client Secret" — here the button really does mean the client secret, unlike the old app where it sat over the Flow Secret). Certificate Type = `None`. **There is no Flow Secret on this tab** — that credential belongs to embedded mode only. |
  | **Flows** | Sign-in = `AIsle Gate Sign-in Flow`. **Sign-up: off. Recovery: off** — matching the no-`/signup` decision above. Sign-out = `Default Sign Out Flow`. So a Gate app still runs the flow engine; the difference is *where* the flow renders (ThunderID's page, not ours). |
  | **Customization** | Theme **Acrylic Purple**, Layout **Centered** — these now matter, because the sign-in screen the user sees is ThunderID's, not ours. Terms-of-Service / Privacy-Policy URIs and admin contacts: blank. |
  | **Token** | Attributes selectable into the access token and the ID token / userinfo (`email`, `groups`, `roles`, `userType`, `ouid`, `username`, …) — **none added yet**. The sample access-token payload is `aud, client_id, exp, grant_type, iat, iss, jti, nbf, scope, sub`. Access-token validity **3600 s**; separate validity tabs for ID token and refresh token. |
  | **Advanced** | Grant types `authorization_code` + **`refresh_token`** — the thing embedded mode could not have. Response type `code`. **Authorized redirect URIs: `http://localhost:3000`** (bare origin, no path — matches `getClientOrigin.js`, which returns proto + host only). Post-logout redirect URIs: `http://localhost:3000`. Client auth method `client_secret_basic`; **Public Client off** (confidential), **PKCE required on**, PAR off. Identity Assertions (**ID-JAG**) toggle present and **off** — this is the Gate 25 lever. Default audience blank, with the note *"Leave empty to use the application client ID"*. |

  ##### ✅ Re-read from the running server, 2026-08-25

  The table above was transcribed from the Console by eye at registration time. Read back from
  ThunderID's admin API on 2026-08-25 — same application, no changes made — it holds up, and adds
  three numbers that were not recorded:

  | Field | Value | Note |
  |---|---|---|
  | `grantTypes` | `["authorization_code", "refresh_token"]` | Refresh really is enabled |
  | `refreshToken.validityPeriod` | **86400** (24 h) | Not previously recorded |
  | `accessToken.validityPeriod` | 3600 (1 h) | Matches |
  | `idToken.validityPeriod` | 3600 | Not previously recorded |
  | `includeActClaim` | **false** | This is the ID-JAG toggle. Off, as intended — Gate 25's lever |
  | `pkceRequired` | true | Matches |
  | `publicClient` | false | Confidential, matches |
  | `tokenEndpointAuthMethod` | `client_secret_basic` | Matches |
  | `dpopBoundAccessTokens` | false | Not previously recorded |
  | `requirePushedAuthorizationRequests` | false | PAR off, matches |
  | `redirectUris` / `postLogoutRedirectUris` | `["http://localhost:3000"]` | Bare origin, matches |
  | `allowedUserTypes` | `["Person"]` | |
  | `isRegistrationFlowEnabled` / `isRecoveryFlowEnabled` | false / false | Matches the no-`/signup` decision |

  **What this settles: the 24-hour refresh window is a fact, not an assumption.** A session should
  now survive the 1-hour access-token expiry and last up to 24 hours. Still not *observed* — nobody
  has sat through an hour — but the registration permits it and, per the SDK reading further down,
  `thunderIDProxy` renews from the refresh token in the session cookie once `clientId` and
  `clientSecret` are present, which they now are in `frontend/.env.local`.

  **What it does not settle: the audience.** `Default Audience` is **blank**, and that is the
  *correct* state, not an oversight — it is only the fallback `aud` for tokens that do not target a
  resource server. The setting that actually drives `aud` is the **default-resource-server flag,
  which lives on the resource server, not on the application**, and the admin API exposes no
  resource-server tool (17 tools: applications, flows, themes, org units, user types, SDK snippets).
  So `Agentic ERP API` / `https://api.agentic-erp.local` being registered and default rests on the
  manual Console change recorded here on 2026-08-23 plus the `aud` decoded from a real token that
  day — not on anything read from the server since. That is good evidence, not verification. To
  verify properly: read it in the Console, or decode `aud` from a freshly minted token.

  **Two consequences worth carrying forward:**

  1. ~~**Backend token validation (this gate) should expect `aud` = the client ID**
     (`vAf_zSFT1qj4733Xy3jgQw`), because Default Audience is blank.~~ **⚠️ Superseded — do not
     follow this.** Note the reasoning was wrong as well as the conclusion: a blank Default Audience
     does not imply the client ID will be used, because a token targeting a resource server takes
     its `aud` from there instead. It was correct when written and stopped being correct the moment the
     `Agentic ERP API` resource server was registered, which is exactly the "if a Resource Server is
     registered later" case the original sentence flagged. The real audience, read off a live token
     and confirmed against `THUNDERID_AUDIENCE` in `core/config.py`, is
     **`https://api.agentic-erp.local`** — the resource server's identifier, not the client ID. See
     the decoded token further down this file. Configuring the client ID here would make the backend
     reject every valid token.
  2. **ID-JAG is a toggle on this application**, not a separate feature to build. Gate 25 turns it
     on; leave it off until then, consistent with the ID-JAG-later rule.

  **`.env.local` changes for Gate mode** — four are wrong or dead right now:

  | Variable | Action |
  |---|---|
  | `NEXT_PUBLIC_THUNDERID_CLIENT_ID` | ✅ set to the Gate app's Client ID. |
  | `THUNDERID_CLIENT_SECRET` | ✅ set (shown once at creation). |
  | `NEXT_PUBLIC_THUNDERID_APPLICATION_ID` | ⚠️ **still the old `AIsle Web` id (`01a02d7e-…`)** — replace with the Gate app's `01a02dcc-…`, or delete it. It is optional: `server/ThunderIDProvider.js` only spreads it into the flow-metadata lookup when present. Leaving a *stale* id is worse than having none, because metadata is then fetched for the wrong application. |
  | `NEXT_PUBLIC_THUNDERID_SIGN_IN_URL` | ⚠️ **must be removed.** This is the one that silently breaks redirect mode. `SignInButton` does `if (signInUrl) router.push(signInUrl); else if (signIn) await signIn(...)` — so while it is set, the button navigates to our local `/signin` and **never** reaches `client.getAuthorizeRequestUrl()`, which is what produces the ThunderID authorize URL. Unset it and the same button redirects to the gate. |
  | `THUNDERID_FLOW_SECRET` | Dead in this mode — the flow runs on ThunderID's side, so nothing sends the `Flow-Secret` header. Remove it once the Gate app signs someone in. |
  | `NEXT_PUBLIC_THUNDERID_SIGN_UP_URL` | Already removed; stays removed. |
  | `NEXT_PUBLIC_THUNDERID_AFTER_SIGN_IN_URL` | ⚠️ **Must stay unset — corrected 2026-08-23, see below.** Despite the name it is not a landing page: it becomes the OAuth `redirect_uri`. |
  | `NEXT_PUBLIC_THUNDERID_SCOPES` | ✅ **Added 2026-08-23.** `openid product.read product.create product.update stock.adjust` — the permissions on the `Agentic ERP API` resource server, verbatim. Without it the token carries no scope and every `actor.can()` fails. |
  | `THUNDERID_SECRET`, `NEXT_PUBLIC_THUNDERID_BASE_URL`, `NODE_TLS_REJECT_UNAUTHORIZED` | Unchanged. |

  **Frontend changes made 2026-08-23**, after the Console's regenerated Copy prompt confirmed the
  variable list above (it asks for `BASE_URL`, `CLIENT_ID`, `CLIENT_SECRET`, `THUNDERID_SECRET` and
  nothing else, and drops `<SignIn>` entirely):

  - `src/app/signin/page.tsx` **deleted**. The sign-in screen is ThunderID's now.
  - `src/app/page.tsx` **is the signed-out landing** and no longer redirects to `/products`; that
    redirect is `NEXT_PUBLIC_THUNDERID_AFTER_SIGN_IN_URL=/products` instead.
  - `src/proxy.ts` — **`"/"` removed from the matcher.**

    ⚠️ **This one corrects an earlier instruction in this document, and it is the sharpest edge in
    the mode switch.** The first draft of this block said to delete the `<SignedIn>`/`<SignedOut>`
    split from the layout because "nothing renders bare any more". That is wrong. Reading
    `server/proxy/thunderIDProxy.js` (lines 160–168): `protectRoute()` redirects to
    `routeOptions?.redirect ?? resolvedConfig.signInUrl ?? fallbackRedirect`, and `fallbackRedirect`
    is `"/"`. With `signInUrl` unset — which Gate mode requires — a protected `/` redirects to
    itself. So `/` must stay public and carry the `<SignInButton>`, and the split in `layout.tsx`
    **stays**, for its original reason: `AgentPanel` POSTs to the protected `/api/agent` on mount,
    so the shell must not render for a signed-out visitor.
  - `components/shell/user-menu.tsx`, `src/lib/api/client.ts` and `src/lib/auth/current-user.ts` are
    unchanged apart from comments that named `/signin`.

  #### ⚠️ Corrected 2026-08-23 — `AFTER_SIGN_IN_URL` is the `redirect_uri`, not a landing page

  The row above originally said to set this variable, and the first Gate-mode commit set it to
  `/products`. That is wrong, and it fails *before* the login screen renders rather than after, which
  makes it look like a Console misconfiguration. The chain, read out of the installed package:

  ```text
  ThunderIDNextClient.js:22    afterSignInUrl: afterSignInUrl ?? origin
  javascript/dist/index.js:3002  redirectUri: configData.afterSignInUrl ?? ""
  javascript/dist/index.js:2745  authorizeRequestParams.set("redirect_uri", redirectUri)
  ```

  So the value is passed verbatim as the OAuth `redirect_uri`. `/products` is not
  `http://localhost:3000`, the Authorized Redirect URI check fails, and no amount of Console editing
  helps unless you register the path — which would then also have to be the callback route, and
  `getClientOrigin.js` only ever produces an origin. **Leave it unset**: the `?? origin` fallback
  yields exactly the registered value.

  The post-sign-in hop to `/products` moved into the app instead:
  `components/shell/after-sign-in-redirect.tsx`, rendered from `app/page.tsx` inside `<SignedIn>`.
  It has to be client-side and effect-driven, because `/` is *also* the OAuth callback URL — a
  server-side session check would run before `ThunderIDProvider` has completed the code exchange and
  would bounce a valid callback.

  **Also settled here: `resource` (RFC 8707) cannot be sent on the authorize request.**
  `server/actions/signInAction.js:41` calls `getAuthorizeRequestUrl({}, sessionId)` with customParams
  hardcoded to `{}`. Audience targeting for human sign-in therefore has to come from the
  application's **Resource Servers** list, via the default flag described below — *not* the
  application's Default Audience field, which stays blank.
  Scopes *can* be sent, via `NEXT_PUBLIC_THUNDERID_SCOPES` → `getSignInUrl` (`index.js:3004`).

  **Still unverified as of 2026-08-23:** Gate 23 only exercised `client_credentials` and token
  exchange. Whether an *authorization_code* token honours Default Audience and carries resource-server
  permissions has not been observed. Confirm by decoding a real token before writing the verifier —
  per Gate 23 finding 4, a silently scopeless token is indistinguishable from a working one.

  #### ⛔ Observed 2026-08-23 — `invalid_target`: Default Audience does not target a resource server

  First run of the redirect flow. `/oauth2/authorize` refused the request outright and bounced back
  to `http://localhost:3000/?error=invalid_target&error_description=No+resource+parameter+supplied+and+no+default+resource+server+is+configured`.

  This answers the "still unverified" question above in the negative, and it is a **configuration
  gap, not a bug in our code** — the sign-in card rendered, the button fired, and the authorize URL
  was well-formed. Three facts settle the shape of it:

  1. **Default Audience is not the same setting as "default resource server".** The Console's own
     help text under the field says *"The default aud for access tokens that **don't target a
     resource server** (OIDC only or scopeless)."* It is the fallback for scopeless tokens, not a
     way to bind scoped ones. **It should be left blank.** Once the token does target a resource
     server, `aud` comes from that server's identifier and this field is never consulted. An earlier
     revision of this document told the developer to fill it in; that instruction was wrong and did
     nothing either way.
  2. **Requesting `product.read` et al. makes the token scoped**, so ThunderID must resolve those
     permission strings to a resource server, and it will not guess.
  3. **The SDK cannot send `resource`.** `server/actions/signInAction.js:41` calls
     `getAuthorizeRequestUrl({}, sessionId)` with customParams hardcoded to `{}`; `getClient` is not
     exported and the package's `exports` map blocks deep imports, so there is no supported seam.
     Building the authorize URL ourselves would mean owning PKCE and the `state` format the SDK's
     callback handler expects — i.e. forking it. Rejected.

  So the target has to be configured **server-side**, in the Console. Silver lining for Gate 25: the
  error proves `/oauth2/authorize` *does* implement RFC 8707 resource indicators, which is what the
  MCP authorization spec requires.

  **Resolved: `Resource Servers` → row menu → "Set as default".** ThunderID v1.0.0 ships **two**
  resource servers, and the built-in one holds the default flag out of the box:

  | Name | Type | Identifier | Default |
  |---|---|---|---|
  | `Agentic ERP API` | API | `https://api.agentic-erp.local` | — |
  | `System` | Custom | `https://localhost:8090/mcp` | ✅ shipped as default |

  `System` is **ThunderID administering itself** — the admin MCP endpoint this project deliberately
  does not use (see the note further down on why: it needs the `system` scope). Its permission
  vocabulary is ThunderID's own, so `product.read` could never resolve against it. Moving the flag to
  `Agentic ERP API` is therefore correct, and the dialog confirms the semantics exactly: *"When an
  application requests a token without naming a resource server, its permissions come from this one.
  Only one resource server can be the default at a time."*

  ⚠️ **Not fully explained:** the flag was already on `System` when the request failed, yet the error
  said *no* default was configured. Either the built-in is not eligible as a general default, or it
  is scoped elsewhere. Worth remembering if the symptom recurs; not worth blocking on.

  ⚠️ **Gate 25 trap:** `System`'s identifier ends in `/mcp`, which looks like it might be *our* MCP
  server. It is not. `backend/mcp_server/` will need its own resource server registered under its own
  URL.

  **Fallback if the default flag turns out not to help:** set `NEXT_PUBLIC_THUNDERID_SCOPES=openid`. The
  token then falls under Default Audience, arrives with the right `aud` and **no permissions**, and
  Gate 24 delivers authentication without authorization — `TokenActor.can()` would have nothing to
  test. That is a real reduction in scope for the gate, not a workaround, and it should be recorded
  as such rather than absorbed quietly.

  No OAuth callback route was added, and none is needed: the vendor prompt states it outright
  (*"The ThunderIDProvider handles the OAuth callback automatically"*), and
  `client/contexts/ThunderID/ThunderIDProvider.js` reads `code`/`state` off the URL on mount. That
  is why the Authorized Redirect URI is the bare origin.

  Also note `THUNDERID_SECRET` is **not** a ThunderID value despite the name, and is not
  `THUNDERID_FLOW_SECRET` with a word missing: it signs our own session cookie and is never sent to
  ThunderID.
- The **developer creates the Application in the Console** — Applications → Add Application →
  Technology **Next.js**, Sign-In Approach **"Redirect to ThunderID" (Gate)** ⚠️ *not* the "Bring
  Your Own UI" default, which this gate tried first and abandoned (see the superseded block above)
  — and `http://localhost:3000` as both Authorized Redirect URI and Post-Logout Redirect URI, then
  reports the Client ID and Client Secret back. The
  assistant never touches the Console. (ThunderID does expose an admin MCP server that could create
  the application programmatically — see "Two capabilities noted" — and it is deliberately not used:
  it requires administrator credentials and the `system` scope, which is more authority than this
  project grants an assistant for a five-minute one-time task.)
- ~~⚠️ **The one real unknown in this gate.**~~ **Closed 2026-08-23, by reading the installed
  package rather than any documentation.** The question was how to obtain an access token for calling
  an *external* API, which `client.ts` needs to attach `Authorization: Bearer` to FastAPI calls. The
  vendor's quickstart never mentions it; `@thunderid/nextjs` **1.0.6** answers it directly. Its
  `/server` subpath exports an undocumented `thunderid()` helper:

  ```ts
  const { getAccessToken, exchangeToken, getSessionId } = await thunderid()
  getAccessToken(sessionId)                 // => Promise<string>  — the raw access token
  exchangeToken(config, sessionId)          // => RFC 8693 token exchange
  ```

  Two consequences:

  1. `client.ts` calls `getAccessToken` and needs no workaround — no cookie parsing, no custom
     refresh, since the session cookie carries the refresh token and the SDK renews from it.
  2. **`exchangeToken` is RFC 8693 delegation, already implemented in the SDK.** Gate 25 assumed
     that call would be hand-rolled. Read this before starting Gate 25.

  The session cookie is itself a `jose`-signed JWT carrying `sub`, `scopes`, `exp` and `sessionId`,
  and `SessionManager`'s own doc comment says *"Never use the returned payload for authorization."*
  That matches this project's rule exactly: `sub` comes from a verified token, permission checks
  live in `services/`. Do not shortcut it by trusting the cookie.

  **Method note worth generalising:** the installed SDK is **1.0.6** while the server is **1.0.0**,
  and the SDK is ahead of both the docs site and the skills cache. For anything ThunderID-shaped,
  `grep` the package in `node_modules` before believing prose.
- ⚠️ `NODE_TLS_REJECT_UNAUTHORIZED=0` is the frontend's version of the spike's `verify=False`. Same
  rule: acceptable locally, **must not survive to Gate 26**. The vendor's own guides mark it
  "Remove in production".
- `frontend/src/lib/auth/current-user.ts`: a real session read, replacing `{ id: "system" }`. It is
  already `async`, so no call site changes — and in fact it has **no call sites at all** today; it is
  a seam kept ready, not a load-bearing module. Its return type widened to `CurrentUser | null`.
  It decodes the `sub` claim **without verifying the signature**, which is correct only because the
  value labels a screen and decides nothing: every authorization question is answered in
  `services/`, against a token the backend verifies against JWKS. The SDK draws the same line —
  *"Never use the returned payload for authorization."* If this value ever starts gating something,
  that is the bug.
- `frontend/src/lib/api/client.ts`: attach `Authorization: Bearer` via `api.use({ onRequest })`.
  Note this file currently builds a module-level client at import with no per-request hook, so this
  is a structural addition rather than a one-line edit. It stays inside `lib/api/`, so the ESLint
  restricted-import rule is unaffected.
- `backend/`: `TokenActor` beside `SystemActor` in `core/actor.py`; JWKS validation in `api/deps.py`'s
  `get_actor()`; `pyjwt[crypto]` added to `requirements.txt` **and** to both `forbidden_modules`
  lists.
- Tests for `TokenActor.can()` and for a rejected or expired token.

**Exit condition:** a real user signs in, the product pages work, `created_by` records their OIDC
`sub` instead of `"api"`, and an unauthenticated request gets a 401.

#### ✅ Gate 24 backend — built and verified 2026-08-23

**The token, captured from a real sign-in** (the whole point of the gate; every
assumption below is now observed rather than predicted):

```json
{
  "aud": "https://api.agentic-erp.local",
  "iss": "https://localhost:8090",
  "scope": "openid product.read product.create product.update stock.adjust",
  "sub": "01a02d8f-0355-74cd-b102-3b1ab2372d64",
  "client_id": "vAf_zSFT1qj4733Xy3jgQw",
  "grant_type": "authorization_code",
  "exp": 1787498781, "iat": 1787495181, "nbf": 1787495181,
  "jti": "...", "tfid": "..."
}
```

Note `aud` is the **resource server's identifier**, not the client id — because
`Agentic ERP API` is now the default resource server. The permission strings
arrive exactly as `services/` already spells them, which is what the `.`
delimiter was chosen for at Gate 23.

**What was built:**

| File | Role |
|---|---|
| `backend/authn/` **(new package)** | `verify_access_token()` — JWKS lookup, RS256, `aud`/`iss`/`exp` checks. See below for why it is not in `core/` |
| `core/actor.py` → `TokenActor` | `can()` is set membership over the `scope` claim. Stores claims; validates nothing |
| `core/exceptions.py` → `AuthenticationError` | 401, distinct from `PermissionDeniedError`'s 403 |
| `api/deps.py` → `get_actor()` | Reads the bearer header, verifies, returns the actor. `HTTPBearer(auto_error=False)` so the 401 keeps this API's error envelope |
| `api/errors.py` | Adds the 401 mapping **and `WWW-Authenticate: Bearer`** — RFC 6750, and required of a resource server by the MCP spec |
| `core/config.py` | `thunderid_issuer` / `_jwks_url` / `_audience` / `_verify_tls` / `auth_enabled` |
| `tests/test_auth.py` | 13 tests, no network — see below |
| `tests/test_api_products.py` | +2 end-to-end through the adapter: no token → 401, valid token without the scope → 403 |

**Why `authn/` is a fourth top-level package.** `core/` and `services/` are
forbidden from importing `jwt` (added to **both** `forbidden_modules` lists this
gate), and `api/` cannot host it because `mcp_server/` needs the identical
verification at Gate 25 and the two adapters may never import each other. So it
gets its own import-linter layer, between the adapters and `services/`.

**Tests run with no ThunderID and no network.** A throwaway RSA key pair is
generated in-process and `_jwk_client` is stubbed, so key *use* is exercised for
real — algorithm pinning, audience, issuer, expiry, required claims — while key
*distribution* is skipped. This also allows minting the tokens that must fail,
which a real issuer would never hand out: wrong audience, wrong issuer, expired,
tampered signature, wrong key, missing `sub`.

**Two deliberate non-goals, recorded so they are not mistaken for oversights:**

- **No introspection.** Tokens are verified locally against the JWKS. A token
  revoked early stays usable until `exp` (3600 s). The alternative is a network
  round trip per request and a hard dependency on ThunderID being up.
- **Failure reasons are not disclosed.** Expired, wrong-audience and
  bad-signature all return the same 401 text. A caller who can distinguish them
  can use the endpoint as an oracle for our configuration.

**`auth_enabled=False`** restores the pre-gate behaviour of handing out
`SystemActor`. It exists for the test suite and offline work, defaults to
**True** so a missing setting fails closed, and must never be set in a deployed
environment.

⚠️ **`mcp_server/server.py`'s `_actor()` still hardcodes `SystemActor`.** That is
Gate 25 and it is the reason `agent/app.py` keeps its loopback binding. The API
is now authenticated; the MCP server is not.

#### Verified end-to-end in a browser, 2026-08-24

The first full run of the real thing — hosted login page, code exchange, session
cookie, an authenticated `GET /products` — with all four services up via
`scripts/dev-up.sh`. It passed, but **only after three defects that the unit
tests could not have caught**, because all three live in the frontend or in the
gap between the app and the identity provider.

**1. Route protection was a complete no-op. Two independent bugs in the SDK,
both copied faithfully from ThunderID's own examples.**

`src/proxy.ts` is the bouncer: it decides whether a signed-out visitor may reach
a page at all. It was letting everyone through, silently, and the only reason no
data leaked is that the backend built this gate refused every tokenless call
with a 401. The backend was carrying the whole building alone.

- **`createRouteMatcher` never matched anything.** It escapes every `.` *before*
  it expands `*`, so the `"/products(.*)"` idiom used throughout the vendor's
  JSDoc compiles to a regex demanding a literal dot: `/products` and
  `/products/123` fail it, `/products.anything` passes. The fix is the plain `*`
  glob — `"/products*"` — which is the form their implementation actually
  supports. Checked against `@thunderid/nextjs` **1.0.6, the latest published
  release**, and against the SDK repo's `main`: both carry the bug, so there is
  no version to upgrade to.
- **`protectRoute()`'s answer was discarded.** It neither throws nor
  short-circuits; it *returns* a redirect `Response`, and `thunderIDProxy` uses
  whatever the handler returns, falling back to `NextResponse.next()` on
  `undefined`. The vendor's example omits the `return`, so ours did too.

A matcher that silently never matches is the worst failure mode a bouncer has:
no error, no warning, every route simply open. **Do not reintroduce `(.*)`, and
do not drop the `return`.** Before/after, verified with curl:

| URL | before | after |
|---|---|---|
| `/` | 200 (correct — public landing) | 200 |
| `/products` | **200, fully rendered** | 307 → `/` |
| `/products/123` | **200** | 307 → `/` |
| `POST /api/agent/chat` | **404, unprotected** | 307 → `/` |

**2. ⚠️ Open the app at `http://localhost:3000`. Never let `127.0.0.1:3000`
reach the server first.**

`ThunderIDNextClient` is a module-level singleton with an `isInitialized` guard,
and it resolves `afterSignInUrl ?? origin` **once**, from the first request the
Node process ever serves. That origin is then baked into every subsequent
`redirect_uri` — for every user, for the life of the process.

A few curls to `127.0.0.1:3000` during testing were enough: every later sign-in,
including from `localhost:3000` in a browser, sent
`redirect_uri=http://127.0.0.1:3000` and ThunderID answered **`Invalid redirect
URI`**. The message points squarely at the Console, and the Console is fine. The
cure is to restart Next and make the first request the right one.

This will bite again. It is invisible, it survives a page reload, and it looks
exactly like a misregistered redirect URI.

**3. The `scope` claim was read unguarded** (found by review, not by the browser
run). `claims.get("scope", "").split()` sits *after* the try block, so a token
carrying `scope` as a list or a number raised `AttributeError` and surfaced as a
**500** — a malformed credential presenting as a server fault. Now type-checked,
treated as no scopes at all, and logged.

**Also fixed in the same pass:** `authn/tokens.py` promised in two comments that
the real refusal reason "goes in the log" — and no logger existed. Since every
refusal is deliberately indistinguishable to the caller, that log was the *only*
way to tell an expired token from a wrong audience from ThunderID being
unreachable. Added: `INFO` for a rejected token (routine — every session expires
hourly), `WARNING` for a key set that could not be reached (not the caller's
fault, and the only signal that the identity provider is the broken thing).

### Gate 25 — agent delegation and the MCP server as a resource server

The risky one. This is where "the agent can only do what you can do" stops being a design and starts
being enforced.

- `backend/mcp_server/server.py`: `MCPServer(..., token_verifier=, auth=AuthSettings(...))`; serve
  the protected-resource metadata; validate `aud`; never forward a token upstream. `_actor()` becomes
  the seam it was always meant to be:

  ```python
  def _actor() -> Actor:
      token = get_access_token()
      return TokenActor(id=token.subject, scopes=frozenset(token.scopes), act=token.claims.get("act"))
  ```

- **New `agent/auth.py`** with `get_scoped_token(...)` — the one place a grant type is named.
- `agent/mcp_client.py`: the connection has to change shape. `Client(url)` builds its transport with
  no HTTP client (`mcp/client/client.py`), and `streamable_http_client`'s own docs say
  authentication is configured by passing a pre-built `httpx2.AsyncClient`. So the call becomes
  `Client(streamable_http_client(url, http_client=httpx2.AsyncClient(auth=...)))`. **This is the one
  line where a future ID-JAG swap happens.** The `_actor` this file has stored unused since Gate 20
  finally gets used.
- `agent/app.py`'s `get_actor()`: read the user's token from the request; the frontend forwards it.
- Auth settings added to `agent/config.py` and `backend/core/config.py` **separately** — they are
  deliberate copies, and sharing them would cross the boundary the whole design holds.
- The transaction-pooler / `NullPool` switch recorded in `BACKEND-PLAN.md`.

**Exit condition:** the agent adjusts stock for a signed-in user and the row carries *that user's*
identity; and an agent scoped read-only is **refused** `stock.adjust` by `services/`. The negative
test is the one that matters, and it must assert the write did not happen — not that the reply looked
like a refusal.

#### Identity-provider side, completed 2026-08-25 — what was built and where reality differed

The Console half of Gate 25 is **done**. No application code changed. Everything below was verified
empirically — by decoding a real token's `aud` and `scope`, never by a status code, because of the
Gate 23 finding restated at the end of this section.

**Built:**

| Thing | Value |
|---|---|
| Agent | `AIsle Agent`, Client ID `6in2mfBltFEEMpYjF5upZA`, Agent ID `01a038f2-baa4-7a5a-a21c-b87124977fb8`, owner `amzal` |
| Grants | `client_credentials`, `authorization_code`, token exchange · `client_secret_basic` · PKCE on, PAR off |
| Redirect URI | `http://localhost:8002/callback` — `localhost`, **not** `127.0.0.1`, which ThunderID rejects |
| Role | `AIsle Full Access` (`01a038dd-5c3f-7c4e-af07-d6e1595c7e2d`), assigned to user `amzal` and `AIsle Agent` **only** |
| New resource server | `Agentic ERP MCP` / `https://mcp.agentic-erp.local` / type **API** / delimiter `.` / **not default** |

The client secret was shown once, saved to the developer's password manager and to gitignored
`agent/.env`. `includeActClaim` was left **off** as planned — nothing in this gate needed it.
`AIsle Gate` was not touched. `AIsle Web` is dead and was never read.

**`Agentic ERP MCP` exists because the resource-server section above says it must** — the built-in
`System` resource server's identifier ends in `/mcp` but is not our MCP server. `backend/mcp_server/`
is a separately reachable network service from Gate 26 on, so it needs its own `aud`. Sharing the
API's audience was considered and rejected: the MCP authorization spec requires an MCP server to
validate that the audience is *itself*, which is unimplementable when "itself" and "the other door"
are the same string — and it would throw away the destination half of delegation, leaving the agent
holding a full-building key.

Its permissions are a **deliberate duplicate** of the API server's four (`product.read`,
`product.create`, `product.update`, `stock.adjust`). ThunderID resource servers cannot share a
permission set. The duplication costs nothing at runtime: `services/` checks the same strings and
never learns which door the token came through.

**Verified by token, 2026-08-25:**

1. `client_credentials` + `resource=<MCP>` → `aud=https://mcp.agentic-erp.local`, all four scopes.
2. **Token exchange across two resource servers**: an API-audience token exchanged with
   `resource=<MCP>`, `scope=product.read` → `aud=https://mcp.agentic-erp.local`, `scope` exactly
   `product.read`. **Audience moved and scope shrank in one call.** Previously untested — Gate 23
   only exercised single-resource narrowing.
3. Over-asking with a nonexistent `admin.delete` → **HTTP 200, `scope` absent from both the response
   body and the token payload.** Gate 23's finding, reconfirmed on the new resource server.

> ⚠️ **Hard requirement for the code half of this gate, from (3).** ThunderID issued a structurally
> valid token, correctly stamped `aud=https://mcp.agentic-erp.local`, carrying **no `scope` claim at
> all**. The `TokenVerifier` MUST treat a missing or empty `scope` as **zero permissions** — `can()`
> false for everything — never as "unspecified, therefore allow". Nothing in the HTTP response
> distinguishes this token from a successful one. This needs its own regression test.

**Handoff to the code half:**

- A second audience setting is needed — `THUNDERID_MCP_AUDIENCE=https://mcp.agentic-erp.local` in
  `core/config.py` and `backend/.env.example`, alongside the existing `thunderid_audience`.
  **Audit of the repo on 2026-08-25 found exactly one audience anywhere**: `thunderid_audience`
  (`core/config.py:93`), consumed by `authn/tokens.py:109`. No code sends a `resource=` parameter at
  all, so today's human sign-in gets its `aud` purely from the default-resource-server flag.
- `agent/.env.example` has **no ThunderID section**, and its auth note still says "the agent and the
  MCP server both run with no authentication at all". This gate makes that false.

**Drift from this document, found while doing the work:**

1. **The admin MCP cannot do most of this gate.** Its 17 tools cover applications, flows, themes, org
   units, user types and SDK snippets — there is **no resource-server, role, user or agent tool**.
   This doc previously noted only the resource-server gap. The gate is therefore Console clicks,
   specified and verified externally.
2. **Resource servers have three types** — API ("REST or HTTP APIs secured as an OAuth2 audience"),
   MCP ("Model Context Protocol servers"), Custom. This doc describes only the generic API type.
3. **The MCP type defaults its delimiter to colon**, and the delimiter is **immutable**. A trap for a
   dot-based codebase; caught in the wizard, before creation.
4. **The MCP type cannot express business permissions.** It has no Default toggle and no Resource
   Hierarchy — only flat tool/resource capabilities where the handle *is* the scope, the delimiter is
   never applied, and handles cannot contain a dot (a handle of `product/read` previews verbatim as
   `product/read`). Per the vendor docs this is by design: *"turn each tool into a permission. The
   permission's handle becomes the scope tools validate."* **`Agentic ERP MCP` was therefore created
   as the API type**, after a first attempt as MCP type was deleted.
   Switching `services/` to tool-level permissions was considered and rejected: `services/` is shared
   by two adapters and only one of them has "tools", so per-tool naming would make the shared logic
   speak MCP's vocabulary — the coupling `CLAUDE.md`'s one rule exists to prevent — and several tools
   legitimately map to one permission.
5. **Roles span resource servers.** The Permissions tab is "grouped by resource server" and one role
   can hold permissions from several. So there is **no** second MCP role; `AIsle Full Access` was
   extended and now holds 12 nodes (6 per server).
6. **Parent permissions are held but not issued.** The Console will not accept a child without its
   parent, so the role carries the bare `product` and `stock` alongside the four dotted strings. Neither
   parent appears in a minted token's `scope`. Exact four-item assertions remain valid.
7. **Agents are a distinct entity class**, not applications — own Console section, own Access tab, an
   Owner, and an Operating Mode. Enabling **Delegated mode** force-adds `authorization_code` and then
   demands at least one redirect URI.
8. **The ThunderID docs live at `https://thunderid.dev/docs/v1.0.x/`.** `thunderid.io` returns empty.

#### Code side, completed 2026-08-25 — what was built

Both halves of Gate 25 are now done. Nothing in the ThunderID Console changed for this half, and no
file in `services/` changed at all — the call sites already took an `Actor` and already called
`can()`, which was the entire point of doing that in gate 3.

| File | What it does now |
|---|---|
| `core/config.py` | `thunderid_mcp_audience`, a **second** audience. `authn/tokens.py`'s `verify_access_token(token, *, audience=None)` takes it as a parameter — one check, two expected strings, rather than two copies to drift |
| **`mcp_server/auth.py`** (new) | `ThunderIDTokenVerifier` — the SDK's `TokenVerifier` protocol, translating to `AccessToken`. In `mcp_server/` and not `authn/` **because the SDK is a dialect**, exactly like `mcp_server/errors.py`. Enforced by a new import-linter contract, "Authn stays adapter-free" |
| `mcp_server/server.py` | `token_verifier=` + `auth=AuthSettings(...)`; `_actor()` returns a real `TokenActor`, raises when auth is on and no token is in context, falls back to `SystemActor("mcp")` only when `AUTH_ENABLED=false` |
| **`agent/auth.py`** (new) | `get_scoped_token(...)` — the one place a grant type is named. Sends `resource`, never `audience`. **Reads the scope that came back**: a partial grant is returned with a warning logged (`thunderid_scopes` is a ceiling, not a minimum), and only a wholly empty grant raises |
| `agent/actor.py` | `UserActor`, carrying the raw token. `can()` returns True because the agent is not an authorization decision point — the ERP is |
| `agent/app.py` | `get_actor()` reads the bearer token; deliberately does **not** verify it (no keys, no JWKS client — the MCP server is the judge) |
| `agent/mcp_client.py` | `Client(streamable_http_client(url, http_client=httpx2.AsyncClient(...)))`. The `_actor` stored unused since Gate 20 is finally used. **The one line a future ID-JAG swap touches** |
| `frontend/.../api/agent/[...path]/route.ts` | Forwards `Authorization: Bearer <session token>` |

**Exit condition met**, by the two tests in `backend/tests/test_mcp_auth.py`:
`test_a_row_written_through_the_agent_carries_the_users_own_identity` and
`test_a_read_only_agent_is_refused_and_the_stock_does_not_move` — the second reads the database
after the refusal, because a refusal that is only a message is not a refusal.

**The inherited defect is closed.** `ConversationRow.started_by` was a placeholder that always said
"system"; it now records the OIDC `sub`, and `store.conversation_exists(id, *, actor_id)` checks it
on every agent route. Answered as **404, never 403** — conversation ids are sequential integers, so
a 403 would confirm which ids are real.

**Two decisions worth not re-litigating.** The agent does not verify tokens locally: two
verification paths is how one of them ends up weaker, and the agent's virtualenv has no JWKS client
on purpose. And `agent/auth.py` prefers pinning `deploy/thunderid-server.cert` over
`verify=False` — the file is gitignored (each machine regenerates it), so its absence falls back to
`THUNDERID_VERIFY_TLS` and logs a WARNING rather than failing.

### Gate 26 — deploy

Unblocked only now. Five services. `agent/app.py`'s `HOST = "127.0.0.1"` and its test are deleted
**in this gate and not before** — the last thing to change, not the first.

**Requirement carried in from Gate 24 review (2026-08-24): refuse to start with authentication
off.** `AUTH_ENABLED` and `THUNDERID_VERIFY_TLS` are plain booleans, and either one wrong on a
deployed machine opens the API *silently* — every caller becomes `SystemActor`, or the signing keys
stop being verified, with no error and no failed request. Gate 24 added a `WARNING` at startup for
each (`core/config.py`), which is a signal, not a guard: nothing prevents it.

The real fix needs something this project does not have — **a notion of which environment it is
running in.** There is no `ENVIRONMENT` setting anywhere in `core/config.py`, and inventing one is a
deployment decision, which is why it belongs here rather than in Gate 24. This gate must:

- introduce an explicit deployment-mode setting (`local` / `test` / `deployed`, or equivalent);
- make `Settings` **fail to construct** — not warn — when either insecure value is set outside
  `local`/`test`, in the same fail-loudly-at-the-boundary spirit as the module's own docstring;
- keep both escape hatches fully working in `local`/`test`, because the test suite depends on
  `AUTH_ENABLED=false` and offline work depends on both.

**Requirement: digest-pin the ThunderID image once it is exposed.** The local file deliberately pins
the *tag* `1.0.0` so vendor patches arrive without an edit (reasoning and the comparison table are
under the install reference above). That trade is only defensible while the thing is loopback-bound
and local. Whatever deployment path Gate 26 chooses — hardened Compose or the Helm chart — must name
the image **by digest**, and treat an upgrade as a deliberate, recorded change verified against the
vendor's release notes. The argument for the tag is that changes arrive unnoticed; that is precisely
the argument against it in a deployment.

**Requirement: rate-limit the token endpoint before it is exposed.** Raised by review (CodeRabbit,
PR #28) against `backend/authn/tokens.py`, verified against the installed PyJWT 2.13.0 source and
**deferred here deliberately, not dismissed.**

The mechanism, so nobody has to rediscover it: a JWT names the key that signed it in its `kid`
header. `PyJWKClient` caches the key set for `lifespan` seconds (we set 300), but
`get_signing_key()` — `jwks_client.py` line 202 — refetches with `refresh=True`, *bypassing that
cache*, whenever the `kid` is absent from the cached set. That is correct for a genuine key
rotation. The catch is that it happens **before any signature is checked**: the `kid` is read out
of the unverified header. So an anonymous caller sending structurally valid tokens with a random
`kid` each time forces one outbound HTTPS fetch per request, at a 30-second timeout, against both
our worker pool and ThunderID's capacity. Cheap to send, expensive to absorb.

Not fixed at Gate 24 because there is no anonymous caller: the API and ThunderID are both
loopback-bound. **That protection disappears at Gate 26**, which is why this is written here.

The fix is a pre-authentication rate limit in front of the API — deployment infrastructure, not
application code. A hand-rolled negative cache of bad `kid` values inside `tokens.py` was considered
and rejected: it adds TTL and thread-safety logic to `authn/` for a problem that does not exist yet,
and it would not remove the need for the rate limit anyway. If Gate 26 ends up wanting one as
defence in depth, it must stay bounded so a real key rotation is never cached out.

**Open decision: how ThunderID is actually deployed.** `deploy/docker-compose.thunderid.yml` is
**temporary — a local development recipe, not the deployment path.** It was committed at Gate 23 to
pin the version the spike validated against, and it is the vendor's quick-start file with the tag
pinned and nothing else changed. It is not suitable as-is for anything reachable from the internet,
for reasons found at Gate 23 and in review. Two remain open:

- the TLS certificate is **self-signed**;
- the named volumes hold the entire identity store with **no backup or tested restore**.

Two others have since been fixed in the file itself and are recorded here so the list is not read as
current: it bound `8090` on **all interfaces** (narrowed to loopback 2026-08-23, and now coupled to
`oauth.dcr.insecure` — do not widen it back without removing that first), and `setup.sh` — the
vendor's script, inside the vendor's image, not ours to edit — **regenerated the signing keys, TLS
certificate, Direct Auth Secret and admin password whenever the setup container was recreated**,
invalidating every previously issued token; it now sits behind an `init` profile that a normal `up`
does not start.

**The vendor's own production path is Kubernetes via their Helm chart**
(`oci://ghcr.io/thunder-id/helm-charts/thunderid`), not Compose — verified 2026-08-18. There is also
a third path, **OpenChoreo** (cell-based, platform-managed, with service-mesh networking), for
platform-managed deployments. Note this reframes the third point above: under Helm the key material
is supplied as secrets rather than generated by a script, so "make `setup.sh` idempotent" is the
wrong fix — not running it in production is the right one.

**Their production hardening list is longer than this document previously recorded.** The earlier
four-item summary (TLS cert, encryption key, CORS, Redis) understated the work; the full list, read
2026-08-18:

| Item | What it means |
| --- | --- |
| **PostgreSQL instead of SQLite** | And not one database — **four**: `config`, `runtime_transient`, `entity`, `runtime_persistent`, each with `ssl mode: require` and pool sizing. This is the item that most changes the cost estimate |
| **TLS certificate** | Replace the self-signed cert with one from a trusted CA |
| **Encryption key** | `openssl rand -hex 32` into `config/certs/crypto.key`. ⚠️ **Lose it and encrypted data is unrecoverable** — this needs a backup story before it is generated, not after |
| **Direct Auth Secret** | `openssl rand -hex 32` into `config/secrets/direct_auth_secret`; gates the Direct API endpoints |
| **CORS allowlist** | Each production origin listed explicitly, full scheme+host, no wildcards |
| **Content Security Policy** | Move from report-only to enforcing, with real origins in `img-src` / `font-src` / `style-src-elem` |
| **Redis** | Required once more than one pod runs — per-pod in-memory caches otherwise go inconsistent |
| **Backups, file permissions, monitoring** | Database backups enabled, sensitive files restricted, ThunderID and its dependencies monitored |

Two consequences worth noting now rather than at Gate 26. The four-database Postgres requirement is
real work, though this project already runs Supabase Postgres, so it is a schema-and-credentials
exercise rather than a new piece of infrastructure. And `crypto.key` is the first artifact in this
project whose **loss is unrecoverable** — it deserves a deliberate answer, not a default.

Choosing between hardening the Compose file and adopting the Helm chart is **a Gate 26 decision and
is deliberately not made here** — it depends on where the other four services land, which is also
still open. Whichever wins, `deploy/docker-compose.thunderid.yml` stays afterwards only if it is
clearly marked as the local-development recipe.

---

## Two capabilities noted, not scheduled

Both are supported by the provider and neither is needed to close these gates. Recorded so they are
not reinvented later.

- **CIBA (Client Initiated Backchannel Authentication)** answers a question Gate 19 left open. That
  gate built "pause and ask for human approval," but approval only works while someone is watching
  the chat. CIBA pushes the request to a separate device with no browser redirect — the
  standards-based version of "the agent wants to adjust stock at 3am, ask the manager's phone."
- **Verifiable credentials for agents.** ThunderID supports issuing them. Relevant only if agent
  identity ever has to be proven to a party that does not trust our issuer.
- **ThunderID's own admin MCP server**, at `/mcp` on the instance (`https://localhost:8090/mcp`).
  Exposes tools to create OAuth applications, design authentication flows, inspect themes, list
  organization units and user types, and generate React SDK integration code — i.e. it lets an AI
  assistant administer ThunderID itself. Auth is OAuth code flow + PKCE requiring the `system` scope,
  and it needs an MCP Client registered in the Console plus a CORS entry. **Deliberately not used in
  these gates**, per the note in Gate 24: registering an application is a one-time Console task, and
  granting an assistant administrator scope over the identity provider is a much larger authority
  than the task needs. Recorded because it is genuinely useful for bulk or repeatable tenant setup
  later, where clicking through a console does not scale.

**One tool that exists and should be treated carefully: `@thunderid/skills`.** The vendor ships an
agent-skill pack (`npx skills add thunder-id/skills`, or as a Claude Code marketplace) covering
server install and per-framework integration. It is installed on this machine. Two cautions learned
2026-08-18: the cache can contain **more than one copy of a skill under different layouts**, and only
the flat `skills/thunderid-*` set is the live one — an older `skills/core/` + `skills/integration/`
tree sitting beside it carried stale instructions (a compose file pinned to `v0.39.0`, and
`CLIENT_ID`/`CLIENT_SECRET` env vars that the current docs have replaced with
`APPLICATION_ID`/`FLOW_SECRET`). The v0.2.0 Next.js skill in the *live* tree still carries the
`CLIENT_SECRET` spelling and is wrong about it — see the 2026-08-23 re-verification under Gate 24.
Staleness is not confined to the duplicate tree. Upstream has since rewritten the Next.js skill to **fetch the
canonical doc at run time instead of embedding steps**, which is the right design and confirms the
embedded versions age badly. **Rule: the skills are a convenience wrapper, the live docs are the
source of truth** — the same verify-against-current-docs rule `PLAN.md` already applies to
everything else.

Other grants available and used implicitly: Authorization Code with PKCE (human login), Client
Credentials (machine-to-machine, and explicitly **not** how the agent should act for a user), and
Refresh Token. Security extensions advertised alongside: PKCE, PAR, DPoP, and **Resource Indicators
(RFC 8707)** — the last is what the MCP authorization spec requires for audience-targeting, so its
presence is load-bearing rather than incidental.

---

## The decision that was left open, now settled

**Whether permissions live in ThunderID roles (carried in the token) or in a local table keyed on the
OIDC `sub`.** This was deferred to Gate 23's close-out, to be settled with real tokens in hand rather
than in advance. They are now in hand.

**Settled: permissions live in ThunderID roles, carried in the token.**

The spike removed the argument for a local table. The permission strings arrive in the token
*identical* to what `services/` already checks — `product.read` and friends, no translation, because
the `.` delimiter was set at creation. And the downscoping guarantee only works because the issuer
knows the permission vocabulary: finding 3 above — an agent being refused more authority than the
incoming token carried — is enforced *by ThunderID*, and it could not enforce it against permissions
it had never heard of. A local table would move that check back to us and lose the guarantee.

`TokenActor.can()` therefore becomes a set-membership test over the token's `scope` claim, with
nothing to map.

**The one cost of this choice**, recorded so it is not discovered later: permissions are now
administered in the ThunderID console, not in the codebase. Adding a permission means a console
change *and* a code change, and the two can drift. The mitigation is that `services/` remains the
only place permissions are *enforced* — a scope in a token that no `can()` call checks is inert.

---

## What we considered and rejected

Compressed from the 2026-07-31 provider survey. Kept because the reasoning still explains why the
shortlist ended where it did; the table's *status* column is the part that has since moved.

| Option | Why not |
| --- | --- |
| **Supabase Auth** | Solves human auth, which is the easy half. **No delegation story for the agent half at all.** This is why Supabase is used for Postgres only. |
| **WSO2 Asgardeo** (SaaS, GA) | Zero ops and a genuine free tier — B2E at 50 monthly active users, which comfortably covers a single supermarket's back office. Rejected once self-hosted ThunderID proved to include token exchange at no licence cost, which removed the question the Asgardeo option existed to answer. Free-tier audit-log retention was 2 days, survivable here only because `created_by`/`updated_by` answer "who adjusted this stock", not the provider's logs. |
| **WSO2 Identity Server** (Java, on-prem, GA) | Established, free to self-host, but heavier and with no agent-specific tooling — which is the half of the problem that actually matters here. |
| **Auth0 "Auth for MCP"** (GA since May 2026) | The most complete packaged story, and commercial. Part of its advantage was Dynamic Client Registration, which the MCP spec has since **deprecated** in favour of Client ID Metadata Documents — a fading selling point. |
| **Keycloak 26.2+** | GA, free, RFC 8693 confirmed shipping, 26.5 adds cross-domain identity chaining. Was the named fallback if Gate 23's spike failed; **the spike passed, so this is now simply rejected**. Rejected as first choice because it models agents as ordinary OAuth clients, so every part of the agent-identity story would be ours to build by hand. |

**The deciding question, and how it resolved.** It was never "is token exchange available for free" —
it is, self-hosted. It was **"is a pre-GA server acceptable as the identity provider for this
system?"** ThunderID was the better *fit* and the worse *bet*; Keycloak was the reverse. This project
chose fit, with a spike as the hedge and Keycloak as the named fallback.

Both halves of that hedge have now resolved in ThunderID's favour: the spike passed, and the running
instance reports `v1.0.0` rather than a release candidate. **The bet is no longer pre-GA.** What
remains of the original concern is maturity, not status — a 1.0.0 reached four weeks after first
alpha has little field history behind it. The mitigations stay in force regardless: pin an exact
tag, and keep every vendor library out of `backend/` and `agent/` so the provider stays swappable.

Two smaller items also retired:

- **"Re-evaluate ThunderID in ~6 months (around Q1 2027)"**, written when it was two months old with
  no GA declaration. Overtaken by events: it reached rc in three weeks. The underlying concern — churn
  — is real and visible in that cadence, which is why an exact tag pin is mandatory.
- **The worry that Pydantic AI is unsupported.** ThunderID's "LangChain integration" is a tutorial
  containing **zero ThunderID libraries** — a `requests.post` to the token endpoint and a
  `contextvar` holding the result. Nothing in it is LangChain-specific, so there is no adapter
  Pydantic AI is missing and the "coming soon" list is a docs backlog, not a capability gate. This
  matters less here than elsewhere anyway, since `agent/mcp_client.py` is already a hand-written
  toolset rather than Pydantic AI's `MCPToolset` — the token attaches in code we own either way.
- **The fear of a framework downgrade.** ThunderID's Python MCP guide is written against
  `fastmcp>=3.4,<4`, which pins `mcp>=1.24,<2.0` — the legacy protocol era this project spent Gate 6
  leaving. Following it verbatim would mean downgrading. **Not necessary**: `mcp==2.0.0` has native
  resource-server support with no FastMCP involved, so their decorator is replaced by a custom
  `TokenVerifier` of roughly forty lines.

  **Re-verified 2026-08-18, and the trap is still live.** Their guide still declares
  `fastmcp>=3.4,<4`; the current `fastmcp` 3.4.7 (released 2026-08-10) depends on
  `fastmcp-slim==3.4.7`, whose metadata requires **`mcp<2.0,>=1.24.0`** exactly as recorded. Their
  guide also demonstrates per-tool scope decorators (`@mcp.tool(auth=require_scopes("add"))`) via
  `RemoteAuthProvider` + FastMCP's `JWTVerifier` — which is the pattern the "one divergence recorded
  deliberately" note above already rejects, since this project checks permissions in `services/`.
  **One thing worth taking from their guide**, though: they pass
  `http_client=httpx.AsyncClient(verify=CA_CERT)` to the verifier. That is the correct answer to the
  self-signed-certificate problem — trust the CA explicitly — and Gate 25's own verifier should use
  that shape rather than the spike's `verify=False`.

---

## Gate 26 entry price: the agent-server's own door

**Decided 2026-08-26. Nothing below is implemented — this section is the record of what was
deferred, why, and what "done" looks like, so gate 26 does not have to re-derive it.**

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

**B2 — give the agent-server its own audience (deferred further, and optional).**
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
4. `grep -n "without verifying" agent/app.py` returns nothing.
5. Only then may `HOST = "127.0.0.1"` in `agent/app.py` be reconsidered — and item (1) of gate 26's
   three (no rate limiting) is still outstanding independently.

### ThunderID-side work required

**For B1: none.** No new resource server, no new permissions, no role changes. B1 uses tokens
ThunderID already issues, checked against the JWKS endpoint it already publishes. The admin MCP
session is *not* needed.

**For B2:** one new resource server, via the Console or the admin MCP — see "Identity-provider
side, completed 2026-08-25" above for the shape `Agentic ERP MCP` used.
