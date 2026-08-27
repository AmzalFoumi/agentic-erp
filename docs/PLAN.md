# Supermarket Inventory — build plan

> This is the **permanent, saved** copy of the plan and the **main source of truth**. It gets
> updated at the end of every stage of work (a "gate") to record what was actually built.
>
> It holds everything every gate needs, and nothing else: the progress table, the background
> story, the rules for how work happens, and the project's file structure as it actually is. More
> detail lives in three other files — if any of them disagrees with this one, **this file is
> right** and the other one is out of date:
>
> | File | Holds | Read when |
> | ---- | ----- | --------- |
> | `docs/BACKEND-PLAN.md` | Gates 0–8, backend decisions and things we put off for later | Changing backend code |
> | `docs/FRONTEND-PLAN.md` | Gates 9–13, a list of screens/features, design reasoning | Changing frontend (UI) code |
> | `docs/AUTH-PLAN.md` | Gates 22–25: the login/security decision, the mechanism, the login providers we checked | The login/security gates |
> | `docs/DEPLOY-PLAN.md` | Gate 26 in detail: sub-gates 26a–26i, the “Aisle in a box” design, and the three things gate 25 handed over | The deployment gate |
> | `docs/AGENT-PLAN.md` | Gates 14–21, how the AI agent works | Changing the AI agent's code |
> | `docs/CI-PLAN.md` | Gates CI-1–CI-2: running the backend/agent test suites and `lint-imports` automatically on every PR | Changing CI, or anything that could break the test suites |
> | `docs/FEATURES-PLAN.md` | Gates 27–30: the Action Draft approval queue and the three standout features (spoilage markdown, reorder/MOQ, delivery discrepancy) | Building any of those features |
>
> **Every decision is written down once, in the file responsible for it**; the other files just
> link to it instead of repeating it. Rules that apply across the whole project — stopping points,
> who does what, checking docs are current — are written here and pointed to from elsewhere. The
> progress table below is the one and only status board for the whole project; none of the other
> files has its own.
>
> This file used to be one 1,067-line document, split apart on 2026-07-31. Nothing was deleted —
> every part was moved, unchanged, into whichever file now owns it. We did this because 73% of what
> got re-read at the start of every session was old, already-finished backend history that nobody
> needed anymore.

## Progress

