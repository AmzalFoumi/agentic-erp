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

### How the code is laid out, and why it is split this way

One responsibility per file, so that gates 28–30 add modules rather than growing existing ones.
The split is by *what the code is*, not by which feature asked for it — a markdown calculation and a
reorder calculation are both pricing arithmetic and belong together, even though they arrive two
gates apart.

⚠️ **Amended 2026-08-27, by gate 29.** That last sentence turned out wrong once the reorder
arithmetic was actually written. The rule it was protecting is real — a business number should have
one definition — but there is no discount ladder in "how many packs to order", so there was nothing
for a shared module to protect against duplicating. Gate 29's arithmetic lives in
`services/purchasing/quantities.py` instead, and still imports `services.pricing.to_money` for
rounding, which is the part of the original rule that mattered. See gate 29's section below.

| File | Owns | Deliberately does not |
|---|---|---|
| `core/enums.py` | the vocabularies both adapters and the database must agree on | know anything about drafts specifically |
| `core/models.py` | the table shape | contain any rule beyond "is this expired" |
| `services/guards.py` | `require_permission` — the check every service makes first | know which permissions exist |
| `services/draft_types.py` | the closed registry: type → schema → handler | know what any particular type means |
| `services/drafts.py` | the queue's lifecycle — propose, decide, read | know what a markdown or a purchase order is |
| `services/pricing.py` *(gate 28)* | discount tiers, cost at risk, projected recovery — the money arithmetic | touch the database or check permissions |

`services/guards.py` is an extraction, not a new idea. `_require` was a private four-line helper
copied into `products.py` and then `drafts.py`, with a comment in the first saying a third copy
should be extracted. Gates 28–30 add five more services, so it was pulled out at gate 27 while there
were only two copies to reconcile. One definition means one error message and one place to change it.

**Arithmetic lives in its own module and is imported, never inlined.** The markdown tiers are needed
by the spoilage scan, by the draft handler that applies them, and by the screen that previews them.
Three inline copies is three chances for the shop's discount policy to disagree with itself.

### State of play — gate 27 code complete 2026-08-27

Every layer is built and tested: `core/enums.py`, `ActionDraft` and its migration
(`c3f81d5a24b7`, applied to Supabase), `services/guards.py`, `services/draft_types.py`,
`services/drafts.py`, four HTTP routes, two MCP tools, the agent's `STAGING_ONLY` allowlist, and
the `/approvals` screen. **132 backend tests and 34 agent tests pass**, all four `lint-imports`
contracts hold, `tsc` and `eslint` are clean, and the routes were exercised through a real uvicorn
rather than only the test client.

Two things are **not** done, and neither is code:

1. **The demo box's ThunderID seed.** The developer's own ThunderID is fully configured (see
   below); the box's committed `.db` files are not. That is a separate job needing a throwaway
   Docker stack.
2. **The browser walkthrough.** The queue would be empty anyway — gate 27 registers no draft types,
   so the first meaningful check of `/approvals` belongs to gate 28.

### ThunderID: what was done on 2026-08-27, and what is left

**Done on the developer's own instance** (`deploy/docker-compose.thunderid.yml`), through the
Console, and verified afterwards by querying the Console's own REST API rather than by reading the
screen back:

| # | Change |
|---|---|
| 1 | `Agentic ERP API` resource server gains a `Draft` resource with actions `Read`, `Create`, **`Decide`** |
| 2 | `Agentic ERP MCP` resource server gains a `Draft` resource with `Read` and `Create` — **and deliberately no `Decide`** |
| 3 | New role **`AIsle Agent Access`**: product/stock on both servers, plus `draft.read` and `draft.create`. No `draft.decide` |
| 4 | The `AIsle Agent` agent moved onto that role |
| 5 | The agent **removed** from `AIsle Full Access`, which is now human-only |
| 6 | `AIsle Full Access` gains `draft.read`, `draft.create` and `draft.decide` |

Steps 3–5 were done **before** step 6 on purpose, so there was never a moment when the agent held
`draft.decide`.

**Why the MCP resource server has no `Decide` action at all.** It is not an oversight and should not
be "fixed". Approving happens only over the web API, so a `decide` permission on the MCP audience
would be a permission nothing can legitimately use — and one more thing that could be granted by
mistake. A permission that does not exist cannot be handed out.

