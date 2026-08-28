"""Checks every service performs before it does anything.

### Why this file exists

`_require` started life as a private four-line helper inside
`services/products.py`, with a comment saying that a second copy would be fine
and a third should be extracted. `services/drafts.py` was the second copy, and
gates 28-30 add four more services - so the third, fourth and fifth were
already visible on the roadmap.

Six copies of a permission check is not a style problem. It is six places where
the error message can drift apart, and six places somebody has to remember to
change if the check ever grows a second clause. A caller reading
"Actor 'x' is not allowed to..." should get the same sentence whichever service
refused them.

### Why it is not in core/

`core/` holds what the *data* is - the models, the exception vocabulary, the
Actor protocol. This is a rule about how services behave, and services are the
only layer allowed to have those. Putting it in `core/` would invite an adapter
to import it and start making authorization decisions of its own, which is the
one thing the Actor design exists to prevent.
"""

from core.actor import Actor
from core.exceptions import PermissionDeniedError


def require_permission(actor: Actor, permission: str) -> None:
    """Raise PermissionDeniedError unless `actor` holds `permission`.

    Every service function that reads or writes calls this first, before
    touching the session. That ordering is deliberate: a refused caller should
    not cause a query, both because it is wasted work and because a query that
    runs before the check is one refactor away from being a query whose result
    leaks.

    The message names the actor and the permission and nothing else. It does
    not say which permissions the actor *does* hold, and it does not name the
    resource - the same reasoning as gate 24's authentication failures, which
    refuse to explain themselves so that nobody can use the API to survey our
    setup.

    ⚠️ Remember that an empty permission set is a legitimate state here, not a
    broken one. ThunderID answers a request for a permission it does not
    recognise with a valid token carrying no scope claim at all, so a
    misspelled permission in configuration produces an actor that authenticates
    perfectly and is refused by every call to this function. If everything is
    suddenly 403, suspect the token before the code. See docs/AUTH-PLAN.md.
    """
    if not actor.can(permission):
        raise PermissionDeniedError(
            f"Actor {actor.id!r} is not allowed to perform {permission!r}."
        )
