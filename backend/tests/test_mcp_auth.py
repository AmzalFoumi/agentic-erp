"""Tests for gate 25: the MCP server checking tokens for itself.

Same discipline as tests/test_auth.py, and for the same reason - nothing here
touches a running ThunderID. A key pair generated in-process proves the
signature check just as well as a real one, and it additionally lets us mint the
tokens that are *supposed* to fail, which a real issuer would never hand out.

The token shapes below are not invented. Each mirrors something observed against
the live server on 2026-08-25 and recorded in docs/AUTH-PLAN.md, "Identity
-provider side, completed 2026-08-25" - in particular the scope-less token, which
is the one that looks like a success from every angle except this one.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from core.config import settings


@pytest.fixture
def signing_key() -> rsa.RSAPrivateKey:
    """A throwaway RSA key pair standing in for ThunderID's signing key."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def verifier(monkeypatch, signing_key):
    """A ThunderIDTokenVerifier whose key lookup returns our public key.

    Patched at `authn.tokens._jwk_client`, the same seam tests/test_auth.py
    uses, rather than anywhere in mcp_server/ - so everything this gate added
    (the audience choice, the AccessToken translation, the empty-scope warning)
    runs exactly as it does in production. Only key *distribution* is skipped.
    """
    from authn import tokens
    from mcp_server.auth import ThunderIDTokenVerifier

    class _StubKey:
        key = signing_key.public_key()

    class _StubClient:
        def get_signing_key_from_jwt(self, token: str) -> _StubKey:
            return _StubKey()

    monkeypatch.setattr(tokens, "_jwk_client", lambda: _StubClient())
    return ThunderIDTokenVerifier()


def _token(signing_key: rsa.RSAPrivateKey, **overrides: Any) -> str:
    """A token shaped like one ThunderID mints for the MCP resource server.

    Note the audience: `thunderid_mcp_audience`, not `thunderid_audience`. Two
    resource servers exist precisely so these differ.
    """
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": "01a02d8f-0355-74cd-b102-3b1ab2372d64",
        "aud": settings.thunderid_mcp_audience,
        "iss": settings.thunderid_issuer,
        "iat": now,
        "nbf": now,
        "exp": now + 3600,
        "scope": "product.read stock.adjust",
        "client_id": "6in2mfBltFEEMpYjF5upZA",
    }
    claims.update(overrides)
    return jwt.encode(claims, signing_key, algorithm="RS256")


# ---------------------------------------------------------------------------
# The verifier
# ---------------------------------------------------------------------------


def _verify(verifier, token: str):
    """Drive `verify_token` from a synchronous test.

    The SDK's `TokenVerifier` protocol is async, so ours is too - but nothing in
    it actually awaits: `authn/tokens.py` checks a signature against a cached
    key set. Rather than take a pytest async plugin as a new dependency for a
    coroutine that never yields, the three lines of `asyncio.run` go here, once.
    """
    return asyncio.run(verifier.verify_token(token))



def test_a_valid_mcp_token_is_accepted(verifier, signing_key):
    token = _verify(verifier, _token(signing_key))

    assert token is not None
    assert token.subject == "01a02d8f-0355-74cd-b102-3b1ab2372d64"
    assert token.scopes == ["product.read", "stock.adjust"]
    # Sorted, so this assertion does not depend on frozenset iteration order.
    assert token.resource == settings.thunderid_mcp_audience


def test_a_token_for_the_http_api_is_refused_by_the_mcp_server(
    verifier, signing_key
):
    """The reason two resource servers exist, in one test.

    Genuine user, genuine signature, genuine issuer, correct scopes - minted for
    `Agentic ERP API` rather than `Agentic ERP MCP`. Accepting it would mean a
    token for one front door opens the other, which throws away the destination
    half of delegation: an agent narrowed to the MCP server would still hold a
    key to the whole building. The MCP authorization spec makes checking this a
    MUST.
    """
    api_token = _token(signing_key, aud=settings.thunderid_audience)

    assert _verify(verifier, api_token) is None