**What is left, and it is only the box:**

- Rebuild `deploy/aisle-box/thunderid-seed/*.db` — export from the dev instance, then
  `prune-config.py` → `build-seed.py` → `scan-seed.py`. `aisle-config.yml` is **generated**, so
  editing it by hand achieves nothing; the `.db` files are the artefact a judge actually runs.
- The box's seed must reproduce the **same role split**. Its `AIsle Full Access` is assigned to both
  the judge user and the agent, which is exactly the trap recorded in `docs/DEPLOY-PLAN.md`.
- `frontend/.env.local` on this machine is already updated (it is gitignored, so it is not carried
  by any commit).

⚠️ **Gate 27 registers no draft types.** The engine ships empty and gate 28 registers the first real
one, so the approval queue shows its empty state until spoilage lands. `test_draft_types.py` pins
this, so a type appearing by accident fails a test rather than going unnoticed. It also means the
first meaningful browser check of `/approvals` belongs to gate 28, not this one.

### The three layers keeping the agent out of its own approvals

Written down together because each one lives somewhere different, and someone changing one will not
naturally see the other two:

| Layer | Where | Fails how |
|---|---|---|
| The permission | `services/drafts.py` requires `draft.decide` on approve and reject | loudly — a test asserts the agent is refused *and* that the handler did not run |
| The tool surface | `mcp_server/server.py` publishes no approval tool | loudly — `FORBIDDEN_TOOL_NAMES` in `tests/test_mcp_products.py` |
| The token ceiling | `agent/config.py`'s `thunderid_scopes` omits `draft.decide` | silently — and the ThunderID role behind it fails silently too |

The third is the weak one, which is why it carries the longest comment.

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

### State of play — gate 28 code complete 2026-08-27

Migration `d5b93a17c204` is **applied to Supabase**: `inventory_lots` exists with RLS enabled, and
the backfill created 22 opening lots for the 22 products that had stock. Verified afterwards by
query, not assumed — no product's `quantity_on_hand` disagrees with the sum of its lots.

| Layer | What landed |
|---|---|
| `core/models.py` | `InventoryLot` — product, lot code, expiry date, quantity, frozen cost price, provenance |
| `services/pricing.py` | The discount ladder and the two money figures. **Pure functions** — no session, no actor, no clock |
| `services/lots.py` | `receive_lot`, `consume` (soonest-expiry-first), `list_lots`, `expiring_lots`, and `recalculate_on_hand` |
| `services/spoilage.py` | `scan_spoilage` (reads), `propose_markdown` (stages), `_apply_markdown` (runs on approval only). Registers `BATCH_PRICE_MARKDOWN` |
| `api/routes/inventory.py` | `GET /inventory/spoilage`, `POST /inventory/spoilage/propose`, and lot list/receive |
| `mcp_server/server.py` | `check_spoilage_risk`, `propose_spoilage_markdown`, `list_product_lots` — **no tool applies a markdown** |
| `frontend/src/app/inventory/spoilage/` | The screen, its server action, and a "Expiring soon" nav entry above Approvals |

**One real bug was found and fixed while building this**, and it is worth knowing because the same
mistake is available again in gates 29–30. `create_product` still assigned `quantity_on_hand`
directly, so a new product claimed stock that no lot backed; the next adjustment recalculated from
lots and appeared to *lose* the opening stock. Opening stock now becomes an undated `OPENING` lot,
exactly like the migration's backfill. Caught by an existing test, not a new one.

`test_lots.py` now carries a **source-level guard**: it greps `services/` and fails if
`quantity_on_hand` is assigned anywhere except `lots.py`. No runtime test can catch a second write
path, because the bug is another correct-looking assignment somewhere else.

**A second real bug surfaced when the seeded data was scanned**, and it is the kind that would
never have shown up in a unit test written from the design. The report has one row per **lot**, but
`sell_price` lives on the **product** — a shelf has one price label. Sourdough had two lots, one
expiring today (70% off) and one tomorrow (50% off), so the payload carried two lines for the same
product and the handler applied them in order. The report is ordered soonest-expiry-first, so the
**last** line won — the least urgent one. The bread expiring today would have been marked down 50%
instead of 70%, silently.

