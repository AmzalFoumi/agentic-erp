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
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings

from core.actor import Actor, SystemActor, TokenActor
from core.config import settings
from core.database import get_session
from core.enums import ClientType, DraftStatus
from core.exceptions import AuthenticationError, ValidationError
from core.models import ActionDraft, Product
from mcp_server.auth import ThunderIDTokenVerifier
from mcp_server.errors import translated
from services import drafts as draft_service
from services import lots as lot_service
from services import products as product_service
from services import purchasing as purchasing_service
from services import spoilage as spoilage_service

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

# --------------------------------------------------------------------------
# Action drafts (gate 27)
# --------------------------------------------------------------------------
#
# Note what is NOT here: there is no approve tool, and there will not be one.
# The agent holds `draft.create` and never `draft.decide`, and the absence of
# the tool is the second layer of that - a tool that does not exist cannot be
# called even by a token that would have been allowed to. Two independent
# mechanisms, because "the agent cannot approve its own work" is the security
# property this whole feature exists to create.


def _describe_lot(lot: Any) -> dict[str, Any]:
    """One lot, in the shape a model reads best.

    Money as a string, for the same reason it crosses every other boundary that
    way: a float cannot hold 10.10 exactly, and a model asked to reason about
    prices should not be handed 10.099999999999999.
    """
    return {
        "lot_id": lot.id,
        "product_id": lot.product_id,
        "lot_code": lot.lot_code,
        # None is meaningful: "we do not know when this expires", not "missing".
        "expiry_date": lot.expiry_date.isoformat() if lot.expiry_date else None,
        "quantity": lot.quantity,
        "cost_price": str(lot.cost_price),
        "is_expired": lot.is_expired,
    }


def _describe_spoilage(report: Any) -> dict[str, Any]:
    """A spoilage report, flattened for a model.

    The two totals are separate keys and are never combined here. See the tool
    docstrings: netting them would turn a forecast into an apparent fact.
    """
    return {
        "scanned_on": report.scanned_on.isoformat(),
        "within_days": report.within_days,
        "total_cost_at_risk": str(report.total_cost_at_risk),
        "total_projected_recovery": str(report.total_projected_recovery),
        "items": [
            {
                "lot_id": item.lot_id,
                "product_id": item.product_id,
                "sku": item.sku,
                "product_name": item.product_name,
                "lot_code": item.lot_code,
                "expiry_date": item.expiry_date.isoformat(),
                "days_remaining": item.days_remaining,
                "quantity": item.quantity,
                "current_price": str(item.current_price),
                "proposed_price": str(item.proposed_price),
                "discount_percent": item.discount_percent,
                "why": item.tier_label,
                "cost_at_risk": str(item.cost_at_risk),
                "projected_recovery": str(item.projected_recovery),
            }
            for item in report.items
        ],
    }


def _describe_draft(draft: ActionDraft) -> dict[str, Any]:
    """Turn an ActionDraft into a plain dict the protocol can send.

    Same job as `_describe` above, same two reasons - a SQLAlchemy object is
    not serialisable and holds a live session link, and choosing the fields by
    hand means an added column is a decision rather than a leak.

    Money becomes a string, as everywhere else. `None` stays `None` rather than
    becoming "0.00", because "this proposal has no financial dimension" and
    "nothing is at stake" are different facts, and a model reading the second
    when the first is true would report a confident zero.
    """
    return {
        "id": draft.id,
        "draft_type": draft.draft_type,
        "status": draft.status,
        "payload": draft.payload,
        "reasoning": draft.reasoning,
        "cost_at_risk": (
            str(draft.cost_at_risk) if draft.cost_at_risk is not None else None
        ),
        "projected_recovery": (
            str(draft.projected_recovery)
            if draft.projected_recovery is not None
            else None
        ),
        "expires_at": draft.expires_at.isoformat() if draft.expires_at else None,
        # Computed on the model and shipped as an answer, not as inputs - the
        # same call `needs_reorder` represents. A model asked to work out
        # whether a timestamp has passed will sometimes get it wrong, and there
        # is no reason to make it try.
        "is_expired": draft.is_expired,
        "created_by": draft.created_by,
        "created_via": draft.created_via,
        "decided_by": draft.decided_by,
        "decided_via": draft.decided_via,
    }


