"""Bearer-token checking for the MCP adapter, in the MCP SDK's own dialect.

### Why this file exists at all

`authn/tokens.py` already knows how to verify a ThunderID token. It is not
enough on its own, because the MCP SDK does not ask "is this token valid" - it
asks for an object satisfying its `TokenVerifier` protocol, returning its own
`AccessToken` model or `None`. That is a dialect, exactly like HTTP status codes
are `api/`'s dialect, so the translation lives here in the adapter, beside
`mcp_server/errors.py`, and `authn/` stays free of the MCP SDK. The
import-linter contract "Authn stays adapter-free" in pyproject.toml enforces
that rather than leaving it to good intentions.

### The audience is this server, not the API

The token must carry `aud = thunderid_mcp_audience`, a *different* resource
server from the HTTP API's. The MCP authorization specification requires an MCP
server to verify that a token was minted for itself; accepting the API's
audience here would mean a token issued for one front door opens the other, and
the destination half of delegation would be worthless. See docs/AUTH-PLAN.md.

### ⚠️ The failure that does not look like one

Verified against the live server on 2026-08-25: asking ThunderID's token
exchange for a permission that does not exist returns **HTTP 200 with a
structurally valid, correctly-audienced token carrying no `scope` claim at
all**. Nothing in the response distinguishes it from a success. So a missing or
empty scope must mean **zero permissions**, never "unspecified, therefore
allow". That is already how `authn/tokens.py` and `TokenActor` behave, and
`tests/test_mcp_auth.py` pins it here as a regression test, because this is the
kind of property that is rewritten by someone being helpful.
"""

from __future__ import annotations

import logging

from mcp.server.auth.provider import AccessToken

from authn import verify_access_token
from core.config import settings
from core.exceptions import AuthenticationError

_log = logging.getLogger(__name__)


class ThunderIDTokenVerifier:
    """Satisfies the SDK's `TokenVerifier` protocol. Structural, not inherited.

    `TokenVerifier` is a `Protocol` - the same structural typing `core/actor.py`
    uses for `Actor`. Having an `async def verify_token` of the right shape is
    the whole of implementing it; there is no base class to subclass and no
    registration step.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return the token's details, or `None` if it is not acceptable.

        `None` rather than an exception because that is what the protocol
        specifies: the SDK turns it into the MCP-flavoured 401 with the
        `WWW-Authenticate` header the spec requires. Raising here would surface
        as a 500 and tell an anonymous caller that something inside broke.

        `async` because the protocol is, not because anything here awaits.
        `authn/tokens.py` verifies against a cached key set and only touches the
        network on a cache miss - see its note on `timeout=5`, which exists so
        that a slow key fetch cannot hold this coroutine open.
        """
        try:
            actor = verify_access_token(
                token, audience=settings.thunderid_mcp_audience
            )
        except AuthenticationError:
            # Deliberately not logged here. `authn/tokens.py` has already logged
            # the real reason at the right level - INFO for an ordinary expired
            # token, WARNING for ThunderID being unreachable - and a second line
            # saying "rejected" would add no information while doubling the
            # volume of a 401 storm.
            return None

        if not actor.scopes:
            # Not a rejection: the token is genuine and the caller is who they
            # say they are. It is worth a line anyway, because this is the shape
            # ThunderID returns for a permission that does not exist, and the
            # symptom - every tool call refused by services/ - looks nothing
            # like its cause. See this module's docstring.
            _log.warning(
                "Access token for subject %s carries no scopes; every "
                "permission check will refuse it. Suspect the token, not the "
                "code - see docs/AUTH-PLAN.md on ThunderID's silent 200.",
                actor.id,
            )

        return AccessToken(
            token=token,
            # The SDK's field, and it is required. We do not carry the OAuth
            # client id through `authn/` - it verifies identity, not which
            # application asked - so the actor id stands in. Nothing downstream
            # reads it: `_actor()` in server.py builds its TokenActor from
            # `subject` and `scopes`, which are the two claims services/ needs.
            client_id=actor.id,
            # `sorted` for a stable value in logs and test failures, the same
            # reason TokenActor.__repr__ sorts. A frozenset has no order.
            scopes=sorted(actor.scopes),
            subject=actor.id,
            resource=settings.thunderid_mcp_audience,
        )
