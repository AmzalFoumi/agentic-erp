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

---

## Status in one paragraph

The deferral has expired and the work is scheduled. **ThunderID is the chosen provider — the Gate 23
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

ThunderID ships SDKs for React, Next.js, Express, Vue, Nuxt, Node, vanilla JS, iOS, Android and
Flutter. **There is no Python SDK.** It does not matter, because of which OAuth role each half of
this system plays:

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

⚠️ **Trap with the `npx` install path.** `npx thunderid --install-dir . …` writes a datastore and
config files into the current directory. **Do not run it inside the repository** — use a sibling
directory such as `D:\Amzal Projects\thunderid-local\`. The Docker Compose path, pinned at a tag, is
preferred anyway because it is closer to how the thing will actually be deployed.

**Install reference, as built at Gate 23:** `deploy/docker-compose.thunderid.yml` in this repo,
pinned to image tag `1.0.0`. Run it from a directory outside the repo, or with `-f`; either way the
data lives in Docker **named volumes**, not in the working directory, so the `npx` trap above does
not apply to the compose path. Server at `https://localhost:8090`, console at `/console`,
**self-signed certificate** — it must be accepted in a browser once before any client will talk to
it. The admin password is *not* `admin`/`admin` on the compose path: it is generated by
`thunderid-setup` and printed in that container's logs, and it is regenerated every time the stack
restarts.

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
  `.claude/problems/thunderid-mcp-access.md` for the full note.

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

- `frontend/`: `@thunderid/nextjs`, `ThunderIDProvider` in `src/app/layout.tsx`, `proxy.ts` with
  `createRouteMatcher` over the product routes, sign-in UI in the existing `components/shell/`.
  The **developer creates the Application in the Console** and reports the Client ID back; the
  assistant never touches the Console.
- `frontend/src/lib/auth/current-user.ts`: a real session read, replacing `{ id: "system" }`. It is
  already `async`, so no call site changes.
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

### Gate 26 — deploy

Unblocked only now. Five services. `agent/app.py`'s `HOST = "127.0.0.1"` and its test are deleted
**in this gate and not before** — the last thing to change, not the first.

**Open decision: how ThunderID is actually deployed.** `deploy/docker-compose.thunderid.yml` is
**temporary — a local development recipe, not the deployment path.** It was committed at Gate 23 to
pin the version the spike validated against, and it is the vendor's quick-start file with the tag
pinned and nothing else changed. It is not suitable as-is for anything reachable from the internet,
for four reasons found at Gate 23 and in review:

- it binds `8090` on **all interfaces**, not loopback;
- the TLS certificate is **self-signed**;
- `setup.sh` — the vendor's script, inside the vendor's image, not ours to edit — **regenerates the
  signing keys, TLS certificate, Direct Auth Secret and admin password whenever the setup container
  is recreated**, which invalidates every previously issued token;
- the named volumes hold the entire identity store with **no backup or tested restore**.

**The vendor's own production path is Kubernetes via their Helm chart**
(`oci://ghcr.io/thunder-id/helm-charts/thunderid`), not Compose — verified 2026-08-18. Their
documented production hardening is: replace the TLS certificate, generate a unique encryption key,
configure a CORS allowlist, and add Redis if more than one instance runs. Note this reframes the
third point above: under Helm the key material is supplied as secrets rather than generated by a
script, so "make `setup.sh` idempotent" is the wrong fix — not running it in production is the
right one.

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