def test_a_token_with_no_scope_claim_authenticates_but_grants_nothing(
    verifier, signing_key, caplog
):
    """⚠️ The regression test this gate was told to write.

    Verified against the live server on 2026-08-25: asking token exchange for a
    permission that does not exist returns **HTTP 200 with a structurally valid,
    correctly-audienced token carrying no `scope` claim at all**. Nothing in the
    HTTP response distinguishes it from a success, so a status code proves
    nothing and every auth check must read the scope that came back.

    The token must therefore *authenticate* - it is genuinely signed, and the
    subject is genuinely that user - while granting **zero** permissions. The
    dangerous reading is "scope unspecified, therefore unrestricted", which is
    how a helpful refactor turns this into a total bypass.
    """
    import logging

    from mcp_server import auth as mcp_auth

    scopeless = jwt.encode(
        {
            "sub": "01a02d8f-0355-74cd-b102-3b1ab2372d64",
            "aud": settings.thunderid_mcp_audience,
            "iss": settings.thunderid_issuer,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        },
        signing_key,
        algorithm="RS256",
    )

    with caplog.at_level(logging.WARNING, logger=mcp_auth.__name__):
        token = _verify(verifier, scopeless)

    assert token is not None, "a scope-less token is genuine; it must authenticate"
    assert token.scopes == [], "a missing scope claim must grant nothing at all"

    # The one place the situation is legible. Without it the symptom - every
    # tool call refused - looks nothing like its cause.
    assert any("no scopes" in r.getMessage() for r in caplog.records)


def test_an_expired_token_is_refused(verifier, signing_key):
    now = int(time.time())
    expired = _token(signing_key, iat=now - 7200, nbf=now - 7200, exp=now - 3600)

    assert _verify(verifier, expired) is None


def test_a_token_signed_by_a_stranger_is_refused(verifier):
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    assert _verify(verifier, _token(other_key)) is None


def test_a_refusal_returns_none_rather_than_raising(verifier):
    """The SDK's protocol, and the reason it matters.

    `TokenVerifier.verify_token` returns `AccessToken | None`. The SDK turns
    `None` into the MCP-flavoured 401 with the `WWW-Authenticate` header the
    specification requires. An exception escaping here would instead surface as
    a 500 and tell an anonymous caller that something inside broke.
    """
    assert _verify(verifier, "not-a-jwt") is None


# ---------------------------------------------------------------------------
# _actor() - the seam itself
# ---------------------------------------------------------------------------


def test_actor_falls_back_to_a_named_system_actor_only_when_auth_is_off(monkeypatch):
    """`AUTH_ENABLED=false` is the test suite's escape hatch, and nothing more.

    The id is "mcp" rather than "system" so an audited row still records which
    front door wrote it - api/deps.py uses "api" for the same reason.
    """
    from core.config import settings as live_settings
    from mcp_server import server

    monkeypatch.setattr(live_settings, "auth_enabled", False)

    actor = server._actor()

    assert actor.id == "mcp"
    assert actor.can("stock.adjust")


def test_actor_refuses_rather_than_inventing_an_identity_when_auth_is_on(monkeypatch):
    """The trap CLAUDE.md carried from gate 6, asserted shut.

    With authentication on and no verified token in context, `_actor()` must
    fail closed. The old behaviour - an all-powerful SystemActor - meant an
    anonymous caller could write, and the row would carry a fabricated
    provenance. That is the single worst failure mode in this codebase, which is
    why it is pinned by a test rather than left to the SDK's own guard.
    """
    from core.config import settings as live_settings
    from core.exceptions import AuthenticationError
    from mcp_server import server

    monkeypatch.setattr(live_settings, "auth_enabled", True)

    with pytest.raises(AuthenticationError):
        server._actor()