def _describe_reorder(report: Any) -> dict[str, Any]:
    """A reorder report, flattened for a model. Same shape as `_describe_spoilage`."""
    return {
        "total_value": str(report.total_value),
        "bundles": [
            {
                "supplier_id": bundle.supplier_id,
                "supplier_name": bundle.supplier_name,
                "lead_time_days": bundle.lead_time_days,
                "minimum_order_value": str(bundle.minimum_order_value),
                "bundle_value": str(bundle.bundle_value),
                "below_minimum": bundle.below_minimum,
                "shortfall": str(bundle.shortfall),
                "lines": [
                    {
                        "product_id": line.product_id,
                        "sku": line.sku,
                        "name": line.name,
                        "quantity_on_hand": line.quantity_on_hand,
                        "reorder_level": line.reorder_level,
                        "quantity": line.quantity,
                        "unit_cost": str(line.unit_cost),
                        "pack_size": line.pack_size,
                        "line_total": str(line.line_total),
                        "is_top_up": line.is_top_up,
                    }
                    for line in bundle.lines
                ],
            }
            for bundle in report.bundles
        ],
        "unsourced": [dict(item) for item in report.unsourced],
    }


def _describe_order(order: Any) -> dict[str, Any]:
    """A purchase order, flattened for a model."""
    return {
        "id": order.id,
        "supplier_id": order.supplier_id,
        "status": order.status,
        "expected_date": order.expected_date.isoformat() if order.expected_date else None,
        "total_value": str(order.total_value),
        "notes": order.notes,
        "source_draft_id": order.source_draft_id,
        "created_by": order.created_by,
        "lines": [
            {
                "product_id": line.product_id,
                "quantity_ordered": line.quantity_ordered,
                "unit_cost": str(line.unit_cost),
                "line_total": str(line.line_total),
            }
            for line in order.lines
        ],
    }


@mcp.tool()
@translated
def create_action_draft(
    draft_type: str,
    payload: dict[str, Any],
    reasoning: str,
    cost_at_risk: str | None = None,
    projected_recovery: str | None = None,
) -> dict[str, Any]:
    """Propose a change for a human to approve. Nothing happens until they do.

    Use this for anything that affects many items at once or involves money:
    marking down a batch of stock that is about to expire, raising a purchase
    order, issuing a supplier credit. Your proposal goes into the manager's
    approval queue with your reasoning attached, and a human decides whether it
    runs.

    You cannot approve your own proposal and there is no tool that would let
    you. Write a clear `reasoning`: it is the only thing the manager has to
    judge by, and a proposal they cannot understand is one they will reject.

    For a single small change to one product - correcting one stock count,
    editing one product's details - use the specific tool for it instead. This
    is for proposals big enough that someone should look at the whole thing
    before it happens.

    Args:
        draft_type: The kind of proposal. Must be one this system recognises;
            an unknown kind is refused rather than stored.
        payload: The proposal's details. The required shape depends on
            draft_type, and is checked now and again when the human approves.
        reasoning: Plain-English explanation of why you are proposing this.
        cost_at_risk: Money currently at risk, as a decimal string like
            "40000.50". Omit when the proposal has no financial dimension -
            do not send "0" to mean "not applicable".
        projected_recovery: Money this proposal would recover, same format.

    Returns:
        The staged proposal, including the id a human will see in the queue.

    Raises:
        An error if the draft type is unknown, the payload does not match that
        type's required shape, or the reasoning is empty.
    """
    with get_session() as session:
        return _describe_draft(
            draft_service.create_draft(
                session,
                _actor(),
                client=ClientType.MCP_AGENT,
                draft_type=draft_type,
                payload=payload,
                reasoning=reasoning,
                cost_at_risk=(
                    _price(cost_at_risk, "cost_at_risk")
                    if cost_at_risk is not None
                    else None
                ),
                projected_recovery=(
                    _price(projected_recovery, "projected_recovery")
                    if projected_recovery is not None
                    else None
                ),
            )
        )


@mcp.tool()
@translated
def list_pending_drafts(limit: int = 20) -> list[dict[str, Any]]:
    """List proposals still waiting for a human decision.

    Use this to check whether something you proposed has been decided yet, or
    to avoid proposing the same thing twice in one conversation.

    A proposal that no longer appears here has been approved or rejected. This
    tool does not say which - read the individual draft if you need to know.

    ⚠️ A proposal that has passed its deadline DOES still appear here, with
    `is_expired` set to true. It is still pending, because nothing expires it
    automatically - no scheduled job exists. Check `is_expired` rather than
    assuming everything listed is still actionable; an expired proposal can no
    longer be approved and should be proposed again if it still matters.

    Args:
        limit: How many to return, newest first.

    Returns:
        The pending proposals, newest first.
    """
    with get_session() as session:
        return [
            _describe_draft(draft)
            for draft in draft_service.list_drafts(
                session, _actor(), status=DraftStatus.PENDING, limit=limit
            )
        ]

