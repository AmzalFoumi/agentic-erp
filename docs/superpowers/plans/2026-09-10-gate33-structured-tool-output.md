# Gate 33 — Structured MCP Tool-Output Contract — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every MCP tool a named Pydantic return model so the agent hands the browser real structured JSON (not a concatenated-JSON string), and generate a committed TypeScript contract the gate-34 cards compile against.

**Architecture:** Three coordinated changes. (1) `backend/mcp_server/schemas.py` (new) holds Pydantic output models mirroring today's `_describe*` dicts field-for-field; `server.py`'s helpers return those models and each `@mcp.tool()` return annotation becomes its model. (2) `agent/mcp_client.py:call_tool` returns `result.structured_content` when the SDK populated it, falling back to the current text join otherwise. (3) A new `backend/mcp_server/dump_schemas.py` writes a deterministic JSON-Schema file into the frontend tree; a new `npm run mcp:types` turns it into `mcp-types.d.ts`. Both generated files are committed. A backend pytest test regenerates the JSON-Schema in-process and diffs it against the committed copy, so drift fails CI without any npm step.

**Tech Stack:** Python 3.12, Pydantic v2 (already a backend dependency via `api/schemas.py`), `mcp==2.0.0` SDK, pytest. Frontend: one new dev dependency, a JSON-Schema→TypeScript generator (`json-schema-to-typescript` / its `json2ts` CLI is the expected choice — confirm current version and flags at implementation). Next.js 16, TypeScript 5.

**Spec:** `docs/superpowers/specs/2026-09-09-chatbot-overhaul-design.md` — section "Gate 33 — structured tool-output contract". Read it and this plan together. The spec's "Verified against the running system — 2026-09-09" block and its "Tool return shapes" table are the source of truth for the field lists.

## Global Constraints

Copied from the spec's "Hard constraints" and the Gate 33 section. Every task's requirements implicitly include these.

