"""HTTP routes for inventory lots and the spoilage report.

No business logic, same as every other route module: get a session, call the
service, return the result. Domain exceptions are translated centrally by
`api/errors.py`.

Two things in here are worth reading rather than skimming.

**`date.today()` is called here, in the adapter, and never in `services/`.**
Every service function that reasons about expiry takes `today` as a required
argument. That is what makes a feature built entirely from date arithmetic
testable at a fixed point in time - a service that reads the clock can only be
tested by changing the clock. The adapter is the right place to ask what day it
is, because the adapter is where the outside world starts.

**`client=ClientType.WEB_UI` is hardcoded** on every write, never read from the
request. This adapter *is* the web door, so it says so itself; a caller cannot
claim to be the agent. See routes/drafts.py for the longer version.
"""

from datetime import date

from fastapi import APIRouter, Query

from api.deps import CurrentActor, DbSession
from api.responses import BAD_REQUEST as _BAD_REQUEST
from api.responses import FORBIDDEN as _FORBIDDEN
from api.responses import NOT_FOUND as _NOT_FOUND
from api.responses import UNPROCESSABLE as _UNPROCESSABLE
from api.responses import error_responses
from api.schemas import (
    DraftRead,
    LotList,
    LotReceive,
    LotRead,
    MarkdownProposal,
    SpoilageReportRead,
)
from core.enums import ClientType
from services import lots, spoilage

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _errors(*codes: int) -> dict[int | str, dict]:
    return error_responses(*codes, descriptions={_NOT_FOUND: "No such product."})


@router.get(
    "/spoilage",
    response_model=SpoilageReportRead,
    responses=_errors(_FORBIDDEN, _UNPROCESSABLE),
)
def get_spoilage_report(
    session: DbSession,
    actor: CurrentActor,
    within_days: int = Query(
        default=None,
        ge=0,
        le=30,
        description="Scan horizon in days. Defaults to the discount ladder's reach.",
    ),
) -> SpoilageReportRead:
    """What is about to expire, and what marking it down would recover.

    Read-only. Stages nothing and changes no price - the numbers here are a
    preview of what `POST /inventory/spoilage/propose` would put in front of a
    human for approval.

    The two money totals are returned separately and must stay that way. One is
    money already spent, the other is a forecast.
    """
    report = spoilage.scan_spoilage(
        session,
        actor,
        today=date.today(),
        **({"within_days": within_days} if within_days is not None else {}),
    )
    return SpoilageReportRead.model_validate(report)


@router.post(
    "/spoilage/propose",
    response_model=DraftRead,
    status_code=201,
    responses=_errors(_FORBIDDEN, _BAD_REQUEST, _UNPROCESSABLE),
)
def propose_markdown(
    session: DbSession,
    actor: CurrentActor,
    proposal: MarkdownProposal,
) -> DraftRead:
    """Stage a markdown as a draft for a human to approve. **No price moves.**

    Returns the created draft, which then appears in `/approvals` alongside
    anything the AI agent proposed. Approving it there is what actually changes
    prices, and that needs `draft.decide` - which the agent does not hold.

    A 400 means there was nothing expiring within the horizon, so there was
    nothing to propose. That is a refusal rather than an empty draft, because a
    queue whose value is "everything here needs a decision" must not fill with
    items that need none.
    """
    draft = spoilage.propose_markdown(
        session,
        actor,
        client=ClientType.WEB_UI,
        today=date.today(),
        reasoning=proposal.reasoning,
        **(
            {"within_days": proposal.within_days}
            if proposal.within_days is not None
            else {}
        ),
    )
    return DraftRead.model_validate(draft)


@router.get(
    "/products/{product_id}/lots",
    response_model=LotList,
    responses=_errors(_FORBIDDEN, _NOT_FOUND, _UNPROCESSABLE),
)
def list_lots(
    session: DbSession,
    actor: CurrentActor,
    product_id: int,
    include_empty: bool = Query(
        default=False,
        description="Include lots already consumed to zero. History, not stock.",
    ),
) -> LotList:
    """A product's lots, soonest expiry first, undated last.

    That ordering is the same one stock is consumed in, and it is defined once
    in `services/lots.py` so two views of the same lots cannot disagree.
    """
    items = lots.list_lots(
        session, actor, product_id=product_id, include_empty=include_empty
    )
    return LotList(
        items=[LotRead.model_validate(lot) for lot in items], total=len(items)
    )


@router.post(
    "/products/{product_id}/lots",
    response_model=LotRead,
    status_code=201,
    responses=_errors(_FORBIDDEN, _NOT_FOUND, _BAD_REQUEST, _UNPROCESSABLE),
)
def receive_lot(
    session: DbSession,
    actor: CurrentActor,
    product_id: int,
    delivery: LotReceive,
) -> LotRead:
    """Book a delivery in as a new lot, and update the product's stock total.

    The total is not sent by the caller and never could be: it is recalculated
    from the lots themselves, in one place, so the summary cannot drift from
    the rows it summarises.
    """
    lot = lots.receive_lot(
        session,
        actor,
        client=ClientType.WEB_UI,
        product_id=product_id,
        lot_code=delivery.lot_code,
        quantity=delivery.quantity,
        cost_price=delivery.cost_price,
        expiry_date=delivery.expiry_date,
    )
    return LotRead.model_validate(lot)
