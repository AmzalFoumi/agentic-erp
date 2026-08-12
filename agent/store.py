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
