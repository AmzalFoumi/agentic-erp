"""The agent's own database connection: engine, session factory, ORM base.

Mirrors backend/core/database.py's three-object pattern (engine / SessionLocal
/ Base) on purpose - same reasoning, same shapes, so nothing here needs to be
re-learned. It is a *copy*, not an import, for the same reason agent/config.py
is a copy of backend/core/config.py: agent/ is a separate process with a
separate venv that must not import backend/ code (docs/AGENT-PLAN.md,
"Architecture").

**Base.metadata.schema = "agent" is the load-bearing line in this file.**
Every table declared against this Base is schema-qualified in the Python
model itself - `agent.conversations`, not `conversations` - independent of
the connecting role's `search_path`. This is one of Gate 18's two explicit
isolation guards (the other is backend/alembic/env.py's include_schemas=False);
see docs/superpowers/specs/2026-08-12-gate-18-persistence-design.md.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    pool_recycle=1800,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for the agent's ORM models. See agent/models.py.

    metadata=MetaData(schema="agent") means every table this Base collects is
    created as agent.<table>, explicitly, in code - not by relying on the
    connecting role's search_path defaulting to "agent" or "public, agent".
    """

    metadata = MetaData(schema="agent")


@contextmanager
def get_session() -> Iterator[Session]:
    """Open a session, and guarantee it gets closed. See core/database.py's
    get_session() for the full reasoning - this is the same contract."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
