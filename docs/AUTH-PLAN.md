# Authentication — decision, provider landscape, and the deferral

> **Subordinate to `docs/PLAN.md`.** This file holds the authentication and agent-identity
> workstream in full: why a provider has not been chosen, the verified comparison of the
> candidates, and the conditions under which the deferral expires. Where this file and `PLAN.md`
> disagree, **`PLAN.md` wins** and this file is the thing that is out of date.
>
> It is split out because it is read at exactly one future gate — the auth gate — while the
> decision it records constrains work in `backend/` and `frontend/` alike, so filing it under
> either one would hide it from the other. `PLAN.md` keeps only the two expiry conditions, because
> those gate further feature work and must sit in the file that is always read.
>
> **The open item is closed** (first 2026-08-13 amendment, below): the design rests on RFC 8693 token
> exchange, and ThunderID ships it free when self-hosted, so the Asgardeo free-tier question no
> longer gates the decision.
>
> **The deferral itself has since expired** (second 2026-08-13 amendment): the stated goal of hosting
> all four services fires expiry condition 1, which makes the auth gate a **hard prerequisite for
> deployment**. No provider is committed yet — a timeboxed spike comes first.
>
> **Read the two 2026-08-13 amendments before the older ones**, and the second before the first;
> where any of them disagree, the later one wins.

---

## Decision: authentication (2026-07-29)

**Supabase is used for Postgres only** — not Auth, Storage, or Realtime. The backend connects with
SQLAlchemy over a plain connection string, so the database stays portable (swap the string for Neon
or RDS and nothing else changes).

**The auth provider choice is deferred; the design for it is not.**

