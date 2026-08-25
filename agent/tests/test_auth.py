"""What `get_scoped_token` does with the token exchange's answer.

This file exists because of a defect CodeRabbit found on PR #30: the scope
check refused any grant narrower than what was asked for, which turned
`thunderid_scopes` from a ceiling into a minimum and locked a read-only user
out of even asking a read-only question. The path had no test at all, which is
how it survived a gate.

**Nothing here reaches ThunderID.** `httpx.AsyncClient` is replaced with a fake
whose `post` returns a canned response, so these tests pin our reading of the
answer rather than the login server's behaviour. The shapes being faked - a
partial grant, a missing `scope` key on a `200 OK` - are the ones observed
against the live server on 2026-08-25 and recorded in docs/AUTH-PLAN.md.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auth as auth_module  # noqa: E402
from auth import DelegationError, get_scoped_token  # noqa: E402


class _Response:
    """Just enough of `httpx.Response` for the code under test."""

    def __init__(self, payload, *, status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@pytest.fixture
def exchange(monkeypatch):
    """Make the token endpoint answer with whatever a test hands it."""

    def _answer(payload, *, status_code: int = 200):
        class _Client:
            def __init__(self, **_kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc):
                return False

            async def post(self, *_args, **_kwargs):
                return _Response(payload, status_code=status_code)

        monkeypatch.setattr(auth_module.httpx, "AsyncClient", _Client)
        monkeypatch.setattr(auth_module.settings, "thunderid_client_id", "test-client")
        monkeypatch.setattr(auth_module.settings, "thunderid_client_secret", "test-secret")

    return _answer


async def test_a_partial_grant_is_returned_not_refused(exchange):
    """⚠️ The defect this file was written for.

    `thunderid_scopes` is a **ceiling** - the most the agent could ever want -
    so a person holding only `product.read` legitimately gets one scope back
    out of four. Refusing that shortfall meant every message such a person
    typed failed before any tool ran, including questions needing nothing but
    read access. Per-permission refusal is `services/`'s job; this function's
    only concern is a token that can do nothing at all.
    """
    exchange({"access_token": "narrowed", "scope": "product.read"})

    token = await get_scoped_token("user-token", scopes="product.read stock.adjust")

    assert token.access_token == "narrowed"
    assert token.scopes == frozenset({"product.read"})


async def test_a_missing_scope_claim_means_zero_permissions(exchange):
    """⚠️ ThunderID's silent 200, pinned.

    Asking for a permission that does not exist returns a structurally valid,
    correctly-audienced token carrying **no `scope` claim at all**. Nothing in
    the response says so. A missing key must therefore read as *zero*
    permissions, never "unspecified, therefore allow" - and it is refused here,
    where the log line above still explains the cause, rather than later as
    every single tool call being denied for no visible reason.
    """
    exchange({"access_token": "scopeless"})

    with pytest.raises(DelegationError):
        await get_scoped_token("user-token")


async def test_a_full_grant_comes_back_intact(exchange):
    """The ordinary case, so the two above are not the only shapes covered."""
    exchange({"access_token": "full", "scope": "product.read product.update"})

    token = await get_scoped_token("user-token", scopes="product.read product.update")

    assert token.scopes == frozenset({"product.read", "product.update"})


async def test_a_body_that_is_not_json_is_still_a_delegation_error(exchange):
    """Every failure leaving this function must wear the same clothes.

    A `200 OK` carrying a proxy's HTML error page used to raise a decode error
    straight through `app.py`'s translation and surface as a 500 with a stack
    trace. The function's documented contract is that its failures are all
    `DelegationError`, and this pins it.
    """
    exchange(ValueError("not json"))

    with pytest.raises(DelegationError):
        await get_scoped_token("user-token")


async def test_an_oauth_refusal_does_not_leak_the_reason(exchange):
    """`invalid_client` versus `invalid_grant` tells a caller about our setup.

    The distinction goes in the log, not the message - otherwise the endpoint
    becomes an oracle for probing our ThunderID configuration.
    """
    exchange({"error": "invalid_client"}, status_code=401)

    with pytest.raises(DelegationError) as caught:
        await get_scoped_token("user-token")

    assert "invalid_client" not in str(caught.value)
