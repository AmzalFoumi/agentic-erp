"""HTTP routes for products.

Read one handler and you have read them all. Each does exactly three things:

    1. receive validated input (Pydantic already checked its shape)
    2. call one service function
    3. return the result

There is no `try`, no `if`, no status code juggling, and above all no business
rule. Every rule you might expect to see - duplicate SKUs, negative stock,
permissions, SKU normalisation - is in services/products.py, where the MCP
adapter will reach it too. If a rule ever appears in this file, the two front
doors have begun to disagree and the architecture has quietly failed.

The absence of error handling is deliberate and is explained in api/errors.py:
domain exceptions propagate out of these functions and are turned into status
codes once, at the application level.

### The decorator, since it is new

    @router.get("/{product_id}")
    def get_product(...): ...

`@router.get(...)` is a function that takes `get_product` and registers it in a
routing table, then hands it back unchanged. It is `@Get(':id')` from Nest, and
the resemblance is not a coincidence - Nest borrowed the idea from Python and
Java. What is different from Nest is that FastAPI reads the *type hints* to
decide how to parse each parameter: `product_id: int` in a path declared as
`/{product_id}` makes it a path parameter, coerced to int, with a 422 if it is
not numeric. Nothing had to be declared twice.
"""

from fastapi import APIRouter, Query, status

from api.deps import CurrentActor, DbSession
from api.responses import BAD_REQUEST as _BAD_REQUEST
from api.responses import CONFLICT as _CONFLICT
from api.responses import FORBIDDEN as _FORBIDDEN
from api.responses import NOT_FOUND as _NOT_FOUND
from api.responses import UNPROCESSABLE as _UNPROCESSABLE
from api.responses import error_responses
from api.schemas import (
    ProductCreate,
    ProductList,
    ProductRead,
    ProductUpdate,
    StockAdjustment,
)
from services import products

# `prefix` is prepended to every path below, so the routes read as "" and
# "/{product_id}" rather than repeating "/products" six times. `tags` groups
# them under one heading in the generated /docs page.
router = APIRouter(prefix="/products", tags=["products"])


# --------------------------------------------------------------------------
# Documented failures
# --------------------------------------------------------------------------
#
# api/errors.py has always produced these responses; until now none of them
# appeared in the OpenAPI document, so a generated client knew the success
# shape and nothing else. `responses=` is what puts them there.
#
# This is declaration, not behaviour: adding or removing an entry changes the
# generated types and the /docs page, never what the API actually returns. The
# risk is therefore drift in one direction only - a failure that happens but
# is not declared. Hence assembling them from named constants rather than
# retyping a dict on six decorators.


def _errors(*codes: int) -> dict[int | str, dict]:
    """`error_responses` with this resource's own 404 and 409 wording.

    The generic builder lives in api/responses.py. It moved there at gate 27:
    this helper was right while there was one router, and gates 27-30 add five
    more - at which point five copies of the same status-code dictionary is
    five places for the same 403 to be described differently.

    What stays here is the wording that is genuinely about products. "No such
    product" and "That SKU is already taken" are better sentences than the
    generic ones, and flattening them would make the generated docs worse.
    """
    return error_responses(
        *codes,
        descriptions={
            _NOT_FOUND: "No such product.",
            _CONFLICT: "That SKU is already taken.",
        },
    )