@mcp.tool()
@translated
def check_spoilage_risk(within_days: int | None = None) -> dict[str, Any]:
    """Find stock that is about to expire and what discounting it would recover.

    Read-only: this looks, and changes nothing. Use it freely while you are
    working out what to recommend.

    Each item tells you what the shop paid for that stock (`cost_at_risk` -
    money already spent, lost entirely if it is thrown away) and what the
    proposed discount would bring in (`projected_recovery` - a forecast that
    assumes the discounted stock actually sells).

    ⚠️ Do not subtract one of those from the other and present the result as a
    saving. They are different kinds of number: one is a fact about the past,
    the other is a guess about the future. Report them separately, as they are
    given to you.

    Stock with no recorded expiry date never appears here. That is deliberate -
    nobody knows when it goes off, so it is not a spoilage risk anyone can act
    on.

    Args:
        within_days: How far ahead to look. Leave it out to use the shop's own
            discount policy, which is the answer you usually want.

    Returns:
        The at-risk items with their proposed prices, and the two totals.
    """
    with get_session() as session:
        report = spoilage_service.scan_spoilage(
            session,
            _actor(),
            today=date.today(),
            **({"within_days": within_days} if within_days is not None else {}),
        )
        return _describe_spoilage(report)


@mcp.tool()
@translated
def propose_spoilage_markdown(
    reasoning: str, within_days: int | None = None
) -> dict[str, Any]:
    """Propose discounting everything that is about to expire. A human approves it.

    This stages one proposal covering every at-risk item and puts it in the
    manager's queue. **No price changes.** Nothing happens until a person reads
    your reasoning and approves it, and they may edit the prices first.

    Check `check_spoilage_risk` before calling this, so that your `reasoning`
    describes the actual situation rather than a guess.

    You cannot approve this yourself and there is no tool that would let you.

    Args:
        reasoning: Why the shop should do this, in plain English, for a manager
            who has not seen the numbers. Say what is at risk, how soon, and
            what happens if nothing is done. This is the only thing they have
            to judge by.
        within_days: How far ahead to include. Leave it out to use the shop's
            own discount policy.

    Returns:
        The staged proposal, including the id a human will see in the queue.

    Raises:
        An error if nothing is expiring within that window - in which case
        there is nothing to propose, and you should say so rather than retry
        with a wider one.
    """
    with get_session() as session:
        return _describe_draft(
            spoilage_service.propose_markdown(
                session,
                _actor(),
                client=ClientType.MCP_AGENT,
                today=date.today(),
                reasoning=reasoning,
                **({"within_days": within_days} if within_days is not None else {}),
            )
        )


@mcp.tool()
@translated
def list_product_lots(product_id: int) -> list[dict[str, Any]]:
    """The separate deliveries making up one product's stock, soonest expiry first.

    A product is "Milk 2L". A lot is the thirty cartons that arrived on Tuesday
    and expire on Friday. Use this when you need to know not just how much
    there is, but how much of it goes off when.

    Stock is always sold from the soonest-expiring lot first, so the first item
    in this list is what leaves the shelf next. A lot with no expiry date was
    on the shelf before the shop tracked expiry, and is used last.

    Args:
        product_id: Which product's deliveries to list.

    Returns:
        The lots that still hold stock, soonest expiry first.
    """
    with get_session() as session:
        return [
            _describe_lot(lot)
            for lot in lot_service.list_lots(
                session, _actor(), product_id=product_id
            )
        ]


@mcp.tool()
@translated
def receive_stock_lot(
    product_id: int,
    lot_code: str,
    quantity: int,
    expiry_date: str | None = None,
    cost_price: str | None = None,
) -> dict[str, Any]:
    """Book a delivery of one product into stock as a new lot.

    Use this when someone tells you stock physically arrived - "we just got 30
    cartons of milk, batch M-2026-08, they expire on the 5th". It creates one
    lot and raises the product's quantity on hand by that amount.

    This is a real write, not a proposal. Every call pauses for a human to
    confirm or cancel before anything is saved - so record exactly what you
    were told and do not invent a number you were not given.

    One call is one delivery of one product. If three different products
    arrived, call this three times.

    Args:
        product_id: Which product arrived.
        lot_code: The batch or delivery code, as printed on the carton or
            paperwork. Required - if you were not given one, ask for it.
        quantity: How many units arrived. Must be positive.
        expiry_date: The date this batch goes off, as "YYYY-MM-DD". Leave out
            if genuinely unknown - do not guess. Unknown-expiry stock is never
            marked down and is sold last.
        cost_price: What one unit cost on this delivery, as a string like
            "18.50". Leave out to use the product's current cost price. Once
            set it is frozen on the lot, so a later price change does not
            rewrite what this delivery actually cost.

    Returns:
        The new lot, including its id and the resulting quantity.
    """
    parsed_expiry: date | None = None
    if expiry_date is not None:
        try:
            parsed_expiry = date.fromisoformat(expiry_date)
        except ValueError:
            raise ValidationError(
                'expiry_date must be a calendar date written as "YYYY-MM-DD" - '
                f"got {expiry_date!r}."
            ) from None

    parsed_cost = _price(cost_price, "cost_price") if cost_price is not None else None

    with get_session() as session:
        lot = lot_service.receive_lot(
            session,
            _actor(),
            client=ClientType.MCP_AGENT,
            product_id=product_id,
            lot_code=lot_code,
            quantity=quantity,
            cost_price=parsed_cost,
            expiry_date=parsed_expiry,
        )
        return _describe_lot(lot)


