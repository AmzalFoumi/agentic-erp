"""add pending approval columns to agent.conversations

Revision ID: b47f0a9e3d12
Revises: c586d296fc6e
Create Date: 2026-08-12 11:00:00.000000+00:00

Gate 20: a turn that stops for human approval now survives a restart. Both
columns are nullable with no default and no backfill - the resting state for
every existing row is "not waiting on anybody", which is already what NULL
means, so this migration cannot change the meaning of existing data.

RLS was enabled on this table by c586d296fc6e and applies to the whole table,
not per column, so nothing about that needs repeating here.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b47f0a9e3d12"
down_revision: str | None = "c586d296fc6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.add_column(
        "conversations",
        sa.Column("pending_state", sa.LargeBinary(), nullable=True),
        schema="agent",
    )
    op.add_column(
        "conversations",
        # timezone=True -> TIMESTAMPTZ. An approval's age is compared against
        # "now" by a human in some timezone; a naive timestamp would make that
        # comparison quietly wrong rather than obviously wrong.
        sa.Column("pending_since", sa.DateTime(timezone=True), nullable=True),
        schema="agent",
    )


def downgrade() -> None:
    """Undo this migration."""
    op.drop_column("conversations", "pending_since", schema="agent")
    op.drop_column("conversations", "pending_state", schema="agent")
