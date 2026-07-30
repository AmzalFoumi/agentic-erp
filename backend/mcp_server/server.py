"""The MCP server: the same product operations, exposed as tools for an agent.

This file is the *proof* the architecture works. Everything it does, the FastAPI
adapter also does - and neither one contains a single business rule. Both call
the same functions in `services/products.py`. If a stock rule changes, it
changes in one place and both front doors change with it.

Worth stating plainly what was NOT done while writing this: no file in `api/`
was opened. That was the experiment (see docs/PLAN.md, Gate 6). If this adapter
could only be written by looking at the HTTP one, the "written once" claim was
never true - the real contract would have quietly moved into `api/schemas.py`.
Everything here came from `services/products.py` and `core/`.

### What MCP is, in one paragraph

An HTTP API exposes *endpoints* for a program to call, where a human developer
read the docs and wrote the call. MCP exposes *tools* for a language model to
call, where the model reads the description and decides to call it. The protocol
is JSON-RPC over some transport - here, stdio: the client starts this file as a
child process and talks to it over stdin/stdout.

**Nothing in this file may print to stdout.** stdout *is* the protocol stream,
so a stray `print()` injects garbage into the middle of a JSON-RPC message and
the client disconnects with a parse error that names no line of our code. This
is the single most common way a first MCP server fails, and the debugging
experience is genuinely awful because the symptom is nowhere near the cause. If
you need to debug, log to **stderr** (or use the `Context` object the SDK can
inject), never `print()`.

### The one idea to take away

`@mcp.tool()` reads the function's **type hints** to build the tool's input
schema, and its **docstring** to build the description the model reads. That is
the same trick FastAPI uses to generate `/docs` from the same two things. One
habit, two adapters - which is why type hints are not optional decoration in
this codebase.

The practical consequence is unusual and takes getting used to: **the docstrings
in this file are not comments, they are the user interface.** A vague docstring
is a tool the model misuses, in the same way an unlabelled button is a button
users press wrongly.
"""

from typing import Any

from mcp.server import MCPServer

from core.actor import SystemActor
from core.database import get_session
from core.models import Product
from services import products as product_service

# The server object. The name is what a client displays when listing what is
# connected; `instructions` is prose the model sees once, describing the server
# as a whole rather than any single tool - use it for context that would be
# repetitive to restate in every docstring.
mcp = MCPServer(
    "supermarket-inventory",
    instructions=(
        "Tools for managing a supermarket's product catalogue and stock levels. "
        "Products are identified either by numeric id or by SKU, the code printed "
        "on shelf labels. Stock is changed only through adjust_stock, never by "
        "editing a quantity directly, so that every movement has a reason "
        "attached to it."
    ),
)


def _actor() -> SystemActor:
    """The caller identity passed to every service function.

    Hardcoded to a SystemActor for now, exactly as the FastAPI adapter does -
    the auth provider decision is deferred (docs/PLAN.md). The id is "mcp" so
    the `created_by` column records which front door a row came through, which
    is genuinely useful the first time you wonder whether a human or an agent
    created something.

    When real authentication lands, this function is one of the two places that
    change. Nothing in `services/` moves.

    Note this is where MCP 2026-07-28 statelessness shows up concretely: there
    is no handshake in which the client says who it is once and the server
    remembers. Identity is rebuilt per call. Our design already assumed that.
    """
    return SystemActor(actor_id="mcp")


def _describe(product: Product) -> dict[str, Any]:
    """Turn a Product ORM object into a plain dict the protocol can send.

    This is the MCP counterpart of a Pydantic response schema: the boundary
    where an internal object becomes an external contract. It exists for two
    separate reasons, and only one of them is about JSON.

    **The mechanical reason.** A SQLAlchemy `Product` is not serialisable. It
    also holds a live link to its session, so returning one directly would
    either fail or - worse - lazily fire a database query long after the session
    closed.

    **The deliberate reason.** Choosing the fields here means an added column is
    not automatically published to every AI agent. That is a decision, made once
    per column, rather than a leak.

    `Decimal` becomes a **string**, not a float. 19.99 has no exact float64
    representation - it stores as 19.989999999999998 - and a system that reports
    prices is the last place to accept that. The FastAPI adapter serialises
    money the same way, which is convergence rather than coordination: both
    adapters hit the same constraint and there is only one correct answer.
    """
    return {
        "id": product.id,
        "sku": product.sku,
        "name": product.name,
        "category": product.category,
        "unit": product.unit,
        "cost_price": str(product.cost_price),
        "sell_price": str(product.sell_price),
        "quantity_on_hand": product.quantity_on_hand,
        "reorder_level": product.reorder_level,
        # Read from the model, not computed here. It was briefly computed in
        # this file, which was the wrong call: "needs reordering" is a rule the
        # business owns, so it belongs where both adapters can reach it. See
        # Product.needs_reorder in core/models.py.
        "needs_reorder": product.needs_reorder,
    }


@mcp.tool()
def list_products(
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List products in the catalogue, newest first.

    Use this to answer questions about what the shop stocks, to find a product
    when you only know part of its name, or to survey stock levels.

    Args:
        search: Optional text matched case-insensitively against both the
            product name and the SKU. Omit it to list everything.
        limit: Maximum number of products to return. Capped at 200.
        offset: How many products to skip, for paging through a long catalogue.

    Returns:
        A list of products. Each includes `needs_reorder`, which is true when
        stock has fallen to or below the product's reorder level.
    """
    with get_session() as session:
        found = product_service.list_products(
            session,
            _actor(),
            search=search,
            limit=limit,
            offset=offset,
        )
        return [_describe(product) for product in found]


if __name__ == "__main__":
    # `if __name__ == "__main__"` runs this block only when the file is executed
    # directly, not when it is imported. Python's equivalent of the `main`
    # guard - and load-bearing here, because without it merely importing this
    # module for a test would hang, waiting for JSON-RPC on stdin.
    #
    # `run()` defaults to stdio transport; the argument is written out anyway
    # because it is the line that changes when this server goes remote, and a
    # visible default is easier to find than an invisible one.
    mcp.run(transport="stdio")