# ---------------------------------------------------------------------------
# The gate's exit condition
# ---------------------------------------------------------------------------
#
# Everything above proves the plumbing. These two prove the point of the gate,
# and the second is the one that matters: "the agent may only do what you may
# do" is a claim about what a *narrowed* token cannot do, and the only honest
# way to test that is to check the database afterwards. A reply that reads like
# a refusal is not evidence - a tool could refuse in its text and still have
# written the row.


@pytest.fixture
def call_as(session, monkeypatch, unique_sku):
    """Call an MCP tool as a specific actor, against a rolled-back session.

    Mirrors the `call` fixture in tests/test_mcp_products.py, with the actor
    made a parameter instead of always being the fallback SystemActor - which
    is the whole thing this gate introduced.
    """
    from contextlib import contextmanager

    import anyio

    from mcp_server import server as mcp_server

    @contextmanager
    def fake_get_session():
        yield session

    monkeypatch.setattr(mcp_server, "get_session", fake_get_session)

    def invoke(actor, _tool: str, /, **arguments):
        monkeypatch.setattr(mcp_server, "_actor", lambda: actor)
        return anyio.run(lambda: mcp_server.mcp.call_tool(_tool, arguments))

    return invoke


def _a_product(call_as, actor, sku: str) -> dict:
    return call_as(
        actor,
        "create_product",
        sku=sku,
        name="Rice 5kg",
        category="Grains",
        unit="bag",
        cost_price="10.00",
        sell_price="15.00",
    ).structured_content


def test_a_row_written_through_the_agent_carries_the_users_own_identity(
    call_as, session, unique_sku
):
    """Half one of the exit condition.

    The agent adjusts stock for a signed-in user, and the row records **that
    user**, not the agent and not "mcp". This is what the `Actor`-as-a-parameter
    design was built for in gate 3, and it is why `created_by`/`updated_by`
    exist at all: an ERP needs to answer "who adjusted this stock?".
    """
    from core.actor import TokenActor
    from core.models import Product

    fatima = TokenActor(
        "01a02d8f-0355-74cd-b102-3b1ab2372d64",
        frozenset({"product.create", "product.read", "stock.adjust"}),
    )

    created = _a_product(call_as, fatima, unique_sku)
    call_as(fatima, "adjust_stock", product_id=created["id"], delta=10)

    row = session.get(Product, created["id"])
    assert row.quantity_on_hand == 10
    assert row.updated_by == "01a02d8f-0355-74cd-b102-3b1ab2372d64"


def test_a_read_only_agent_is_refused_and_the_stock_does_not_move(
    call_as, session, unique_sku
):
    """⚠️ Half two, and the half that actually proves the gate.

    A token narrowed to reads is handed the write tool. It must be refused by
    `services/` - not by the adapter, not by the model declining - and the
    quantity must be **unchanged afterwards**.

    Asserting only on the reply would be the classic mistake this project's plan
    warned about explicitly: a tool that wrote the row and then returned an
    apologetic message would pass a text assertion and be the worst bug in the
    codebase. So the last line reads the database.
    """
    from mcp.server.mcpserver.exceptions import ToolError

    from core.actor import TokenActor
    from core.models import Product

    # `product.read` is in the set because adjust_stock reads the row before it
    # writes it. Worth noticing rather than papering over: permissions here are
    # per-operation, not per-tool, and one tool can need two of them.
    setup = TokenActor(
        "setup-user",
        frozenset({"product.create", "product.read", "stock.adjust"}),
    )
    created = _a_product(call_as, setup, unique_sku)
    call_as(setup, "adjust_stock", product_id=created["id"], delta=10)

    # Same person, narrower token: reads only. Note this is exactly what
    # ThunderID hands back for a downscoped exchange - the scope set shrinks and
    # nothing else about the token changes.
    read_only = TokenActor("setup-user", frozenset({"product.read"}))

    with pytest.raises(ToolError):
        call_as(read_only, "adjust_stock", product_id=created["id"], delta=500)

    session.expire_all()
    row = session.get(Product, created["id"])
    assert row.quantity_on_hand == 10, (
        "the write happened despite the refusal - a refusal that is only a "
        "message is not a refusal"
    )
