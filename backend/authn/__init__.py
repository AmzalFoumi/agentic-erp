"""Token validation, shared by both adapters.

A fourth top-level package, and the reason it exists is worth stating because
the obvious homes are all wrong:

  - Not `core/`, and not `services/`. Both are forbidden from importing a web
    or protocol library, and that ban now includes `jwt` (see the
    forbidden_modules lists in pyproject.toml). A JWT is a transport-level
    credential; the moment core/ knows how to parse one, the boundary this
    project is built around has a hole in it.
  - Not `api/`. `mcp_server/` needs exactly the same verification at gate 25,
    and the two adapters may never import each other. Putting it in one would
    force either a duplicate or a violation.

So it sits on its own layer: above `services/`, below the adapters, importing
neither. It converts a bearer token into a `core.actor.TokenActor` and raises
`core.exceptions.AuthenticationError` when it cannot.
"""

from authn.tokens import verify_access_token

__all__ = ["verify_access_token"]
