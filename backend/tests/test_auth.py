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
    monkeypatch's own teardown restores the real function. Nothing here ever
    populates the real cache.
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
