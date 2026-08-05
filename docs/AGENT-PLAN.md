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
> verify-against-current-docs rule in `PLAN.md`. Five things are flagged as **uncertain**
> rather than asserted; they are marked inline and each is assigned to the gate that settles
> it — enumerated in the re-evaluation at the end.

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

That underneath matters for the teaching gate: **Gate 15 writes against `google-genai`
directly, and Gate 16 wraps the same package in `GoogleModel`.** The framework is added to
code the developer has already read, rather than substituted for code they never saw.

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
| `config.py` | Settings from `agent/.env`, validated at import | Imported by everything, including `_learning/` | `pydantic-settings` |
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

`agent/_learning/` is excluded from this contract. It is teaching code, it imports whatever
makes the lesson clearest, and nothing that runs imports it.

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

### Gate 15 — the teaching loop (no framework)

**Before any framework is installed.** A bare agent loop written directly against the Gemini
SDK (`google-genai`) and the MCP Python SDK client, with nothing between them:

> model call → tool-use response → dispatch to the MCP client → feed the result back → repeat

**Sub-gates**, broken up the way 12 and 13 were:

| Sub-gate | What is built | What it teaches |
|---|---|---|
| **15a** | A raw model call, no tools. Send a string, print the response. | The SDK's request/response shape; where the API key lives; what a "turn" is |
| **15b** | One tool declared **by hand** (`list_products`). Print the tool-use response. **Do not execute it.** | That the model does not call anything — it *asks*, and control returns to your code. This is the single most important idea in the gate |
| **15c** | The MCP client alone against the running server. List tools, call one by hand. | That MCP is just a protocol; the server is already built and already works |
| **15d** | The two joined into the loop. | Where the loop lives, and that it is ordinary Python |

**Constraints, because the purpose is comprehension rather than shipped code:**

- **Deliberately under-abstracted.** One flat function, an explicit `while` loop, no helper
  layer, no clever error handling. Ugly and readable beats elegant and opaque. This is the one
  gate in the project where that is the correct trade, and it is only correct because the
  output is quarantined.
- **But flat means the *logic*, not the *plumbing*. Amended 2026-08-05, during 15a.** The
  first cut of `15a_raw_call.py` read `os.environ["GEMINI_API_KEY"]` directly and skipped
  `config.py`, on the reasoning that a settings object was ceremony a teaching script did not
  need. **That was wrong**, and the developer corrected it: the teaching scripts must stand on
  the *same infrastructure the real agent will use* — the same `BaseSettings` config, the same
  `.env`, later the same session and store — with only the agent reasoning left flat.

  The reason it was wrong is the reason `_learning/` is kept at all. Its value is that it is
  **the same system with fewer layers**, so that six months from now, when something misbehaves
  inside Pydantic AI, these files are still a true picture of what the framework is doing. A
  script wired to throwaway config is a *different* system, and the moment the real config
  landed, the loop the developer had read would stop being the loop that runs. The lesson
  evaporates precisely when it is needed.

  So the rule, stated so it survives into 15b–15d: **flatten the thinking, not the plumbing.**
  No helper layer over the model call, no wrapper class over the loop, nothing to jump to in
  order to follow the flow — and real settings, real clients, real error types underneath it.
  The one concession is `sys.path` scaffolding in each script, because `agent/` does not become
  an importable package until Gate 17; it is commented as scaffolding wherever it appears.
- **Comments explain the protocol, not the Python.** What a tool-use block is, what shape a
  result goes back in, why the whole conversation is resent each time. Not what a `while` loop
  does.
- **The tool-dispatch block is left as `raise NotImplementedError`**, with a comment
  describing what belongs there. The developer fills it in. Reading a working loop teaches
  less than completing a broken one.

**This gate does not close on tests passing.** There are no tests. It closes when the developer
can answer these four, unprompted:

1. **Where does the loop terminate, and what stops runaway tool calls?**
2. **What exact shape does a tool result take going back to the model?**
3. **Which line would an approval check sit on?**
4. **What is lost if the process dies mid-turn?**

Those are the exit criteria, and they are chosen deliberately: each one is a design decision
made in a later gate. Question 3 is Gate 19. Question 4 is the resumability deferral. A
developer who can answer them can evaluate the framework's choices instead of accepting them.

**This code is kept**, at `agent/_learning/`, excluded from the import-linter contract and
imported by nothing that runs, with a header stating it is a teaching artifact and not the real
loop. Kept rather than deleted because its value is highest six months from now, when the
framework has hidden all of this and something has gone wrong inside it. A framework is much
easier to debug when you have read the thing it replaced.

**Not in this gate:** Pydantic AI, persistence, approval, HTTP, the frontend.

### Gate 16 — Pydantic AI against the running MCP server

Pydantic AI installed and pinned (verified against PyPI on the day). `GoogleModel` +
`GoogleProvider` with an AI Studio key. `MCPToolset` connected to the MCP server over
**Streamable HTTP**; the server's HTTP run mode lands here.

**Also in this gate:** confirm the account's real free-tier limits from
<https://aistudio.google.com/rate-limit> and record them with the date, closing the first of
the three uncertainty flags above. Verify the `mcp==2.0.0` Streamable HTTP API against current
docs, closing the second.

**Python concepts introduced:** async/await and async context managers, which Pydantic AI's
MCP client requires and which the rest of this codebase has so far avoided.

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
cut.** The constraint was read as licence to skip real infrastructure — the first
`15a_raw_call.py` read `os.environ` directly rather than using a settings object. The developer
rejected it: the teaching scripts are how they learn the system, so the scripts must *be* the
system, minus the abstraction. The constraint is now stated as **flatten the thinking, not the
plumbing**, in full under Gate 15.

Two consequences beyond the wording. `config.py` joined the module table, which had listed only
the four behaviour-carrying modules and silently assumed settings would materialise. And the
scope of Gate 15a grew slightly — it now lands the agent's config, its `requirements.txt`, its
`.env.example` and its own `.gitignore`, not just a script. That is the right growth: those
files were going to be written at Gate 16 regardless, and writing them now means the teaching
scripts and the real agent never diverge.

**7. `agent/` gets its own `.gitignore`, duplicating the root's secret rules.** Developer's
call, and the reasoning generalises: the root `.gitignore` already covers `.env`, so the second
file adds no rule — it adds a second thing that must fail before a key escapes. The asymmetry
justifies it. A redundant ignore rule costs nothing and is never noticed; a leaked API key
cannot be un-leaked, since `git rm --cached` clears the tip but not the history and the key
still has to be revoked. Worth applying to `backend/` and `frontend/` at whichever gate next
touches them.
