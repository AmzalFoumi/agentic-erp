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

### The status codes

    NotFoundError          404 Not Found
    DuplicateError         409 Conflict
    ValidationError        422 Unprocessable Entity
    PermissionDeniedError  403 Forbidden
    DomainError (other)    400 Bad Request        <- safety net

The mapping is the one already written into core/exceptions.py, kept in step
deliberately: that file is the contract both adapters read.

One wrinkle worth knowing. FastAPI already uses **422** for its own request
validation - the error you get for posting `"abc"` into an int field. So 422
now carries two quite different meanings: "your JSON was the wrong shape"
(a bug in the client) and "not enough stock" (a thing to show the user).

Rather than pick a different code and diverge from core/exceptions.py, we make
the two distinguishable in the body: every error response from this API has the
same envelope, with an `error` field naming the exception class. A client
switches on `error`, not on the status code alone:

    {"error": "ValidationError",        "detail": "Cannot remove 5 of RICE-1: only 2 in stock."}
    {"error": "RequestValidationError", "detail": "sell_price: Input should be greater than or equal to 0"}

That also means FastAPI's built-in 422 gets reshaped below, so the frontend has
exactly one error format to handle instead of two.

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
    ValidationError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    PermissionDeniedError: status.HTTP_403_FORBIDDEN,
    # The catch-all. A future domain exception that nobody remembered to map
    # lands here as a 400 rather than as a 500 with a stack trace - wrong-ish,
    # but honest: the request was bad, not the server.
    DomainError: status.HTTP_400_BAD_REQUEST,
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "RequestValidationError",
                "detail": "; ".join(problems),
            },
        )
