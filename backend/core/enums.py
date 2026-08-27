"""Closed vocabularies shared by every layer.

An enum lives here rather than in a service when both adapters and the database
need to agree on the same set of strings. `core/` is the only package both
adapters may import, so it is the only place that agreement can be expressed
once.

Every enum here subclasses `str`. That is not decoration: it means a member IS
its stored value, so SQLAlchemy writes "web_ui" without a converter, Pydantic
serialises it without a converter, and a comparison against a plain string read
back from the database works. The alternative - a plain `Enum` - stores fine
and then fails the first time something compares a loaded row against a literal.
"""

from enum import Enum


class ClientType(str, Enum):
    """Which front door an action came through.

    This exists because `Actor` deliberately does not know. `Actor` has exactly
    `id` and `can()`, and the whole architecture rests on `services/` not being
    able to tell HTTP from MCP. But provenance genuinely needs the answer, so
    the adapter - which knows for certain what it is - passes it down as an
    ordinary argument.

    There is a second, subtler reason it cannot be derived from the actor: when
    the AI agent acts, it carries a *narrowed copy of the user's own token*, so
    `actor.id` is the same human being in both cases. The door is the only
    thing that differs, and only the door knows which one it is.
    """

    WEB_UI = "web_ui"
    MCP_AGENT = "mcp_agent"
    # Migrations, seed scripts, and anything else with no human behind it.
    SYSTEM = "system"


class DraftStatus(str, Enum):
    """Where an Action Draft is in its life.

    PENDING  - proposed, waiting for a human
    APPROVED - a human said yes; reserved for a future two-phase execution
    REJECTED - a human said no. Terminal
    EXECUTED - the handler ran and the change is real. Terminal

    **There is deliberately no EXPIRED.** A draft carries `expires_at`, and
    whether that moment has passed is computed when the row is read. Storing it
    would need something to do the storing, and this project has no scheduler -
    so the value would only ever be written by whoever happened to read the row
    next, which is the same work as computing it plus a write.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
