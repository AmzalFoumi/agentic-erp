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


class PurchaseOrderStatus(str, Enum):
    """Where a purchase order is in its life.

    draft              - being built. Lines may still be changed
    sent               - placed with the supplier. Lines are now frozen,
                         because gate 30 compares what arrives against them
    partially_received - some lines short or still outstanding (gate 30)
    received           - complete (gate 30)
    cancelled          - abandoned from draft or sent. Terminal

    `partially_received` and `received` are declared now and only reachable in
    gate 30; `cancelled` is reachable already, from either state. A state
    machine with holes in it is harder to read than one whose later states are
    written down and unused.

    These five values, not the external spec's DRAFT/APPROVED/DISPATCHED/
    FULFILLED - see docs/FEATURES-PLAN.md, row 7. "Partially received" is
    exactly what a dock discrepancy produces, and gate 30 is built on it.
    """

    DRAFT = "draft"
    SENT = "sent"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class CreditMemoReason(str, Enum):
    """Why the shop is owed money on a receipt.

    Two reasons only, matching gate 30's design: a line either arrived short
    of what was ordered, or arrived damaged. A line can carry both - a
    shortfall and a damage credit are two separate rows, not one merged
    figure, so a manager reading the supplier's credit list can tell which
    problem is which.
    """

    SHORT_SHIPPED = "short_shipped"
    DAMAGED = "damaged"


class CreditMemoStatus(str, Enum):
    """Where a credit memo stands.

    One value today, on purpose. `docs/superpowers/specs/2026-08-27-gate30-
    delivery-discrepancy-design.md`'s "Alternatives considered" defers
    tracking a credit against a future order - that would need a second
    status (e.g. APPLIED). A real enum column with one member costs nothing
    now and needs no migration to grow later.
    """

    OPEN = "open"
