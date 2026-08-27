"""The Action Draft queue: propose now, decide later.

Follows every convention established in services/products.py - session first,
actor second, everything else keyword-only, `actor.can()` before any write,
exceptions rather than None or False, and the service owns its own commit. Read
that file first if any of those look arbitrary; the reasoning is written out
there and not repeated here.

Two things are specific to this module, and both are the reason it exists:

**The handler runs as the approving human, not as the proposer.** The agent
writes the draft; a manager approves it; the change is then made with the
*manager's* actor. So the audit columns on whatever the handler touches name
the person who took responsibility, which is the entire point of an approval
queue. An agent that could propose and then have its own identity stamped on
the result would be an agent acting unsupervised with extra steps.

**The payload is validated twice.** Once here on creation, and again on
approval, because `approve_draft` accepts an edited payload. Validating only on
creation would mean the schema guarded the proposer and never the editor - and
an edited payload is where a human can type anything they like.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.actor import Actor
from core.enums import ClientType, DraftStatus
from core.exceptions import NotFoundError, ValidationError
from core.models import ActionDraft
from services import draft_types
from services.guards import require_permission

# How long a proposal stays actionable unless the caller says otherwise.
#
# 24 hours because these are perishable in the literal sense. A markdown
# proposal for stock expiring tomorrow is worthless the day after; a purchase
# order assembled from this morning's stock levels should not be executed next
# week against numbers that have moved. A stale draft approved by accident is a
# worse outcome than one that has to be regenerated - regenerating costs a
# click, and executing a stale one costs money.
DEFAULT_EXPIRY_HOURS = 24


def _require_actionable(draft: ActionDraft) -> None:
    """Raise unless this draft is still waiting and still in date.

    Shared by approve and reject so the two can never disagree about what
    "still open" means. A draft that could be rejected but not approved - or
    the reverse - would be a state nobody designed.
    """
    if draft.status != DraftStatus.PENDING:
        raise ValidationError(
            f"Draft {draft.id} is already {draft.status}, so it can no longer "
            "be decided."
        )
    if draft.is_expired:
        raise ValidationError(
            f"Draft {draft.id} expired at {draft.expires_at.isoformat()} and "
            "can no longer be executed."
        )


def _get_or_raise(session: Session, draft_id: int) -> ActionDraft:
    """Load a draft by id, or raise NotFoundError.

    Separate from `get_draft` below because the two differ in one important
    way: `get_draft` is a read and checks `draft.read`, while approve and
    reject check `draft.decide` and must not *also* demand `draft.read`. A
    manager who can decide but cannot browse is an odd configuration, but it
    should not fail with a confusing error about the wrong permission.
    """
    draft = session.get(ActionDraft, draft_id)
    if draft is None:
        raise NotFoundError(f"No action draft with id {draft_id}.")
    return draft


# --- writes ----------------------------------------------------------------


def create_draft(
    session: Session,
    actor: Actor,
    *,
    client: ClientType,
    draft_type: str,
    payload: dict,
    reasoning: str,
    cost_at_risk: Decimal | None = None,
    projected_recovery: Decimal | None = None,
    expires_in_hours: int = DEFAULT_EXPIRY_HOURS,
) -> ActionDraft:
    """Stage a proposal. Changes nothing operational.

    Creating a draft is safe by construction: it writes one row that no other
    part of the system acts on until a human approves it. That is why the AI
    agent is allowed to do this without an in-conversation confirmation, while
    remaining unable to change a single price. See docs/FEATURES-PLAN.md,
    decision 1 - the human approval did not disappear, it moved to a screen
    where the whole proposal can be read and edited.
    """
    require_permission(actor, "draft.create")

    if not reasoning.strip():
        # The human reading the card needs to know why. A draft with no
        # reasoning is a button with no label, and the manager's only honest
        # response to it is to reject it.
        raise ValidationError("A draft must carry a reason.")

    if expires_in_hours < 0:
        raise ValidationError("expires_in_hours cannot be negative.")

    # Raises for an unknown type or a payload of the wrong shape, before
    # anything is written. The parsed object is discarded - the dict is what
    # gets stored, because JSONB holds JSON and not Python objects - but the
    # validation has done its work by not raising.
    draft_types.validate_payload(draft_type, payload)

    draft = ActionDraft(
        draft_type=draft_type,
        status=DraftStatus.PENDING,
        payload=payload,
        reasoning=reasoning.strip(),
        cost_at_risk=cost_at_risk,
        projected_recovery=projected_recovery,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_in_hours),
        created_by=actor.id,
        created_via=client,
    )
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return draft


def approve_draft(
    session: Session,
    actor: Actor,
    *,
    client: ClientType,
    draft_id: int,
    payload: dict | None = None,
) -> ActionDraft:
    """Say yes, optionally with edits, and run the handler.

    `payload` replaces the stored one when given. That is the inline adjuster
    the design calls for: a manager who agrees with the idea but wants 30%
    instead of 50% should not have to reject the draft and ask the agent to
    think again.

    **The order of the checks below is the design, not an accident.**
    Permission, then whether the draft is still open, then payload validation,
    then the handler, then the status update. Everything that can refuse
    happens before anything runs, so a refusal never leaves half a change
    behind - and the handler runs before the status is written, so a handler
    that raises leaves the draft PENDING and retryable rather than marked
    EXECUTED against work that did not happen.
    """
    require_permission(actor, "draft.decide")

    draft = _get_or_raise(session, draft_id)
    _require_actionable(draft)

    effective_payload = payload if payload is not None else draft.payload

    # The second validation - the one that guards the editor rather than the
    # agent. Raises before the handler is reached.
    validated = draft_types.validate_payload(draft.draft_type, effective_payload)
    spec = draft_types.spec_for(draft.draft_type)

    # The handler receives the APPROVING actor, so whatever rows it writes
    # record the manager who took responsibility - not the agent that proposed
    # it. This single argument is what makes the queue an accountability
    # mechanism rather than a delay.
    spec.handler(session, actor, client, validated)

    draft.payload = effective_payload
    draft.status = DraftStatus.EXECUTED
    draft.decided_by = actor.id
    draft.decided_at = datetime.now(timezone.utc)
    draft.decided_via = client

    session.commit()
    session.refresh(draft)
    return draft


def reject_draft(
    session: Session, actor: Actor, *, client: ClientType, draft_id: int
) -> ActionDraft:
    """Say no. Terminal, and runs nothing.

    Rejecting takes the same `draft.decide` permission as approving. The
    security difference between the two is negligible - neither changes the
    world, one just closes the door - and every distinct permission costs seven
    configuration edits plus a rebuild of the shipped ThunderID seed, with a
    failure mode that is silent. See docs/FEATURES-PLAN.md.
    """
    require_permission(actor, "draft.decide")

    draft = _get_or_raise(session, draft_id)
    _require_actionable(draft)

    draft.status = DraftStatus.REJECTED
    draft.decided_by = actor.id
    draft.decided_at = datetime.now(timezone.utc)
    draft.decided_via = client

    session.commit()
    session.refresh(draft)
    return draft


# --- reads -----------------------------------------------------------------


def get_draft(session: Session, actor: Actor, *, draft_id: int) -> ActionDraft:
    """One draft, or raise NotFoundError.

    Raising rather than returning `ActionDraft | None` for the reason spelled
    out in services/products.py: a nullable return is a check the caller can
    forget, and this one would be forgotten in an adapter that then rendered
    "None" into a page.
    """
    require_permission(actor, "draft.read")
    return _get_or_raise(session, draft_id)


def list_drafts(
    session: Session,
    actor: Actor,
    *,
    status: DraftStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ActionDraft]:
    """A page of drafts, newest first.

    Newest first, like the product list, but for a different reason: an
    approval queue is read from the top, and the newest proposal is the one
    still worth acting on. `id DESC` rather than `created_at DESC` because ids
    are assigned in insertion order and are unique, so the ordering is total -
    two drafts created in the same millisecond would otherwise come back in an
    unpredictable order and paginate unstably.
    """
    require_permission(actor, "draft.read")

    stmt = select(ActionDraft)
    if status is not None:
        stmt = stmt.where(ActionDraft.status == status)

    stmt = stmt.order_by(ActionDraft.id.desc()).limit(limit).offset(offset)
    return list(session.scalars(stmt))


def count_drafts(
    session: Session, actor: Actor, *, status: DraftStatus | None = None
) -> int:
    """How many drafts match, ignoring limit and offset.

    Shares its filter with `list_drafts` for the reason `_search_filter` exists
    in products.py: a total that counts rows the list would not return produces
    a pagination control promising a page that comes back empty. Here the
    filter is one `where`, so it is inlined in both rather than extracted - but
    if a second filter is ever added, extract it in the same commit.
    """
    require_permission(actor, "draft.read")

    stmt = select(func.count()).select_from(ActionDraft)
    if status is not None:
        stmt = stmt.where(ActionDraft.status == status)
    return session.scalar(stmt) or 0
