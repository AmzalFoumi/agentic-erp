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
