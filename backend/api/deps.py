"""Dependencies - the things FastAPI supplies to a handler automatically.

### What a "dependency" is

If you have used Nest, this is its DI container, with one big difference: there
is no container and no module registration. A dependency is just a function.
You declare that a handler needs one by annotating a parameter with it, and
FastAPI calls it for you before the handler runs.

    def list_products(session: DbSession):   # <- FastAPI calls get_db() first
        ...

That is the whole mechanism. No `@Injectable()`, no provider array, no tokens.

### Why the session is injected rather than grabbed

A handler could call `SessionLocal()` itself. Injecting it instead buys two
things. First, teardown is guaranteed: the `yield` below means FastAPI closes
the session after the response is sent, even if the handler raised. Second,
tests can *override* the dependency - swap in a session bound to a rolled-back
transaction - without the handler knowing. That is the same trick
tests/conftest.py already uses at the service level.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from authn import verify_access_token
from core.actor import Actor, SystemActor
from core.config import settings
from core.database import SessionLocal
from core.exceptions import AuthenticationError

# `auto_error=False` matters. Left at its default, HTTPBearer raises its own
# bare 403 when the header is missing - the wrong status, and a response body
# that does not match the {"error": ..., "detail": ...} shape every other error
# in this API uses. Turning it off lets the header come back as None and puts
# the decision below, where AuthenticationError produces a proper 401.
_bearer = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    """One database session per request, closed when the request ends.

    Note this does NOT reuse `core.database.get_session`, even though the body
    is nearly identical. That one is decorated with `@contextmanager`, which
    turns it into an object you use with a `with` statement - and FastAPI wants
    the raw generator function, not the wrapped object. Passing the wrapped one
    to `Depends` fails in a confusing way, so we write the four lines out.

    `yield` rather than `return` is what makes this a *setup/teardown*
    dependency: everything before the yield runs before the handler, everything
    after runs once the response has been sent.

    There is no `commit()` here on purpose. Services own the commit - see
    services/products.py. If this dependency committed, it would commit whatever
    half-finished state a failing handler left behind.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_actor(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ] = None,
) -> Actor:
    """Who is making this request.

    The seam the whole Actor design was built around, now carrying its real
    load. Everything it does is confined to this function: read the bearer
    token, verify it, return an Actor carrying that user's permissions. No
    route handler and no service function changed when this landed, because
    they already took an Actor and already called `actor.can()`.

    The token's `sub` becomes the actor id, so `created_by` / `updated_by`
    record the OIDC subject of the person who actually did the thing - which
    was the point of the audit columns in the first place.

    `auth_enabled=False` restores the pre-gate-24 behaviour of handing out a
    SystemActor. That is for the test suite and for local work unrelated to
    auth; it must never be set in a deployed environment, and it defaults to
    True so that a missing setting fails closed.
    """
    if not settings.auth_enabled:
        # The id is "api" rather than "system" so an audited row still tells you
        # which front door wrote it - the MCP server uses "mcp".
        return SystemActor(actor_id="api")

    if credentials is None:
        raise AuthenticationError("Authorization header is missing.")

    return verify_access_token(credentials.credentials)


# `Annotated[X, Depends(f)]` reads as "an X, obtained by calling f". Naming the
# combination once here means handlers write `session: DbSession` instead of
# repeating `session: Session = Depends(get_db)` on every route - and the
# Annotated form is what current FastAPI docs recommend over the default-value
# form, because a real default value can then still be given if needed.
DbSession = Annotated[Session, Depends(get_db)]
CurrentActor = Annotated[Actor, Depends(get_actor)]
