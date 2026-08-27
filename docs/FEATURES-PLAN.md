# Standout features — gates 27–30

> Subordinate to `docs/PLAN.md`, like every other detail doc. Where this file and
> `PLAN.md` disagree, `PLAN.md` is right and this one is out of date.
>
> This file owns gates 27–30: the Action Draft engine and the three domain features that
> turn the product catalogue into an agentic ERP. Read it before touching anything in
> `services/drafts.py`, `services/inventory.py`, `services/purchasing.py`, or the
> `/approvals`, `/inventory/spoilage` and `/purchasing` screens.

## Where these features came from, and why the source was not followed literally

The feature set was specified outside this repository by a model with no access to the codebase. It
is a good statement of **what the business needs**. It is not a statement of how this system works,
and eight of its assumptions do not hold here.

⚠️ **The original document is not in git.** It sits at `submission/New Features/Agentic ERP Standout
Features Specification.md` on the developer's machine, and `submission/.gitignore` is a single `*`,
so the whole folder is untracked. That makes the table below the **only durable record** of what was
asked for versus what was built — it is not a courtesy summary of a document you can go and read.
Anyone reconstructing the reasoning later has this and nothing else.

| # | The spec says | Why it does not hold | What we did |
|---|---|---|---|
| 1 | The draft payload stores "target service function names and arguments" | Looking a function up by a name held in a database row means anyone who can write a draft can call anything with anything. That is a remote-code-execution shape, not a design | `draft_type` is a **closed enum**; each value maps to one hand-written handler in a registry. A type with no handler is inert |
| 2 | "Extend inventory to track lot-level data" — reads as additive | `products.quantity_on_hand` is load-bearing: `needs_reorder` is a `hybrid_property` that compiles to SQL, so the products list filters in the database. Lots change where stock lives | Lots become the truth; `quantity_on_hand` is recalculated by `services/` on every lot change and stays a correct summary. Nothing above it changes |
| 3 | Every row records `last_client_type` (`web_ui` vs `mcp_agent`) | `Actor` has exactly `id` and `can()`. It deliberately does not know which adapter built it — that is the abstraction the architecture rests on. Worse, the agent carries a *narrowed copy of the user's own token*, so `actor.id` is the human either way | A `ClientType` enum in `core/`, passed as a keyword argument by each adapter. `Actor` is untouched |
| 4 | `/inventory/spoilage` is "sorted by expiry date" | `GET /products` is fixed to `id DESC` and takes no sort parameter. `FRONTEND-PLAN.md`'s capability inventory names this as a thing designers assume and the API does not have | The lot-listing endpoints take an explicit expiry ordering. Not retrofitted onto `/products` |
| 5 | Spoilage checks run "automatically scheduled"; drafts reach an `EXPIRED` state | Nothing in this project schedules anything. Adding a scheduler for one status field is not worth it | Scans are triggered on demand. `expires_at` is checked **when a draft is read**; expiry is computed, never stored |
| 6 | Financial formulas written as plain arithmetic | Money is `Numeric(10,2)` and `Decimal` end to end. Mixing `Decimal` with `float` in one expression raises in Python, and the API serialises money as a JSON **string** on purpose | Every new money field is `Numeric(10,2)`, every calculation stays in `Decimal`, every response serialises as a string |
| 7 | Purchase orders go `DRAFT → APPROVED → DISPATCHED → FULFILLED` | `services/purchasing.py`'s existing docstring already specifies `draft → sent → partially received → received/cancelled` | The existing one wins. "Partially received" is exactly what a dock discrepancy produces, and gate 30 needs it |
| 8 | The agent stages every write into a draft queue | Gate 19 already built an approval mechanism that works differently — an in-conversation pause with Confirm/Cancel, tested, shipped, and visible in the agent panel | Split by consequence. See decision 1 below |

## The four decisions

Recorded here because this is the doc that owns them. Do not restate them elsewhere; link here.

### 1. Two approval mechanisms, split by consequence (2026-08-27)

Both exist, and the boundary between them is a rule, not a preference:

- **Single-item writes** keep gate 19's in-conversation approval. The agent pauses, the panel shows
  Confirm/Cancel, the turn resumes. "Take 2 off the milk" should not require visiting another screen.
- **Multi-item or financial proposals** become Action Drafts: marking down forty lots, raising a
  purchase order, issuing a supplier credit. These end the conversation and wait for a manager.

Creating a draft is itself safe — a draft changes nothing operationally — so the tool that creates
one runs without in-conversation approval. That is not a loophole; it is the point. The human
approval moved to `/approvals`, where the proposal can be read in full and edited before it runs.

**The agent cannot approve its own drafts.** Its ThunderID role gets `draft.create` and not
`draft.decide`. This is enforced by the permission set, not by convention, and there is a test.

### 2. Build order: spine → F1 → F3 → F2 (2026-08-27)

Cheapest first, and each gate complete before the next starts, so a hard stop leaves finished
features rather than three half-built ones. F1 needs one new table and `products` already carries
`cost_price` and `sell_price`. F3 adds suppliers and purchase orders. F2 reuses all of F3's tables
and adds credit memos and shrinkage on top — which is why it is last despite telling the best story.

### 3. Lots are the source of truth; `quantity_on_hand` is a maintained summary (2026-08-27)

This is what `services/inventory.py`'s placeholder docstring proposed on day one. One private
function recalculates a product's `quantity_on_hand` from its lots, and every operation that touches
a lot calls it. One write path, so the summary cannot drift from the lots.

