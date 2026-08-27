# Gate 30 — delivery discrepancy and supplier credit

**Status:** design approved 2026-08-27. Implementation not started.
**Owns:** gate 30 only, exactly as scoped by section 10 of
`docs/superpowers/specs/2026-08-27-gate29-purchasing-design.md` — receiving a **sent** purchase
order, splitting what arrived from what was ordered, and recording a supplier credit.

> Subordinate to `docs/PLAN.md` and `docs/FEATURES-PLAN.md`. Where this file disagrees with either,
> they are right and this one is out of date.

## The problem, stated in one paragraph

A purchase order has been sent. A truck arrives. What's on it rarely matches the order exactly —
some cases are short, some are crushed. Someone at the dock needs to record what actually showed
up, in whatever way is fastest for them — typing three numbers into a form, or telling the AI
agent in plain words — and the system needs to turn that into: real stock (dated lots, because
that's when the boxes' expiry dates are finally known), and a record of what the supplier owes for
the difference.

## Scope boundary (carried over from the gate 29 design, restated so this file stands alone)

Gate 30 receives against an **existing, sent** purchase order only. It does not open new orders,
does not touch anything before "sent," and does not touch deliveries with no matching order at all
— see "Alternatives considered" below for why, and where that goes if picked up later.

---

## 1. Data model — one new table

**`credit_memos`.** One row per shortfall on a receipt.

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `supplier_id` | FK → `suppliers` | denormalized off the order for a supplier-wide credit list without a join |
| `purchase_order_id` | FK → `purchase_orders` | |
| `reason` | enum: `short_shipped` / `damaged` | |
| `amount` | `Numeric(10,2)` | |
| `status` | enum: `open` | one value today, on purpose — see decision 2 below. A real column, not a stub, so a later state doesn't need a migration |
| provenance columns | — | same shape as every table since decision 4 in `FEATURES-PLAN.md`: who, through which door, which draft (nullable — the form path has none) |

No changes to `purchase_orders` or `purchase_order_lines` — `quantity_received` and
`quantity_damaged` already exist on the line, built by gate 29 specifically for this gate.

## 2. Two doors, one shared core

A private function, `_apply_receipt(session, actor, order, lines, *, draft=None)`, does the actual
work:
1. For each line: cap `quantity_received` at the line's ordered quantity (see decision 5 below).
2. Write one `InventoryLot` per line for the **good** units only, with the expiry date supplied for
   that line.
3. Damaged units are never written to inventory — they're a number on the credit memo only.
4. If `quantity_received + quantity_damaged < ordered`, write a `credit_memos` row for the
   shortfall (`short_shipped`), and a separate row if `quantity_damaged > 0` (`damaged`).
5. Move the order to `received` (everything accounted for) or `partially_received` (something
   short or damaged) — never back to `sent` or forward past `received`.

Two public entry points call it:

- **`receive_order(session, actor, purchase_order_id, lines, ...)`** — the plain form. Applies
  immediately. Requires `purchasing.write`. No draft involved.
- **`propose_receipt(...)`**, registered as draft type `DELIVERY_RECEIPT` — the AI path. The agent
  has already turned the dock worker's sentence into structured per-line numbers (this is a normal
  MCP tool call with typed arguments, the same shape as gate 29's `propose_reorder_order` — no new
  natural-language-parsing code lives in `services/`; the agent's own model call is the parser).
  Creates an `ActionDraft` only; commits nothing. A manager approves it on `/approvals`, and
  approval is what calls `_apply_receipt`, recording `source_draft_id` via the same
  `DraftHandler` contract gate 29 already extended for this.

**Why the two doors don't get the same review step.** The queue exists so a person checks the
AI's guess before it becomes stock and money. A person typing the form already **is** the check —
there's no guess to verify. This is a refinement of `FEATURES-PLAN.md` decision 1 (which splits by
item-count/financial-consequence), not a contradiction of it: this gate's queue boundary is drawn
by **who produced the numbers**, agent or human, because unlike the reorder bundler, the human path
here has no automated guess to sit in judgement of.

