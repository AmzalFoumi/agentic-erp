"""HTTP routes for suppliers, the reorder bundler, and purchase orders.

No business logic, same as every other route module: get a session, call the
service, return the result. Domain exceptions are translated centrally by
`api/errors.py`.

Two things worth reading rather than skimming, both the same as inventory.py:

**`date.today()` is called here, in the adapter, and never in `services/`.**
`send_order` takes `today` as a required argument, which is what makes a
lead-time calculation testable at a fixed point in time.

**`client=ClientType.WEB_UI` is hardcoded** on every write, never read from the
request. This adapter *is* the web door, so it says so itself; a caller cannot
claim to be the agent.
"""

from datetime import date

from fastapi import APIRouter, Query, status

from api.deps import CurrentActor, DbSession
from api.responses import BAD_REQUEST as _BAD_REQUEST
from api.responses import CONFLICT as _CONFLICT
from api.responses import FORBIDDEN as _FORBIDDEN
from api.responses import NOT_FOUND as _NOT_FOUND
from api.responses import UNPROCESSABLE as _UNPROCESSABLE
from api.responses import error_responses
from api.schemas import (
    DraftRead,
    PurchaseOrderCreate,
    PurchaseOrderList,
    PurchaseOrderRead,
    ReorderProposal,
    ReorderReportRead,
    SupplierCreate,
    SupplierList,
    SupplierProductCreate,
    SupplierProductList,
    SupplierProductRead,
    SupplierProductUpdate,
    SupplierRead,
    SupplierUpdate,
)
from core.enums import ClientType
from services import purchasing

router = APIRouter(tags=["purchasing"])


def _errors(*codes: int) -> dict[int | str, dict]:
    return error_responses(*codes)


# --- suppliers -------------------------------------------------------------


@router.get(
    "/suppliers",
    response_model=SupplierList,
    responses=_errors(_FORBIDDEN, _UNPROCESSABLE),
)
def list_suppliers(
    session: DbSession,
    actor: CurrentActor,
    active_only: bool = Query(default=False),
) -> SupplierList:
    items = purchasing.list_suppliers(session, actor, active_only=active_only)
    return SupplierList(items=items, total=len(items))


@router.post(
    "/suppliers",
    response_model=SupplierRead,
    status_code=status.HTTP_201_CREATED,
    responses=_errors(_BAD_REQUEST, _FORBIDDEN, _CONFLICT, _UNPROCESSABLE),
)
def create_supplier(
    session: DbSession, actor: CurrentActor, body: SupplierCreate
) -> SupplierRead:
    return purchasing.create_supplier(
        session,
        actor,
        client=ClientType.WEB_UI,
        **body.model_dump(),
    )


@router.get(
    "/suppliers/{supplier_id}",
    response_model=SupplierRead,
    responses=_errors(_FORBIDDEN, _NOT_FOUND, _UNPROCESSABLE),
)
def get_supplier(
    session: DbSession, actor: CurrentActor, supplier_id: int
) -> SupplierRead:
    return purchasing.get_supplier(session, actor, supplier_id=supplier_id)


@router.patch(
    "/suppliers/{supplier_id}",
    response_model=SupplierRead,
    responses=_errors(_BAD_REQUEST, _FORBIDDEN, _NOT_FOUND, _CONFLICT, _UNPROCESSABLE),
)
def update_supplier(
    session: DbSession, actor: CurrentActor, supplier_id: int, body: SupplierUpdate
) -> SupplierRead:
    # `exclude_unset=True` is what makes a partial update partial: a field the
    # caller did not send never reaches the service, so it keeps its `_UNSET`
    # default and the stored value is left alone. Without it, editing the lead
    # time would blank the contact email.
    return purchasing.update_supplier(
        session, actor, supplier_id=supplier_id, **body.model_dump(exclude_unset=True)
    )


# --- the supplier catalogue ------------------------------------------------


@router.get(
    "/suppliers/{supplier_id}/products",
    response_model=SupplierProductList,
    responses=_errors(_FORBIDDEN, _NOT_FOUND, _UNPROCESSABLE),
)
def list_supplier_products(
    session: DbSession, actor: CurrentActor, supplier_id: int
) -> SupplierProductList:
    items = purchasing.list_supplier_products(session, actor, supplier_id=supplier_id)
    return SupplierProductList(items=items, total=len(items))


