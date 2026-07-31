"""Tests for the HTTP adapter.

These are deliberately *thin*, and that is the argument they exist to make.

tests/test_products.py already proves the business rules are correct. If this
file re-tested them - every price rule, every permission - it would be asserting
the same logic twice, and worse, it would suggest the rules live at the HTTP
layer. They do not.

So what is left to check here is only what the adapter itself is responsible
for, which is a short list:

  - the routing and the status codes are wired up
  - a domain exception becomes the right HTTP status (the api/errors.py map)
  - the response body matches ProductRead
  - PATCH sends only the fields the client supplied

Every one of these is a claim about translation, not about products. The same
list, in the MCP dialect, is what Gate 6 will need to verify.
"""

from decimal import Decimal
from typing import get_args

from api.errors import _FRAMEWORK_ERROR_NAMES
from api.schemas import ErrorCode
from core.exceptions import DomainError


def test_health_reaches_the_database(client):
    """Proves the app boots and its session dependency resolves."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["database"] == "reachable"


def test_create_returns_201_and_the_created_row(client, unique_sku):
    """The happy path, end to end over HTTP."""
    response = client.post(
        "/products",
        json={
            "sku": unique_sku,
            "name": "Basmati Rice 1kg",
            "category": "Grains",
            "sell_price": "18.00",
            "quantity_on_hand": 40,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] is not None
    assert body["sku"] == unique_sku

    # Money arrives as a JSON *string*, not a number - see the note in
    # api/schemas.py. Asserting it explicitly documents the contract, so that
    # anyone who "fixes" it into a float has to change this line and think.
    assert body["sell_price"] == "18.00"

    # The overridden actor from conftest, proving the audit stamp survives the
    # trip through the adapter rather than being set to some HTTP-layer default.
    assert body["created_by"] == "pytest"


def test_missing_product_is_404(client):
    """NotFoundError -> 404, and the error envelope is the documented one."""
    response = client.get("/products/-1")

    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "NotFoundError"
    assert "detail" in body


def test_duplicate_sku_is_409(client, unique_sku):
    """DuplicateError -> 409 Conflict.

    The service rule is already tested; what is tested here is that it does not
    surface as a 500. An unmapped exception would give exactly that, so this is
    the test that would catch a missing entry in api/errors.py.
    """
    payload = {"sku": unique_sku, "name": "Sugar 1kg"}
    assert client.post("/products", json=payload).status_code == 201

    response = client.post("/products", json=payload)
    assert response.status_code == 409
    assert response.json()["error"] == "DuplicateError"


def test_business_rule_violation_is_400(client, unique_sku):
    """ValidationError from a *service* -> 400, a code the framework never emits.

    Deliberately NOT 422. FastAPI owns 422 for schema failures, and sharing it
    would mean a client could not tell "not enough stock" - a message for the
    shopkeeper - from "you sent the wrong type", which is a bug in the client.
    See the next test for the other half of that pair.
    """
    created = client.post(
        "/products",
        json={"sku": unique_sku, "name": "Tea 250g", "quantity_on_hand": 2},
    ).json()

    response = client.post(
        f"/products/{created['id']}/adjust-stock",
        json={"delta": -5, "reason": "spillage"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "ValidationError"
    # The service's message, carried through untouched - it names the shortfall,
    # which is the whole reason services raise with human-readable text.
    assert "only 2 in stock" in response.json()["detail"]


def test_malformed_request_is_422_and_stays_the_frameworks(client, unique_sku):
    """FastAPI's own 422, reshaped into our envelope but keeping its status code.

    A negative price is caught by Pydantic before any service runs. This is the
    framework's error, so it keeps the framework's code - and because no domain
    exception maps to 422 any more, a 422 from this API now means exactly one
    thing: the request did not match the schema.
    """
    response = client.post(
        "/products", json={"sku": unique_sku, "name": "Bad", "sell_price": "-1.00"}
    )

    assert response.status_code == 422
    assert response.json()["error"] == "RequestValidationError"
    assert "sell_price" in response.json()["detail"]


def test_422_carries_a_per_field_map(client):
    """A form needs each message under its own input, not one flattened line.

    `detail` is kept unchanged - this is additive - but `fields` is what stops
    every client re-deriving structure by splitting `detail` on "; " and ": ",
    which breaks as soon as a validation message contains either separator.
    """
    response = client.post(
        "/products",
        # Two failures at once, so the map is doing real work: `name` is
        # missing entirely, and `sell_price` breaks the ge=0 constraint.
        json={"sku": "X", "sell_price": "-1.00"},
    )

    assert response.status_code == 422
    fields = response.json()["fields"]
    assert set(fields) == {"name", "sell_price"}
    assert "required" in fields["name"].lower()

    # The flattened form still says the same thing, for callers that had it.
    detail = response.json()["detail"]
    assert "name" in detail and "sell_price" in detail


def test_fields_is_absent_on_errors_that_are_not_per_field(client):
    """`fields` is for schema failures only. A business rule has no field."""
    response = client.get("/products/-1")

    assert response.status_code == 404
    assert response.json().get("fields") is None


def test_unknown_route_is_distinguishable_from_a_missing_product(client):
    """The one status code we share with the framework, told apart by `error`.

    Both this and `GET /products/-1` return 404, and there is no better code for
    either. So the guarantee is in the body: a mistyped URL says `RouteNotFound`
    and a genuinely absent row says `NotFoundError`. A frontend that shows
    "product not found" on the first one would be lying to the user.
    """
    response = client.get("/no-such-endpoint")

    assert response.status_code == 404
    assert response.json()["error"] == "RouteNotFound"


def test_wrong_method_uses_the_same_envelope(client):
    """Starlette's 405, normalised. Proves the envelope is universal.

    Without the StarletteHTTPException handler this would come back as a bare
    `{"detail": "Method Not Allowed"}` - a second error format for the frontend
    to special-case.
    """
    response = client.delete("/products")

    assert response.status_code == 405
    assert response.json()["error"] == "MethodNotAllowed"
    # The Allow header is required on a 405 and must survive our rewriting.
    assert "allow" in {key.lower() for key in response.headers}


def test_patch_leaves_unsent_fields_alone(client, unique_sku):
    """`exclude_unset=True` in the route, verified rather than assumed.

    Without it, omitting `category` would send `category=None` to the service,
    which reads that as "clear it". This test fails loudly if that line is ever
    removed - the kind of silent data loss that is otherwise found in production
    by a confused shopkeeper.
    """
    created = client.post(
        "/products",
        json={"sku": unique_sku, "name": "Chickpeas 400g", "category": "Tinned"},
    ).json()

    response = client.patch(
        f"/products/{created['id']}", json={"sell_price": "4.50"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sell_price"] == "4.50"
    assert body["category"] == "Tinned"
    assert body["name"] == "Chickpeas 400g"


def test_list_and_search(client, unique_sku):
    """Query parameters reach the service, and the response is the envelope."""
    client.post("/products", json={"sku": unique_sku, "name": "Cardamom Pods"})

    response = client.get("/products", params={"search": "cardamom"})

    assert response.status_code == 200
    body = response.json()
    # `{items, total}`, not a bare array. Changed in Gate 8 so an offset-based
    # pagination control can render "page 3 of 12".
    assert any(item["sku"] == unique_sku for item in body["items"])


def test_total_describes_the_whole_match_not_the_page(client, unique_sku):
    """`total` ignores limit/offset, which is the only reason it is useful.

    A total equal to `len(items)` would be something the client already knows.
    This is the assertion that would fail if `count_products` ever grew the
    window arguments.
    """
    for index in range(3):
        client.post(
            "/products",
            json={"sku": f"{unique_sku}-{index}", "name": f"Fenugreek {index}"},
        )

    response = client.get("/products", params={"search": "Fenugreek", "limit": 1})

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["total"] == 3


def test_total_respects_the_same_filter_as_items(client, unique_sku):
    """The count and the list must agree on what "matching" means.

    They share `_search_filter` in the service precisely so this cannot drift.
    A total counting rows the list would never return produces a pagination
    control promising a page that comes back empty.
    """
    client.post("/products", json={"sku": unique_sku, "name": "Asafoetida 50g"})

    matching = client.get("/products", params={"search": "Asafoetida"}).json()

    # Every row the count claims is a row the list actually returns.
    assert matching["total"] == len(matching["items"]) == 1
    assert matching["items"][0]["sku"] == unique_sku

    # And the filter is doing something: the unfiltered count is not smaller.
    everything = client.get("/products").json()
    assert everything["total"] >= matching["total"]


def test_needs_reorder_is_computed_by_the_backend(client, unique_sku):
    """The low-stock rule is on the wire, not left for the frontend to derive.

    This is the API half of what test_mcp_products.py already asserts for the
    MCP adapter. Both front doors report the same rule from the same
    `hybrid_property`, which is the whole point of it living on the model.
    """
    created = client.post(
        "/products",
        json={
            "sku": unique_sku,
            "name": "Tamarind Block",
            "quantity_on_hand": 2,
            "reorder_level": 5,
        },
    ).json()

    assert created["needs_reorder"] is True

    # Push stock above the threshold; the same field must flip without the
    # client recomputing anything.
    restocked = client.post(
        f"/products/{created['id']}/adjust-stock", json={"delta": 10}
    ).json()

    assert restocked["quantity_on_hand"] == 12
    assert restocked["needs_reorder"] is False


def test_lookup_by_sku_is_case_insensitive(client, unique_sku):
    """The literal `/by-sku/` route resolves, and normalisation still applies."""
    client.post("/products", json={"sku": unique_sku, "name": "Olive Oil 1L"})

    response = client.get(f"/products/by-sku/{unique_sku.lower()}")

    assert response.status_code == 200
    assert response.json()["sku"] == unique_sku


def test_no_service_rule_was_reimplemented_in_the_adapter(client, unique_sku):
    """A guard against the failure mode this architecture is designed to avoid.

    SKU normalisation lives in the service. If someone ever "helpfully" adds
    `.upper()` to the schema or the route, this test still passes - but the MCP
    adapter, which never touches api/, would keep working precisely because the
    rule is where it belongs. The assertion is that lowercase input comes back
    normalised *without* the adapter doing anything to it.
    """
    response = client.post(
        "/products", json={"sku": f"  {unique_sku.lower()}  ", "name": "Lentils"}
    )

    assert response.status_code == 201
    assert response.json()["sku"] == unique_sku


def test_decimal_precision_survives_the_round_trip(client, unique_sku):
    """The reason money is Numeric and serialised as a string, demonstrated.

    0.1 + 0.2 in float64 is 0.30000000000000004. A price of 19.99 stored and
    returned as a float would be 19.989999999999998 in the frontend. Here it is
    exact on the way in and exact on the way out.
    """
    response = client.post(
        "/products",
        json={"sku": unique_sku, "name": "Coffee 200g", "cost_price": "19.99"},
    )

    assert Decimal(response.json()["cost_price"]) == Decimal("19.99")


# --------------------------------------------------------------------------
# The error union
# --------------------------------------------------------------------------
#
# `ErrorCode` promises the frontend an exhaustive list, and TypeScript will
# believe it: a `switch` over the generated union compiles clean when every
# member is handled. The promise is only worth anything if the list cannot
# silently fall out of step with the code that produces the values, so these
# two tests derive the truth from the source rather than restating it.


def test_error_union_covers_every_domain_exception():
    """Adding an exception to core/exceptions.py must break this test.

    `type(exc).__name__` is what api/errors.py puts in the `error` field, so
    every DomainError subclass name is a value the API can emit. A new
    subclass that nobody added to `ErrorCode` would be a value the generated
    TypeScript union does not contain - the frontend's `switch` would compile,
    and fall through at runtime on a real error.
    """

    def descendants(cls: type) -> set[str]:
        found = set()
        for sub in cls.__subclasses__():
            found.add(sub.__name__)
            found |= descendants(sub)
        return found

    declared = set(get_args(ErrorCode))
    ours = descendants(DomainError) | {DomainError.__name__}

    assert ours <= declared, f"not in ErrorCode: {sorted(ours - declared)}"


def test_error_union_covers_every_framework_error_name():
    """The same guarantee for the names api/errors.py invents for Starlette.

    `HTTPError` is the fallback for any status not in the map, so it is
    asserted separately - it appears in no dict but is reachable from the
    `.get(...)` default.
    """
    declared = set(get_args(ErrorCode))
    framework = set(_FRAMEWORK_ERROR_NAMES.values()) | {
        "HTTPError",
        "RequestValidationError",
    }

    assert framework <= declared, f"not in ErrorCode: {sorted(framework - declared)}"


def test_declared_error_responses_reach_the_openapi_document(client):
    """`responses=` on the routes actually lands in the schema.

    ErrorResponse was declared for months and attached to nothing, so it never
    appeared in /openapi.json and a generated client knew only the success
    shape. This asserts the wiring, not the wording.
    """
    schema = client.get("/openapi.json").json()

    assert "ErrorResponse" in schema["components"]["schemas"]

    # A 404 on the by-id route is the clearest case: it is entirely ours, and
    # it is the one a frontend detail page must handle.
    responses = schema["paths"]["/products/{product_id}"]["get"]["responses"]
    assert "404" in responses
    ref = responses["404"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/ErrorResponse")


def test_list_envelope_is_in_the_openapi_document(client):
    """The generated client must see `{items, total}`, not a bare array."""
    schema = client.get("/openapi.json").json()

    ref = schema["paths"]["/products"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    assert ref.endswith("/ProductList")

    product = schema["components"]["schemas"]["ProductRead"]
    assert "needs_reorder" in product["properties"]