- **No routing changes.** No new routes, no changes to `src/proxy.ts` or `src/app/api/agent/[...path]/route.ts`.
- **No auth / permission / ThunderID changes.** No new scopes, no Console changes, no token-handling changes. **No new MCP tools** (gate 33 changes return shapes only — a new tool would raise the "which permission?" question the user has ruled out). `deploy/aisle-box/` is not touched.
- **`services/`, `core/`, `authn/`, `api/deps.py`, `api/errors.py`, and the MCP auth path (`mcp_server/auth.py`, `mcp_server/server.py`'s `_actor()`) are not modified.** Gate 33 is pure serialization/declaration in `mcp_server/` plus one agent-cluster edit.
- **MCP tool descriptions (the docstrings the model reads) are unchanged.** Only the `-> ReturnType` annotation and the helper return values change.
- **The one architecture rule holds.** `services/` never imports from `api/` or `mcp_server/`. `import-linter` must still pass (`lint-imports` from `backend/`, `lint-imports --config agent/pyproject.toml` from repo root).
- **Agent isolation cluster.** Framework types live only in `agent/`'s `conversation.py`, `model_provider.py`, `mcp_client.py`, `app.py`. Gate 33 touches only `mcp_client.py`. `store.py` / `app.py` persistence is untouched (that is gate 34).
- **Loopback binding stays.** `agent/app.py`'s `HOST = "127.0.0.1"` and `mcp_server/server.py`'s `--host 127.0.0.1` default are not touched.
- **Money is a JSON string, never a float** (`Numeric(10,2)` precision). Every money field in every model is typed `str`.
- **Frontend has no test runner.** Frontend verification is `npx tsc --noEmit` + `npm run lint` + (where the dev stack is up and the developer says continue) a chrome-devtools sanity check. Backend and agent use `pytest` and TDD applies.
- **Generated files are build output — committed, never hand-edited:** `frontend/src/lib/api/mcp-schema.json`, `frontend/src/lib/api/mcp-types.d.ts` (same rule as the existing `schema.d.ts`).
- **Developer runs `npm install`, `pip install`, `alembic`, and all `git`/`gh` commands.** The controller may run read/build commands: `pytest` (against the local `docker-compose.test.yml` Postgres), `lint-imports`, `python -m mcp_server.dump_schemas`, `npx tsc --noEmit`, `npm run lint`, `npm run build`, `npm run mcp:types`. The one new frontend dev dependency is installed by the developer (like gate 32's `npm install streamdown`).
- **Commit trailers, verbatim, on every commit:**
  ```
  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01XruycPu9FKxDpuCES3GRC6
  ```
- **Branch:** `feat/client/chatbot` (carried from gates 31–32). No worktree. Not pushed.

---

## File Structure

| File | New/Mod | Responsibility |
|---|---|---|
| `backend/mcp_server/schemas.py` | **new** | Pydantic output models mirroring `_describe*`; the `TOOL_OUTPUT_MODELS` name→model map (single source of truth for tasks 2, 3, 6). |
| `backend/mcp_server/server.py` | mod | `_describe*` helpers return models; each tool's return annotation becomes its model; list tools build the wrapper; `list_products` calls `count_products` for `total`. Docstrings unchanged. |
| `backend/mcp_server/dump_schemas.py` | **new** | `python -m mcp_server.dump_schemas` → writes `frontend/src/lib/api/mcp-schema.json` deterministically from `TOOL_OUTPUT_MODELS`. Pure introspection, no server, no DB. |
| `backend/tests/test_mcp_schemas.py` | **new** | (a) each model validates a representative dict; (b) every tool in `TOOL_OUTPUT_MODELS`, called via the `call` fixture against seeded data, produces `structured_content` that validates against its model; (c) schema-drift: regenerate the JSON-Schema in-process, assert byte-equal to the committed `mcp-schema.json`. |
| `backend/tests/test_mcp_products.py` | mod | Existing `.structured_content` assertions get slightly stronger (list tools now return `{"products": [...], "total": N}`). |
| `backend/tests/test_mcp_drafts.py` | mod | Same, for `list_pending_drafts` → `{"drafts": [...]}`. |
| `agent/mcp_client.py` | mod | Extract `_tool_output(result)` pure helper; `call_tool` uses it; module docstring line about "structured content ... we do not do" updated. |
| `agent/tests/test_tool_output.py` | **new** | Unit-test `_tool_output`: structured object returned when present; text fallback when `structured_content is None`; `ModelRetry` on `is_error`. |
| `frontend/package.json` | mod | `mcp:types`, `mcp:types:check` scripts + the generator dev dependency. |
| `frontend/src/lib/api/mcp-schema.json` | **new (generated, committed)** | The JSON-Schema contract. |
| `frontend/src/lib/api/mcp-types.d.ts` | **new (generated, committed)** | The TypeScript types the gate-34 cards import. |
| `docs/PLAN.md` | mod | Gate 33 row → done, with commit range. |
| `docs/FRONTEND-PLAN.md` | mod | Record the two generated files + the two-part drift check. |
| `docs/DEPLOY-PLAN.md` | mod | "What a new feature has to update in the box" → gate 33 owes it nothing; state so. |
| `docs/superpowers/specs/2026-09-09-chatbot-overhaul-design.md` | mod | Gate 33 status line → done. |

---

## Task 1: Output models — `backend/mcp_server/schemas.py`

**Files:**
- Create: `backend/mcp_server/schemas.py`
- Create: `backend/tests/test_mcp_schemas.py`

**Interfaces:**
- Consumes: nothing (leaf module). Imports only `pydantic`.
- Produces:
  - Row models: `ProductOut`, `LotOut`, `DraftOut`, `SpoilageItemOut`, `ReorderLineOut`, `ReorderBundleOut`, `UnsourcedOut`, `POLineOut`, `PurchaseOrderOut`.
  - Result wrappers: `ProductListOut`, `LotListOut`, `DraftListOut`, `SpoilageReportOut`, `ReorderReportOut`, `PurchaseOrderListOut`.
  - `TOOL_OUTPUT_MODELS: dict[str, type[pydantic.BaseModel]]` — every registered tool name → the model its `@mcp.tool()` return annotation will use (Task 2 must match this exactly; Task 3 and Task 6 iterate it).

**Field lists** — mirror `mcp_server/server.py`'s `_describe*` helpers exactly (read them; the spec's "Tool return shapes" table is the cross-check). Money fields (`cost_price`, `sell_price`, `total_value`, `minimum_order_value`, `bundle_value`, `shortfall`, `unit_cost`, `line_total`, `current_price`, `proposed_price`, `cost_at_risk`, `projected_recovery`, `total_cost_at_risk`, `total_projected_recovery`) are `str`. Nullable stays nullable (`expiry_date: str | None`, `category: str | None`, `updated_by: str | None`, `notes: str | None`, `source_draft_id: int | None`, `decided_by: str | None`, `decided_via: str | None`, `cost_at_risk: str | None`, `projected_recovery: str | None`, `expires_at: str | None`). `DraftOut.payload` is `dict[str, Any]` with a docstring saying it is polymorphic by `draft_type` (spec finding 10) and the gate-34 card switches on that at runtime.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_mcp_schemas.py`:

```python
"""Gate 33: the MCP tool-output models mirror what the tools actually return.

Two layers of check live here:
  - each model accepts a representative dict (fast, no DB) - this file, below
  - every real tool call's `structured_content` validates against its model
    (test_mcp_products.py / a fixture-backed test in Task 2)
  - the generated JSON-Schema matches the committed copy (Task 3)
"""

import pytest

from mcp_server.schemas import (
    DraftListOut,
    DraftOut,
    LotListOut,
    LotOut,
    ProductListOut,
    ProductOut,
    PurchaseOrderListOut,
    ReorderReportOut,
    SpoilageReportOut,
    TOOL_OUTPUT_MODELS,
)

_PRODUCT = {
    "id": 143, "sku": "2002-1001", "name": "Full Cream Milk 1L",
    "category": "Dairy", "unit": "piece", "cost_price": "380.00",
    "sell_price": "450.00", "quantity_on_hand": 12, "reorder_level": 6,
    "needs_reorder": False, "updated_by": "01a02d8f-0000-0000-0000-000000000000",
}


def test_product_out_accepts_a_representative_row():
    model = ProductOut.model_validate(_PRODUCT)
    assert model.cost_price == "380.00"
    assert isinstance(model.cost_price, str)


def test_product_list_out_wraps_rows_and_a_total():
    model = ProductListOut.model_validate({"products": [_PRODUCT], "total": 47})
    assert model.total == 47
    assert model.products[0].sku == "2002-1001"


def test_money_is_never_coerced_to_a_number():
    # A model that typed cost_price as float would accept 380.0 here and the
    # precision guarantee would be gone.
    with pytest.raises(Exception):
        ProductOut.model_validate({**_PRODUCT, "cost_price": 380.0})


def test_tool_output_models_map_covers_every_registered_tool():
    import anyio
    from mcp_server import server as mcp_server

    registered = {t.name for t in anyio.run(mcp_server.mcp.list_tools)}
    assert set(TOOL_OUTPUT_MODELS) == registered
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_mcp_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcp_server.schemas'`.

- [ ] **Step 3: Write `backend/mcp_server/schemas.py`**

```python
"""Pydantic output models for the MCP tools. Gate 33.

The MCP counterpart of `api/schemas.py`: the boundary where an internal object
becomes an external contract. Until gate 33 the tools were typed `-> dict[str,
Any]`, which the `mcp` SDK turns into structured output with a useless schema
("some object", no field names). These named models give:

  - a real JSON Schema to generate `frontend/src/lib/api/mcp-types.d.ts` from
  - a drift check: rename a field here without regenerating and CI fails

They mirror `mcp_server/server.py`'s `_describe*` helpers field-for-field. Keep
them in lockstep - a field added to `_describe` and not here means the model
rejects a real tool result, which `tests/test_mcp_schemas.py` catches.

Money is `str`, never `float` - 19.99 has no exact float64 form and a system
that reports prices does not get to lose that. Same rule as `_describe`,
`api/schemas.py`, and every other boundary in this codebase.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    # `strict=False` for ints (JSON numbers) but no float->str coercion: a money
    # field declared `str` rejects `380.0`, which is the guarantee we want.
    model_config = ConfigDict(extra="forbid")


class ProductOut(_Strict):
    id: int
    sku: str
    name: str
    category: str | None
    unit: str
    cost_price: str
    sell_price: str
    quantity_on_hand: int
    reorder_level: int
    needs_reorder: bool
    updated_by: str | None


class ProductListOut(_Strict):
    products: list[ProductOut]
    total: int


class LotOut(_Strict):
    lot_id: int
    product_id: int
    lot_code: str
    expiry_date: str | None
    quantity: int
    cost_price: str
    sell_price: str
    discount_percent: int
    is_expired: bool


class LotListOut(_Strict):
    lots: list[LotOut]


class DraftOut(_Strict):
    id: int
    draft_type: str
    status: str
    # Polymorphic by `draft_type` (spec finding 10): SUPPLIER_REORDER carries
    # {supplier_id, expected_date, lines:[{product_id, quantity, unit_cost}]};
    # BATCH_PRICE_MARKDOWN carries {lines:[{lot_id, product_id, new_price}]}.
    # A discriminated union is a later refinement; the gate-34 card switches on
    # `draft_type` at runtime.
    payload: dict[str, Any]
    reasoning: str
    cost_at_risk: str | None
    projected_recovery: str | None
    expires_at: str | None
    is_expired: bool
    created_by: str | None
    created_via: str
    decided_by: str | None
    decided_via: str | None


class DraftListOut(_Strict):
    drafts: list[DraftOut]


class SpoilageItemOut(_Strict):
    lot_id: int
    product_id: int
    sku: str
    product_name: str
    lot_code: str
    expiry_date: str
    days_remaining: int
    quantity: int
    current_price: str
    proposed_price: str
    discount_percent: int
    why: str
    cost_at_risk: str
    projected_recovery: str


class SpoilageReportOut(_Strict):
    scanned_on: str
    within_days: int
    total_cost_at_risk: str
    total_projected_recovery: str
    items: list[SpoilageItemOut]


class ReorderLineOut(_Strict):
    product_id: int
    sku: str
    name: str
    quantity_on_hand: int
    reorder_level: int
    quantity: int
    unit_cost: str
    pack_size: int
    line_total: str
    is_top_up: bool


class ReorderBundleOut(_Strict):
    supplier_id: int
    supplier_name: str
    lead_time_days: int
    minimum_order_value: str
    bundle_value: str
    below_minimum: bool
    shortfall: str
    lines: list[ReorderLineOut]


class UnsourcedOut(_Strict):
    product_id: int
    sku: str
    name: str
    quantity_on_hand: int
    reorder_level: int


class ReorderReportOut(_Strict):
    total_value: str
    bundles: list[ReorderBundleOut]
    unsourced: list[UnsourcedOut]


class POLineOut(_Strict):
    product_id: int
    quantity_ordered: int
    unit_cost: str
    line_total: str


class PurchaseOrderOut(_Strict):
    id: int
    supplier_id: int
    status: str
    expected_date: str | None
    total_value: str
    notes: str | None
    source_draft_id: int | None
    created_by: str | None
    lines: list[POLineOut]


class PurchaseOrderListOut(_Strict):
    orders: list[PurchaseOrderOut]
    total: int


# Every registered @mcp.tool() -> the model its return annotation uses.
# Task 2 must make server.py match this exactly; test_mcp_schemas.py asserts
# the key set equals the set of registered tool names.
TOOL_OUTPUT_MODELS: dict[str, type[BaseModel]] = {
    "list_products": ProductListOut,
    "get_product": ProductOut,
    "get_product_by_sku": ProductOut,
    "create_product": ProductOut,
    "update_product": ProductOut,
    "adjust_stock": ProductOut,
    "check_spoilage_risk": SpoilageReportOut,
    "propose_spoilage_markdown": DraftOut,
    "list_product_lots": LotListOut,
    "receive_stock_lot": LotOut,
    "suggest_reorder_bundles": ReorderReportOut,
    "propose_reorder_order": DraftOut,
    "list_purchase_orders": PurchaseOrderListOut,
    "propose_delivery_receipt": DraftOut,
    "create_action_draft": DraftOut,
    "list_pending_drafts": DraftListOut,
}
```

**Note for the implementer:** the field *types* above (`discount_percent: int`, `pack_size: int`, `status: str`, enum-ish fields) are best-effort from reading `_describe*`. If Task 2's fixture-backed test (a real tool result validated against the model) rejects a real value, adjust the type here to match what `_describe` actually emits — a str-valued enum stays `str`, a `Decimal` percent becomes `str`. Record any such change in your report.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && pytest tests/test_mcp_schemas.py -v`
Expected: PASS — 4 tests. (`test_tool_output_models_map_covers_every_registered_tool` passes because the map lists exactly the 16 registered tools.)

- [ ] **Step 5: Check architecture boundary**

Run: `cd backend && lint-imports`
Expected: PASS — `schemas.py` imports only `pydantic`, forbidden to nobody.

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/schemas.py backend/tests/test_mcp_schemas.py
git commit -m "feat(mcp): add Pydantic output models for every tool (gate 33)

<trailers>"
```

---

## Task 2: Wire the models into `server.py`

**Files:**
- Modify: `backend/mcp_server/server.py` — `_describe`, `_describe_lot`, `_describe_draft`, `_describe_spoilage`, `_describe_reorder`, `_describe_order`, and every `@mcp.tool()` return annotation + the list-tool bodies.
- Modify: `backend/tests/test_mcp_products.py`, `backend/tests/test_mcp_drafts.py` — assertions for the new list-wrapper shape.
- Modify: `backend/tests/test_mcp_schemas.py` — add the fixture-backed "real result validates" test.

**Interfaces:**
- Consumes: every model + `TOOL_OUTPUT_MODELS` from `mcp_server.schemas` (Task 1).
- Produces: after this task, `mcp.call_tool(name, args).structured_content` for every tool is a dict that `TOOL_OUTPUT_MODELS[name].model_validate(...)` accepts. List tools: `list_products` → `{"products": [...], "total": int}`, `list_product_lots` → `{"lots": [...]}`, `list_pending_drafts` → `{"drafts": [...]}`, `list_purchase_orders` → unchanged `{"orders": [...], "total": int}`.

- [ ] **Step 1: Write the failing test** — add to `backend/tests/test_mcp_schemas.py`:

```python
def test_every_tool_result_validates_against_its_model(call, unique_sku):
    """The real contract check: a live tool call's structured_content is exactly
    what its model declares. This is what catches a field-type guess in
    schemas.py being wrong against reality."""
    from mcp_server.schemas import ProductOut, ProductListOut

    created = call("create_product", sku=unique_sku, name="Rice 1kg").structured_content
    ProductOut.model_validate(created)  # raises on any mismatch

    listed = call("list_products").structured_content
    parsed = ProductListOut.model_validate(listed)
    assert parsed.total >= 1
    assert any(p.sku == unique_sku for p in parsed.products)
```

Add the same shape for a lot (`receive_stock_lot` then `list_product_lots` → `LotListOut`) and a draft (`create_action_draft` then `list_pending_drafts` → `DraftListOut`) — copy the pattern, don't reference it. Use the existing fixtures in `conftest.py` / the sibling test files for seeding (`unique_sku`, `call`).

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_mcp_schemas.py::test_every_tool_result_validates_against_its_model -v`
Expected: FAIL — `list_products` currently returns a bare list, so `ProductListOut.model_validate` gets a list and raises.

- [ ] **Step 3: Edit `server.py`**

3a. Import at the top (after the existing `from services import ...` block):

```python
from mcp_server.schemas import (
    DraftListOut,
    DraftOut,
    LotListOut,
    LotOut,
    POLineOut,
    ProductListOut,
    ProductOut,
    PurchaseOrderListOut,
    PurchaseOrderOut,
    ReorderBundleOut,
    ReorderLineOut,
    ReorderReportOut,
    SpoilageItemOut,
    SpoilageReportOut,
    UnsourcedOut,
)
```

3b. Each `_describe*` helper: keep the exact dict it builds today, and return the model built from it. Minimal-diff form — wrap the existing `return { ... }` as `return ProductOut(**{ ... })`. Example for `_describe`:

```python
def _describe(product: Product) -> ProductOut:
    """... (docstring unchanged) ..."""
    return ProductOut(
        id=product.id,
        sku=product.sku,
        name=product.name,
        category=product.category,
        unit=product.unit,
        cost_price=str(product.cost_price),
        sell_price=str(product.sell_price),
        quantity_on_hand=product.quantity_on_hand,
        reorder_level=product.reorder_level,
        needs_reorder=product.needs_reorder,
        updated_by=product.updated_by,
    )
```

Do the same for `_describe_lot -> LotOut`, `_describe_draft -> DraftOut`, `_describe_spoilage -> SpoilageReportOut` (nested `items` become `SpoilageItemOut(...)`), `_describe_reorder -> ReorderReportOut` (nested `bundles`→`ReorderBundleOut`, its `lines`→`ReorderLineOut`, `unsourced`→`UnsourcedOut(**item)`), `_describe_order -> PurchaseOrderOut` (nested `lines`→`POLineOut`).

3c. Every `@mcp.tool()` function: change `-> dict[str, Any]` / `-> list[dict[str, Any]]` to the model from `TOOL_OUTPUT_MODELS`. **Docstrings unchanged.**

3d. The three bare-list tools build the wrapper:

```python
@mcp.tool()
@translated
def list_products(search: str | None = None, limit: int = 50, offset: int = 0) -> ProductListOut:
    """... (docstring unchanged) ..."""
    with get_session() as session:
        actor = _actor()
        found = product_service.list_products(session, actor, search=search, limit=limit, offset=offset)
        total = product_service.count_products(session, actor, search=search)
        return ProductListOut(products=[_describe(p) for p in found], total=total)
```

```python
@mcp.tool()
@translated
def list_product_lots(product_id: int) -> LotListOut:
    """... (docstring unchanged) ..."""
    with get_session() as session:
        lots = lot_service.list_lots(session, _actor(), product_id=product_id)
        return LotListOut(lots=[_describe_lot(lot) for lot in lots])
```

```python
@mcp.tool()
@translated
def list_pending_drafts(limit: int = 20) -> DraftListOut:
    """... (docstring unchanged) ..."""
    with get_session() as session:
        drafts = draft_service.list_drafts(session, _actor(), status=DraftStatus.PENDING, limit=limit)
        return DraftListOut(drafts=[_describe_draft(d) for d in drafts])
```

`list_purchase_orders` keeps its shape but returns the model:

```python
        return PurchaseOrderListOut(
            orders=[_describe_order(order) for order in orders],
            total=total,
        )
```

`_actor()` note: `list_products` now calls `_actor()` once and reuses it (two service calls). Do not call `_actor()` twice — it is cheap but calling once is clearer and matches the pattern.

3e. `from typing import Any` may become unused in `server.py` if no annotation references it — check and remove the import if so (lint will flag it). `date` / `Decimal` are still used.

- [ ] **Step 4: Run the tests**

Run: `cd backend && pytest tests/test_mcp_schemas.py tests/test_mcp_products.py tests/test_mcp_drafts.py tests/test_mcp_auth.py -v`
Expected: `test_mcp_schemas.py` all PASS. `test_mcp_products.py` / `test_mcp_drafts.py`: the `.structured_content` reads that expected a bare list now need the wrapper key — fix those assertions (`call("list_products").structured_content["products"]`, `["total"]`; `call("list_pending_drafts").structured_content["drafts"]`). Everything else passes unchanged. `test_mcp_auth.py` untouched — must stay green (proves the auth path did not move).

- [ ] **Step 5: Full backend suite + boundary**

Run: `cd backend && pytest && lint-imports`
Expected: PASS. (If `pytest` needs the local Postgres: `docker compose -f docker-compose.test.yml up -d` first, per `backend/tests/README.md`.)

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/server.py backend/tests/test_mcp_schemas.py backend/tests/test_mcp_products.py backend/tests/test_mcp_drafts.py
git commit -m "feat(mcp): tools return named models; list tools gain a wrapper (gate 33)

<trailers>"
```

---

## Task 3: Schema-dump script + committed `mcp-schema.json`

**Files:**
- Create: `backend/mcp_server/dump_schemas.py`
- Create: `frontend/src/lib/api/mcp-schema.json` (generated, committed)
- Modify: `backend/tests/test_mcp_schemas.py` — the drift test.

**Interfaces:**
- Consumes: `TOOL_OUTPUT_MODELS` from `mcp_server.schemas`.
- Produces: `python -m mcp_server.dump_schemas` writes `frontend/src/lib/api/mcp-schema.json`. Deterministic (sorted keys, trailing newline, 2-space indent) so `git diff --exit-code` is a valid drift check. `dump_schemas.build_document() -> dict` is importable for the in-process test.

- [ ] **Step 1: Write the failing test** — add to `backend/tests/test_mcp_schemas.py`:

```python
import json
from pathlib import Path

_COMMITTED = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "lib" / "api" / "mcp-schema.json"
)


