"""Supplier use cases: permissions, validation, and the no-delete rule."""

from decimal import Decimal

import pytest

from core.enums import ClientType
from core.exceptions import DuplicateError, NotFoundError, PermissionDeniedError
from services.purchasing import suppliers


class _Actor:
    """An actor holding exactly the permissions named.

    Built here rather than imported so a test can express "holds read but not
    write" in one line. `SystemActor` grants everything, which is the wrong
    tool for testing a refusal.
    """

    def __init__(self, *permissions: str) -> None:
        self.id = "test-user"
        self._permissions = frozenset(permissions)

    def can(self, permission: str) -> bool:
        return permission in self._permissions


READER = _Actor("purchasing.read")
WRITER = _Actor("purchasing.read", "purchasing.write")
NOBODY = _Actor()


def test_creating_a_supplier_needs_write(session):
    with pytest.raises(PermissionDeniedError):
        suppliers.create_supplier(
            session, READER, client=ClientType.WEB_UI, name="DairyCo"
        )


def test_listing_suppliers_needs_read(session):
    with pytest.raises(PermissionDeniedError):
        suppliers.list_suppliers(session, NOBODY)


def test_a_created_supplier_comes_back(session):
    created = suppliers.create_supplier(
        session,
        WRITER,
        client=ClientType.WEB_UI,
        name="DairyCo",
        lead_time_days=3,
        minimum_order_value=Decimal("300.00"),
    )
    assert created.id is not None
    assert created.lead_time_days == 3
    assert created.minimum_order_value == Decimal("300.00")
    assert created.is_active is True
    assert created.created_by == "test-user"


def test_two_suppliers_cannot_share_a_name(session):
    suppliers.create_supplier(session, WRITER, client=ClientType.WEB_UI, name="DairyCo")
    with pytest.raises(DuplicateError):
        suppliers.create_supplier(
            session, WRITER, client=ClientType.WEB_UI, name="DairyCo"
        )


def test_a_blank_name_is_refused(session):
    from core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        suppliers.create_supplier(session, WRITER, client=ClientType.WEB_UI, name="   ")


def test_a_negative_lead_time_is_refused(session):
    from core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        suppliers.create_supplier(
            session, WRITER, client=ClientType.WEB_UI, name="X", lead_time_days=-1
        )


def test_a_negative_minimum_is_refused(session):
    from core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        suppliers.create_supplier(
            session,
            WRITER,
            client=ClientType.WEB_UI,
            name="X",
            minimum_order_value=Decimal("-1.00"),
        )


def test_an_unknown_supplier_raises_rather_than_returning_none(session):
    with pytest.raises(NotFoundError):
        suppliers.get_supplier(session, READER, supplier_id=999999)


def test_deactivating_is_how_a_supplier_leaves(session):
    """There is no delete anywhere in this API. This is the replacement."""
    created = suppliers.create_supplier(
        session, WRITER, client=ClientType.WEB_UI, name="Gone Ltd"
    )
    updated = suppliers.update_supplier(
        session, WRITER, supplier_id=created.id, is_active=False
    )
    assert updated.is_active is False
    assert updated.updated_by == "test-user"

    active = suppliers.list_suppliers(session, READER, active_only=True)
    assert created.id not in [s.id for s in active]

    everyone = suppliers.list_suppliers(session, READER)
    assert created.id in [s.id for s in everyone]


def test_update_leaves_unmentioned_fields_alone(session):
    """A partial update must not blank the fields it was not given.

    The obvious implementation - assign every keyword onto the row - sets
    contact_email to None when the caller only wanted to change the lead time.
    """
    created = suppliers.create_supplier(
        session,
        WRITER,
        client=ClientType.WEB_UI,
        name="Keep Me",
        contact_email="a@b.com",
        lead_time_days=5,
    )
    updated = suppliers.update_supplier(
        session, WRITER, supplier_id=created.id, lead_time_days=7
    )
    assert updated.lead_time_days == 7
    assert updated.contact_email == "a@b.com"


def test_updating_needs_write(session):
    created = suppliers.create_supplier(
        session, WRITER, client=ClientType.WEB_UI, name="Needs Write"
    )
    with pytest.raises(PermissionDeniedError):
        suppliers.update_supplier(
            session, READER, supplier_id=created.id, lead_time_days=1
        )


