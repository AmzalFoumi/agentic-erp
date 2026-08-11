# Gate 18 — Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **This project's working
> agreement overrides the sub-skill's default: the agent never runs `git add`/`git commit`, and
> never creates a worktree.** Each task ends with a checkpoint describing what changed and why, and
> the developer commits it manually — see "Execution note" below.

**Goal:** Conversations and messages persist to Postgres and reload correctly, in the agent's own
`agent` schema with its own Alembic history, invisible to `backend/`'s Alembic.

**Architecture:** Same Supabase Postgres instance backend already uses, isolated by a separate
`agent` Postgres schema (not a separate database). Two explicit isolation guards, not relying on
defaults: `MetaData(schema="agent")` on the agent's ORM `Base`, and `include_schemas=False` in
backend's `alembic/env.py`. `store.py` is the only file callers use.

**Tech Stack:** SQLAlchemy 2.0, psycopg3, Alembic — same libraries backend already uses, in the
agent's separate venv. Pydantic AI's `ModelMessagesTypeAdapter` for the provider-opaque bytes field
(confirmed present in `agent/.venv` — `python -c "from pydantic_ai.messages import
ModelMessagesTypeAdapter"` succeeds).

## Global Constraints

- `services/`-style rule for `agent/`: `agent/store.py`, `agent/database.py`, `agent/models.py` must
  never import `pydantic_ai` or `mcp` — only `agent/conversation.py`, `agent/model_provider.py`,
  `agent/mcp_client.py` may (the Gate 17 "runtime cluster", enforced by `agent/pyproject.toml`'s
  import-linter contract). Do not add these three new files to that contract's allowed cluster.
- Integer serial primary keys on every new table (matches `backend/core/models.py`'s `Product.id`
  convention) — no UUIDs.
- `started_by` / `created_by` columns default to the string `"system"` (matches
  `backend/core/models.py:140-141`'s `created_by`/`updated_by` deferral pattern).
- `agent.conversations` and `agent.messages` get RLS enabled (deny-all, no policies) via a
  hand-written migration, mirroring `backend/alembic/versions/20260730_0900-a1c4e7b2f019_enable_rls_on_alembic_version.py`.
  RLS is not a column, so autogenerate cannot produce this migration.
- No new error handling anywhere in `agent/`: a Postgres failure raises SQLAlchemy's own exception,
  uncaught — matches `conversation.py`'s existing "no caller needs different behavior yet" policy.
- Money is not touched in this gate — nothing here.
- `agent/`'s dependency pins mirror `backend/requirements.txt`'s already-verified versions
  (`sqlalchemy==2.0.51`, `psycopg[binary]==3.3.4`, `alembic==1.18.5`) rather than being
  re-researched — same libraries, same repo, pinned the same week.

## Execution note (read before starting)

This session's working agreement is stricter than the executing-plans skill's default: **the agent
never runs `git add`, `git commit`, or creates a worktree** — those are the developer's to run.
Work directly on the current branch. At the end of each task, stop and report what changed and why,
and let the developer review and commit before you continue to the next task. Running
`pip install` is also the developer's job — when a task needs a new dependency, add it to
`agent/requirements.txt` and tell the developer to run `pip install -r requirements.txt` from
`agent/` before you continue past that task's verification step (which will fail without it).

---

## File overview

```
agent/requirements.txt        # + sqlalchemy, psycopg[binary], alembic
agent/config.py                # + database_url setting
agent/database.py              # NEW — engine, SessionLocal, Base (schema="agent")
agent/models.py                # NEW — ConversationRow, MessageRow
agent/store.py                 # NEW — start_conversation, append_message, load_history
agent/conversation.py          # Message gains provider_data; run_turn/_to_model_history use it
agent/alembic.ini               # NEW
agent/alembic/env.py            # NEW
agent/alembic/script.py.mako    # NEW (stock Alembic template, copied verbatim)
agent/alembic/versions/..._create_agent_tables.py   # NEW
agent/alembic/versions/..._enable_rls_on_agent_tables.py   # NEW
agent/pyproject.toml            # + version_table_schema = "agent"
agent/scripts/verify_store.py   # NEW — the gate's round-trip verification script
backend/alembic/env.py          # + include_schemas=False on both configure() calls
```

---

### Task 1: Agent database dependencies and connection plumbing

**Files:**
- Modify: `agent/requirements.txt`
- Create: `agent/database.py`

**Interfaces:**
- Produces: `agent.database.engine` (SQLAlchemy `Engine`), `agent.database.SessionLocal`
  (`sessionmaker`), `agent.database.Base` (`DeclarativeBase` subclass, `metadata.schema == "agent"`),
  `agent.database.get_session()` (contextmanager yielding a `Session`).
- Consumes: `agent.config.settings.database_url` (added in Task 2 — this task can be written first
  since it only reads the attribute name, not the value).

- [ ] **Step 1: Add the three dependencies to `agent/requirements.txt`**

Append to the end of the file:

```
# SQLAlchemy is the ORM: it maps Python classes to SQL tables. Pinned to the
# same version as backend/requirements.txt - same library, verified the same
# week, no reason for the two services to drift.
sqlalchemy==2.0.51

# The Postgres driver. SQLAlchemy speaks SQL; psycopg speaks to the actual
# socket. Same pin as backend/requirements.txt.
psycopg[binary]==3.3.4

# Alembic generates and applies database migrations for the agent's own
# schema, independent of backend/'s migration history. Same pin as
# backend/requirements.txt.
alembic==1.18.5
```

- [ ] **Step 2: Tell the developer to install, then wait**

Report to the developer: "Run `pip install -r requirements.txt` from `agent/` (with `agent/.venv`
active) before I continue." Do not proceed to Step 3 until they confirm it's done.