| Gate | What                                                                                                                   | Status                                                                                                                                                                             |
| ---- | ---------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0    | Plan, repo, branch, push                                                                                               | ✅ done — commit `4d25463`, pushed to `AmzalFoumi/agentic-erp`, working on `dev`                                                                                                   |
| 1    | Python setup and required packages                                                                                    | ✅ done — `.venv` at `backend/.venv`, 53 packages installed, `mcp==2.0.0` checked and confirmed                                                                                                 |
| 2    | Online database (Postgres) on Supabase                                                                                            | ✅ done — project `khinbdvubrxqqalejcbp` (eu-west-3), connected via the session pooler, `PostgreSQL 17.6` confirmed; database checked and empty as expected                     |
| 3    | Data models, error types, first migration                                                                                | ✅ done — commit `18545e4`; `products` table created with row-level security switched on, confirmed and checked for issues                                |
| 4    | The business-logic layer                                                                                                      | ✅ done — commit `f1da67f`; `services/products.py` (6 functions), 9 tests written against this layer directly (no web requests involved), 3 automated checks enforcing the separation of concerns               |
| 5    | Front door #1: the web API (FastAPI)                                                                                          | ✅ done — merged via PR #3; `22 passed` (9 business-logic + 13 API tests), architecture checks still passing across 29 files                                                                        |
| 6    | Front door #2: the AI agent server (MCP)                                                                                          | ✅ done on `feat/mcp/initial`; `31 passed` (9 business-logic + 13 API + 9 agent-server tests), architecture checks still passing across 37 files, tested live end-to-end |
| 7    | Docs reorganised — added `docs/FRONTEND-PLAN.md`, updated two earlier decisions                         | ✅ done — merged to `dev`; docs only, no code changed                                                                                                                                      |
| 8    | Tidying up the web API — reorder alerts, consistent response shape, clearer validation errors, configurable security settings | ✅ done on `feat/fastapi/contract`; all tests passing and architecture checks holding, both confirmed by the developer                                                              |
| 8.5  | Docs split — `PLAN.md` trimmed down to an index plus shared rules; gates 0–8 moved to `BACKEND-PLAN.md`, login/security info moved to `AUTH-PLAN.md`, frontend file renamed | ✅ done — docs only, no code changed; every piece moved as-is, nothing removed                                                                                                            |
| 9    | Set up the Next.js website (with TypeScript, Tailwind, and shadcn/ui) in `frontend/`                                                 | ✅ done on `feat/client/web`; next `16.2.12`, react `19.2.4`, tailwindcss `4.3.3` — rebuilt once after an earlier attempt used a stale cached version                                                                                                                                     |
| 10   | Auto-generated web-request code from the API's own description, a check that catches the two getting out of sync, a list of what the API can and can't do yet, and the seam where login will plug in                           | ✅ done on `feat/client/web`; generated file committed, a drift-check script, two rule checks, and a placeholder "current user" function. One earlier finding ("the error format isn't documented") was **wrong and was retracted** — see below |
| 11   | Design basics — `frontend/DESIGN.md` + `globals.css`, a "density" setting (compact vs. spacious), Sri Lankan Rupee number formatting  | ✅ done on `feat/client/web`; first pass done, then real values (fonts, colors, spacing) finalised later — Figtree/IBM Plex Mono fonts, a purple-blue accent color, sharp corners, four stock-status colors |
| 12   | Reconciling the AI-generated design with reality — brief, screens. Sub-gates **12a–12e** are detailed in `FRONTEND-PLAN.md`              | ✅ done — the design values were finalised, pushed into the design tool, and six screens plus an AI-agent side panel were generated and reviewed. 12e was skipped: 12d's screens were already what gate 13 built from. Sub-gate detail in `FRONTEND-PLAN.md` |
| 13   | Handoff — build the real website from the generated screens, pull out reusable pieces, connect it to the API. Sub-gates **13a–13h** are detailed in `FRONTEND-PLAN.md` | ✅ done — merged to `main` and `dev` at `af3234b`. All six screens built, connected to the API, then reviewed for gaps against the design (13g) and cleaned up (13h). The website (gates 9–13) is done for now; the agent panel still has six states left to build once the AI agent exists — that's gate 21. Sub-gate detail in `FRONTEND-PLAN.md` |
| 14   | AI agent planning — wrote `docs/AGENT-PLAN.md`, decided how the agent will run, which AI model it uses, and how it remembers conversations       | ✅ done — docs only, no code. Chose **Pydantic AI** as the framework (the alternatives had blocking technical problems). Chose **Gemini Flash** as the AI model (it's free; the more capable Gemini Pro is not). Chose to connect to the agent-server over the network, but **only from the same computer** for now, with a clear rule for when that has to change (see below). Chose to store conversation history in its own separate part of the database. Left some open questions to resolve in gate 16 |
| 15   | The teaching loop — a bare-bones version of the agent with no framework, built just to learn from. **It was run, we kept what we learned, then deleted the code** | ✅ closed 2026-08-06 — built in four parts (first committed as `38ac202`), then **deleted on the developer's decision**, since it wasn't worth maintaining. What we kept: the agent's project setup, one diagnostic script that tests the agent's tools with no AI model involved, and **six lessons that changed later gates** — the biggest being that a single AI response can ask for several actions at once, which our approval design hadn't accounted for. All six are written up in `AGENT-PLAN.md`. Some questions raised here were deferred to gate 16 — an accepted cost of deleting the code |
| 16   | Connecting the AI agent framework to the running agent-server                        | ✅ done 2026-08-11 — **the AI agent answered a real question about real data for the first time.** Asked four questions, it picked tools by itself and got all four right with no invented numbers, including correctly saying we don't stock goat cheese rather than offering a substitute. **One honest limit:** it used the same "list everything" tool every time, so we know it prefers looking things up over guessing, but not that it picks correctly between all six tools; the three tools that *change* data are untested until gate 19. The ready-made way of connecting to the agent-server was dropped over a version conflict and hand-written instead. All four of the gate's open questions are now closed. Detail in `AGENT-PLAN.md` |
| 17   | Writing the agent's own conversation-handling code, with clear boundaries enforced automatically | ✅ done 2026-08-12 — `conversation.py` built with our own `Message`/`TurnResult` types and one public `run_turn()` function; the developer's own automated check confirms only three files in the whole agent talk to the AI framework directly, everything else uses our own plain types |
| 18   | Saving conversations to the database, with the same row-level security used elsewhere, and confirming this doesn't interfere with the backend's own database setup | ✅ done 2026-08-12 — conversations and messages now persist to their own isolated area of the same database, with the same lock-it-down-by-default security switched on; proved this can't accidentally interfere with the existing website/API's own database area by triggering the exact mistake once (caught before it touched anything) and then fixing it so it structurally can't happen again |
| 19   | Requiring human approval before the AI agent can run any of its three actions that change data, enforced at the API level before any UI exists for it                          | ✅ done 2026-08-12 — the agent now stops and asks before it changes anything, and carries on correctly whether the answer is yes or no. Built to **fail safe**: we listed the three actions that are safe to run freely rather than the three that need permission, so any *new* action added later needs permission automatically instead of slipping through. Also the agent's first automated test suite — nine tests, no internet and no real AI model needed, checking whether the action *actually ran* rather than whether the reply looked right. Two limits: a pending question is held in memory only (fixed at gate 20) and there's no screen for it yet (gate 21). Detail in `AGENT-PLAN.md` |
| 20   | Giving the AI agent its own web address, with live streaming responses, plus wiring it into the website           | ✅ done 2026-08-12 — the agent now has its own address a browser can talk to, and answers arrive word by word as they're generated. Gate 19's pending approval is now **written down**, so closing the tab or restarting no longer loses it — the one gap that gate stopped at. Built on the AI library's implementation of a published streaming standard, which matters because approval is part of that standard: the yes-or-no travels the same channel as everything else. Every request now records **who** is asking (always "the system" until gate 24), because gate 19 created a privileged action with no notion of who granted it. **The one real constraint:** the agent is reachable only from this machine, with a test that fails if that changes — so it cannot go online before the login gates. See "Login and security" below. Detail in `AGENT-PLAN.md` |
| 21   | The website's AI-agent panel — building the six remaining screens/states described in `FRONTEND-PLAN.md`, wired to the real agent service from gate 20                   | ✅ done — code complete and reviewed 2026-08-13; the manual browser walkthrough this gate was held open for is finished and both commits (`002d0fc`, `e41cf24`) are merged to `main` via PR #23, confirmed 2026-08-18. The panel now actually talks to the agent: idle prompts, a "thinking" indicator, a streamed reply, the approval card with Confirm/Cancel, and a success card. Reloading the page resumes the conversation you were in, pending approval included. Two review rounds caught six real problems before they shipped, three of them only visible once everything was wired together. Two things deliberately not built: the design's exact `12 → 20 (+8)` figure needs a *before* quantity the tool call doesn't carry, and no automated tests — the website has none yet. Full close-out in `AGENT-PLAN.md` |
| 22   | **Logins and security — the written plan.** Rewrote `docs/AUTH-PLAN.md` against the login providers' current documentation, and split what used to be a single "logins" gate into four | ✅ done 2026-08-14 — **docs only, no code changed** (5 files: this one, `AUTH-PLAN.md` rewritten in place, plus one-line pointers in `CLAUDE.md`, `AGENT-PLAN.md`, `BACKEND-PLAN.md`). The old plan had gone stale: the "newer alternative mechanism" we thought we'd have to choose between turned out to be **a single setting on the same request**, not a rival design, and the code for it already ships in a library we use — so keeping that door open costs nearly nothing and needs nothing built now. This gate exists so the plan survives a lost session and the gates below are written down *before* work starts against them |
| 23   | **Proving it works before building on it** — a short, throwaway experiment run outside this repository | ✅ done 2026-08-18 — **the experiment passed**, so **the login server is now chosen rather than provisional** and the named backup is no longer needed. No application code merged; the test script lived in a scratch folder and was deleted. The result gate 25 depends on: **an agent cannot give itself more power than it was handed** — a test agent *allowed* to change stock, handed a read-only pass, asked for stock-change too and got read-only back. Passes for the wrong service and with tampered signatures were both refused. The finding most likely to cause a bug later: **asking for too much doesn't error, it quietly gives you less** — so our code must always check what it actually received. Two things that create work: the library ships no ready-made pass-checking code (gate 25 writes ~55 lines), and a **startup recipe** now exists at `deploy/docker-compose.thunderid.yml`, pinned to an exact version because the official one says "use the latest" — which is how our login server silently upgraded itself between two sessions. It's for local use only. Full findings in `AUTH-PLAN.md` |
| 24   | **People signing in** — real accounts on the website and the web API, replacing the built-in "system" identity that currently has full access | ✅ done 2026-08-23 — **a real person now signs in and the web API knows who they are.** Signing in goes through the login server's own hosted page; the pass it hands back is checked by the API on every request, and an unsigned-in request is now refused instead of quietly getting full access. The permissions inside the pass are spelled *exactly* the way the business-logic code already spells them, which is what gate 23's delimiter choice bought us — no translation table, no mapping to keep in step. **Not one line of business logic changed**, because the identity seam was built in from gate 2; the empty slot just got filled. 15 new tests that need neither the login server nor internet — a throwaway key pair is made up on the spot, which also lets us mint the passes that *must* be rejected (expired, wrong service, tampered) and check they are. Three things recorded as deliberate rather than missed: a cancelled pass stays usable for up to an hour (checking with the login server on every request would make it a single point of failure); refusals never say *why* they were refused, so nobody can use the API to probe our setup; and **staying signed in should now work, but nobody has watched it happen** — the login application was re-registered on 2026-08-23 in a mode that can renew a session, and reading its settings back off the running login server on 2026-08-25 confirms renewal is switched on with a **24-hour** window against a 1-hour pass. So the expected behaviour is that a pass quietly renews itself for a day, not that you are thrown out after an hour. Nobody has yet sat through a full hour to see it, so this is *expected* rather than *observed*. ⚠️ An earlier version of this row said sessions cannot renew and gate 26 must fix it — that was wrong twice over: the setting was already on, and it is not gate 26's problem. ⚠️ **This gate covers people only.** The agent-server still runs as the old "system" identity with full access — that's gate 25, and it's why the agent is still locked to this machine. Verified end-to-end in a real browser on 2026-08-24, which caught three things unit tests could not: **the website's own door was not actually locked** — two bugs in the login vendor's example code meant every page was reachable while signed out, and only the API's refusal kept the data in. Fixed and re-checked. Full write-up in `AUTH-PLAN.md` |
| 25   | **The AI agent acting for a signed-in person**, with no more power than that person has, and the agent-server locked down to match | ✅ done 2026-08-25 — **both halves finished.** The code half landed the same day: the agent-server now demands a pass and refuses without one; the MCP server checks passes itself, against the login server's published keys, and against **its own** service name rather than the web API's; and the AI agent trades the person's pass for a narrower one before touching the ERP. The result the gate exists for, proven by two tests: a stock change made through the agent records **that person's** name on the row, and an agent handed a read-only pass is refused — with the test reading the database afterwards to confirm the number did not move, because a refusal that is only a message is not a refusal. **The inherited defect is closed too**: conversations now record who started them and every route checks that, so changing a number in the URL no longer opens someone else's chat or lets the agent act on their history (answered as "no such conversation", never "not yours", so the ids stay unguessable). The trap this project had carried since gate 6 — the MCP server handing out full access to anyone who connected — is gone, and a test now fails if it comes back. 13 new tests, none of which need the login server running. Two things deliberately left for gate 26: nothing rate-limits an anonymous caller yet, and the login server's certificate is still self-signed. **The machine-only lock stays until then** — it is no longer the only protection, but it is still protection. Earlier status on this row: 🟨 half done — On 2026-08-25 the AI agent got its own real account on the login server (replacing gate 23's throwaway test one), it was given the same four permissions the human has, and the agent-server was registered as a *second* protected service in its own right — separate from the web API, because it is a separate door onto the same building and a pass cut for one must not open the other. Proven with real passes, not assumptions: the agent can take the person's pass and trade it for a narrower one aimed at the agent-server, and gate 23's warning held — **asking for a permission that doesn't exist returns a perfectly valid pass carrying *no* permissions at all, with no error.** Our code must read that as "allowed to do nothing", never as "unspecified, so allow". Eight places where the written plan turned out not to match the real product are recorded in `AUTH-PLAN.md`. What remains is code, and nothing on the login server needs to change for it. The risky one: it's where "the agent can only do what you can do" stops being a design and starts being something actually enforced. **Carries one inherited defect that must close with it:** the agent panel can reopen an old conversation and act on it — it created a product unasked during gate 24's verification. That is the agent *writing to the database* off stale history, so it is a write-safety problem, not a cosmetic one, and it must not reach gate 26 unfixed. It waits for this gate rather than being fixed sooner because the likely cause — conversations not being keyed to a person — is exactly what this gate changes. Detail in `AGENT-PLAN.md` |
| 26   | **Putting it in front of other people** — the website, the web API, the MCP server, the AI agent, **and the login server**, all runnable together | 🟨 in progress — **on `dev`/`main`, not on a feature branch.** `build/aisle-box` was fully merged (PR #35) and is now a stale pointer kept only for history; do not check it out — **the target of this gate changed on 2026-08-26 and that is the thing to read first.** Aisle is being submitted to the Ascentic AI Launch Pad (deadline Saturday 29 August 2026, 5pm), where a hosted link is *optional* and supporting files are allowed. So the deliverable is **not hosting**: it is a **reusable box** — one folder, one command, five services, run on the judge's own machine. Smaller than hosting, and deliberately so, but not a detour: the container recipes it produces are the same ones real hosting needs, and **no service code changed to make the box work.** **Note the count: five things, not four.** The login provider we chose has no hosted option, so we run it ourselves — a real cost of the choice, recorded in `AUTH-PLAN.md`. **The detail for this gate is in `docs/DEPLOY-PLAN.md`**, which now carries sub-gates 26a–26i; **26a–26h are done and the whole demo has been walked in a browser** against a box rebuilt from nothing. Only 26i is open, and it is optional — see below. Done so far: container recipes for all three services; the login server ships a **pre-made configuration** so nobody meets its eight-step import wizard (every password in it stored as a one-way hash, checked before it was committed); all six containers **share one network**, which is what lets a single address be correct for the browser and for server-side code at the same time; and a **dedicated least-privilege database login** for judges, with the SQL that removes it again after judging. **Of the three things gate 25 handed over, the box closes one and only inside the box:** (2) the two “don't check the certificate” switches are **gone from the box** — each container is taught to trust the login server's certificate instead, and certificate checking is left ON everywhere (proven in all three runtimes on 2026-08-26). Real hosting still needs a genuine certificate. (1) nothing rate-limits an anonymous caller and (3) **the agent-server still reads a name off a pass without checking the seal** are **both still open** — the box avoids them by publishing only two ports, both to this machine only, and by never removing the agent's machine-only lock. Both remain hard prerequisites before any of this is reachable from another computer. |

| 27   | **The approval queue** — the agent writes down what it wants to do; a manager reads it and presses a button | ⬜ planned 2026-08-27, not started. The `action_drafts` table, the `/approvals` screen, and the rule that splits it from gate 19's in-conversation approval. **The security shape is the point of this gate:** a draft names a *type* from a closed list, never a function, so a draft row can never become "run this code". Detail in `docs/FEATURES-PLAN.md` |
| 28   | **Spoilage and markdown (F1)** — find food about to go off, work out what to discount, propose it | ⬜ planned 2026-08-27, not started. Adds `inventory_lots`, so stock stops being one number per product and becomes batches with their own expiry dates and costs. `products.quantity_on_hand` survives as a summary the business logic keeps correct, which is why nothing above it has to change. Detail in `docs/FEATURES-PLAN.md` |
| 29   | **Reorder and MOQ bundler (F3)** — group low stock by supplier, top the order up to the supplier's minimum | ⬜ planned 2026-08-27, not started. Adds suppliers and purchase orders. `products.reorder_level` and `needs_reorder` already exist, so half the inputs are built. Detail in `docs/FEATURES-PLAN.md` |
| 30   | **Delivery discrepancy (F2)** — a dock worker types what actually arrived; the system works out the supplier credit | ⬜ planned 2026-08-27, not started. The strongest AI story (turning "DairyCo sent 40 cases instead of 50, 2 broken" into structured numbers) and the most expensive, because it needs everything gate 29 builds plus credit memos and shrinkage. Last on purpose. Detail in `docs/FEATURES-PLAN.md` |

Gates 0–8 are explained in detail in **`docs/BACKEND-PLAN.md`**, gates 9–13 in
**`docs/FRONTEND-PLAN.md`**, gates 14–21 in **`docs/AGENT-PLAN.md`**, gates 22–25 in
**`docs/AUTH-PLAN.md`**, gate 26 in **`docs/DEPLOY-PLAN.md`**, and gates 27–30 in
**`docs/FEATURES-PLAN.md`**.
The numbering deliberately doesn't reset or branch: if there were a separate "F0…Fn" sequence for
the frontend, "which gate are we on" would have two different answers, and this table would stop
working as a single status board. Gate 8.5 is numbered that way for the same reason — renumbering
gates 9–13 to fit it in would break every "Gate 11" reference already written in
`FRONTEND-PLAN.md`, for no real benefit.

---

## Background

The project started from an empty, brand-new code repository. The goal is a supermarket inventory
system where the **business rules are written exactly once** and used by two completely different
things:

- a **web API** (FastAPI), for a Next.js website that store staff will use
- an **AI agent server** (MCP), which exposes those same actions as tools an AI assistant can call

This plan builds that structure and proves the idea works by taking one type of data —
**products** — all the way through every layer, so there's a working example to copy when we add
inventory, suppliers, and purchasing later.

The developer is new to Python, so the plan favours well-documented, beginner-friendly tools
(`venv` + `pip`, SQLAlchemy, Alembic) over faster but less-common ones (`uv`), and every new file
gets a short comment explaining what it's for.

**Early decisions:** use hosted Postgres on **Supabase** from day one · build a skeleton plus one
complete example end-to-end · backend first, website later · work happens in gates with a stop and
review after each one.

> **Updated 2026-07-31 (end of gate 7): "website later" no longer applies.** The backend proved the
> two-front-door idea worked through gate 6, so the website is now the active work — gates 9–13,
> detailed in `docs/FRONTEND-PLAN.md`. Two things are still on hold and are _not_ part of that work:
> **choosing a login/security provider** (see `docs/AUTH-PLAN.md`) and **the AI agent itself**. The
> website's job in gates 9–13 is to leave clean, ready-to-use gaps for both, not to build either one.
>
> **Updated 2026-08-05 (end of gate 13): the website gates are done**, merged at `af3234b`, and
> both of those gaps were left exactly as planned — a placeholder file for login,
> and an agent panel that's visibly "not available yet." **The AI agent is now the active work** — the
> last of the three things we put on hold. Choosing a login provider stays on hold behind it, because
> (as explained in `docs/AUTH-PLAN.md`) figuring out how the AI agent identifies itself is the harder
> problem and needs to be solved first.

## Login and security: ~~on hold, on purpose~~ — **the hold ended on 2026-08-13**

**~~Every user in the system is still treated as one built-in "system" identity with full access.~~**
**Half true as of gate 24 (2026-08-23):** the website and the web API now know who you really are.
The AI agent and its MCP server do not — they still run as the built-in "system" identity, and that
stays true until gate 25. What changed is that it now has a
deadline (see "the trigger has fired" below) and, as of gate 22 (2026-08-14), a chosen provider:
**ThunderID — no longer provisional, since gate 23's experiment passed on 2026-08-18.** Keycloak was
the named fallback if it hadn't; it is no longer needed. The full explanation — why Supabase is used for the database and not for login, why the AI
agent's identity is the harder problem, how one access pass gets swapped for a narrower one, what
running a login server actually costs, and the providers we compared and rejected — is in
**`docs/AUTH-PLAN.md`**. Don't re-research this; just read that file.

Only one part of it needs to live here, because it's a trigger for *stopping* other work rather than
a description of future work:

**Two things will force us to deal with login/security immediately, before any further feature
work.** *(The first of them has since fired — see "the trigger has fired" below. Both are kept here
because they explain why the auth gates exist and when a future change would re-trigger them.)*

1. The AI agent server becomes reachable over the network by anything other than the developer's
   own computer.
2. A second real person starts using the system.

While both of those remain false, treating everyone as one "system" user is acceptable — but only
because there's currently no way for an unauthorized caller to reach it.

**From gate 16 onward, the first condition stops being hypothetical.** The AI agent server gains
the ability to be reached over the network so the AI agent service can talk to it. It will only
accept connections from **the same computer** (`127.0.0.1`), and that restriction is the *entire*
reason it's still safe to run without a login system. Three things would break that safety and must
trigger the login/security work **before any further AI agent work continues**: changing that
network setting so other computers can connect; putting the server behind any kind of tunnel, proxy,
or port-forwarding; or having any process on a different machine successfully call it. This is
written as a specific list, rather than just a general rule, because the risky version of this
mistake is never a considered decision — it's something like "I'll just tunnel it so I can demo it
from my phone," a thirty-second convenience that would expose data-changing actions to the internet
with no login and no record of who did what. Full reasoning is in **`docs/AGENT-PLAN.md`**.

### The trigger has fired (2026-08-13) — logins now come before going online

The developer's stated goal is to **host all five pieces**: the website, the web API, the MCP
server, the agent-server, and — from gate 23 — ThunderID itself. (This said "four" until 2026-08-25;
the MCP server is a separate process on its own port, and Gate 23 added an identity provider that
also has to run somewhere. Gate 26 (now in `DEPLOY-PLAN.md`) has said "five services" throughout, and it was
right.) A hosted agent-server *is* condition 1 above — "reachable over the
network by anything other than the developer's own computer" — so the hold is over. That's why
gates 22–26 now exist in the table, in that order, and why the order can't be flipped. Full
reasoning — including why "system-identity" access makes a half-version unshippable, what the
mechanism is, and what running it costs — is in **`docs/AUTH-PLAN.md`**, which was rewritten from
scratch at gate 22 (2026-08-14) and now reads front-to-back. **Read it before touching gate 23.**

---

## Backend work still owed after the website gates

Kept here, in the file everyone reads every time, because this is work created during one part of
the project that needs to be paid for by another part — the kind of thing that's easy to forget if
it's only written down by whoever noticed it.

### ~~Document the error format properly~~ — **turned out to already be done. Retracted 2026-08-04**

Gate 10 recorded that the API's error responses weren't described anywhere machine-readable, and a
hand-written workaround was added to the website code to compensate. **That finding was simply
wrong** — it was wrong even at the time it was written. The proper, documented error format already
existed, was already being used everywhere it needed to be, was already tested, and was already
present in the generated website code. All of that had been true since gate 8, two gates before
someone reported it as missing.

The lesson is really our own "always check current docs, don't trust memory" rule, turned inward: the
claim was repeated from an earlier, outdated understanding of the backend instead of being checked
against the actual file — the exact mistake that rule exists to prevent, just aimed at our own code
instead of someone else's.

**What was actually left to do, and it was small and website-only:** delete the hand-written
workaround file and use the proper generated version instead. Nothing else depended on the
workaround, so this was a deletion, not a rewrite. No backend changes needed.

**Done in gate 13h (2026-08-05).** The workaround file is gone; every error screen now reads from
the proper generated format. This is closed.

### Stock status: three out of four kinds are supported today

The "reorder level" setting **does exist** — it's a required number on each product, can be set when
creating or editing a product, and the backend already calculates and returns whether a product
needs reordering. An earlier note here wrongly said this was missing and planned work to add it;
that was wrong for the same reason as the item above.

So today: "out of stock" means quantity is zero, "running low" means it needs reordering, and
"OK" means neither of those. **Only "overstocked" has nothing behind it yet** — that would need a
maximum-quantity setting per product, which genuinely doesn't exist yet.

That one is being deliberately left for later: overstocking is a real concern for a supermarket, but
adding a second threshold would mean every single product needs it filled in, and no screen has
shown yet that it's actually worth the effort. We planned to revisit this after gate 13, once real
screens could tell us whether anyone would actually use it.

**Checked again at the end of gate 13 (2026-08-05): still on hold.** All six screens are built and
the gate 13g review of what's built vs. missing didn't flag this as needed — no screen ran into a
need for it while being built. That's weak evidence, not a final answer, so we're leaving it as-is
and will revisit next time work touches product data.

---

## How the work is organised: stop points

Work happens in **gates**, and at the end of every gate the assistant will:

1. **Stop.** No more file changes.
2. **Explain** what was built, in plain language, including any programming concepts introduced
   along the way.
3. **List every file created or changed, and why** each one exists.
4. **Re-check the rest of the plan** against what was actually learned — saying clearly if something
   should change, be dropped, or be reordered, and updating this document if so.
5. **Hand off for the developer to commit the changes to git.** The assistant suggests the command;
   the developer runs it. The assistant never commits on its own.
6. **Wait for the developer to say "continue."** Nothing else happens until then.

## Who does what

**The developer runs every command that touches the toolchain or the code repository.** The
assistant explains each command — what it does, what to expect, and what a failure would look like —
and then waits. Learning by actually typing the commands is the point.

Developer runs these (the assistant only explains them, never runs them):

- **Environment setup:** creating/activating the Python virtual environment
- **Packages:** installing, uninstalling, or listing packages, any dependency change
- **Running things:** starting the web server, starting the agent server, running tests
- **Database migrations:** creating and applying them
- **Git:** `add`, `commit`, `push`, `checkout`, and anything with `gh` (GitHub's command-line tool)

The assistant runs these:

- Writing and editing files
- Read-only checks (git status/history, reading files, searching)
- Read-only Supabase tools (creating the project, listing tables, running queries, checking for
  issues)

If a command fails, the developer pastes the output and the assistant helps figure out why.

### Extended 2026-07-31 (gate 7): the website side of things

The rule above was originally written back when Python was the only toolchain involved — now made
general. From gate 9 onward, the website adds a second toolchain, run from the `frontend/` folder,
**not** `backend/`. Same split, same idea:

| Python side                      | Website equivalent (run from `frontend/`)         |
| --------------------------- | ---------------------------------------------- |
| create/activate virtual environment      | install dependencies (`npm ci`, `npm install`)                        |
| install a package | install a package, or any change to the lockfile       |
| run tests                    | run tests, type-check, run the linter |
| start the server               | start the dev server, build for production                     |
| create a database migration          | regenerate API-connection code    |
| git / GitHub commands              | unchanged — developer runs these                                       |

Three situations the original rule didn't cover, spelled out explicitly since otherwise gate 9 has
no clear owner:

- **Some tools both run a command and generate code.** Scaffolding tools, component generators, and
  the API-code generator all "run a command" and "produce files" at the same time. Rule: **the
  developer runs the generator; the assistant edits the generated files afterward.**
- **Some generated code counts as an official part of the project, but is never hand-edited.** One
  generated file (`schema.d.ts`) is saved into the repository — so if it changes, that shows up as a
  reviewable change — but **neither the developer nor the assistant edits it by hand.** If it looks
  wrong, that means the backend itself is wrong; fix that and regenerate.
- **Checking a screen actually works needs two servers running at once.** From gate 13 onward,
  checking that a page works needs both the web-API server and the website's dev server running.
  The assistant is not allowed to start either one. Rule: **the developer starts both and says
  "continue"; only then can the assistant use browser-automation tools to check the page.** Without
  this rule the assistant would just be guessing whether the UI actually works, which defeats the
  whole point of having those tools.

---

## Standing rule: always check current docs, not memory

At the start of every gate, look up current documentation and released version numbers instead of
relying on the assistant's training data, which can be outdated or simply wrong. Gate 6 is the
proof this matters: the underlying AI-agent standard changed within 24 hours of doing that work, and
five out of nine version numbers written from memory were wrong before anyone checked them against
the real package registry.

---

## Project file structure — as it actually exists (last refreshed 2026-08-26 at the end of gate 25; `deploy/` added at gate 23, the `agent/` folder 2026-08-06, its database and test files at gates 18–19)

⚠️ **This inventory is a snapshot, and a stale one is worse than none** — it is the thing a new
session reads to decide what already exists. Three entries had drifted a full gate behind and were
still describing gate-25 files as unwritten when CodeRabbit caught it on PR #31. Refresh it in the
same commit as the gate that changes the tree, not afterwards.

```text
agentic-erp/
├── .gitignore, README.md
├── .editorconfig, .gitattributes, .prettierrc, .prettierignore
├── CLAUDE.md                      # a short summary for AI assistants, not a rival to the docs below
├── deploy/                        # added at gate 23: docker-compose.thunderid.yml, the login
│                                  # server's own container setup, pinned to an exact version.
│                                  # Adapted from the vendor's quick-start — good enough to run
│                                  # locally, NOT production-ready. The login server itself is
│                                  # NOT copied into this repo — it's treated like the database:
│                                  # something we run, not something we own
│   └── aisle-box/                 # gate 26: the whole system as one runnable box — compose
│                                  # file, the login server's pre-made configuration, the scripts
│                                  # that seed it, and README.md aimed at someone who has never
│                                  # seen this project. A SECOND, separate stack from the one
│                                  # above: different volumes, so their data can never mix, but
│                                  # they collide on ports 3000 and 8090, so only one runs at a
│                                  # time. See deploy/README.md
├── docs/PLAN.md                   # the main source of truth: gates, shared rules, file structure
├── docs/BACKEND-PLAN.md           # gates 0-8 in detail; subordinate to PLAN.md
├── docs/FRONTEND-PLAN.md          # gates 9-13 in detail; subordinate to PLAN.md
├── docs/DEPLOY-PLAN.md            # gate 26 in detail: hosting all five services
├── docs/AUTH-PLAN.md              # gates 22-25 in detail: the login/security decision, the
│                                  # delegation mechanism, the providers; subordinate to PLAN.md
├── docs/AGENT-PLAN.md             # gates 14-21 in detail; subordinate to PLAN.md
├── backend/
│   ├── .env (not saved to git), .env.example, requirements.txt, pyproject.toml
│   ├── alembic.ini, alembic/versions/   # 2 migrations: create products table, add row-level security
│   ├── core/        config.py  database.py  models.py  exceptions.py  actor.py
│   ├── authn/       tokens.py — gate 24: verifies the access tokens ThunderID issues.
│   │                 Its own layer because core/ and services/ may not import `jwt`,
│   │                 and api/ cannot host it — mcp_server/ needs the same code at
│   │                 gate 25 and the two adapters may never import each other
│   ├── services/    products.py  +  inventory.py  suppliers.py  purchasing.py (empty placeholders)
│   ├── api/         main.py  schemas.py  deps.py  errors.py  routes/products.py
│   ├── mcp_server/  server.py  errors.py
│   └── tests/       conftest.py  test_products.py  test_api_products.py  test_mcp_products.py
│                     test_auth.py — gate 24; runs with no ThunderID and no network
├── agent/                          # the AI agent service — started at gate 15a, has its OWN Python environment
│   ├── .env (not saved to git), .env.example, .gitignore, requirements.txt
│   │                               # having its own separate .gitignore is deliberate: two
│   │                               # separate safety nets have to both fail before an API key leaks
│   ├── config.py                   # settings, mirrors backend/core/config.py. Copied,
│   │                               # not shared code — sharing code with backend/ would
│   │                               # break the separation the AI-agent-only rule protects
│   ├── model_provider.py           # gate 16: sets up the AI model based on settings.
│   │                               # Built so adding a second AI provider later is easy
│   ├── mcp_client.py               # gate 16: the code that talks to the agent-server.
│   │                               # Hand-written because the ready-made version couldn't
│   │                               # be used — see AGENT-PLAN.md, gate 16, for why
│   ├── conversation.py             # gate 17: runs one turn. Gate 19 added the approval
│   │                               # pause and resume; still the only file callers import
│   ├── auth.py                     # gate 25 (written 2026-08-25): the one place that swaps the
│   │                               # signed-in person's access pass for a narrower one for the
│   │                               # agent. The only file that names an OAuth grant type
│   ├── store.py  models.py  database.py  alembic/
│   │                               # gate 18: saving conversations to the agent's own
│   │                               # separate area of the database
│   ├── tests/                      # gate 19: the agent's own test suite, the first one.
│   │                               # Runs with no internet and no real AI model — stand-ins
│   │                               # for both — so approve/deny is checked in seconds
│   └── scripts/check_mcp.py        # a diagnostic script: tests the agent-server's tools
│       scripts/ask.py              # directly, with NO AI model involved. Everything else
│       scripts/verify_store.py     # from gate 15 was deleted; this one script was kept.
│                                    # ask.py is the demo script; verify_store.py proves
│                                    # gate 18's saving works across two separate runs
└── frontend/                       # the website (Next.js 16) — set up at gate 9, built out in gates 9-13
    ├── .env.example, package.json, next.config.ts, eslint.config.mjs, components.json
    ├── DESIGN.md                   # the design rules (colors, fonts, spacing); other reference docs alongside
    ├── .design-sync/               # settings for pushing design values to the design tool
    └── src/
        ├── app/         layout.tsx  globals.css  products/{list,[id],[id]/edit,[id]/adjust-stock,new}
        │                            # each page has its own code, actions, and small helper components
        ├── components/  ui/        # basic UI building blocks, auto-generated
        │                domain/    # reusable pieces specific to this project (stock badge, money display,
        │                           # form fields, error display) — pulled out of the built screens
        │                shell/     # navigation, density toggle, theme toggle, the agent panel
        └── lib/         api/client.ts  api/schema.d.ts (auto-generated, never hand-edited)
                         api-error.ts  format.ts  auth/current-user.ts (reads the real session)
```

Four files exist that weren't part of the original plan, each added for a reason explained in
`docs/BACKEND-PLAN.md`: `core/actor.py` (so "who is doing this action" is passed in explicitly,
rather than the business logic needing to know anything about web requests); `api/deps.py` (the
place where a real login system will eventually plug in); and a matching pair of files,
`api/errors.py` and `mcp_server/errors.py` (one shared list of error types, translated differently
for the web API versus the AI agent server). One config file holds test and code-quality settings
only; the actual list of required packages lives in `requirements.txt` (see the note under gate 1
in `docs/BACKEND-PLAN.md`).

On the website side, three folders carry specific rules, not just code. `components/ui/` is
auto-generated and treated like a third-party library — excluded from code-quality checks. The
`components/domain/` folder was built by pulling reusable pieces *out of* the finished screens,
rather than designing them ahead of time, as explained in gate 13. And `lib/api/` is the *only*
folder allowed to use the generated API-connection code or make network requests directly — this is
the website's equivalent of the backend's strict separation rule, and it's enforced automatically by
a linting rule. `lib/auth/current-user.ts` is the login seam. It was hardcoded to "system" until
gate 25; it now reads the real signed-in session and returns `CurrentUser | null`. It still has no
callers — it is the seam, not live code — see `docs/AUTH-PLAN.md`.

Note: the original sketch expected `services/inventory.py` to be the first fully-built file.
`products.py` ended up being the first one instead, because tracking inventory movements requires
products to already exist; `inventory.py` remains an empty placeholder for stock movements and
adjustment history.
