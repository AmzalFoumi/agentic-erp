"""Tests for services/products.py - the business rules, with no HTTP involved.

That last part is the point being proven. These tests import a plain Python
function and call it. No test client, no app, no routes, no MCP session. If
these pass, the logic is correct independently of how it is reached - which is
exactly the claim the two-adapter architecture rests on.

pytest conventions in use, since they differ from Jest:

  - a test is a module-level function named `test_*`, not a callback inside a
    `describe`. No wrapper, no registration.
  - assertions are the bare `assert` keyword. pytest rewrites the bytecode so a
    failure prints the actual operand values, which is why there is no
    `expect(...).toBe(...)` vocabulary to learn.
  - a parameter name that matches a fixture in conftest.py gets that fixture
    injected. `def test_x(session, actor)` is a request for both.
  - `pytest.raises` asserts that a block raises. It is the equivalent of
    `expect(fn).toThrow(Error)`, and it fails if nothing is raised at all.
"""

from decimal import Decimal

import pytest

from core.exceptions import DuplicateError, NotFoundError, ValidationError
from services import products


def test_create_and_read_back(session, actor, unique_sku):
    """The happy path, and the audit stamp that comes with it."""
    created = products.create_product(
        session,
        actor,
        sku=unique_sku,
        name="Basmati Rice 1kg",
        category="Grains",
        cost_price=Decimal("12.50"),
        sell_price=Decimal("18.00"),
        quantity_on_hand=40,
        reorder_level=10,
    )

    # The database assigned these, not us - proof the row really was written
    # and refreshed, rather than the object merely existing in memory.
    assert created.id is not None
    assert created.created_at is not None

    # Set from actor.id by the service. The whole reason Actor is a parameter.
    assert created.created_by == "pytest"

    fetched = products.get_product(session, actor, product_id=created.id)
    assert fetched.sku == unique_sku
    assert fetched.sell_price == Decimal("18.00")


def test_sku_is_normalised(session, actor, unique_sku):
    """Whitespace and case are stripped, so shelf labels and rows agree."""
    created = products.create_product(
        session, actor, sku=f"  {unique_sku.lower()}  ", name="Lentils"
    )
    assert created.sku == unique_sku

    # And lookup normalises the same way, or the round trip would not close.
    found = products.get_product_by_sku(session, actor, sku=unique_sku.lower())
    assert found.id == created.id


def test_duplicate_sku_is_rejected(session, actor, unique_sku):
    """The rule: one SKU, one product.

    Note the second attempt differs in case, which also proves the duplicate
    check runs on the *normalised* value. Checking the raw input would let
    `rice-1` and `RICE-1` both through, and then the UNIQUE index would reject
    the insert with an IntegrityError instead - the right outcome by accident,
    with the wrong error type.
    """
    products.create_product(session, actor, sku=unique_sku, name="Sugar 1kg")

    with pytest.raises(DuplicateError):
        products.create_product(
            session, actor, sku=unique_sku.lower(), name="Sugar 1kg (duplicate)"
        )


def test_missing_product_raises_not_found(session, actor):
    """Absence is an exception, not a None the caller can forget to check."""
    with pytest.raises(NotFoundError):
        products.get_product(session, actor, product_id=-1)


def test_adjust_stock_moves_the_quantity(session, actor, unique_sku):
    """Both directions, and the total is the running one, not the delta."""
    product = products.create_product(
        session, actor, sku=unique_sku, name="Olive Oil 1L", quantity_on_hand=10
    )

    products.adjust_stock(session, actor, product_id=product.id, delta=5)
    updated = products.adjust_stock(
        session, actor, product_id=product.id, delta=-3, reason="damaged"
    )

    assert updated.quantity_on_hand == 12


def test_adjust_stock_refuses_to_go_negative(session, actor, unique_sku):
    """The headline rule of this service, and the stronger half of the test.

    Asserting the error is raised is not enough. A service that raised *after*
    already writing the new quantity would pass a `pytest.raises` check and
    still be badly broken, so the second half re-reads the row and asserts the
    stock is untouched.
    """
    product = products.create_product(
        session, actor, sku=unique_sku, name="Tea 250g", quantity_on_hand=2
    )

    with pytest.raises(ValidationError):
        products.adjust_stock(session, actor, product_id=product.id, delta=-5)

    unchanged = products.get_product(session, actor, product_id=product.id)
    assert unchanged.quantity_on_hand == 2


def test_update_changes_only_what_is_given(session, actor, unique_sku):
    """Omitted parameters mean "leave alone", not "set to null"."""
    product = products.create_product(
        session,
        actor,
        sku=unique_sku,
        name="Chickpeas 400g",
        category="Tinned",
        sell_price=Decimal("4.00"),
    )

    updated = products.update_product(
        session, actor, product_id=product.id, sell_price=Decimal("4.50")
    )

    assert updated.sell_price == Decimal("4.50")
    assert updated.name == "Chickpeas 400g"
    assert updated.category == "Tinned"


def test_negative_price_is_rejected(session, actor, unique_sku):
    """Structurally a valid Decimal; still not a thing that can exist."""
    with pytest.raises(ValidationError):
        products.create_product(
            session, actor, sku=unique_sku, name="Bad", sell_price=Decimal("-1.00")
        )


def test_search_matches_name_and_sku(session, actor, unique_sku):
    """The filter is case-insensitive and covers both columns."""
    products.create_product(session, actor, sku=unique_sku, name="Cardamom Pods")

    by_name = products.list_products(session, actor, search="cardamom")
    assert any(p.sku == unique_sku for p in by_name)

    by_sku = products.list_products(session, actor, search=unique_sku[5:])
    assert any(p.sku == unique_sku for p in by_sku)
