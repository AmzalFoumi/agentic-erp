"""Who is asking. The identity abstraction every service function depends on.

Every real operation has an implicit "who": not just *a product was created*,
but *Fatima created this product at 14:32*. That matters for authorization
(may this person do this?) and for audit (the created_by / updated_by columns
on every table).

The design question is where "who" comes from. In a Nest app you would reach
for `@Req() req` and read `req.user`, populated by a guard. Convenient - and
fatal here. The instant `services/products.py` knows what a request is, it is
welded to HTTP and the MCP server cannot reuse it.

So identity is a **parameter**, not ambient state. Every service function takes
`session` first and `actor` second. Each adapter builds an Actor from whatever
it happens to have - FastAPI from a validated JWT, the MCP server from
per-request metadata - and passes it down. Services never learn where it came
from, which is exactly the point.

This also lines up with MCP 2026-07-28, which removed the `initialize`
handshake and protocol-level sessions: a server can no longer establish "this
client is Fatima" once and remember it. Identity now arrives with every call.
Passing an Actor per call is not just our preference; it is the shape the
protocol requires.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Actor(Protocol):
    """Anything that can act on the system.

    `Protocol` is Python's structural typing - the TypeScript `interface` you
    already know. A class satisfies this by *having* an `id` and a `can()`, not
    by inheriting from it and not by importing it. That matters: an adapter can
    define its own Actor without `core` and the adapter knowing about each
    other, which keeps the dependency arrow pointing one way.

    (`@runtime_checkable` additionally allows `isinstance(x, Actor)`. It only
    checks that the attributes exist, not their signatures - useful for a
    sanity assert, not a substitute for a type checker.)

    The `...` bodies below are not placeholders to fill in later. A Protocol
    declares shape only; there is deliberately no implementation here.
    """

    @property
    def id(self) -> str:
        """Stable identifier for this actor, stored in audit columns.

        A string rather than an int because it has to survive whatever the
        eventual auth provider hands us - a UUID, an OIDC `sub` claim, or a
        synthetic name like "system".
        """
        ...

    def can(self, permission: str) -> bool:
        """Is this actor allowed to perform `permission`?

        Permissions are dotted strings - "product.create", "product.update",
        "stock.adjust". Plain strings rather than an enum on purpose: the real
        permission set will come from the auth provider, and hardcoding an enum
        now would mean rewriting every call site when it arrives.
        """
        ...


class SystemActor:
    """An actor with unrestricted permissions. The only implementation today.

    The authentication provider decision is deliberately deferred (see
    docs/AUTH-PLAN.md). Until it lands, adapters pass a SystemActor and every
    `can()` returns True, so nothing is actually gated yet.

    Two things are true at once, and both matter:

      - Nothing is enforced today. This grants everything.
      - Every service is already *written* as though it were, with the
        permission check and the audit stamp in place.

    That is the whole value of doing this now. Swapping SystemActor for a real
    implementation later changes this file and the two adapters, and touches
    nothing in `services/` - because the call sites already exist. Retrofitting
    an actor argument into thirty finished service functions is the expensive
    version of this work, and this is how we avoid it.
    """

    def __init__(self, actor_id: str = "system") -> None:
        # A single leading underscore is Python's convention for "internal,
        # please do not touch from outside". It is a convention only - nothing
        # prevents access, unlike TypeScript's `private`. The public read-only
        # view is the `id` property below.
        self._id = actor_id

    @property
    def id(self) -> str:
        """See Actor.id. Defaults to the literal string "system"."""
        return self._id

    def can(self, permission: str) -> bool:
        """Always True. See the class docstring for why that is deliberate."""
        return True

    def __repr__(self) -> str:
        # `__repr__` is what appears in a debugger, a REPL, or a failing pytest
        # assertion. Without it you get the useless default
        # `<core.actor.SystemActor object at 0x000001F8...>`.
        return f"SystemActor(id={self._id!r})"


class TokenActor:
    """A real person or agent, described by a validated access token.

    The implementation the whole Actor design was built for. Where SystemActor
    grants everything, this grants exactly what the token's `scope` claim says
    and nothing else.

    Two claims from the token matter here, and they map onto the protocol
    without translation:

        sub    -> id       the OIDC subject, e.g. "01a02d8f-0355-74cd-..."
        scope  -> scopes   space-delimited, e.g. "openid product.read ..."

    `can()` is therefore a set-membership test with no mapping table. That is
    not a happy accident: the ThunderID resource server was registered with
    `.` as its permission delimiter precisely so that its strings come out
    identical to the ones already written in services/ - `product.read`,
    `stock.adjust`. Accepting the `:` default would have meant maintaining a
    translation layer forever, and the delimiter cannot be changed after the
    resource server is created. See docs/AUTH-PLAN.md.

    Note this class does no validating. It is handed claims that have *already*
    been verified - signature, issuer, audience, expiry - by `authn/tokens.py`.
    Keeping it dumb is deliberate: `core/` must not grow a JWT dependency, and
    a class that only stores two fields is trivially constructible in a test.

    ⚠️ An empty `scopes` is a legitimate, dangerous state. ThunderID answers a
    request for permissions it does not recognise with `200 OK` and a token
    carrying no scope claim at all - indistinguishable from a correctly issued
    token for a user with no permissions. Such an actor authenticates fine and
    is refused by every `can()`. If everything 403s, suspect the token before
    the code.
    """

    def __init__(self, actor_id: str, scopes: frozenset[str]) -> None:
        self._id = actor_id
        self._scopes = scopes

    @property
    def id(self) -> str:
        """See Actor.id. The OIDC `sub` claim, stored in created_by/updated_by."""
        return self._id

    @property
    def scopes(self) -> frozenset[str]:
        """The permissions this token carries. Read-only view for diagnostics."""
        return self._scopes

    def can(self, permission: str) -> bool:
        """True when the token's scope claim contains `permission` exactly.

        No prefix matching and no hierarchy: `product.read` does not imply
        `product.create`, and holding `product` alone grants nothing. The
        issuer decides what the permission set means; we only check membership.
        """
        return permission in self._scopes

    def __repr__(self) -> str:
        # Scopes are sorted so the repr is stable across runs - a frozenset's
        # iteration order is not guaranteed, and an unstable repr makes test
        # failures harder to read than they need to be.
        return f"TokenActor(id={self._id!r}, scopes={sorted(self._scopes)!r})"