Human auth and agent auth are different problems. Human auth is commoditized (Supabase Auth, Clerk,
Auth0). Agent auth — an AI acting _on behalf of_ a person, with a subset of their permissions and a
clear accountability trail — is unsettled and actively churning. **WSO2 ThunderID**
(<https://github.com/asgardeo/thunder>, announced May 2026) targets exactly that, with RBAC spanning
humans, agents and workloads, and is being contributed to the OpenWallet Foundation. It is also two
months old with no GA declaration, which makes it a poor first dependency for this project today.

Also note: while the MCP server runs over **stdio locally**, the agent runs as the developer and
there is no auth question to answer. It only appears when the MCP server goes remote.

**What we do now, from Gate 3/4 onward:**

- Every service function takes an `actor` as its second argument, after `session`.
- `core/exceptions.py` includes `PermissionDeniedError`.
- Permission checks live in `services/` (`actor.can("inventory:adjust")`), never in the adapters.
- Models carry `created_by` / `updated_by` audit columns.
- A `SystemActor` with full permissions is used until a real provider is wired in.

Services never learn _how_ someone authenticated — only who they are and what they may do. FastAPI
will derive the `Actor` from a JWT; MCP will derive it from its session context. Both hand the
service the same object, so adopting a provider later is a change to two adapter files rather than
a rewrite. The audit columns are wanted regardless — an ERP needs "who adjusted this stock?".

**Re-evaluate ThunderID in ~6 months** (around Q1 2027), once it has a GA release, if agent-identity
governance becomes central. Otherwise Supabase Auth is the pragmatic default, since the project is
already provisioned and it integrates with Postgres row-level security.

### Amended 2026-07-31 (Gate 7): the provider landscape, verified

Raised by the developer while planning the frontend: _can an agent be restricted to only the
logged-in user's allowed actions, is an identity server actually required, and is there a free option?_

**An identity server is required.** The standards-based mechanism for "the agent may only do what the
user may do" is **OAuth 2.0 Token Exchange (RFC 8693)**: the agent presents the user's token as
`subject_token` and receives a _derived, narrower_ token carrying both the user's identity and the
agent's. Issuing that token is by definition an authorization server's job. The alternatives —
forwarding the user's raw token, or running the agent as a service account — are precisely the
confused-deputy and privilege-escalation failures documented under "three deployment shapes" in
`docs/BACKEND-PLAN.md` (Gate 6).
MCP assumes this too: an HTTP MCP server is an OAuth resource server that must never forward the
caller's token upstream.

| Option                                                            | Status                                                               | Who runs the server                                 | Cost                                                                                                    |
| ----------------------------------------------------------------- | -------------------------------------------------------------------- | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| **ThunderID** (Apache 2.0, Go)                                    | ~~**Alpha** — `v1.0.0-alpha2`~~ **beta2 as of 2026-08-07** — see the 2026-08-13 amendment | **You** — binary/container, datastore, TLS, backups | Free licence, paid for in ops                                                                           |
| **WSO2 Asgardeo** — renaming to **WSO2 Identity Platform** (SaaS) | GA                                                                   | **WSO2** — nothing to run                           | Free tier; see below                                                                                    |
| **WSO2 Identity Server** (Java, on-prem)                          | GA, established                                                      | **You** — JVM, heavier                              | Free to self-host; no agent-specific tooling                                                            |
| **Auth0 "Auth for MCP"**                                          | **GA since May 2026**                                                | Auth0                                               | Commercial. Most complete packaged story: OBO token exchange, DCR, resource indicators                  |
| **Keycloak 26.2+**                                                | GA                                                                   | **You** — container + database                      | Free. RFC 8693 token exchange officially supported since 26.2; 26.5 adds cross-domain identity chaining |

**Correction to the note above:** ThunderID has moved from `asgardeo/thunder` to
<https://github.com/thunder-id/thunderid>, with its own site at <https://thunderid.dev>. It is
**standalone — it does not require WSO2 Identity Server.** It is still alpha, which confirms rather
than undermines the Q1 2027 re-evaluation.

**Asgardeo free tier, verified 2026-07-31.** "Free forever", no credit card, three tiers by use case:
B2C up to 7,500 MAUs · B2B up to 250 · **B2E up to 50 employee MAUs**. This ERP is **B2E** — the users
are stock clerks and managers, not consumers — so 50 monthly active users is the relevant allowance,
which comfortably covers a single supermarket's back office. Beyond it, B2E is Enterprise-quoted at
~$2.50/MAU. Free-tier limits: 3 administrators, 5 applications, 2 MFA methods, **2 days audit-log
retention**, 3 days session retention; accounts inactive 2+ months are terminated. The audit retention
is survivable here only because "who adjusted this stock" is answered by our own
`created_by`/`updated_by` columns, not by the provider's logs.

**Open question, to be settled at the auth gate before committing to a provider: is RFC 8693 token
exchange available on the Asgardeo free tier?** That single feature is what the entire delegation
design rests on, and free tiers commonly gate it. If it is paid-only, the free answer is Keycloak,
where RFC 8693 is confirmed shipping.

**Revised shortlist:** Asgardeo free tier (zero ops, _if_ token exchange is included) or Keycloak
(self-hosted, free, confirmed). **Not Supabase Auth** — it solves human auth, which is the easy half,
and has no delegation story for the agent half. That supersedes the "Supabase Auth is the pragmatic
default" line above.

### The deferral, stated plainly (2026-07-31)

**Nothing in gates 7–13 implements authentication, and nothing in them should.** No provider is
chosen, no login screen is built, no token is issued or validated. `SystemActor` remains the only
`Actor` implementation; `frontend/src/lib/auth/current-user.ts` will hardcode `"system"` to match it.

Why, restated so it is not mistaken for an oversight: the hard half is _agent_ identity, not human
identity. Human auth is commoditized and can be added in a week. Agent delegation is unsettled — the
best-fitting product is at alpha, and the feature the design rests on is unconfirmed on the free tier
of the shipping alternative. Choosing now would mean choosing on the easy half and discovering the
hard half afterward.

Cost of deferring: three functions — `api/deps.py`'s `get_actor()`, `mcp_server/server.py`'s
`_actor()`, and `frontend/src/lib/auth/current-user.ts`. Cost of _forgetting_: the privilege-escalation
bypass described under "three deployment shapes" in `docs/BACKEND-PLAN.md`, with no log entry
distinguishing it from
legitimate use.

**Two conditions make this deferral expire.** Either one triggers the auth gate before further
feature work:

1. The MCP server becomes reachable over HTTP by anything that is not the developer's own machine.
2. A second human user exists.

Until both are false, `SystemActor` is acceptable _only_ because no unauthenticated caller exists.

---

## Amended 2026-08-13: ThunderID researched against its live docs

Raised by the developer while the agent gates were closing: _implement ThunderID for auth — humans
reach the FastAPI backend through the frontend, and the agent runs at the same level of access or
lower (an inventory agent reaching only inventory tools), which means securing the MCP server too._
The specific worry was framework support: ThunderID's site advertises LangChain, with ADK and CrewAI
"coming soon", and **Pydantic AI is not mentioned anywhere**.

Verified against <https://thunderid.dev/docs/next/> and the GitHub releases API on 2026-08-13. Four
findings, in descending order of how much they change the plan.

### 1. The Pydantic AI concern is moot — there is nothing to port

ThunderID's "LangChain integration" is a tutorial, not a package. It contains **zero ThunderID
libraries**: a `requests.post` to the token endpoint for `client_credentials`, and a `contextvar`
holding the resulting token so a tool can read it. Nothing in it is LangChain-specific, and there is
therefore no adapter Pydantic AI is missing. The "coming soon" list is a docs backlog, not a
capability gate.

This matters more here than for most projects because `agent/mcp_client.py` is already a
hand-written `AbstractToolset` rather than Pydantic AI's `MCPToolset` — the token would be attached
where that file builds its client, which is code we own either way.

### 2. RFC 8693 is present, free, and behaves the way the design assumed

This closes the open item that headed this file. Self-hosting ThunderID (Apache 2.0) carries no
licence cost, so the Asgardeo free-tier question is no longer load-bearing.

From `guides/protocols/oauth-oidc/token-exchange/`, the parts the design depends on:

| Aspect | Behavior |
| --- | --- |
| Endpoint / grant | `POST /oauth2/token`, `grant_type=urn:ietf:params:oauth:grant-type:token-exchange` |
| `scope` | **Downscoping allowed, widening rejected with `invalid_scope`.** Final scopes must also be permissions on the target resource server _and_ authorized for the issuing app or agent |
| `resource` | RFC 8707 resource indicator. The issued token is bound to exactly this resource server |
| `audience` | Accepted for RFC 8693 compatibility but **does not determine the `aud` claim** — use `resource` |
| `actor_token` | Optional; supplies the acting party in a delegation chain |
| `requested_token_type` | `:access_token`, `:jwt`, `:id-jag`. Not `id_token`, not `refresh_token` |

The scope row is the whole design in one line: "the agent may only do what the user may do" is
enforced by the issuer, not by us. An inventory-only agent is an agent authorized for a narrower
permission set, exchanged against a token that cannot widen it.

Two traps recorded because they cost a debugging session each if unknown: **`audience` is a decoy**
— setting it and expecting the token's `aud` to follow will silently fail, and `resource` is the
parameter that works; and the `act` claim only appears when an explicit `actor_token` is supplied,
so a delegation chain that omits it produces a token that is downscoped but does not say _who_
narrowed it.

### 3. Set the resource-server `delimiter` to `"."` — it is immutable after creation

From `guides/resource-servers/`: permissions are `{resource-handle}{delimiter}{action-handle}`, with
`delimiter` defaulting to `:` and **"cannot be changed after creation"**. Allowed characters include
`.`.

Our permission vocabulary is already `product.create`, `product.update`, `stock.adjust` — the strings
`services/` passes to `actor.can()` today. Registering the backend with `delimiter: "."` makes
ThunderID's permission strings identical to the ones already in the code, so `TokenActor.can()` is a
set membership test and nothing needs translating. Accepting the `:` default would mean either
rewriting every `can()` call site or maintaining a mapping table forever, and the field cannot be
corrected afterward.

Permission strings are **not** prefixed by the resource server; the server is identified by its
`identifier`, which becomes the token's `aud`.

### 4. Compatibility risk is real but survivable: their guide assumes a stack we do not run

ThunderID's Python MCP guide is written against `fastmcp>=3.4,<4`, which pins `mcp>=1.24,<2.0` — the
**legacy** protocol era. `backend/` runs `mcp==2.0.0` deliberately (see `mcp_client.py`'s opening
docstring for why that pin exists on both halves). Following their guide verbatim would mean
downgrading the backend to the protocol era the project spent Gate 6 leaving.

Not necessary. Verified directly against the installed `mcp==2.0.0` source that it has native
resource-server support, no FastMCP involved:

- `mcp.server.auth.settings.AuthSettings(issuer_url, resource_server_url, required_scopes, ...)`
- `mcp.server.auth.provider.AccessToken(token, client_id, scopes, expires_at, resource, subject, claims)`
- `mcp.server.auth.middleware.auth_context.get_access_token() -> AccessToken | None`
- `MCPServer(..., token_verifier=, auth=)` wires `BearerAuthBackend` + `AuthContextMiddleware`

So the tutorial's FastMCP decorator is replaced by a custom `TokenVerifier` — roughly forty lines —
and `mcp_server/server.py`'s `_actor()` becomes the seam it was always meant to be:

```python
def _actor() -> Actor:
    token = get_access_token()
    return TokenActor(id=token.subject, scopes=frozenset(token.scopes), act=token.claims.get("act"))
```

**One real gap.** `AuthSettings.required_scopes` is a single server-wide list; `mcp==2.0.0` has no
per-tool equivalent to FastMCP's `require_scopes()`. That is not a blocker here, because
per-operation authorization already lives in `services/` via `actor.can(...)` — which is where this
project decided it belongs. The MCP layer checks "may you reach this server at all"; the service
layer checks "may you adjust stock". Do not try to move the second one up.

### Status and what changes in this file

**ThunderID is at `v1.0.0-beta2` (2026-08-07)**, not the `v1.0.0-alpha2` recorded in the 2026-07-31
table above — four releases in three weeks (alpha 07-21, alpha2 07-28, beta 08-04, beta2 08-07).
Still no GA. The churn that motivated "re-evaluate around Q1 2027" is real and visible in that
cadence; a pin to an exact tag is mandatory if we adopt it.

**Revised position.** The shortlist's premise has changed: the deciding question is no longer
"is token exchange available for free" (yes, self-hosted ThunderID) but "is a pre-GA server
acceptable as the identity provider for this system". Keycloak remains the conservative answer and
its RFC 8693 support is confirmed; ThunderID is the better _fit_ and the worse _bet_. **Nothing is
committed here** — the two deferral expiry conditions above still stand unchanged, and no provider
is chosen until one of them fires.

**Before adopting, timebox a spike:** install ThunderID via Docker, register the backend as a
resource server with `delimiter: "."`, and prove that one token-exchange call produces a downscoped
token that a real `TokenVerifier` on `mcp==2.0.0` accepts. That last step is the only part of this
that no documentation can answer for us.

---

## Amended 2026-08-13 (second pass): the deferral has expired, and what running ThunderID costs

The amendment above settled *whether the design works*. This one settles *when it has to happen* and
*what we are signing up to operate*. Where the two disagree, this one is later and wins.

### 1. Condition 1 has fired — auth now precedes deployment, not the reverse

The developer stated the goal: **host the frontend, the API backend, the MCP server, and the agent.**
A hosted MCP server is, by definition, "reachable over HTTP by anything that is not the developer's
own machine" — expiry condition 1, further up this file. So the deferral is no longer open-ended:

> **The auth gate is a hard prerequisite for deployment.** Not a nice-to-have that follows it.

Deploying first is not a "ship it and add auth after" trade-off, which is how it usually gets
rationalised. `mcp_server/server.py`'s `_actor()` returns `SystemActor`, and `services/` grants
`SystemActor` everything — so a publicly reachable MCP server with today's code gives **anonymous
callers full write access to inventory**, with every row stamped `created_by="mcp"` and no way to
tell those writes from legitimate ones. There is no partial version of this to ship.

Stage 20 already anticipated it: the agent binds to `127.0.0.1` with a test that fails if that
changes, and `AGENT-PLAN.md` records the intended order as **local → auth → deploy**. This amendment
just confirms the middle step is now scheduled rather than hypothetical.

### 2. The full grant-type table, and two capabilities the design had not considered

Verified against `guides/protocols/oauth-oidc/` on 2026-08-13:

| Grant | Spec | Relevance here |
| --- | --- | --- |
| Authorization Code | RFC 6749 §4.1 | Human login. PKCE required for public clients |
| Client Credentials | RFC 6749 §4.4 | Machine-to-machine, no user. **Not** how the agent should act for a user |
| Refresh Token | RFC 6749 §6 | Session continuity |
| **Token Exchange** | **RFC 8693** | The delegation mechanism this design rests on — see amendment above |
| **Identity Assertion Grant (ID-JAG)** | `draft-ietf-oauth-identity-assertion-authz-grant` | Cross-domain identity assertions. A **second** candidate for the agent→MCP hop |
| **CIBA** | CIBA Core 1.0 | Decoupled approval on a separate device, no browser redirect |

Security extensions advertised alongside these: PKCE, PAR, DPoP, and **Resource Indicators
(RFC 8707)** — the last is what the MCP authorization spec requires for audience-targeting, so its
presence is load-bearing, not incidental.

Two of these were not in the design and are worth considering at the gate rather than after it:

- **CIBA answers a question stage 19 left open.** That stage built "pause and ask for human
  approval," but approval only works while someone is watching the chat. CIBA pushes the request to
  a separate device — the standards-based version of "the agent wants to adjust stock at 3am, ask
  the manager's phone." Not needed to close the auth gate; noted so it is not reinvented later.
- **ID-JAG may fit the agent→MCP hop better than RFC 8693.** Both are supported, so this is a design
  choice at the gate, not a provider constraint. Do not assume token exchange is the only option
  just because it is the one this file has discussed longest.

### 3. There is no hosted ThunderID — self-hosting is the whole offering

Searched 2026-08-13: **no SaaS tier, no cloud sandbox, no demo instance.** This matters because the
2026-07-31 shortlist framed the choice as "Asgardeo free tier (zero ops) or Keycloak (self-hosted)",
and ThunderID is unambiguously in the second category. Adopting it means:

- a **fifth deployed service**, with its own container, persistent datastore, TLS, and backups;
- **pinning an exact tag** — four releases in three weeks, still pre-GA;
- owning the upgrade path when a pre-GA server makes a breaking change.

Stated plainly so the trade is visible: five services and a pre-GA identity provider is meaningfully
more operational surface than four services. That is the real cost of "free licence", and it is the
same cost Keycloak carries — Keycloak simply carries it with a GA release behind it.

### 4. No Python SDK — and this is not a problem

ThunderID ships SDKs for React, Next.js, Express, Vue, Nuxt, Node, vanilla JS, iOS, Android and
Flutter. **There is no Python SDK.** It does not matter, because of which OAuth role each half of
this system plays:

| Component | OAuth role | What it needs |
| --- | --- | --- |
| `frontend/` (Next.js) | **Client** | Runs the login redirect, holds the client secret, manages the session. This is where an SDK earns its keep — `@thunderid/nextjs` exists |
| `backend/api/` | **Resource server** | Only validates an incoming JWT against the JWKS endpoint. ~40 lines of `pyjwt[crypto]` or `authlib` |
| `backend/mcp_server/` | **Resource server** | Same, via `mcp==2.0.0`'s native `TokenVerifier` — see amendment above |

So **no vendor library enters `backend/` at all.** That is worth protecting deliberately: it keeps
the provider swappable the same way SQLAlchemy keeps Supabase swappable, which matters more than
usual given the pre-GA risk in point 3. If adopting a provider ever requires a vendor import below
`api/` or `mcp_server/`, that is a signal the integration is being done wrong.

### 5. Where ThunderID lives — not in this repository

Recorded because it is the question a newcomer to auth asks first, and the wrong answer creates mess
that is annoying to undo. **Treat ThunderID exactly like Postgres.** Supabase's source is not vendored
into `backend/`; neither is this. What belongs in the repo is only: a compose file or `deploy/`
config, environment variables (issuer URL, client ID, client secret), and the generic OIDC validation
code described in point 4.

⚠️ **Trap with the `npx` install path.** `npx thunderid --install-dir . …` writes a datastore and
config files into the current directory. **Do not run it inside the repository** — use a sibling
directory such as `D:\Amzal Projects\thunderid-local\`. The Docker Compose path (pinned at a tag) is
preferred anyway, because it is closer to how the thing will actually be deployed.

Install reference, for the spike: `npx thunderid --install-dir . --admin-username admin
--admin-password secret`, or the pinned `install/quick-start/docker-compose.yml`. Server at
`https://localhost:8090`, console at `/console`, **self-signed certificate** — it must be accepted in
a browser once before any client will talk to it.

### 6. What the MCP authorization spec actually requires

Read 2026-08-13, because "MCP needs the full OAuth stack" was doing a lot of unexamined work in this
file. The requirements on a hosted `mcp_server/` are **resource-server** requirements, and the list
is shorter than the phrase implies:

- It is an **OAuth 2.1 resource server**, and nothing more.
- It **MUST** serve `/.well-known/oauth-protected-resource` (RFC 9728) naming its authorization server.
- It **MUST** validate that the token's audience is **itself** (RFC 8707).
- It **MUST NOT** accept or forward tokens issued for anything else — no passthrough.
- Failures are `401` with `WWW-Authenticate`, or `403` with `insufficient_scope`.
- Clients must validate the `iss` parameter (RFC 9207).
- **RFC 7591 Dynamic Client Registration is deprecated**, in favour of Client ID Metadata Documents.
  The 2026-07-31 table credits Auth0 with DCR as a selling point; that is now a fading advantage.
- **stdio transports SHOULD NOT follow this spec** — which independently confirms that today's local
  setup is correct rather than merely unaudited.

Note what is *absent*: **RFC 8693 is not required by MCP.** Token exchange is our answer to the
delegation problem, not the protocol's demand. That is why point 2's ID-JAG option is genuinely open.

### 7. Sequencing

1. **Spike** — the timeboxed one at the end of the amendment above. Nothing else starts until a real
   downscoped token is accepted by a real `TokenVerifier`.
2. **Commit to a provider** and update this file. ThunderID is the better fit; Keycloak is the safer
   bet; the deciding question is pre-GA tolerance, not features.
3. **Human auth end-to-end** — login in `frontend/`, bearer token attached in `src/lib/api/`,
   `get_actor()` validating the JWT. One gate.
4. **Agent delegation + MCP over Streamable HTTP as a resource server** — points 2 and 6 above, plus
   the transaction-pooler/`NullPool` switch recorded in `BACKEND-PLAN.md`. One gate, and the risky one.
5. **Then deploy.**

One decision deliberately left open, because it belongs to step 2 and not to this file: whether
permissions live in ThunderID roles (carried in the token) or in a local table keyed on the OIDC
`sub`. The permission *strings* are already business rules owned by `services/` — see the `delimiter`
finding above — which argues for the local table, but the token-exchange downscoping rule argues the
issuer needs to know them too. Settle it with the spike in hand.

