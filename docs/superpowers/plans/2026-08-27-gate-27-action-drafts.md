# Gate 27 — Action Draft engine, implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the staging queue where the agent writes down what it wants to do and a human approves it, with a draft type system that can never become "run arbitrary code".

**Architecture:** One table (`action_drafts`) holding a JSON payload plus provenance. A closed registry maps each `draft_type` to one Pydantic schema and one hand-written handler; a type with no registry entry cannot execute. Payloads are validated on creation *and* re-validated at approval, because a manager may edit them in between. Business logic in `services/drafts.py`, exposed by both adapters unchanged in shape from `products.py`.

**Tech Stack:** SQLAlchemy 2.0, Alembic, Pydantic v2, FastAPI, MCP Python SDK 2.0.0, Next.js 16 App Router.

**Spec:** `docs/FEATURES-PLAN.md` (owns gates 27–30). Read its "four decisions" section before starting.

## Global Constraints

- `services/` and `core/` must not import `fastapi`, `starlette`, `mcp`, `uvicorn`, `httpx` or `jwt`. Verified by `lint-imports` from `backend/`. **Pydantic is allowed** — `core/config.py` already uses it.
- Every service function: `session` first, `actor` second, everything else keyword-only.
- Every write calls `actor.can(...)` first via `_require`, and raises `PermissionDeniedError`.
- Failure is an exception from `core/exceptions.py` — never `None`, never `False`.
- Services call `session.commit()` themselves.
- Money is `Numeric(10, 2)` in the database and `Decimal` in Python. Never `float`. Pydantic serialises `Decimal` to a JSON **string**, which is intended.
- Timestamps are `DateTime(timezone=True)`, never naive.
- Every new table gets `ENABLE ROW LEVEL SECURITY` **inside its create migration** — that is this project's pattern, see `20260730_0838` for products.
- New permissions this gate: `draft.read`, `draft.create`, `draft.decide`. No others.
- Tests never use a separate database; `tests/conftest.py`'s `session` fixture rolls everything back.

---

### Task 1: `ClientType` and `DraftStatus` vocabulary

**Files:**
- Create: `backend/core/enums.py`
- Test: `backend/tests/test_drafts.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ClientType.WEB_UI`, `ClientType.MCP_AGENT`, `ClientType.SYSTEM`, `DraftStatus.PENDING/APPROVED/REJECTED/EXECUTED`. Both are `str` enums, so `ClientType.WEB_UI == "web_ui"` is True and SQLAlchemy stores the plain string.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_drafts.py
"""Tests for the Action Draft engine (gate 27)."""

from core.enums import ClientType, DraftStatus


def test_client_type_values_are_the_stored_strings():
    """The enum members ARE their database values.

    Subclassing `str` means no conversion layer between Python and the column,
    and no risk of storing `ClientType.WEB_UI` (which would stringify to
    "ClientType.WEB_UI" in some contexts) instead of "web_ui".
    """
    assert ClientType.WEB_UI == "web_ui"
    assert ClientType.MCP_AGENT == "mcp_agent"
    assert ClientType.SYSTEM == "system"


def test_draft_status_values_are_the_stored_strings():
    assert DraftStatus.PENDING == "pending"
    assert DraftStatus.APPROVED == "approved"
    assert DraftStatus.REJECTED == "rejected"
    assert DraftStatus.EXECUTED == "executed"


def test_there_is_no_expired_status():
    """Expiry is computed when a draft is read, never stored.

    Nothing in this project schedules anything, so a stored EXPIRED status
    would only ever be set by whoever happened to read the row next - which is
    the same work as computing it, plus a write. See docs/FEATURES-PLAN.md.
    """
    assert not hasattr(DraftStatus, "EXPIRED")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_drafts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.enums'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/core/enums.py
"""Closed vocabularies shared by every layer.

An enum lives here rather than in a service when both adapters and the database
need to agree on the same set of strings. `core/` is the only package both
adapters may import, so it is the only place that agreement can be expressed
once.

Every enum here subclasses `str`. That is not decoration: it means a member IS
its stored value, so SQLAlchemy writes "web_ui" without a converter, Pydantic
serialises it without a converter, and a comparison against a plain string from
the database works. The alternative - a plain `Enum` - stores fine and then
fails the first time something compares a loaded row against a literal.
"""

from enum import Enum


class ClientType(str, Enum):
    """Which front door an action came through.

    This exists because `Actor` deliberately does not know. `Actor` has exactly
    `id` and `can()`, and the entire architecture rests on services/ not being
    able to tell HTTP from MCP. But provenance genuinely needs the answer, so
    the adapter - which knows for certain what it is - passes it as an ordinary
    argument.

    There is a second, subtler reason it cannot be derived from the actor: when
    the AI agent acts, it carries a *narrowed copy of the user's own token*, so
    `actor.id` is the human being in both cases. The door is the only thing
    that differs, and only the door knows.
    """

    WEB_UI = "web_ui"
    MCP_AGENT = "mcp_agent"
    # Migrations, seed scripts, and anything with no human behind it.
    SYSTEM = "system"


