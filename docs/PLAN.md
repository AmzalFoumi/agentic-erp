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
> | `docs/AUTH-PLAN.md` | Gates 22–26: the login/security decision, the mechanism, the login providers we checked | The login/security gates |
> | `docs/AGENT-PLAN.md` | Gates 14–21, how the AI agent works | Changing the AI agent's code |
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
| 12   | Reconciling the AI-generated design with reality — brief, screens. Sub-gates **12a–12e** are detailed in `FRONTEND-PLAN.md`              | ✅ done — **12a** reviewed what was generated, **12b** finalised the actual colors/fonts/spacing, **12c** the design brief was completed — gate 11 closed out and two outdated notes corrected. (The "brief" itself is a working document put together at handoff time, not something we keep permanently.) **12d**: finalised fonts and design values were pushed back into the design tool, and six screens plus an AI-agent side panel were generated and reviewed directly, without manually copy-pasting anything. **12e**: skipped — the screens reviewed in 12d were already what gate 13 was built from |
| 13   | Handoff — build the real website from the generated screens, pull out reusable pieces, connect it to the API. Sub-gates **13a–13h** are detailed in `FRONTEND-PLAN.md` | ✅ done — merged to `main` and `dev` at `af3234b`. The developer decided to build everything first and review what was and wasn't supported afterward, at step 13g. **13a–13f**: built the page layout, the product list, product detail, create/edit forms, the stock-adjustment form, and the AI-agent panel (shown in its one available "not ready yet" state) — each reviewed and committed by the developer. **13g**: wrote up what the website can and can't do yet, and where it differs from the design — nothing was removed without discussion. **13h**: cleanup — removed a leftover test page and an unused error-handling file, fixed lint warnings, excluded auto-generated folders from linting, and switched to a light/dark theme toggle. The website (gates 9–13) is done for now; the agent panel still has five states left to build once the AI agent itself exists |
| 14   | AI agent planning — wrote `docs/AGENT-PLAN.md`, decided how the agent will run, which AI model it uses, and how it remembers conversations       | ✅ done — docs only, no code. Chose **Pydantic AI** as the framework (the alternatives had blocking technical problems). Chose **Gemini Flash** as the AI model (it's free; the more capable Gemini Pro is not). Chose to connect to the agent-server over the network, but **only from the same computer** for now, with a clear rule for when that has to change (see below). Chose to store conversation history in its own separate part of the database. Left some open questions to resolve in gate 16 |
| 15   | The teaching loop — a bare-bones version of the agent with no framework, built just to learn from. **It was run, we kept what we learned, then deleted the code** | ✅ closed 2026-08-06 — built in four parts (first part committed as `38ac202`), then **the whole thing was deleted on the developer's decision, since it wasn't worth maintaining long-term**. What we kept: the agent's basic project setup (its own environment, settings, dependency list), one useful diagnostic script that tests the agent's tools without any AI model involved, and **six lessons learned** that changed our plans for later gates — written up in `AGENT-PLAN.md`. In short: figured out how to correctly save the AI's internal reasoning between turns, how to handle optional settings the AI model needs reformatted, how to match up simultaneous tool calls with their results, how a single AI response can ask for several actions at once (which our design for approval prompts hadn't accounted for), and that the AI library we use has two different ways of doing the same thing, with the official docs describing the wrong one for our needs. Also decided that async/await code arrives one gate later than planned, and reframed a design principle as "keep the *thinking* simple, not necessarily the code." Some questions raised here were deferred to gate 16 — an accepted cost of deleting the code |
| 16   | Connecting the AI agent framework to the running agent-server                        | ✅ done 2026-08-11 — **the AI agent answered a real question about real data for the first time.** Asked "what's low on stock?", it chose the right tool by itself, read the database, and listed all nine understocked products with correct figures — no invented numbers. Three more questions were tried (a price, a product code, and a product we don't stock); it got all three right, including correctly saying we don't sell goat cheese rather than offering something similar. **One honest limit:** it used the same "list everything" tool for all four questions, so we know it prefers looking things up over guessing, but not yet that it picks correctly between all six tools. The three tools that *change* data haven't been tried at all — that's gate 19. To make the test real we also added 20 products across seven categories, since with one product in the catalogue any question had the same answer. **The originally planned approach was dropped** on 2026-08-06 because of a dependency version conflict that made it impossible to use with our agent-server. We wrote our own replacement instead, with a note to revisit once the underlying library fixes the issue. Built so far: the code that sets up the AI model, and the code that talks to the agent-server. On 2026-08-11 we added the agent-server's network mode (it can now be reached at a web address instead of only being launched as a child program), simplified the tool-testing script from thirty lines of locating the backend's files down to one web address, and wrote the small demo script this gate is judged by — one question in, a real database answer out. Two of the four open questions are now closed: free usage limits (2026-08-06) and which part of the Gemini library our framework uses (2026-08-11 — the stateless one, which is what our plan for saving conversations assumed). The exact model names were also read off Google's console on 2026-08-11 and put into the settings file — you can now write a short nickname (`gemma-31b`, `gemma-26b`, `flash-lite`) instead of the long official name, and leaving the setting blank picks the sensible default. We checked first that the Gemma models can actually use tools at all, since that's the only thing we need a model for; they can. All four of the gate's open questions are now closed |
| 17   | Writing the agent's own conversation-handling code, with clear boundaries enforced automatically | ✅ done 2026-08-12 — `conversation.py` built with our own `Message`/`TurnResult` types and one public `run_turn()` function; the developer's own automated check confirms only three files in the whole agent talk to the AI framework directly, everything else uses our own plain types |
| 18   | Saving conversations to the database, with the same row-level security used elsewhere, and confirming this doesn't interfere with the backend's own database setup | ✅ done 2026-08-12 — conversations and messages now persist to their own isolated area of the same database, with the same lock-it-down-by-default security switched on; proved this can't accidentally interfere with the existing website/API's own database area by triggering the exact mistake once (caught before it touched anything) and then fixing it so it structurally can't happen again |
| 19   | Requiring human approval before the AI agent can run any of its three actions that change data, enforced at the API level before any UI exists for it                          | ✅ done 2026-08-12 — the agent now stops and asks before it changes anything, and correctly carries on whether the answer is yes or no. Built to **fail safe**: rather than listing the three actions that need permission, we listed the three that are safe to run freely, so any *new* action someone adds later needs permission automatically instead of slipping through unnoticed. This is also the first gate with an automated test suite for the AI agent itself — nine tests that run without the internet or the real AI model, using stand-ins for both, so the yes-and-no behaviour can be checked in seconds and a refusal can be tested at all (you can't ask a real AI model to be refused). The tests check whether the action *actually ran*, not whether the reply looked right — a version that said "done" without doing anything would pass a sloppier test. Two honest limits recorded: a pending question is held in memory only, so it's lost if the program restarts — deliberately left until gate 20, when there's a real server for that to matter on — and there's still no screen for any of this; that's gate 21. Also corrected a wrong detail in this gate's own plan: it named a feature of the AI library that isn't reachable the way we've built ours, though the same mechanism is available one level down |
| 20   | Giving the AI agent its own web address, with live streaming responses, plus wiring it into the website           | ✅ done 2026-08-12 — the agent now has its own address a browser can talk to, and answers arrive word by word as they're generated rather than all at once at the end. Gate 19's "ask before changing anything" survives the trip: the approval question now gets **written down**, so if you close the tab or the program restarts, the thing waiting for your yes-or-no is still there when you come back — that was the one honest gap left open at gate 19, and it's the reason that gate deliberately stopped where it did. Built on the AI library's own implementation of a published streaming standard rather than inventing our own message format; that turned out to matter more than expected, because approval is built into the standard, so the yes-or-no travels the same channel as everything else instead of needing a second one. Two other things worth knowing. First, we now record **who** is asking on every request — always "the system" for now, since there are no logins yet — because gate 19 created something privileged (permission to change data) with no notion of who granted it, and adding that in afterwards is exactly the kind of retrofit that goes wrong. It's written to work with any future login provider; none is chosen. Second, and this is a real constraint rather than a detail: the agent is deliberately reachable **only from this machine**, spelled out in the code with the reason, and there's now a test that fails if someone changes it. That means the agent cannot be deployed to the internet until the login gate is done — a deployed website has no way to reach a program running only on your laptop. That ordering was chosen on purpose: this gate locally, then logins, then deploy. Also corrected a wrong detail in the earlier plan: it said the website's architecture rules needed one exception for this; they needed two |
| 21   | The website's AI-agent panel — building the six remaining screens/states described in `FRONTEND-PLAN.md`, wired to the real agent service from gate 20                   | 🟡 code complete and reviewed 2026-08-13, **manual browser verification still pending** — the panel now actually talks to the AI agent: idle prompts, a "thinking" indicator, a streamed reply, the approval card with Confirm/Cancel, a success card, and a settled reply (a plain decline renders the same as any other finished answer — there's no separate "refusal" signal on the wire to tell them apart, so a distinct look for that one wasn't built). Uses the AI library's own React hook for approvals rather than hand-rolling anything — the Confirm/Cancel buttons call a function the library provides. Reloading the page now resumes the conversation you were in (including a still-pending approval) instead of silently starting a new one, using the same saved-approval mechanism gate 20 already put in the database. Two review rounds caught six real problems before they shipped, three of them only visible once everything was wired together rather than in any one piece on its own — see `AGENT-PLAN.md`'s Gate 21 close-out for the full list; the two that would have been most visible to a user were the "thinking" indicator never actually appearing, and a plain lookup question wrongly showing the "change applied, updated_by: system" success card. One thing intentionally not built: the exact `12 → 20 (+8)` change amount shown in the original design needs the product's *before* quantity, which isn't in the tool call itself; no automated tests were added either, since this project has none yet for the website. The approval card's raw product id is no longer shown as a bare number, though — a follow-up added 2026-08-13 resolves it to a "SKU — Name" label (a Server Action calling the same product-detail endpoint the products pages already use, with a skeleton loading state) so the reviewer can see what's actually being approved. **Still to do:** a hand-driven browser walkthrough with both the backend and the agent service running — only the developer can do this last part, and note the two most recent commits (`002d0fc`, `e41cf24`) are still unmerged to `main` as of this writing. (`npm install ai@7.0.64 @ai-sdk/react@4.0.67`, `npx tsc --noEmit`, and `npm run lint` all done 2026-08-13, all clean throughout, including after the SKU-lookup addition) |
| 22   | **Logins and security — the written plan.** Rewrote `docs/AUTH-PLAN.md` against the login providers' current documentation, and split what used to be a single "logins" gate into four | ✅ done 2026-08-14 — **docs only, no code changed** (5 files: this one, `AUTH-PLAN.md` rewritten in place, plus one-line pointers in `CLAUDE.md`, `AGENT-PLAN.md`, `BACKEND-PLAN.md`). The old plan was written against facts that had since moved: the login server we're considering went from an early preview to a release candidate, and the "newer alternative mechanism" we thought we'd eventually have to choose between turned out to be **a single setting on the same request**, not a rival design — which makes keeping the door open for it nearly free. Also found that the code needed for that alternative already ships inside a library we already use, so there's nothing to build for it now. This gate exists so the plan survives a lost session and so the gates below are written down *before* work starts against them, rather than being filled in afterwards |
| 23   | **Proving it works before building on it** — a short, throwaway experiment run outside this repository | ⬜ not started — nothing gets merged. Installs the login server, registers this system with it, and proves that one *narrowed-down* access pass is actually accepted by the real code that will be checking it. That last part is the only bit no documentation can answer for us, which is the whole reason this is a separate gate. **If it fails, we change login providers rather than push on.** This is also where the provider stops being provisional and gets written down as chosen |
| 24   | **People signing in** — real accounts on the website and the web API, replacing the built-in "system" identity that currently has full access | ⬜ not started — blocked by gate 23 |
| 25   | **The AI agent acting for a signed-in person**, with no more power than that person has, and the agent-server locked down to match | ⬜ not started — blocked by gate 24. The risky one: it's where "the agent can only do what you can do" stops being a design and starts being something actually enforced |
| 26   | **Putting it online** — the website, the web API, the agent-server, and the AI agent, all hosted                          | ⬜ not started — blocked by gate 25, and this is a hard block, not a preference. See the note below |

Gates 0–8 are explained in detail in **`docs/BACKEND-PLAN.md`**, gates 9–13 in
**`docs/FRONTEND-PLAN.md`**, gates 14–21 in **`docs/AGENT-PLAN.md`**, and gates 22–26 in
**`docs/AUTH-PLAN.md`**.
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

**Every user in the system is still treated as one built-in "system" identity with full access.**
That remains true of the code and stays true until gate 24. What changed is that it now has a
deadline (see "the trigger has fired" below) and, as of gate 22 (2026-08-14), a chosen provider:
**ThunderID, subject to gate 23's experiment passing.** Keycloak is the named fallback if it
doesn't. The full explanation — why Supabase is used for the database and not for login, why the AI
agent's identity is the harder problem, how one access pass gets swapped for a narrower one, what
running a login server actually costs, and the providers we compared and rejected — is in
**`docs/AUTH-PLAN.md`**. Don't re-research this; just read that file.

Only one part of it needs to live here, because it's a trigger for *stopping* other work rather than
a description of future work:

**Two things will force us to deal with login/security immediately, before any further feature
work:**

1. The AI agent server becomes reachable over the network by anything other than the developer's
   own computer.
2. A second real person starts using the system.

Until both of those are still false, treating everyone as one "system" user is acceptable — but only
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

The developer's stated goal is to **host all four pieces**: the website, the web API, the
agent-server, and the AI agent. A hosted agent-server *is* condition 1 above — "reachable over the
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

## Project file structure — as it actually exists (last refreshed 2026-08-12 at the end of gate 19; the `agent/` folder added 2026-08-06, its database and test files added at gates 18–19)

```
agentic-erp/
├── .gitignore, README.md
├── .editorconfig, .gitattributes, .prettierrc, .prettierignore
├── CLAUDE.md                      # a short summary for AI assistants, not a rival to the docs below
├── deploy/                        # gate 23 onward (NOT YET WRITTEN): the login server's own
│                                  # container setup, pinned to an exact version. The login
│                                  # server itself is NOT copied into this repo — it's treated
│                                  # like the database: something we run, not something we own
├── docs/PLAN.md                   # the main source of truth: gates, shared rules, file structure
├── docs/BACKEND-PLAN.md           # gates 0-8 in detail; subordinate to PLAN.md
├── docs/FRONTEND-PLAN.md          # gates 9-13 in detail; subordinate to PLAN.md
├── docs/AUTH-PLAN.md              # gates 22-26 in detail: the login/security decision, the
│                                  # delegation mechanism, the providers; subordinate to PLAN.md
├── docs/AGENT-PLAN.md             # gates 14-21 in detail; subordinate to PLAN.md
├── backend/
│   ├── .env (not saved to git), .env.example, requirements.txt, pyproject.toml
│   ├── alembic.ini, alembic/versions/   # 2 migrations: create products table, add row-level security
│   ├── core/        config.py  database.py  models.py  exceptions.py  actor.py
│   ├── services/    products.py  +  inventory.py  suppliers.py  purchasing.py (empty placeholders)
│   ├── api/         main.py  schemas.py  deps.py  errors.py  routes/products.py
│   ├── mcp_server/  server.py  errors.py
│   └── tests/       conftest.py  test_products.py  test_api_products.py  test_mcp_products.py
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
│   ├── auth.py                     # gate 25 (NOT YET WRITTEN): the one place that swaps the
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
                         api-error.ts  format.ts  auth/current-user.ts (the login placeholder)
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
a linting rule. `lib/auth/current-user.ts` is the placeholder for login, hardcoded to always say
"system" for now — see `docs/AUTH-PLAN.md`.

Note: the original sketch expected `services/inventory.py` to be the first fully-built file.
`products.py` ended up being the first one instead, because tracking inventory movements requires
products to already exist; `inventory.py` remains an empty placeholder for stock movements and
adjustment history.
