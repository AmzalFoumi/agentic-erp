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
