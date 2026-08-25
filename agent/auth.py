"""Trading the user's token for a narrower one. The delegation half of gate 25.

### The idea, before the mechanism

The person signs in to the web app and gets an access token - a small signed
note from ThunderID saying "this is Fatima, and she may read products and adjust
stock". If the agent simply forwarded that note to the ERP, the agent would be
exactly as powerful as Fatima, forever, for anything.

Instead it hands the note back to ThunderID and asks for a **smaller** one:
still Fatima, still signed, but valid only at the MCP server and only for the
permissions this task needs. ThunderID mints it. The important part is what it
will not do: **it cannot hand back more authority than the note it was given**,
no matter what the agent asks for. "The agent may only do what the user may do"
is enforced at the issuer, not by our code, which is why it survives our bugs.

### ⚠️ The failure that returns 200 OK

Verified against the live server on 2026-08-25, and this is the whole reason
`get_scoped_token` reads the `scope` that came back rather than trusting the
status code:

  - asking for **more** scope than the user has → `200 OK`, with *less* scope
    in the response than was asked for. No error, no warning.
  - asking for a permission that **does not exist** → `200 OK`, with a
    structurally valid, correctly-audienced token carrying **no `scope` claim at
    all**.

Neither is distinguishable from success by looking at the status code. So this
module never trusts a 200: it reads the `scope` that came back and decides from
that. The two cases are **not** treated alike, and the difference matters:

  - a **partial** grant is returned, with a warning logged. `thunderid_scopes`
    is a ceiling, not a minimum, so a read-only user legitimately gets one scope
    back out of four. Refusing that shortfall - which this module did until
    CodeRabbit found it on PR #30 - locked such a user out of even asking a
    read-only question. Deciding permission-by-permission is `services/`'s job;
    it has the information, and this function does not.
  - an **empty** grant is refused. A token that can do nothing at all
    authenticates and is then denied by every permission check downstream, and
    that symptom looks nothing like its cause. Refusing it here, next to the log
    line that explains why, is far kinder than debugging it there.

### The rule that keeps ID-JAG open

**Never hardcode the grant type or the requested token type.** Both are
parameters of this one function. Switching to ID-JAG later means passing
`ID_JAG_TOKEN_TYPE` and swapping what `mcp_client.py` hands its transport (the
SDK already ships `IdentityAssertionOAuthProvider` for exactly that slot);
agent-to-agent delegation
means supplying `actor_token`, which this function already accepts. Nothing
above this file names an OAuth mechanism. See docs/AUTH-PLAN.md, "ID-JAG is a
parameter, not a second architecture" - and note that ID-JAG is deliberately
**off** for this gate.
"""

from __future__ import annotations

import logging
import os
import ssl
from dataclasses import dataclass

import httpx

from config import settings

_log = logging.getLogger(__name__)

# RFC 8693. Spelled out rather than assembled, because a typo in a URN produces
# `unsupported_grant_type`, which reads like a server misconfiguration.
TOKEN_EXCHANGE_GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"

ACCESS_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"

# The ID-JAG output type. Present so the switch is a value, not a rewrite; not
# used anywhere today. See this module's docstring.
ID_JAG_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:id-jag"


class DelegationError(Exception):
    """Token exchange did not produce a token we can use.

    A plain exception rather than one of `core/exceptions.py`'s: `agent/` is a
    separate service with a separate virtualenv and never imports the backend
    (docs/AGENT-PLAN.md, "Architecture"). `app.py` translates this into an HTTP
    response, the same way each backend adapter translates its own errors.
    """


@dataclass(frozen=True)
class ScopedToken:
    """An exchanged token and, crucially, what it actually turned out to allow.

    `scopes` is the set ThunderID *returned*, not the set that was requested.
    Keeping both apart in the type is the point: a caller that reads `scopes`
    cannot accidentally read its own wish list back.
    """

    access_token: str
    scopes: frozenset[str]


def _verify() -> ssl.SSLContext | bool:
    """What to pass to httpx as `verify`. An SSL context, or a bool.

    Prefers pinning ThunderID's own self-signed certificate, which still refuses
    an attacker's certificate, over disabling verification wholesale. Falls back
    only when the file is genuinely absent - it is gitignored, because each
    machine's Compose run generates its own - and says so at WARNING, because a
    silent downgrade from "pinned" to "unchecked" is exactly the kind of thing
    that survives into a deployment.

    ⚠️ A **context**, not the path. Handing httpx a path string still works on
    the pinned `httpx==0.28.1` but is deprecated there, and the deprecation is
    the kind that becomes a hard failure on a future bump - at which point the
    symptom would be "the agent cannot reach the login server", nowhere near
    this line. Building the context here also keeps the rest of the default
    security policy that `create_default_context` sets, rather than only the
    trust store. Raised by CodeRabbit on PR #30.
    """
    if os.path.isfile(settings.thunderid_ca_cert):
        return ssl.create_default_context(cafile=settings.thunderid_ca_cert)

    if not settings.thunderid_verify_tls:
        _log.warning(
            "ThunderID's certificate is not being checked: %s does not exist "
            "and THUNDERID_VERIFY_TLS is false. Anyone able to intercept this "
            "connection can mint tokens the agent will use.",
            settings.thunderid_ca_cert,
        )
        return False

    return True


