"""The shared error vocabulary.

This is a small file with an outsized architectural job, so it is worth being
explicit about why it exists.

`services/` must never know it is being called over HTTP. The moment a service
raises `HTTPException`, it has a FastAPI dependency baked into it, and the MCP
server can no longer reuse it - the whole services-first design collapses.

So services raise these plain Python exceptions instead, and each adapter
translates them into its own dialect:

    NotFoundError         ->  api/: HTTP 404      mcp_server/: "no such product"
    DuplicateError        ->  api/: HTTP 409      mcp_server/: "SKU already used"
    ValidationError       ->  api/: HTTP 400      mcp_server/: "invalid input"
    PermissionDeniedError ->  api/: HTTP 403      mcp_server/: "not allowed"

The translation happens once, in the adapter. The rule stays intact: knowledge
about the web lives only in code that talks to the web.

### Why ValidationError is 400 and not 422 (decided 2026-07-30)

422 was the obvious choice and is wrong here, because **FastAPI already owns
it**: a request whose JSON does not match the declared schema gets a 422 before
any of our code runs. Reusing it would put two unrelated failures behind one
status code - "not enough stock", which a shopkeeper should read, and "you sent
a string where a number belongs", which is a bug in the client. A frontend could
not tell them apart from the status line alone.

400 is free: nothing in FastAPI or Starlette generates it for a JSON API. 409
and 403 are likewise untouched by the framework. 404 is the one unavoidable
overlap - Starlette returns it when no route matches - and that is handled in
api/errors.py by giving every response, ours and the framework's, an `error`
field naming the specific failure. See the note there.

None of this applies to mcp_server/: MCP is JSON-RPC and has its own numeric
error codes, with no relationship to HTTP status. It translates these same four
exceptions into text a model can read.

Coming from TypeScript, this is the same shape as defining your own `Error`
subclasses in a domain package rather than throwing Nest's `NotFoundException`
from a service.
"""


class DomainError(Exception):
    """Base class for every error this application raises deliberately.

    Having a common parent means an adapter can write one `except DomainError`
    catch-all as a safety net, and still handle the specific subclasses above
    it for precise status codes.

    Note what inheriting from `Exception` (rather than `BaseException`) buys:
    `BaseException` also covers `KeyboardInterrupt` and `SystemExit`, which you
    never want to swallow. Subclassing `Exception` is the normal choice.
    """


class NotFoundError(DomainError):
    """The thing you asked for does not exist.

    Example: `get_product(session, actor, product_id=999)` where no such row is
    in the table.
    """


class DuplicateError(DomainError):
    """Creating this would violate a uniqueness rule.

    Example: creating a second product with an SKU that is already taken. Note
    we raise this from a deliberate pre-check in the service, rather than
    letting the database's UNIQUE constraint blow up - the constraint is still
    there as the real guarantee, but a service-level check produces a message a
    human can act on.
    """


class ValidationError(DomainError):
    """The input is structurally fine but breaks a business rule.

    Example: `adjust_stock` with a delta that would drive quantity_on_hand
    below zero.

    This is *not* for "you passed a string where an int was expected" - that is
    caught earlier, by Pydantic in the adapter, before the service is reached.
    """


class PermissionDeniedError(DomainError):
    """The caller is known, but is not allowed to do this.

    Raised when `actor.can(...)` returns False. Deliberately distinct from
    "not authenticated at all", which is the adapter's problem: by the time a
    service runs, an Actor already exists.
    """


class AuthenticationError(DomainError):
    """We do not know who is asking.

    The counterpart to PermissionDeniedError, and the distinction is worth
    holding onto because the two look similar and mean opposite things:

        AuthenticationError    no credential, or one we cannot trust  -> 401
        PermissionDeniedError  a credential we trust, lacking a right -> 403

    Only adapters raise this. A service never does: by the time service code
    runs it has been handed an Actor, so the question "who is this?" is already
    answered. That is why it lives here rather than in api/ - `mcp_server/`
    needs the same vocabulary, and neither adapter may import the other.

    Carrying it through the shared vocabulary also means the 401 response shape
    matches every other error the API returns, instead of being a special case
    that clients have to discriminate differently.
    """
