"""What a draft is allowed to be, and what approving one actually does.

### The threat this file removes

The feature set this gate implements was specified outside this repository, and
it had the draft payload carry "target service function names and arguments".
That reads as flexible and is a remote-code-execution shape: if the executor
resolves a function from a string held in a database row, then anyone who can
write a row - the agent, a bug, a stolen token, a manager editing a payload in
the browser - can call anything in this codebase with anything.

So a draft names a **type**, and a type is looked up in a registry that only
this application's own source code can add to. A type nobody registered does
not exist and cannot run. The worst a hostile row can do is name a type that is
refused.

### Why Pydantic is allowed in services/

`services/` is barred from importing fastapi, starlette, mcp, uvicorn, httpx
and jwt - the web frameworks and the transport credential. Pydantic is none of
those. It is a validation library with no web concepts, `core/config.py`
already depends on it, and `lint-imports` confirms rather than merely tolerates
this: the forbidden list is explicit, and pydantic is not on it. Using it here
means a payload's shape is declared once, in the same language as the rest of
the domain, instead of being restated in each adapter.

### Registration happens at import time

Each feature gate registers its own type from its own module - gate 28 will
register BATCH_PRICE_MARKDOWN from services/spoilage.py - and importing that
module is what runs the registration.

**Gate 27 deliberately registers nothing.** The engine ships empty and the
first real type arrives with the first real feature. That means the approval
queue is empty until gate 28 lands, which is correct: an engine and its first
user are separate deliverables, and shipping a draft type here would mean
writing a handler for a feature that does not exist yet.
"""

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from core.actor import Actor
from core.enums import ClientType
from core.exceptions import ValidationError

# What a handler is.
#
# It receives an already-validated payload *object*, never a raw dict, so a
# handler never has to ask whether a field is present or what type it is - that
# question was settled before it was called.
#
# It returns None. A handler's effect is the rows it writes; the draft row
# itself is updated by services/drafts.py, not by the handler. A return value
# would only invite callers to start depending on one.
DraftHandler = Callable[[Session, Actor, ClientType, BaseModel], None]


@dataclass(frozen=True)
class DraftTypeSpec:
    """The two things a draft type is: a shape, and something that runs it.

    `frozen=True` makes instances immutable, so a spec handed out by
    `spec_for()` cannot be mutated in place by whatever received it - the
    registry cannot be rewritten through a reference it gave away.
    """

    schema: type[BaseModel]
    handler: DraftHandler


# Module-level, and deliberately private. The only supported way in is
# `register()`, which refuses to overwrite.
_REGISTRY: dict[str, DraftTypeSpec] = {}


def register(
    draft_type: str, *, schema: type[BaseModel], handler: DraftHandler
) -> None:
    """Add a draft type. Refuses to replace one that already exists.

    The refusal matters more than it looks. Registration happens as a side
    effect of importing a module, and import order is not something anyone
    reasons about carefully. A silent overwrite would mean the handler that
    actually runs depends on which module happened to be imported last - so a
    second registration under the same name is a programming error, and is
    raised as one at startup rather than discovered in production.
    """
    if draft_type in _REGISTRY:
        raise ValidationError(f"Draft type {draft_type!r} is already registered.")
    _REGISTRY[draft_type] = DraftTypeSpec(schema=schema, handler=handler)


def registered_types() -> frozenset[str]:
    """Every draft type this build knows about. For diagnostics and tests.

    A frozenset rather than the live dict's keys, so a caller cannot iterate it
    while something else registers, and cannot mutate the registry through it.
    """
    return frozenset(_REGISTRY)


def spec_for(draft_type: str) -> DraftTypeSpec:
    """The schema and handler for `draft_type`, or raise.

    ⚠️ The error names the type that was asked for and does NOT list the ones
    that exist. Enumerating the valid set in an error handed back to a caller
    is a map for whoever is probing - the same reasoning that makes gate 24's
    authentication failures refuse to say *why* they failed.
    """
    spec = _REGISTRY.get(draft_type)
    if spec is None:
        raise ValidationError(f"Unknown draft type {draft_type!r}.")
    return spec


def validate_payload(draft_type: str, payload: dict) -> BaseModel:
    """Check `payload` against `draft_type`'s schema and return the parsed object.

    Called twice in a draft's life, and **the second call is the important
    one**: once when the draft is created, and again when it is approved,
    because `approve_draft` lets a manager edit the payload in between.
    Validating only on the way in would mean the schema guarded the agent and
    never the browser - and the browser is the one place a human can type
    anything at all.

    Pydantic's own ValidationError is caught and re-raised as ours. Letting it
    escape would put a third-party exception type into the vocabulary that
    `api/errors.py` and `mcp_server/errors.py` translate, and neither adapter
    has a handler for it - so a bad payload would surface as an unhandled 500
    instead of a 400 telling the caller what to fix.

    The message reports how many problems there were and not what they were.
    Pydantic's detail names field paths and the values it received, and this
    string reaches an API client; the count is enough for a human to know the
    shape is wrong without echoing input back out.
    """
    spec = spec_for(draft_type)
    try:
        return spec.schema.model_validate(payload)
    except PydanticValidationError as exc:
        raise ValidationError(
            f"Payload does not match the shape of {draft_type!r}: "
            f"{exc.error_count()} problem(s)."
        ) from exc
