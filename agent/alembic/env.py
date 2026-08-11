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
