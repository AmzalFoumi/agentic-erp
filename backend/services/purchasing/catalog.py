"""Which supplier stocks which product, at what price, in what pack size.

Three fields carry this module:

  unit_cost     what THIS supplier charges. The same product often has two
                prices, and the bundler picks between them
  pack_size     you buy milk in cases of 12, not units of 7. Ignoring this is
                how a system proposes an order a supplier cannot fill
  is_preferred  the shop's own answer to "who do we normally use", and the
                first tiebreak when two suppliers stock the same thing
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from core.actor import Actor
from core.exceptions import DuplicateError, NotFoundError, ValidationError
from core.models import Product, SupplierProduct
from services.guards import require_permission
from services.purchasing import _repository as repo

_UNSET: Any = object()


def list_supplier_products(
    session: Session, actor: Actor, *, supplier_id: int
) -> list[SupplierProduct]:
    require_permission(actor, "purchasing.read")
    if repo.get_supplier(session, supplier_id) is None:
        raise NotFoundError(f"Supplier {supplier_id} does not exist.")
    return repo.links_for_supplier(session, supplier_id)


def link_product(
    session: Session,
    actor: Actor,
    *,
    supplier_id: int,
    product_id: int,
    unit_cost: Decimal,
    pack_size: int = 1,
    is_preferred: bool = False,
) -> SupplierProduct:
    """Record that this supplier sells this product at this price.

    The duplicate is checked here as well as by the unique constraint on the
    table. The constraint is the backstop that guarantees correctness; this
    check is what produces a sentence a person can act on instead of a driver
    error naming an index.
    """
    require_permission(actor, "purchasing.write")

    if unit_cost < 0:
        raise ValidationError("Unit cost cannot be negative.")
    if pack_size < 1:
        raise ValidationError("Pack size must be at least 1.")

    if repo.get_supplier(session, supplier_id) is None:
        raise NotFoundError(f"Supplier {supplier_id} does not exist.")
    if session.get(Product, product_id) is None:
        raise NotFoundError(f"Product {product_id} does not exist.")

    if repo.find_link(session, supplier_id=supplier_id, product_id=product_id):
        raise DuplicateError(
            f"Supplier {supplier_id} already stocks product {product_id}."
        )

    link = SupplierProduct(
        supplier_id=supplier_id,
        product_id=product_id,
        unit_cost=unit_cost,
        pack_size=pack_size,
        is_preferred=is_preferred,
        created_by=actor.id,
    )
    session.add(link)
    session.commit()
    session.refresh(link)
    return link


def update_link(
    session: Session,
    actor: Actor,
    *,
    link_id: int,
    unit_cost: Decimal = _UNSET,
    pack_size: int = _UNSET,
    is_preferred: bool = _UNSET,
) -> SupplierProduct:
    """Change a price, a pack size, or which supplier is preferred.

    Same `_UNSET` sentinel as `suppliers.update_supplier`, for the same reason.
    """
    require_permission(actor, "purchasing.write")

    link = repo.get_link(session, link_id)
    if link is None:
        raise NotFoundError(f"Supplier product link {link_id} does not exist.")

    if unit_cost is not _UNSET:
        if unit_cost < 0:
            raise ValidationError("Unit cost cannot be negative.")
        link.unit_cost = unit_cost

    if pack_size is not _UNSET:
        if pack_size < 1:
            raise ValidationError("Pack size must be at least 1.")
        link.pack_size = pack_size

    if is_preferred is not _UNSET:
        link.is_preferred = is_preferred

    link.updated_by = actor.id
    session.commit()
    session.refresh(link)
    return link
