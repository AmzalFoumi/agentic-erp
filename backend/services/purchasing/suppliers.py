"""Suppliers: who we buy from.

There is no delete. `is_active = False` is how a supplier leaves, which keeps
order history pointing at a name rather than an orphaned id - and matches the
rest of this API, which deletes nothing anywhere.

`_UNSET` below is the reason partial updates work. See `update_supplier`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from core.actor import Actor
from core.enums import ClientType
from core.exceptions import DuplicateError, NotFoundError, ValidationError
from core.models import Supplier
from services.guards import require_permission
from services.purchasing import _repository as repo

# A sentinel meaning "the caller did not mention this field".
#
# None cannot do this job: None is a legitimate value for contact_email, so a
# function that treats it as "not given" can never clear an email address, and
# one that treats it as "given" blanks the address on every unrelated update.
# A private object is unambiguous because no caller can produce one by accident.
_UNSET: Any = object()


def _get_or_raise(session: Session, supplier_id: int) -> Supplier:
    supplier = repo.get_supplier(session, supplier_id)
    if supplier is None:
        raise NotFoundError(f"Supplier {supplier_id} does not exist.")
    return supplier


def _clean_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValidationError("A supplier must have a name.")
    return name


def list_suppliers(
    session: Session, actor: Actor, *, active_only: bool = False
) -> list[Supplier]:
    """Every supplier, by name. `active_only` hides the ones we have left."""
    require_permission(actor, "purchasing.read")
    return repo.list_suppliers(session, active_only=active_only)


def get_supplier(session: Session, actor: Actor, *, supplier_id: int) -> Supplier:
    require_permission(actor, "purchasing.read")
    return _get_or_raise(session, supplier_id)


def create_supplier(
    session: Session,
    actor: Actor,
    *,
    client: ClientType,
    name: str,
    contact_email: str | None = None,
    contact_phone: str | None = None,
    lead_time_days: int = 0,
    minimum_order_value: Decimal = Decimal("0.00"),
) -> Supplier:
    """Add a supplier.

    `minimum_order_value` defaults to zero, which means "no minimum" - a
    supplier who will ship any size of order. That is a real arrangement, and
    the bundler treats such a supplier as always satisfied.
    """
    require_permission(actor, "purchasing.write")

    name = _clean_name(name)
    if lead_time_days < 0:
        raise ValidationError("Lead time cannot be negative.")
    if minimum_order_value < 0:
        raise ValidationError("Minimum order value cannot be negative.")

    if repo.get_supplier_by_name(session, name) is not None:
        raise DuplicateError(f"A supplier named {name!r} already exists.")

    supplier = Supplier(
        name=name,
        contact_email=contact_email,
        contact_phone=contact_phone,
        lead_time_days=lead_time_days,
        minimum_order_value=minimum_order_value,
        created_by=actor.id,
    )
    session.add(supplier)
    session.commit()
    session.refresh(supplier)
    return supplier


def update_supplier(
    session: Session,
    actor: Actor,
    *,
    supplier_id: int,
    name: str = _UNSET,
    contact_email: str | None = _UNSET,
    contact_phone: str | None = _UNSET,
    lead_time_days: int = _UNSET,
    minimum_order_value: Decimal = _UNSET,
    is_active: bool = _UNSET,
) -> Supplier:
    """Change some fields on a supplier, leaving the rest alone.

    Every parameter defaults to `_UNSET` rather than None, so "clear the email
    address" and "do not touch the email address" are different calls. The
    obvious alternative - assigning every keyword onto the row - blanks
    contact_email whenever someone edits only the lead time.
    """
    require_permission(actor, "purchasing.write")
    supplier = _get_or_raise(session, supplier_id)

    if name is not _UNSET:
        cleaned = _clean_name(name)
        existing = repo.get_supplier_by_name(session, cleaned)
        if existing is not None and existing.id != supplier.id:
            raise DuplicateError(f"A supplier named {cleaned!r} already exists.")
        supplier.name = cleaned

    if contact_email is not _UNSET:
        supplier.contact_email = contact_email
    if contact_phone is not _UNSET:
        supplier.contact_phone = contact_phone

    if lead_time_days is not _UNSET:
        if lead_time_days < 0:
            raise ValidationError("Lead time cannot be negative.")
        supplier.lead_time_days = lead_time_days

    if minimum_order_value is not _UNSET:
        if minimum_order_value < 0:
            raise ValidationError("Minimum order value cannot be negative.")
        supplier.minimum_order_value = minimum_order_value

    if is_active is not _UNSET:
        supplier.is_active = is_active

    supplier.updated_by = actor.id
    session.commit()
    session.refresh(supplier)
    return supplier
