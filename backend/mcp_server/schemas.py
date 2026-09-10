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
