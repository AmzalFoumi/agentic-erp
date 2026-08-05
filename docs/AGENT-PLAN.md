# The agent service — runtime decision, architecture, and gates 15–21

> **Subordinate to `docs/PLAN.md`.** This file holds the agent workstream in full: why
> Pydantic AI and Gemini Flash were chosen over the alternatives, where conversation state
> lives, what is deliberately not built, and how gates 15–21 are sequenced. Where this file
> and `PLAN.md` disagree, **`PLAN.md` wins** and this file is the thing that is out of date.
>
> It is split out for the same reason `AUTH-PLAN.md` and `FRONTEND-PLAN.md` are: it is read
> when working in `agent/`, and filing it under either existing plan would hide it from the
> other. `PLAN.md` keeps only the items that gate other work — the gate rows and the
> localhost-binding stop condition — because those must sit in the file that is always read.
>
> **It is subordinate in a second sense too.** The auth deferral is recorded in
> `AUTH-PLAN.md` and the privilege-escalation trap in `BACKEND-PLAN.md`. This file
> cross-references both and restates neither.
>
> Every external claim below carries a source and the date it was checked, per the standing
> verify-against-current-docs rule in `PLAN.md`. Things that are **uncertain** are flagged as
> such rather than asserted; each is marked inline and assigned to the gate that settles it —
> enumerated in the re-evaluation at the end. The count started at five and moves as gates
> open and close: Gate 15 closed one (thought signatures) and opened two (Flash-Lite's
> tool-choosing ability, and which `google-genai` API surface Pydantic AI drives). **Four now
> sit on Gate 16, which does not close with any of them open.**

---

## Decision: the runtime is Pydantic AI (2026-08-05)

Compared against LangGraph and Google ADK. The reasoning matters more than the outcome,
because two of the three reasons are about *our* constraints rather than framework quality.

### Why not LangGraph

