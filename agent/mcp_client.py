"""The MCP connection, exposed to Pydantic AI as a toolset.

**Why this is hand-written instead of `pydantic_ai.mcp.MCPToolset`.** Pydantic AI
ships an MCP toolset and using it would be the obvious choice. It is not usable
here, for a reason that is about protocol eras rather than taste:

  - `pydantic-ai-slim[mcp]` 2.24.0 requires `fastmcp-slim[client]>=3.3.0,<4`.
  - `fastmcp-slim` 3.x (`[client]`) requires `mcp>=1.24.0,<2.0`.
  - `fastmcp-slim` 4.0.0b1 does support `mcp>=2.0` - but Pydantic AI's `<4` cap
    puts it out of reach, and it is a beta besides.

So `MCPToolset` is a **legacy-era client**: it speaks the `initialize`-handshake
revisions (2025-11-25 and earlier), because `mcp` 1.x is all it can install. Our
backend runs `mcp==2.0.0`, which is dual-era and would serve it happily - the
2026-07-28 spec's compatibility matrix says *legacy client -> dual-era server*
works, so this would have functioned. It was rejected because it would have
meant the agent talking the old protocol to a server built for the new one, and
the point of pinning 2.0.0 across both halves was to actually use the modern
revision: stateless per-request metadata, no handshake, no protocol-level
session. Adopting `MCPToolset` would have quietly given that up in exchange for
about eighty lines.

**What that decision costs, plainly.** These two methods are now ours to
maintain, and Pydantic AI's own implementation is where bug fixes will land -
task support, structured content, result mapping we do not do. The exit
condition is a Pydantic AI release whose `mcp` extra permits `fastmcp-slim>=4`;
at that point this file should shrink to a `MCPToolset` construction and the
schema normalisation below moved into a `PreparedToolset` wrapper.

**One thing it buys back, which is not a consolation prize.** The `anyOf` schema
normalisation that Gate 15 found to be necessary (docs/AGENT-PLAN.md, finding 2)
has to happen wherever tools are declared to the model. Owning `get_tools()`
puts it exactly there, in the open. Behind `MCPToolset` it would have needed a
wrapper toolset rewriting schemas that the layer below had just built.

**Note on attribute naming.** Pydantic AI's `mcp.py` reads `inputSchema` and
`isError`; those are FastMCP's camelCase types. The raw `mcp` 2.0 SDK we use
here exposes `input_schema` and `is_error`. Reading their source as a reference
and copying the attribute names across is a silent `AttributeError` waiting to
happen - the names below are the ones `scripts/check_mcp.py` verified against a
live server.
"""

from contextlib import AsyncExitStack
from typing import Any, Literal

import httpx2
import pydantic_core
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic_ai import ModelRetry, RunContext, ToolDefinition
from pydantic_ai.toolsets import AbstractToolset, ToolsetTool

from actor import Actor
from auth import get_scoped_token
from config import settings

# Validates tool arguments as "a dict with string keys and any values", i.e. it
# checks the shape and nothing else. The real schema is enforced by the server -
# `@mcp.tool()`'s own pydantic validation - so validating twice here would only
# add a second place for the two to disagree.
#
# Built rather than imported: the equivalent constant lives in
# `pydantic_ai.toolsets.external`, which is not part of the documented API.
_ARGS_VALIDATOR = pydantic_core.SchemaValidator(
    schema=pydantic_core.core_schema.dict_schema(
        pydantic_core.core_schema.str_schema(),
        pydantic_core.core_schema.any_schema(),
    )
)


# The tools that only read. Everything else - now and in future - requires
# human approval before it runs.
#
# **Why this is an allowlist of reads rather than a denylist of writes.**
# docs/AGENT-PLAN.md's Gate 19 names the three mutating tools, and listing
# those three here would have been the literal reading. It fails in the wrong
# direction: a seventh @mcp.tool() added to backend/mcp_server/server.py would
# default to ungated, execute without approval, and nothing would fail or warn.
# Inverted, a new tool is gated until someone deliberately declares it a read,
# and the worst case is one unnecessary confirmation.
#
# This also supplies the safety property that get_tools()'s existing choice
# needs: it asks tools/list on every run rather than caching, specifically so a
# new backend tool appears without a restart here. A new tool appearing
# automatically is only safe if it is also gated automatically.
READ_ONLY = frozenset({"list_products", "get_product", "get_product_by_sku"})


def tool_kind(name: str) -> Literal["function", "unapproved"]:
    """Whether a tool runs freely or waits for a human.

    **`kind="unapproved"` is how Pydantic AI's own `requires_approval=True`
    works one layer down.** That kwarg belongs to FunctionToolset and the
    @agent.tool decorators, and is not reachable from a hand-written
    AbstractToolset like ours - docs/AGENT-PLAN.md's Gate 19 wording named an
    API surface we do not have. It is not a different mechanism, though:
    pydantic_ai/tools.py:506 sets `kind='unapproved' if self.requires_approval
    else 'function'`, and the run graph reads only tool_def.kind
    (_tool_execution.py:627, result.py:1062). Verified against the installed
    2.24.0 source on 2026-08-12.

    A separate function rather than an inline conditional in get_tools() so the
    rule can be tested without a live MCP server, and so tests/ can gate its
    own fake tools through the same function that gates the real ones.
    """
    return "function" if name in READ_ONLY else "unapproved"