- [ ] **Step 3: Write `agent/database.py`**

```python
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
```

- [ ] **Step 4: Verify it imports (no database call yet)**

Run from `agent/` (venv active): `python -c "from database import Base, engine, get_session; print(Base.metadata.schema)"`
Expected output: `agent`

- [ ] **Step 5: Report the change**

Stop here. Report to the developer: "Added SQLAlchemy/psycopg/Alembic deps and `agent/database.py`
(schema-qualified Base, verified `Base.metadata.schema == 'agent'`). No migrations yet — nothing to
run against Postgres. Ready to commit these two files before I continue to Task 2?"

---

### Task 2: `database_url` setting on `agent/config.py`

**Files:**
- Modify: `agent/config.py:96` (immediately after the `gemini_api_key: str` field, before
  `gemini_model`)
- Modify: `agent/.env.example`

**Interfaces:**
- Produces: `agent.config.settings.database_url: str` — read by `agent/database.py` (Task 1).

- [ ] **Step 1: Add the field to `Settings`**

In `agent/config.py`, insert immediately after the `gemini_api_key: str` field (currently line 96):

```python

    # Required. Same Supabase Postgres instance backend/ already uses, reached
    # over the session pooler - a separate setting because agent/ never
    # imports backend/core/config.py (see this file's module docstring). The
    # agent's tables live in their own `agent` Postgres schema, not `public`;
    # see agent/database.py's Base for how that isolation is enforced in code.
    database_url: str
```

- [ ] **Step 2: Add the matching block to `agent/.env.example`**

Insert a new section into `agent/.env.example`, directly after the `GEMINI_API_KEY` block and before
the "Everything below is optional" comment:

```
# ---------------------------------------------------------------------------
# DATABASE_URL - required. Same Supabase Postgres instance backend/ uses,
# a different schema (`agent`, not `public`). Get the connection string the
# same way backend/.env.example describes: Supabase dashboard -> Connect ->
# Session pooler tab, then swap the scheme and append sslmode as shown below.
# ---------------------------------------------------------------------------

DATABASE_URL=postgresql+psycopg://postgres.your-project-ref:YOUR-PASSWORD@aws-0-eu-west-3.pooler.supabase.com:5432/postgres?sslmode=require
```

- [ ] **Step 3: Verify settings load**

Tell the developer: "Add `DATABASE_URL=...` to your real `agent/.env` (same value as backend's
`DATABASE_URL`, since it's the same instance) before I continue — otherwise `Settings()` will fail
at import with a missing-field error." Wait for confirmation, then run from `agent/`:
`python -c "from config import settings; print(settings.database_url[:20])"`
Expected: prints the start of the connection string, no traceback.

- [ ] **Step 4: Report the change**

Stop here. Report: "`agent/config.py` now requires `DATABASE_URL`; `.env.example` documents it.
Confirmed `settings.database_url` loads from your `.env`. Ready to commit before Task 3?"

---

### Task 3: `agent/models.py` — `ConversationRow`, `MessageRow`

**Files:**
- Create: `agent/models.py`

