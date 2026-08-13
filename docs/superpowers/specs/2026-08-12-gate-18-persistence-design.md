# Gate 18 — Persistence Design

**Status:** Approved by user 2026-08-12, section by section. Feeds `docs/superpowers/plans/`
implementation plan; the permanent record of *why* remains `docs/AGENT-PLAN.md`'s Gate 18 section
(~line 1051) and its two forward notes (~line 745, ~line 924) — this doc is the disposable design
scaffold, not a second source of truth.

**Goal:** conversations and messages persisted to Postgres and reloadable, using the agent's own
Postgres schema and its own Alembic history — completely invisible to `backend/`'s Alembic setup.

## Architecture

Same Supabase Postgres instance backend already uses — **not** a separate database. Isolation
comes from a separate Postgres **schema** named `agent` (next to backend's `public`), decided
2026-08-05 (`docs/AGENT-PLAN.md` "Decision: the agent owns its own schema and its own Alembic").
This design makes that isolation explicit in code and in `backend/`'s own migration config,
rather than resting on Alembic's `include_schemas` default (`False`, confirmed against
`alembic.sqlalchemy.org/en/latest/api/runtime.html` on 2026-08-12) staying unchanged forever.

## Files

```
agent/database.py     # engine, SessionLocal, Base — mirrors core/database.py's pattern
agent/models.py        # SQLAlchemy ORM: ConversationRow, MessageRow
agent/store.py         # the only file callers use; wraps database.py + models.py
agent/alembic/         # own env.py, versions/ — independent history from backend/alembic/
agent/pyproject.toml   # gains version_table_schema = "agent" for the alembic contract
```

`agent/config.py` gains a `database_url` setting — same Supabase host/session-pooler style as
`backend/core/config.py`'s, a separate setting because `agent/` never imports `backend/`.

## Schema

```
agent.conversations
  id           serial, primary key
  title        text, nullable
  started_by   text, not null, default "system"
  created_at   timestamptz, server default now()

agent.messages
  id                serial, primary key
  conversation_id   int, foreign key -> agent.conversations.id, not null
  role              text, not null            ("user" or "assistant")
  content           text, not null
  provider_data     bytea, nullable
  created_by        text, not null, default "system"
  created_at        timestamptz, server default now()
```

- Integer serial PKs, matching backend's `Product` convention (`core/models.py`) — no reason to
  introduce UUIDs for this gate.
- `started_by`/`created_by` follow the same deferral pattern as backend's `created_by`/`updated_by`
  (`core/models.py:140-141`): the column exists now, stamped `"system"` (the only actor that
  exists today), so wiring in real auth later is a data change, not a migration.
- `title` exists so a human can search conversations later; no auto-summarization logic in this
  gate, the column is just there.
- RLS enabled (deny-all, no policies) on both tables via a hand-written migration — same pattern
  as backend's `enable_rls_on_alembic_version` migration, since RLS is not a column autogenerate
  can see.

## The opaque-bytes field (`provider_data`)

Pydantic AI's model responses carry provider-specific "reasoning" data (e.g. Google's function-
call signature) that our own `Message` dataclass in `conversation.py` currently discards, keeping
only plain text. Losing it means a reloaded conversation's follow-up call to the model starts
without that inner context. `docs/AGENT-PLAN.md`'s Gate 15b note (~line 745) flagged this as a
known Gate 18 requirement, not a surprise.

**Decision:** `Message` (in `conversation.py`) gains one new optional field:

```python
@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str
    provider_data: bytes | None = None
```

Only `conversation.py` ever populates or interprets `provider_data` — it stays inside the
Gate 17 "runtime cluster" (the three files allowed to import `pydantic_ai`). `store.py` persists
whatever is there (or `NULL`) as a `bytea` column, never parsing it. This keeps the design
provider-agnostic: a future non-Google provider would populate the same field with its own opaque
bytes, using the same mechanism, and `store.py` would not need to change.

Size/cost check: these blobs are small (low hundreds of bytes to a few KB per message, not files),
trivial against Supabase's free-tier 500MB.

## store.py's public interface

```python
def start_conversation(*, title: str | None = None) -> int:
    """Creates a conversation row, returns its id."""

def append_message(conversation_id: int, message: Message) -> None:
    """Writes one Message (from conversation.py) as a row."""

def load_history(conversation_id: int) -> list[Message]:
    """Reads all rows for a conversation, ordered by id, rebuilds the Message list."""
```

`ask.py` (Gate 17's script) calls `start_conversation()` once at startup and `append_message()`
after each turn. It does **not** gain a `--conversation <id>` flag to resume an old one in this
gate — that edges into Gate 20's HTTP surface / the resumability deferral, which stays explicitly
out of scope. `load_history()` still exists and is proven by this gate's own verification step
(round-trip test), just not wired into the CLI yet.

## The two explicit isolation guards

Two places where this design deliberately does not rely on a default staying the way it is today:

1. **`agent/database.py`'s `Base`:**
   ```python
   from sqlalchemy import MetaData
   from sqlalchemy.orm import DeclarativeBase

   class Base(DeclarativeBase):
       metadata = MetaData(schema="agent")
   ```
   Every table SQLAlchemy emits is schema-qualified (`agent.conversations`, not `conversations`)
   by definition in the Python model, independent of the connecting role's `search_path`.

2. **`backend/alembic/env.py`'s two `context.configure(...)` calls** (currently at lines ~55-60
   and ~76-86) each gain an explicit `include_schemas=False`, with a comment naming this decision.
   Alembic's own docs confirm `False` is already the default (checked 2026-08-12), so this changes
   no behavior today — it makes the boundary survive a future Alembic version changing that
   default out from under this project.

## The negative-case verification (the reason this design exists)

After Gate 18's own migrations are applied, run `alembic revision --autogenerate` **from
`backend/`** and confirm the generated file is empty. This proves `backend/`'s `Base.metadata`
never learned about `agent.conversations`/`agent.messages` — the two schemas are genuinely
isolated, not isolated by an unenforced convention.

## Verification for the gate overall

A small round-trip check: call `start_conversation()`, `append_message()` a couple of times, then
`load_history()` in a way that proves it isn't just reading back in-memory state (e.g. a fresh
script invocation or a fresh session) — confirming the reloaded list matches what was written,
including a message that carries non-`None` `provider_data`.

## Error handling

No new error handling. If Postgres is unreachable, `store.py`'s calls raise SQLAlchemy's own
exception, uncaught — the same "no caller needs different behavior yet" reasoning already applied
to `conversation.py` (a tool failure already becomes a `ModelRetry`; anything else propagates).
`ask.py` crashes with a traceback naming the problem rather than silently continuing without
persistence.

## Not in this gate

- Resumability. History survives; an interrupted turn does not. `ask.py` does not gain a way to
  continue an old conversation by ID.
- Real auth. `started_by`/`created_by` are stamped `"system"` — the columns exist so a later auth
  gate is a data change, not a schema migration.
- Anything in `backend/` beyond the two `include_schemas=False` lines in `env.py`.