@router.get(
    "",
    response_model=ProductList,
    responses=_errors(_FORBIDDEN, _UNPROCESSABLE),
)
def list_products(
    session: DbSession,
    actor: CurrentActor,
    search: str | None = Query(default=None, description="Matches name or SKU."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List products, newest first, optionally filtered by a search term.

    Docstrings on these functions are not only for developers: FastAPI puts them
    into the OpenAPI document, so this text appears in the /docs page. It is the
    same trick the MCP adapter will use in Gate 6, where the docstring becomes
    the tool description an AI model reads to decide whether to call it.

    `response_model=ProductList` does two jobs. It documents the shape in
    OpenAPI, and it *filters* the output: even if the service returned an object
    with extra attributes, only the fields declared on ProductRead are
    serialised. That is the guarantee that makes returning ORM objects safe.

    Pagination: `{items, total}`, where `total` counts everything matching
    `search` regardless of the window. That costs a second COUNT query on every
    list call, which is the honest price of page numbers - an offset-based
    control cannot render "of 12 pages" without knowing there are 12.

    The two calls are deliberately separate service functions rather than one
    returning a pair, so the MCP adapter - where an agent has no use for a page
    total - does not pay for the COUNT. See `services/products.py`.
    """
    return {
        "items": products.list_products(
            session, actor, search=search, limit=limit, offset=offset
        ),
        "total": products.count_products(session, actor, search=search),
    }


@router.post(
    "",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    responses=_errors(_BAD_REQUEST, _FORBIDDEN, _CONFLICT, _UNPROCESSABLE),
)
def create_product(payload: ProductCreate, session: DbSession, actor: CurrentActor):
    """Create a product.

    `payload: ProductCreate` is how FastAPI knows to read the request *body*:
    the parameter's type is a Pydantic model, so it cannot be a path or query
    parameter. Path, query and body are distinguished by type, not by decorator.

    `status_code=201` because a POST that creates a resource should say so. The
    default would be 200, which is not wrong so much as uninformative.

    `**payload.model_dump()` unpacks the model's fields into keyword arguments -
    `sku=..., name=..., cost_price=...`. It works precisely because the schema's
    field names were chosen to match the service's parameter names, and because
    every one of those parameters is keyword-only. Spelling all eight out by
    hand would be more explicit but would rot: adding a field to the schema and
    forgetting it here would silently drop it.
    """
    return products.create_product(session, actor, **payload.model_dump())


@router.get(
    "/by-sku/{sku}",
    response_model=ProductRead,
    responses=_errors(_FORBIDDEN, _NOT_FOUND),
)
def get_product_by_sku(sku: str, session: DbSession, actor: CurrentActor):
    """Look a product up by the code on its shelf label.

    This route is declared *before* `/{product_id}` on purpose. FastAPI matches
    in declaration order, and `/products/by-sku/X` has two segments where
    `/products/{product_id}` has one, so there is no real collision here - but
    the habit matters: a literal path that could be mistaken for a parameter
    must come first, or the parameterised route swallows it.
    """
    return products.get_product_by_sku(session, actor, sku=sku)


@router.get(
    "/{product_id}",
    response_model=ProductRead,
    responses=_errors(_FORBIDDEN, _NOT_FOUND, _UNPROCESSABLE),
)
def get_product(product_id: int, session: DbSession, actor: CurrentActor):
    """Fetch a single product by id.

    Missing row -> the service raises `NotFoundError` -> api/errors.py turns it
    into a 404. Nothing in this function knows any of that happened.
    """
    return products.get_product(session, actor, product_id=product_id)


@router.patch(
    "/{product_id}",
    response_model=ProductRead,
    responses=_errors(_BAD_REQUEST, _FORBIDDEN, _NOT_FOUND, _UNPROCESSABLE),
)
def update_product(
    product_id: int, payload: ProductUpdate, session: DbSession, actor: CurrentActor
):
    """Update the fields that were supplied, leaving the rest alone.

    PATCH rather than PUT, and `exclude_unset=True` is what makes that true - it
    drops any field the client did not send, so the service receives only the
    ones actually being changed. Without it, every omitted field would arrive as
    an explicit `None` and the service would read that as "clear this value",
    wiping the category off any product updated with a price change.
    """
    return products.update_product(
        session, actor, product_id=product_id, **payload.model_dump(exclude_unset=True)
    )


@router.post(
    "/{product_id}/adjust-stock",
    response_model=ProductRead,
    responses=_errors(_BAD_REQUEST, _FORBIDDEN, _NOT_FOUND, _UNPROCESSABLE),
)
def adjust_stock(
    product_id: int, payload: StockAdjustment, session: DbSession, actor: CurrentActor
):
    """Move stock by a signed amount: `+12` received, `-3` damaged.

    Not a PATCH on `quantity_on_hand`, and the distinction is the point. A stock
    level is not an editable field, it is the consequence of events. Modelling
    it as an action keeps the *reason* attached and leaves room for
    services/inventory.py to record a ledger row per movement later, without any
    change to this endpoint's contract.

    Refusing to go negative is the service's rule, and it produces a message
    naming the actual shortfall. It reaches the client as a **400**, not a 422 -
    `ValidationError` was moved off 422 precisely so a shopkeeper-readable "only
    2 in stock" is not behind the same code as a malformed request body. See
    core/exceptions.py.
    """
    return products.adjust_stock(
        session, actor, product_id=product_id, delta=payload.delta, reason=payload.reason
    )
