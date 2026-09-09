"""Gate 33: the MCP tool-output models mirror what the tools actually return.

Two layers of check live here:
  - each model accepts a representative dict (fast, no DB) - this file, below
  - every real tool call's `structured_content` validates against its model
    (test_mcp_products.py / a fixture-backed test in Task 2)
  - the generated JSON-Schema matches the committed copy (Task 3)
"""

from contextlib import contextmanager
from pathlib import Path

import anyio
import pytest
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.enums import DraftStatus
from mcp_server import server as mcp_server
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
from services import draft_types


class _MarkPayload(BaseModel):
    product_id: int


@pytest.fixture
def registered_type():
    """A throwaway draft type, copied from test_mcp_drafts.py.

    The registry is module-level state, so the entry is popped afterwards.
    """
    calls: list[int] = []

    draft_types.register(
        "TEST_MARK",
        schema=_MarkPayload,
        handler=lambda session, actor, client, payload: calls.append(
            payload.product_id
        ),
    )
    yield calls
    draft_types._REGISTRY.pop("TEST_MARK", None)


@pytest.fixture
def call(session: Session, monkeypatch: pytest.MonkeyPatch):
    """Call an MCP tool by name, against this test's rolled-back session.

    Copied verbatim from test_mcp_drafts.py rather than promoted to conftest.py:
    it hard-codes that `auth_enabled` is off, which tests/test_mcp_auth.py must
    not inherit. See that file's docstring.
    """

    @contextmanager
    def fake_get_session():
        yield session

    monkeypatch.setattr(mcp_server, "get_session", fake_get_session)
    monkeypatch.setattr(mcp_server.settings, "auth_enabled", False)

    def invoke(_tool: str, /, **arguments):
        return anyio.run(lambda: mcp_server.mcp.call_tool(_tool, arguments))

    return invoke

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


def test_every_tool_result_validates_against_its_model(call, unique_sku):
    """The real contract check: a live tool call's structured_content is exactly
    what its model declares. This is what catches a field-type guess in
    schemas.py being wrong against reality."""
    created = call("create_product", sku=unique_sku, name="Rice 1kg").structured_content
    ProductOut.model_validate(created)  # raises on any mismatch

    listed = call("list_products").structured_content
    parsed = ProductListOut.model_validate(listed)
    assert parsed.total >= 1
    assert any(p.sku == unique_sku for p in parsed.products)


def test_lot_tool_results_validate_against_their_models(call, unique_sku):
    """Same shape, for a lot: a real receive + list validates field-for-field."""
    product = call("create_product", sku=unique_sku, name="Milk 2L").structured_content

    received = call(
        "receive_stock_lot",
        product_id=product["id"],
        lot_code="LOT-1",
        quantity=10,
        expiry_date="2099-01-01",
    ).structured_content
    LotOut.model_validate(received)

    listed = call("list_product_lots", product_id=product["id"]).structured_content
    parsed = LotListOut.model_validate(listed)
    assert any(lot.lot_code == "LOT-1" for lot in parsed.lots)


def test_draft_tool_results_validate_against_their_models(call, registered_type):
    """Same shape, for a draft: a real create + list validates field-for-field."""
    created = call(
        "create_action_draft",
        draft_type="TEST_MARK",
        payload={"product_id": 3},
        reasoning="milk expires tomorrow",
    ).structured_content
    DraftOut.model_validate(created)
    assert created["status"] == DraftStatus.PENDING

    listed = call("list_pending_drafts", limit=50).structured_content
    parsed = DraftListOut.model_validate(listed)
    assert any(d.id == created["id"] for d in parsed.drafts)


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


def test_reorder_and_spoilage_reports_validate_against_their_models(call):
    """Task 1 could not verify UnsourcedOut / SpoilageItemOut field lists from
    the diff. A live read-only call must - even an empty scenario validates the
    wrapper, and any seeded rows validate the nested items."""
    reorder = call("suggest_reorder_bundles").structured_content
    ReorderReportOut.model_validate(reorder)

    spoilage = call("check_spoilage_risk").structured_content
    SpoilageReportOut.model_validate(spoilage)
