"""Domain exception -> HTTP status. The entire translation layer, in one file.

### Why this is not a try/except in each handler

The plan originally said each route handler would catch `NotFoundError` and
raise a 404. That works, and it is what most tutorials show. It is also how the
mapping drifts: twelve handlers, each with its own try/except, and the day
someone adds a thirteenth in a hurry, a missing product returns a 500 with a
stack trace. The rule "NotFoundError means 404" is one rule, so it is written
once, here, and registered on the application.

FastAPI supports this directly: `@app.exception_handler(SomeError)` installs a
function that runs whenever that exception escapes a handler. The handlers in
routes/ therefore contain no error handling at all - they call a service and
return. That is what makes them short enough to verify at a glance.

### The status codes, and the deliberate avoidance of the framework's own

    NotFoundError          404 Not Found            (see the 404 note below)
    DuplicateError         409 Conflict             framework never emits this
    ValidationError        400 Bad Request          framework never emits this
    PermissionDeniedError  403 Forbidden            framework never emits this
    DomainError (other)    400 Bad Request          safety net

The mapping matches core/exceptions.py, kept in step deliberately: that file is
the contract both adapters read.

**Codes the framework generates by itself**, which our own errors must not be
confused with: 422 (request does not match the schema), 404 (no route matched),
405 (wrong method), 500 (unhandled). Note that neither MCP nor Supabase appears
here - MCP is JSON-RPC with its own numeric codes, and we reach Postgres through
SQLAlchemy rather than PostgREST, so neither can put a status code on one of our
responses.

`ValidationError` was originally mapped to 422 and moved to 400 for exactly this
reason. 422 is FastAPI's, and sharing it would have put "not enough stock" -
a message for the shopkeeper - behind the same status code as "you posted a
string into an int field", which is a bug in the client.

### The one unavoidable overlap: 404

A missing product is a 404, and so is a typo in the URL. There is no better code
for either, and inventing one would be worse than the overlap.

So the discriminator is not the status code, it is the body. **Every** error
response from this API - ours and the framework's alike - has the same envelope
with an `error` field naming the specific failure:

    {"error": "NotFoundError",          "detail": "No product with id 42."}
    {"error": "RouteNotFound",          "detail": "Not Found"}
    {"error": "ValidationError",        "detail": "Cannot remove 5 of RICE-1: only 2 in stock."}
    {"error": "RequestValidationError", "detail": "sell_price: Input should be >= 0"}

A client switches on `error`, never on the status code alone. The two handlers
at the bottom of this file exist to bring FastAPI's and Starlette's own errors
into that envelope, so there is one error format in the whole API rather than
three.

### 403 vs 401

`PermissionDeniedError` is 403, never 401. 401 means "I do not know who you
are"; 403 means "I know, and no". By the time a service raises this, an Actor
exists - authentication already succeeded. Authentication failure will be
raised by `get_actor` in deps.py when there is a real auth provider, and that
one is a 401.
"""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.exceptions import (
    DomainError,
    DuplicateError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

# The mapping, as data rather than as five near-identical functions. Order is
# irrelevant here because FastAPI dispatches on the exact exception class it was
# registered against, not by scanning this in sequence.
_STATUS_BY_EXCEPTION: dict[type[DomainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    DuplicateError: status.HTTP_409_CONFLICT,
    ValidationError: status.HTTP_400_BAD_REQUEST,
    PermissionDeniedError: status.HTTP_403_FORBIDDEN,
    # The catch-all. A future domain exception that nobody remembered to map
    # lands here as a 400 rather than as a 500 with a stack trace - wrong-ish,
    # but honest: the request was bad, not the server.
    DomainError: status.HTTP_400_BAD_REQUEST,
}

# Names for the status codes Starlette raises on its own, so that its errors
# carry a discriminator too. Without this a routing 404 and a missing-product
# 404 are indistinguishable to a client, which is the single overlap we cannot
# design away by choosing a different status code.
_FRAMEWORK_ERROR_NAMES: dict[int, str] = {
    status.HTTP_404_NOT_FOUND: "RouteNotFound",
    status.HTTP_405_METHOD_NOT_ALLOWED: "MethodNotAllowed",
    status.HTTP_401_UNAUTHORIZED: "NotAuthenticated",
}


def install_error_handlers(app: FastAPI) -> None:
    """Register every exception handler on the app. Called once, from main.py.

    A function rather than a series of decorators at module scope, because
    decorators would need `app` to already exist here - and importing the app
    into this module while main.py imports this module is a circular import.
    Passing the app in sidesteps it entirely.
    """

    def _handler_for(status_code: int):
        """Build a handler that renders any DomainError with a fixed status.

        A function returning a function - a closure. `status_code` is captured
        from the enclosing call, so each generated handler remembers its own.
        The same pattern as a factory returning an arrow function in TypeScript.

        `async def` because Starlette awaits exception handlers. There is no
        actual I/O in here; it just has to be awaitable.
        """

        async def handler(request: Request, exc: Exception) -> JSONResponse:
            return JSONResponse(
                status_code=status_code,
                content={
                    # `type(exc).__name__` is the class name as a string:
                    # "NotFoundError". This is what the frontend switches on.
                    "error": type(exc).__name__,
                    # `str(exc)` is the message the service passed when raising.
                    # Those messages were written to be shown to a person - see
                    # services/products.py, e.g. "Cannot remove 5 of RICE-1:
                    # only 2 in stock." They contain no internals and no SQL.
                    "detail": str(exc),
                },
            )

        return handler

    for exception_class, status_code in _STATUS_BY_EXCEPTION.items():
        app.add_exception_handler(exception_class, _handler_for(status_code))

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Reshape FastAPI's own 422 into the envelope above.

        Without this the API returns two different error formats depending on
        whether the failure was structural or a business rule, and the frontend
        needs two code paths. `exc.errors()` is a list of dicts; we flatten it
        to one readable line per problem, keeping the field name so the client
        can point at the right input.
        """
        problems = []
        for error in exc.errors():
            # `loc` is a tuple like ("body", "sell_price"). The first element is
            # always the source, which is noise to the caller, so drop it.
            field = ".".join(str(part) for part in error["loc"][1:]) or "request"
            problems.append(f"{field}: {error['msg']}")

        return JSONResponse(
            # `_CONTENT`, not the older `_ENTITY`. Both constants are the
            # integer 422; RFC 9110 renamed only the reason phrase, from
            # "Unprocessable Entity" to "Unprocessable Content", and Starlette
            # followed by deprecating the old spelling. Nothing about the
            # response changes - the rename is taken because a deprecated name
            # eventually disappears, and this would then fail at import.
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "error": "RequestValidationError",
                "detail": "; ".join(problems),
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Bring Starlette's own errors into the same envelope.

        This covers the responses nothing in our code produces: an unmatched
        URL, a GET on a POST-only route. By default they come back as
        `{"detail": "Not Found"}` - a different shape from every other error
        this API returns, and with no way to tell a mistyped URL from a product
        that genuinely is not there.

        Naming them here means a client has exactly one error format and one
        field to switch on. `RouteNotFound` versus `NotFoundError` is the
        distinction that the shared 404 status code cannot express.

        Note this also catches `HTTPException` raised deliberately from our own
        code - `fastapi.HTTPException` subclasses this one. There is currently
        no such call anywhere in api/, and there should not be: raising an HTTP
        exception from a handler is how business logic starts leaking into the
        adapter. The domain exceptions above are the supported route.
        """
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": _FRAMEWORK_ERROR_NAMES.get(exc.status_code, "HTTPError"),
                "detail": str(exc.detail),
            },
            # Preserved because 405 responses carry a required `Allow` header,
            # and dropping it would make the response non-compliant.
            headers=getattr(exc, "headers", None),
        )