`_lines_for()` now collapses to one line per product at the **deepest** discount, which is also the
correct answer rather than an arbitrary tie-break: stock sells soonest-expiry-first, so the next
carton off the shelf is the one from the most urgent lot. The report still shows both lots, because
a manager wants the whole picture. Pinned by
`test_two_lots_of_one_product_are_priced_at_the_deepest_discount`.

**The catalogue now has dated lots.** `backend/seed/2026-08-27-dated-lots.sql` carves 14 dated
batches out of the products' `OPENING` lots — **splitting rather than deleting**, so product ids
survive and every total is unchanged. Dates are `CURRENT_DATE + n`, never literal, so the data does
not go stale before the demo. Idempotent. A real scan returns 12 items across all three discount
rungs, with the day-9 and day-14 batches correctly excluded.

**What is left, and none of it is business logic:**

1. ⚠️ **`lot.read` and `lot.write` do not exist on the login server.** Until they are created, a
   real token cannot carry them, and every spoilage screen and tool answers 403 for a signed-in
   user. Tests pass regardless — they build actors directly. This is the silent-failure mode the
   whole permissions table below warns about.
2. `frontend/src/lib/api/schema.d.ts` needs regenerating (`npm run api:types` against a running
   uvicorn). It is build output, committed but never hand-edited.
3. The browser walkthrough — now finally meaningful, because `/approvals` has something to show.
4. The demo box seed, still deferred until all features stop changing. See `deploy/SEED-REBUILD.md`.

**`lot.write` is deliberately NOT given to the agent.** Receiving a delivery is a physical event a
person witnesses. An agent that could invent stock could invent a spoilage problem and then propose
the solution to it. `agent/config.py` requests `lot.read` only.

### Known and deliberately deferred: concurrent decisions are not serialised

Found by review on 2026-08-27, judged real, and **left in place on purpose** — recorded here so it
is a decision rather than an oversight.

Two transactions can both pass a check before either commits:

| Where | What could happen |
|---|---|
| `drafts.approve_draft` | Both pass `_require_actionable()`, so one draft's handler runs twice |
| `lots.consume` | Both read the same lots and consume the last unit |
| `lots.receive_lot` / `adjust_stock` | Both recalculate and write a partial sum, or create two correction lots |

The fix is a `SELECT … FOR UPDATE` on the product (and on the draft) held until commit.

**Why it is not being done now.** It needs two people acting on the same product within the same
moment; this system has one user and a demo on 2026-08-29. The change touches every write path in
`lots.py` and `products.py`, which is the largest possible blast radius for the smallest observable
gain before a deadline — and a lock taken in the wrong order is a deadlock, which is a worse failure
than the one being fixed.

⚠️ **This stops being acceptable the moment a second human user exists** — the same condition that
expired the auth deferral in `PLAN.md`. Do it before then, not after.

## Gate 29 — reorder and the MOQ bundler

**`suppliers` and `supplier_products`.** Who the shop buys from, and which supplier stocks which
product at what price, in what pack size, with which one preferred. `supplier_products` is
SQLAlchemy's **association-object** pattern — a mapped class on the link table, with relationships
from both sides to it — because the price and pack size are the reason the row exists, not
incidental columns on a bare many-to-many. The `secondary=` shortcut is deliberately not defined
alongside it: the 2.0 docs warn that combining the two writes `NULL` into the extra columns unless
the shortcut carries `viewonly=True`, and not defining it at all avoids the trap outright.

**`purchase_orders` and `purchase_order_lines`.** An order against one supplier, in `draft` /
`sent` / `partially_received` / `received` / `cancelled` — the last two states declared now and
reachable only from gate 30, because a state machine with holes in it is harder to read than one
whose later states are written down and unused. `quantity_received` and `quantity_damaged` on the
line are gate 30 fields, created now because a second migration later would have to be applied by
hand to Supabase **and** carried into the demo box by hand — the same reasoning as decision 4.

### The bundler, in four steps

`services/purchasing/reorder.py::scan_reorder` is a **read**. It changes nothing and stages nothing.

