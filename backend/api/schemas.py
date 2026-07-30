"""Pydantic schemas - the API's public contract.

### Schema vs model, and why both exist

`core/models.py` describes the *database*. This file describes the *API*. They
currently look almost identical, which invites the obvious question: why not
return the ORM object directly and delete this file?

Because they answer to different masters. The moment you return ORM objects,
every column is public. Add a `supplier_cost_notes` column for internal use and
it silently appears in the JSON the frontend receives. Rename a column and the
frontend breaks. Add a `password_hash` anywhere and you have shipped a leak.

Keeping them separate means the database schema and the wire format can move
independently, and every field on the wire is one someone chose to put there.
This is the same reason a Nest app has DTOs alongside its TypeORM entities.

### Pydantic in one paragraph

Pydantic reads type hints and enforces them at runtime. `sell_price: Decimal`
is not a comment - post a string where a number belongs and the request is
rejected with a 422 and a precise message, before your code runs. It is `zod`,
except the schema *is* the type declaration rather than a parallel object you
have to keep in sync.

### One surprise worth knowing up front

Pydantic v2 serializes `Decimal` to JSON as a **string**: `"18.00"`, not
`18.00`. That looks wrong and is actually correct. JavaScript numbers are
float64 - exactly the representation we refused in core/models.py because it
cannot hold 0.1 exactly. Emitting money as a JSON number would hand the
frontend the very precision bug the `Numeric` column exists to prevent. As a
string it arrives intact, and the frontend formats it or parses it with a
decimal library. Do not "fix" this by casting to float.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------


class ProductCreate(BaseModel):
    """The body of POST /products.

    `Field(...)` attaches constraints and documentation to a field. The
    constraints here are *structural* - things that can be checked by looking at
    the value alone, with no database and no context: is it a string, is it
    short enough, is it non-negative.

    Business rules stay in `services/products.py`. "This SKU is already taken"
    cannot be checked here because it needs a query, and "stock may not go
    negative" cannot be checked here because it needs the current stock. That
    split is the important one: Pydantic guards the shape, the service guards
    the meaning. Duplicating a service rule here would mean the MCP adapter,
    which never sees this file, silently loses it.

    Note the deliberate redundancy on prices: `ge=0` here *and* a check in the
    service. The service one is authoritative and covers both adapters; this one
    exists so an HTTP client gets a clean field-level 422 instead of a 400.
    """

    # `...` as the first argument to Field means "required, no default". It is
    # Python's `Ellipsis` object, used here purely as a marker - a piece of
    # Pydantic idiom that looks alarming the first time you meet it.
    sku: str = Field(..., min_length=1, max_length=64, description="Shelf label code.")
    name: str = Field(..., min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    unit: str = Field(default="piece", max_length=32)

    # max_digits/decimal_places mirror the Numeric(10, 2) column, so an
    # over-precise price is rejected at the door rather than by Postgres.
    cost_price: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=10, decimal_places=2)
    sell_price: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=10, decimal_places=2)

    quantity_on_hand: int = Field(default=0, ge=0, description="Opening stock.")
    reorder_level: int = Field(default=0, ge=0)


class ProductUpdate(BaseModel):
    """The body of PATCH /products/{id}. Every field optional.

    This mirrors `update_product`'s signature exactly, including its known
    limitation: `None` means "not supplied, leave alone", so there is currently
    no way to clear `category` back to NULL through this endpoint. Fixing that
    needs a sentinel value distinct from None, and it is not worth the machinery
    until something actually needs to clear a field.

    `sku` and `quantity_on_hand` are absent by design. An SKU is printed on
    shelf labels, so changing it is a bigger event than a PATCH. Stock moves
    only through the adjust endpoint, so that a reason stays attached to it.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, max_length=32)
    cost_price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    sell_price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    reorder_level: int | None = Field(default=None, ge=0)


class StockAdjustment(BaseModel):
    """The body of POST /products/{id}/adjust-stock.

    A signed delta, not a new total. "Three cases arrived" and "we counted and
    there are 47" are different events, and a delta records the first honestly.
    A stock-take that sets an absolute figure is a separate operation, and it
    belongs in `services/inventory.py` when that exists.
    """

    delta: int = Field(..., description="Signed change: +12 received, -3 damaged.")
    reason: str | None = Field(default=None, max_length=200)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


class ProductRead(BaseModel):
    """What every product endpoint returns.

    `from_attributes=True` is the line that makes this work with the ORM. By
    default Pydantic builds a model from a dict; with this set it will also read
    plain attributes off an arbitrary object, so a SQLAlchemy `Product` can be
    handed straight to it. FastAPI does that conversion automatically when this
    class is the declared `response_model`.

    (In Pydantic v1 this setting was called `orm_mode`. Tutorials showing that
    name, or a `class Config:` block instead of `model_config`, are v1 - the
    single most common source of copy-paste failure when learning this stack.)

    Every field listed here is a deliberate decision to make it public. The
    audit columns are included because an inventory manager genuinely wants to
    know who last touched a row; `created_by` would be omitted if it held
    anything sensitive.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    category: str | None
    unit: str
    cost_price: Decimal
    sell_price: Decimal
    quantity_on_hand: int
    reorder_level: int
    created_at: datetime
    updated_at: datetime
    created_by: str | None
    updated_by: str | None


class ErrorResponse(BaseModel):
    """The shape of every error this API returns.

    Declared as a schema so it shows up in the OpenAPI document, which means the
    frontend can generate a typed client for the failure cases too - not just
    the happy path. See api/errors.py for what fills it in.
    """

    error: str = Field(description="Machine-readable class, e.g. 'NotFoundError'.")
    detail: str = Field(description="Human-readable message, safe to show a user.")
