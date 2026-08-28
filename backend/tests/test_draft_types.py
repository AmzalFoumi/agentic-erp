"""The registry is the reason a draft row cannot become arbitrary code.

Read docs/FEATURES-PLAN.md, the table row about "target service function names
and arguments". The externally-written spec had the payload carry a function
name; resolving a function from a string held in a database row means anyone
who can write a row can call anything with anything. These tests pin the
replacement shut.

None of these need a database. The registry is in-memory, which is why this
file has no `session` fixture anywhere.
"""

import pytest
from pydantic import BaseModel

from core.exceptions import ValidationError
from services import draft_types


class _NoopPayload(BaseModel):
    """A payload shape for a type that exists only in this test file."""

    product_id: int
    note: str = ""


def _noop_handler(session, actor, client, payload):
    """A handler that does nothing, for testing the machinery around it."""
    return None


@pytest.fixture(autouse=True)
def _registered_test_type():
    """Register a test type, and remove it again afterwards.

    `autouse=True` applies it to every test in this file without each one
    naming it. The teardown is not optional: the registry is module-level
    state, so a type left behind leaks into every later test in the run - the
    same reasoning as `app.dependency_overrides.clear()` in conftest.py's
    client fixture.

    It reaches into `_REGISTRY` directly, which is private. That is deliberate
    and confined to tests: there is no public `unregister()`, because outside a
    test there is no legitimate reason to remove a draft type at runtime, and
    offering one would be offering a way to disable a handler in production.
    """
    draft_types.register("TEST_NOOP", schema=_NoopPayload, handler=_noop_handler)
    yield
    draft_types._REGISTRY.pop("TEST_NOOP", None)


def test_unknown_draft_type_is_refused():
    """The property this whole gate exists for."""
    with pytest.raises(ValidationError) as exc:
        draft_types.spec_for("DROP_EVERYTHING")

    assert "DROP_EVERYTHING" in str(exc.value)


def test_the_refusal_does_not_enumerate_the_valid_types():
    """An error that lists what IS allowed is a map for whoever is probing.

    Same reasoning as gate 24's authentication failures, which refuse to say
    why they failed so that nobody can use the API to survey our setup.
    """
    with pytest.raises(ValidationError) as exc:
        draft_types.spec_for("DROP_EVERYTHING")

    assert "TEST_NOOP" not in str(exc.value)


def test_a_registered_type_resolves_to_its_schema_and_handler():
    spec = draft_types.spec_for("TEST_NOOP")

    assert spec.schema is _NoopPayload
    assert spec.handler is _noop_handler


def test_a_spec_cannot_be_mutated_through_the_reference_it_hands_out():
    """frozen=True, asserted rather than assumed."""
    spec = draft_types.spec_for("TEST_NOOP")

    with pytest.raises(Exception):
        spec.handler = lambda *args: None  # type: ignore[misc]


def test_payload_is_validated_against_the_type_schema():
    validated = draft_types.validate_payload("TEST_NOOP", {"product_id": 42})

    assert isinstance(validated, _NoopPayload)
    assert validated.product_id == 42
    assert validated.note == ""


def test_a_payload_of_the_wrong_shape_is_refused():
    with pytest.raises(ValidationError):
        draft_types.validate_payload("TEST_NOOP", {"product_id": "not a number"})


def test_a_payload_for_an_unknown_type_is_refused():
    """Validation must not pass merely because the dict looks plausible.

    Without this, a payload shaped like a known type would sail through for a
    type name nobody registered - and the refusal would move to the handler
    lookup, which is one layer too late to be reassuring.
    """
    with pytest.raises(ValidationError):
        draft_types.validate_payload("DROP_EVERYTHING", {"product_id": 42})


def test_the_validation_error_does_not_echo_the_rejected_value_back():
    """The message says how many problems, not what was sent.

    Pydantic's own detail names field paths and the values it received, and
    this string travels to an API client. A count is enough for a human to know
    the shape is wrong.
    """
    with pytest.raises(ValidationError) as exc:
        draft_types.validate_payload(
            "TEST_NOOP", {"product_id": "sqlinjection-lookalike"}
        )

    assert "sqlinjection-lookalike" not in str(exc.value)


def test_registering_the_same_type_twice_is_refused():
    """A silent overwrite would let import order decide which handler runs."""
    with pytest.raises(ValidationError):
        draft_types.register(
            "TEST_NOOP", schema=_NoopPayload, handler=_noop_handler
        )


def test_gate_27_ships_with_no_real_draft_types_registered():
    """The engine ships empty; gate 28 registers the first real type.

    If this test starts failing, a feature registered a type - update it to
    name that type deliberately, rather than deleting it. It is the thing that
    would notice a draft type appearing by accident through some import.

    Gate 28 registered BATCH_PRICE_MARKDOWN (services/spoilage.py, imported by
    services/__init__.py). Gate 29 added SUPPLIER_REORDER the same way
    (services/purchasing/drafts.py). Gate 30 added DELIVERY_RECEIPT
    (services/purchasing/drafts.py). TEST_NOOP is this file's own fixture and
    exists nowhere in production code.
    """
    assert draft_types.registered_types() == frozenset(
        {
            "TEST_NOOP",
            "BATCH_PRICE_MARKDOWN",
            "SUPPLIER_REORDER",
            "DELIVERY_RECEIPT",
        }
    )