class DraftStatus(str, Enum):
    """Where an Action Draft is in its life.

    PENDING  - proposed, waiting for a human
    APPROVED - a human said yes; the handler has not finished yet
    REJECTED - a human said no. Terminal
    EXECUTED - the handler ran and the change is real. Terminal

    **There is deliberately no EXPIRED.** A draft carries `expires_at`, and
    whether it has passed is computed when the row is read. Storing it would
    need something to do the storing, and this project has no scheduler.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_drafts.py -v`
Expected: PASS, 3 tests

- [ ] **Step 5: Verify the architecture boundary still holds**

Run: `cd backend && lint-imports`
Expected: `Contracts: 4 kept, 0 broken.`

- [ ] **Step 6: Commit**

```bash
git add backend/core/enums.py backend/tests/test_drafts.py
git commit -m "feat(drafts): add ClientType and DraftStatus vocabularies"
```

---

### Task 2: `ActionDraft` model and its migration

**Files:**
- Modify: `backend/core/models.py` (append a class; do not touch `Product`)
- Create: `backend/alembic/versions/<generated>_create_action_drafts_table.py`
- Test: `backend/tests/test_drafts.py`

**Interfaces:**
- Consumes: `ClientType`, `DraftStatus` from Task 1.
- Produces: `core.models.ActionDraft` with columns `id, draft_type, status, payload, reasoning, cost_at_risk, projected_recovery, expires_at, created_at, updated_at, created_by, created_via, decided_by, decided_at, decided_via`, and a property `is_expired -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_drafts.py
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from core.models import ActionDraft


def test_draft_defaults_to_pending_and_is_not_expired(session):
    draft = ActionDraft(
        draft_type="TEST_NOOP",
        payload={"note": "hello"},
        reasoning="because",
        created_by="pytest",
        created_via=ClientType.WEB_UI,
    )
    session.add(draft)
    session.flush()

    assert draft.id is not None
    assert draft.status == DraftStatus.PENDING
    assert draft.is_expired is False


def test_draft_with_a_past_expiry_reports_expired(session):
    draft = ActionDraft(
        draft_type="TEST_NOOP",
        payload={},
        reasoning="because",
        created_by="pytest",
        created_via=ClientType.WEB_UI,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    session.add(draft)
    session.flush()

    assert draft.is_expired is True


def test_money_columns_keep_full_precision(session):
    """Numeric(10,2), not float. 0.1 + 0.2 must not become 0.30000000000000004."""
    draft = ActionDraft(
        draft_type="TEST_NOOP",
        payload={},
        reasoning="because",
        created_by="pytest",
        created_via=ClientType.WEB_UI,
        cost_at_risk=Decimal("40000.50"),
        projected_recovery=Decimal("12000.25"),
    )
    session.add(draft)
    session.flush()
    session.refresh(draft)

    assert draft.cost_at_risk == Decimal("40000.50")
    assert draft.projected_recovery == Decimal("12000.25")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_drafts.py -v`
Expected: FAIL — `ImportError: cannot import name 'ActionDraft' from 'core.models'`

- [ ] **Step 3: Write the model**

Append to `backend/core/models.py` (keep the existing `Product` class untouched):

```python
class ActionDraft(Base):
    """A proposed change, waiting for a human to approve it.

    The agent does not change prices, raise purchase orders or issue credits.
    It writes down what it *wants* to do, with its reasoning and the money at
    stake, and a manager reads it and presses a button. See
    docs/FEATURES-PLAN.md, decision 1, for why this coexists with gate 19's
    in-conversation approval rather than replacing it.

    **`draft_type` is a name from a closed list, never a function.** The
    registry in `services/draft_types.py` maps it to one schema and one
    hand-written handler. This is the whole security design of the gate: if a
    row could name a function, anyone who could write a row could call anything.
    """

    __tablename__ = "action_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Not a database ENUM type. A Postgres enum needs a migration to add a
    # value, and gates 28-30 each add one; a checked string keeps that a
    # one-line change. The real gate is the registry, not the column type.
    draft_type: Mapped[str] = mapped_column(String(64), index=True)

    status: Mapped[str] = mapped_column(
        String(16), default=DraftStatus.PENDING, index=True
    )

    # JSONB, not JSON: Postgres stores it decomposed, so it can be indexed and
    # queried. The shape is decided per draft_type by that type's Pydantic
    # schema - deliberately not by this column, because three different shapes
    # share this table.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)

    # The agent's own words, for the human reading the card. Text, not
    # String(n): a model writing a summary should not hit a length limit and
    # get truncated mid-sentence.
    reasoning: Mapped[str] = mapped_column(Text)

    # --- the two money figures -------------------------------------------
    #
    # Two columns rather than one net figure, on purpose. "We saved 12,000" and
    # "we were about to lose 40,000 and recovered 12,000" are different
    # sentences to a manager, and a single number cannot tell them apart.
    # Nullable because not every draft type has a financial dimension.
    cost_at_risk: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), default=None
    )
    projected_recovery: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), default=None
    )

    # Null means "never expires". See DraftStatus for why this is a timestamp
    # compared on read rather than a status somebody has to write.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    # --- provenance -------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[str] = mapped_column(String(128))
    created_via: Mapped[str] = mapped_column(String(16))

    # Null until somebody decides. `decided_via` records which door the
    # DECISION came through, which is not necessarily the door the proposal
    # came through - the agent proposes, a human in the browser approves, and
    # that difference is the point of the whole feature.
    decided_by: Mapped[str | None] = mapped_column(String(128), default=None)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    decided_via: Mapped[str | None] = mapped_column(String(16), default=None)

    @property
    def is_expired(self) -> bool:
        """True when this draft's deadline has passed.

        A plain `@property`, not a `hybrid_property` like `Product.needs_reorder`.
        The difference matters and the choice is deliberate: a hybrid also
        compiles to SQL so the database can filter on it, which `needs_reorder`
        genuinely needs. Expiry does not - drafts are few, and the pending list
        is already small enough to read. A hybrid here would mean writing the
        rule twice (Python and SQL) for no benefit.

        `datetime.now(timezone.utc)` and not `datetime.now()`: the column is
        TIMESTAMPTZ, so the value loaded back is timezone-aware, and comparing
        an aware datetime with a naive one raises TypeError.
        """
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) >= self.expires_at

    def __repr__(self) -> str:
        return (
            f"ActionDraft(id={self.id!r}, type={self.draft_type!r}, "
            f"status={self.status!r})"
        )
```

Add to the imports at the top of `core/models.py`:

```python
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from core.enums import ClientType, DraftStatus  # noqa: F401  (ClientType used by callers)
```

- [ ] **Step 4: Generate the migration**

⚠️ **Developer runs this**, from `backend/` with the venv active:

```bash
alembic revision --autogenerate -m "create action_drafts table"
```

Autogenerate compares `core/models.py` against the live database and writes the `create_table` call. It will **not** write the RLS line — row-level security is not a column, so it is invisible to autogenerate. Add it by hand.

- [ ] **Step 5: Add RLS to the generated migration by hand**

In the generated file, append to `upgrade()` and `downgrade()`:

```python
def upgrade() -> None:
    # ... the autogenerated op.create_table('action_drafts', ...) stays here ...

    # Deny-all backstop. Authorization is enforced in services/, not in RLS
    # policies - RLS exists so that a future bug or a leaked anon key cannot
    # read or write silently. Same pattern as the products table; see
    # 20260730_0838. Our own connection is unaffected: the table owner
    # bypasses RLS.
    op.execute("ALTER TABLE action_drafts ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.execute("ALTER TABLE action_drafts DISABLE ROW LEVEL SECURITY;")
    # ... the autogenerated op.drop_table('action_drafts') stays here ...
```

- [ ] **Step 6: Apply the migration**

⚠️ **Developer runs this.** It writes to the shared Supabase database.

```bash
alembic upgrade head
```

Expected: `Running upgrade a1c4e7b2f019 -> <new hash>, create action_drafts table`

- [ ] **Step 7: Run the tests**

Run: `cd backend && pytest tests/test_drafts.py -v`
Expected: PASS, 6 tests

- [ ] **Step 8: Commit**

```bash
git add backend/core/models.py backend/alembic/versions/ backend/tests/test_drafts.py
git commit -m "feat(drafts): add the action_drafts table with RLS enabled"
```

---

### Task 3: The draft type registry — the security core of this gate

**Files:**
- Create: `backend/services/draft_types.py`
- Test: `backend/tests/test_draft_types.py`

**Interfaces:**
- Consumes: `core.exceptions.ValidationError`.
- Produces:
  - `DraftHandler = Callable[[Session, Actor, ClientType, BaseModel], None]`
  - `register(draft_type: str, *, schema: type[BaseModel], handler: DraftHandler) -> None`
  - `spec_for(draft_type: str) -> DraftTypeSpec` — raises `ValidationError` for an unknown type
  - `validate_payload(draft_type: str, payload: dict) -> BaseModel` — raises `ValidationError` on a bad shape
  - `registered_types() -> frozenset[str]`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_draft_types.py
"""The registry is the reason a draft row cannot become arbitrary code.

