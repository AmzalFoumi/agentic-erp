"""Declaring which errors a route can return, in one place.

### What this is for

Every route needs a `responses={...}` mapping so its failure cases reach the
OpenAPI document, and from there the frontend's generated client. Without it,
`openapi-fetch`'s error branch is typed `unknown` and the UI has to guess.

This is **declaration, not behaviour**. Adding or removing an entry changes the
generated types and the /docs page, never what the API actually returns - the
handlers in `api/errors.py` do that. So the risk is drift in one direction
only: a failure that really happens but is not declared, which the frontend
then cannot type.

### Why it moved out of routes/products.py

It started as a private `_errors` helper there, which was right while there was
one router. Gates 27-30 add five more, and five copies of the same status-code
dictionary is five places for the same 403 to be described differently. The
descriptions a client reads should not depend on which router happened to be
written first.

Resource-specific wording is passed in rather than hardcoded, because "No such
product" and "No such draft" are genuinely different sentences and flattening
them to "Not found" would make the generated docs worse, not better.
"""

from fastapi import status

from api.schemas import ErrorResponse

# Wording that is genuinely the same whatever the resource is. A 403 means the
# same thing everywhere in this API, because every service call begins with the
# same permission check.
_SHARED_DESCRIPTIONS: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "A business rule was broken.",
    status.HTTP_403_FORBIDDEN: "The actor lacks the required permission.",
    status.HTTP_404_NOT_FOUND: "The resource does not exist.",
    status.HTTP_409_CONFLICT: "That would violate a uniqueness rule.",
    status.HTTP_422_UNPROCESSABLE_CONTENT: (
        "The request body does not match the schema. Carries `fields`."
    ),
}


def error_responses(
    *codes: int, descriptions: dict[int, str] | None = None
) -> dict[int | str, dict]:
    """Build a `responses=` mapping for the given status codes.

    Every error this API emits shares one envelope, so the schema is always
    `ErrorResponse` and only the set of codes - and sometimes the wording -
    differs per route.

    Declaring 422 here deliberately **overrides** the `HTTPValidationError`
    entry FastAPI adds by itself. That default describes the shape FastAPI
    would return if nothing intervened, and something does: the handler in
    `api/errors.py` reshapes every 422 into this envelope. Leaving the default
    in place would document a response the API never actually sends.

    Args:
        codes: the HTTP status codes this route can return.
        descriptions: per-code wording that overrides the shared default, for
            cases where a resource-specific sentence is genuinely more useful
            than a generic one.
    """
    merged = {**_SHARED_DESCRIPTIONS, **(descriptions or {})}
    return {
        code: {"model": ErrorResponse, "description": merged[code]} for code in codes
    }


# Named constants so a decorator reads as words rather than numbers. `404`
# appearing bare in six decorators is six chances to type `440`.
FORBIDDEN = status.HTTP_403_FORBIDDEN
NOT_FOUND = status.HTTP_404_NOT_FOUND
CONFLICT = status.HTTP_409_CONFLICT
BAD_REQUEST = status.HTTP_400_BAD_REQUEST
UNPROCESSABLE = status.HTTP_422_UNPROCESSABLE_CONTENT