def normalise_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Rewrite an MCP input schema into one Gemini handles reliably.

    Gate 15's finding 2: `@mcp.tool()` renders an optional parameter like
    `search: str | None` as `anyOf: [{type: string}, {type: null}]`, in five of
    the six tools. Gemini's function-calling schema handles that unreliably -
    the symptom is a 400 that names a schema rather than a tool, which is why
    `scripts/check_mcp.py` prints the raw shape and flags these.

    Two rewrites, both lossless for our purposes:

      - `anyOf: [X, null]` collapses to `X`. Nothing is lost, because
        optionality is already carried by the parameter's absence from
        `required` - the null branch was a second, redundant encoding of it.
      - pydantic's generated `title` is dropped. It is derived from the field
        name the model already has, so it is noise in the prompt.

    `default` is deliberately kept: it tells the model what happens if it omits
    the argument, which is real information.

    Returns a new dict; the input is not mutated.
    """

    properties: dict[str, Any] = {}

    for name, spec in schema.get("properties", {}).items():
        spec = {k: v for k, v in spec.items() if k != "title"}

        branches = spec.pop("anyOf", None)
        if branches:
            # Only collapse the `X | None` shape. A genuine union of two real
            # types (`str | int`) is not this, and silently picking its first
            # branch would misdeclare the tool - leave those alone and let the
            # 400 be loud rather than the schema be wrong.
            non_null = [b for b in branches if b.get("type") != "null"]
            if len(non_null) == 1:
                spec = {**non_null[0], **spec}
            else:
                spec["anyOf"] = branches

        properties[name] = spec

    return {**schema, "properties": properties}


class ErpToolset(AbstractToolset[Any]):
    """The backend's MCP tools, as a Pydantic AI toolset.

    Owns the client connection: enter it as an async context manager and the
    connection lives for that block. Pydantic AI enters the toolsets registered
    with an agent, so in practice `conversation.py` hands this to `Agent(...)`
    and never calls `__aenter__` itself.

    Takes a URL rather than a `Client` so that nothing above this file imports
    `mcp` - the mirror of `model_provider.py` keeping `pydantic_ai` off
    `config.py` and `scripts/`, the files the Gate 17 `lint-imports` contract
    actually forbids it in. `mcp_client.py` is one of the allowed runtime
    cluster (with `conversation.py` and `model_provider.py`). Both halves of
    the protocol boundary stay in one module each.
    """

    def __init__(self, base_url: str, *, actor: Actor) -> None:
        self._base_url = base_url
        # **Wired through at gate 25**, having been stored and deliberately
        # unused since Gate 20. The note that used to sit here said sending an
        # identity would "invite backend/mcp_server/server.py's `_actor()` to
        # trust an unauthenticated claim" - and that was the right call. What
        # changed is not this file: the MCP server now verifies the token itself
        # against ThunderID's published keys, so what travels below is evidence
        # rather than an assertion. Both ends landed in the same gate, which is
        # what made it safe.
        #
        # A `UserActor` carries the signed-in person's token; a `SystemActor`
        # (AUTH_ENABLED=false) carries nothing and the connection stays
        # anonymous, exactly as it was before this gate.
        self._actor = actor
        self._stack = AsyncExitStack()
        self._client: Client | None = None

    @property
    def id(self) -> str | None:
        """Abstract on the base class, so it is not optional despite the return type.

        A fixed string is right here: there is exactly one ERP behind exactly
        one MCP server, so two instances with different IDs would be two
        connections to the same place.
        """
        return "erp"

    async def __aenter__(self) -> "ErpToolset":
        # `Client(url)` used to be the whole of connecting over Streamable HTTP -
        # no subprocess, no interpreter paths, no cross-venv reach. Compare
        # `scripts/check_mcp.py`, which needs thirty lines to locate and launch
        # the backend over stdio; that gap is the reason AGENT-PLAN chose HTTP
        # for the real agent.
        #
        # Gate 25 makes it two lines instead of one, because `Client(url)` builds
        # its transport with no HTTP client and so has nowhere to put a
        # credential. `streamable_http_client`'s own documentation says
        # authentication is configured by passing a pre-built
        # `httpx2.AsyncClient` - so we build one and hand it over.
        #
        # ⚠️ `httpx2`, not `httpx`. The SDK's signature is explicit about it, and
        # the two packages have separate `Auth` base classes. `agent/auth.py`
        # uses plain `httpx` for the token-endpoint call, which is a different
        # connection to a different host and shares nothing with this one.
        token = await self._scoped_token()

        if token is None:
            # AUTH_ENABLED=false. Anonymous, exactly as before this gate, and
            # matched by `_actor()` on the other end falling back to SystemActor.
            transport = streamable_http_client(self._base_url)
        else:
            # **The one line where a future ID-JAG swap happens.** The SDK ships
            # `IdentityAssertionOAuthProvider`, an `httpx2.Auth` implementing the
            # SEP-990 flow, which drops into this same client. Nothing above this
            # file would change. See docs/AUTH-PLAN.md, "ID-JAG is a parameter,
            # not a second architecture".
            transport = streamable_http_client(
                self._base_url,
                http_client=httpx2.AsyncClient(
                    headers={"Authorization": f"Bearer {token}"}
                ),
            )

        self._client = await self._stack.enter_async_context(Client(transport))
        return self

    async def _scoped_token(self) -> str | None:
        """The token this connection should present, or None to stay anonymous.

        Where "the agent may only do what you can do" actually happens. The
        signed-in person's token goes to ThunderID and a **narrower** one comes
        back: same person, valid only at the MCP server, carrying only the
        permissions this agent is allowed to use. ThunderID cannot return more
        authority than the token it was given, which is why the guarantee holds
        even if this file is wrong.

        Exchanged per connection rather than per call. A connection is one
        conversation turn, tokens live an hour, and exchanging on every tool call
        would put a round trip to the login server in front of every question the
        model asks.
        """
        if not settings.auth_enabled:
            return None

        user_token = getattr(self._actor, "token", None)
        if user_token is None:
            # A SystemActor with auth on. `app.py` does not produce that
            # combination, so reaching here means someone constructed a toolset
            # by hand - a script, a test. Anonymous is the honest answer; the ERP
            # will refuse it, which is the correct outcome rather than a silent
            # escalation.
            return None

        scoped = await get_scoped_token(user_token)
        return scoped.access_token

    async def __aexit__(self, *args: Any) -> bool | None:
        self._client = None
        return await self._stack.__aexit__(*args)

    @property
    def _connected(self) -> Client:
        if self._client is None:
            raise RuntimeError(
                "ErpToolset used before connecting. Register it on an Agent, or "
                "enter it with `async with`, before running a turn."
            )
        return self._client

    async def get_tools(self, ctx: RunContext[Any]) -> dict[str, ToolsetTool[Any]]:
        """Declare the server's tools to the model.

        `tools/list` is asked on every run rather than cached at startup. It is
        one cheap round trip against a server on loopback, and it means adding a
        seventh `@mcp.tool()` to the backend needs no restart here - discovery
        at runtime is the property MCP exists to provide, and caching it away on
        the first turn would trade that for nothing measurable.
        """

        result = await self._connected.list_tools()

        return {
            tool.name: ToolsetTool(
                toolset=self,
                tool_def=ToolDefinition(
                    name=tool.name,
                    description=tool.description,
                    # The docstrings in `mcp_server/server.py` are the entire
                    # basis on which the model picks a tool. Passed through
                    # whole, deliberately: truncating to the first line here
                    # would silently discard the argument documentation the
                    # server treats as interface.
                    parameters_json_schema=normalise_tool_schema(tool.input_schema),
                    # Gate 19: anything not in READ_ONLY stops for human
                    # approval before it runs. See tool_kind's docstring for
                    # why this is `kind=` rather than `requires_approval=True`.
                    kind=tool_kind(tool.name),
                ),
                max_retries=ctx.max_retries,
                args_validator=_ARGS_VALIDATOR,
            )
            for tool in result.tools
        }

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[Any],
        tool: ToolsetTool[Any],
    ) -> Any:
        """Run one tool call and return what the model should see.

        **No approval check on this line.** It is the line where one would go -
        Gate 15's comprehension question 3 - but the approval design uses
        Pydantic AI's `DeferredToolRequests`, which gates the call *before* the
        toolset is reached. A check here would be a second, redundant gate in a
        place `store.py` cannot see, which is the wrong shape.
        """

        result = await self._connected.call_tool(name, tool_args)

        # `mcp_server/errors.py` reports a domain failure - "no product has that
        # SKU" - as a normal result with is_error=True, never a protocol error.
        # Deliberate on MCP's part and it converges with Gemini's own choice
        # (finding 4): both decided a failed tool is information the model reads
        # and recovers from.
        #
        # `ModelRetry` is how that text reaches the model in Pydantic AI, and
        # `max_retries` above is what stops a loop. It is not a perfect fit for
        # every case - a NotFoundError is something to adapt to rather than
        # retry, which is closer to `ToolFailed` - but telling those apart means
        # parsing the message, and the error vocabulary is not currently
        # distinguishable over the wire. Revisit at Gate 19 if the model is seen
        # retrying a lookup that cannot succeed.
        text = "\n".join(
            block.text for block in result.content if getattr(block, "text", None)
        )

        if result.is_error:
            raise ModelRetry(text or f"Tool {name!r} returned an error")

        return text
