"""Alembic's entry point. Every `alembic ...` command runs this file first.

Its job is to answer two questions for Alembic:

  1. What SHOULD the database look like?  -> `target_metadata`, below
  2. How do I connect to what it actually looks like?  -> our engine

Given both, `alembic revision --autogenerate` can diff them and write a
migration. That diff is the whole point of the file.

This is a trimmed version of the stock `alembic init` output, with two
deliberate changes from the default, both noted inline: we reuse our own engine
rather than building one from alembic.ini, and we import the models so the
metadata is actually populated.
"""

from logging.config import fileConfig

from alembic import context

from core.database import Base, engine

# `core.models` is imported purely for its side effect, which is unusual enough
# to deserve a comment. Importing the module executes the class definitions in
# it, and every class inheriting from Base registers itself with
# Base.metadata as it is defined. Without this line, Base.metadata is empty,
# autogenerate sees a schema with no tables, and cheerfully writes a migration
# that DROPS everything.
#
# The `noqa: F401` silences "imported but unused" from linters, which are
# right in general and wrong here.
import core.models  # noqa: F401

# The Alembic Config object, providing access to alembic.ini.
config = context.config

# Set up the loggers defined in alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# What the database SHOULD look like: every table registered on Base.
# `.metadata` is SQLAlchemy's in-memory catalogue of tables, populated by the
# import above.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL to a file instead of running it against a database.

    `alembic upgrade head --sql` prints the statements rather than executing
    them - useful when a DBA has to review changes before they touch
    production. We do not use it today; kept because it costs six lines and
    removing it is the kind of thing you regret.
    """
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Explicit, not relying on the default. Gate 18 added a second Postgres
        # schema (`agent`) reached over this same connection, with its own
        # Alembic history. Without this, autogenerate would reflect every
        # schema it can see, compare it against this file's target_metadata
        # (backend's tables only), and propose dropping agent.* as "extra" -
        # exactly the mistake this line rules out structurally rather than
        # relying on a human to catch it in review each time.
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and run migrations against it. The normal path.

    Note we reuse `engine` from core.database rather than calling
    `engine_from_config(config.get_section(...))` as the stock env.py does.
    That default reads the connection string out of alembic.ini - a committed
    file - which is how database passwords end up in git history. Reusing our
    engine means the URL comes from backend/.env via core.config, in exactly
    one place.
    """
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Detect when a column's TYPE changes, not just when columns are
            # added or removed. Off by default because it produces occasional
            # false positives; worth it, because a silently-missed type change
            # is far more painful than a diff you have to eyeball.
            compare_type=True,
            # Same, for server-side defaults.
            compare_server_default=True,
            # See run_migrations_offline()'s identical setting above for why.
            include_schemas=False,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
