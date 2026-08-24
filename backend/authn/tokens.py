"""Turn a bearer token into an Actor, or refuse it.

### What this does, and what it deliberately does not

It checks four things, in the order that matters:

  1. the signature, against ThunderID's published public keys;
  2. the issuer (`iss`) - someone else's valid signature is still someone else's;
  3. the audience (`aud`) - a token minted for another service is not ours to
     accept, even if the user and the signature are genuine;
  4. expiry (`exp` / `nbf`).

It does *not* ask ThunderID whether the token is still good. That would be
token introspection - a network round trip on every single request, and a hard
dependency on the identity provider being up. The cost of local verification is
that a token revoked early stays usable until it expires. With a 3600-second
lifetime that is an acceptable trade, and it is the trade the MCP authorization
spec assumes.

### Why the audience check is not optional

It is the one check that stops token passthrough. Without it, any service that
can obtain a valid ThunderID token for *anything* could replay it here and be
believed. RFC 8707 exists for this, and the MCP specification makes it a MUST.

### Keys are cached

`PyJWKClient` fetches the key set once and reuses it (`lifespan` seconds),
refetching when it sees a `kid` it does not know - which is exactly what
happens after a key rotation. Without caching this would fetch a document over
the network on every request.
"""

from __future__ import annotations

import logging
import ssl
from functools import lru_cache

import jwt
from jwt import PyJWKClient

from core.actor import TokenActor
from core.config import settings
from core.exceptions import AuthenticationError

# ThunderID signs with RS256. Pinning the list is a real check, not ceremony:
# accepting whatever the token's own header asks for is the classic JWT
# vulnerability, where an attacker sets `alg: none` or downgrades an RSA key
# into an HMAC secret. pyjwt requires `algorithms` for this reason.
_ALGORITHMS = ["RS256"]

# The other half of "the reason goes in the log, not the response". Every
# refusal below is deliberately indistinguishable to the caller, which leaves
# this logger as the ONLY way to tell an expired token from a wrong audience
# from ThunderID being unreachable. Without it a 401 storm is undiagnosable.
_log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _jwk_client() -> PyJWKClient:
    """The cached key-set client. Built once, on first use.

    Lazily rather than at import time on purpose: importing this module must
    not require ThunderID to be reachable, or the test suite and every offline
    task would depend on a running container.
    """
    ssl_context: ssl.SSLContext | None = None
    if not settings.thunderid_verify_tls:
        # LOCAL ONLY - see the note on thunderid_verify_tls in core/config.py.
        # Scoped to this one client so it cannot leak into any other TLS
        # connection the process makes.
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    return PyJWKClient(
        settings.thunderid_jwks_url,
        cache_jwk_set=True,
        lifespan=300,
        ssl_context=ssl_context,
    )


def verify_access_token(token: str) -> TokenActor:
    """Validate `token` and return the actor it describes.

    Raises AuthenticationError for every failure mode, with a message safe to
    hand back to a caller. The distinction between "expired", "wrong audience"
    and "signature failed" is deliberately NOT exposed: a caller who can tell
    those apart can use the endpoint as an oracle to probe our configuration.
    The specific reason goes in the log, not the response.
    """
    try:
        signing_key = _jwk_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=_ALGORITHMS,
            audience=settings.thunderid_audience,
            issuer=settings.thunderid_issuer,
            # `sub` is required because it becomes created_by/updated_by. A
            # token without one would write NULL into an audit column and the
            # row would silently lose its provenance.
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        # INFO, not WARNING: an expired token is the single most common event
        # in a healthy system - every session reaches this once an hour. Logging
        # it as a warning would train everyone to ignore the warnings.
        _log.info("Rejected access token: %s: %s", type(exc).__name__, exc)
        raise AuthenticationError("The access token is not valid.") from exc
    except Exception as exc:
        # Reaching the key set can fail for reasons that are not the token's
        # fault - ThunderID down, TLS refused, DNS. Still a 401 rather than a
        # 500, because from the caller's side the outcome is identical: we
        # cannot establish who they are. The cause is preserved for the log.
        # WARNING here, because this branch is NOT the token's fault and is not
        # routine: it means the key set could not be reached. The caller sees
        # the same 401 either way, so this line is the only signal that the
        # identity provider - not the user - is the thing that is broken.
        _log.warning(
            "Could not verify access token - key set unreachable or malformed: %s: %s",
            type(exc).__name__,
            exc,
        )
        raise AuthenticationError("Could not verify the access token.") from exc

    # A missing `scope` claim is not an error here - see the warning on
    # TokenActor: ThunderID emits exactly that when it does not recognise the
    # permissions requested. It produces an actor that can do nothing, which is
    # the correct fail-closed outcome.
    #
    # The isinstance guard is not defensive noise. `scope` arrives from outside
    # this process, and this line sits *after* the try block: a token carrying
    # `scope` as a list or a number would raise AttributeError here and surface
    # as a 500, turning a malformed credential into a server fault. Anything
    # that is not a string is treated as no scopes at all - fail closed, and
    # say so in the log, because it means the issuer is emitting a shape we do
    # not understand.
    raw_scope = claims.get("scope", "")
    if not isinstance(raw_scope, str):
        _log.warning(
            "Ignoring non-string `scope` claim (%s) for subject %s; granting nothing.",
            type(raw_scope).__name__,
            claims["sub"],
        )
        raw_scope = ""

    return TokenActor(actor_id=claims["sub"], scopes=frozenset(raw_scope.split()))