**Interfaces:**
- Consumes: `agent.database.Base` (Task 1).
- Produces: `ConversationRow` (`id: int`, `title: str | None`, `started_by: str`,
  `created_at: datetime`), `MessageRow` (`id: int`, `conversation_id: int`, `role: str`,
  `content: str`, `provider_data: bytes | None`, `created_by: str`, `created_at: datetime`) — used
  by `agent/store.py` (Task 4).

- [ ] **Step 1: Write `agent/models.py`**

```python
"""SQLAlchemy ORM models for the agent's own schema.

Named ConversationRow/MessageRow, not Conversation/Message, because
conversation.py already defines a plain-dataclass `Message` for the
provider-agnostic boundary (Gate 17) - two classes named `Message` in the
same process would be a constant source of wrong imports. "Row" also signals
correctly: these are persistence-layer records, not the shape any caller
outside store.py should hold onto.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ConversationRow(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Nullable: no auto-summarization in this gate, just a column a human can
    # fill in later when searching conversations back.
    title: Mapped[str | None] = mapped_column(Text, default=None)

    # Defaults to "system" because SystemActor is the only actor that exists
    # today (docs/AUTH-PLAN.md). The column exists now so wiring in real auth
    # later is a data change, not a migration - same deferral pattern as
    # backend/core/models.py's created_by/updated_by.
    started_by: Mapped[str] = mapped_column(String(128), default="system")

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Unqualified "conversations.id" resolves to agent.conversations because
    # both tables share this Base's schema-qualified MetaData - confirmed by
    # inspecting Base.metadata.tables after declaring both classes.
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)

    # "user" or "assistant" - matches conversation.py's Message.role Literal.
    # Plain String rather than a Postgres ENUM: a third role would be a code
    # change either way, and ENUM migrations are more ceremony than this gate
    # needs.
    role: Mapped[str] = mapped_column(String(16), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Provider-opaque bytes (e.g. a serialized Pydantic AI ModelResponse,
    # carrying Google's function-call signature) - see conversation.py's
    # Message.provider_data for what populates this and why. store.py never
    # parses it, only round-trips it.
    provider_data: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)

    created_by: Mapped[str] = mapped_column(String(128), default="system")

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

- [ ] **Step 2: Verify the schema is correct**

Run from `agent/`:

```
python -c "from database import Base; import models; print(sorted(Base.metadata.tables))"
```

Expected: `['agent.conversations', 'agent.messages']`

- [ ] **Step 3: Report the change**

Stop here. Report: "`agent/models.py` defines `ConversationRow`/`MessageRow`, both registered under
`agent.*` — confirmed via `Base.metadata.tables`. Ready to commit before Task 4?"

---

### Task 4: `agent/store.py`

**Files:**
- Create: `agent/store.py`

**Interfaces:**
- Consumes: `agent.database.get_session` (Task 1), `ConversationRow`/`MessageRow` (Task 3),
  `agent.conversation.Message` (the dataclass — Task 6 adds `provider_data` to it, but the field
  already exists as a plain 2-field dataclass today, so this task can be written against it now;
  Task 6's addition is backward-compatible).
- Produces: `start_conversation(*, title: str | None = None) -> int`,
  `append_message(conversation_id: int, message: Message) -> None`,
  `load_history(conversation_id: int) -> list[Message]` — used by `agent/scripts/verify_store.py`
  (Task 7) and, in a future gate, `ask.py`.

- [ ] **Step 1: Write `agent/store.py`**

```python
"""Persistence for conversations and messages. The only file any caller needs
to import to save or reload a conversation - callers never see database.py or
models.py directly.

No new error handling: if Postgres is unreachable or a write fails,
SQLAlchemy's own exception propagates uncaught. This matches
conversation.py's existing policy (a tool failure becomes a ModelRetry;
everything else propagates) - no caller needs different behavior yet.
"""

from conversation import Message
from database import get_session
from models import ConversationRow, MessageRow


def start_conversation(*, title: str | None = None) -> int:
    """Create a conversation row, return its id."""
    with get_session() as session:
        row = ConversationRow(title=title)
        session.add(row)
        session.commit()
        return row.id


def append_message(conversation_id: int, message: Message) -> None:
    """Write one Message as a row under the given conversation."""
    with get_session() as session:
        row = MessageRow(
            conversation_id=conversation_id,
            role=message.role,
            content=message.content,
            provider_data=message.provider_data,
        )
        session.add(row)
        session.commit()