1. For each product `Product.needs_reorder` flags, choose one supplier: preferred first, then
   cheapest, then lowest supplier id. The third tiebreak looks pointless and is not — without a
   total order, two suppliers at the same price could swap places between two reads of the same
   data, and the approval screen would contradict itself between refreshes, with real money on it.
2. Order up to twice the reorder level (`REORDER_TARGET_MULTIPLIER = 2`), rounded **up** to whole
   packs — rounding down can produce an order that still leaves the product below its reorder
   level, which is an order that did not solve the problem it was raised for.
3. Group the chosen lines by supplier and price the group.
4. If a group is under that supplier's `minimum_order_value`, add packs of that supplier's other
   products — the ones closest to going low, not the cheapest — one pack at a time until it clears.
   If it still cannot clear, the bundle is returned flagged (`below_minimum: true`, with the
   shortfall), never proposed as if it were fine. Approving an under-minimum order and then seeing a
   delivery charge is the software misleading the manager.

**The `reorder_level = 0` hole.** `reorder_level` defaults to 0, and `needs_reorder` is
`quantity_on_hand <= reorder_level` — so a product with no stock and no configured level *is*
flagged low, and the naive target (`0 × 2 = 0`) would order none of it. The bundler would then
report a product as needing reordering and propose buying zero, which looks like the feature not
working at all. The rule: when nothing is on the shelf, order one pack regardless of what
`reorder_level` says. Pinned by name in `test_purchasing_quantities.py`, alongside the companion
test that stops the rule becoming "always order one pack" — it only fires when the shelf is
genuinely empty.

**`propose_reorder` stages, never places.** It scans, picks one supplier's bundle, and writes one
`ActionDraft` row carrying `SUPPLIER_REORDER`. Approving it creates a purchase order in `draft`
status — **not `sent`** — because a person still has to press send, which is the last point at
which anyone can look at the whole order before it counts as placed with a supplier.
`expected_date` in the payload is indicative only; `send_order` recomputes it as
`today + supplier.lead_time_days` at the moment the order is actually placed, because the lead time
counts from then — a draft approved on Friday and sent on Monday must not claim Friday's arrival
date.

**The caveat, recorded rather than hidden.** The bundler reads `quantity_on_hand` and does not look
at expiry. A product can appear on a reorder bundle *and* on the spoilage report at the same time —
technically consistent (low stock and about-to-expire stock are independent facts), but it can read
oddly on screen next to each other. Not solved here.

### The `DraftHandler` contract change

Writing this gate surfaced a defect in gate 27's draft contract: a handler never received the draft
it came from, so it had no way to record `PurchaseOrder.source_draft_id`. The id **cannot** travel
in the payload — the payload is editable by the approving manager, so an id inside it is a number a
browser can set, and provenance you can forge is not provenance. `DraftHandler` gained a fifth
argument, `ActionDraft`, threaded through `drafts.py`'s call site and every handler, including gate
28's `_apply_markdown`, which takes it and ignores it — a markdown changes prices on `products`,
which has no `source_draft_id` column to write to.

### State of play — gate 29 code complete 2026-08-27

Migration `276428c7f1dd` (`create_purchasing_tables`) is **applied to Supabase**: all four tables
exist with RLS enabled, verified by query afterwards rather than assumed.

| Layer | What landed |
|---|---|
| `core/enums.py` | `PurchaseOrderStatus` |
| `core/models.py` | `Supplier`, `SupplierProduct`, `PurchaseOrder`, `PurchaseOrderLine` |
| `services/purchasing/` | The first **package** under `services/`, not a flat module — `quantities.py`, `_repository.py`, `suppliers.py`, `catalog.py`, `reorder.py`, `orders.py`, `drafts.py` (registers `SUPPLIER_REORDER`), each with an explicit `__all__` contract in `__init__.py` |
| `api/routes/purchasing.py` | Suppliers CRUD-minus-delete, the catalogue, the reorder report, propose, and the order state machine's HTTP surface |
| `mcp_server/server.py` | `suggest_reorder_bundles`, `propose_reorder_order`, `list_purchase_orders` — **no create-order, send, or cancel tool exists at all** |
| `backend/seed/2026-08-27-suppliers.sql` | Five suppliers, fourteen price-list links — two products carry two supplier offers each at different prices, one preferred, and one supplier's minimum is set deliberately high, so the demo data exercises the tiebreak and the top-up branch rather than only the easy path |
| `frontend/src/app/suppliers/`, `frontend/src/app/purchasing/` | Supplier list/detail/price-list screens, the bundle cards (labelling top-up lines and stating `below_minimum` in words), and the order list/detail screens with Send/Cancel |

