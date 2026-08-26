"""Tests for the MCP adapter.

Thin, for the same reason `test_api_products.py` is thin: `test_products.py`
already proves the business rules, and re-testing them here would assert the
same logic a third time while implying the rules live at the protocol boundary.
What is left is only what this adapter is responsible for:

  - the tools are registered, with schemas and descriptions
  - a domain exception becomes a message written for a model (mcp_server/errors)
  - an *unexpected* exception does not leak internals
  - money survives the round trip as a decimal string

Two of those have no counterpart on the HTTP side, which is the interesting
part. The FastAPI adapter cannot lose its own route descriptions, and an
exception leaking a connection string into a 500 body is seen by a developer,
not fed into a language model's context.

### Why the fixtures look different from the HTTP ones

`conftest.client` swaps the database session using FastAPI's
`dependency_overrides`. The MCP server has no dependency injection - each tool
calls `get_session()` directly, by name - so the seam is the module-level name
itself, replaced with `monkeypatch`. Same goal, cruder mechanism, and worth
noticing: dependency injection is a convenience the framework happens to
provide, not a thing the architecture depends on.
"""

from contextlib import contextmanager

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy.orm import Session

from mcp_server import server as mcp_server

# Every tool the server is expected to publish. Written out by hand rather than
# derived from the module, so that deleting a tool fails a test instead of
# quietly shrinking the expected set.
EXPECTED_TOOLS = {
    "list_products",
    "get_product",
    "get_product_by_sku",
    "create_product",
    "update_product",
    "adjust_stock",
}


@pytest.fixture
def call(session: Session, monkeypatch: pytest.MonkeyPatch):
    """Call an MCP tool by name, against this test's rolled-back session.

    `monkeypatch.setattr` replaces `get_session` *as the server module sees it*
    and restores it when the test ends. Note the target is
    `mcp_server.server.get_session`, not `core.database.get_session`: patching
    the definition would not help, because `server.py` did
    `from core.database import get_session`, which copied the reference into its
    own namespace at import time. Python imports bind names, they do not alias
    modules. Getting this wrong is the classic first monkeypatch bug and it
    presents as "the patch had no effect".

    The replacement deliberately does **not** close the session - conftest owns
    its lifetime and rolls it back.
    """

    @contextmanager
    def fake_get_session():
        yield session

    monkeypatch.setattr(mcp_server, "get_session", fake_get_session)

    # Gate 25: `_actor()` now refuses to invent an identity when authentication
    # is on, so these in-process calls - which have no HTTP request and
    # therefore no verified token - would every one of them fail with
    # "carries no verified identity". Turning auth off restores the SystemActor
    # this file has always run against.
    #
    # Deliberately flipping the *setting* rather than stubbing `_actor`: this
    # way the real function runs, including its fallback branch, so a change
    # that broke it would still be caught here. What `_actor` does with a real
    # token, and that it fails closed without one, is tested in
    # tests/test_mcp_auth.py - which is where those assertions belong.
    monkeypatch.setattr(mcp_server.settings, "auth_enabled", False)

    def invoke(_tool: str, /, **arguments):
        # The `/` makes `_tool` positional-only. Without it, calling
        # `invoke("create_product", name="Rice")` raises "got multiple values
        # for argument 'name'", because a tool argument happens to share the
        # helper's own parameter name. Positional-only is exactly the fix for a
        # function that forwards arbitrary keywords, and is why the standard
        # library uses it so heavily.
        return anyio.run(lambda: mcp_server.mcp.call_tool(_tool, arguments))

    return invoke


def test_every_tool_is_registered_with_a_description_and_schema():
    """The regression test for a decorator that silently eats metadata.

    `@mcp.tool()` builds the input schema from the signature and the description
    from `__doc__`. `mcp_server/errors.translated` wraps every tool, and a
    wrapper written without `functools.wraps` would register six tools all named
    `wrapper`, taking `**kwargs`, with no description - a completely broken
    server that raises no error and starts perfectly happily.

    This test is the only thing standing between that mistake and a very
    confusing afternoon.
    """
    tools = {t.name: t for t in anyio.run(mcp_server.mcp.list_tools)}

    assert set(tools) == EXPECTED_TOOLS

    for name, tool in tools.items():
        assert tool.description, f"{name} lost its docstring"
        assert tool.input_schema.get("properties"), f"{name} lost its parameters"

    # Spot-check that the parameters are the real ones rather than *args-shaped.
    assert "product_id" in tools["get_product"].input_schema["properties"]


def test_create_then_read_back_over_the_protocol(call, unique_sku):
    """The happy path, through tool dispatch rather than direct function calls.

    Going through `call_tool` means the arguments are validated against the
    generated schema on the way in, so this also proves the schema is usable.
    """
    created = call(
        "create_product",
        sku=unique_sku,
        name="Basmati Rice 1kg",
        category="Grains",
        sell_price="18.00",
        quantity_on_hand=40,
        reorder_level=10,
    ).structured_content

    assert created["sku"] == unique_sku
    assert created["id"] is not None

    # The audit columns are deliberately absent from the tool's output - see
    # `_describe`. Asserting that here makes it a documented choice rather than
    # something a future reader assumes was forgotten.
    assert "created_by" not in created
    assert "created_at" not in created

    fetched = call("get_product_by_sku", sku=unique_sku.lower()).structured_content
    assert fetched["id"] == created["id"]
    assert fetched["name"] == "Basmati Rice 1kg"