def load_history(conversation_id: int) -> list[Message]:
    """Read all rows for a conversation, ordered by id, rebuilt as Messages."""
    with get_session() as session:
        rows = (
            session.query(MessageRow)
            .filter(MessageRow.conversation_id == conversation_id)
            .order_by(MessageRow.id)
            .all()
        )
        return [
            Message(role=row.role, content=row.content, provider_data=row.provider_data)
            for row in rows
        ]
```

- [ ] **Step 2: Verify it imports**

Run from `agent/`: `python -c "import store; print(store.start_conversation, store.append_message, store.load_history)"`
Expected: prints the three function objects, no traceback. (This only checks the import graph — no
database call yet, since no migration has created the tables. That happens in Task 5.)

- [ ] **Step 3: Report the change**

Stop here. Report: "`agent/store.py` written with the three-function interface from the spec.
Import verified; no live database call yet — that's Task 7's round-trip check, after the tables
exist. Ready to commit before Task 5?"

---

### Task 5: Agent's own Alembic setup and initial migration

**Files:**
- Create: `agent/alembic.ini`
- Create: `agent/alembic/env.py`
- Create: `agent/alembic/script.py.mako`
- Create: `agent/alembic/versions/` (directory, populated by Step 4 below)
- Modify: `agent/pyproject.toml`

**Interfaces:**
- Consumes: `agent.database.Base`/`engine` (Task 1), `agent.models` (Task 3, imported for its
  side effect exactly like `backend/alembic/env.py` imports `core.models`).
- Produces: the applied `agent.conversations`/`agent.messages` tables in Postgres, and
  `agent.alembic_version` (via `version_table_schema`) tracking this history separately from
  backend's `public.alembic_version`.

- [ ] **Step 1: Write `agent/alembic.ini`**

Copy `backend/alembic.ini` verbatim, since the reasoning (documented in the copied comments)
applies identically to `agent/`.

```ini
# Alembic configuration.
#
# Alembic is to SQLAlchemy what `prisma migrate` is to Prisma: it compares your
# models against the real database and writes the SQL that closes the gap.
#
# This file is a trimmed version of what `alembic init` generates - the stock
# one ships ~100 lines of commented-out options for features we do not use.
# Everything kept below is something we actually rely on.

[alembic]
# Where the migration environment lives, relative to this file.
script_location = alembic

# Put `.` - i.e. agent/ - at the front of the import path.
#
# This looks redundant if you have internalised "Python adds the current
# directory to sys.path", but that rule only holds for `python` and `python -c`.
# `alembic` is an installed console script at .venv/Scripts/alembic.exe, and for
# a script Python sets sys.path[0] to the SCRIPT's directory - Scripts/ - not to
# the directory you are standing in. Without this line, alembic/env.py fails on
# `from database import ...` with ModuleNotFoundError.
prepend_sys_path = .

# Prefix generated migration filenames with a UTC timestamp, so `ls` on the
# versions/ folder shows them in the order they were written. Without this you
# get bare random hashes and no way to eyeball the sequence.
file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d-%%(rev)s_%%(slug)s
timezone = UTC

# Deliberately NOT set here: sqlalchemy.url.
#
# The stock alembic.ini hardcodes the connection string in this file. This file
# is committed to git, so that would put the database password in the repo.
# Instead alembic/env.py reads it from config.py at runtime, which reads
# agent/.env, which is gitignored. One source of truth, no secrets in git.

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
# INFO so that `alembic upgrade` tells you which revisions it is applying.
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: Write `agent/alembic/script.py.mako`**

Copy `backend/alembic/script.py.mako` verbatim (it is Alembic's own stock template, unmodified by
backend either):

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# Identifiers Alembic uses to order migrations. `down_revision` pointing at the
# previous revision is what forms the chain; the first migration has None.
revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """Apply this migration."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Undo this migration."""
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 3: Write `agent/alembic/env.py`**

```python
"""Alembic's entry point for the agent's own migration history.

Mirrors backend/alembic/env.py's structure (same reasoning: reuse our own
engine rather than alembic.ini's connection string; import the models for
their metadata side effect). Two differences from backend's version, both
explained inline: `version_table_schema` and the schema this history
tracks are the agent's own, and there is no `include_schemas` question here
because this env.py's target_metadata (Base.metadata, schema="agent") only
ever contains agent.* tables regardless of that setting.
"""

from logging.config import fileConfig

from alembic import context

from database import Base, engine

# Imported for the side effect of registering ConversationRow/MessageRow on
# Base.metadata - see backend/alembic/env.py's identical comment on why this
# import is not "unused" despite what a linter thinks.
import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # This history's own bookkeeping table lives at agent.alembic_version,
        # not the default public.alembic_version - the second of Gate 18's
        # explicit isolation guards. Without this, this env.py and backend's
        # would both write to public.alembic_version and stomp each other's
        # revision pointer.
        version_table_schema="agent",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            version_table_schema="agent",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Add `version_table_schema` to `agent/pyproject.toml`**

This value belongs in `env.py` (above), not `pyproject.toml` — Alembic has no `pyproject.toml`
setting for it. Add a comment to `agent/pyproject.toml` instead, immediately after the existing
`[tool.importlinter]` section, recording the decision where a future reader would look for it:

```toml