Read docs/FEATURES-PLAN.md, table row 1. The externally-written spec had the
payload carry "target service function names and arguments". Looking a function
up by a name held in a database row means anyone who can write a row can call
anything with anything. These tests pin the replacement shut.
"""

import pytest
from pydantic import BaseModel

from core.exceptions import ValidationError
from services import draft_types


class _NoopPayload(BaseModel):
    product_id: int
    note: str = ""


def _noop_handler(session, actor, client, payload):
    """A handler that does nothing, for testing the machinery around it."""
    return None


@pytest.fixture(autouse=True)
def _clean_registry():
    """Register a test type, and remove it afterwards.

    The registry is module-level state, so a type left behind would leak into
    every later test in the run - the same reasoning as the
    `app.dependency_overrides.clear()` in conftest.py's client fixture.
    """
    draft_types.register("TEST_NOOP", schema=_NoopPayload, handler=_noop_handler)
    yield
    draft_types._REGISTRY.pop("TEST_NOOP", None)


def test_unknown_draft_type_is_refused():
    """The property the whole gate exists for."""
    with pytest.raises(ValidationError) as exc:
        draft_types.spec_for("DROP_EVERYTHING")

    # The message names the type but does NOT list the registered ones -
    # an error that enumerates what IS allowed is a map for whoever is probing.
    assert "DROP_EVERYTHING" in str(exc.value)
    assert "TEST_NOOP" not in str(exc.value)


def test_a_registered_type_resolves_to_its_schema_and_handler():
    spec = draft_types.spec_for("TEST_NOOP")

    assert spec.schema is _NoopPayload
    assert spec.handler is _noop_handler


def test_payload_is_validated_against_the_type_schema():
    validated = draft_types.validate_payload("TEST_NOOP", {"product_id": 42})

    assert isinstance(validated, _NoopPayload)
    assert validated.product_id == 42
    assert validated.note == ""


def test_a_payload_of_the_wrong_shape_is_refused():
    with pytest.raises(ValidationError):
        draft_types.validate_payload("TEST_NOOP", {"product_id": "not a number"})


def test_a_payload_for_an_unknown_type_is_refused():
    """Validation must not succeed just because the dict looks plausible."""
    with pytest.raises(ValidationError):
        draft_types.validate_payload("DROP_EVERYTHING", {"product_id": 42})


def test_registering_the_same_type_twice_is_refused():
    """A silent overwrite would let a later import replace a handler."""
    with pytest.raises(ValidationError):
        draft_types.register(
            "TEST_NOOP", schema=_NoopPayload, handler=_noop_handler
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_draft_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.draft_types'`

- [ ] **Step 3: Write the registry**

```python
# backend/services/draft_types.py
"""What a draft is allowed to be, and what running it actually does.

### The threat this file removes

The feature set this gate implements was specified outside this repository, and
it had the draft payload carry "target service function names and arguments".
That reads as convenient and is a remote-code-execution shape: if the executor
resolves a function from a string held in a database row, then anyone who can
write a row - the agent, a bug, a compromised token - can call anything in the
codebase with anything.

So a draft names a **type**, and a type is looked up in a registry that only
this application's own source code can add to. A type nobody registered does
not exist and cannot run. The worst a malicious row can do is name a type that
is refused.

### Why Pydantic is allowed here

`services/` is barred from importing fastapi, starlette, mcp, uvicorn, httpx
and jwt - the web frameworks and the transport credential. Pydantic is none of
those; it is a validation library with no web concepts, and `core/config.py`
already depends on it. `lint-imports` agrees. Using it here means the payload
shape is declared once, in the same language as the rest of the domain.

### Registration happens at import time

Each feature gate registers its own type in its own module - gate 28 registers
BATCH_PRICE_MARKDOWN in services/spoilage.py - and `services/__init__.py`
imports those modules so the registration runs. Gate 27 registers nothing: the
engine ships empty, and the first real type arrives with the first real
feature.
"""

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from core.actor import Actor
from core.enums import ClientType
from core.exceptions import ValidationError

# What a handler is. It receives an already-validated payload object, never a
# raw dict, so a handler never has to ask whether a field is present.
#
# It returns None. A handler's effect is the database rows it writes, and the
# draft row itself is updated by services/drafts.py, not by the handler - so
# there is nothing meaningful for it to hand back, and a return value would
# only invite callers to depend on one.
DraftHandler = Callable[[Session, Actor, ClientType, BaseModel], None]


@dataclass(frozen=True)
class DraftTypeSpec:
    """The two things a draft type is: a shape, and something that runs it.

    `frozen=True` makes instances immutable, so a registered spec cannot be
    mutated in place by anything that gets hold of it.
    """

    schema: type[BaseModel]
    handler: DraftHandler


# Module-level and deliberately private. The only supported way in is
# `register()`, which refuses to overwrite - see below.
_REGISTRY: dict[str, DraftTypeSpec] = {}


def register(
    draft_type: str, *, schema: type[BaseModel], handler: DraftHandler
) -> None:
    """Add a draft type. Refuses to replace one that already exists.

    The refusal matters more than it looks. Registration happens as a side
    effect of importing a module, and import order is not something anyone
    reasons about carefully. A silent overwrite would mean the handler that
    runs depends on which module was imported last - so a second registration
    of the same name is a programming error, and is raised as one at startup
    rather than discovered later in production.
    """
    if draft_type in _REGISTRY:
        raise ValidationError(f"Draft type {draft_type!r} is already registered.")
    _REGISTRY[draft_type] = DraftTypeSpec(schema=schema, handler=handler)


def registered_types() -> frozenset[str]:
    """Every draft type this build knows about. For diagnostics and tests."""
    return frozenset(_REGISTRY)


def spec_for(draft_type: str) -> DraftTypeSpec:
    """The schema and handler for `draft_type`, or raise.

    ⚠️ The error message names the type that was asked for and does NOT list
    the ones that exist. Enumerating the valid set in an error handed back to a
    caller is a map for whoever is probing - the same reasoning that makes
    gate 24's authentication failures refuse to say *why* they failed.
    """
    spec = _REGISTRY.get(draft_type)
    if spec is None:
        raise ValidationError(f"Unknown draft type {draft_type!r}.")
    return spec


def validate_payload(draft_type: str, payload: dict) -> BaseModel:
    """Check `payload` against `draft_type`'s schema and return the parsed object.

    Called twice in a draft's life, and the second call is the important one:
    once when the draft is created, and again when it is approved - because a
    manager can edit the payload in between. Validating only on the way in
    would mean the schema guarded the agent and never the browser.

    Pydantic's own ValidationError is translated into ours. Letting it escape
    would put a third-party exception type into the vocabulary that
    `api/errors.py` and `mcp_server/errors.py` translate, and neither adapter
    knows what to do with it.
    """
    spec = spec_for(draft_type)
    try:
        return spec.schema.model_validate(payload)
    except PydanticValidationError as exc:
        raise ValidationError(
            f"Payload does not match the shape of {draft_type!r}: {exc.error_count()} problem(s)."
        ) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_draft_types.py -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Verify the boundary**

Run: `cd backend && lint-imports`
Expected: `Contracts: 4 kept, 0 broken.` — this is the check that Pydantic in `services/` is genuinely allowed rather than merely unnoticed.

- [ ] **Step 6: Commit**

```bash
git add backend/services/draft_types.py backend/tests/test_draft_types.py
git commit -m "feat(drafts): add the closed draft-type registry"
```

---

### Task 4: `services/drafts.py` — the business logic

**Files:**
- Create: `backend/services/drafts.py`
- Test: `backend/tests/test_drafts.py` (append)

**Interfaces:**
- Consumes: `ActionDraft`, `ClientType`, `DraftStatus`, `draft_types.validate_payload`, `draft_types.spec_for`.
- Produces:
  - `create_draft(session, actor, *, client, draft_type, payload, reasoning, cost_at_risk=None, projected_recovery=None, expires_in_hours=DEFAULT_EXPIRY_HOURS) -> ActionDraft`
  - `list_drafts(session, actor, *, status=None, limit=50, offset=0) -> list[ActionDraft]`
  - `count_drafts(session, actor, *, status=None) -> int`
  - `get_draft(session, actor, *, draft_id) -> ActionDraft`
  - `approve_draft(session, actor, *, client, draft_id, payload=None) -> ActionDraft`
  - `reject_draft(session, actor, *, client, draft_id) -> ActionDraft`
  - Constant `DEFAULT_EXPIRY_HOURS = 24`

- [ ] **Step 1: Write the failing tests**

```python
# append to backend/tests/test_drafts.py
import pytest
from pydantic import BaseModel

from core.actor import TokenActor
from core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from services import draft_types, drafts


class _MarkPayload(BaseModel):
    product_id: int
    new_price: str


@pytest.fixture
def noop_type():
    """A registered draft type whose handler records that it ran."""
    calls = []

    def handler(session, actor, client, payload):
        calls.append((actor.id, client, payload.product_id))

    draft_types.register("TEST_MARK", schema=_MarkPayload, handler=handler)
    yield calls
    draft_types._REGISTRY.pop("TEST_MARK", None)


@pytest.fixture
def manager():
    return TokenActor("manager-1", frozenset({"draft.read", "draft.create", "draft.decide"}))


@pytest.fixture
def robot():
    """An actor with the agent's real permission set: it may propose, not decide."""
    return TokenActor("robot-1", frozenset({"draft.read", "draft.create"}))


