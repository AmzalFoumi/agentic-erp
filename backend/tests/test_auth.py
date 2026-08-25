"""Tests for gate 24: turning a bearer token into an Actor.

Nothing here touches a running ThunderID. The verifier's job is to check a
signature against a public key, and a key pair generated in-process proves that
just as well as a real one - while also letting us mint the tokens that are
*supposed* to fail, which a real issuer would never hand out. A test suite that
needs a login server running is a test suite that gets skipped.
"""

from __future__ import annotations

import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from core.actor import TokenActor
from core.config import settings
from core.exceptions import AuthenticationError


# ---------------------------------------------------------------------------
# TokenActor - the permission check itself
# ---------------------------------------------------------------------------


def test_can_is_exact_membership():
    actor = TokenActor("user-1", frozenset({"product.read", "stock.adjust"}))

    assert actor.can("product.read")
    assert actor.can("stock.adjust")
    assert not actor.can("product.create")


def test_a_parent_scope_grants_nothing():
    """`product` does not imply `product.read`.

    Worth pinning down because the dotted strings *look* hierarchical. They are
    not - the delimiter exists to make ThunderID's strings match the ones in
    services/, not to express a tree. A prefix rule here would silently widen
    every permission in the system.
    """
    actor = TokenActor("user-1", frozenset({"product"}))

    assert not actor.can("product.read")
    assert actor.can("product")  # only the exact string it was granted


def test_no_scopes_denies_everything():
    """The fail-closed case, and the one most likely to happen by accident.

    ThunderID answers a request for permissions it does not recognise with a
    perfectly valid token carrying no scope claim. The resulting actor must be
    able to do nothing at all.
    """
    actor = TokenActor("user-1", frozenset())

    assert not actor.can("product.read")
    assert actor.id == "user-1"


# ---------------------------------------------------------------------------
# verify_access_token - signature, issuer, audience, expiry
# ---------------------------------------------------------------------------


