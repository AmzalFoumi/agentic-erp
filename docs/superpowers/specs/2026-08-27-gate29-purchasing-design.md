# Gate 29 — suppliers, purchase orders, and the reorder bundler

**Status:** design approved 2026-08-27. Implementation not started.
**Owns:** gate 29 only. Gate 30 (receiving and supplier credits) is scoped at the end of this
document but designed separately.

> Subordinate to `docs/PLAN.md` and `docs/FEATURES-PLAN.md`. Where this file disagrees with either,
> they are right and this one is out of date. Two amendments to `FEATURES-PLAN.md` are proposed
> here and marked ⚠️; they are not in force until that file is edited.

## The problem, stated in one paragraph

The system already knows which products are low — every product carries `reorder_level`, and
`Product.needs_reorder` is a `hybrid_property` that compiles to SQL, so the database can filter on
it. What it cannot do is turn that list into orders, because you do not buy from "the shop": you
buy from named suppliers, most of whom have a **minimum order value** below which they add a
delivery charge or refuse to ship. The manager's real question is *"I have eleven low products
across four suppliers — which orders are worth placing today, and what should I add to the DairyCo
one so it clears their minimum?"* Gate 29 answers exactly that question and stages the answer as an
Action Draft.

**No third-party systems are involved.** "Sending" a purchase order sets a status column in our own
database. Nothing emails a supplier, calls an API, or leaves the machine. This is worth stating
because the feature sounds like an integration and is not one.

## Scope boundary with gate 30

Gate 29 ends when a purchase order reaches status `sent`. Gate 30 owns everything from the truck
arriving onward: receiving into dated lots, the short-shipped-versus-damaged split, the credit memo,
and the natural-language parse of what the dock worker typed.

The line is drawn there because receiving and discrepancy-receiving are the *same function with
different inputs*. Building plain receiving in gate 29 and rewriting it in gate 30 would be doing
the work twice. It also keeps all of the model-dependent risk inside gate 30, so a hard stop at the
end of gate 29 leaves a complete, mechanical, definitely-working purchasing module.

---

## 1. Data model

Four tables, **one migration**.

⚠️ **Amendment to `FEATURES-PLAN.md`, "One migration per table".** That rule was written when each
gate added exactly one table. These four carry foreign keys to each other, so a partially applied
set is a broken database rather than a smaller one. They ship as a single migration, with
`ALTER TABLE ... ENABLE ROW LEVEL SECURITY` for each of the four inside it and the matching
`DISABLE` in `downgrade()`. Autogenerate does not write those lines — it compares columns, and RLS
is not a column.

### `suppliers`

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `name` | String(200), unique, not null | |
| `contact_email` | String(255), nullable | |
| `contact_phone` | String(50), nullable | |
| `lead_time_days` | int, not null, default 0 | How many days from order to arrival |
| `minimum_order_value` | Numeric(12,2), not null, default 0 | **The field the whole gate exists for** |
| `is_active` | bool, not null, default true | No delete anywhere in this API; deactivation is how a supplier leaves |
| provenance | `created_at`, `updated_at`, `created_by`, `updated_by` | Same shape as `Product` |

`Numeric(12,2)` rather than `(10,2)`: a minimum order is a whole-order figure, not a unit price, and
`10,2` caps at 99,999,999.99. In VND that is an ordinary weekly order.

### `supplier_products` — an association object, not a plain link table

Which supplier stocks which product, at what price, in what pack size.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `supplier_id` | FK → `suppliers.id`, CASCADE, indexed | |
| `product_id` | FK → `products.id`, CASCADE, indexed | |
| `unit_cost` | Numeric(10,2), not null | What *this* supplier charges. The same product often has two prices |
| `pack_size` | int, not null, default 1 | **You buy milk in cases of 12, not units of 7** |
| `is_preferred` | bool, not null, default false | First tiebreak when two suppliers stock the same product |
| provenance | as above | |

Unique constraint on `(supplier_id, product_id)`.

**Mapping style — verified against SQLAlchemy 2.0.51 docs on 2026-08-27.** This is the
*association object* pattern: a mapped class on the link table, with `relationship()` from both
sides to it. The `secondary=` many-to-many shortcut is **not** used at all. The SQLAlchemy docs
warn that combining both writes `NULL` into the extra columns unless the shortcut is marked
`viewonly=True`; not defining the shortcut avoids the trap outright, and nothing in this gate needs
to hop from supplier straight to product without seeing the price.