The consequence worth knowing: **`adjust_stock` keeps its exact signature** — same route, same MCP
tool, same screen, same tests. What changes is internal. A decrease consumes from the **earliest
expiry first**, which is what a shop actually does. That rule lives in `services/`, so the website
and the agent can never disagree about which carton was removed.

Two alternatives were considered and rejected: flagging only some products as lot-tracked (leaves
the system with two kinds of stock that behave differently, permanently), and rebuilding stock as a
full movement ledger (the right destination, but it rewrites the existing stock feature before the
first new one begins). The ledger stays available later — this decision does not block it.

### 4. Provenance columns now; the audit ledger later (2026-08-27)

Every new table carries provenance from birth: who acted, through which door, and which draft it
came from. Those columns are nearly free while writing a table and expensive to retrofit.

The `audit_events` ledger, the `/audit` screen and the natural-language history tool are **not** part
of gates 27–30. They land afterwards or not at all. Nothing above depends on them.

## Gate 27 — the Action Draft engine

**One table, `action_drafts`.** `draft_type` and `status` (`PENDING / APPROVED / REJECTED /
EXECUTED`), a JSONB `payload`, the agent's plain-English `reasoning` for the human to read, the two
money figures below, provenance columns, and `expires_at`.

**Two money figures, not one.** `cost_at_risk` and `projected_recovery`, both `Numeric(10,2)`,
both nullable. A single net figure would hide which half moved, and "we saved 12,000" and "we were
about to lose 40,000 and recovered 12,000" are different sentences to a manager.

**Validated twice.** The payload is checked against its type's schema on the way in, and **again**
on the way out — because a manager can edit it in between. Trusting the stored payload at execution
time would mean the schema only ever guarded the agent, never the browser.

**Endpoints:** list drafts (filterable by status), get one, approve, reject.
**MCP tools:** create a draft, list pending drafts. No approve tool exists at all.

## Gate 28 — spoilage and markdown

**`inventory_lots`:** `product_id`, `lot_code`, `expiry_date`, `quantity`, `cost_price`, provenance.

**The backfill.** Products have stock today and no lots. The migration creates one lot per product
holding the current quantity with **no expiry date** — an "arrived before we tracked this" lot that
spoilage scans skip. Without it the totals contradict each other from the first minute.

**The catalogue is then reseeded.** The developer authorised deleting the current demo data
(2026-08-27) so the reseed can carry real expiry dates — a lot expiring tomorrow is what makes the
feature demonstrable. The "before" copy is `backend/seed/2026-08-27-products-snapshot.sql`.

**Discount tiers live in code, not settings**: 2 days → 25%, 1 day → 50%, today → 70%. They are a
business rule, and `services/` is where business rules live. This also avoids a real trap: a new
setting silently takes its **default** inside the demo box, because the box declares environment in
`docker-compose.yml` rather than reading `.env`. A module constant cannot drift that way.

**The scan reads; proposing writes.** `scan_spoilage()` returns cost at risk versus projected
recovered margin and changes nothing. `propose_markdown()` stages a draft. No price moves until a
human approves at `/approvals`.

## Permissions these gates add

Five for gates 27–28. Each one costs seven edits plus a seed rebuild, so the set is kept deliberately
small — `draft.decide` covers both approving and rejecting, because the security difference between
them is negligible and the maintenance difference is not.

| Permission | Held by | For |
|---|---|---|
| `draft.read` | human, agent | see the queue |
| `draft.create` | human, agent | stage a proposal |
| `draft.decide` | human **only** | approve or reject — see decision 1 |
| `lot.read` | human, agent | expiry and spoilage views |
| `lot.write` | human, agent | receive stock into a lot |

⚠️ Adding any of these means changing **all seven** places listed in `docs/DEPLOY-PLAN.md`, "What a
new feature has to update in the box", and rebuilding the shipped seed (`prune-config.py` →
`build-seed.py` → `scan-seed.py`). A missed permission does not error: ThunderID answers a request
for an unknown permission with a valid token carrying **no scope claim at all**, so the symptom is
the whole application answering 403 to a signed-in user.

⚠️ **The seven places are not filled in identically.** `draft.decide` goes to the human role and
must never reach the agent's. "The agent cannot approve its own work" is a decision made in code and
*enforced in configuration* — a careless copy-paste of the full permission list into the agent's
role would undo it silently, with every test still green.

### One migration per table, RLS inside it

Gates 27 and 28 add one migration each. Row-level security goes **in the create migration**, not in
a follow-up — the pattern set by `20260730_0838` for `products`. Worth knowing because
`alembic revision --autogenerate` will not write that line for you: it compares columns against the
models, and row-level security is not a column. Add the `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`
by hand after generating, and the matching `DISABLE` in `downgrade()`.

## What these gates deliberately do not build

- **No `/audit` screen and no `audit_events` table** — decision 4.
- **No scheduler.** Every scan is triggered by a human or by the agent on request.
- **No delete, anywhere.** Consistent with the rest of the API. Drafts are rejected or expire; they
  are never removed.
- **No frontend tests.** `frontend/` has neither a test suite nor a CI job today, and a two-day
  feature push is not when that gets fixed. The new screens are checked in a real browser instead,
  with the developer running both servers. This is a known gap, recorded so it is not a surprise.

## Open finding, unrelated to these gates

`agent.alembic_version` has **row-level security disabled** (found 2026-08-27 via Supabase's own
advisor). Every other table in both schemas has it enabled. `public.alembic_version` got its own
migration at gate 2; the agent's equivalent never did. It holds one row containing a migration id —
not sensitive — but it is the one table in the project that is reachable with the anon key. Closing
it is one `ALTER TABLE` in a new agent migration. Not done here because it belongs to `agent/`, not
to these gates.