**Its Python Postgres checkpointer would put unmanaged tables in our schema.**
`AsyncPostgresSaver.setup()` creates `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`
and `checkpoint_migrations`, and the Python package — unlike the JavaScript one — cannot
target a non-`public` schema. It emits unqualified table names whose resolution depends on
the connection's `search_path`. This is an acknowledged gap, tracked as an open feature
request: [langchain-ai/langgraph#7345](https://github.com/langchain-ai/langgraph/issues/7345)
(checked 2026-08-05).

That contradicts a rule this project already wrote down. `public` is Alembic-managed here,
RLS is enabled on every table including `alembic_version` (Gate 3), and
`alembic revision --autogenerate` run from `backend/` diffs models against the live database.
Four tables it has never heard of would appear as four `op.drop_table` calls in the next
generated migration. The whole appeal of `--autogenerate` is not having to read the output
carefully, which is exactly why that failure would land.

**Its approval gate cannot be had without persistence machinery.** LangGraph's `interrupt()`
requires a checkpointer to function at all. So adopting it means paying the persistence cost
on day one to get the approval gate — and in doing so also buying resumability, which we are
deferring (below). Paying for a deferred feature in order to get a non-deferred one is the
wrong trade at this scale.

### Why not Google ADK

Highest churn risk of the three. ADK 2.0 shipped breaking changes across the agent API, the
event model and the session schema: execution moved from a hierarchical agent executor to a
graph-based `WorkflowRuntime`, `Event` gained `node_info` and `output`, and 2.0-generated
sessions are unreadable by ADK versions below 1.28 (checked 2026-08-05 against
[adk.dev/2.0](https://adk.dev/2.0/) and the
[migration write-up](https://dev.to/peytongreen_dev/google-adk-20-is-now-stable-workflow-runtimes-breaking-changes-and-how-to-migrate-4ah8)).

**Where the sources disagree, as required:** Google's own 2.0 docs describe the workflow
runtime and the schema additions plainly, but are considerably softer than the third-party
migration posts on how much 1.x code breaks. The specific claim that "1.x `@tool` decorators
are superseded by `@WorkflowNode` patterns" comes from a community post, not from Google. It
does not change the conclusion — the schema and event-model changes alone are enough — but
the strength of the claim should not be overstated.

### Why Pydantic AI

**It owns no tables.** Conversation persistence stays ours: our models, our Alembic, our
schema, in the database we already have. Nothing to discover in `list_tables` that we did not
put there.

**Its approval mechanism needs no checkpointer.** A run that hits a tool requiring approval
ends with a `DeferredToolRequests` output listing the pending calls. The caller collects the
human's decisions, builds a `DeferredToolResults`, and resumes by passing it *alongside the
original run's message history* — history the caller kept, because the caller always had it.
Confirmed at
[pydantic.dev/docs/ai/tools-toolsets/deferred-tools](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/)
(checked 2026-08-05). Static approval via `requires_approval=True`, conditional approval by
raising `ApprovalRequired`.

That is the whole reason this framework fits: the feature we want arrives without the
feature we are deferring.

**Version.** Observed at **v2.21.0**, released 2026-07-29
([PyPI](https://pypi.org/project/pydantic-ai/), checked 2026-08-05). Deliberately **not a
pin** — this gate installs nothing, and pinning from a number written days earlier is how
five of nine pins were wrong last time. Each gate that installs a package verifies its own
pin against PyPI on the day.

---

## Decision: the model is Gemini Flash on the free tier (2026-08-05)

Reached through Pydantic AI's `GoogleModel` with `GoogleProvider` — the Gemini Developer API
via an AI Studio key, surfaced under the `google:` prefix. `GoogleModel` uses the
`google-genai` package underneath
([Pydantic AI Google docs](https://ai.pydantic.dev/models/google/), checked 2026-08-05).

That underneath was the basis of the teaching gate's design — Gate 15 wrote against
`google-genai` directly so that Gate 16 would wrap a package the developer had already read.
**Gate 15's code was deleted, so that property no longer does any work**, but the dependency
itself still matters: it is why the `anyOf` schema finding and the thought-signature rule from
Gate 15 apply to Gate 16 unchanged, rather than being observations about a package we stopped
using. **Which `google-genai` API surface `GoogleModel` drives is now an open question** — see
Gate 16.

**Pro is not available on the free tier.** Neither Gemini 2.5 Pro nor 3 Pro; the free tier is
scoped to Flash-class models. Flash is also the right call on merit here — the tool-calling
loop is short, the tools are well described, and the latency of a demo panel matters more
than the marginal reasoning quality.

**Which Flash, settled at Gate 15a (2026-08-06): `gemini-3.5-flash-lite`, pinned.** The first
version used the `gemini-flash-latest` alias, on the reasoning that a moving pointer never
retires while a dated model does. The first real call returned **503 UNAVAILABLE** — the alias
resolves to the newest release, which is the one under the heaviest load. "Always current" and
"actually available" pull in opposite directions on a free tier, and availability won.

The cost is not argued away: a dated model eventually retires and that pin is what breaks. It
is acceptable only because the model is a **setting** (`GEMINI_MODEL` in `agent/.env`, read by
`agent/config.py`), so the failure costs one line of config rather than a code change. Fallback
order if it becomes unavailable: `gemini-3.5-flash`, then `gemini-2.5-flash`.

**Open until Gate 16:** whether Flash-Lite is strong enough at *choosing tools*, which is a
different skill from answering well and is not exercised at all by Gate 15a's single call.
Re-check it against the real loop; move up to `gemini-3.5-flash` if it picks wrongly.

### Free-tier limits: what is knowable, and what is not

**⚠️ Uncertain — settled at Gate 16.** Google's
[rate-limits page](https://ai.google.dev/gemini-api/docs/rate-limits) **no longer publishes
per-model free-tier figures.** It states that limits depend on the usage tier and directs you
to your own dashboard at <https://aistudio.google.com/rate-limit> (checked 2026-08-05).

Third-party sources disagree by roughly 6× — 10 RPM / 250 RPD in some, 1,500 RPD in others —
which is consistent with a widely reported free-tier quota reduction in December 2025. **No
number is recorded here**, because a wrong number written confidently is worse than an
acknowledged gap. Confirming the account's actual limits from the AI Studio dashboard is an
explicit item on Gate 16.

### Free-tier data handling, since this will be demoed

**⚠️ Partially uncertain.** Google's
[logs policy](https://ai.google.dev/gemini-api/docs/logs-policy) (checked 2026-08-05) states
that prompt/response logging is available only for **billing-enabled projects**, and that
within those logs, prompts and responses "are not used for product improvement or development"
by default. What the page does *not* state plainly is the converse — the free tier's own data
handling is described by the general API terms rather than by this page.

The practical reading, and it should be treated as a working assumption rather than a quote:
**free-tier usage carries weaker data guarantees than paid, and linking a billing account is
what buys the stronger ones.** For this project that is acceptable, because the demo runs
against a fictional supermarket catalogue. It becomes unacceptable the moment real business
data — real suppliers, real margins, real stock positions — is typed into the panel. That is
worth stating as a condition rather than a footnote: **if the catalogue stops being
fictional, link a billing account before demoing.**

### Rate limiting and backoff

This is the part that survives a quota change, so it is recorded in more detail than the
numbers are.

One conversational turn is **several model calls**, not one — each tool call round-trips
through the model again. At free-tier RPM a single user question can therefore exhaust a
per-minute budget on its own. Backoff is not optional polish here.

A 429 `RESOURCE_EXHAUSTED` from the Gemini API carries structured detail that distinguishes
*which* limit was hit:

- a **`QuotaFailure`** detail whose `quotaId` names the dimension — e.g.
  `GenerateRequestsPerMinutePerProjectPerModel-FreeTier` versus
  `GenerateRequestsPerDayPerProjectPerModel-FreeTier`
- a **`RetryInfo`** detail with a `retryDelay`

**⚠️ Confidence flag.** This structure is corroborated by issue trackers and community
sources ([gemini-cli#9248](https://github.com/google-gemini/gemini-cli/issues/9248) and
related), **not** by Google's own error-reference page, which documents the 429 status but not
the detail payload (checked 2026-08-05). Verify the actual shape against a real 429 at the
gate that implements backoff.

The three-way distinction the panel must make, and why each is different:

| What happened | How it is recognised | What the agent does | What the user sees |
|---|---|---|---|
| **Per-minute limit** | 429, `quotaId` contains `PerMinute` | Back off for `retryDelay` and retry, bounded attempts | "Busy — retrying." The turn is still alive |
| **Per-day limit** | 429, `quotaId` contains `PerDay` | **Do not retry.** Fail the turn | A distinct terminal message naming the daily quota. Retrying until midnight Pacific is not a strategy |
| **Model unavailable** | 5xx, timeout, connection failure | Retry a small number of times, then fail | A generic "the assistant is unavailable" — this is not our quota, it is their outage |

If the `quotaId` is absent or unparseable, treat a 429 as the **per-day** case. Failing
closed costs one retyped question; failing open burns the remaining daily quota in a retry
loop.

---

## Scope: what is in, and what is deferred

**In scope:** conversation history persisted to Postgres, and human approval before any
mutating tool runs.

### Deferred: resumability

A half-finished turn surviving a page refresh — the user asks a question, the agent is
mid-tool-call, the browser reloads, and the turn continues from where it stopped.

**Why it is deferred.** At localhost-and-demo scale the failure mode is a retyped question,
not lost data. Conversation *history* is persisted, so nothing the user said is lost; only
the in-flight turn is. That is a small, visible, recoverable annoyance rather than a
correctness problem, and buying it now means adopting durable-execution infrastructure to fix
a page refresh.

**The upgrade path.** Pydantic AI natively supports four durable-execution backends —
Temporal, DBOS, Prefect and Restate — with the integrations co-maintained by Pydantic and the
vendor teams
([overview](https://pydantic.dev/docs/ai/integrations/durable_execution/overview/), checked
2026-08-05). An agent is wrapped (e.g. `DBOSAgent`) and `Agent.run` becomes a durable
workflow.

**⚠️ Uncertain — verify before adopting.** The exact API and config shape of whichever backend
is chosen must be checked against current docs at that time, not from this paragraph.

**The cost being deferred alongside the work, stated honestly:** DBOS and Temporal checkpoint
into a database, which means adopting one **reintroduces framework-owned tables** — the very
thing that ruled LangGraph out. That is not a reason never to do it; it is a reason to do it
deliberately, at a gate that decides where those tables live, rather than as a side effect of
wanting a page refresh to work.

**The condition that expires the deferral — a proposal, not a measurement.** No usage data
exists yet, so any threshold here is invented and is labelled as such. Proposed: *a second
human uses the agent panel, or a single turn routinely takes long enough that a refresh
during it is plausible rather than unlucky.* Revisit at Gate 21, when the panel is real and
turn duration is observable for the first time.

### Known and accepted gap: approval is not authorization

Even with approval gating, **the window between a user approving and the tool executing is
never zero.** State can change in it. The user approves "adjust Sourdough by +8" against a
displayed quantity of 12, and the tool executes against 15.

More fundamentally, the approval card is a *client-side* construct. The real protection for a
write is server-side — the `Actor` check inside `services/`, and any spend or scope limit
enforced there. Pydantic AI's own documentation makes the same point about its own feature:
human-in-the-loop approval "is *not* an authorization boundary against untrusted clients — it
protects against the model acting without human approval." Those are different things, and
only the second one is what the approval card delivers.

**Cross-reference:** this is the same failure described under "three deployment shapes" in
`docs/BACKEND-PLAN.md` (Gate 6) and restated as the known trap in `CLAUDE.md` — an agent
running with `SystemActor` while acting for a human is more powerful than the human it acts
for. The approval card does not fix that. Only the auth gate does. See `docs/AUTH-PLAN.md`.

---

## Architecture

```
browser ──▶ Next proxy ──▶ agent/ ──▶ MCP (Streamable HTTP, 127.0.0.1) ──▶ backend/services/
   │                          │
   └── agent panel            └── agent's own schema in Postgres (conversations)
```

The agent is **its own directory with its own venv**, a sibling of `backend/` and
`frontend/`. It reaches ERP data **only over the MCP protocol** and never by importing
`backend/services/` — that restriction is the point of the whole design, and importing across
the venv boundary would quietly undo it.

### The modules

| Module | What it does | How it is used | What it depends on |
|---|---|---|---|
| `config.py` | Settings from `agent/.env`, validated at import | Imported by everything, incl. `scripts/` | `pydantic-settings` |
| `mcp_client.py` | Owns the connection to the MCP server and exposes its tools as a toolset | Constructed once at startup, handed to `conversation.py` | Pydantic AI's `MCPToolset`, the running MCP server |
| `conversation.py` | Runs a turn: model call, tool calls, approval interrupts, the reply | Called by `app.py` with our own types in and out | **The only module allowed to import `pydantic_ai`** |
| `store.py` | Persists and loads conversations and messages | Called by `app.py` around each turn | SQLAlchemy, the `agent` Postgres schema |
| `app.py` | The HTTP surface the Next proxy calls; streams responses | The agent's front door | FastAPI, `conversation.py`, `store.py` |

**`config.py` was added at Gate 15a** and the heading changed from "the four modules"; the
original sketch listed only the four that carry behaviour, which quietly assumed settings would
appear from somewhere. It mirrors `backend/core/config.py` — same `BaseSettings` pattern, same
fail-loudly-at-the-boundary reasoning — and is a **copy rather than an import**, because
importing `backend.core.config` would cross the venv boundary that the MCP-only rule above
exists to hold. A dozen duplicated lines is the price of that boundary and it is a good price.

It also holds `mcp_base_url`, which makes it the file where the localhost stop condition is
physically enforced rather than merely documented — commented there in full.

Identity stays a **parameter**, exactly as in `backend/services/` — nothing in `agent/` reads
ambient request state to decide who is acting. That seam is where the auth gate lands here,
and it is deliberately shaped like `api/deps.py`'s `get_actor()` so that both change together.

### The `conversation.py` isolation rule

**`conversation.py` is the only module that may import from `pydantic_ai`.** Its public
functions take and return plain dicts or our own dataclasses — never Pydantic AI message
objects, never `DeferredToolRequests`, never a tool-request type. `store.py` persists our
shapes. `app.py` serialises our shapes.

**Why.** This is the two-adapter thesis one layer up. The project's central claim is that
business logic written once, framework-free, can serve two front doors; the proof was writing
the MCP adapter without opening a single file in `api/`. The same reasoning applies to the
runtime: if a Pydantic AI message object reaches `store.py`, then the database schema encodes
Pydantic AI's internal shape, and switching runtimes becomes a data migration rather than a
code change. Held to, a switch is **a rewrite of one module**. Broken, it is four.

There is a concrete near-term reason too, not just a hypothetical one. Pydantic AI is at
v2.x and moving quickly. A message-format change inside the framework should cost us one
module, not the persistence layer.

**Enforcement — and the honest version of how.** The obvious candidate is an `import-linter`
contract, matching the three that already guard `backend/`. It works, but **not** as a fourth
contract in the existing config, and the difference is worth stating because assuming
otherwise would produce a rule that silently passes.

The existing config lives in `backend/pyproject.toml`, is run as `lint-imports` **from
`backend/`**, and declares `root_packages = ["core", "services", "api", "mcp_server"]`. A
sibling `agent/` with its own virtualenv is not on that graph and cannot be added to it
meaningfully. So the agent gets a **second config and a second command**:

```toml
# agent/pyproject.toml
[tool.importlinter]
root_packages = ["agent"]
include_external_packages = true   # without this the rule matches nothing, silently

[[tool.importlinter.contracts]]
name = "Only conversation.py knows the agent runtime"
type = "forbidden"
source_modules = ["agent.store", "agent.app", "agent.mcp_client"]
forbidden_modules = ["pydantic_ai"]
```

`include_external_packages = true` is load-bearing for the same reason it is in
`backend/pyproject.toml`: by default the graph contains only our own code, so a rule naming
`pydantic_ai` would pass not because the import is absent but because the linter never looked.

**Its cost, stated plainly:** a second `lint-imports` invocation the developer has to
remember, run from `agent/`. That is a real ongoing tax, and it is accepted because the
alternative — enforcing the rule by memory — is what `import-linter` was adopted to replace
in the first place.

**`agent/scripts/` is excluded from this contract**, and the exclusion is narrower than the one
originally written here. The first version exempted `agent/_learning/` on the grounds that
teaching code should import whatever makes the lesson clearest; that directory was deleted at
Gate 15 (see below), so what remains is `scripts/check_mcp.py`, a diagnostic that talks to the
MCP server with no model or runtime involved.

It is excluded because it is deliberately *below* the runtime rather than beside it — it exists
to test the layer the agent sits on, so a rule about which module may import `pydantic_ai` has
nothing to say about it. Worth watching, though: the exemption is safe only while `scripts/`
stays free of the runtime. A diagnostic that starts importing `pydantic_ai` has stopped being a
diagnostic, and should be moved rather than exempted.

---

## Why the browser does not talk to the agent directly

Recorded in full because it is the design decision here most likely to be questioned, and the
one whose reasoning is least self-evident from the code.

The browser talks to a **Next.js route handler**, which forwards to the agent service. The
panel never holds the agent's address or any credential for it.

At first glance this is an extra hop for nothing — today there are no tokens, the agent runs
on localhost, and the proxy adds latency and a file to maintain. The reason it is built now
anyway is that **the hop is where the credential will live**, and retrofitting it later means
retrofitting it into a shipped UI.

This is the **Backend-For-Frontend (BFF)** pattern, and it is not a local invention. The IETF
OAuth working group's
[draft-ietf-oauth-browser-based-apps-26](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-browser-based-apps-26)
(checked 2026-08-05) presents architectural patterns for browser-based apps **in decreasing
order of security, with BFF first**. Its BFF has three responsibilities: act as a confidential
OAuth client, hold access and refresh tokens in a cookie-based session where JavaScript cannot
reach them, and proxy every request to the resource server after attaching the right token.

The security argument is one sentence: **tokens that never enter the browser cannot be
extracted from it.** A browser-based app that holds its own tokens is a public client, so an
attacker with script execution can both read the tokens and start a fresh flow. A BFF is a
confidential client; neither is available.

So the extra hop is not overhead absorbed for a future benefit. It is where the browser-facing
confidential client has to live, built at the point where building it is cheap.

### What this does *not* settle — an open auth-gate question

The delegation half is [RFC 8693 token exchange](https://datatracker.ietf.org/doc/html/rfc8693),
the recorded mechanism in `docs/AUTH-PLAN.md`: the agent presents the user's token as
`subject_token` and receives a *narrower* token carrying both identities. **Where that exchange
runs is not decided by the BFF decision, and this file does not decide it either.**

`docs/FRONTEND-PLAN.md` (Gate 10) already records a position: *"the confidential client that
performs the RFC 8693 token exchange for agent calls will most likely be Python, alongside the
agent service — not Next. The Next tier stays thin."* That is compatible with a BFF — the two
roles are different. The BFF holds the user's session and token custody so the browser never
does; the exchange is a separate step performed by whichever confidential client needs the
narrowed token.

**But it leaves a tension worth naming rather than smoothing over.** If the agent service
performs the exchange, the proxy must hand it something to exchange — and `AUTH-PLAN.md` lists
*forwarding the user's raw token* as one of the two failures the design exists to prevent.
Resolving that is an auth-gate question, not an agent-gate one: it depends on the provider,
on whether the agent can be registered as its own confidential client, and on whether the
chosen provider offers RFC 8693 on a tier we can use — itself still open in `AUTH-PLAN.md`.

Recorded here so the conflict is visible when the auth gate opens. **Nothing in gates 15–21
depends on the answer**, because no token exists yet in any of them.

**One consequence for the frontend's own rules.** `frontend/`'s ESLint
`no-restricted-imports` architecture rules permit only `src/lib/api` to call `fetch`. The
proxy route needs an amendment: **transport-only proxying to `AGENT_BASE_URL` is permitted in
exactly one file.** Transport-only is the operative constraint — the route forwards a request
and streams a response; it does not parse, branch on, or reshape the agent's payload. The
moment it does, it has become a third adapter, which is the mistake `CLAUDE.md` already names
under "no `app/api` handlers mirroring FastAPI." The amendment lands at Gate 20 alongside the
route.

---

## Decision: MCP over Streamable HTTP on localhost (2026-08-05)

The agent reaches the MCP server over **Streamable HTTP bound to `127.0.0.1`**, not stdio.
`backend/mcp_server/server.py` currently ends with `mcp.run(transport="stdio")`; it grows an
HTTP run mode at Gate 16. Gate 6's comment already anticipated this — *"the argument is
written out anyway because it is the line that changes when this server goes remote."*

**⚠️ Verify at Gate 16:** the exact `mcp==2.0.0` API for Streamable HTTP. The SDK is new (the
2026-07-28 spec, adopted one day after release) and this is precisely the kind of thing
training data gets wrong.

Stdio was the alternative and was rejected despite being simpler: it would have made the
agent responsible for launching the backend's virtualenv as a subprocess, coupling two
directories that otherwise share nothing but a protocol. HTTP costs a third server to start
and buys a boundary that stays honest.

### The stop condition — written down so scenario A cannot quietly become scenario B

**The MCP server binds `127.0.0.1` only.** This is the entire basis on which the design runs
unauthenticated.

`docs/AUTH-PLAN.md` records two conditions that expire the auth deferral. The first is: *the
MCP server becomes reachable over HTTP by anything that is not the developer's own machine.*
A loopback-bound socket does not trip it. **Everything else does.**

Concretely, each of the following triggers the auth gate **before any further agent work**:

1. The bind address changes from `127.0.0.1` to `0.0.0.0` or a LAN address.
2. The server is placed behind a tunnel, reverse proxy, or port-forward of any kind — ngrok,
   Cloudflare Tunnel, a Docker port publish, a cloud deployment.
3. Any process on a second machine successfully calls it.

The reason this is written as a list rather than a principle: the dangerous version of this
mistake is not a decision, it is a convenience. "I'll just tunnel it so I can demo from my
phone" is a thirty-second action that converts an unauthenticated localhost service into an
unauthenticated internet service, with an MCP tool surface that can mutate inventory, and no
log entry distinguishing the caller from the developer. A principle can be reasoned around at
speed. A list cannot.

---

## Decision: the agent owns its own schema and its own Alembic (2026-08-05)

Conversation tables live in a **Postgres schema named `agent`**, migrated by **`agent/alembic/`**
with its own independent history, with models defined in `agent/store.py`. Same Supabase
instance, same connection style (session pooler), RLS enabled to match the convention on every
other table.

### Why not simply put them in `public` with the rest

Two failure modes, and they are the same two that ruled LangGraph out — which makes the
symmetry worth naming. Rejecting a framework for a problem and then reproducing the problem by
hand would be an unusually silly outcome.

**Failure one: the version table collides.** Alembic records the applied revision in a table
named `alembic_version` — one row, one column, and that name is the default. Two independent
Alembic setups against one database write to the same row. Backend applies `abc123`; the agent
then applies `def456` and overwrites it; the next `alembic upgrade head` from `backend/` reads
a revision id that is not in its own history and refuses to proceed.

**Failure two, worse: autogenerate proposes deletions.** `alembic revision --autogenerate` run
from `backend/` diffs `core.models.Base.metadata` against the live database. It would find
`conversations` and `messages` present in the database and absent from the metadata, conclude
they were deleted, and write `op.drop_table("conversations")` into the migration.

### Why a separate schema fixes both at once

`include_schemas` **defaults to `False`**, so Alembic autogenerate reflects only the default
schema; and `version_table_schema` places the version table wherever it is told
([Alembic runtime docs](https://alembic.sqlalchemy.org/en/latest/api/runtime.html), checked
2026-08-05). So:

- Backend autogenerate **cannot see** the agent's tables, and therefore cannot propose
  dropping them. Failure two is not mitigated, it is impossible.
- The agent's version table sits at `agent.alembic_version`, so failure one cannot occur.

One decision, both failure modes gone, and no hand-written guard that has to keep working.

### The decoupling claim, stated honestly

The reason this shape was chosen over the alternatives is that it survives the two futures the
developer named: swapping the agent out, and going microservices later.

**What it genuinely buys.** The agent's storage is reached through one connection string in
`agent/`'s own config, one metadata object, one migration history, in one namespace nothing
else reads. Moving it to a separate database is **editing that connection string** — nothing
in `backend/` knows the tables exist, so nothing in `backend/` changes. Removing the agent
entirely is `DROP SCHEMA agent CASCADE` plus deleting the directory, with no risk to
`products`.

**What it does not buy, so it is not oversold.** A schema is a namespace, not an isolation
boundary. Both services still point at one Postgres instance and share its uptime, its
connection limit, and its blast radius. Nothing here prevents a credential with broad rights
from reading across schemas — RLS is the backstop for that, exactly as recorded in `PLAN.md`,
and authorization remains enforced in code.

That is the correct amount of separation for localhost-and-demo: the shape that makes the next
step cheap, rather than the shape that makes it unnecessary.

---

## Gates 15–21

Numbering continues **flat** from the `PLAN.md` table, for the reason recorded there: a
parallel sequence would give "which gate are we on" two answers. The stop-gate ritual is
unchanged — the developer runs every command, the agent explains and hands off, each gate ends
with a manual commit.

The gates are small on purpose. The developer is new to agentic AI, and the failure mode being
designed against is a single large gate that works without being understood.

### Gate 15 — the teaching loop (no framework). Ran; findings kept, code deleted

**Outcome, 2026-08-06.** The gate was built and run, produced six findings that changed four
later gates, and then **its code was deleted at the developer's decision as not worth
maintaining.** One script survives, repurposed as a diagnostic. This section records what
happened and why, because "we tried a hand-written teaching loop and did not keep it" is a
decision worth not re-litigating.

The original intent stands as written history: a bare agent loop against the Gemini SDK
(`google-genai`) and the MCP Python SDK client, with nothing between them —

> model call → tool-use response → dispatch to the MCP client → feed the result back → repeat

— built as four sub-gates (15a a raw call; 15b one tool declared by hand and deliberately not
executed; 15c the MCP client with no model; 15d the two joined, shipped with its tool-dispatch
block raising `NotImplementedError` for the developer to complete).

#### What was kept

| Kept | Where | Why |
|---|---|---|
| `config.py`, `requirements.txt`, `.env.example`, `agent/.gitignore` | `agent/` | Real infrastructure, not gate artifacts. Would have been written at Gate 16 regardless |
| The MCP-client script, as a **diagnostic** | `agent/scripts/check_mcp.py` | Operational value, not teaching value — see below |
| Six findings | This file | The gate's actual output |

**`agent/scripts/check_mcp.py`** drives the six MCP tools with no model in the path. When the
agent misbehaves at gates 16–21, running it settles whether the tools work — halving the search
space without guessing. It also prints the raw parameter schemas, which is how a Gemini 400 that
names a schema rather than a tool gets diagnosed. It needs a three-line change at Gate 16 when
the server goes HTTP: the subprocess block collapses to `Client(settings.mcp_base_url)`.

Note it connects over **stdio**, not HTTP — `mcp_server/server.py` still ends with
`mcp.run(transport="stdio")` and the HTTP run mode is Gate 16 work. So it spawns the server as a
child process and hardcodes the path to *the backend's* interpreter, because the server needs
`sqlalchemy` and `psycopg` and `agent/`'s venv has neither. That is exactly the coupling the
Streamable-HTTP decision above rejected; it is commented as such in the file.

#### Why the rest was deleted

**The stated reason for keeping it did not survive contact.** The plan said the code's value was
highest six months out, when the framework has hidden all of this and something breaks inside
it. Against that: nothing tests these files, nothing imports them, and they were excluded from
the import-linter contract by design — so they cannot rot loudly. And this gate itself proved
they *would* rot, by discovering that `google-genai` already ships two competing generation APIs
with Google's own docs site documenting the one we are not using. A teaching artifact frozen
against a superseded API is not a true picture of what the framework replaced; it is a
confidently wrong one, read by someone debugging.

`15d` had a second problem specific to it: a permanently committed file that raises
`NotImplementedError` reads as broken code to anyone who has not read this plan. It made sense
only as a live exercise.

**What was genuinely produced was the findings, and they are recorded where they are enforced**
— in the gate write-ups below, not in code comments. Deleting the scripts costs none of them.

#### The six findings, and where each lands

1. **Thought signatures — settled.** Recorded in full below; the rule is that history is
   appended as *objects*, never rebuilt from `part.text`. Consequence for Gate 18.
2. **Optional parameters arrive as `anyOf`.** `@mcp.tool()` renders `search: str | None` as a
   union of string and null, in five of the six tools. Gemini's function-calling schema handles
   that unreliably, so tool schemas must be normalised before being declared — collapse
   `anyOf: [X, null]` to `X` (already optional by absence from `required`) and drop pydantic's
   generated `title`, keeping `default`. Lands at **Gate 16**, in whatever code declares tools.
3. **`FunctionResponse.id` must be echoed from the request.** It is how the model matches a
   result to its call; without it, *parallel* tool calls are silently mismatched rather than
   rejected. Lands at **Gate 19**.
4. **`FunctionResponse.response` is a keyed dict** — `"output"` for success, `"error"` for
   failure. Which converges with MCP's own choice to report tool failures as results rather than
   protocol errors: both protocols independently decided a failed tool is information the model
   should read, not an exception to raise. Good sign the approval design cuts with the grain.
5. **A response can request several tools at once.** This file described "the tool-use response"
   in the singular throughout. A loop written from that description works against one call and
   silently drops the rest of a parallel batch. Consequence for **Gate 21**: an approval card may
   have to present several pending mutations from one turn, which `FRONTEND-PLAN.md`'s state
   table — one card, one product — does not currently answer.
6. **`google-genai` 2.16.0 ships two generation APIs**, and the docs site documents the one we
   are not using. Full note under Gate 16, where it is a blocking item.

Also noted: `google-genai`'s `types.Tool` has an `mcp_servers` field — the SDK can act as an MCP
client and run the whole tool loop itself. Deliberately unused. It would have hidden the entire
lesson at Gate 15, and from Gate 16 the loop belongs to Pydantic AI; two frameworks racing to
own it is not a design.

#### Two corrections to the plan that the gate forced, worth keeping

**async/await arrives here, not at Gate 16.** The MCP client is async to the bottom — a
connection is a long-lived thing with a subprocess or socket behind it — so there is no
synchronous way to write the client script at all. Gate 16's Python-concepts note is corrected
there.

**"Deliberately under-abstracted" was ambiguous, and the ambiguity produced a wrong first
cut.** The first version of the raw-call script read `os.environ["GEMINI_API_KEY"]` directly and
skipped `config.py`, reasoning that a settings object was ceremony a teaching script did not
need. The developer rejected it: teaching code must stand on the *same infrastructure the real
agent uses*, with only the reasoning left flat. The rule was restated as **flatten the thinking,
not the plumbing**, and it is the reason `config.py` exists as production code from Gate 15
rather than Gate 16. It is recorded here because it outlived the code it was written for —
`agent/scripts/check_mcp.py` still follows it, and so should anything else written to be read.

#### The four comprehension questions, unretired

The gate was specified to close on these rather than on tests, and deleting the code does not
answer them. They remain the right questions and each is a decision made in a later gate —
question 3 is Gate 19, question 4 is the resumability deferral:

1. Where does the loop terminate, and what stops runaway tool calls?
2. What exact shape does a tool result take going back to the model?
3. Which line would an approval check sit on?
4. What is lost if the process dies mid-turn?

**They now land at Gate 16 instead**, against Pydantic AI's loop rather than a hand-written one.
That is a weaker position than the plan intended — the questions were chosen so the framework's
choices could be *judged* rather than accepted, and judging them is harder without having built
the alternative. Stated plainly rather than smoothed over: this is the cost of the deletion, and
it was accepted knowingly.

**Settled at Gate 15b — thought signatures, and why history is handled as objects.**

Gemini 3.x attaches an opaque `thought_signature` (bytes) to response parts. The SDK's own
field description calls it "an opaque signature for the thought so it can be reused in
subsequent requests"; Google's [thinking guide](https://ai.google.dev/gemini-api/docs/thinking)
is explicit that a client managing its own history **must resend the model's parts exactly as
received**, and must not remove or modify them, because the signatures are what let the model
continue its reasoning (checked 2026-08-06 — flagged as unverified when it entered this plan,
now confirmed against both the docs and the installed `google-genai` 2.16.0 type).

Dropping them is not an error. There is no exception and no warning — just a model that gets
quietly worse at multi-step work. Which makes it exactly the class of bug worth spending a
paragraph on before it happens rather than an afternoon on afterwards.

**The rule this produces, and it outlives the teaching gate:** append the model's `Content`
**object** to the history untouched. Never rebuild one from `part.text`. Handle the object; do
not copy the value.

**This has a consequence for Gate 18 that should be decided there, not assumed.** `store.py`
persists *our* shapes, not Pydantic AI's (the isolation rule). But an opaque signature is not
one of our shapes — it is a blob whose only meaning is to the model. So conversation history
that round-trips through Postgres has to carry it, or a reloaded conversation resumes with its
reasoning thread cut. That is a real design question for the persistence gate: **our message
type needs somewhere to keep provider-opaque bytes without letting the provider's message
format into the schema.** Recorded here so it arrives at Gate 18 as a known requirement rather
than a surprise.

**Also noted at 15b:** `google-genai`'s `types.Tool` has an `mcp_servers` field — the SDK can
act as an MCP client and run the whole tool loop itself. Deliberately unused here and later.
At Gate 15 it would hide the entire lesson; from Gate 16 the loop belongs to Pydantic AI, and
two frameworks racing to own it is not a design.

**Not in this gate:** Pydantic AI, persistence, approval, HTTP, the frontend.

### Gate 16 — Pydantic AI against the running MCP server

Pydantic AI installed and pinned (verified against PyPI on the day). `GoogleModel` +
`GoogleProvider` with an AI Studio key. `MCPToolset` connected to the MCP server over
**Streamable HTTP**; the server's HTTP run mode lands here.

**Also in this gate — four items, and the gate does not close with any of them open:**

1. Confirm the account's real free-tier limits from <https://aistudio.google.com/rate-limit>
   and record them with the date.
2. Verify the `mcp==2.0.0` Streamable HTTP API against current docs. Gate 15c settled the
   *client* half by introspecting the installed package — `Client(url)` selects
   `streamable_http_client` internally, so the agent side is likely one line. **The server
   half is the unverified part**, and it is a change to `backend/mcp_server/server.py`, not to
   `agent/` — easy to overlook in an agent gate.
3. Judge whether `gemini-3.5-flash-lite` is strong enough at *choosing tools*. Gate 15
   exercised tool choice only against a hand-written declaration; whether Lite picks correctly
   among all six real tools is untested.
4. **Settle which google-genai API surface Pydantic AI's `GoogleModel` uses** — see below.
   This is new, found at Gate 15.

**⚠️ New uncertainty flag, opened 2026-08-06 at Gate 15b.** The installed `google-genai`
2.16.0 ships **two** generation APIs: `client.models.generate_content` (what its own README
documents, and what Gate 15 is written against) and `client.interactions.create` (what
<https://ai.google.dev>'s current quickstart and function-calling pages document, with a
different shape — `input=`, `steps`, `previous_interaction_id`, server-side state). Both
modules exist in the package; neither source acknowledges the other.

Gate 15 uses `generate_content` deliberately. It is what the package's own README shows, and
more importantly it is stateless — history is a list we own and resend, which is the property
Gate 18's persistence design depends on. `interactions.create` with `previous_interaction_id`
puts conversation state on **Google's** servers, which would quietly relocate the thing this
project has decided to store in its own Postgres schema.

**Why it matters at Gate 16 rather than now:** re-evaluation item 1 below says Gate 15 and 16
share a package, so the framework is added to code already read. That property only holds if
`GoogleModel` also uses `generate_content`. If it has moved to the Interactions API, the
teaching gate still teaches the protocol correctly but no longer teaches *this* framework's
mechanics — and the stateless-history assumption needs re-checking against how Pydantic AI
drives it. Check `GoogleModel`'s source on the day, not its docs.

**Python concepts introduced:** none new — async/await and async context managers arrive
earlier, at 15c, because the MCP client has no synchronous form. Corrected 2026-08-06; see the
note under Gate 15.

**Done looks like:** a script that answers "what's low on stock?" by calling the real
`list_products` tool against the real database.

**Not in this gate:** persistence, approval, HTTP surface, our own boundary types.

### Gate 17 — the conversation loop with our own boundary types

`conversation.py` and `mcp_client.py`. Our own dataclasses for messages and turn results. The
isolation rule lands here, with `agent/pyproject.toml` and its `lint-imports` contract.

**Python concepts introduced:** dataclasses as a boundary type; why a public function's
signature is an architectural decision.

**Done looks like:** `lint-imports` run from `agent/` reports the contract kept, and
`conversation.py` is the only file that would break if `pydantic_ai` vanished.

**Not in this gate:** anything touching the database or the network beyond MCP.

### Gate 18 — persistence

`store.py`, `agent/alembic/`, the `agent` schema, `version_table_schema="agent"`, RLS enabled
on the new tables. Conversations and messages persisted and reloaded.

**Verification includes the negative case**, because it is the whole reason for the design:
run `alembic revision --autogenerate` from `backend/` and confirm the generated migration is
empty — that it does **not** propose dropping the agent's tables.

**Not in this gate:** resumability. History survives; an interrupted turn does not.

### Gate 19 — approval gating

`requires_approval=True` on the three mutating tools — `create_product`, `update_product`,
`adjust_stock` — surfaced through `DeferredToolRequests`, resumed with `DeferredToolResults`
plus the stored message history.

The three read tools (`list_products`, `get_product`, `get_product_by_sku`) run without
approval; gating reads would make the panel unusable and protects nothing.

**Done looks like:** a turn that stops with a pending approval, and resumes correctly on both
approve and deny.

**Not in this gate:** the UI for it. This is proven at the API level first, because a broken
interrupt behind a nice card is very hard to diagnose.

### Gate 20 — the HTTP surface

`app.py` with SSE streaming, and the Next proxy route at
`frontend/src/app/api/agent/[...path]/route.ts`. The ESLint `no-restricted-imports` amendment
lands here: transport-only proxying to `AGENT_BASE_URL` permitted in exactly that one file.

**Not in this gate:** the panel's five states.

### Gate 21 — the frontend panel

Build the **six** unbuilt states specified in `docs/FRONTEND-PLAN.md` — idle/empty, thinking,
streaming reply, tool call in progress, success, refusal — against the shipped
`agent-panel.tsx`, which currently exists only in the unavailable state.

*(Gate 12e's write-up says "five" in three places while its own state table lists six rows and
its footnote says "six interactive states". Six is correct; the count is corrected in
`FRONTEND-PLAN.md` and `PLAN.md` too. Recorded because a gate whose "done" is a count should
not disagree with itself.)*

**The tool-call-in-progress state is the one this whole design exists to protect.**
`FRONTEND-PLAN.md` already specifies it precisely: an uppercase label, a card naming the
product and showing `12 → 20 (+8)` in tabular numerals, then Confirm / Cancel. That maps
exactly onto `DeferredToolRequests` / `DeferredToolResults` — which is a pleasant confirmation
that the design and the runtime agree, arrived at independently and two months apart.

Read the spec from `FRONTEND-PLAN.md`'s state table rather than from memory, and re-fetch from
the Claude Design project if the markup has moved.

**Also at this gate:** revisit the resumability deferral, per its condition above — this is the
first point at which real turn duration is observable.

---

## Re-evaluation, per step 4 of the stop-gate ritual

Writing this file surfaced five things that were not visible when the plan was agreed.

**1. The teaching gate got better, not just longer.** The discovery that Pydantic AI's
`GoogleModel` sits on top of `google-genai` means Gate 15 and Gate 16 use the *same package*.
The framework is added to code the developer has already read, rather than substituted for
code they never saw. That was luck rather than design, and it is worth protecting: if the model
choice changes, check whether this property survives.

> **Superseded 2026-08-06.** Gate 15's code was deleted, so there is no longer any
> already-read code for the framework to be added to. The shared dependency still matters for a
> different reason — Gate 15's findings about `google-genai` carry into Gate 16 unchanged
> instead of being observations about a package we abandoned — but the pedagogical benefit
> claimed here is gone. Kept rather than edited away, because the item's real lesson is the one
> it ends on: a property arrived at by luck is worth *checking* rather than relying on, and this
> one did not survive its first contact with a scope decision.

**2. The resumability deferral is less clean than it first looked.** The stated upgrade path —
wrap the agent for durable execution — reintroduces framework-owned tables, which is the
headline reason LangGraph was rejected. The deferral still holds, but the file now says so
explicitly rather than presenting the upgrade as free. Anyone taking it up later should treat
"where do the checkpoint tables live" as a gate question, not an implementation detail.

**3. Five uncertainty flags are carried rather than resolved.** Two close at Gate 16 — the
Gemini free-tier limits, and the `mcp==2.0.0` Streamable HTTP API. The 429 detail structure
closes whenever backoff is implemented. The free-tier data-handling wording closes if and when
the catalogue stops being fictional. The durable-execution config shape closes only if
resumability is ever taken up. None blocks the gate before it, which is why they are flagged
rather than researched further now — but **Gate 16 should not be called done with its two
open**.

**4. A conflict with `FRONTEND-PLAN.md` surfaced and is recorded rather than resolved.** Gate 10
already stated that the RFC 8693 exchange would most likely run in Python beside the agent, not
in Next. That is compatible with the BFF decision, but it implies the proxy hands the agent
something to exchange — and `AUTH-PLAN.md` lists forwarding the user's raw token as a failure
mode. The BFF section above now names the tension and assigns it to the auth gate. Nothing in
gates 15–21 depends on the answer.

**5. Nothing else should change.** The gate sequence, the four modules, and the three
decisions settled with the developer this session all survived being written out at length.
The one correction made in the writing is the import-linter enforcement, which is a second
config and a second command rather than a fourth contract — recorded accurately above, because
the version that was assumed would have produced a rule that passed without ever looking.

### Added 2026-08-05, at Gate 15a

**6. "Deliberately under-abstracted" was ambiguous, and the ambiguity produced a wrong first
cut.** The constraint was read as licence to skip real infrastructure — the first raw-call script
read `os.environ` directly rather than using a settings object. The developer rejected it:
teaching code must stand on the *same infrastructure the real agent uses*, with only the
reasoning left flat. Restated as **flatten the thinking, not the plumbing** — recorded under
Gate 15, where it outlived the code it was written for.

Two consequences beyond the wording. `config.py` joined the module table, which had listed only
the four behaviour-carrying modules and silently assumed settings would materialise. And Gate
15a's scope grew to land the agent's config, `requirements.txt`, `.env.example` and its own
`.gitignore` — the right growth, since all four were due at Gate 16 anyway and are the part of
Gate 15 that survived it.
**7. `agent/` gets its own `.gitignore`, duplicating the root's secret rules.** Developer's
call, and the reasoning generalises: the root `.gitignore` already covers `.env`, so the second
file adds no rule — it adds a second thing that must fail before a key escapes. The asymmetry
justifies it. A redundant ignore rule costs nothing and is never noticed; a leaked API key
cannot be un-leaked, since `git rm --cached` clears the tip but not the history and the key
still has to be revoked. Worth applying to `backend/` and `frontend/` at whichever gate next
touches them.

### Added 2026-08-06, at Gates 15b–15d, and revised the same day when the code was deleted

**8. Google's own documentation site could not be trusted for the SDK's API, and introspecting
the installed package was the thing that worked.** Three separate fetches of `ai.google.dev` —
quickstart, function calling, models — returned an `interactions.create` API that contradicts
the `google-genai` README and is not what this project uses. Both surfaces genuinely exist in
2.16.0. Every API detail at Gate 15 was therefore verified by reading the installed `types.py`
and `client.py`, not by reading docs.

Worth generalising, because `PLAN.md`'s standing rule says *verify against current docs rather
than training data* and this is a case the rule did not anticipate: **docs and installed package
can both be current and still disagree.** When they do, the package wins for what a call
accepts, and the docs win for what the *service* requires. The thought-signature rule came from
the docs for exactly that reason — no amount of reading `types.py` tells you signatures must be
resent.

**9. The gate's findings are recorded under Gate 15 rather than here**, deliberately: five of the
six are enforced by later gates (16, 18, 19, 21) and belong beside the gate that acts on them,
not in a re-evaluation list nobody reads while implementing. This item exists only to say where
they went.

**10. The gate's code was deleted, and the plan records that rather than hiding it.** The
developer's judgement was that the teaching loop was not worth its maintenance; on review the
plan's own justification for keeping it — value six months out — was found to be weaker than
written, since nothing tests or imports the files and this very gate proved the underlying SDK
is moving fast enough to make a frozen artifact misleading rather than instructive.

**The cost was accepted knowingly and is stated at Gate 15 rather than argued away:** the four
comprehension questions were chosen so the framework's choices could be *judged* rather than
accepted, and judging them is harder without having built the alternative. They move to Gate 16.

The generalisable part: **a gate can be worth running and not worth keeping.** Six findings
changed four later gates; the artifact that produced them changed nothing after the day it was
written. Recording the deletion with its reasoning is what stops the idea being re-proposed at
the next gate that feels under-understood.