Seed data was run and the bundler verified directly against it: Dairy Direct clears its minimum
outright with the preferred-milk tiebreak firing, Fresh Farms and Prime Meats & Poultry both needed
a top-up to clear their minimums (Prime Meats: chicken breast alone ₨28,800, short of its ₨60,000
minimum; with an egg top-up, ₨60,290). All three designed scenarios confirmed working against real
data, not only against the test suite.

**Why this is a package when its siblings are flat modules.** It is the shape the rest of
`services/` is intended to move to — see "Documented follow-up" below. Proving the shape on new code
first is the cheap way to find out whether it is right before applying it to code that already
works.

### Documented follow-up: repackaging the older flat modules

`products.py` (487 lines), `spoilage.py` (421 lines) and `lots.py` (295 lines) are candidates to
become packages in the same shape as `services/purchasing/`, for the same reason: each has grown
several distinct responsibilities living in one file. Not done as part of gate 29 — it moves
roughly 40 import sites and needs the `import-linter` contracts in `backend/pyproject.toml` edited,
two days before the submission deadline. Trigger: the next non-trivial change to any of the three
files, or 2026-08-29, whichever comes first.

80 backend tests were added this gate (271 total), all four `lint-imports` contracts hold, and the
agent's pinned tool-gating set (34 tests) passes with the three new tools correctly split — two in
`READ_ONLY`, one in `STAGING_ONLY`, none anywhere the agent could create, send, or cancel an order.
`tsc`, `eslint` and `next build` are all clean on the two new screens.

**What is left, and none of it is business logic:**

1. ⚠️ **`purchasing.read` and `purchasing.write` do not exist on the login server.** Until they are
   created, a real token cannot carry them, and the feature 403s for a signed-in user — the same
   silent-failure mode gate 28's `lot.read`/`lot.write` carries. Batched with those two for after
   gate 30, to avoid a seed rebuild per gate.
2. The browser walkthrough is blocked by the same permissions gap — `/suppliers` and `/purchasing`
   redirect the same way `/products` does for a session without them.
3. The demo box seed, still deferred until all features stop changing. See `deploy/SEED-REBUILD.md`.

**`purchasing.write` is deliberately NOT given to the agent.** Placing an order commits the shop's
money. The agent proposes; only a human's approval, checked by `purchasing.write` inside
`create_order`, turns a proposal into a `draft`-status order — and only a human pressing Send, a
second and separate check, turns that into a placed one. `agent/mcp_client.py` requests
`purchasing.read` only, via `READ_ONLY`; `propose_reorder_order` sits in `STAGING_ONLY`, which
writes a queued suggestion and nothing operational.

## Permissions these gates add

Seven for gates 27–29. Each one costs seven edits plus a seed rebuild, so the set is kept
deliberately small — `draft.decide` covers both approving and rejecting, because the security
difference between them is negligible and the maintenance difference is not.

| Permission | Held by | For |
|---|---|---|
| `draft.read` | human, agent | see the queue |
| `draft.create` | human, agent | stage a proposal |
| `draft.decide` | human **only** | approve or reject — see decision 1 |
| `lot.read` | human, agent | expiry and spoilage views |
| `lot.write` | human, agent | receive stock into a lot |
| `purchasing.read` | human, agent | suppliers, price lists, the reorder report, orders |
| `purchasing.write` | human **only** | create/edit suppliers and links, place and send/cancel orders — see gate 29's note above |

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

⚠️ **Amended 2026-08-27, by gate 29.** "One migration per table" is right when tables are
independent, which `action_drafts` and `inventory_lots` were. Gate 29's four tables carry foreign
keys to each other — `supplier_products` to both `suppliers` and `products`, `purchase_order_lines`
to `purchase_orders` — so applying them as four separate migrations would let the database sit in a
state where some of those keys have nothing to point at. One migration, `276428c7f1dd`, creates all
four together. RLS still goes in the create migration, and still has to be added by hand for every
table it touches.

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