### `purchase_orders`

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `supplier_id` | FK → `suppliers.id`, RESTRICT, indexed | Not CASCADE: deleting a supplier must never silently delete order history |
| `status` | String(32), not null, default `draft` | Values from `PurchaseOrderStatus` |
| `expected_date` | Date, nullable | Computed at send time as today + the supplier's lead time |
| `total_value` | Numeric(12,2), not null, default 0 | A maintained summary of the lines — see §4 |
| `notes` | Text, nullable | |
| `source_draft_id` | int, nullable, **no FK** | Same deliberate choice as `InventoryLot.source_draft_id` |
| provenance | as above | |

### `purchase_order_lines`

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `purchase_order_id` | FK → `purchase_orders.id`, CASCADE, indexed | |
| `product_id` | FK → `products.id`, RESTRICT, indexed | |
| `quantity_ordered` | int, not null | |
| `unit_cost` | Numeric(10,2), not null | **Frozen at order time**, same reason `InventoryLot.cost_price` is |
| `quantity_received` | int, not null, default 0 | **Gate 30. Unused in gate 29** |
| `quantity_damaged` | int, not null, default 0 | **Gate 30. Unused in gate 29** |
| provenance | as above | |

**Why gate 30's two columns are created now.** They are free while writing the table and cost a
second migration later — one that must be applied by hand to Supabase *and* carried into the demo
box by hand, per `CLAUDE.md`'s box checklist. This is the same reasoning as `FEATURES-PLAN.md`
decision 4 applied to a second gate instead of an audit ledger. They are documented in the model as
gate-30 fields so nobody reads them as dead columns.

### `core/enums.py` — one new enum

```python
class PurchaseOrderStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    CANCELLED = "cancelled"
```

The values are those already specified in `services/purchasing.py`'s placeholder docstring, which
`FEATURES-PLAN.md` decision 7 chose over the external spec's four-state version. The last three
values are written now and only reachable in gate 30; a state machine with holes in it is harder to
read than one whose later states are declared and unused.

---

## 2. The bundler

This is the part of the gate a reviewer will ask about, so the rule is written before the code.

### Inputs

- Products where `needs_reorder` is true.
- Their `supplier_products` rows.
- Each supplier's `minimum_order_value`.

### Step 1 — choose one supplier per low product

A product may be stocked by several. The rule, in order:

1. `is_preferred` is true
2. lowest `unit_cost`
3. lowest `supplier_id`

**The third tiebreak looks pointless and is not.** The same scan run twice must produce the same
bundle. Without a total order, two suppliers at the same price could swap places between two reads,
and the approval screen would contradict itself between refreshes — with real money on it.

A low product stocked by nobody is reported in a separate `unsourced` list. It is not silently
dropped: "we cannot buy this from anyone" is information the manager needs.

### Step 2 — how much of each

Order up to a **target level**, defined as `reorder_level * REORDER_TARGET_MULTIPLIER` (2), then
round *up* to a whole number of packs.

```
shortfall  = max(0, target_level - quantity_on_hand)
packs      = ceil(shortfall / pack_size)
quantity   = packs * pack_size
```

A product already at or above target contributes no line. Rounding up rather than to nearest is
deliberate: rounding down can produce a line that still leaves the product below its reorder level,
which is an order that did not solve the problem it was raised for.

**The `reorder_level = 0` hole, and how it is closed.** `reorder_level` defaults to 0, and
`needs_reorder` is `quantity_on_hand <= reorder_level`. So a product with zero stock and an unset
reorder level *is* flagged low — correctly, there is none of it — while `target = 0 * 2 = 0` yields
a shortfall of 0 and an empty line. The bundler would report a product as needing reordering and
then order none of it.

The rule: when the computed quantity is 0 but the product is flagged low, order **one pack**.
"There is none on the shelf and nobody has configured a reorder level" is still a reason to buy
some. A test pins this case by name.

### Step 3 — group and price

Group the lines by chosen supplier. `bundle_value = sum(quantity * unit_cost)`, rounded through
`pricing.to_money` so the rounding rule has exactly one definition in the codebase.

### Step 4 — top up to the minimum

If `bundle_value >= minimum_order_value`, the bundle is done.

