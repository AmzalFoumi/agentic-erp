"""Every query in the purchasing package. Private to it.

### Why the queries are collected here

So the use-case files read as business rules rather than as SQL. `reorder.py`
should be legible to someone who has never used SQLAlchemy: it decides which
supplier to buy from and how much, and it asks this module for rows.

### What it does not do

No permission checks and no commits, exactly like
`services/lots.py::recalculate_on_hand`. It is a step inside somebody else's
unit of work: the use case has already checked the permission for the operation
this is part of, and the use case decides when the transaction ends.

The leading underscore is the whole contract. Nothing outside
`services/purchasing/` imports this module, and `__init__.py` does not
re-export it.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from core.models import (
    Product,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierProduct,
)

# --- suppliers -------------------------------------------------------------


def get_supplier(session: Session, supplier_id: int) -> Supplier | None:
    return session.get(Supplier, supplier_id)


def get_supplier_by_name(session: Session, name: str) -> Supplier | None:
    return session.execute(
        select(Supplier).where(Supplier.name == name)
    ).scalar_one_or_none()


def list_suppliers(session: Session, *, active_only: bool = False) -> list[Supplier]:
    statement = select(Supplier)
    if active_only:
        statement = statement.where(Supplier.is_active.is_(True))
    return list(session.execute(statement.order_by(Supplier.name.asc())).scalars())


# --- supplier catalogue ----------------------------------------------------


def get_link(session: Session, link_id: int) -> SupplierProduct | None:
    return session.get(SupplierProduct, link_id)


def find_link(
    session: Session, *, supplier_id: int, product_id: int
) -> SupplierProduct | None:
    return session.execute(
        select(SupplierProduct).where(
            SupplierProduct.supplier_id == supplier_id,
            SupplierProduct.product_id == product_id,
        )
    ).scalar_one_or_none()


def links_for_supplier(session: Session, supplier_id: int) -> list[SupplierProduct]:
    return list(
        session.execute(
            select(SupplierProduct)
            .where(SupplierProduct.supplier_id == supplier_id)
            .order_by(SupplierProduct.id.asc())
        ).scalars()
    )


def links_for_products(
    session: Session, product_ids: Sequence[int]
) -> list[SupplierProduct]:
    """Every supplier offer for the given products, from active suppliers only.

    An inactive supplier is one we have stopped buying from, so their prices
    must not influence which supplier the bundler picks.

    Ordered so the caller can rely on a stable sequence: the tiebreak rules in
    reorder.py depend on a total order existing, and getting it from the
    database is cheaper and more reliable than re-sorting in Python.
    """
    if not product_ids:
        return []
    return list(
        session.execute(
            select(SupplierProduct)
            .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
            .where(
                SupplierProduct.product_id.in_(product_ids),
                Supplier.is_active.is_(True),
            )
            .order_by(
                SupplierProduct.product_id.asc(),
                SupplierProduct.is_preferred.desc(),
                SupplierProduct.unit_cost.asc(),
                SupplierProduct.supplier_id.asc(),
            )
        ).scalars()
    )


# --- products --------------------------------------------------------------


def low_products(session: Session) -> list[Product]:
    """Products at or below their reorder level.

    `Product.needs_reorder` is a hybrid_property, so this filters in the
    database rather than loading the catalogue and sieving it in Python.
    """
    return list(
        session.execute(
            select(Product).where(Product.needs_reorder).order_by(Product.id.asc())
        ).scalars()
    )


def products_by_id(session: Session, product_ids: Sequence[int]) -> dict[int, Product]:
    if not product_ids:
        return {}
    rows = session.execute(
        select(Product).where(Product.id.in_(product_ids))
    ).scalars()
    return {product.id: product for product in rows}


# --- orders ------------------------------------------------------------


def get_order(session: Session, order_id: int) -> PurchaseOrder | None:
    """One order with its lines already loaded.

    `selectinload` fetches the lines in a second query rather than letting each
    one lazy-load on first access. Without it, rendering an order of twenty
    lines is twenty-one queries.
    """
    return session.execute(
        select(PurchaseOrder)
        .where(PurchaseOrder.id == order_id)
        .options(
            selectinload(PurchaseOrder.lines),
            selectinload(PurchaseOrder.credit_memos),
        )
    ).scalar_one_or_none()


def list_orders(
    session: Session,
    *,
    status: str | None = None,
    supplier_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[PurchaseOrder], int]:
    """A page of orders, newest first, and the total matching the filters."""
    filters = []
    if status is not None:
        filters.append(PurchaseOrder.status == status)
    if supplier_id is not None:
        filters.append(PurchaseOrder.supplier_id == supplier_id)

    total = session.execute(
        select(func.count()).select_from(PurchaseOrder).where(*filters)
    ).scalar_one()

    rows = session.execute(
        select(PurchaseOrder)
        .where(*filters)
        .options(selectinload(PurchaseOrder.lines))
        .order_by(PurchaseOrder.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars()

    return list(rows), int(total)


def sum_line_values(session: Session, order_id: int):
    """The order's line total, summed in the database.

    Returns a Decimal. COALESCE because SUM over zero rows is NULL in SQL, not
    0 - an order whose last line was removed would otherwise write NULL into a
    NOT NULL column and fail at flush time with an error naming the column
    rather than the cause. Same trap as lots.recalculate_on_hand.
    """
    return session.execute(
        select(
            func.coalesce(
                func.sum(
                    PurchaseOrderLine.unit_cost * PurchaseOrderLine.quantity_ordered
                ),
                0,
            )
        ).where(PurchaseOrderLine.purchase_order_id == order_id)
    ).scalar_one()