async def get_scoped_token(
    user_token: str,
    *,
    resource: str | None = None,
    scopes: str | None = None,
    requested_token_type: str = ACCESS_TOKEN_TYPE,
    actor_token: str | None = None,
    actor_token_type: str = ACCESS_TOKEN_TYPE,
) -> ScopedToken:
    """Exchange `user_token` for one narrowed to `resource` and `scopes`.

    Args:
        user_token: the signed-in person's access token, as it arrived.
        resource: RFC 8707 resource indicator - which service the new token is
            valid at. Defaults to the MCP server. **This is the parameter that
            sets `aud`**; `audience` is accepted by ThunderID and then ignored.
        scopes: space-delimited ceiling. Defaults to the configured set. Asking
            for more than the user has is not an error and does not warn - it
            silently returns less, which is what the check below is for.
        requested_token_type: what kind of token to get back. The ID-JAG seam.
        actor_token: who is doing the narrowing, for a delegation chain. Omitted
            today: without it the token is correctly downscoped but carries no
            `act` claim recording the agent. Our `created_by`/`updated_by`
            columns already carry that accountability, so it is knowingly not
            paid for here.

    Raises:
        DelegationError: on a transport failure, an OAuth error, an
            unreadable body, or - the case that matters - a `200 OK` whose
            token carries **no scope at all**. A token carrying *some* of what
            was asked for is returned, not refused: `scopes` is a ceiling, and
            `services/` refuses individual permissions.
    """
    if not settings.thunderid_client_id or not settings.thunderid_client_secret:
        raise DelegationError(
            "The agent has no ThunderID credentials, so it cannot obtain a "
            "token for you. Set THUNDERID_CLIENT_ID and THUNDERID_CLIENT_SECRET "
            "in agent/.env (see agent/.env.example)."
        )

    resource = resource or settings.thunderid_mcp_audience
    scopes = scopes if scopes is not None else settings.thunderid_scopes
    wanted = frozenset(scopes.split())

    form = {
        "grant_type": TOKEN_EXCHANGE_GRANT,
        "subject_token": user_token,
        "subject_token_type": ACCESS_TOKEN_TYPE,
        "requested_token_type": requested_token_type,
        # RFC 8707. Not `audience` - see this module's docstring.
        "resource": resource,
        "scope": scopes,
    }
    if actor_token is not None:
        # `actor_token_type` is required whenever `actor_token` is given.
        form["actor_token"] = actor_token
        form["actor_token_type"] = actor_token_type

    try:
        async with httpx.AsyncClient(verify=_verify(), timeout=10) as client:
            response = await client.post(
                settings.thunderid_token_url,
                data=form,
                # Basic, not form fields. `AIsle Agent` is registered as
                # `client_secret_basic`; sending the secret in the body instead
                # is answered with `unauthorized_client`.
                auth=(settings.thunderid_client_id, settings.thunderid_client_secret),
            )
    except httpx.HTTPError as exc:
        # The reason goes in the log; the caller gets a message that does not
        # describe our infrastructure.
        _log.warning("Token exchange failed to reach ThunderID: %s", exc)
        raise DelegationError("Could not reach the login server.") from exc

    if response.status_code != 200:
        # OAuth error responses carry a machine-readable `error` code. Logged,
        # not returned: `invalid_client` versus `invalid_grant` tells a caller
        # things about our configuration they should not learn from us.
        _log.warning(
            "Token exchange refused (HTTP %s): %s",
            response.status_code,
            response.text[:500],
        )
        raise DelegationError("The login server refused to issue a token.")

    try:
        payload = response.json()
    except ValueError as exc:
        # A 200 carrying something that is not JSON - a proxy's error page, say.
        # Caught so that every failure leaving this function is a
        # `DelegationError`, which is what its `Raises:` block promises and what
        # `app.py` translates. A decode error escaping raw would surface as a
        # 500 with a stack trace.
        _log.warning("Token exchange returned a body that is not JSON.")
        raise DelegationError("The login server returned no usable token.") from exc

    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise DelegationError("The login server returned no usable token.")

    # ⚠️ The line the whole module exists for. A missing `scope` key is not
    # "unspecified, therefore everything" - it is what ThunderID returns when it
    # did not recognise a permission that was asked for, and it means nothing
    # was granted.
    raw_granted = payload.get("scope", "")
    granted = frozenset(raw_granted.split()) if isinstance(raw_granted, str) else frozenset()

    if wanted - granted:
        _log.warning(
            "Token exchange returned less than was asked for. Wanted %s, got "
            "%s. This is a 200 OK - ThunderID narrows silently rather than "
            "erroring, so check the user's role and the agent's role before "
            "suspecting the code.",
            sorted(wanted),
            sorted(granted) or "nothing at all",
        )

    # ⚠️ A partial grant is the normal case, not a failure. `thunderid_scopes`
    # is a **ceiling** - see the note on it in config.py - so a person holding
    # only `product.read` legitimately gets one scope back out of four. This
    # used to refuse on any shortfall, which turned the ceiling into a minimum
    # and locked read-only users out of even asking a question. Found by
    # CodeRabbit on PR #30. Per-permission refusal belongs to `services/`, which
    # has the actual information; this function's job is only to notice a token
    # that can do nothing at all.
    if not granted:
        # No scope whatsoever is the shape ThunderID returns for a permission it
        # did not recognise. Such a token authenticates and is then refused by
        # every `can()`, so it is refused here instead, where the cause is still
        # legible in the log line above.
        raise DelegationError(
            "You do not have any of the permissions this agent needs."
        )

    return ScopedToken(access_token=token, scopes=granted)