def _make(session, actor, **kw):
    return drafts.create_draft(
        session,
        actor,
        client=ClientType.MCP_AGENT,
        draft_type="TEST_MARK",
        payload={"product_id": 1, "new_price": "9.99"},
        reasoning="milk expires tomorrow",
        **kw,
    )


def test_create_records_who_proposed_and_through_which_door(session, robot, noop_type):
    draft = _make(session, robot)

    assert draft.status == DraftStatus.PENDING
    assert draft.created_by == "robot-1"
    assert draft.created_via == ClientType.MCP_AGENT
    assert draft.decided_by is None


def test_create_refuses_an_unknown_draft_type(session, robot):
    with pytest.raises(ValidationError):
        drafts.create_draft(
            session,
            robot,
            client=ClientType.MCP_AGENT,
            draft_type="DROP_EVERYTHING",
            payload={},
            reasoning="trust me",
        )


def test_create_refuses_a_payload_of_the_wrong_shape(session, robot, noop_type):
    with pytest.raises(ValidationError):
        drafts.create_draft(
            session,
            robot,
            client=ClientType.MCP_AGENT,
            draft_type="TEST_MARK",
            payload={"product_id": "not a number", "new_price": "9.99"},
            reasoning="oops",
        )


def test_create_requires_the_create_permission(session, noop_type):
    nobody = TokenActor("nobody", frozenset())
    with pytest.raises(PermissionDeniedError):
        _make(session, nobody)


def test_the_agent_cannot_approve_its_own_draft(session, robot, noop_type):
    """The security property decision 1 in FEATURES-PLAN.md exists to create."""
    draft = _make(session, robot)

    with pytest.raises(PermissionDeniedError):
        drafts.approve_draft(
            session, robot, client=ClientType.MCP_AGENT, draft_id=draft.id
        )

    session.refresh(draft)
    assert draft.status == DraftStatus.PENDING


def test_approve_runs_the_handler_and_records_the_decider(session, robot, manager, noop_type):
    draft = _make(session, robot)

    approved = drafts.approve_draft(
        session, manager, client=ClientType.WEB_UI, draft_id=draft.id
    )

    assert approved.status == DraftStatus.EXECUTED
    assert approved.decided_by == "manager-1"
    assert approved.decided_via == ClientType.WEB_UI
    assert approved.decided_at is not None
    # The handler actually ran, with the approving manager as the actor -
    # not the agent that proposed it.
    assert noop_type == [("manager-1", ClientType.WEB_UI, 1)]


def test_approve_revalidates_a_payload_the_manager_edited(session, robot, manager, noop_type):
    """The second validation. A manager may edit before approving."""
    draft = _make(session, robot)

    with pytest.raises(ValidationError):
        drafts.approve_draft(
            session,
            manager,
            client=ClientType.WEB_UI,
            draft_id=draft.id,
            payload={"product_id": "still not a number", "new_price": "9.99"},
        )

    session.refresh(draft)
    assert draft.status == DraftStatus.PENDING
    assert noop_type == []


def test_an_edited_payload_is_what_actually_runs(session, robot, manager, noop_type):
    draft = _make(session, robot)

    drafts.approve_draft(
        session,
        manager,
        client=ClientType.WEB_UI,
        draft_id=draft.id,
        payload={"product_id": 99, "new_price": "1.00"},
    )

    assert noop_type == [("manager-1", ClientType.WEB_UI, 99)]
    session.refresh(draft)
    assert draft.payload["product_id"] == 99


def test_an_expired_draft_cannot_be_approved(session, robot, manager, noop_type):
    draft = _make(session, robot, expires_in_hours=0)

    with pytest.raises(ValidationError) as exc:
        drafts.approve_draft(
            session, manager, client=ClientType.WEB_UI, draft_id=draft.id
        )

    assert "expired" in str(exc.value).lower()
    assert noop_type == []


def test_a_draft_cannot_be_approved_twice(session, robot, manager, noop_type):
    draft = _make(session, robot)
    drafts.approve_draft(session, manager, client=ClientType.WEB_UI, draft_id=draft.id)

    with pytest.raises(ValidationError):
        drafts.approve_draft(
            session, manager, client=ClientType.WEB_UI, draft_id=draft.id
        )

    # Exactly one run, not two.
    assert len(noop_type) == 1


def test_reject_is_terminal_and_runs_nothing(session, robot, manager, noop_type):
    draft = _make(session, robot)

    rejected = drafts.reject_draft(
        session, manager, client=ClientType.WEB_UI, draft_id=draft.id
    )

    assert rejected.status == DraftStatus.REJECTED
    assert rejected.decided_by == "manager-1"
    assert noop_type == []


def test_get_draft_raises_rather_than_returning_none(session, manager):
    with pytest.raises(NotFoundError):
        drafts.get_draft(session, manager, draft_id=999_999_999)


