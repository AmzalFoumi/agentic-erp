"""The MCP server: the same product operations, exposed as tools for an agent.

This file is the *proof* the architecture works. Everything it does, the FastAPI
adapter also does - and neither one contains a single business rule. Both call
the same functions in `services/products.py`. If a stock rule changes, it
changes in one place and both front doors change with it.

Worth stating plainly what was NOT done while writing this: no file in `api/`
was opened. That was the experiment (see docs/BACKEND-PLAN.md, Gate 6). If this
adapter could only be written by looking at the HTTP one, the "written once" claim was
never true - the real contract would have quietly moved into `api/schemas.py`.
Everything here came from `services/products.py` and `core/`.

### What MCP is, in one paragraph

An HTTP API exposes *endpoints* for a program to call, where a human developer
read the docs and wrote the call. MCP exposes *tools* for a language model to
call, where the model reads the description and decides to call it. The protocol
is JSON-RPC over some transport, and this file offers two (see `main()` at the
bottom): **stdio**, where the client starts this file as a child process and
talks to it over stdin/stdout, and **Streamable HTTP**, where the client only
needs a URL. The tools below are identical either way - a transport is how bytes
move, not what they mean.

**Nothing in this file may print to stdout.** Under stdio, stdout *is* the
protocol stream, so a stray `print()` injects garbage into the middle of a
JSON-RPC message and the client disconnects with a parse error that names no
line of our code. This is the single most common way a first MCP server fails,
and the debugging experience is genuinely awful because the symptom is nowhere
near the cause. If you need to debug, log to **stderr** (or use the `Context`
object the SDK can inject), never `print()`.

The rule stays absolute rather than becoming transport-conditional now that HTTP
exists: a `print()` added while running over HTTP breaks nothing until the day
someone runs the same file over stdio, which is the worst possible moment to
discover it.

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

import argparse
from decimal import Decimal, InvalidOperation
from typing import Any

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings

from core.actor import Actor, SystemActor, TokenActor
from core.config import settings
from core.database import get_session
from core.exceptions import AuthenticationError, ValidationError
from core.models import Product
from mcp_server.auth import ThunderIDTokenVerifier
from mcp_server.errors import translated
from services import products as product_service

# The server object. The name is what a client displays when listing what is
# connected; `instructions` is prose the model sees once, describing the server
# as a whole rather than any single tool - use it for context that would be
# repetitive to restate in every docstring.
#
# **Auth (gate 25).** `token_verifier` is what actually checks a bearer token;
# `auth` is the configuration that turns checking on and describes this server
# as an OAuth *resource server* - one that accepts tokens issued elsewhere and
# never issues any itself. The SDK requires both together or neither: passing a
# verifier with no `auth` raises, and so does the reverse, which is a good
# design because either half alone is authentication theatre.
#
# `resource_server_url` is this server's own identity, and it is deliberately
# NOT the HTTP API's. See core/config.py on thunderid_mcp_audience.
#
# `required_scopes` is left unset on purpose. It would gate the whole server on
# one permission, and the real check is per-operation: `services/` asks
# `actor.can("stock.adjust")` for a stock move and `actor.can("product.read")`
# for a lookup. A blanket requirement here would either be too weak to matter or
# would lock a read-only agent out of reads it is entitled to.
#
# ⚠️ `AUTH_ENABLED=false` produces an unauthenticated server, for the test suite
# and offline work. It must never be false anywhere reachable by anything but
# the developer's own machine; it defaults to True so forgetting fails closed.
_auth_settings = (
    AuthSettings(
        issuer_url=settings.thunderid_issuer,  # type: ignore[arg-type]
        resource_server_url=settings.thunderid_mcp_audience,  # type: ignore[arg-type]
        # ID-JAG stays off. It is a value of `requested_token_type` on the same
        # endpoint, not a second architecture, and nothing in this gate needs
        # it: `created_by`/`updated_by` already record who acted. Turning it on
        # before there is a second party to test against would be speculative
        # work against a draft spec. See docs/AUTH-PLAN.md.
        identity_assertion_enabled=False,
    )
    if settings.auth_enabled
    else None
)

mcp = MCPServer(
    "supermarket-inventory",
    token_verifier=ThunderIDTokenVerifier() if settings.auth_enabled else None,
    auth=_auth_settings,
    instructions=(
        "Tools for managing a supermarket's product catalogue and stock levels. "
        "Products are identified either by numeric id or by SKU, the code printed "
        "on shelf labels. Stock is changed only through adjust_stock, never by "
        "editing a quantity directly, so that every movement has a reason "
        "attached to it."
    ),
)


def _actor() -> Actor:
    """The caller identity passed to every service function.

    **The trap CLAUDE.md carried since gate 6, closed at gate 25.** Until now
    this returned an all-powerful `SystemActor` unconditionally: the HTTP API
    was authenticated and the MCP server was not, which was survivable only
    because `agent/app.py` binds to 127.0.0.1 with a test that fails if that
    changes. An agent must never be more powerful than the person it acts for.

    Nothing in `services/` moved when this landed. The call sites already took
    an actor and already called `actor.can(...)`, which was the entire point of
    making identity a parameter in gate 3.

    `get_access_token()` reads the token the SDK has *already verified* through
    `mcp_server/auth.py` - this function does no checking of its own, and must
    not start: two verification paths is how one of them ends up weaker.

    Note this is where MCP 2026-07-28 statelessness shows up concretely: there
    is no handshake in which the client says who it is once and the server
    remembers. Identity is rebuilt per call. Our design already assumed that.
    """
    token = get_access_token()

    if token is None:
        # No auth context. Two very different situations reach here, and
        # conflating them is exactly the bug this gate exists to remove.
        if settings.auth_enabled:
            # Should be unreachable: with `auth` configured the SDK refuses an
            # unauthenticated request before any tool runs. Kept as a belt to
            # the SDK's braces, because the failure mode if it ever *is*
            # reachable - anonymous writes stamped with a fake identity - is
            # the worst one in this codebase. Fail closed and loudly.
            raise AuthenticationError("This request carries no verified identity.")
        # AUTH_ENABLED=false: the pre-gate-24 behaviour, for the test suite and
        # for offline work. The id is "mcp" rather than "system" so an audited
        # row still records which front door wrote it - api/deps.py uses "api".
        return SystemActor(actor_id="mcp")

    # `subject` is the OIDC `sub`, so `created_by`/`updated_by` record the
    # actual person the agent was acting for - not the agent, and not "mcp".
    # That is the gate's exit condition in one line.
    #
    # ⚠️ `scopes` can legitimately be empty: ThunderID answers a request for a
    # permission it does not recognise with 200 OK and a token carrying no
    # scope claim. Such an actor authenticates and is then refused by every
    # `can()`, which is the correct fail-closed reading. If everything 403s,
    # suspect the token before the code - mcp_server/auth.py logs a warning
    # naming the subject when it sees one.
    if token.subject is None:
        # `AccessToken.subject` is Optional in the SDK because a verifier is
        # allowed not to supply it. Ours always does - `authn/tokens.py`
        # requires `sub` precisely because it becomes an audit column - so this
        # is a contract check, not an expected path. A row with no provenance
        # is not acceptable, and neither is `created_by = None`.
        raise AuthenticationError("The verified token names no subject.")

    return TokenActor(actor_id=token.subject, scopes=frozenset(token.scopes))


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
        # Published at gate 25, and per this docstring that is a decision rather
        # than a leak. Two reasons it earns its place:
        #
        # 1. It is the *confirmation* of the thing this gate built. The agent
        #    panel shows this value back to the person who just approved a
        #    write, so "the agent acted as you" is visible on screen instead of
        #    being something only a test knows. Until now that line was the
        #    hardcoded string "system" - true when SystemActor was the only
        #    actor, and a lie afterwards, printed in exactly the place someone
        #    would look to check the audit trail.
        # 2. It is not a disclosure. The value is the OIDC `sub` of whoever
        #    acted, and the only caller that can read it is one already holding
        #    a token for this resource server.
        #
        # Nullable: rows written before the audit columns existed carry None.
        "updated_by": product.updated_by,
    }


def _price(value: str, field: str) -> Decimal:
    """Parse a money string into a Decimal, or raise ValidationError.

    Money crosses the protocol as a **string** in both directions. Outbound the
    reason is precision (see `_describe`); inbound the reason is the same one
    running backwards - if the tool took a `float`, the model would send
    `19.99`, JSON would parse it to the nearest float64, and the value stored
    would already be wrong before any of our code ran.

    This is parsing, not business logic, so it belongs in the adapter. The
    proof: `api/schemas.py` does the identical job with a Pydantic field type.
    Both adapters must turn outside text into a Decimal before `services/` sees
    it, because `services/` is entitled to assume it was given a Decimal.

    The `InvalidOperation` catch matters more here than on the HTTP side. A
    language model writing `"about 20"` or `"20 MAD"` into a price field is not
    a hypothetical; without this, that surfaces as a raw decimal library error
    with no indication of which argument was wrong.
    """
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValidationError(
            f"{field} must be a decimal number written as a string, "
            f'like "19.99" - got {value!r}.'
        ) from None


@mcp.tool()
@translated
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


@mcp.tool()
@translated
def get_product(product_id: int) -> dict[str, Any]:
    """Get one product by its numeric id.

    Prefer get_product_by_sku when you have a shelf-label code rather than an
    id. Ids appear in the output of other tools; they are not printed on
    packaging, so a user will almost never say one out loud.

    Args:
        product_id: The product's numeric id, as returned by list_products.

    Returns:
        The product's full details.

    Raises:
        An error if no product has that id. Do not retry with a guessed id -
        search for the product with list_products instead.
    """
    with get_session() as session:
        return _describe(product_service.get_product(session, _actor(), product_id=product_id))


@mcp.tool()
@translated
def get_product_by_sku(sku: str) -> dict[str, Any]:
    """Get one product by its SKU, the code printed on the shelf label.

    Matching ignores case and surrounding spaces, so "rice-1kg" finds
    "RICE-1KG". This is the tool to use when a user quotes a code to you.

    Args:
        sku: The stock keeping unit code, for example "RICE-1KG".

    Returns:
        The product's full details.

    Raises:
        An error if no product has that SKU. That usually means the code was
        misheard or mistyped; try list_products with part of the code as the
        search term rather than guessing variations.
    """
    with get_session() as session:
        return _describe(product_service.get_product_by_sku(session, _actor(), sku=sku))


@mcp.tool()
@translated
def create_product(
    sku: str,
    name: str,
    category: str | None = None,
    unit: str = "piece",
    cost_price: str = "0.00",
    sell_price: str = "0.00",
    quantity_on_hand: int = 0,
    reorder_level: int = 0,
) -> dict[str, Any]:
    """Add a new product to the catalogue.

    Check first with get_product_by_sku or list_products that the product does
    not already exist under a slightly different name - creating a duplicate
    under a second SKU splits its stock across two records, which is tedious to
    unpick. If the user has not given a SKU, ask for one rather than inventing
    it: SKUs are printed on shelf labels and must match the physical shop.

    Args:
        sku: The shelf-label code. Stored upper-cased and trimmed. Must be
            unique across the catalogue.
        name: The product's display name, for example "Basmati Rice 1kg".
        category: Optional grouping such as "Grains" or "Dairy".
        unit: What stock is counted in - "piece", "kg", "litre", "box". Use a
            smaller unit rather than fractions: a product sold by weight should
            be counted in "gram", because quantities are whole numbers.
        cost_price: What the shop pays, as a decimal string like "12.50".
        sell_price: What the customer pays, as a decimal string like "18.00".
        quantity_on_hand: Opening stock. Leave at 0 and use adjust_stock if the
            stock is arriving as a delivery, so the movement has a reason.
        reorder_level: Stock level at or below which the product counts as
            needing reordering.

    Returns:
        The created product, including the id assigned by the database.

    Raises:
        An error if the SKU is already used, if the name is empty, or if a
        price or quantity is negative.
    """
    with get_session() as session:
        return _describe(
            product_service.create_product(
                session,
                _actor(),
                sku=sku,
                name=name,
                category=category,
                unit=unit,
                cost_price=_price(cost_price, "cost_price"),
                sell_price=_price(sell_price, "sell_price"),
                quantity_on_hand=quantity_on_hand,
                reorder_level=reorder_level,
            )
        )


@mcp.tool()
@translated
def update_product(
    product_id: int,
    name: str | None = None,
    category: str | None = None,
    unit: str | None = None,
    cost_price: str | None = None,
    sell_price: str | None = None,
    reorder_level: int | None = None,
) -> dict[str, Any]:
    """Change details of an existing product. Omitted fields are left alone.

    Send only the fields being changed. Sending a field its current value is
    harmless but sending every field is a good way to overwrite something the
    user did not ask you to touch.

    Two things cannot be changed here, deliberately. **SKU** is fixed once
    printed on a label - to correct one, the product is deleted and recreated.
    **Stock quantity** is changed only through adjust_stock, so that every
    movement carries a reason.

    Args:
        product_id: Which product to change.
        name: New display name.
        category: New category. Sending an empty string clears it.
        unit: New counting unit.
        cost_price: New cost price, as a decimal string like "12.50".
        sell_price: New selling price, as a decimal string like "18.00".
        reorder_level: New reorder threshold.

    Returns:
        The product as it now stands.

    Raises:
        An error if the product does not exist, the name is blank, or a price
        or level is negative.
    """
    with get_session() as session:
        return _describe(
            product_service.update_product(
                session,
                _actor(),
                product_id=product_id,
                name=name,
                category=category,
                unit=unit,
                cost_price=None if cost_price is None else _price(cost_price, "cost_price"),
                sell_price=None if sell_price is None else _price(sell_price, "sell_price"),
                reorder_level=reorder_level,
            )
        )


@mcp.tool()
@translated
def adjust_stock(product_id: int, delta: int, reason: str | None = None) -> dict[str, Any]:
    """Move a product's stock up or down by a given amount.

    This is the only way stock changes. `delta` is a **change**, not a new
    total: to record a delivery of 20 use delta=20, and to record 3 broken jars
    use delta=-3. If a user says "we now have 50", first read the current
    quantity and send the difference - sending 50 would add 50 to what is
    already there.

    Stock cannot go below zero. A request to remove more than is on hand is
    refused rather than clamped, because the shortfall usually means the count
    is wrong somewhere and silently zeroing it would hide that.

    Args:
        product_id: Which product to adjust.
        delta: How much to add (positive) or remove (negative). Cannot be zero.
        reason: Short note on why, such as "delivery", "breakage", "stocktake
            correction". Always supply one when the user has given a reason;
            it is not yet stored, but will be once the stock ledger exists.

    Returns:
        The product with its updated quantity.

    Raises:
        An error if the product does not exist, delta is zero, or the removal
        would drive stock negative - the message states how much is actually
        in stock.
    """
    with get_session() as session:
        return _describe(
            product_service.adjust_stock(
                session,
                _actor(),
                product_id=product_id,
                delta=delta,
                reason=reason,
            )
        )


def main(argv: list[str] | None = None) -> None:
    """Run the server on one of its two transports.

    Two, because they answer different questions. **stdio** is for a client that
    starts this file as a child process - Claude Desktop, an inspector, or
    `agent/scripts/check_mcp.py` before Gate 16. **Streamable HTTP** is for a
    client that only has a URL, which is what `agent/` is: a separate directory
    with a separate virtualenv, reaching the ERP over a protocol and nothing else
    (docs/AGENT-PLAN.md, "Architecture"). Adding HTTP is what let that script
    stop knowing the backend's interpreter path.

    A flag rather than an environment variable because it is a per-run choice,
    not a per-machine one: the same checkout serves both, often in the same hour.
    """
    parser = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="stdio (default) for a client that launches this process; "
        "streamable-http for a client that has only a URL.",
    )
    # 8001, not 8000: `uvicorn api.main:app` already owns 8000. The two adapters
    # are separate processes and are expected to run at the same time.
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Loopback only, deliberately. Binding this to 0.0.0.0 or a LAN "
        "address trips the auth deferral's stop condition - read "
        "docs/AGENT-PLAN.md, 'The stop condition', before changing it.",
    )
    parser.add_argument(
        "--path",
        default="/mcp",
        help="Must match agent/'s MCP_BASE_URL (default http://127.0.0.1:8001/mcp).",
    )
    parser.add_argument(
        "--sessions",
        action="store_true",
        help="Keep a server-side session per client. Off by default: the "
        "2026-07-28 revision carries identity per request instead, which is "
        "the property this project pinned mcp 2.0 on both halves to use. Turn "
        "it on only to serve a 2025-era client, which needs the handshake.",
    )
    args = parser.parse_args(argv)

    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return

    # Auth is configured on the `mcp` object above, not here, because it is a
    # property of the server rather than of a transport - the same tokens are
    # required whichever way bytes arrive. (In practice only this branch can
    # enforce it: stdio has no request to carry a header, so a stdio run is
    # implicitly the developer's own machine and `_actor()` falls back to
    # SystemActor only when AUTH_ENABLED is false.)
    #
    # The loopback host above is therefore no longer the *only* thing standing
    # between this port and anonymous writes - but it stays until gate 26
    # regardless. The SDK also adds DNS-rebinding protection for loopback hosts,
    # which is a backstop against a browser reaching this port, not
    # authentication and not a substitute for it.
    mcp.run(
        transport="streamable-http",
        host=args.host,
        port=args.port,
        streamable_http_path=args.path,
        stateless_http=not args.sessions,
    )


if __name__ == "__main__":
    # `if __name__ == "__main__"` runs this block only when the file is executed
    # directly, not when it is imported. Python's equivalent of the `main`
    # guard - and load-bearing here, because without it merely importing this
    # module for a test would hang, waiting for JSON-RPC on stdin.
    main()
