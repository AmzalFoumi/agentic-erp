# Gate 30 — Delivery Discrepancy and Supplier Credit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Receive a **sent** purchase order — via a plain form or the AI agent — splitting what
arrived from what was ordered, writing good units into dated inventory lots, and recording a
supplier credit for anything short-shipped or damaged.

**Architecture:** One new table, `credit_memos`. One private core function,
`services/purchasing/receiving._apply_receipt`, does the actual work; two public entry points call
it — `receive_order` (the form, applies immediately) and a new draft type, `DELIVERY_RECEIPT`
(the AI path, always queues to `/approvals`). Reuses `services.lots.receive_lot` for lot creation
rather than writing a second lot-writing code path.

**Tech Stack:** Same as gates 27–29 — FastAPI, SQLAlchemy 2.0, Pydantic, pytest, Next.js/React on
the frontend. No new libraries.

**Spec:** `docs/superpowers/specs/2026-08-27-gate30-delivery-discrepancy-design.md` — read it
first. This plan implements it task-by-task; where the two disagree, the spec is right.

## Global Constraints

- **No Co-Authored-By trailer on any commit.** Plain commit messages only.
- **Commit locally only — do not push to origin.** The gate 29 PR is still open under CodeRabbit
  review; gate 30 work must not push until that merges.
- **Atomic commits, one per step 5 in each task below.**
- **Money is `Decimal`/`Numeric(10,2)`, serialized as a JSON string** — never `float`.
- **`services/` and `core/` may not import `fastapi`, `starlette`, `mcp`, `uvicorn`, `httpx`, or
  `jwt`.** Run `lint-imports` from `backend/` after every task that touches those layers.
- **`session` first, `actor` second, everything else keyword-only** in every service function.
  Check `actor.can(...)` (via `require_permission`) before touching the session.