def test_list_filters_by_status_and_counts_the_whole_match(session, robot, manager, noop_type):
    first = _make(session, robot)
    _make(session, robot)
    drafts.reject_draft(session, manager, client=ClientType.WEB_UI, draft_id=first.id)

    pending = drafts.list_drafts(session, manager, status=DraftStatus.PENDING)
    total = drafts.count_drafts(session, manager, status=DraftStatus.PENDING)

    assert all(d.status == DraftStatus.PENDING for d in pending)
    assert total == len(pending)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_drafts.py -v`
Expected: FAIL — `ImportError: cannot import name 'drafts' from 'services'`

- [ ] **Step 3: Write the service**

```python
# backend/services/drafts.py
"""The Action Draft queue: propose now, decide later.

Follows every convention established in services/products.py - session first,
actor second, everything else keyword-only, `actor.can()` before any write,
exceptions rather than None, and the service owns its own commit. Read that
file first if any of those look arbitrary.

Two things here are specific to this module and are the reason it exists:

**The handler runs as the approving human, not as the proposer.** The agent
writes the draft; a manager approves it; the change is then made with the
manager's actor. So the audit columns on whatever the handler touches name the
person who took responsibility, which is the entire point of an approval queue.
An agent that could propose *and* have its own identity stamped on the result
would be an agent that acts unsupervised with extra steps.

**The payload is validated twice.** Once here on creation, and again on
approval, because `approve_draft` accepts an edited payload. Validating only on
creation would mean the schema guarded the agent and never the browser - and
the browser is the one place a human can type anything they like.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.actor import Actor
from core.enums import ClientType, DraftStatus
from core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from core.models import ActionDraft
from services import draft_types

# How long a proposal stays actionable unless the caller says otherwise.
#
# 24 hours because these are perishable in the literal sense: a markdown
# proposal for stock expiring tomorrow is worthless the day after, and a
# purchase order assembled from this morning's stock levels should not be
# executed next week against numbers that have moved. A stale draft executed by
# accident is a worse outcome than one that has to be regenerated.
DEFAULT_EXPIRY_HOURS = 24


def _require(actor: Actor, permission: str) -> None:
    """Raise PermissionDeniedError unless `actor` holds `permission`.

    Deliberately duplicated from services/products.py rather than shared. It is
    four lines, and a `services/_permissions.py` imported by every service
    would be a new shared dependency for no real saving. If a third copy
    appears, extract it then.
    """
    if not actor.can(permission):
        raise PermissionDeniedError(
            f"Actor {actor.id!r} is not allowed to perform {permission!r}."
        )


def create_draft(
    session: Session,
    actor: Actor,
    *,
    client: ClientType,
    draft_type: str,
    payload: dict,
    reasoning: str,
    cost_at_risk: Decimal | None = None,
    projected_recovery: Decimal | None = None,
    expires_in_hours: int = DEFAULT_EXPIRY_HOURS,
) -> ActionDraft:
    """Stage a proposal. Changes nothing operational.

    Creating a draft is safe by construction - it writes one row that no other
    part of the system reads until a human approves it. That is why the agent
    is allowed to do this without an in-conversation confirmation, while still
    being unable to change a price. See docs/FEATURES-PLAN.md, decision 1.
    """
    _require(actor, "draft.create")

    if not reasoning.strip():
        # The human reading the card needs to know WHY. A draft with no
        # reasoning is a button with no label.
        raise ValidationError("A draft must carry a reason.")

    # Raises for an unknown type or a payload of the wrong shape, before
    # anything is written. The parsed object is discarded - the dict is what
    # gets stored, because JSONB holds JSON, not Python objects - but the
    # validation has done its job by not raising.
    draft_types.validate_payload(draft_type, payload)

    draft = ActionDraft(
        draft_type=draft_type,
        status=DraftStatus.PENDING,
        payload=payload,
        reasoning=reasoning.strip(),
        cost_at_risk=cost_at_risk,
        projected_recovery=projected_recovery,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_in_hours),
        created_by=actor.id,
        created_via=client,
    )
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


def list_drafts(
    session: Session,
    actor: Actor,
    *,
    status: DraftStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ActionDraft]:
    """A page of drafts, newest first.

    Newest first rather than the `id DESC` of products for the same reason it
    looks the same: an approval queue is read from the top, and the newest
    proposal is the one still worth acting on.
    """
    _require(actor, "draft.read")

    stmt = select(ActionDraft)
    if status is not None:
        stmt = stmt.where(ActionDraft.status == status)

    stmt = stmt.order_by(ActionDraft.id.desc()).limit(limit).offset(offset)
    return list(session.scalars(stmt))


def count_drafts(
    session: Session, actor: Actor, *, status: DraftStatus | None = None
) -> int:
    """How many drafts match, ignoring limit/offset.

    Shares its filter with `list_drafts` for the reason `_search_filter` exists
    in products.py: a total that counts rows the list would not return produces
    a pagination control promising a page that comes back empty.
    """
    _require(actor, "draft.read")

    stmt = select(func.count()).select_from(ActionDraft)
    if status is not None:
        stmt = stmt.where(ActionDraft.status == status)
    return session.scalar(stmt) or 0


def get_draft(session: Session, actor: Actor, *, draft_id: int) -> ActionDraft:
    """One draft, or raise NotFoundError."""
    _require(actor, "draft.read")

    draft = session.get(ActionDraft, draft_id)
    if draft is None:
        raise NotFoundError(f"No action draft with id {draft_id}.")
    return draft


def _require_actionable(draft: ActionDraft) -> None:
    """Raise unless this draft is still waiting and still in date.

    Shared by approve and reject so the two can never disagree about what
    "still open" means.
    """
    if draft.status != DraftStatus.PENDING:
        raise ValidationError(
            f"Draft {draft.id} is {draft.status}, so it can no longer be decided."
        )
    if draft.is_expired:
        raise ValidationError(
            f"Draft {draft.id} expired at {draft.expires_at.isoformat()} "
            "and can no longer be executed."
        )


def approve_draft(
    session: Session,
    actor: Actor,
    *,
    client: ClientType,
    draft_id: int,
    payload: dict | None = None,
    ) -> ActionDraft:
    """Say yes, optionally with edits, and run the handler.

    `payload` replaces the stored one when given. That is the "inline adjuster"
    the design calls for - a manager who agrees with the idea but wants 30%
    instead of 50% should not have to reject and ask the agent again.

    The order below matters. Permission, then actionability, then validation,
    then the handler, then the status. Every check that can refuse happens
    before anything runs, so a refusal never leaves half a change behind.
    """
    _require(actor, "draft.decide")

    draft = session.get(ActionDraft, draft_id)
    if draft is None:
        raise NotFoundError(f"No action draft with id {draft_id}.")

    _require_actionable(draft)

    effective_payload = payload if payload is not None else draft.payload

    # The second validation. Raises before the handler is reached.
    validated = draft_types.validate_payload(draft.draft_type, effective_payload)
    spec = draft_types.spec_for(draft.draft_type)

    # The handler receives the APPROVING actor, so whatever it writes records
    # the manager who took responsibility - not the agent that proposed it.
    spec.handler(session, actor, client, validated)

    draft.payload = effective_payload
    draft.status = DraftStatus.EXECUTED
    draft.decided_by = actor.id
    draft.decided_at = datetime.now(timezone.utc)
    draft.decided_via = client

    session.commit()
    session.refresh(draft)
    return draft


def reject_draft(
    session: Session, actor: Actor, *, client: ClientType, draft_id: int
) -> ActionDraft:
    """Say no. Terminal, and runs nothing.

    Rejecting takes the same `draft.decide` permission as approving. The
    security difference between the two is negligible - neither changes the
    world, one just closes the door - and every permission costs seven
    configuration edits plus a seed rebuild. See docs/FEATURES-PLAN.md.
    """
    _require(actor, "draft.decide")

    draft = session.get(ActionDraft, draft_id)
    if draft is None:
        raise NotFoundError(f"No action draft with id {draft_id}.")

    _require_actionable(draft)

    draft.status = DraftStatus.REJECTED
    draft.decided_by = actor.id
    draft.decided_at = datetime.now(timezone.utc)
    draft.decided_via = client

    session.commit()
    session.refresh(draft)
    return draft
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_drafts.py tests/test_draft_types.py -v`
Expected: PASS — 6 model/enum tests + 14 service tests + 6 registry tests

- [ ] **Step 5: Run the whole suite and the boundary check**

Run: `cd backend && pytest && lint-imports`
Expected: all previous tests still pass; `Contracts: 4 kept, 0 broken.`

- [ ] **Step 6: Commit**

```bash
git add backend/services/drafts.py backend/tests/test_drafts.py
git commit -m "feat(drafts): add the draft service with double payload validation"
```

---

### Task 5: The HTTP adapter

**Files:**
- Create: `backend/api/routes/drafts.py`
- Modify: `backend/api/schemas.py` (append draft schemas)
- Modify: `backend/api/main.py` (one `include_router` line)
- Test: `backend/tests/test_api_drafts.py`

**Interfaces:**
- Consumes: everything from Task 4.
- Produces: `GET /drafts`, `GET /drafts/{id}`, `POST /drafts/{id}/approve`, `POST /drafts/{id}/reject`. Response shapes `DraftRead` and `DraftList` (`{items, total}`, matching `ProductList`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_api_drafts.py
"""HTTP tests for the draft queue.

