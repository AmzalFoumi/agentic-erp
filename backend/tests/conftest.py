"""Shared test fixtures. pytest imports this file automatically.

`conftest.py` is a pytest convention, not something you import: any test module
in this directory or below can request a fixture defined here just by naming it
as a parameter. Closest Jest analogue is a `setupFilesAfterEach` module, except
the injection is per-parameter rather than global.

### The problem this file solves

We have exactly one database - the live Supabase project. There is no local
Postgres. So a test that calls `create_product(...)` writes a real row to the
real database and leaves it there forever. Run the suite twice and the
duplicate-SKU test fails against leftovers from its own previous run, which is
the worst kind of failing test: correct code, red bar, no bug.

### The fix

Each test runs inside a transaction that is **always rolled back**, whatever
happens. The database sees the writes while the test runs, so foreign keys,
constraints and defaults all behave exactly as in production, and then the
whole thing is discarded.

The wrinkle is that our service functions call `session.commit()` themselves -
deliberately, see services/products.py - and a naive outer transaction would be
ended by the first of those commits. SQLAlchemy 2.0 has a purpose-built answer:
`join_transaction_mode="create_savepoint"`. The session joins the connection's
existing transaction, and each `commit()` inside the test releases a SAVEPOINT
rather than committing for real. The outer `rollback()` in teardown still undoes
everything.

TypeScript analogue: wrapping each Jest test in a Prisma `$transaction` whose
callback always throws at the end so it never commits.

### Worth revisiting

The more thorough answer is a dedicated test database, so the suite cannot
touch production data even in principle. That means a second Supabase project
(or Docker Postgres locally) and a `TEST_DATABASE_URL`. Not worth it for four
tests; worth it the moment the suite grows or anyone else runs it. Noted in
docs/PLAN.md.
"""

from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.orm import Session

from core.actor import SystemActor
from core.database import engine

if TYPE_CHECKING:
    # Imported for the type annotation only. `TYPE_CHECKING` is False at
    # runtime, so this line never executes - it exists so a type checker and an
    # editor can resolve `TestClient` without the import happening for real.
    from fastapi.testclient import TestClient


@pytest.fixture
def session() -> Iterator[Session]:
    """A Session whose writes are all undone when the test finishes.

    The `yield` splits the fixture: everything above it is setup, the test runs
    at the yield, and everything below is teardown - the same shape as the
    `@contextmanager` in core/database.py.

    `finally` matters here. Teardown must run even when the test fails, or one
    failing test leaves rows behind and poisons every run after it.
    """
    connection = engine.connect()
    transaction = connection.begin()

    # Bound to the *connection*, not the engine - that is what puts the session
    # inside the transaction opened above rather than in one of its own.
    db = Session(bind=connection, join_transaction_mode="create_savepoint")

    try:
        yield db
    finally:
        db.close()
        # Unconditional. There is no code path in this file that commits.
        transaction.rollback()
        connection.close()


@pytest.fixture
def actor() -> SystemActor:
    """The caller identity every service function takes as its second argument.

    A SystemActor permits everything, so these tests exercise business rules,
    not authorization. Once a real Actor implementation exists, the
    permission-denied cases get their own fixture and their own tests.
    """
    return SystemActor(actor_id="pytest")


@pytest.fixture
def client(session: Session) -> Iterator["TestClient"]:
    """A test client for the FastAPI app, sharing this test's rolled-back session.

    `TestClient` calls the application in-process. No port is opened, no uvicorn
    starts, nothing is listening - it drives the ASGI app directly and hands
    back a real response object. Roughly supertest against an Express app.

    The important line is `dependency_overrides`. Normally a request gets its
    session from `api.deps.get_db`, which opens a fresh one against the engine -
    and that session would be outside this test's transaction, so its writes
    would be committed for real and survive the rollback. Overriding the
    dependency hands every request the *same* savepoint-bound session the
    service tests use, so HTTP tests are as disposable as the rest.

    This is the payoff for injecting the session rather than reaching for it
    inside the handlers: the swap happens without a single line of api/ knowing
    it is under test.

    `actor` is overridden too, so audit columns read "pytest" rather than "api",
    and so the day a real auth dependency lands here, these tests do not all
    start failing on a missing token.
    """
    from fastapi.testclient import TestClient

    from api.deps import get_actor, get_db
    from api.main import app

    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_actor] = lambda: SystemActor(actor_id="pytest")
    try:
        yield TestClient(app)
    finally:
        # `app` is a module-level singleton, so an override left behind would
        # leak into every later test in the run.
        app.dependency_overrides.clear()


@pytest.fixture
def unique_sku() -> str:
    """An SKU no other test - or previous run - will have used.

    Belt and braces. The rollback above should make this unnecessary, but if a
    fixture ever leaks, a collision here would look like a bug in
    `create_product` rather than a bug in the test setup. `uuid4` is imported
    locally because this is the only fixture that needs it.
    """
    from uuid import uuid4

    return f"TEST-{uuid4().hex[:12].upper()}"