@pytest.fixture
def signing_key() -> rsa.RSAPrivateKey:
    """A throwaway RSA key pair standing in for ThunderID's signing key."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def verify(monkeypatch, signing_key):
    """`verify_access_token`, with the JWKS fetch replaced by our public key.

    Patching `_jwk_client` rather than the network keeps the test honest about
    what it is skipping: key *distribution* is out of scope here, key *use* is
    not. Everything after the lookup - algorithm pinning, aud, iss, exp, the
    required-claims list - runs exactly as it does in production.

    Patched as a plain attribute rather than by clearing the lru_cache, so
    monkeypatch's own teardown restores the real function. This fixture never
    populates the real cache.

    One test in this module does, and harmlessly:
    `test_garbage_is_refused_without_reaching_the_network` deliberately takes no
    fixture, so `_jwk_client()` runs and its lru_cache holds a real PyJWKClient
    for the rest of the session. No network call happens - constructing the
    client does not fetch anything, and the token is rejected while decoding its
    header, before any key lookup. That ordering is the property that test
    exists to pin.
    """
    from authn import tokens

    class _StubKey:
        key = signing_key.public_key()

    class _StubClient:
        def get_signing_key_from_jwt(self, token: str) -> _StubKey:
            return _StubKey()

    monkeypatch.setattr(tokens, "_jwk_client", lambda: _StubClient())
    return tokens.verify_access_token


def _token(signing_key: rsa.RSAPrivateKey, **overrides: Any) -> str:
    """A token shaped exactly like the real one captured on 2026-08-23."""
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": "01a02d8f-0355-74cd-b102-3b1ab2372d64",
        "aud": settings.thunderid_audience,
        "iss": settings.thunderid_issuer,
        "iat": now,
        "nbf": now,
        "exp": now + 3600,
        "scope": "openid product.read product.create",
        "client_id": "vAf_zSFT1qj4733Xy3jgQw",
    }
    claims.update(overrides)
    return jwt.encode(claims, signing_key, algorithm="RS256")


def test_a_valid_token_becomes_an_actor(verify, signing_key):
    actor = verify(_token(signing_key))

    assert actor.id == "01a02d8f-0355-74cd-b102-3b1ab2372d64"
    assert actor.can("product.read")
    assert actor.can("product.create")
    assert not actor.can("stock.adjust")


def test_a_token_for_another_service_is_refused(verify, signing_key):
    """The audience check - the one that stops token passthrough.

    Genuine user, genuine signature, genuine issuer, minted for someone else.
    Accepting it would let any service holding a ThunderID token replay it here.
    """
    with pytest.raises(AuthenticationError):
        verify(_token(signing_key, aud="https://someone-elses-api.example"))


def test_a_token_from_another_issuer_is_refused(verify, signing_key):
    """A valid signature only proves *someone* signed it."""
    with pytest.raises(AuthenticationError):
        verify(_token(signing_key, iss="https://evil.example"))


def test_an_expired_token_is_refused(verify, signing_key):
    now = int(time.time())
    with pytest.raises(AuthenticationError):
        verify(_token(signing_key, iat=now - 7200, nbf=now - 7200, exp=now - 3600))


def test_a_tampered_signature_is_refused(verify, signing_key):
    """Flip one character in the middle of the signature segment.

    Deliberately not the *last* character: base64url encodes the trailing bits
    with slack, so several final characters decode to the same bytes and the
    signature still verifies. The middle is unambiguous.
    """
    token = _token(signing_key)
    head, payload, signature = token.split(".")
    mid = len(signature) // 2
    swap = "A" if signature[mid] != "A" else "B"
    tampered = f"{head}.{payload}.{signature[:mid]}{swap}{signature[mid + 1:]}"

    with pytest.raises(AuthenticationError):
        verify(tampered)


def test_a_token_signed_with_a_different_key_is_refused(verify):
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    with pytest.raises(AuthenticationError):
        verify(_token(other_key))


def test_a_token_without_a_subject_is_refused(verify, signing_key):
    """`sub` becomes created_by. A row with no provenance is not acceptable."""
    with pytest.raises(AuthenticationError):
        verify(_token(signing_key, sub=None))


def test_a_token_with_no_scope_claim_authenticates_but_can_do_nothing(
    verify, signing_key
):
    """Not an error - see the warning on TokenActor. Fails closed instead."""
    token = jwt.encode(
        {
            "sub": "user-9",
            "aud": settings.thunderid_audience,
            "iss": settings.thunderid_issuer,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        },
        signing_key,
        algorithm="RS256",
    )

    actor = verify(token)

    assert actor.id == "user-9"
    assert not actor.can("product.read")


def test_garbage_is_refused_without_reaching_the_network():
    """No stub here on purpose.

    A malformed token must fail before anything tries to fetch a key set. If
    this test ever starts hanging or needing a container, that ordering broke.
    """
    from authn import verify_access_token

    with pytest.raises(AuthenticationError):
        verify_access_token("not-a-jwt")


def test_a_non_string_scope_claim_grants_nothing_rather_than_crashing(
    verify, signing_key
):
    """A malformed credential must not become a 500.

    The `scope` claim is read *after* the try block that turns JWT problems into
    AuthenticationError, so a claim of the wrong shape - a list, a number - used
    to reach `.split()` unguarded and surface as a server error. A token we
    cannot make sense of is a refused token, not a broken server, and an actor
    with no permissions is the fail-closed reading.
    """
    for bad_scope in (["product.read"], 42, {"read": True}):
        actor = verify(_token(signing_key, scope=bad_scope))

        assert actor.id == "01a02d8f-0355-74cd-b102-3b1ab2372d64"
        assert not actor.can("product.read")
        assert actor.scopes == frozenset()


def test_an_unreachable_key_set_is_logged_as_a_provider_fault(
    monkeypatch, caplog, signing_key
):
    """An identity-provider outage must not be logged as a rejected token.

    This pins an ordering, not a behaviour. `PyJWKClientConnectionError` is a
    *subclass* of `PyJWTError`, and `PyJWKClient.fetch_data()` wraps `URLError`
    and `TimeoutError` into it - so a `except jwt.PyJWTError` clause placed
    first swallows "ThunderID is down" and logs it at INFO as an ordinary
    expired-token event. That is exactly what happened until 2026-08-24, which
    made the WARNING branch dead code for the one case it was written to catch.

    The caller still sees the same AuthenticationError either way - deliberately,
    so nobody can probe our infrastructure through the API - which is precisely
    why the log line is the only place the distinction survives, and why it is
    worth a test.
    """
    import logging

    from authn import tokens, verify_access_token

    class _DownClient:
        def get_signing_key_from_jwt(self, token: str):
            raise jwt.PyJWKClientConnectionError("Fail to fetch data from the url")

    monkeypatch.setattr(tokens, "_jwk_client", lambda: _DownClient())

    with caplog.at_level(logging.INFO, logger=tokens.__name__):
        with pytest.raises(AuthenticationError):
            verify_access_token(_token(signing_key))

    assert [r.levelno for r in caplog.records] == [logging.WARNING], (
        "an unreachable key set must log WARNING, not INFO - check that the "
        "PyJWKClientError clause still sits above the PyJWTError clause"
    )
    assert "key set unreachable" in caplog.records[0].getMessage()


def test_every_rejection_reason_looks_identical_to_the_caller(verify, signing_key):
    """The refusal must not say *why* it refused.

    `verify_access_token`'s docstring promises this: a caller who can tell
    "expired" from "wrong audience" from "bad signature" can use the endpoint as
    an oracle to map our configuration - probing audience strings until one
    fails differently, for instance. The reason goes to the log, never to the
    response.

    Nothing pinned that promise until now, so a well-meaning change like
    `raise AuthenticationError(f"Token invalid: {exc}")` would have leaked every
    reason at once and kept the suite green. This asserts the *set* of messages
    across four genuinely different failures collapses to exactly one string.
    """
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())

    bad_tokens = {
        "expired": _token(signing_key, exp=now - 1, iat=now - 3600, nbf=now - 3600),
        "wrong audience": _token(signing_key, aud="https://someone-elses.example"),
        "wrong issuer": _token(signing_key, iss="https://not-our-thunderid.example"),
        "signed by a stranger": _token(other_key),
    }

    messages = {}
    for reason, token in bad_tokens.items():
        with pytest.raises(AuthenticationError) as caught:
            verify(token)
        messages[reason] = str(caught.value)

    assert len(set(messages.values())) == 1, (
        "the refusal message must not vary with the reason for refusal - a "
        f"caller could tell these apart and probe our config: {messages}"
    )

    # And it must not name the reason even in the single shared string.
    only_message = next(iter(set(messages.values()))).lower()
    for leaked in ("expired", "audience", "issuer", "signature", "algorithm"):
        assert leaked not in only_message, (
            f"the shared refusal message names {leaked!r}: {only_message!r}"
        )
