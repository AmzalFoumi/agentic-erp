"""The MCP adapter's draft tools.

Thin, for the same reason test_mcp_products.py is thin: the business rules are
proven in test_drafts.py against the service. What is left is what this adapter
alone is responsible for - that a proposal made over MCP is recorded as coming
from the agent, that money survives the round trip as a decimal string, and
that a domain exception becomes a message written for a model rather than a
stack trace.

The tool *inventory* - which tools exist, and which deliberately do not - is
asserted in test_mcp_products.py, where the whole registry is checked at once.
"""

from contextlib import contextmanager
from decimal import Decimal

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.enums import ClientType, DraftStatus
from mcp_server import server as mcp_server
from services import draft_types


class _MarkPayload(BaseModel):
    product_id: int


@pytest.fixture
def registered_type():
    """A draft type that exists only for these tests.

    Gate 27 registers none of its own - the engine ships empty and gate 28
    registers the first real one - so a test that needs a valid type has to
    supply it. Removed afterwards because the registry is module-level state
    and a leftover would follow the rest of the run around.
    """
    calls: list[int] = []

    draft_types.register(
        "TEST_MARK",
        schema=_MarkPayload,
        handler=lambda session, actor, client, payload: calls.append(
            payload.product_id
        ),
    )
    yield calls
    draft_types._REGISTRY.pop("TEST_MARK", None)


@pytest.fixture
def call(session: Session, monkeypatch: pytest.MonkeyPatch):
    """Call an MCP tool by name, against this test's rolled-back session.

    Copied from test_mcp_products.py rather than shared through conftest.py,
    which is a deliberate call and worth stating: the fixture encodes two
    assumptions - that `get_session` is patched on the server module and that
    `auth_enabled` is off - and moving it into conftest would apply those to
    every future test file by default, including ones that should be exercising
    the real authentication path. tests/test_mcp_auth.py is exactly such a file.

    The target is `mcp_server.server.get_session`, not
    `core.database.get_session`: server.py did `from core.database import
    get_session`, which copied the reference into its own namespace at import
    time, so patching the original would have no effect.
    """

    @contextmanager
    def fake_get_session():
        yield session

    monkeypatch.setattr(mcp_server, "get_session", fake_get_session)
    monkeypatch.setattr(mcp_server.settings, "auth_enabled", False)

    def invoke(_tool: str, /, **arguments):
        return anyio.run(lambda: mcp_server.mcp.call_tool(_tool, arguments))

    return invoke


def _payload(result):
    """Unwrap a call_tool result into the dict the tool returned."""
    return result.structured_content


def test_a_proposal_made_over_mcp_is_recorded_as_coming_from_the_agent(
    call, registered_type
):
    """The provenance column the whole ClientType parameter exists for."""
    draft = _payload(
        call(
            "create_action_draft",
            draft_type="TEST_MARK",
            payload={"product_id": 3},
            reasoning="milk expires tomorrow",
        )
    )

    assert draft["status"] == DraftStatus.PENDING
    assert draft["created_via"] == ClientType.MCP_AGENT
    assert draft["decided_by"] is None


def test_creating_a_draft_runs_no_handler(call, registered_type):
    """A proposal changes nothing. That is why the agent may make one freely."""
    call(
        "create_action_draft",
        draft_type="TEST_MARK",
        payload={"product_id": 3},
        reasoning="milk expires tomorrow",
    )

    assert registered_type == []


def test_an_unknown_draft_type_is_refused_with_a_readable_message(
    call, registered_type
):
    """The security property, reached through tool dispatch.

    `ToolError` is how mcp_server/errors.translated surfaces a domain failure -
    text a model can read and act on, never a JSON-RPC error code, which is
    reserved for protocol failures.
    """
    with pytest.raises(ToolError) as exc:
        call(
            "create_action_draft",
            draft_type="DROP_EVERYTHING",
            payload={"product_id": 3},
            reasoning="trust me",
        )

    assert "DROP_EVERYTHING" in str(exc.value)


def test_the_refusal_does_not_tell_the_model_which_types_exist(
    call, registered_type
):
    """An error listing the valid set is a map for whoever is probing."""
    with pytest.raises(ToolError) as exc:
        call(
            "create_action_draft",
            draft_type="DROP_EVERYTHING",
            payload={"product_id": 3},
            reasoning="trust me",
        )

    assert "TEST_MARK" not in str(exc.value)


def test_a_payload_of_the_wrong_shape_is_refused(call, registered_type):
    with pytest.raises(ToolError):
        call(
            "create_action_draft",
            draft_type="TEST_MARK",
            payload={"product_id": "not a number"},
            reasoning="oops",
        )


def test_money_crosses_the_protocol_as_a_decimal_string(call, registered_type):
    """Inbound and outbound both. A float64 would already be wrong on arrival."""
    draft = _payload(
        call(
            "create_action_draft",
            draft_type="TEST_MARK",
            payload={"product_id": 3},
            reasoning="milk expires tomorrow",
            cost_at_risk="40000.50",
            projected_recovery="12000.25",
        )
    )

    assert draft["cost_at_risk"] == "40000.50"
    assert draft["projected_recovery"] == "12000.25"


def test_money_written_as_prose_is_refused_rather_than_guessed(
    call, registered_type
):
    """A model writing "about 40000" is not hypothetical.

    Without _price's InvalidOperation catch this surfaces as a raw decimal
    library error naming no argument.
    """
    with pytest.raises(ToolError) as exc:
        call(
            "create_action_draft",
            draft_type="TEST_MARK",
            payload={"product_id": 3},
            reasoning="milk expires tomorrow",
            cost_at_risk="about 40000",
        )

    assert "cost_at_risk" in str(exc.value)


def test_omitted_money_stays_null_rather_than_becoming_zero(call, registered_type):
    """"No financial dimension" and "nothing at stake" are different facts."""
    draft = _payload(
        call(
            "create_action_draft",
            draft_type="TEST_MARK",
            payload={"product_id": 3},
            reasoning="milk expires tomorrow",
        )
    )

    assert draft["cost_at_risk"] is None
    assert draft["projected_recovery"] is None


def test_list_pending_drafts_returns_what_was_just_proposed(call, registered_type):
    created = _payload(
        call(
            "create_action_draft",
            draft_type="TEST_MARK",
            payload={"product_id": 3},
            reasoning="milk expires tomorrow",
        )
    )

    listed = call("list_pending_drafts", limit=50).structured_content

    assert any(d["id"] == created["id"] for d in listed["result"])