Otherwise, look at that supplier's **other** products — ones not currently low — and rank them by
*headroom*, `quantity_on_hand - reorder_level`, smallest first: the product closest to going low is
the most useful thing to add. Add one pack at a time, cheapest-first within equal headroom, until
the minimum clears.

If the supplier's whole catalogue is exhausted and the bundle is still short, return it flagged
`below_minimum` with the shortfall shown. **It is never silently proposed as if it were fine** — a
manager who approves an under-minimum order and then sees a delivery charge has been misled by the
software.

### Why not the two alternatives

**Cheapest-possible top-up** (solve for the least money that clears the threshold) is tidier
mathematically and fills the order with whatever happens to be cheap rather than whatever the shop
will actually need. A manager reading it cannot tell why any particular item is on the list, which
makes the proposal unapprovable in practice.

**Scaling the existing lines up** is the simplest to write and buys three times the rice instead of
adding the milk you will want next week.

The chosen rule wins because every line survives the test that matters: it can be justified in one
sentence a manager accepts. *"Butter is on here because you are two days from needing it and it got
DairyCo over their minimum."*

### The one caveat, recorded not hidden

The bundler reads `quantity_on_hand`, which gate 28 made a maintained summary of the lots. It does
**not** look at expiry. A supplier bundle can therefore propose reordering a product that also
appears on the spoilage report — technically consistent (you are low *and* what you have is about
to expire, which is exactly when you reorder) but confusing on screen. Not solved in this gate;
noted so it is not read later as an oversight.

---

## 3. Code layout

```
services/purchasing/
  __init__.py       the contract — the only names other code may import
  _repository.py    every query in the package. Private
  quantities.py     pure arithmetic: target level, pack rounding, bundle value
  suppliers.py      supplier use cases
  catalog.py        supplier↔product links
  reorder.py        the scan and the bundler
  orders.py         create / send / cancel — the state machine
  drafts.py         the SUPPLIER_REORDER draft type and its handler
```

### What `__init__.py` is for

It re-exports a named list and nothing else. Other code writes `from services import purchasing`
and can reach only what the contract exposes; `_repository` and the module internals are not part of
it. This is the "interface" boundary: the package can be reorganised internally without touching a
single caller, which is precisely what the flat modules cannot do today.

`__all__` is declared explicitly rather than left implicit, so adding a function to a module does
not silently widen the public surface.

### What `_repository.py` is for

Every `select()` in the package lives there. The use-case files then read as business rules rather
than as queries — `reorder.py` should be legible to someone who does not know SQLAlchemy. It takes
a `Session` and returns models; it checks no permissions and commits nothing, exactly like
`lots.recalculate_on_hand`.

### ⚠️ Amendment to `FEATURES-PLAN.md`, "How the code is laid out"

That table assigns "reorder calculation" to `services/pricing.py`, on the grounds that a markdown
calculation and a reorder calculation are both pricing arithmetic. This design puts it in
`purchasing/quantities.py` instead.

The reason the original rule was written was to stop the **discount ladder** existing in two places,
because a shop that advertises one price and charges another has a real problem. There is no ladder
here. `pricing.py` is *what we charge*; `quantities.py` is *how much we buy*. They are different
domains that happen to both use numbers. `quantities.py` imports `pricing.to_money` for rounding,
so the money rules still have exactly one definition — which is the part of the original rule that
actually mattered.

### Documented follow-up: the flat modules should become packages too

Not done in gate 29, and this is the record of why.

`services/products.py` is 487 lines, `services/spoilage.py` 421, `services/lots.py` 295. All three
would read better in the shape above — `products/` with the catalogue use cases separated from
stock adjustment, `inventory/` holding lots and spoilage behind one contract.

**Why not now:** it moves roughly forty import sites across `api/`, `mcp_server/`, `agent/` and 191
tests, and requires editing the `import-linter` contracts in `backend/pyproject.toml`. A broken
import two days before the submission deadline is a broken demo, and the churn buys no capability.

**The trigger to do it:** the next time any of those three files is opened for a change larger than
a bug fix, or immediately after the submission deadline of 2026-08-29 — whichever comes first.
Gate 29 proves the shape on new code first, which is the cheap way to find out whether the shape is
right before applying it to code that already works.

---

## 4. Rules that live in `services/` and nowhere else

**The state machine.** `draft → sent → partially_received → received`, plus `cancelled` from
`draft` or `sent`. Every other transition raises `ValidationError`. This lives in `orders.py`
because there are two adapters and an adapter cannot be trusted to enforce a legal transition — they
will drift.