# Gate 18 note: the agent's own Alembic history (agent/alembic/) sets
# version_table_schema="agent" directly in agent/alembic/env.py's two
# context.configure() calls - Alembic has no pyproject.toml equivalent for
# this setting, so it is not duplicated here. Recorded in this file only so
# "why does agent/alembic exist and where is it configured" has one answer.
```

- [ ] **Step 5: Generate the initial migration**

Tell the developer: "Run `mkdir agent/alembic/versions` if it doesn't exist, then from `agent/`:
`alembic revision --autogenerate -m "create agent tables"`. Paste me the generated file's path and
contents." Wait for their response — this must be autogenerated against the real Postgres instance,
not hand-written, so it will fail loudly if `DATABASE_URL` or the model definitions are wrong.

- [ ] **Step 6: Review the generated migration**

Confirm the generated file creates exactly `conversations` and `messages` under the `agent` schema
(both `op.create_table(...)` calls should show `schema='agent'` or the table names should already
read `conversations`/`messages` with Alembic inferring the schema from `target_metadata` — either
form is correct; what matters is both tables appear and nothing from `public` is touched). If
anything looks wrong (e.g. it tries to touch `public.products` or `public.alembic_version`), stop
and report it rather than applying it.

- [ ] **Step 7: Apply the migration**

Tell the developer: "Run `alembic upgrade head` from `agent/`. Confirm it succeeds." Wait for
confirmation.

- [ ] **Step 8: Verify the tables exist and are isolated**

Run from `agent/`:

```
python -c "
from database import get_session
from sqlalchemy import text
with get_session() as s:
    print(s.execute(text(\"select table_schema, table_name from information_schema.tables where table_name in ('conversations','messages','alembic_version') order by 1,2\")).fetchall())
"
```

Expected: three rows — `('agent', 'alembic_version')`, `('agent', 'conversations')`,
`('agent', 'messages')`. If `alembic_version` shows up under `public` too, that's backend's own
table, not a collision — the two are meant to coexist, one per schema.

- [ ] **Step 9: Report the change**

Stop here. Report: "Agent's own Alembic history is set up and applied — `agent.conversations`,
`agent.messages`, `agent.alembic_version` all confirmed present via `information_schema`. Ready to
commit `agent/alembic.ini`, `agent/alembic/`, and the `pyproject.toml` note before Task 6?"

---

### Task 6: RLS on the agent's tables

**Files:**
- Create: `agent/alembic/versions/..._enable_rls_on_agent_tables.py`

**Interfaces:**
- Consumes: nothing new — a hand-written migration, chained via `down_revision` onto Task 5's
  migration.

- [ ] **Step 1: Find Task 5's revision id**

Run from `agent/`: `alembic current`. Note the revision hash printed — Task 5's migration's
`revision` value. This task's migration's `down_revision` must equal it.

- [ ] **Step 2: Write the migration**

Create the file at `agent/alembic/versions/`, following the naming Alembic itself would generate
(`file_template` from `alembic.ini` produces `YYYYMMDD_HHMM-<hash>-<slug>.py` — pick any valid hex
string distinct from Task 5's for `revision`, or let `alembic revision -m "enable rls on agent
tables"` (without `--autogenerate`) generate the file and hash for you, then fill in the body
below):

```python
"""enable rls on agent tables

Revision ID: <fill in from the generated file or your chosen hash>
Revises: <Task 5's revision id, from Step 1>
Create Date: <fill in from the generated file>

Written by hand rather than autogenerated, because autogenerate only compares
*columns* against the models. Row-level security is not a column. Same
pattern as backend/alembic/versions/20260730_0900-a1c4e7b2f019_enable_rls_on_alembic_version.py.

Enabling RLS with no policies means deny-all for every role except the
table's owner (our own connection), which bypasses RLS. This is a backstop,
not the authorization mechanism - authorization is enforced in store.py's
callers, same division of labor as backend/'s services layer.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "<fill in>"
down_revision: str | None = "<Task 5's revision id>"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.execute("ALTER TABLE agent.conversations ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE agent.messages ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    """Undo this migration."""
    op.execute("ALTER TABLE agent.messages DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE agent.conversations DISABLE ROW LEVEL SECURITY;")
```

- [ ] **Step 3: Apply it**

Tell the developer: "Run `alembic upgrade head` from `agent/`." Wait for confirmation.

- [ ] **Step 4: Verify RLS is on**

Run from `agent/`:

```
python -c "
from database import get_session
from sqlalchemy import text
with get_session() as s:
    print(s.execute(text(\"select relname, relrowsecurity from pg_class where relname in ('conversations','messages')\")).fetchall())
"
```

Expected: `[('conversations', True), ('messages', True)]` (order may vary).

- [ ] **Step 5: Report the change**

Stop here. Report: "RLS enabled on both agent tables, confirmed via `pg_class.relrowsecurity`.
Ready to commit before Task 7?"

---

### Task 7: `include_schemas=False` in backend's Alembic, and the negative-case verification

**Files:**
- Modify: `backend/alembic/env.py:55-60` (the `run_migrations_offline` `context.configure(...)`
  call)
- Modify: `backend/alembic/env.py:76-86` (the `run_migrations_online` `context.configure(...)`
  call)

**Interfaces:**
- Consumes: nothing from earlier tasks — this is the isolation guard on the backend side, and can
  technically run independently, but is sequenced last so the agent's tables already exist in
  Postgres when the negative-case check runs (a real, not hypothetical, temptation for autogenerate
  to notice them).

- [ ] **Step 1: Add `include_schemas=False` to `run_migrations_offline`**

In `backend/alembic/env.py`, change:

```python
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
```

to:

```python
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Explicit, not relied-on-as-default (Gate 18). Alembic's own default
        # is already False - autogenerate only ever scans the "public" schema
        # unless this is True - confirmed against
        # alembic.sqlalchemy.org/en/latest/api/runtime.html on 2026-08-12. This
        # line changes no behavior today; it means a future Alembic version
        # changing that default cannot silently make autogenerate propose
        # dropping agent/'s tables (agent.conversations, agent.messages).
        include_schemas=False,
    )
```

- [ ] **Step 2: Add the same to `run_migrations_online`**

Change:

```python
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
```

to:

```python
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            # See run_migrations_offline()'s identical comment.
            include_schemas=False,
        )
```

- [ ] **Step 3: Run the negative-case verification**

This is the check the spec calls "the reason this design exists." Run from `backend/`:

```
alembic revision --autogenerate -m "gate 18 negative case check"
```

Open the generated file. Expected: an empty migration — `upgrade()` and `downgrade()` both contain
only `pass` (or the auto-generated `### commands auto generated by Alembic - please adjust! ###`
comment with nothing between them). This proves `backend/`'s `Base.metadata` never learned about
`agent.conversations`/`agent.messages`.

If the file is **not** empty — if it proposes touching anything under `agent.*` — stop immediately
and report it; do not apply it. That would mean the isolation guard failed and the design needs
re-examination before proceeding.

- [ ] **Step 4: Delete the throwaway verification migration**

Tell the developer: "Delete the file generated in Step 3 (`backend/alembic/versions/..._gate_18_negative_case_check.py`) — it was empty and only existed to prove backend/'s Alembic can't see agent/'s tables. Confirm once deleted." Wait for confirmation. Do not run `alembic downgrade` or touch git — the file was never applied (an empty migration has nothing to apply), so deleting the file is sufficient.

- [ ] **Step 5: Report the change**

Stop here. Report: "Both `backend/alembic/env.py` `configure()` calls now pass
`include_schemas=False` explicitly. Negative-case check passed — the autogenerated migration was
empty, confirming backend's Alembic is blind to `agent.*`. The throwaway verification file has been
deleted. Ready to commit the two `env.py` lines before Task 8?"

---

### Task 8: `provider_data` on `conversation.py`'s `Message`, wired into `run_turn`

**Files:**
- Modify: `agent/conversation.py:52-59` (the `Message` dataclass)
- Modify: `agent/conversation.py:77-86` (`_to_model_history`)
- Modify: `agent/conversation.py:89-117` (`run_turn`)

**Interfaces:**
- Consumes: `pydantic_ai.messages.ModelMessagesTypeAdapter` — confirmed present in `agent/.venv`
  (`from pydantic_ai.messages import ModelMessagesTypeAdapter` succeeds; it is a
  `TypeAdapter(list[ModelMessage])`, so `.dump_json(list_of_messages) -> bytes` and
  `.validate_json(bytes) -> list[ModelMessage]`, verified interactively against the installed
  package on 2026-08-12).
- Produces: `Message(role, content, provider_data: bytes | None = None)` — the new shape
  `agent/store.py` (Task 4) already reads/writes via `message.provider_data`.

This task stays inside the "runtime cluster" (`conversation.py` is one of the three files allowed
to import `pydantic_ai` per `agent/pyproject.toml`'s import-linter contract) — nothing here crosses
that boundary.

- [ ] **Step 1: Add `provider_data` to `Message`**

Change:

```python
@dataclass(frozen=True)
class Message:
    """One turn of plain text. The only shape any code outside this file's
    cluster ever needs to know about a conversation."""

    role: Literal["user", "assistant"]
    content: str
```

to:

```python
@dataclass(frozen=True)
class Message:
    """One turn of plain text, plus whatever provider-opaque bytes came with
    it. The only shape any code outside this file's cluster ever needs to
    know about a conversation.

    provider_data holds a serialized Pydantic AI ModelMessage (e.g. carrying
    Google's function-call signature) when this Message is an assistant
    turn produced by run_turn(); None for user turns and for any assistant
    turn where nothing provider-specific needs preserving. store.py (Gate 18)
    persists these bytes as an opaque bytea column and never parses them -
    only this file (via ModelMessagesTypeAdapter) ever does.
    """

    role: Literal["user", "assistant"]
    content: str
    provider_data: bytes | None = None
```

- [ ] **Step 2: Import `ModelMessagesTypeAdapter`**

In the existing `from pydantic_ai.messages import (...)` block, add `ModelMessagesTypeAdapter` to
the imported names (keep alphabetical, matching the existing style):

```python
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
```

- [ ] **Step 3: Use `provider_data` when rebuilding history**

Change `_to_model_history`:

```python
def _to_model_history(history: list[Message]) -> list[ModelMessage]:
    """Our Message list -> Pydantic AI's message_history kwarg shape."""

    converted: list[ModelMessage] = []
    for message in history:
        if message.role == "user":
            converted.append(ModelRequest(parts=[UserPromptPart(content=message.content)]))
        else:
            converted.append(ModelResponse(parts=[TextPart(content=message.content)]))
    return converted
```

to:

```python
def _to_model_history(history: list[Message]) -> list[ModelMessage]:
    """Our Message list -> Pydantic AI's message_history kwarg shape.

    An assistant Message with provider_data set is rebuilt from those exact
    bytes via ModelMessagesTypeAdapter, rather than a fresh plain-text
    ModelResponse - this is what carries the model's own reasoning/signature
    data across a reload, instead of losing it the moment a conversation is
    read back from the database.
    """

    converted: list[ModelMessage] = []
    for message in history:
        if message.role == "user":
            converted.append(ModelRequest(parts=[UserPromptPart(content=message.content)]))
        elif message.provider_data is not None:
            converted.extend(ModelMessagesTypeAdapter.validate_json(message.provider_data))
        else:
            converted.append(ModelResponse(parts=[TextPart(content=message.content)]))
    return converted
```

- [ ] **Step 4: Populate `provider_data` in `run_turn`**

Change the end of `run_turn`:

```python
    new_messages = [
        Message(role="user", content=question),
        Message(role="assistant", content=result.output),
    ]

    return TurnResult(answer=result.output, new_messages=new_messages, tool_calls=tool_calls)
```

to:

```python
    # The last of Pydantic AI's own new_messages() is the final ModelResponse
    # carrying the answer - serializing just that one message (not the whole
    # turn, which also includes intermediate tool-call/tool-result messages)
    # keeps provider_data minimal: enough to rebuild this one assistant turn
    # on reload, no more.
    provider_data = ModelMessagesTypeAdapter.dump_json([result.new_messages()[-1]])

    new_messages = [
        Message(role="user", content=question),
        Message(role="assistant", content=result.output, provider_data=provider_data),
    ]

    return TurnResult(answer=result.output, new_messages=new_messages, tool_calls=tool_calls)
```

- [ ] **Step 5: Verify with `ask.py`**

Tell the developer: "Run `python scripts/ask.py "What's low on stock?" "What's the price of the
first one?"` from `agent/` (backend must be running over HTTP first, per `ask.py`'s docstring).
Confirm it still answers the follow-up correctly." This proves `provider_data` round-trips through
one live process without breaking the existing Gate 17 behavior — it does not yet prove reload
across a fresh process, which is Task 9.

- [ ] **Step 6: Run import-linter**

Run from `agent/`: `lint-imports`. Expected: passes (all 3 contracts) — `conversation.py` is
already inside the allowed cluster, so this change should not affect the result. If it fails,
report the exact contract violation rather than guessing a fix.

- [ ] **Step 7: Report the change**

Stop here. Report: "`Message.provider_data` added, `_to_model_history`/`run_turn` wired to
`ModelMessagesTypeAdapter`. `ask.py`'s two-question demo still answers the follow-up correctly;
`lint-imports` passes. Ready to commit before Task 9?"

---

### Task 9: The gate's round-trip verification script

**Files:**
- Create: `agent/scripts/verify_store.py`

**Interfaces:**
- Consumes: `agent.store.start_conversation/append_message/load_history` (Task 4),
  `agent.conversation.Message` (Task 8's shape, with `provider_data`).

This is the gate-level check the spec calls for: prove `load_history()` isn't just reading back
in-memory state, by writing in one process invocation and reading in a second, separate one.

- [ ] **Step 1: Write `agent/scripts/verify_store.py`**

```python
"""Gate 18's verification: prove conversations/messages actually round-trip
through Postgres, not just through in-memory state within one process.

Two invocations, not one function call: `--write` creates a conversation and
appends messages (one with fake provider_data bytes, to prove that column
round-trips too), printing the conversation id. `--read <id>` is a SEPARATE
process invocation that loads that id back and prints what it found. Running
these as two separate `python` calls - not two functions in one script - is
what makes this a real test of "did Postgres actually keep it", since a bug
that only worked by accident of shared process memory would still pass a
single-process version of this check.

Usage:

    python scripts/verify_store.py --write
        # prints: conversation id: <n>

    python scripts/verify_store.py --read <n>
        # prints each message's role, content, and whether provider_data is set
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conversation import Message  # noqa: E402
from store import append_message, load_history, start_conversation  # noqa: E402


def _write() -> None:
    conversation_id = start_conversation(title="gate 18 verification")
    append_message(conversation_id, Message(role="user", content="hello"))
    append_message(
        conversation_id,
        Message(role="assistant", content="hi there", provider_data=b'{"fake": "signature bytes"}'),
    )
    print(f"conversation id: {conversation_id}")


def _read(conversation_id: int) -> None:
    history = load_history(conversation_id)
    if not history:
        print(f"no messages found for conversation {conversation_id}")
        return
    for message in history:
        has_provider_data = message.provider_data is not None
        print(f"{message.role}: {message.content!r} (provider_data set: {has_provider_data})")


def main() -> None:
    if sys.argv[1:2] == ["--write"]:
        _write()
    elif sys.argv[1:2] == ["--read"] and len(sys.argv) == 3:
        _read(int(sys.argv[2]))
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the write half**

Tell the developer: "Run `python scripts/verify_store.py --write` from `agent/`. Paste me the
printed conversation id." Wait for the id.

- [ ] **Step 3: Run the read half, as a genuinely separate invocation**

Tell the developer: "Now run `python scripts/verify_store.py --read <id>` (the id from Step 2) —
a fresh `python` process, not the same one." Wait for the output.

Expected output (two lines, in this order):

```
user: 'hello' (provider_data set: False)
assistant: 'hi there' (provider_data set: True)
```

If the order is wrong, or `provider_data set` reads `False` for the assistant line, stop and report
it — either would mean `load_history`'s `ORDER BY id` or `store.py`'s write path has a bug.

- [ ] **Step 4: Report gate completion**

Stop here. Report to the developer: "Gate 18 round-trip verified: a conversation written in one
process reloads correctly in a separate one, including the `provider_data` column. This closes out
Gate 18's own verification (spec section 'Verification for the gate overall'). Ready to commit
`agent/scripts/verify_store.py`, and then to update `docs/AGENT-PLAN.md`'s progress table marking
Gate 18 done?"

---

## Not in this plan

Matches the spec's "Not in this gate" section exactly — do not add any of these:

- `ask.py` gaining a `--conversation <id>` flag to resume an old conversation. `load_history()`
  exists and is proven by Task 9, but nothing wires it into the CLI yet.
- Real auth. `started_by`/`created_by` stay stamped `"system"`.
- Anything in `backend/` beyond the two `include_schemas=False` lines (Task 7).
