"""HTTP routes for the Action Draft approval queue.

No business logic. Get a session, call the service, return the result - the
same shape as routes/products.py, and the reason there is not a single
try/except in this file: every domain exception is translated centrally by
api/errors.py, so a `NotFoundError` raised three layers down arrives as a 404
carrying the standard envelope without this file knowing it happened.

The one thing worth reading closely is `client=ClientType.WEB_UI` on the two
write routes. It is hardcoded, and never read from anything the caller sends.
That is the whole point of the parameter: a client cannot claim to be a
different door, because this adapter *is* the web door and says so itself. The
MCP adapter says `MCP_AGENT` for the same reason. If this were a request field,
the provenance column would record whatever the caller typed.
"""

from fastapi import APIRouter, Query

from api.deps import CurrentActor, DbSession
from api.responses import BAD_REQUEST as _BAD_REQUEST
from api.responses import FORBIDDEN as _FORBIDDEN
from api.responses import NOT_FOUND as _NOT_FOUND
from api.responses import UNPROCESSABLE as _UNPROCESSABLE
from api.responses import error_responses
from api.schemas import DraftApproval, DraftList, DraftRead
from core.enums import ClientType, DraftStatus
from services import drafts

router = APIRouter(prefix="/drafts", tags=["drafts"])


def _draft_errors(*codes: int) -> dict[int | str, dict]:
    """`error_responses` with this resource's own 404 wording."""
    return error_responses(
        *codes, descriptions={_NOT_FOUND: "No such action draft."}
    )


@router.get(
    "",
    response_model=DraftList,
    responses=_draft_errors(_FORBIDDEN, _UNPROCESSABLE),
)
def list_drafts(
    session: DbSession,
    actor: CurrentActor,
    status: DraftStatus | None = Query(
        default=None, description="Filter by status. Omit for all."
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List action drafts, newest first, optionally filtered by status.

    `{items, total}` where `total` counts everything matching `status`
    regardless of the window, so page numbers are buildable - the same contract
    as GET /products.

    Typing `status` as `DraftStatus` rather than `str` means FastAPI rejects an
    unknown value with a 422 before the service is reached, and the generated
    TypeScript gets a union type rather than `string`. A typo in a query string
    becomes a compile error in the frontend instead of an empty list.
    """
    return {
        "items": drafts.list_drafts(
            session, actor, status=status, limit=limit, offset=offset
        ),
        "total": drafts.count_drafts(session, actor, status=status),
    }


@router.get(
    "/{draft_id}",
    response_model=DraftRead,
    responses=_draft_errors(_FORBIDDEN, _NOT_FOUND),
)
def get_draft(draft_id: int, session: DbSession, actor: CurrentActor):
    """One action draft, including its full payload and reasoning."""
    return drafts.get_draft(session, actor, draft_id=draft_id)


@router.post(
    "/{draft_id}/approve",
    response_model=DraftRead,
    responses=_draft_errors(
        _BAD_REQUEST, _FORBIDDEN, _NOT_FOUND, _UNPROCESSABLE
    ),
)
def approve_draft(
    draft_id: int, body: DraftApproval, session: DbSession, actor: CurrentActor
):
    """Approve a draft and run it, optionally with an edited payload.

    Requires `draft.decide`, which the AI agent does not hold - approving is
    the one thing in this feature only a human can do, and there is no MCP tool
    for it either.

    A 400 here means the draft is no longer decidable (already decided, or
    expired) or the payload does not match its type's schema. Both are business
    rules, so both arrive as `ValidationError` and translate to 400 rather than
    422 - 422 is reserved for a body that fails FastAPI's own schema check,
    which is a different failure with a different fix.
    """
    return drafts.approve_draft(
        session,
        actor,
        client=ClientType.WEB_UI,
        draft_id=draft_id,
        payload=body.payload,
    )


@router.post(
    "/{draft_id}/reject",
    response_model=DraftRead,
    responses=_draft_errors(_BAD_REQUEST, _FORBIDDEN, _NOT_FOUND),
)
def reject_draft(draft_id: int, session: DbSession, actor: CurrentActor):
    """Reject a draft. Terminal, and runs nothing.

    Takes the same `draft.decide` permission as approving: neither changes the
    world without a human, one simply closes the door. See
    docs/FEATURES-PLAN.md for why the two were not given separate permissions.
    """
    return drafts.reject_draft(
        session, actor, client=ClientType.WEB_UI, draft_id=draft_id
    )