def test_committed_schema_matches_the_models():
    """Rename a field in schemas.py without running `python -m
    mcp_server.dump_schemas` and this fails - the frontend types would be stale.
    Fix: regenerate and commit the result."""
    from mcp_server.dump_schemas import render

    on_disk = _COMMITTED.read_text(encoding="utf-8")
    regenerated = render()
    assert on_disk == regenerated, (
        "mcp-schema.json is out of date - run `python -m mcp_server.dump_schemas` "
        "from backend/ and commit frontend/src/lib/api/mcp-schema.json"
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && pytest tests/test_mcp_schemas.py::test_committed_schema_matches_the_models -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcp_server.dump_schemas'` (and the file does not exist yet).

- [ ] **Step 3: Write `backend/mcp_server/dump_schemas.py`**

```python
"""Emit the MCP tool-output JSON Schema the frontend generates types from.

    python -m mcp_server.dump_schemas

writes `frontend/src/lib/api/mcp-schema.json` - one document, every tool-output
model under `$defs`, and a top-level object whose properties map each tool name
to a `$ref`. `npm run mcp:types` (frontend) turns that into `mcp-types.d.ts`.

Pure model introspection: no server, no database, no auth. The counterpart of
`npm run api:types` for the REST client, except the source is Pydantic models
rather than a running FastAPI's /openapi.json - so this runs anywhere, and the
drift check is a plain file diff instead of "boot a server first".

Deterministic output (sorted keys, 2-space indent, trailing newline) so
`git diff --exit-code` on the committed file is a valid CI check.
`tests/test_mcp_schemas.py::test_committed_schema_matches_the_models` is the
same check inside pytest, so it runs in CI's existing backend job with no npm.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic.json_schema import GenerateJsonSchema, models_json_schema

from mcp_server.schemas import TOOL_OUTPUT_MODELS

_TARGET = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "lib" / "api" / "mcp-schema.json"
)


def build_document() -> dict:
    """The schema document, as a dict. One `$defs` block shared by all tools."""
    models = [(m, "validation") for m in dict.fromkeys(TOOL_OUTPUT_MODELS.values())]
    defs_by_model, top = models_json_schema(
        models, ref_template="#/$defs/{model}"
    )
    # `top` holds {"$defs": {...}}. Build a stable properties map name -> $ref.
    properties = {
        name: defs_by_model[(model, "validation")]
        for name, model in sorted(TOOL_OUTPUT_MODELS.items())
    }
    return {
        "$schema": GenerateJsonSchema.schema_dialect,
        "title": "MCPToolOutputs",
        "description": "Generated by backend/mcp_server/dump_schemas.py - do not edit.",
        "type": "object",
        "properties": properties,
        "required": sorted(TOOL_OUTPUT_MODELS),
        "additionalProperties": False,
        "$defs": top.get("$defs", {}),
    }


def render() -> str:
    """The exact bytes written to disk (and compared in the drift test)."""
    return json.dumps(build_document(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    _TARGET.write_text(render(), encoding="utf-8")
    print(f"wrote {_TARGET}")


if __name__ == "__main__":
    main()
```

**Implementer note (verify-docs):** Pydantic v2's `models_json_schema` signature and return shape must be confirmed against the installed Pydantic version (`pip show pydantic` in `backend/`). The intent is fixed — one document, shared `$defs`, a name→schema map, deterministic bytes. If `models_json_schema`'s return tuple differs, adjust `build_document` to produce that same document. The drift test pins the output; `test_every_tool_result_validates_against_its_model` pins correctness.

- [ ] **Step 4: Generate the file**

Run: `cd backend && python -m mcp_server.dump_schemas`
Expected: prints `wrote .../frontend/src/lib/api/mcp-schema.json`; the file now exists.

- [ ] **Step 5: Run the drift test**

Run: `cd backend && pytest tests/test_mcp_schemas.py -v`
Expected: all PASS, including `test_committed_schema_matches_the_models`.

- [ ] **Step 6: Sanity-check the file by eye**

Open `frontend/src/lib/api/mcp-schema.json`. Confirm: `$defs` has `ProductOut`, `DraftOut`, `LotOut`, etc.; `properties.list_products` is a `$ref` to `ProductListOut`; money fields show `"type": "string"` (never `"number"`).

- [ ] **Step 7: Commit**

```bash
git add backend/mcp_server/dump_schemas.py backend/tests/test_mcp_schemas.py frontend/src/lib/api/mcp-schema.json
git commit -m "feat(mcp): dump tool-output JSON Schema to the frontend tree (gate 33)

<trailers>"
```

---

## Task 4: Agent — `call_tool` prefers `structured_content`

**Files:**
- Modify: `agent/mcp_client.py` — extract `_tool_output`; `call_tool` uses it; module docstring line updated.
- Create: `agent/tests/test_tool_output.py`

**Interfaces:**
- Consumes: nothing new. `_tool_output` takes the object returned by `mcp.client.Client.call_tool` (has `.content: list[block]`, `.is_error: bool`, `.structured_content: dict | None`).
- Produces: `_tool_output(result) -> Any` — returns `result.structured_content` when it is not `None`; else the joined text of `result.content`; raises `pydantic_ai.ModelRetry` when `result.is_error`.

- [ ] **Step 1: Write the failing test** — `agent/tests/test_tool_output.py`:

```python
"""Gate 33: the toolset hands the model structured output when the server sent it.

Before gate 33 `call_tool` did `"\\n".join(block.text ...)` over the *unstructured*
content blocks and dropped `structured_content` entirely - which is why a list
tool arrived at the browser as `}\\n{`-concatenated JSON text instead of an array.
`_tool_output` is that logic, pulled out so it can be tested without a live MCP
server (the same move `tool_kind` made for the approval rule)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_client import _tool_output  # noqa: E402
from pydantic_ai import ModelRetry  # noqa: E402


class _Block:
    def __init__(self, text):
        self.text = text


class _Result:
    def __init__(self, *, content=(), is_error=False, structured_content=None):
        self.content = list(content)
        self.is_error = is_error
        self.structured_content = structured_content


def test_structured_content_is_returned_verbatim_when_present():
    payload = {"products": [{"sku": "RICE-1KG"}], "total": 1}
    result = _Result(content=[_Block('{"products": [...]}')], structured_content=payload)
    assert _tool_output(result) is payload


def test_falls_back_to_joined_text_when_no_structured_content():
    result = _Result(content=[_Block("line one"), _Block("line two")])
    assert _tool_output(result) == "line one\nline two"


def test_an_error_result_raises_model_retry_with_the_text():
    result = _Result(content=[_Block("no product has that SKU")], is_error=True)
    with pytest.raises(ModelRetry, match="no product has that SKU"):
        _tool_output(result)


def test_an_error_result_with_no_text_still_raises():
    result = _Result(is_error=True)
    with pytest.raises(ModelRetry):
        _tool_output(result)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd agent && pytest tests/test_tool_output.py -v`
Expected: FAIL — `ImportError: cannot import name '_tool_output'`.

- [ ] **Step 3: Edit `agent/mcp_client.py`**

3a. Add the helper above the `ErpToolset` class (module level, near `tool_kind` / `normalise_tool_schema`):

```python
def _tool_output(result: Any) -> Any:
    """What the model should see for one tool call.

    Gate 33: prefer `structured_content`. The `mcp` SDK builds it from each
    tool's Pydantic return model (backend/mcp_server/schemas.py), so a list tool
    arrives as a real array/object rather than the `}\n{`-concatenated text that
    `result.content` carries for backwards compatibility. The text join stays as
    the fallback for any tool with no output model - `structured_content` is
    `None` then, and the unstructured blocks are all there is.

    `mcp_server/errors.py` reports a domain failure ("no product has that SKU")
    as `is_error=True` with human-readable text, never a protocol error.
    `ModelRetry` is how that reaches the model in Pydantic AI; `max_retries`
    (set in `get_tools`) stops a loop.
    """
    text = "\n".join(
        block.text for block in result.content if getattr(block, "text", None)
    )
    if result.is_error:
        raise ModelRetry(text or "Tool returned an error")
    if result.structured_content is not None:
        return result.structured_content
    return text
```

3b. `call_tool` body becomes:

```python
        result = await self._connected.call_tool(name, tool_args)
        try:
            return _tool_output(result)
        except ModelRetry as exc:
            # Re-raise with the tool name, which _tool_output does not have.
            raise ModelRetry(str(exc) or f"Tool {name!r} returned an error") from exc
```

Keep the existing long comment block in `call_tool` about "No approval check on this line" and the `ModelRetry` / `max_retries` rationale — move the parts about the text join into `_tool_output`'s docstring, leave the approval-check paragraph where it is.

3c. Module docstring: the paragraph beginning "**What that decision costs, plainly.**" lists "structured content" among "result mapping we do not do". Change that clause to note gate 33 added `structured_content` preference in `_tool_output` (still no task support, still no full result mapping).

- [ ] **Step 4: Run the tests**

Run: `cd agent && pytest tests/test_tool_output.py tests/test_mcp_client.py tests/test_approval.py tests/test_tool_gating.py -v`
Expected: `test_tool_output.py` all PASS; the others unchanged and green.

- [ ] **Step 5: Full agent suite + boundary**

Run: `cd agent && pytest && cd .. && lint-imports --config agent/pyproject.toml`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent/mcp_client.py agent/tests/test_tool_output.py
git commit -m "feat(agent): call_tool returns structured_content when present (gate 33)

<trailers>"
```

---

## Task 5: Frontend type generation

**Files:**
- Modify: `frontend/package.json` — 2 scripts + 1 dev dependency.
- Create: `frontend/src/lib/api/mcp-types.d.ts` (generated, committed).

**Interfaces:**
- Consumes: `frontend/src/lib/api/mcp-schema.json` (Task 3).
- Produces: `frontend/src/lib/api/mcp-types.d.ts` — a TypeScript interface per model in `$defs` plus the `MCPToolOutputs` root. Gate-34 cards import from here.

- [ ] **Step 1: Add the scripts + dependency to `package.json`**

```json
    "api:types:check": "npm run api:types && git diff --exit-code -- src/lib/api/schema.d.ts",
    "mcp:types": "json2ts src/lib/api/mcp-schema.json -o src/lib/api/mcp-types.d.ts --additionalProperties false --style.singleQuote false",
    "mcp:types:check": "npm run mcp:types && git diff --exit-code -- src/lib/api/mcp-types.d.ts"
```

and under `devDependencies`:

```json
    "json-schema-to-typescript": "^15.0.4",
```

**Implementer note (verify-docs):** confirm the current `json-schema-to-typescript` version and that its `json2ts` CLI accepts these flags (`-o`, `--additionalProperties`, `--style.*`). Newer major versions have changed the CLI flag surface. If the flags differ, match the intent: read `mcp-schema.json`, emit one `.d.ts`, no `[k: string]: unknown` index signatures on our closed models, stable formatting. If a small wrapper script (`scripts/gen-mcp-types.mjs` calling the library's `compileFromFile`) is cleaner than the CLI, do that instead and point `mcp:types` at it.

- [ ] **Step 2: Developer installs the dependency**

Hand off: **"Run `npm install` in `frontend/` — it adds `json-schema-to-typescript` as a dev dependency (a build-time tool that turns the JSON Schema into TypeScript types; it ships no runtime code)."** Wait for confirmation before Step 3.

- [ ] **Step 3: Generate the types**

Run: `cd frontend && npm run mcp:types`
Expected: creates `src/lib/api/mcp-types.d.ts`.

- [ ] **Step 4: Verify it typechecks and lints**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: EXIT 0 both. If `tsc` complains the file is unused — it is, until gate 34. That is fine; a `.d.ts` with only `export`ed types and no importer does not error. If lint's restricted-import rule flags the new file's location: `src/lib/api/` is the allowed home (it already holds `schema.d.ts`), so this should pass; if not, the file is fine and the rule needs the same allowance `schema.d.ts` has — check `eslint.config.*`.

- [ ] **Step 5: Eyeball `mcp-types.d.ts`**

Confirm: `ProductOut` has `cost_price: string` (not `number`); `ProductListOut` has `products: ProductOut[]` and `total: number`; `DraftOut.payload` is `{ [k: string]: unknown }` or similar (the deliberate loose field).

- [ ] **Step 6: Drift check**

Run: `cd frontend && npm run mcp:types:check`
Expected: EXIT 0 (no diff — the file was just generated and committed-to-be).

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/lib/api/mcp-types.d.ts
git commit -m "feat(frontend): generate mcp-types.d.ts from mcp-schema.json (gate 33)

<trailers>"
```

---

## Task 6: Docs + regression sanity check

**Files:**
- Modify: `docs/PLAN.md` (gate 33 row), `docs/FRONTEND-PLAN.md`, `docs/DEPLOY-PLAN.md`, `docs/superpowers/specs/2026-09-09-chatbot-overhaul-design.md` (status line).

**Interfaces:** none (documentation).

- [ ] **Step 1: `docs/PLAN.md`** — gate 33 row: change status from `⬜ not started` to `✅ done 2026-09-10 (\`<first>..<last>\`)` with a one-cell summary: "MCP tools return named Pydantic models (`mcp_server/schemas.py`); `agent/mcp_client.py` prefers `structured_content`; `frontend/src/lib/api/mcp-schema.json` + `mcp-types.d.ts` generated + drift-checked in pytest. No `services/`/`authn/`/auth-path/ThunderID change; no new tools." Fill the commit range from `git log --oneline` for this task sequence.

- [ ] **Step 2: `docs/FRONTEND-PLAN.md`** — add an "Amended 2026-09-10 (Gate 33)" note: two new generated-and-committed files under `src/lib/api/` (`mcp-schema.json` from `python -m mcp_server.dump_schemas`, `mcp-types.d.ts` from `npm run mcp:types`); the drift check has two halves — `test_mcp_schemas.py::test_committed_schema_matches_the_models` in the backend pytest job guards the JSON Schema, and `npm run mcp:types:check` guards the `.d.ts` locally (not yet in CI, same status as `api:types:check`); `json-schema-to-typescript` is a build-time dev dependency, no runtime code. Note the gate-34 cards will import from `mcp-types.d.ts`.

- [ ] **Step 3: `docs/DEPLOY-PLAN.md`** — in "What a new feature has to update in the box", add a line: "Gate 33 (structured tool-output contract): **nothing.** No new permission, no new setting, no migration — it changes only the JSON shape MCP tools return."

- [ ] **Step 4: spec status line** — `docs/superpowers/specs/2026-09-09-chatbot-overhaul-design.md`, the Status blockquote: mark gate 33 complete with the commit range; note gate 34 is next and depends on this.

- [ ] **Step 5: Regression sanity check (only if the dev stack is up and the developer says continue)**

The gate-34 cards do not exist yet, so there is nothing new to *see* — this step only confirms gate 33 did not break the existing raw rendering. With `uvicorn` (api :8000), the MCP server (:8001), the agent (:8002), the frontend (:3000), and ThunderID (:8090) all up, signed in as `amzal`:
  - Ask the chat "list all products". Confirm: a normal answer streams, no error card, console clean.
  - In chrome-devtools, capture the SSE for that turn (`POST /api/agent/conversations/{id}/turns`). Confirm the `tool-output-available` frame's `output` is now a JSON **object** `{"products":[...],"total":N}` — not a string of concatenated objects. This is the gate's observable win.
  - If the dev stack is not up, skip this step and note it in the report; the pytest coverage (Task 2 + Task 4) is the real gate.

- [ ] **Step 6: Commit**

```bash
git add docs/PLAN.md docs/FRONTEND-PLAN.md docs/DEPLOY-PLAN.md docs/superpowers/specs/2026-09-09-chatbot-overhaul-design.md
git commit -m "docs: mark gate 33 (structured tool-output contract) done

<trailers>"
```

---

## Self-Review

**1. Spec coverage:**

| Spec requirement (Gate 33 section) | Task |
|---|---|
| Named Pydantic models replace `dict`/`list[dict]` hints | 1, 2 |
| Q1: `list_products` → `{products, total}` via existing `count_products`; lots/drafts → single named field; `list_purchase_orders` unchanged | 2 |
| Q2: offline `dump_schemas.py` → committed `mcp-schema.json`; `npm run mcp:types` → `mcp-types.d.ts`; two-part drift check | 3, 5 |
| Q3: type the shared `_describe*` helpers → write/proposal tools covered too; all ~15 outputs get models + TS | 1, 2, 3, 5 |
| Agent `call_tool` prefers `structured_content` | 4 |
| `DraftOut.payload` stays loose, documented | 1 |
| No `services/`/`core/`/`authn/`/auth-path change; no new tools; descriptions unchanged | Global Constraints; enforced by `test_mcp_auth.py` staying green (2) + `lint-imports` (1, 2, 4) |
| Owes the box nothing — stated in DEPLOY-PLAN | 6 |
| Tests: `structured_content` validates against model; existing MCP tests pass; drift fails on a deliberate change | 2 (`test_every_tool_result_validates_against_its_model`), 3 (`test_committed_schema_matches_the_models`) |
| Deferred items survive compaction | in the spec (committed) + this plan + memory update (controller, at plan close) |

No gaps.

**2. Placeholder scan:** The two `<trailers>` markers in commit messages are the literal trailer block from Global Constraints — expand them when committing. The two "Implementer note (verify-docs)" blocks (Task 3 Pydantic API, Task 5 `json2ts` CLI) are the project's mandatory verify-against-current-docs rule, not deferred design — the intent and the output contract are fully specified; only the exact library call surface is to be confirmed. No other placeholders.

**3. Type consistency:** `TOOL_OUTPUT_MODELS` (Task 1) is the single source of truth; Task 2 matches `server.py` annotations to it (asserted by `test_tool_output_models_map_covers_every_registered_tool`), Task 3 iterates it, Task 5 consumes its rendered schema. `_tool_output` (Task 4) signature is consistent between its definition and its test. Model names are identical across tasks 1/2/3. `render()` (Task 3) is the name used by both `main()` and the drift test.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-09-10-gate33-structured-tool-output.md`.**

Per this session's decision: the user will compact the chat first, then execution runs **subagent-driven** (superpowers:subagent-driven-development) — fresh implementer per task, task review (spec + quality) after each, whole-branch review at the end. The controller runs the read/build commands listed in Global Constraints itself; `npm install` (Task 5 Step 2) is the one developer hand-off.