- **No new ThunderID permissions.** Reuse `purchasing.write` (moves order status, creates credit
  memos) and `lot.write` (writes lots) — both already exist as *concepts* in this codebase, even
  though neither is created on the login server yet (that's a separate, already-tracked gap).
- **A receipt above ordered is rejected, not capped.** A receipt where `quantity_received +
  quantity_damaged` exceeds `quantity_ordered` is rejected outright — never silently truncated to
  the ordered amount. Overshipment is out of scope — see the design spec's "Alternatives
  considered."
- **Expiry date is required on both doors, no default.** Never invent one.
- **`quantity_received` is already the count of good units** — it does NOT include
  `quantity_damaged`. The two are separate counts that both come out of the same
  `quantity_ordered`; only `quantity_received` units become a lot, damaged units never do.
- **One delivery closes the order.** No partial-receipt-then-top-up-later tracking.
- Run only the test file(s) for the task you're on while iterating; save a full `pytest` run for
  the end of the plan.

---

## Task 1: `credit_memos` table, enums, migration

**Files:**
- Modify: `backend/core/enums.py`
- Modify: `backend/core/models.py`
- Create: `backend/alembic/versions/<generated>_create_credit_memos_table.py`
- Test: `backend/tests/test_models_credit_memo.py`

**Interfaces:**
- Produces: `CreditMemoReason` enum (`SHORT_SHIPPED = "short_shipped"`, `DAMAGED = "damaged"`),
  `CreditMemoStatus` enum (`OPEN = "open"`), `CreditMemo` ORM model with columns `id`,
  `supplier_id` (FK → `suppliers.id`, `RESTRICT`), `purchase_order_id` (FK → `purchase_orders.id`,
  `RESTRICT`), `reason` (`String(32)`), `amount` (`Numeric(10,2)`), `status` (`String(16)`,
  default `CreditMemoStatus.OPEN.value`), plus the standard provenance columns
  (`created_at`, `updated_at`, `created_by`, `updated_by`, `created_via`, `source_draft_id`
  nullable, no FK — same shape as `InventoryLot`/`PurchaseOrder`).

- [ ] **Step 1: Add the two enums to `core/enums.py`**

Add after `PurchaseOrderStatus`:

```python
class CreditMemoReason(str, Enum):
    """Why the shop is owed money on a receipt.

    Two reasons only, matching gate 30's design: a line either arrived short
    of what was ordered, or arrived damaged. A line can carry both — a
    shortfall and a damage credit are two separate rows, not one merged
    figure, so a manager reading the supplier's credit list can tell which
    problem is which.
    """

    SHORT_SHIPPED = "short_shipped"
    DAMAGED = "damaged"


class CreditMemoStatus(str, Enum):
    """Where a credit memo stands.

    One value today, on purpose. `docs/superpowers/specs/2026-08-27-gate30-
    delivery-discrepancy-design.md`'s "Alternatives considered" defers
    tracking a credit against a future order — that would need a second
    status (e.g. APPLIED). A real enum column with one member costs nothing
    now and needs no migration to grow later.
    """

    OPEN = "open"
```

- [ ] **Step 2: Add the `CreditMemo` model to `core/models.py`**

Add near `PurchaseOrderLine` (after it). Check the top of `core/models.py` for existing imports —
`Numeric`, `String`, `ForeignKey`, `DateTime`, `func`, `Mapped`, `mapped_column`, `Decimal`,
`datetime` are all already imported there for the other tables; `CreditMemoReason` and
`CreditMemoStatus` need adding to the `from core.enums import ...` line.

```python
class CreditMemo(Base):
    """The supplier owes the shop money: a receipt came in short or damaged.

    Record-only for gate 30 — see the design spec's "Alternatives
    considered". `PurchaseOrderRead` exposes these rows for reading, but
    nothing applies or settles a credit memo against a future order yet — it
    exists so a manager can see who owes what. `supplier_id` is denormalized
    off the order so a supplier-wide credit list needs no join.
    """

    __tablename__ = "credit_memos"

    id: Mapped[int] = mapped_column(primary_key=True)

    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True
    )
    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="RESTRICT"), index=True
    )

    reason: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(
        String(16), default=CreditMemoStatus.OPEN.value
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[str] = mapped_column(String(128))
    updated_by: Mapped[str | None] = mapped_column(String(128), default=None)
    created_via: Mapped[str] = mapped_column(String(16), default="system")
    source_draft_id: Mapped[int | None] = mapped_column(default=None)

    def __repr__(self) -> str:
        return (
            f"CreditMemo(id={self.id!r}, supplier_id={self.supplier_id!r}, "
            f"reason={self.reason!r}, amount={self.amount!r})"
        )
```

- [ ] **Step 3: Write a failing model-existence test**

```python
# backend/tests/test_models_credit_memo.py
"""The credit_memos table exists with the shape gate 30 needs."""

from decimal import Decimal

from core.enums import CreditMemoReason, CreditMemoStatus
from core.models import CreditMemo


def test_credit_memo_round_trips(session, supplier, purchase_order):
    memo = CreditMemo(
        supplier_id=supplier.id,
        purchase_order_id=purchase_order.id,
        reason=CreditMemoReason.SHORT_SHIPPED.value,
        amount=Decimal("120.50"),
        created_by="tester",
        created_via="system",
    )
    session.add(memo)
    session.commit()
    session.refresh(memo)

    assert memo.id is not None
    assert memo.status == CreditMemoStatus.OPEN.value
    assert memo.source_draft_id is None
```

Check `backend/tests/conftest.py` for existing `supplier` and `purchase_order` fixtures before
writing new ones — gate 29's `test_purchasing_orders.py` likely already has a `purchase_order`
fixture in a local `conftest.py` under `services/purchasing`-adjacent tests. If none exists at
module scope, add minimal ones in this test file directly using `purchasing.create_supplier` and
`purchasing.create_order`.

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_models_credit_memo.py -v`
Expected: FAIL — `ImportError: cannot import name 'CreditMemo'` (or `CreditMemoReason`)

- [ ] **Step 5: Confirm it passes once Steps 1–2 are in place, then generate and hand-fix the migration**

Run: `pytest tests/test_models_credit_memo.py -v` → expect PASS (the test only needs the model,
not a real migrated table, because `conftest.py`'s `session` fixture runs against the already-
migrated live schema — so this step actually requires the migration to exist first if run against
the real database; if it fails with a "relation does not exist" error, that confirms the migration
is the missing piece and step 6 below is next).

The developer runs `alembic revision --autogenerate -m "create credit memos table"` from
`backend/` (per this project's working agreement — the agent does not run alembic). Once they
paste back the generated file's path and content:

- [ ] **Step 6: Hand-edit the generated migration to add RLS**

Follow the exact pattern of `276428c7f1dd_create_purchasing_tables.py` (gate 29's migration):
append `op.execute("ALTER TABLE credit_memos ENABLE ROW LEVEL SECURITY")` at the end of
`upgrade()`, and prepend `op.execute("ALTER TABLE credit_memos DISABLE ROW LEVEL SECURITY")` at
the start of `downgrade()`. Verify `down_revision` points at gate 29's migration
(`276428c7f1dd`) — it should autogenerate that way since it's the current head, but confirm rather
than assume.

- [ ] **Step 7: Verify with the developer, then commit**

Ask the developer to run `alembic upgrade head` and `alembic current`, and confirm
`276428c7f1dd`'s child is now head. Then, once confirmed:

```bash
git add backend/core/enums.py backend/core/models.py backend/alembic/versions/ backend/tests/test_models_credit_memo.py
git commit -m "feat(purchasing): add credit_memos table for gate 30"
```

---

## Task 2: The shared receiving core and the direct (form) door

**Files:**
- Create: `backend/services/purchasing/receiving.py`
- Modify: `backend/services/purchasing/__init__.py`
- Test: `backend/tests/test_purchasing_receiving.py`

**Interfaces:**
- Consumes: `services.lots.receive_lot(session, actor, *, client, product_id, lot_code, quantity,
  cost_price=None, expiry_date=None, source_draft_id=None) -> InventoryLot` (existing,
  `backend/services/lots.py:128`). `services.purchasing.orders._get_or_raise` (existing, gate 29).
  `core.models.CreditMemo`, `core.enums.CreditMemoReason` (Task 1).
- Produces: `ReceiptLineInput` dataclass (`product_id: int`, `quantity_received: int`,
  `quantity_damaged: int`, `expiry_date: date`, `lot_code: str`). `_apply_receipt(session, actor,
  *, client, order, lines, source_draft_id=None) -> PurchaseOrder`. `receive_order(session, actor,
  *, client, order_id, lines) -> PurchaseOrder` — the direct door, used by Task 4's route.
  `_apply_receipt` is consumed by Task 3's draft handler.

- [ ] **Step 1: Write the failing tests for `_apply_receipt`'s branches**

```python
# backend/tests/test_purchasing_receiving.py
"""services/purchasing/receiving.py — the shared receiving core."""

from datetime import date
from decimal import Decimal

import pytest

from core.actor import SystemActor
from core.enums import ClientType, CreditMemoReason, PurchaseOrderStatus
from core.exceptions import PermissionDeniedError, ValidationError
from services import purchasing
from services.purchasing.orders import OrderLineInput
from services.purchasing.receiving import ReceiptLineInput, receive_order


@pytest.fixture
def sent_order(session, product):
    supplier = purchasing.create_supplier(
        session,
        SystemActor(),
        client=ClientType.SYSTEM,
        name="Receiving Test Supplier",
        lead_time_days=2,
        minimum_order_value=Decimal("0.00"),
    )
    order = purchasing.create_order(
        session,
        SystemActor(),
        client=ClientType.SYSTEM,
        supplier_id=supplier.id,
        lines=[OrderLineInput(product_id=product.id, quantity=50, unit_cost=Decimal("2.00"))],
    )
    return purchasing.send_order(
        session, SystemActor(), order_id=order.id, today=date(2026, 8, 27)
    )


def test_receiving_everything_ordered_moves_order_to_received(session, sent_order, product):
    result = receive_order(
        session,
        SystemActor(),
        client=ClientType.WEB_UI,
        order_id=sent_order.id,
        lines=[
            ReceiptLineInput(
                product_id=product.id,
                quantity_received=50,
                quantity_damaged=0,
                expiry_date=date(2026, 9, 10),
                lot_code="DN-TEST-1",
            )
        ],
    )
    assert result.status == PurchaseOrderStatus.RECEIVED.value
    line = result.lines[0]
    assert line.quantity_received == 50
    assert line.quantity_damaged == 0


def test_short_shipment_writes_a_credit_memo_and_partial_status(session, sent_order, product):
    result = receive_order(
        session,
        SystemActor(),
        client=ClientType.WEB_UI,
        order_id=sent_order.id,
        lines=[
            ReceiptLineInput(
                product_id=product.id,
                quantity_received=40,
                quantity_damaged=0,
                expiry_date=date(2026, 9, 10),
                lot_code="DN-TEST-2",
            )
        ],
    )
    assert result.status == PurchaseOrderStatus.PARTIALLY_RECEIVED.value

    from core.models import CreditMemo
    from sqlalchemy import select

    memos = session.execute(
        select(CreditMemo).where(CreditMemo.purchase_order_id == result.id)
    ).scalars().all()
    assert len(memos) == 1
    assert memos[0].reason == CreditMemoReason.SHORT_SHIPPED.value
    assert memos[0].amount == Decimal("20.00")  # 10 short * 2.00 unit_cost


def test_damaged_units_are_excluded_from_stock_and_credited(session, sent_order, product):
    result = receive_order(
        session,
        SystemActor(),
        client=ClientType.WEB_UI,
        order_id=sent_order.id,
        lines=[
            ReceiptLineInput(
                product_id=product.id,
                quantity_received=48,
                quantity_damaged=2,
                expiry_date=date(2026, 9, 10),
                lot_code="DN-TEST-3",
            )
        ],
    )
    assert result.status == PurchaseOrderStatus.PARTIALLY_RECEIVED.value
    line = result.lines[0]
    assert line.quantity_received == 48
    assert line.quantity_damaged == 2

    from core.models import CreditMemo
    from sqlalchemy import select

    memos = session.execute(
        select(CreditMemo).where(CreditMemo.purchase_order_id == result.id)
    ).scalars().all()
    assert len(memos) == 1
    assert memos[0].reason == CreditMemoReason.DAMAGED.value
    assert memos[0].amount == Decimal("4.00")  # 2 damaged * 2.00 unit_cost

    session.refresh(product)
    assert product.quantity_on_hand == 48  # damaged units never became stock


def test_received_quantity_above_ordered_is_rejected(session, sent_order, product):
    with pytest.raises(ValidationError):
        receive_order(
            session,
            SystemActor(),
            client=ClientType.WEB_UI,
            order_id=sent_order.id,
            lines=[
                ReceiptLineInput(
                    product_id=product.id,
                    quantity_received=51,
                    quantity_damaged=0,
                    expiry_date=date(2026, 9, 10),
                    lot_code="DN-TEST-4",
                )
            ],
        )


def test_receiving_requires_purchasing_write(session, sent_order, product):
    from core.actor import Actor

    class NoPermActor:
        id = "no-perms"

        def can(self, permission: str) -> bool:
            return False

    with pytest.raises(PermissionDeniedError):
        receive_order(
            session,
            NoPermActor(),
            client=ClientType.WEB_UI,
            order_id=sent_order.id,
            lines=[
                ReceiptLineInput(
                    product_id=product.id,
                    quantity_received=50,
                    quantity_damaged=0,
                    expiry_date=date(2026, 9, 10),
                    lot_code="DN-TEST-5",
                )
            ],
        )
```

Check `backend/tests/conftest.py` for an existing `product` fixture before assuming its shape —
gate 28/29's test files already depend on one; reuse it rather than redefining it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_purchasing_receiving.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.purchasing.receiving'`

- [ ] **Step 3: Write `services/purchasing/receiving.py`**

```python
"""Receiving a sent purchase order: the shared core both doors call.

### The one rule this module exists to enforce

Damaged units never become stock. Only `quantity_received - quantity_damaged`
units become an InventoryLot; damaged units are a number on a credit memo
only. This is checked in exactly one place, `_apply_receipt`, so the two
public doors below - a human typing a form, or a manager approving the AI's
parse of what the dock worker said - can never disagree about it.

### Reuses services.lots.receive_lot rather than writing stock twice

`receive_lot` already does the "write a lot, recalculate quantity_on_hand"
work correctly (gate 28). Writing a second lot-creation path here would be
exactly the drift `docs/FEATURES-PLAN.md` decision 3 exists to prevent.

### Received is capped at ordered

Overshipment is out of scope for gate 30 - see the design spec's
"Alternatives considered". A line asking for more than was ordered is
refused before anything is written, not silently truncated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from core.actor import Actor
from core.enums import ClientType, CreditMemoReason, PurchaseOrderStatus
from core.exceptions import NotFoundError, ValidationError
from core.models import CreditMemo, PurchaseOrder
from services import lots
from services.guards import require_permission
from services.purchasing.orders import _get_or_raise


@dataclass(frozen=True)
class ReceiptLineInput:
    """What arrived for one line on the order.

    Frozen, and deliberately not the ORM model - a caller describing a
    receipt should not be handing us half-built database rows, the same
    reasoning as orders.OrderLineInput.
    """

    product_id: int
    quantity_received: int
    quantity_damaged: int
    expiry_date: date
    lot_code: str


def _find_line(order: PurchaseOrder, product_id: int):
    for line in order.lines:
        if line.product_id == product_id:
            return line
    raise ValidationError(
        f"Product {product_id} is not on purchase order {order.id}."
    )


def _apply_receipt(
    session: Session,
    actor: Actor,
    *,
    client: ClientType,
    order: PurchaseOrder,
    lines: list[ReceiptLineInput],
    source_draft_id: int | None = None,
) -> PurchaseOrder:
    """Do the actual work of receiving. Not exported - both public doors below
    call this after their own checks.

    No commit: like every gate 29 core function, the caller (`receive_order`
    directly, or `drafts.approve_draft` via the DELIVERY_RECEIPT handler)
    owns the transaction.
    """
    if order.status != PurchaseOrderStatus.SENT.value:
        raise ValidationError(
            f"A purchase order that is {order.status!r} cannot be received."
        )

    if not lines:
        raise ValidationError("A receipt must have at least one line.")

    seen: set[int] = set()
    fully_received = True

    for receipt_line in lines:
        if receipt_line.product_id in seen:
            raise ValidationError(
                f"Product {receipt_line.product_id} appears on this receipt "
                "more than once."
            )
        seen.add(receipt_line.product_id)

        if receipt_line.quantity_received < 0 or receipt_line.quantity_damaged < 0:
            raise ValidationError("Received and damaged quantities cannot be negative.")

        order_line = _find_line(order, receipt_line.product_id)
        total_accounted = receipt_line.quantity_received + receipt_line.quantity_damaged
        if total_accounted > order_line.quantity_ordered:
            raise ValidationError(
                f"Product {receipt_line.product_id}: received "
                f"({receipt_line.quantity_received}) plus damaged "
                f"({receipt_line.quantity_damaged}) exceeds the "
                f"{order_line.quantity_ordered} ordered."
            )

        good_units = receipt_line.quantity_received - receipt_line.quantity_damaged
        if good_units < 0:
            raise ValidationError(
                f"Product {receipt_line.product_id}: damaged quantity cannot "
                "exceed received quantity."
            )

        order_line.quantity_received = receipt_line.quantity_received
        order_line.quantity_damaged = receipt_line.quantity_damaged
        order_line.updated_by = actor.id

        if good_units > 0:
            lots.receive_lot(
                session,
                actor,
                client=client,
                product_id=receipt_line.product_id,
                lot_code=receipt_line.lot_code,
                quantity=good_units,
                cost_price=order_line.unit_cost,
                expiry_date=receipt_line.expiry_date,
                source_draft_id=source_draft_id,
            )

        shortfall = order_line.quantity_ordered - total_accounted
        if shortfall > 0:
            session.add(
                CreditMemo(
                    supplier_id=order.supplier_id,
                    purchase_order_id=order.id,
                    reason=CreditMemoReason.SHORT_SHIPPED.value,
                    amount=Decimal(shortfall) * order_line.unit_cost,
                    created_by=actor.id,
                    created_via=client.value,
                    source_draft_id=source_draft_id,
                )
            )
            fully_received = False

        if receipt_line.quantity_damaged > 0:
            session.add(
                CreditMemo(
                    supplier_id=order.supplier_id,
                    purchase_order_id=order.id,
                    reason=CreditMemoReason.DAMAGED.value,
                    amount=Decimal(receipt_line.quantity_damaged) * order_line.unit_cost,
                    created_by=actor.id,
                    created_via=client.value,
                    source_draft_id=source_draft_id,
                )
            )
            fully_received = False

        if total_accounted < order_line.quantity_ordered:
            fully_received = False

    order.status = (
        PurchaseOrderStatus.RECEIVED.value
        if fully_received
        else PurchaseOrderStatus.PARTIALLY_RECEIVED.value
    )
    order.updated_by = actor.id

    return order


def receive_order(
    session: Session,
    actor: Actor,
    *,
    client: ClientType,
    order_id: int,
    lines: list[ReceiptLineInput],
) -> PurchaseOrder:
    """The plain-form door. Applies immediately - a human typing these numbers
    already is the review, so this does not go through the draft queue.

    Requires `purchasing.write`, same permission `send_order`/`cancel_order`
    already check - receiving is one more state transition on the same order.
    """
    require_permission(actor, "purchasing.write")

    order = _get_or_raise(session, order_id)
    _apply_receipt(session, actor, client=client, order=order, lines=lines)

    session.commit()
    session.refresh(order)
    return order
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_purchasing_receiving.py -v`
Expected: PASS, all five tests

- [ ] **Step 5: Export `receive_order` and add it to `__init__.py`'s `__all__`, run `lint-imports`, then commit**

In `backend/services/purchasing/__init__.py`, add:
```python
from services.purchasing.receiving import receive_order
```
to the import block, and `"receive_order"` to `__all__` (keep both alphabetically sorted, matching
the existing style).

Run: `lint-imports` from `backend/` → expect `Contracts: 4 kept, 0 broken.`

```bash
git add backend/services/purchasing/receiving.py backend/services/purchasing/__init__.py backend/tests/test_purchasing_receiving.py
git commit -m "feat(purchasing): add the shared receiving core and the direct receive door"
```

---

## Task 3: The AI path — `DELIVERY_RECEIPT` draft type

**Files:**
- Modify: `backend/services/purchasing/drafts.py`
- Test: `backend/tests/test_purchasing_receiving_drafts.py`

**Interfaces:**
- Consumes: `services.purchasing.receiving._apply_receipt`, `ReceiptLineInput` (Task 2).
  `services.draft_types.register`, `services.drafts.create_draft` (existing).
  `services.purchasing.orders._get_or_raise` (existing).
- Produces: `DELIVERY_RECEIPT` draft type constant. `ReceiptPayload` Pydantic schema (`order_id:
  int`, `lines: list[ReceiptPayloadLine]`, each with `product_id`, `quantity_received`,
  `quantity_damaged`, `expiry_date`, `lot_code`). `propose_receipt(session, actor, *, client,
  order_id, lines, reasoning) -> ActionDraft` — consumed by Task 5's MCP tool.

- [ ] **Step 1: Write the failing draft round-trip tests**

```python
# backend/tests/test_purchasing_receiving_drafts.py
"""DELIVERY_RECEIPT: propose a receipt, approve it, watch it apply."""

from datetime import date
from decimal import Decimal

import pytest

from core.actor import SystemActor
from core.enums import ClientType, PurchaseOrderStatus
from core.exceptions import ValidationError
from services import drafts as draft_queue
from services import purchasing
from services.purchasing.drafts import DELIVERY_RECEIPT, propose_receipt
from services.purchasing.orders import OrderLineInput


@pytest.fixture
def sent_order(session, product):
    supplier = purchasing.create_supplier(
        session,
        SystemActor(),
        client=ClientType.SYSTEM,
        name="Draft Receiving Supplier",
        lead_time_days=2,
        minimum_order_value=Decimal("0.00"),
    )
    order = purchasing.create_order(
        session,
        SystemActor(),
        client=ClientType.SYSTEM,
        supplier_id=supplier.id,
        lines=[OrderLineInput(product_id=product.id, quantity=50, unit_cost=Decimal("2.00"))],
    )
    return purchasing.send_order(
        session, SystemActor(), order_id=order.id, today=date(2026, 8, 27)
    )


def test_propose_receipt_creates_a_pending_draft_and_touches_nothing_else(
    session, sent_order, product
):
    draft = propose_receipt(
        session,
        SystemActor(),
        client=ClientType.MCP_AGENT,
        order_id=sent_order.id,
        lines=[
            {
                "product_id": product.id,
                "quantity_received": 40,
                "quantity_damaged": 0,
                "expiry_date": "2026-09-10",
                "lot_code": "DN-DRAFT-1",
            }
        ],
        reasoning="Dock worker said 40 of 50 cases arrived.",
    )
    assert draft.draft_type == DELIVERY_RECEIPT
    assert draft.status == "pending"

    session.refresh(sent_order)
    assert sent_order.status == PurchaseOrderStatus.SENT.value  # unchanged until approved


def test_approving_a_receipt_draft_applies_it_and_records_provenance(
    session, sent_order, product
):
    draft = propose_receipt(
        session,
        SystemActor(),
        client=ClientType.MCP_AGENT,
        order_id=sent_order.id,
        lines=[
            {
                "product_id": product.id,
                "quantity_received": 48,
                "quantity_damaged": 2,
                "expiry_date": "2026-09-10",
                "lot_code": "DN-DRAFT-2",
            }
        ],
        reasoning="Dock worker: 2 crushed, rest fine.",
    )

    approved = draft_queue.approve_draft(
        session, SystemActor(), client=ClientType.WEB_UI, draft_id=draft.id
    )
    assert approved.status == "executed"

    session.refresh(sent_order)
    assert sent_order.status == PurchaseOrderStatus.PARTIALLY_RECEIVED.value

    from core.models import CreditMemo
    from sqlalchemy import select

    memo = session.execute(
        select(CreditMemo).where(CreditMemo.purchase_order_id == sent_order.id)
    ).scalar_one()
    assert memo.source_draft_id == draft.id


def test_a_duplicate_product_line_is_refused(session, sent_order, product):
    with pytest.raises(ValidationError):
        propose_receipt(
            session,
            SystemActor(),
            client=ClientType.MCP_AGENT,
            order_id=sent_order.id,
            lines=[
                {
                    "product_id": product.id,
                    "quantity_received": 20,
                    "quantity_damaged": 0,
                    "expiry_date": "2026-09-10",
                    "lot_code": "DN-DUP-1",
                },
                {
                    "product_id": product.id,
                    "quantity_received": 20,
                    "quantity_damaged": 0,
                    "expiry_date": "2026-09-10",
                    "lot_code": "DN-DUP-2",
                },
            ],
            reasoning="Two lines, same product.",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_purchasing_receiving_drafts.py -v`
Expected: FAIL — `ImportError: cannot import name 'DELIVERY_RECEIPT'`

- [ ] **Step 3: Extend `services/purchasing/drafts.py`**

Append to the existing file (after `_create_purchase_order` and its `draft_types.register(...)`
call, which stays exactly as-is — this only adds a second registration):

```python
from datetime import date as _date  # already imported as `date` above; reuse that name instead
```

Do not add the import above — `date` is already imported at the top of this file for
`ReorderPayload.expected_date`. Instead add these imports to the existing `from services.purchasing
import orders, reorder` line and the ones above it:

```python
from services.purchasing import orders, reorder, receiving
```

Then append:

```python
# A second closed name from a closed list, exactly like SUPPLIER_REORDER above.
DELIVERY_RECEIPT = "DELIVERY_RECEIPT"


class ReceiptPayloadLine(BaseModel):
    """What arrived for one product on the order."""

    product_id: int
    quantity_received: int = Field(..., ge=0)
    quantity_damaged: int = Field(..., ge=0)
    expiry_date: date
    lot_code: str = Field(..., min_length=1, max_length=64)


class ReceiptPayload(BaseModel):
    """What a DELIVERY_RECEIPT draft carries."""

    order_id: int
    lines: list[ReceiptPayloadLine] = Field(..., min_length=1)

    @field_validator("lines")
    @classmethod
    def _one_line_per_product(
        cls, lines: list[ReceiptPayloadLine]
    ) -> list[ReceiptPayloadLine]:
        """Refuse a payload naming one product twice - the identical defect
        ReorderPayload guards against above, for the identical reason: a
        manager editing the payload on the approval screen is exactly how a
        duplicate gets in."""
        seen: set[int] = set()
        for line in lines:
            if line.product_id in seen:
                raise ValueError(
                    f"Product {line.product_id} appears more than once."
                )
            seen.add(line.product_id)
        return lines


def propose_receipt(
    session: Session,
    actor: Actor,
    *,
    client: ClientType,
    order_id: int,
    lines: list[dict],
    reasoning: str,
) -> ActionDraft:
    """Stage what arrived as a draft for a human. **Writes nothing operational.**

    Unlike propose_reorder, this always requires `reasoning` from the caller
    rather than generating a default - the dock worker's own words are the
    entire reason this feature exists, and losing them in favour of a
    templated string would defeat the point.
    """
    require_permission(actor, "draft.create")

    if not reasoning or not reasoning.strip():
        raise ValidationError("A delivery receipt draft must carry a reason.")

    # Confirms the order exists and is in `sent` before staging - a draft
    # proposing to receive an order that cannot legally be received yet is
    # noise nobody can approve.
    order = orders._get_or_raise(session, order_id)
    if order.status != "sent":
        raise ValidationError(
            f"Purchase order {order_id} is {order.status!r}, not 'sent', "
            "and cannot be received."
        )

    payload = {"order_id": order_id, "lines": lines}
    # Validate here too, before staging - the same reason ReorderPayload is
    # validated inside propose_reorder: an obviously malformed draft should
    # never reach the queue.
    ReceiptPayload.model_validate(payload)

    return draft_queue.create_draft(
        session,
        actor,
        client=client,
        draft_type=DELIVERY_RECEIPT,
        payload=payload,
        reasoning=reasoning.strip(),
        cost_at_risk=None,
        projected_recovery=None,
    )


def _apply_delivery_receipt(
    session: Session,
    actor: Actor,
    client: ClientType,
    payload: ReceiptPayload,
    draft: ActionDraft,
) -> None:
    """Runs only when a human approves. Records `source_draft_id` on every
    lot and credit memo this creates, via `receiving._apply_receipt`.

    ⚠️ Does not commit - `drafts.approve_draft` owns the transaction, same
    contract as `_create_purchase_order` above.
    """
    order = orders._get_or_raise(session, payload.order_id)
    receiving._apply_receipt(
        session,
        actor,
        client=client,
        order=order,
        lines=[
            receiving.ReceiptLineInput(
                product_id=line.product_id,
                quantity_received=line.quantity_received,
                quantity_damaged=line.quantity_damaged,
                expiry_date=line.expiry_date,
                lot_code=line.lot_code,
            )
            for line in payload.lines
        ],
        source_draft_id=draft.id,
    )


draft_types.register(
    DELIVERY_RECEIPT,
    schema=ReceiptPayload,
    handler=_apply_delivery_receipt,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_purchasing_receiving_drafts.py -v`
Expected: PASS, all three tests

- [ ] **Step 5: Export, lint, commit**

Add `propose_receipt` and `DELIVERY_RECEIPT` to `backend/services/purchasing/__init__.py`'s
imports and `__all__`, same pattern as `propose_reorder`/`SUPPLIER_REORDER`.

Run: `lint-imports` from `backend/` → expect 4 kept, 0 broken. Run the full purchasing test
directory: `pytest tests/test_purchasing_receiving.py tests/test_purchasing_receiving_drafts.py -v`

```bash
git add backend/services/purchasing/drafts.py backend/services/purchasing/__init__.py backend/tests/test_purchasing_receiving_drafts.py
git commit -m "feat(purchasing): add the DELIVERY_RECEIPT draft type"
```

---

## Task 4: HTTP routes and schemas

**Files:**
- Modify: `backend/api/schemas.py`
- Modify: `backend/api/routes/purchasing.py`
- Test: `backend/tests/test_api_purchasing_receiving.py`

**Interfaces:**
- Consumes: `services.purchasing.receive_order`, `services.purchasing.propose_receipt` (Tasks 2–3).
- Produces: `ReceiptLineCreate`, `PurchaseOrderReceive` (request schemas), `CreditMemoRead`
  (response schema), `PurchaseOrderLineRead` gains `quantity_received`/`quantity_damaged`.
  Two new routes: `POST /purchase-orders/{order_id}/receive` (direct),
  `POST /purchase-orders/{order_id}/receipt-drafts` (stages a `DELIVERY_RECEIPT`).

- [ ] **Step 1: Write the failing API tests**

```python
# backend/tests/test_api_purchasing_receiving.py
"""HTTP surface for gate 30 receiving."""

from datetime import date
from decimal import Decimal

import pytest

from core.actor import SystemActor
from core.enums import ClientType
from services import purchasing
from services.purchasing.orders import OrderLineInput


@pytest.fixture
def sent_order_id(session, product):
    supplier = purchasing.create_supplier(
        session,
        SystemActor(),
        client=ClientType.SYSTEM,
        name="API Receiving Supplier",
        lead_time_days=1,
        minimum_order_value=Decimal("0.00"),
    )
    order = purchasing.create_order(
        session,
        SystemActor(),
        client=ClientType.SYSTEM,
        supplier_id=supplier.id,
        lines=[OrderLineInput(product_id=product.id, quantity=10, unit_cost=Decimal("5.00"))],
    )
    sent = purchasing.send_order(session, SystemActor(), order_id=order.id, today=date(2026, 8, 27))
    session.commit()
    return sent.id


def test_receive_endpoint_applies_immediately(client, sent_order_id, product, auth_headers):
    response = client.post(
        f"/purchase-orders/{sent_order_id}/receive",
        json={
            "lines": [
                {
                    "product_id": product.id,
                    "quantity_received": 10,
                    "quantity_damaged": 0,
                    "expiry_date": "2026-09-15",
                    "lot_code": "DN-API-1",
                }
            ]
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "received"
    assert body["lines"][0]["quantity_received"] == 10


def test_receipt_draft_endpoint_stages_without_applying(client, sent_order_id, product, auth_headers):
    response = client.post(
        f"/purchase-orders/{sent_order_id}/receipt-drafts",
        json={
            "lines": [
                {
                    "product_id": product.id,
                    "quantity_received": 8,
                    "quantity_damaged": 0,
                    "expiry_date": "2026-09-15",
                    "lot_code": "DN-API-2",
                }
            ],
            "reasoning": "Dock worker said 8 of 10.",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
```

Check `backend/tests/conftest.py` for the exact names of the `client` and `auth_headers` (or
equivalent) fixtures used by other `test_api_*.py` files (e.g. `test_api_drafts.py`) before
assuming these names — copy whatever pattern gate 27's or gate 29's API tests already use.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_purchasing_receiving.py -v`
Expected: FAIL — 404, the routes don't exist yet

- [ ] **Step 3: Add schemas to `api/schemas.py`**

Add near the existing `PurchaseOrder*` schemas:

```python
class ReceiptLineCreate(BaseModel):
    product_id: int
    quantity_received: int = Field(..., ge=0)
    quantity_damaged: int = Field(..., ge=0)
    expiry_date: date
    lot_code: str = Field(..., min_length=1, max_length=64)


class PurchaseOrderReceive(BaseModel):
    lines: list[ReceiptLineCreate] = Field(..., min_length=1)


class ReceiptDraftCreate(BaseModel):
    lines: list[ReceiptLineCreate] = Field(..., min_length=1)
    reasoning: str = Field(..., min_length=1, max_length=2000)


class CreditMemoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_id: int
    purchase_order_id: int
    reason: str
    amount: Decimal
    status: str
    created_at: datetime
```

Update `PurchaseOrderLineRead` to add the two fields already on the model:

```python
class PurchaseOrderLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity_ordered: int
    unit_cost: Decimal
    line_total: Decimal
    quantity_received: int
    quantity_damaged: int
```

- [ ] **Step 4: Add the routes to `api/routes/purchasing.py`**

Add to the imports:
```python
from api.schemas import (
    ...,  # existing imports
    PurchaseOrderReceive,
    ReceiptDraftCreate,
)
```

Add after the existing `cancel_order` route:

```python
@router.post(
    "/purchase-orders/{order_id}/receive",
    response_model=PurchaseOrderRead,
    responses=_errors(_BAD_REQUEST, _FORBIDDEN, _NOT_FOUND, _UNPROCESSABLE),
)
def receive_order(
    session: DbSession, actor: CurrentActor, order_id: int, body: PurchaseOrderReceive
) -> PurchaseOrderRead:
    """Record what arrived. Applies immediately - see gate 30's design for
    why this door skips the draft queue while the AI door below does not."""
    from services.purchasing.receiving import ReceiptLineInput

    return purchasing.receive_order(
        session,
        actor,
        client=ClientType.WEB_UI,
        order_id=order_id,
        lines=[
            ReceiptLineInput(
                product_id=line.product_id,
                quantity_received=line.quantity_received,
                quantity_damaged=line.quantity_damaged,
                expiry_date=line.expiry_date,
                lot_code=line.lot_code,
            )
            for line in body.lines
        ],
    )


@router.post(
    "/purchase-orders/{order_id}/receipt-drafts",
    response_model=DraftRead,
    status_code=status.HTTP_201_CREATED,
    responses=_errors(_BAD_REQUEST, _FORBIDDEN, _NOT_FOUND, _UNPROCESSABLE),
)
def propose_receipt(
    session: DbSession, actor: CurrentActor, order_id: int, body: ReceiptDraftCreate
) -> DraftRead:
    """Stage what arrived for approval. No lot or credit memo is written yet."""
    return purchasing.propose_receipt(
        session,
        actor,
        client=ClientType.WEB_UI,
        order_id=order_id,
        lines=[line.model_dump(mode="json") for line in body.lines],
        reasoning=body.reasoning,
    )
```

- [ ] **Step 5: Run tests, run `lint-imports`, commit**

Run: `pytest tests/test_api_purchasing_receiving.py -v` → expect PASS
Run: `lint-imports` from `backend/` → expect 4 kept, 0 broken

```bash
git add backend/api/schemas.py backend/api/routes/purchasing.py backend/tests/test_api_purchasing_receiving.py
git commit -m "feat(purchasing): add HTTP routes for receiving and receipt drafts"
```

---

## Task 5: MCP tool and agent gating

**Files:**
- Modify: `backend/mcp_server/server.py`
- Modify: `agent/mcp_client.py`
- Modify: `agent/tests/test_tool_gating.py`
- Test: `backend/tests/test_mcp_products.py` (the file that actually holds `EXPECTED_TOOLS` — see
  gate 29's note in `docs/FEATURES-PLAN.md`: it is not `test_mcp_tools.py`, despite the name being
  the obvious guess)

**Interfaces:**
- Consumes: `services.purchasing.propose_receipt` (Task 3).
- Produces: one new MCP tool, `propose_delivery_receipt`. **No direct-receive tool is exposed to
  the agent** — matching gate 29's rule that no create/send/cancel-shaped tool reaches it. The
  agent can only ever propose; a human always presses approve.

- [ ] **Step 1: Read the existing `suggest_reorder_bundles`/`propose_reorder_order` tools in
  `backend/mcp_server/server.py` (around lines 877–940) to match their exact docstring and
  error-handling style before writing the new one.**

- [ ] **Step 2: Write the failing gating test**

In `agent/tests/test_tool_gating.py`, find the existing assertions for `propose_reorder_order`
being in `STAGING_ONLY` (gate 29 added these) and add a parallel one:

```python
def test_propose_delivery_receipt_is_staging_only():
    assert "propose_delivery_receipt" in STAGING_ONLY
    assert "propose_delivery_receipt" not in READ_ONLY
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest agent/tests/test_tool_gating.py -v` (from repo root, or `agent/` per the project's
existing agent test invocation — check `docs/CI-PLAN.md` or the agent job in `.github/workflows/ci.yml`
if unsure of the working directory)
Expected: FAIL — `AssertionError`, the tool name isn't in `STAGING_ONLY` yet

- [ ] **Step 4: Add the MCP tool in `backend/mcp_server/server.py`**

Add after `propose_reorder_order` (or after `list_purchase_orders`, matching the file's existing
ordering — suppliers/reorder/orders sections):

```python
@mcp.tool()
def propose_delivery_receipt(
    order_id: int, lines: list[dict[str, Any]], reasoning: str
) -> dict[str, Any]:
    """Stage what arrived for a sent purchase order as a proposal for a human to approve.

    Call this after the dock worker (or whoever is telling you) describes
    what showed up. Turn their words into the structured `lines` this tool
    needs - do not guess a missing number.

    Args:
        order_id: The purchase order this delivery is against. It must be
            in 'sent' status.
        lines: One entry per product that arrived, each a dict with:
            - product_id (int)
            - quantity_received (int): good units that arrived, not
              counting anything damaged
            - quantity_damaged (int): units that arrived broken/crushed/
              otherwise unsellable
            - expiry_date (str, "YYYY-MM-DD"): **required.** If the person
              describing the delivery did not mention an expiry or
              best-before date, ask them for one before calling this tool -
              never invent one.
            - lot_code: the delivery note number or any code identifying
              this specific delivery, e.g. "DN-4417"
        reasoning: Your own summary of what was said, in plain words, for
            the approving manager to read.

    This creates a proposal only. Nothing is added to stock and no credit
    is recorded until a human approves it in the approvals queue.
    """
    with _session() as session:
        draft = purchasing_service.propose_receipt(
            session,
            _actor(),
            client=ClientType.MCP_AGENT,
            order_id=order_id,
            lines=lines,
            reasoning=reasoning,
        )
        return {
            "draft_id": draft.id,
            "status": draft.status,
            "reasoning": draft.reasoning,
        }
```

Check the file's actual error-handling convention (likely a decorator or try/except around each
tool converting domain exceptions to `mcp_server/errors.py`'s vocabulary) before assuming this
bare version is complete — match whatever `propose_reorder_order` actually does at
`backend/mcp_server/server.py:908` verbatim, including any wrapping this plan's excerpt above
does not show.

- [ ] **Step 5: Add the tool name to `agent/mcp_client.py`'s `STAGING_ONLY`, run tests, lint, commit**

In `agent/mcp_client.py`, add `"propose_delivery_receipt"` to the `STAGING_ONLY` frozenset (around
line 126–138, alongside `"propose_reorder_order"`).

Run: `pytest agent/tests/test_tool_gating.py -v` → expect PASS
Run: `pytest backend/tests/test_mcp_products.py -v` (update `EXPECTED_TOOLS` there to include
`propose_delivery_receipt`, matching how gate 29 added its three tools to the same list)
Run: `lint-imports` from `backend/`

```bash
git add backend/mcp_server/server.py agent/mcp_client.py agent/tests/test_tool_gating.py backend/tests/test_mcp_products.py
git commit -m "feat(purchasing): add the propose_delivery_receipt MCP tool"
```

---

## Task 6: Frontend — receiving a sent order

**Files:**
- Create: `frontend/src/app/purchasing/orders/[id]/receive-form.tsx` (or a name matching the
  existing convention in that directory — check what's already there for gate 29's send/cancel
  actions first)
- Modify: `frontend/src/app/purchasing/orders/[id]/page.tsx`
- Modify: `frontend/src/app/purchasing/orders/[id]/actions.ts`
- Modify: `frontend/src/lib/api/schema.d.ts` (regenerated, not hand-edited — see Step 1)

**Interfaces:**
- Consumes: `POST /purchase-orders/{id}/receive` (Task 4). Existing patterns from
  `frontend/src/app/purchasing/orders/[id]/actions.ts`'s `sendOrder`/`cancelOrder` (gate 29) for
  how a server action calls the generated API client and revalidates the page.

- [ ] **Step 1: Ask the developer to run `npm run api:types` (from `frontend/`) after Task 4 is
  merged/available, to regenerate `schema.d.ts` with the two new routes and the two new response
  fields on `PurchaseOrderLineRead`.** Per this session's standing exception (the user has
  authorized running non-destructive dev-toolchain commands directly during this project), this
  may be run directly rather than only requested — confirm the exact phrasing with the user before
  assuming so if this plan is executed in a later session where that exception may not carry over.

- [ ] **Step 2: Read the existing order detail page and its actions file**

Read `frontend/src/app/purchasing/orders/[id]/page.tsx` and `actions.ts` in full before writing
anything — this task must match their existing component structure (how `sendOrder`/`cancelOrder`
buttons are wired, how errors surface, what loading state pattern is used) rather than introducing
a second style.

- [ ] **Step 3: Add a `receiveOrder` server action to `actions.ts`**, following the exact shape of
  the existing `sendOrder` action there (same error handling, same `revalidatePath` call, same
  return shape) but posting to `/purchase-orders/{id}/receive` with a `lines` array built from the
  form.

- [ ] **Step 4: Build the receiving form** — one row per order line, showing `product`,
  `quantity_ordered`, and three inputs: `quantity_received`, `quantity_damaged`, `expiry_date`
  (all three required — `expiry_date` must not submit blank, matching the design's "no default"
  rule), plus a `lot_code` text input. Only rendered when `order.status === "sent"` — matching how
  the existing Send/Cancel buttons are already conditionally shown based on status.

- [x] **Step 5: Show credit memos on the order detail page**, if any exist for this order — a
  simple list (`reason`, `amount`) below the lines table. Resolved via a Task 4b follow-up, approved
  by the developer: `PurchaseOrderRead` gained `credit_memos: list[CreditMemoRead]`, eager-loaded in
  both `_repository.get_order` and `_repository.list_orders` (the latter was missed on the first pass
  and fixed in the final whole-branch review — see gate 30's commit history).

- [ ] **Step 6: Manual browser check** — per this project's standing rule, browser MCP tools may
  only be used after the developer has started both `uvicorn` and `npm run dev` and says continue.
  Ask for that before attempting to view the page. Verify: the form only appears on a `sent`
  order, submitting it moves the order to `received` or `partially_received`, credit memos appear
  on the order detail page, and a short/damaged
  submission shows a credit memo afterward (once Step 5's gap is resolved either way).

- [ ] **Step 7: Run `tsc`/`eslint`/`next build` from `frontend/` (developer runs these), then commit**

```bash
git add frontend/src/app/purchasing/orders/ frontend/src/lib/api/schema.d.ts
git commit -m "feat(purchasing): add the delivery receiving screen"
```

---

## Task 7: Docs — close out gate 30's state of play

**Files:**
- Modify: `docs/PLAN.md`
- Modify: `docs/FEATURES-PLAN.md`

**Interfaces:** None — documentation only, following the exact pattern gate 29 used for its own
"State of play" section (`docs/FEATURES-PLAN.md` lines 376–431).

- [ ] **Step 1: Update `docs/FEATURES-PLAN.md`'s gate 30 section** with a "State of play" block
  matching gate 29's: what tables/files landed, test counts, `lint-imports` result, what remains
  (almost certainly: `purchasing.write`/`lot.write` already exist as permissions from earlier
  gates, so — unlike gates 28/29 — there may be **no new permissions gap to record here**; confirm
  this is actually true by checking whether any new permission was introduced anywhere in Tasks
  1–6, and state clearly either way rather than assuming).

- [ ] **Step 2: Update `docs/PLAN.md`'s gate 30 row** from "design approved, not built" to "code
  complete", following the exact phrasing pattern gates 27–29 used (see the current row for gate
  29 as the template).

- [ ] **Step 3: Commit**

```bash
git add docs/PLAN.md docs/FEATURES-PLAN.md
git commit -m "docs: record gate 30 as code complete"
```

---

## Self-review notes (for whoever executes this plan)

- **Task ordering matters**: Task 3 imports `receiving` from Task 2, Task 4 imports from both.
  Do not skip ahead.
- **`_apply_receipt`'s transition check** (Task 2, Step 3) deliberately only accepts an order
  currently in `sent` — per this gate's "one delivery closes the order" decision, there is no
  path back into `_apply_receipt` for an order already `partially_received`. If a future gate
  revisits multi-delivery receiving (see the design spec's "Alternatives considered"), this
  function's entry check is the first thing that has to change.
- **The two-door split by "who produced the numbers"** (form = immediate, AI = always queued) is
  gate 30's own refinement of `docs/FEATURES-PLAN.md` decision 1, not a preexisting rule — Task 7
  should make sure this refinement is legible in the docs, not just in this plan.
