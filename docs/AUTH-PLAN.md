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
> **Open item, unresolved:** whether RFC 8693 token exchange is available on the Asgardeo free
> tier. It is the single feature this design rests on, and free tiers commonly gate it. Confirm
> before committing to a provider. If it is paid-only, the free self-hosted answer is Keycloak.

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
| **ThunderID** (Apache 2.0, Go)                                    | **Alpha** — `v1.0.0-alpha2`, breaking changes across recent releases | **You** — binary/container, datastore, TLS, backups | Free licence, paid for in ops                                                                           |
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
`Actor` implementation; `frontend/lib/auth/current-user.ts` will hardcode `"system"` to match it.

Why, restated so it is not mistaken for an oversight: the hard half is _agent_ identity, not human
identity. Human auth is commoditized and can be added in a week. Agent delegation is unsettled — the
best-fitting product is at alpha, and the feature the design rests on is unconfirmed on the free tier
of the shipping alternative. Choosing now would mean choosing on the easy half and discovering the
hard half afterward.

Cost of deferring: three functions — `api/deps.py`'s `get_actor()`, `mcp_server/server.py`'s
`_actor()`, and `frontend/lib/auth/current-user.ts`. Cost of _forgetting_: the privilege-escalation
bypass described under "three deployment shapes" in `docs/BACKEND-PLAN.md`, with no log entry
distinguishing it from
legitimate use.

**Two conditions make this deferral expire.** Either one triggers the auth gate before further
feature work:

1. The MCP server becomes reachable over HTTP by anything that is not the developer's own machine.
2. A second human user exists.

Until both are false, `SystemActor` is acceptable _only_ because no unauthenticated caller exists.

