"""The database connection: engine, session factory, and the ORM base class.

Three objects live here, and it is worth being clear on what each one is,
because tutorials tend to use them without explaining the difference.

  engine        Created ONCE for the whole program. It owns the connection
                pool - a set of live TCP connections to Postgres that get
                reused. Creating a connection is slow; the pool hides that.

  SessionLocal  A *factory*. Calling it (`SessionLocal()`) borrows a connection
                from the engine's pool and wraps it in a Session - a workspace
                for one unit of work, with its own transaction.

  Base          The parent class every ORM model inherits from. SQLAlchemy uses
                it as a registry: any class inheriting from Base gets collected,
                which is how Alembic later discovers what tables should exist.

The rule to internalise: **one engine per process, one session per request.**
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from core.config import settings

engine = create_engine(
    settings.database_url,
    # Prints every SQL statement when SQL_ECHO=true in .env.
    echo=settings.sql_echo,
    # Before handing out a pooled connection, send a cheap "are you alive?"
    # ping. Supabase's pooler drops idle connections, and without this the
    # first query after a quiet period fails with a stale-connection error.
    # Costs one round-trip; saves a class of intermittent bug.
    pool_pre_ping=True,
    # Keep 5 connections open, allow 5 more during a burst. The free Supabase
    # tier has a modest connection ceiling shared with its own services, so
    # being a good citizen here matters.
    pool_size=5,
    max_overflow=5,
    # Recycle a connection after 30 minutes rather than letting the pooler
    # close it out from under us.
    pool_recycle=1800,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models. See core/models.py."""


@contextmanager
def get_session() -> Iterator[Session]:
    """Open a session, and guarantee it gets closed.

    Usage:

        with get_session() as session:
            product = session.get(Product, 1)

    The `@contextmanager` decorator turns this generator into something usable
    with `with`. Everything before `yield` is setup; everything after is
    teardown, and `finally` means the teardown runs even if the body raised.

    Note what this does NOT do: it does not commit. Committing is a decision
    about business intent, so it belongs to the caller in services/, not to
    plumbing down here.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