## 3. Expiry date is required on both doors, no default

Form: the field does not submit blank. Agent tool: `expiry_date` is a required parameter, so the
tool's own description makes the agent's next reply ask the dock worker for it rather than invent
one — the same mechanism gate 29 already relies on for required tool arguments, not new code.

## 4. Testing

Same shape as gate 29: `services/purchasing/` gains `receiving.py` (or an addition to `orders.py` —
decided at plan-writing time, not here) with unit tests for `_apply_receipt`'s branches (all good,
all short, all damaged, mixed), `receive_order`'s permission check, and `propose_receipt` /
`DELIVERY_RECEIPT`'s draft-approval round trip. HTTP route tests and MCP tool-gating tests
(`DELIVERY_RECEIPT`'s propose tool in `STAGING_ONLY`, same as `SUPPLIER_REORDER`; no direct-receive
tool reaches the agent, matching "no create/send/cancel tool" from gate 29).

---

## 5. Alternatives considered, and deferred rather than rejected

Recorded so a return trip to any of these is a decision to revisit, not a decision to re-litigate
from nothing.

**Off-order arrivals (a delivery with no matching purchase order) — deferred to a future gate
(tentatively "gate 31").** Considered building it into this gate as a second receiving path that
creates lots directly with no order involved. Rejected for now purely on time: the deadline is
2026-08-29, and it is a genuinely separate feature (no order to reconcile against, no credit-memo
math), not a variant of this one. `services/inventory.py`'s existing plain `adjust_stock` tool
already covers the "just add stock" case in the meantime, without any of the new discrepancy
machinery.

**Credit memos tracked against future orders — deferred, kept record-only for now.** Considered
having an open credit reduce what's owed on the supplier's next order. Rejected for now: it needs
its own status/workflow (open → applied → an order that has to know to look one up) and doubles the
financial logic to get right before the deadline. `credit_memos.status` is a real enum column with
one value today specifically so this can be added later without a migration — only a new status
value and the logic that consumes it.

**Damaged units sometimes still sellable (e.g. at a discount) — deferred, damaged is always
excluded.** Considered a per-line manager choice: exclude, or bring in anyway at a reduced price.
Rejected for now: it's a second decision per line, on top of the discrepancy numbers themselves, and
overlaps with gate 28's own markdown machinery in a way that needs its own design pass, not a quick
addition here.

**Multiple deliveries against one order (partial receipt today, the rest later) — deferred, one
delivery closes the order.** Considered letting an order stay `partially_received` and accept a
second receipt later. Rejected for now: it means tracking how much of each line is still
outstanding across repeated receives, real logic for a case that adds risk this close to the
deadline for a scenario the seeded demo data doesn't need to show.

**Overshipment (more arrives than was ordered) — deferred, received is capped at ordered.**
Considered allowing `quantity_received > ordered`, which would need the credit-memo math to run in
both directions (shop owes supplier, not just the reverse). Rejected for now as a rare case not
worth doubling the number of branches the AI parser and the credit logic both have to get right
before the deadline. Today, a received quantity above what was ordered is simply not
representable — not silently dropped, just not a case this gate handles.

**Repackaging `services/`'s remaining flat modules (`products.py`, `spoilage.py`, `lots.py`) into
the package shape `services/purchasing/` proved — deferred, not part of gate 30.** This was in the
original brainstorming scope for gate 29/30 together. `FEATURES-PLAN.md`'s existing trigger for this
("the next non-trivial change to any of the three files, or 2026-08-29, whichever comes first") is
about to fire, because gate 30's receiving logic is a non-trivial change to `lots.py`. Explicitly
deferred anyway: the restructure touches ~40 import sites and the `import-linter` contracts two days
before the deadline, for a readability improvement with no user-visible effect. If time remains
after gate 30 is done, this is the next candidate — not before.