@mcp.tool()
@translated
def suggest_reorder_bundles() -> dict[str, Any]:
    """Work out what to buy today, grouped by supplier.

    Read-only: this looks and changes nothing. Use it freely while working out
    what to recommend.

    Each bundle is one supplier's proposed order. Two things in it matter when
    you explain it to a person:

    - `is_top_up` on a line. False means the product is at or below its reorder
      level and the order is replacing it. True means the product is not low
      yet and is on the order only because the supplier has a minimum order
      value the rest of the lines did not reach. Say which is which; do not
      present a top-up as something that ran out.
    - `below_minimum`. True means the order is still under the supplier's
      minimum and there is nothing else to add. Tell the person plainly - it
      usually means a delivery charge.

    `unsourced` lists low products no active supplier stocks. They cannot be
    ordered by anyone. Mention them; do not quietly leave them out.

    Returns:
        The supplier bundles, the unsourced products, and the total value.
    """
    with get_session() as session:
        report = purchasing_service.scan_reorder(session, _actor())
        return _describe_reorder(report)


@mcp.tool()
@translated
def propose_reorder_order(supplier_id: int, reasoning: str) -> dict[str, Any]:
    """Propose one supplier's order for a manager to approve.

    This writes a proposal into the approvals queue and **places no order**.
    Nothing is bought until a human opens the approvals screen, reads the
    whole thing, optionally edits it, and approves.

    Call `suggest_reorder_bundles` first and propose a supplier that actually
    appears there. Proposing for a supplier with nothing low is refused.

    Args:
        supplier_id: Which supplier's bundle to propose.
        reasoning: Your own explanation, in your own words, of why this order
            is worth placing. A manager reads this to decide. Say what is low,
            what was added to reach the minimum, and when it would arrive.

    Returns:
        The staged proposal, including its id.
    """
    with get_session() as session:
        draft = purchasing_service.propose_reorder(
            session,
            _actor(),
            client=ClientType.MCP_AGENT,
            supplier_id=supplier_id,
            reasoning=reasoning,
        )
        return _describe_draft(draft)


@mcp.tool()
@translated
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
    with get_session() as session:
        draft = purchasing_service.propose_receipt(
            session,
            _actor(),
            client=ClientType.MCP_AGENT,
            order_id=order_id,
            lines=lines,
            reasoning=reasoning,
        )
        return _describe_draft(draft)


@mcp.tool()
@translated
def list_purchase_orders(
    status: str | None = None, limit: int = 20
) -> dict[str, Any]:
    """List purchase orders, newest first.

    Read-only. Statuses are: draft (raised, not placed), sent (placed with the
    supplier), partially_received, received, cancelled.

    An order created by approving your proposal starts as `draft` - a person
    still presses send. If someone asks whether their order went out, `sent` is
    the answer they mean.

    Args:
        status: Filter to one status. Leave it out for all of them.
        limit: How many to return. Defaults to 20.

    Returns:
        The orders and how many matched.
    """
    with get_session() as session:
        orders, total = purchasing_service.list_orders(
            session, _actor(), status=status, limit=limit
        )
        return {
            "orders": [_describe_order(order) for order in orders],
            "total": total,
        }


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
        if settings.auth_enabled:
            # stdio carries no HTTP request, so there is nowhere for a bearer
            # token to travel and `get_access_token()` returns None on every
            # call. `_actor()` then raises `AuthenticationError` for each tool
            # invocation, one at a time, with no mention of the setting that
            # caused it - so the developer meets the same opaque failure over
            # and over instead of one message naming the cause. `parser.error`
            # exits 2 with the text on stderr, which is the argparse convention
            # for "this combination of options cannot work".
            #
            # Raised by CodeRabbit on PR #30 as an outside-diff comment (the
            # line was not part of that PR's changes, so GitHub could not post
            # it inline).
            parser.error(
                "stdio cannot carry a bearer token, so every tool call would be "
                "refused with an authentication error. Set AUTH_ENABLED=false in "
                "backend/.env for a local stdio run, or use "
                "--transport streamable-http."
            )
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
