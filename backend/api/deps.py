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
from sqlalchemy.orm import Session

from core.actor import Actor, SystemActor
from core.database import SessionLocal


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


def get_actor() -> Actor:
    """Who is making this request.

    A placeholder, and deliberately an obvious one. There is no auth provider
    yet - that decision is deferred, see docs/PLAN.md - so every HTTP caller is
    currently the same all-powerful `SystemActor`.

    The reason this exists *now*, before it does anything useful, is that it is
    the seam. When a real auth provider lands, the change is confined to this
    one function: read the bearer token, validate it, return an Actor carrying
    that user's permissions. Not one handler and not one service function
    changes, because they already take an Actor and already call `actor.can()`.
    Retrofitting that later would mean touching every signature in the codebase.

    The id is "api" rather than "system" so that an audited row tells you which
    front door wrote it - the MCP server will use "mcp".
    """
    return SystemActor(actor_id="api")


# `Annotated[X, Depends(f)]` reads as "an X, obtained by calling f". Naming the
# combination once here means handlers write `session: DbSession` instead of
# repeating `session: Session = Depends(get_db)` on every route - and the
# Annotated form is what current FastAPI docs recommend over the default-value
# form, because a real default value can then still be given if needed.
DbSession = Annotated[Session, Depends(get_db)]
CurrentActor = Annotated[Actor, Depends(get_actor)]