These test *translation* - that a domain exception becomes the right status and
the right body - not business rules. The rules are tested in test_drafts.py
against the service directly, which is the whole point of having a service.
"""

import pytest
from pydantic import BaseModel

from core.enums import ClientType, DraftStatus
from services import draft_types, drafts


class _MarkPayload(BaseModel):
    product_id: int


@pytest.fixture
def registered(session):
    ran = []
    draft_types.register(
        "TEST_MARK",
        schema=_MarkPayload,
        handler=lambda s, a, c, p: ran.append(p.product_id),
    )
    yield ran
    draft_types._REGISTRY.pop("TEST_MARK", None)


@pytest.fixture
def a_draft(session, actor, registered):
    return drafts.create_draft(
        session,
        actor,
        client=ClientType.MCP_AGENT,
        draft_type="TEST_MARK",
        payload={"product_id": 7},
        reasoning="expires tomorrow",
    )


def test_list_returns_items_and_total(client, a_draft):
    response = client.get("/drafts", params={"status": "pending"})

    assert response.status_code == 200
    body = response.json()
    assert "items" in body and "total" in body
    assert any(d["id"] == a_draft.id for d in body["items"])


def test_get_unknown_draft_is_404_with_the_error_envelope(client):
    response = client.get("/drafts/999999999")

    assert response.status_code == 404
    assert response.json()["error"] == "NotFoundError"


def test_approve_executes_and_returns_the_updated_draft(client, a_draft, registered):
    response = client.post(f"/drafts/{a_draft.id}/approve", json={})

    assert response.status_code == 200
    assert response.json()["status"] == DraftStatus.EXECUTED
    assert registered == [7]


def test_approving_with_a_bad_edited_payload_is_400(client, a_draft, registered):
    response = client.post(
        f"/drafts/{a_draft.id}/approve",
        json={"payload": {"product_id": "not a number"}},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "ValidationError"
    assert registered == []


def test_reject_returns_the_rejected_draft(client, a_draft, registered):
    response = client.post(f"/drafts/{a_draft.id}/reject")

    assert response.status_code == 200
    assert response.json()["status"] == DraftStatus.REJECTED
    assert registered == []


def test_money_serialises_as_a_string_not_a_number(client, session, actor, registered):
    from decimal import Decimal

    draft = drafts.create_draft(
        session, actor,
        client=ClientType.MCP_AGENT,
        draft_type="TEST_MARK",
        payload={"product_id": 7},
        reasoning="x",
        cost_at_risk=Decimal("40000.50"),
    )

    body = client.get(f"/drafts/{draft.id}").json()

    # A JSON number here would be a float64 and would eventually lose a cent.
    assert body["cost_at_risk"] == "40000.50"
    assert isinstance(body["cost_at_risk"], str)


def test_an_unauthenticated_request_is_refused(unauthenticated_client):
    response = unauthenticated_client.get("/drafts")

    assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_api_drafts.py -v`
Expected: FAIL — all requests 404, because no router is mounted.

- [ ] **Step 3: Add the schemas**

Append to `backend/api/schemas.py`:

```python
class DraftRead(BaseModel):
    """What every draft endpoint returns.

    `cost_at_risk` and `projected_recovery` are `Decimal`, which Pydantic
    serialises to a JSON **string** - the same decision `ProductRead` makes for
    prices, and for the same reason: a JSON number is a float64, and float64
    cannot hold 40000.50 exactly. The frontend already formats money from
    strings.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    draft_type: str
    status: str
    payload: dict
    reasoning: str
    cost_at_risk: Decimal | None
    projected_recovery: Decimal | None
    expires_at: datetime | None
    is_expired: bool = Field(
        description="True when expires_at has passed. Computed, never stored."
    )
    created_at: datetime
    created_by: str
    created_via: str
    decided_by: str | None
    decided_at: datetime | None
    decided_via: str | None


class DraftList(BaseModel):
    """A page of drafts plus the size of the whole match. Mirrors ProductList."""

    items: list[DraftRead]
    total: int = Field(description="Total matching the status filter, ignoring limit/offset.")


class DraftApproval(BaseModel):
    """The body of POST /drafts/{id}/approve.

    `payload` is optional and replaces the stored one when present - the inline
    adjuster. Absent means "approve exactly what was proposed".
    """

    payload: dict | None = None
```

- [ ] **Step 4: Write the router**

```python
# backend/api/routes/drafts.py
"""HTTP routes for the Action Draft queue.

No business logic. Get a session, call the service, return the result - the
same shape as routes/products.py. Every domain exception is translated centrally
by api/errors.py, which is why there is not a single try/except here.
"""

from fastapi import APIRouter, Query

from api.deps import CurrentActor, DbSession
from api.schemas import DraftApproval, DraftList, DraftRead
from core.enums import ClientType, DraftStatus
from services import drafts

router = APIRouter(prefix="/drafts", tags=["drafts"])


