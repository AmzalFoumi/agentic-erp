"""Turning domain exceptions into something an AI agent can act on.

The counterpart of `api/errors.py`. Same job - translate `core/exceptions.py`
into one adapter's dialect - but the dialect is unrecognisable, because the
audience is different. HTTP errors are read by a programmer who wrote the call
months ago; these are read by a model deciding what to do in the next second.

### The two error channels MCP has, and why we only use one

Verified against the installed SDK (mcp 2.0.0, `server/mcpserver/server.py` and
`tools/base.py`) rather than assumed, because getting this backwards is silent:

1. **A JSON-RPC protocol error** - raised by throwing `MCPError`, which carries
   a numeric code. The SDK re-raises these untouched. This says *the protocol
   failed*: malformed request, unknown method, bad parameters. It is reported to
   the **client** - the program running the model - and the model may never see
   it at all.

2. **`CallToolResult(isError=True)`** - what any other exception becomes. This
   says *the tool ran and could not do the job*. It is delivered to the **model**
   as the tool's output, so the model reads it and chooses what to do next.

**Everything in this file uses channel 2, deliberately.** "No product with id 5"
is not a protocol failure - the request was perfectly well formed, the machinery
worked exactly as designed, and the answer is simply no. Reaching for an
`MCPError` code there would be the same mistake as returning HTTP 422 for a
business rule: borrowing the framework's vocabulary for something the framework
did not say, so that afterwards nobody can tell the two apart. The JSON-RPC
error range stays entirely the SDK's.

### Why this file exists at all, given the SDK already catches exceptions

Left alone, the SDK turns *every* uncaught exception into the same shape:
`isError=True` with the text `f"Error executing tool {name}: {e}"`. That is a
sensible default and it is not sufficient here, for two reasons.

**One: a model cannot tell the two kinds of failure apart.** "You asked for a
product that does not exist" and "the database is unreachable" arrive looking
identical. The first should make the model change its input and try something
else; the second should make it stop. Undifferentiated, a model will retry
against a dead database until something times out - and retrying is exactly what
models do when a tool fails without saying otherwise.

**Two: `str(e)` on an infrastructure exception leaks.** A SQLAlchemy
`OperationalError` stringifies to the failing statement and connection details -
which, with our Supabase URL, can include the host and user. Passing that
straight to a language model puts it in the model's context, in the client's
logs, and quite possibly in a provider's telemetry. The generic message for
unexpected errors below is a privacy control, not tidiness.

### The house style for these messages

Each message says three things in order: **what happened**, **why**, and **what
to do next**. The third is the one that gets skipped and the one that matters.
"No product with id 5" leaves a model free to try id 6; "no product with id 5,
search with list_products rather than guessing another id" does not.
"""

from __future__ import annotations

import sys
import traceback
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from mcp.server.mcpserver.exceptions import ToolError

from core.exceptions import (
    DomainError,
    DuplicateError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

F = TypeVar("F", bound=Callable[..., Any])

# What to append to each domain error's own message. The service already says
# what went wrong in words a person can read - these add the instruction the
# model needs and the service has no business knowing about.
#
# A dict keyed by exception class, mirroring `api/errors.py` mapping the same
# classes to status codes. Convergent structure, from having the same problem.
_GUIDANCE: dict[type[DomainError], str] = {
    NotFoundError: (
        "Search for it with list_products instead of guessing another id or SKU. "
        "If it genuinely does not exist, say so rather than creating it, unless "
        "you were asked to add it."
    ),
    DuplicateError: (
        "The product already exists. Look it up with get_product_by_sku and "
        "update or restock that one instead of creating a second record - a "
        "duplicate splits one product's stock across two rows."
    ),
    ValidationError: (
        "This is a business rule, not a typo in the protocol. Re-read the "
        "message, correct the value, and try once more. Do not retry the same "
        "arguments - the result will be the same."
    ),
    PermissionDeniedError: (
        "This is a permissions decision, so retrying will not help and neither "
        "will another tool. Tell the user they are not allowed to do this."
    ),
}


def translated(fn: F) -> F:
    """Convert exceptions escaping a tool into messages written for a model.

    Applied *underneath* `@mcp.tool()`, so the decorator order reads:

        @mcp.tool()
        @translated
        def get_product(product_id: int) -> dict[str, Any]:

    Order matters and is not arbitrary. Decorators apply bottom-up, so
    `translated` wraps the raw function first and `mcp.tool()` registers the
    wrapped version - which is what we want, because the registration is what
    ends up being called. Reversed, `mcp.tool()` would register the untranslated
    function and this would never run.

    `functools.wraps` is load-bearing rather than good manners. `@mcp.tool()`
    builds the tool's input schema by inspecting the signature and its
    description from `__doc__`. Without `wraps`, every tool would register as
    `wrapper(*args, **kwargs)` with no docstring - six identically useless
    tools, and no error to say so. (`wraps` also sets `__wrapped__`, which is
    how `inspect.signature` sees through to the real parameters.)
    """

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except DomainError as exc:
            # A rule we wrote, doing its job. The message is already meant for
            # a reader; append the instruction for this particular reader.
            guidance = _GUIDANCE.get(type(exc), "")
            raise ToolError(f"{exc} {guidance}".strip()) from exc
        except Exception as exc:
            # Anything else is our bug or our infrastructure, and the model can
            # do nothing useful about either.
            #
            # The detail goes to **stderr**, never stdout: under stdio transport
            # stdout is the JSON-RPC stream itself, and a traceback printed
            # there corrupts the message frame and drops the connection. stderr
            # is free, and is where the client shows server logs.
            print(
                f"[mcp] unhandled {type(exc).__name__} in {fn.__name__}:",
                file=sys.stderr,
            )
            traceback.print_exc(file=sys.stderr)

            # Deliberately says nothing about what went wrong. See the module
            # docstring: `str(exc)` here can carry database credentials.
            raise ToolError(
                "The inventory system failed to handle this request. This is a "
                "fault in the system, not in your request, so retrying it or "
                "rewording it will not help. Tell the user the inventory system "
                "is unavailable and stop."
            ) from exc

    return wrapper  # type: ignore[return-value]