@router.post(
    "/suppliers/{supplier_id}/products",
    response_model=SupplierProductRead,
    status_code=status.HTTP_201_CREATED,
    responses=_errors(_BAD_REQUEST, _FORBIDDEN, _NOT_FOUND, _CONFLICT, _UNPROCESSABLE),
)
def link_product(
    session: DbSession,
    actor: CurrentActor,
    supplier_id: int,
    body: SupplierProductCreate,
) -> SupplierProductRead:
    return purchasing.link_product(
        session, actor, supplier_id=supplier_id, **body.model_dump()
    )


@router.patch(
    "/supplier-products/{link_id}",
    response_model=SupplierProductRead,
    responses=_errors(_BAD_REQUEST, _FORBIDDEN, _NOT_FOUND, _UNPROCESSABLE),
)
def update_link(
    session: DbSession,
    actor: CurrentActor,
    link_id: int,
    body: SupplierProductUpdate,
) -> SupplierProductRead:
    return purchasing.update_link(
        session, actor, link_id=link_id, **body.model_dump(exclude_unset=True)
    )


# --- the bundler -----------------------------------------------------------


@router.get(
    "/purchasing/reorder-suggestions",
    response_model=ReorderReportRead,
    responses=_errors(_FORBIDDEN, _UNPROCESSABLE),
)
def reorder_suggestions(
    session: DbSession, actor: CurrentActor
) -> ReorderReportRead:
    """What to buy today. Reads only - nothing is written or proposed."""
    return purchasing.scan_reorder(session, actor)


@router.post(
    "/purchasing/reorder-drafts",
    response_model=DraftRead,
    status_code=status.HTTP_201_CREATED,
    responses=_errors(_BAD_REQUEST, _FORBIDDEN, _NOT_FOUND, _UNPROCESSABLE),
)
def propose_reorder(
    session: DbSession, actor: CurrentActor, body: ReorderProposal
) -> DraftRead:
    """Stage one supplier's bundle for approval. No order is created."""
    return purchasing.propose_reorder(
        session,
        actor,
        client=ClientType.WEB_UI,
        supplier_id=body.supplier_id,
        reasoning=body.reasoning,
    )


# --- purchase orders ---------------------------------------------------


@router.get(
    "/purchase-orders",
    response_model=PurchaseOrderList,
    responses=_errors(_BAD_REQUEST, _FORBIDDEN, _UNPROCESSABLE),
)
def list_orders(
    session: DbSession,
    actor: CurrentActor,
    order_status: str | None = Query(default=None, alias="status"),
    supplier_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PurchaseOrderList:
    items, total = purchasing.list_orders(
        session,
        actor,
        status=order_status,
        supplier_id=supplier_id,
        limit=limit,
        offset=offset,
    )
    return PurchaseOrderList(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/purchase-orders",
    response_model=PurchaseOrderRead,
    status_code=status.HTTP_201_CREATED,
    responses=_errors(_BAD_REQUEST, _FORBIDDEN, _NOT_FOUND, _UNPROCESSABLE),
)
def create_order(
    session: DbSession, actor: CurrentActor, body: PurchaseOrderCreate
) -> PurchaseOrderRead:
    from services.purchasing.orders import OrderLineInput

    return purchasing.create_order(
        session,
        actor,
        client=ClientType.WEB_UI,
        supplier_id=body.supplier_id,
        lines=[
            OrderLineInput(
                product_id=line.product_id,
                quantity=line.quantity,
                unit_cost=line.unit_cost,
            )
            for line in body.lines
        ],
        notes=body.notes,
    )


@router.get(
    "/purchase-orders/{order_id}",
    response_model=PurchaseOrderRead,
    responses=_errors(_FORBIDDEN, _NOT_FOUND, _UNPROCESSABLE),
)
def get_order(
    session: DbSession, actor: CurrentActor, order_id: int
) -> PurchaseOrderRead:
    return purchasing.get_order(session, actor, order_id=order_id)


@router.post(
    "/purchase-orders/{order_id}/send",
    response_model=PurchaseOrderRead,
    responses=_errors(_BAD_REQUEST, _FORBIDDEN, _NOT_FOUND, _UNPROCESSABLE),
)
def send_order(
    session: DbSession, actor: CurrentActor, order_id: int
) -> PurchaseOrderRead:
    """Place the order. `date.today()` is read here, never in the service."""
    return purchasing.send_order(
        session, actor, order_id=order_id, today=date.today()
    )


@router.post(
    "/purchase-orders/{order_id}/cancel",
    response_model=PurchaseOrderRead,
    responses=_errors(_BAD_REQUEST, _FORBIDDEN, _NOT_FOUND, _UNPROCESSABLE),
)
def cancel_order(
    session: DbSession, actor: CurrentActor, order_id: int
) -> PurchaseOrderRead:
    return purchasing.cancel_order(session, actor, order_id=order_id)