**`total_value` has one write path.** `_recalculate_total(session, order)` sums the lines and
writes the column. Nothing else assigns to `total_value`. This is the same rule gate 28 established
for `Product.quantity_on_hand`, and it gets the same protection: a source-level test that greps
`services/` and fails if the column is assigned anywhere else. No runtime test can catch that bug,
because the bug is another correct-looking assignment somewhere else in the tree.

**Orders are immutable once sent.** Lines may be added, changed or removed only while the order is
`draft`. After `send_order`, the lines are what was ordered, and gate 30 compares reality against
them. An editable sent order would make the discrepancy figure meaningless.

**Nothing is deleted.** Consistent with the rest of the API. Suppliers deactivate, orders cancel.

---

## 5. The draft type

`SUPPLIER_REORDER`, registered in `services/purchasing/drafts.py` and imported from
`services/__init__.py` alongside `spoilage`, so the registry is complete for anyone importing the
service layer.

**Payload schema** (Pydantic, validated on the way in *and again* on the way out — a manager may
edit it in between, and the edited version is the one that runs):

```
supplier_id: int
expected_date: date | None
lines: list[ReorderLine]        # min_length=1
    product_id: int
    quantity: int               # > 0
    unit_cost: Decimal          # >= 0
```

A `field_validator` rejects duplicate `product_id` values across lines — the same defect found and
fixed in gate 28's markdown payload, where two lines for one product meant the last one silently
won.

`expected_date` in the payload is **indicative only** — it is what the bundler estimated when it
proposed, so the manager can see roughly when the stock would land. `send_order` recomputes it as
`today + supplier.lead_time_days` and overwrites it, because the lead time counts from the day the
order was actually placed, not from the day something suggested it. A draft approved on Friday and
sent on Monday must not claim Friday's arrival date.

**Handler** `_create_purchase_order(session, actor, client, payload)`:
requires `purchasing.write`, creates the order in `draft` with its lines, sets `source_draft_id`,
recalculates the total, and **does not commit** — `drafts.approve_draft` owns the transaction.

The handler runs as the *approving human*, never as the agent. It does not send the order: approving
a proposal creates a purchase order in `draft`, and a person still presses send. That second step is
not ceremony — it is the last point at which someone can look at the whole order before it counts as
placed.

**The two money figures** on the draft: `cost_at_risk` is left `None` (nothing is at risk here —
this is spending, not loss), and `projected_recovery` is `None` too. `FEATURES-PLAN.md` made both
nullable for exactly this case. The order's value is in the payload where it belongs; forcing it
into a field named "recovery" would make the approvals screen lie.

---

## 6. Permissions

Two, not four.

| Permission | Held by | For |
|---|---|---|
| `purchasing.read` | human, agent | suppliers, links, reorder suggestions, orders |
| `purchasing.write` | human **only** | create/edit suppliers and links, create/send/cancel orders |

**Why two rather than `supplier.read` / `supplier.write` / `order.read` / `order.write`.** Each
permission costs seven hand-edits plus a full seed rebuild, per `docs/DEPLOY-PLAN.md`. A missed one
does not error: ThunderID answers a request for an unknown permission with a valid token carrying
**no scope claim at all**, so the symptom is a signed-in user getting 403 on every screen in the
application. Four names is four chances at that. There is no meaningful security boundary between
"may edit a supplier" and "may create an order" — both are manager work.

**The agent must never hold `purchasing.write`**, for the same reason it must never hold
`draft.decide` or `lot.write`: an agent that could place orders could invent a shortage and solve
it. It proposes; a human approves; the handler runs as that human.

⚠️ These are added to ThunderID in the **batched session after gate 30**, together with gate 28's
`lot.read` / `lot.write`. Until then every test passes (tests build actors directly) and a real
signed-in user gets 403 on the new screens. This is a known, chosen state, not a bug.

---

## 7. What each door exposes

### API (`api/routes/purchasing.py`)

```
GET    /suppliers                      list, filterable by is_active
POST   /suppliers                      create
GET    /suppliers/{id}                 one supplier
PATCH  /suppliers/{id}                 update, including deactivate
GET    /suppliers/{id}/products        its catalogue with prices
POST   /suppliers/{id}/products        link a product
PATCH  /supplier-products/{id}         change price, pack size, preferred
GET    /purchasing/reorder-suggestions the bundles. Read-only, changes nothing
POST   /purchasing/reorder-drafts      stage a bundle as an Action Draft
GET    /purchase-orders                list, filterable by status and supplier
POST   /purchase-orders                create directly, without a draft
GET    /purchase-orders/{id}           one order with its lines
POST   /purchase-orders/{id}/send      draft -> sent
POST   /purchase-orders/{id}/cancel    draft|sent -> cancelled
```

