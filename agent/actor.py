"""Who is asking. The agent's own copy of the identity seam.

**A copy of `backend/core/actor.py`, not an import** - for exactly the reason
`config.py` and `database.py` are copies: `agent/` is a separate process with a
separate virtualenv that reaches the ERP only over MCP (docs/AGENT-PLAN.md,
"Architecture"). Importing `backend.core.actor` would cross the boundary the
whole design exists to hold. Read that file for the full reasoning on why
identity is a parameter rather than ambient request state; it is the original
and this is the mirror.

**Why this exists at Gate 20 rather than at the auth gate.** Gate 19 created a
privileged action - approving a tool call that changes data - with no notion of
who is deciding. In-process that was harmless: the only caller was a test. Gate
20 puts an HTTP boundary in front of it, and retrofitting identity into an
HTTP-shaped approval path afterwards is precisely the "known trap" CLAUDE.md
records for `mcp_server/server.py`'s `_actor()`. So the parameter lands now,
carrying `SystemActor`, and threading a real actor later is a change to
`app.py`'s `get_actor()` and `mcp_client.py`'s `call_tool` - not a rewrite.

**Provider agnostic, deliberately.** Nothing in this file - and nothing anywhere
in `agent/` - imports an auth library or names a provider. The seam carries a
Protocol with `id` and `can()` and nothing else. `docs/AUTH-PLAN.md` owns the
provider comparison and the choice is still open; this file must not narrow it.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Actor(Protocol):
    """Anything that can act on the system. Structural, like a TS interface.

    A class satisfies this by *having* an `id` and a `can()`, not by inheriting
    from it - which is what lets the eventual auth code define its own Actor
    without this module and that one knowing about each other.

    The `...` bodies are not placeholders. A Protocol declares shape only.
    """

    @property
    def id(self) -> str:
        """Stable identifier for this actor, stored in audit columns.

        A string, so it survives whatever the eventual provider hands us - a
        UUID, an OIDC `sub` claim, or a synthetic name like "system".
        """
        ...

    def can(self, permission: str) -> bool:
        """Is this actor allowed to perform `permission`?

        Dotted strings - "product.update", "stock.adjust" - matching the
        vocabulary `backend/services/` already checks against, because those are
        the permissions an agent's tool call ultimately needs.
        """
        ...


class SystemActor:
    """An actor with unrestricted permissions. The only implementation today.

    The auth provider decision is deferred (docs/AUTH-PLAN.md). Until it lands,
    `app.py` builds one of these per request and every `can()` returns True, so
    nothing is gated by identity yet. What *is* gated - and this is the
    distinction worth holding onto - is data-changing tool calls, by Gate 19's
    human approval. Approval is not authorization; the agent is currently as
    powerful as whoever can reach the port, which is why that port is loopback.
    """

    def __init__(self, actor_id: str = "system") -> None:
        self._id = actor_id

    @property
    def id(self) -> str:
        """See Actor.id. Defaults to the literal string "system"."""
        return self._id

    def can(self, permission: str) -> bool:
        """Always True. See the class docstring for why that is deliberate."""
        return True

    def __repr__(self) -> str:
        return f"SystemActor(id={self._id!r})"
