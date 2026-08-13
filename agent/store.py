"""Persistence for conversations and messages. The only file any caller needs
to import to save or reload a conversation - callers never see database.py or
models.py directly.

No new error handling: if Postgres is unreachable or a write fails,
SQLAlchemy's own exception propagates uncaught. This matches
conversation.py's existing policy (a tool failure becomes a ModelRetry;
everything else propagates) - no caller needs different behavior yet.
"""

from datetime import datetime

from sqlalchemy import func, update

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


def conversation_exists(conversation_id: int) -> bool:
    """Is there a conversation with this id?

    Needed because `load_history` returns [] for an unknown id and for a real
    conversation nobody has spoken in yet, and an HTTP caller has to tell those
    apart - one is a 404, the other is a fresh chat window.
    """
    with get_session() as session:
        return session.get(ConversationRow, conversation_id) is not None


def save_pending(conversation_id: int, resume_state: bytes) -> None:
    """Park a turn that stopped for human approval.

    `resume_state` is conversation.py's `TurnResult.resume_state` - the
    interrupted run's serialized message list - stored opaquely, never parsed
    here. `pending_since` is stamped from the database clock rather than the
    application's, so the age of an approval does not depend on which machine
    asked.

    Gate 19 held this in memory only and Gate 20 inherited the question of where
    it lives; this is the answer. Nothing is appended to `messages`, because a
    half-finished turn is not conversation history.
    """
    with get_session() as session:
        session.execute(
            update(ConversationRow)
            .where(ConversationRow.id == conversation_id)
            .values(pending_state=resume_state, pending_since=func.now())
        )
        session.commit()


def clear_pending(conversation_id: int) -> None:
    """Mark a conversation as no longer waiting on a person.

    Called when a paused turn completes - on approve *and* on deny, because both
    are decisions. Unconditional rather than checked-then-cleared: setting NULL
    on a row that is already NULL is the correct no-op, and a caller that clears
    a conversation which never paused has not broken anything.
    """
    with get_session() as session:
        session.execute(
            update(ConversationRow)
            .where(ConversationRow.id == conversation_id)
            .values(pending_state=None, pending_since=None)
        )
        session.commit()


def load_pending(conversation_id: int) -> tuple[bytes, datetime] | None:
    """The parked turn for this conversation, or None if it is not waiting.

    Returns both halves together because they are only ever meaningful together:
    the bytes say what is pending and the timestamp says how stale it is. A tuple
    rather than two functions so a caller cannot read one and forget the other.
    """
    with get_session() as session:
        row = session.get(ConversationRow, conversation_id)
        if row is None or row.pending_state is None or row.pending_since is None:
            return None
        return row.pending_state, row.pending_since


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
