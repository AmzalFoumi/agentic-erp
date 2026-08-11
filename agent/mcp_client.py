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
from typing import Any

import pydantic_core
from mcp.client import Client
from pydantic_ai import ModelRetry, RunContext, ToolDefinition
from pydantic_ai.toolsets import AbstractToolset, ToolsetTool

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
    `store.py` and `app.py`. Both halves of the protocol boundary stay in one
    module each.
    """

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url
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
        # `Client(url)` is the whole of connecting over Streamable HTTP - no
        # subprocess, no interpreter paths, no cross-venv reach. Compare
        # `scripts/check_mcp.py`, which needs thirty lines to locate and launch
        # the backend over stdio; that gap is the reason AGENT-PLAN chose HTTP
        # for the real agent.
        self._client = await self._stack.enter_async_context(Client(self._base_url))
        return self

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