def test_money_crosses_the_protocol_as_a_string(call, unique_sku):
    """Both directions, in one test, because they are one decision.

    "19.99" as a JSON number is parsed to float64 as 19.989999999999998. The
    tool accepts a string on the way in (`_price`) and emits one on the way out
    (`_describe`) so the value never passes through a float at all.
    """
    created = call(
        "create_product", sku=unique_sku, name="Coffee 200g", cost_price="19.99"
    ).structured_content

    assert created["cost_price"] == "19.99"
    assert isinstance(created["cost_price"], str)


def test_needs_reorder_is_reported(call, unique_sku):
    """The derived field, computed on the model and merely relayed here.

    If this ever disagrees with the same flag on the HTTP side, the rule has
    been duplicated somewhere it should not have been.
    """
    created = call(
        "create_product",
        sku=unique_sku,
        name="Tea 250g",
        quantity_on_hand=3,
        reorder_level=5,
    ).structured_content

    assert created["needs_reorder"] is True

    restocked = call("adjust_stock", product_id=created["id"], delta=10).structured_content
    assert restocked["quantity_on_hand"] == 13
    assert restocked["needs_reorder"] is False


def test_domain_error_carries_instructions_for_the_model(call):
    """NotFoundError becomes a message that tells the model what to do next.

    The assertion on the guidance text is not decoration. A message that only
    says what failed leaves a model free to retry with a guessed id, which is
    precisely what they do. If someone strips the guidance for brevity, this
    test says why it was there.
    """
    with pytest.raises(ToolError) as excinfo:
        call("get_product", product_id=-1)

    message = str(excinfo.value)
    assert "No product with id -1" in message
    assert "list_products" in message


def test_business_rule_violation_is_reported_as_such(call, unique_sku):
    """ValidationError from a service, with its own message preserved intact."""
    created = call(
        "create_product", sku=unique_sku, name="Sugar 1kg", quantity_on_hand=2
    ).structured_content

    with pytest.raises(ToolError) as excinfo:
        call("adjust_stock", product_id=created["id"], delta=-5)

    assert "only 2 in stock" in str(excinfo.value)


def test_unparseable_price_is_caught_in_the_adapter(call, unique_sku):
    """A model writing "about 20" into a price field, which happens.

    Note where this is caught: `_price` in the adapter, before any service runs.
    The equivalent on the HTTP side is Pydantic rejecting the body. Neither is a
    business rule, and `services/` is entitled to assume it received a Decimal.
    """
    with pytest.raises(ToolError) as excinfo:
        call("create_product", sku=unique_sku, name="Mystery", cost_price="about 20")

    assert "cost_price" in str(excinfo.value)


def test_unexpected_errors_do_not_leak_internals(call, monkeypatch, capsys):
    """The privacy control in mcp_server/errors, tested rather than assumed.

    A SQLAlchemy failure stringifies to the failing statement and connection
    details - with our Supabase URL, that can include the host and user. Handing
    that to a language model puts it in the model's context, the client's logs,
    and possibly a model provider's telemetry.

    So the test simulates an infrastructure failure carrying a secret and
    asserts the secret does not reach the caller, while the detail *does* reach
    stderr where an operator can see it.
    """
    secret = "postgresql://postgres:hunter2@db.example.supabase.co:5432"

    def explode(*args, **kwargs):
        raise RuntimeError(f"connection failed: {secret}")

    monkeypatch.setattr(mcp_server.product_service, "list_products", explode)

    with pytest.raises(ToolError) as excinfo:
        call("list_products")

    message = str(excinfo.value)
    assert secret not in message
    assert "hunter2" not in message
    assert "unavailable" in message

    # The operator still gets the truth - on stderr, never stdout. Under stdio
    # transport stdout is the JSON-RPC stream, so a traceback printed there
    # would corrupt the message frame and drop the connection.
    captured = capsys.readouterr()
    assert secret in captured.err
    assert captured.out == ""


def test_the_mcp_adapter_never_imports_the_http_adapter():
    """The experiment behind Gate 6, asserted mechanically.

    `lint-imports` enforces this properly across the whole package. This test
    exists as well because it fails during a normal `pytest` run, which is where
    the mistake would actually be made - the tempting shortcut being
    `from api.schemas import ProductCreate`, which looks like clean reuse and
    quietly makes the agent adapter depend on the web adapter.

    Checked by reading the source rather than by inspecting `sys.modules`,
    because by the time this runs the HTTP tests have already imported `api`
    into the same process. A runtime check would pass or fail depending on test
    ordering, which is worse than no check at all.
    """
    from pathlib import Path

    package = Path(mcp_server.__file__).parent

    for path in package.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(source.splitlines(), start=1):
            statement = line.strip()
            assert not statement.startswith(("import api", "from api")), (
                f"{path.name}:{lineno} imports the HTTP adapter: {statement!r}"
            )