No delete. Money serialises as a JSON **string** throughout, per the existing convention.

### MCP (`mcp_server/server.py`)

| Tool | Gating | Does |
|---|---|---|
| `suggest_reorder_bundles` | `READ_ONLY` | Reports what to buy. Changes nothing |
| `propose_reorder_order` | `STAGING_ONLY` | Writes one draft row |
| `list_purchase_orders` | `READ_ONLY` | Reads orders |

**There is no create-order tool, no send tool and no cancel tool.** The agent's entire reach into
purchasing is "look" and "suggest". `agent/tests/test_tool_gating.py` pins the allowlists and must
be updated deliberately, as its own docstring instructs.

### Frontend

| Route | Shows |
|---|---|
| `/suppliers` | list with create; deactivate from the row |
| `/suppliers/[id]` | one supplier, its product links, add/edit a link |
| `/purchasing` | the reorder bundles, with "propose this order" per supplier |
| `/purchasing/orders` | orders, filterable by status |
| `/purchasing/orders/[id]` | one order, its lines, send/cancel |

Server Components reading through the generated client; Server Actions for writes. No `app/api`
route — that would be a third adapter, which `FRONTEND-PLAN.md` forbids. Nav gains a "Purchasing"
group.

⚠️ `src/lib/api/schema.d.ts` is regenerated by `npm run api:types` with the API running. It is
build output: committed, never hand-edited.

### Seed

`backend/seed/2026-08-27-suppliers.sql` — five suppliers with realistic lead times and minimum
order values, linked to the existing catalogue at prices and pack sizes chosen so that **at least
one bundle lands under its supplier's minimum and needs topping up**. A demo where the interesting
branch never fires demonstrates nothing. Idempotent, guarded on supplier name, and `CURRENT_DATE`
relative wherever a date appears.

---

## 8. Testing

`backend/tests/test_purchasing_quantities.py` — pure arithmetic, no database: pack rounding, target
level, the ceiling behaviour, and that a product at target contributes no line.

`backend/tests/test_purchasing_reorder.py` — supplier choice including every tiebreak, the top-up
walk, the `below_minimum` flag, the `unsourced` list, and **determinism**: the same scan twice
returns identical bundles.

`backend/tests/test_purchasing_orders.py` — every legal transition, and that every illegal one
raises. The `total_value` single-write-path source guard.

`backend/tests/test_purchasing_drafts.py` — payload validation both ways, duplicate-product
rejection, that the handler creates an order in `draft` and not `sent`, and that an actor without
`purchasing.write` is refused.

No frontend tests: `frontend/` has no suite and no CI job, and a two-day feature push is not when
that gets fixed. Recorded in `FEATURES-PLAN.md` already; restated here so it is not a surprise.

---

## 9. What gate 29 deliberately does not build

- **No receiving.** Gate 30.
- **No emails, no supplier portal, no EDI.** "Sent" is a status column.
- **No delete**, anywhere.
- **No scheduler.** Every scan is triggered by a human or by the agent on request.
- **No row locking.** The concurrency deferral recorded in `FEATURES-PLAN.md` for gate 28 applies
  here identically, with the same expiry condition: when a second human user exists.
- **No multi-currency.** One currency, as everywhere else in this system.

## 10. Gate 30, scoped only

Recorded so the gate-29 tables are shaped for it, not designed here.

Receiving a sent order into dated `InventoryLot` rows (which is where the expiry dates on the
cartons finally enter the system), splitting the difference between ordered and arrived into
**short-shipped** (the supplier owes us) and **damaged** (a claim, or our loss), a `credit_memos`
table, and an MCP tool that turns *"DairyCo came, only 40 cases not 50, 2 crushed"* into structured
lines against the open order.

The model risk lives entirely here, and the mitigation is structural: the parse produces a **draft**
laid out beside the original order, so a wrong number costs a correction rather than money. If the
parse proves unreliable in testing, the fallback is the same screen with three number boxes and no
model involved — the feature survives without the agent.