@router.get("", response_model=DraftList)
def list_drafts(
    session: DbSession,
    actor: CurrentActor,
    status: DraftStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """A page of drafts, newest first, optionally filtered by status."""
    items = drafts.list_drafts(
        session, actor, status=status, limit=limit, offset=offset
    )
    total = drafts.count_drafts(session, actor, status=status)
    return DraftList(items=items, total=total)


@router.get("/{draft_id}", response_model=DraftRead)
def get_draft(draft_id: int, session: DbSession, actor: CurrentActor):
    """One draft."""
    return drafts.get_draft(session, actor, draft_id=draft_id)


@router.post("/{draft_id}/approve", response_model=DraftRead)
def approve_draft(
    draft_id: int, body: DraftApproval, session: DbSession, actor: CurrentActor
):
    """Approve a draft and run its handler, optionally with an edited payload.

    `ClientType.WEB_UI` is hardcoded rather than read from anything the caller
    sends. That is the point of the parameter: a client cannot claim to be a
    different door, because this adapter IS the web door and says so itself.
    """
    return drafts.approve_draft(
        session,
        actor,
        client=ClientType.WEB_UI,
        draft_id=draft_id,
        payload=body.payload,
    )


@router.post("/{draft_id}/reject", response_model=DraftRead)
def reject_draft(draft_id: int, session: DbSession, actor: CurrentActor):
    """Reject a draft. Terminal, and runs nothing."""
    return drafts.reject_draft(
        session, actor, client=ClientType.WEB_UI, draft_id=draft_id
    )
```

- [ ] **Step 5: Mount the router**

In `backend/api/main.py`, next to the existing `app.include_router(products.router)`:

```python
from api.routes import drafts, products
...
app.include_router(products.router)
app.include_router(drafts.router)
```

- [ ] **Step 6: Run the tests**

Run: `cd backend && pytest tests/test_api_drafts.py -v`
Expected: PASS, 7 tests

- [ ] **Step 7: Run everything**

Run: `cd backend && pytest && lint-imports`
Expected: full suite green, `Contracts: 4 kept, 0 broken.`

- [ ] **Step 8: Commit**

```bash
git add backend/api/routes/drafts.py backend/api/schemas.py backend/api/main.py backend/tests/test_api_drafts.py
git commit -m "feat(drafts): expose the draft queue over HTTP"
```

---

### Task 6: The MCP adapter, and the agent's approval gate

**Files:**
- Modify: `backend/mcp_server/server.py` (append two tools)
- Modify: `agent/mcp_client.py:88` (the approval allowlist)
- Test: `backend/tests/test_mcp_drafts.py`, `agent/tests/test_tool_gating.py`

**Interfaces:**
- Consumes: everything from Task 4.
- Produces: MCP tools `create_action_draft` and `list_pending_drafts`. **No approve tool exists**, by design.

- [ ] **Step 1: Write the failing agent-side test**

```python
# append to agent/tests/test_tool_gating.py
from mcp_client import tool_kind


def test_creating_a_draft_needs_no_in_conversation_approval():
    """A draft changes nothing operational, so it runs freely.

    The human approval did not disappear - it moved to /approvals, where the
    proposal can be read in full and edited. See docs/FEATURES-PLAN.md,
    decision 1.
    """
    assert tool_kind("create_action_draft") == "function"


def test_listing_pending_drafts_needs_no_approval():
    assert tool_kind("list_pending_drafts") == "function"


def test_an_unknown_tool_still_defaults_to_needing_approval():
    """The fail-safe direction. A new backend tool is gated until declared."""
    assert tool_kind("some_future_tool") == "unapproved"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd agent && pytest tests/test_tool_gating.py -v`
Expected: FAIL — `create_action_draft` is currently `unapproved`.

- [ ] **Step 3: Widen the allowlist**

In `agent/mcp_client.py`, keep `READ_ONLY` exactly as it is and add below it:

```python
# Tools that WRITE but change nothing anyone can act on. Today that is exactly
# one: creating an Action Draft writes a row that sits in a queue until a human
# reads it at /approvals. No price moves, no order is placed, no stock changes.
#
# This is a separate constant rather than three more entries in READ_ONLY,
# because READ_ONLY means what it says and a writing tool listed there would
# make the name a lie for the next person who reads it.
#
# The bar for adding anything here: approving it later must be a real decision
# a human actually makes, and the row must be inert until they make it. If
# something in this set ever becomes load-bearing on its own, it belongs back
# under approval.
STAGING_ONLY = frozenset({"create_action_draft", "list_pending_drafts"})
```

and change `tool_kind` to consult both:

```python
def tool_kind(name: str) -> Literal["function", "unapproved"]:
    """Whether a tool runs freely or waits for a human.

    (existing docstring stays - append the paragraph below)

    Gate 27 added STAGING_ONLY alongside READ_ONLY. The default is unchanged
    and is the important part: anything in neither set is `unapproved`, so a
    new backend tool is gated automatically rather than slipping through.
    """
    return "function" if name in READ_ONLY or name in STAGING_ONLY else "unapproved"
```

- [ ] **Step 4: Run the agent test**

Run: `cd agent && pytest tests/test_tool_gating.py -v`
Expected: PASS

- [ ] **Step 5: Write the failing MCP-server test**

```python
# backend/tests/test_mcp_drafts.py
"""The MCP server's draft tools.

Note what is NOT here: there is no approve tool and no test for one. The agent
holds draft.create and never draft.decide, and the absence of the tool is the
second layer of that - a tool that does not exist cannot be called even by a
token that would be allowed to.
"""

import pytest
from pydantic import BaseModel

from services import draft_types


class _MarkPayload(BaseModel):
    product_id: int


@pytest.fixture
def registered():
    draft_types.register(
        "TEST_MARK", schema=_MarkPayload, handler=lambda s, a, c, p: None
    )
    yield
    draft_types._REGISTRY.pop("TEST_MARK", None)


def test_the_mcp_server_exposes_no_approval_tool():
    """The design property, asserted rather than assumed."""
    from mcp_server import server

    tool_names = {
        name for name in dir(server) if not name.startswith("_")
    }
    assert "approve_action_draft" not in tool_names
    assert "approve_draft" not in tool_names


def test_create_action_draft_stages_a_pending_row(session, monkeypatch, registered):
    """Mirrors the pattern in tests/test_mcp_products.py: the tool functions are
    called directly, with the session dependency patched to the test's."""
    from core.enums import DraftStatus
    from mcp_server import server

    monkeypatch.setattr(server, "get_session", lambda: _fake_ctx(session))

    result = server.create_action_draft(
        draft_type="TEST_MARK",
        payload={"product_id": 3},
        reasoning="milk expires tomorrow",
    )

    assert result["status"] == DraftStatus.PENDING
    assert result["created_via"] == "mcp_agent"


def _fake_ctx(session):
    """A context manager yielding the test's session, matching get_session()."""
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        yield session

    return _cm()
```

> **Note for the implementer:** read `backend/tests/test_mcp_products.py` first and copy its exact
> session-patching approach rather than the sketch above — it is the established pattern in this
> repo and it is known to work with the MCP SDK 2.0.0 tool wrapper.

- [ ] **Step 6: Add the two MCP tools**

Append to `backend/mcp_server/server.py`, following the shape of the existing six tools. The
docstrings matter more than usual here — they become the tool descriptions the model reads.

```python
@mcp.tool()
def create_action_draft(
    draft_type: str,
    payload: dict[str, Any],
    reasoning: str,
    cost_at_risk: str | None = None,
    projected_recovery: str | None = None,
) -> dict[str, Any]:
    """Propose a change for a human to approve. Nothing happens until they do.

    Use this for anything that affects many items at once or involves money:
    marking down a batch of stock, raising a purchase order, issuing a supplier
    credit. The proposal appears in the manager's approval queue with your
    reasoning attached, and a human decides.

    You cannot approve your own proposal, and there is no tool to do so. Write
    a clear `reasoning` - it is the only thing the manager has to judge by.

    Args:
        draft_type: The kind of proposal. Must be one this system knows.
        payload: The proposal's details. Its required shape depends on draft_type.
        reasoning: Plain-English explanation of why you are proposing this.
        cost_at_risk: Money currently at risk, as a decimal string, e.g. "40000.50".
        projected_recovery: Money this proposal would recover, as a decimal string.
    """
    with get_session() as session:
        draft = drafts.create_draft(
            session,
            _actor(),
            client=ClientType.MCP_AGENT,
            draft_type=draft_type,
            payload=payload,
            reasoning=reasoning,
            cost_at_risk=_price(cost_at_risk, "cost_at_risk") if cost_at_risk else None,
            projected_recovery=(
                _price(projected_recovery, "projected_recovery")
                if projected_recovery
                else None
            ),
        )
        return _describe_draft(draft)


@mcp.tool()
def list_pending_drafts(limit: int = 20) -> list[dict[str, Any]]:
    """List proposals still waiting for a human decision.

    Use this to check whether something you proposed has been decided, or to
    avoid proposing the same thing twice.

    Args:
        limit: How many to return, newest first.
    """
    with get_session() as session:
        found = drafts.list_drafts(
            session, _actor(), status=DraftStatus.PENDING, limit=limit
        )
        return [_describe_draft(d) for d in found]
```

and a describer alongside the existing `_describe`:

```python
def _describe_draft(draft: ActionDraft) -> dict[str, Any]:
    """One draft as plain JSON-safe values a model can read.

    Money becomes a string for the same reason it does in the HTTP adapter -
    and `None` stays `None` rather than becoming "0.00", because "no financial
    dimension" and "zero rupees" are different facts.
    """
    return {
        "id": draft.id,
        "draft_type": draft.draft_type,
        "status": draft.status,
        "payload": draft.payload,
        "reasoning": draft.reasoning,
        "cost_at_risk": str(draft.cost_at_risk) if draft.cost_at_risk is not None else None,
        "projected_recovery": (
            str(draft.projected_recovery)
            if draft.projected_recovery is not None
            else None
        ),
        "expires_at": draft.expires_at.isoformat() if draft.expires_at else None,
        "is_expired": draft.is_expired,
        "created_by": draft.created_by,
        "created_via": draft.created_via,
    }
```

- [ ] **Step 7: Run both suites**

Run: `cd backend && pytest && lint-imports`
Run: `cd agent && pytest && lint-imports --config pyproject.toml`
Expected: both green.

- [ ] **Step 8: Commit**

```bash
git add backend/mcp_server/server.py backend/tests/test_mcp_drafts.py agent/mcp_client.py agent/tests/test_tool_gating.py
git commit -m "feat(drafts): expose staging tools over MCP, gated as no-approval"
```

---

### Task 7: The `/approvals` screen

**Files:**
- Create: `frontend/src/lib/api/drafts.ts`
- Create: `frontend/src/app/approvals/page.tsx`
- Create: `frontend/src/app/approvals/actions.ts`
- Create: `frontend/src/app/approvals/_components/draft-card.tsx`
- Create: `frontend/src/app/approvals/loading.tsx`, `error.tsx`
- Modify: `frontend/src/components/shell/nav.tsx` (one link)
- Modify: `frontend/src/lib/api/schema.d.ts` — **regenerated, never hand-edited**

**Interfaces:**
- Consumes: `GET /drafts`, `POST /drafts/{id}/approve`, `POST /drafts/{id}/reject`.
- Produces: nothing other tasks depend on.

**Rules that apply here** (from `docs/FRONTEND-PLAN.md`): only `src/lib/api/` may call `fetch` or
touch the generated client; no route handlers under `app/api/` mirroring FastAPI; no business logic —
render `is_expired` and the two money figures, never recompute them.

- [ ] **Step 1: Regenerate the API types**

⚠️ **Developer runs this**, with `uvicorn` already running:

```bash
cd frontend && npm run api:types
```

This rewrites `src/lib/api/schema.d.ts` from the live `/openapi.json`. It is committed but never
hand-edited: if it looks wrong, the backend is wrong.

- [ ] **Step 2: Write the data module**

```typescript
// frontend/src/lib/api/drafts.ts
// The ONLY place the app talks to the draft endpoints. Everything else imports
// from here - the frontend's equivalent of the backend's services/ boundary,
// enforced by ESLint's no-restricted-imports.
import "server-only";

import { client } from "./client";

export type Draft =
  paths["/drafts/{draft_id}"]["get"]["responses"]["200"]["content"]["application/json"];

export async function listPendingDrafts() {
  const { data, error } = await client.GET("/drafts", {
    params: { query: { status: "pending", limit: 50 } },
  });
  if (error) throw error;
  return data;
}

export async function approveDraft(draftId: number, payload?: Record<string, unknown>) {
  const { data, error } = await client.POST("/drafts/{draft_id}/approve", {
    params: { path: { draft_id: draftId } },
    body: { payload: payload ?? null },
  });
  if (error) throw error;
  return data;
}

export async function rejectDraft(draftId: number) {
  const { data, error } = await client.POST("/drafts/{draft_id}/reject", {
    params: { path: { draft_id: draftId } },
  });
  if (error) throw error;
  return data;
}
```

> **Implementer note:** copy the exact import style and error handling from the existing
> `frontend/src/lib/api/products.ts` — including how it names the generated `paths` type. The
> snippet above shows intent; that file shows the house style.

- [ ] **Step 3: Build the page and the card**

The page is a React Server Component that awaits `listPendingDrafts()` and renders one
`<DraftCard>` per item. Each card shows: the draft type as a readable label, the agent's
`reasoning` in full, `cost_at_risk` and `projected_recovery` side by side through the existing
`<MoneyDisplay>` domain component, an expiry badge driven by `is_expired`, and two buttons wired to
server actions.

Reuse rather than rebuild: `<MoneyDisplay>`, `<StockBadge>`'s badge styling conventions, and
`<ApiErrorState>` for the error boundary all already exist in `src/components/domain/`.

- [ ] **Step 4: Check it in a real browser**

⚠️ **Developer runs the servers first** — `bash scripts/dev-up.sh` plus ThunderID via
`deploy/docker-compose.thunderid.yml` — then says continue. Only then may browser automation be used.

Verify: the queue lists pending drafts; approving one removes it and the change is real; rejecting
one removes it and nothing changed; an expired draft shows its badge and its buttons refuse.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api/drafts.ts frontend/src/app/approvals frontend/src/components/shell/nav.tsx frontend/src/lib/api/schema.d.ts
git commit -m "feat(drafts): add the /approvals queue screen"
```

---

### Task 8: Carry the gate into the demo box

**Files:**
- Modify: `frontend/.env.example`, and the developer's own `frontend/.env`
- Modify: `deploy/aisle-box/docker-compose.yml` (the `web` service's `args:`)
- Modify: `agent/config.py` (`thunderid_scopes` default), `agent/.env.example`
- Modify: `deploy/aisle-box/seed-build/aisle-config.yml` (**both** resource servers, and the
  `AIsle Full Access` role)
- The developer's own running ThunderID, via its Console

**This task has no tests and fails silently if skipped.** ThunderID answers a request for an unknown
permission with a valid token carrying **no scope claim at all**, so a missed entry shows up as the
whole application returning 403 to a signed-in user. Full checklist: `docs/DEPLOY-PLAN.md`, "What a
new feature has to update in the box".

- [ ] **Step 1: Add the three permissions everywhere**

`draft.read`, `draft.create`, `draft.decide` — into all seven places named in `DEPLOY-PLAN.md`.

⚠️ **Not identically in all seven.** The agent's role gets `draft.read` and `draft.create` only.
`draft.decide` goes to the human role and **must not** reach the agent's — that is the security
property this gate exists to create, and configuration is where it is actually enforced.

- [ ] **Step 2: Rebuild the shipped seed**

⚠️ **Developer runs this.** Editing the YAML alone changes nothing a judge runs — the committed
`.db` files are the artefact.

```bash
cd deploy/aisle-box/seed-build && python prune-config.py && python build-seed.py && python scan-seed.py
```

- [ ] **Step 3: Confirm the migration reached Supabase**

The box runs no migrations and points at the shared hosted database. Task 2 already applied it; this
step is the deliberate double-check, because the failure mode is the box starting cleanly and then
dying at the first query.

- [ ] **Step 4: Commit**

```bash
git add frontend/.env.example agent/config.py agent/.env.example deploy/aisle-box/
git commit -m "chore(box): carry gate 27's permissions into the demo box"
```

---

## Self-review notes

**Spec coverage.** Every gate-27 item in `docs/FEATURES-PLAN.md` maps to a task: the table and its
two money columns (Task 2), the closed registry (Task 3), double validation and the agent's
inability to decide (Tasks 3–4), computed expiry (Tasks 2 and 4), the four endpoints (Task 5), the
two MCP tools and no approve tool (Task 6), `/approvals` (Task 7), the box tax (Task 8).

**Deliberately deferred to gate 28.** No draft type is registered by this gate, so `/approvals` is
an empty queue until spoilage lands. That is correct — the engine and its first user are separate
deliverables — but it means the browser check in Task 7 needs a draft created by hand through the
MCP tool or a Python shell.

**Known weak spot.** Task 6's MCP test sketch patches `get_session`; the established pattern lives
in `tests/test_mcp_products.py` and should be copied from there rather than from this plan.