def test_renaming_to_your_own_current_name_is_not_a_duplicate(session):
    """The duplicate check must exclude the row being updated, or every
    no-op rename (or an update that leaves the name untouched but re-sends
    it) would incorrectly raise DuplicateError against itself."""
    created = suppliers.create_supplier(
        session, WRITER, client=ClientType.WEB_UI, name="Self Ref Co"
    )
    updated = suppliers.update_supplier(
        session, WRITER, supplier_id=created.id, name="Self Ref Co"
    )
    assert updated.name == "Self Ref Co"


# --- the supplier catalogue ------------------------------------------------


def _a_product(session, unique_sku):
    """A product to hang supplier links off.

    Created through the service so it gets an OPENING lot like every other
    product - gate 28 made create_product do that, and a product with stock no
    lot backs is exactly the bug that change fixed.
    """
    from services import products

    return products.create_product(
        session,
        WRITER_WITH_PRODUCTS,
        sku=unique_sku,
        name="Test Milk",
        unit="litre",
        cost_price=Decimal("1.00"),
        sell_price=Decimal("2.00"),
        quantity_on_hand=0,
        reorder_level=10,
    )


WRITER_WITH_PRODUCTS = _Actor(
    "purchasing.read", "purchasing.write", "product.create", "product.read"
)


def test_linking_a_product_records_this_suppliers_price(session, unique_sku):
    from services.purchasing import catalog

    supplier = suppliers.create_supplier(
        session, WRITER, client=ClientType.WEB_UI, name="DairyCo"
    )
    product = _a_product(session, unique_sku)

    link = catalog.link_product(
        session,
        WRITER,
        supplier_id=supplier.id,
        product_id=product.id,
        unit_cost=Decimal("1.20"),
        pack_size=12,
    )
    assert link.unit_cost == Decimal("1.20")
    assert link.pack_size == 12
    assert link.is_preferred is False


def test_the_same_product_cannot_be_linked_twice_to_one_supplier(session, unique_sku):
    from services.purchasing import catalog

    supplier = suppliers.create_supplier(
        session, WRITER, client=ClientType.WEB_UI, name="DairyCo"
    )
    product = _a_product(session, unique_sku)
    catalog.link_product(
        session,
        WRITER,
        supplier_id=supplier.id,
        product_id=product.id,
        unit_cost=Decimal("1.20"),
    )
    with pytest.raises(DuplicateError):
        catalog.link_product(
            session,
            WRITER,
            supplier_id=supplier.id,
            product_id=product.id,
            unit_cost=Decimal("1.30"),
        )


def test_a_pack_size_below_one_is_refused(session, unique_sku):
    from core.exceptions import ValidationError
    from services.purchasing import catalog

    supplier = suppliers.create_supplier(
        session, WRITER, client=ClientType.WEB_UI, name="DairyCo"
    )
    product = _a_product(session, unique_sku)
    with pytest.raises(ValidationError):
        catalog.link_product(
            session,
            WRITER,
            supplier_id=supplier.id,
            product_id=product.id,
            unit_cost=Decimal("1.20"),
            pack_size=0,
        )


def test_linking_to_a_product_that_does_not_exist_raises(session):
    from services.purchasing import catalog

    supplier = suppliers.create_supplier(
        session, WRITER, client=ClientType.WEB_UI, name="DairyCo"
    )
    with pytest.raises(NotFoundError):
        catalog.link_product(
            session,
            WRITER,
            supplier_id=supplier.id,
            product_id=999999,
            unit_cost=Decimal("1.20"),
        )


def test_linking_a_product_needs_write(session, unique_sku):
    supplier = suppliers.create_supplier(
        session, WRITER, client=ClientType.WEB_UI, name="ReadOnlyTest"
    )
    product = _a_product(session, unique_sku)
    from services.purchasing import catalog

    with pytest.raises(PermissionDeniedError):
        catalog.link_product(
            session,
            READER,
            supplier_id=supplier.id,
            product_id=product.id,
            unit_cost=Decimal("1.20"),
        )


def test_updating_a_link_leaves_unmentioned_fields_alone(session, unique_sku):
    from services.purchasing import catalog

    supplier = suppliers.create_supplier(
        session, WRITER, client=ClientType.WEB_UI, name="UpdateLinkCo"
    )
    product = _a_product(session, unique_sku)
    link = catalog.link_product(
        session,
        WRITER,
        supplier_id=supplier.id,
        product_id=product.id,
        unit_cost=Decimal("1.20"),
        pack_size=6,
    )
    updated = catalog.update_link(
        session, WRITER, link_id=link.id, is_preferred=True
    )
    assert updated.is_preferred is True
    assert updated.unit_cost == Decimal("1.20")
    assert updated.pack_size == 6
