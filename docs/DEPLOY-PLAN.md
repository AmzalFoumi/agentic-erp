# DEPLOY-PLAN.md — Gate 26: putting it online

**Scope: gate 26 only.** `docs/PLAN.md` remains the root source of truth and the progress table;
this file is the detail doc for the deployment gate, the way `BACKEND-PLAN.md` is for gates 0–8 and
`AUTH-PLAN.md` is for gates 22–25.

**Status: not started.** Gate 25 is code-complete but its pull request (#30) is not merged yet. The
block is real, not a formality — see "Entry conditions" below.

**Where this content was before.** Gate 26 was written up inside `AUTH-PLAN.md`, because at the
time it looked like the last of the login gates. It is not: gates 22–25 are about *who you are*,
gate 26 is about *where the code runs*. Splitting it out on 2026-08-26 closes `AUTH-PLAN.md` at
gate 25 and gives the deployment work a doc it can grow into. Everything below was moved here
as-is; nothing was reworded to look better than it is.

---

## What this gate actually is

**Five things to host, not four.** The website, the web API, the agent-server, the AI agent, and
**the login server**. ThunderID has no hosted option, so we run it ourselves — a real, recurring
cost of the provider decision, recorded in `AUTH-PLAN.md`.

Today all five run on the developer's machine. The container recipe in `deploy/` — its `README.md`
covers safe shutdown and restart — is **for local use only** and is not a deployment artefact. How
the five actually get hosted is an open decision this gate has to make; nothing is chosen yet.

---

## Entry conditions

These must all be true before gate 26 work begins:

1. **PR #30 merged.** Gate 25's code is on `feat/auth/agent` and pushed, with CodeRabbit's findings
   addressed, but the PR is still open against `dev`. Merge `#30` → `dev`, then `dev` → `main`.
2. **Both suites green on the merge result** — `backend/` 72 passed, `agent/` 29 passed,
   `lint-imports` 4 contracts kept / 0 broken, as of `c704312`.
3. **Nothing else half-finished.** As of 2026-08-26 there is one known loose end, and it is
   optional rather than blocking: pre-gate-25 conversation rows (e.g. conversation 5) carry
   `started_by = "system"` and now 404 for every real person. Leaving them is the recommended
   choice; a SQL update stamping them with the developer's `sub` is the alternative.

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
