"""Diagnostic: exercise the MCP tools with no model involved.

**What this is for.** When the agent misbehaves, the first question is whether
the fault is in the tools or in the model and loop above them. This script
answers it: it connects to the backend's MCP server, lists the tools, and calls
one - with no Gemini, no Pydantic AI, and no agent code in the path.

If this passes and the agent still fails, the tools are not why. That halves the
search space without guessing, which is the whole reason it is kept.

**It also prints the schema the model actually receives.** `@mcp.tool()` renders
an optional parameter like `search: str | None` as a union of string and null,
which Gemini's function-calling schema handles unreliably - so `agent/`
normalises tool schemas before declaring them (`mcp_client.py`). Seeing the raw
shape here is how you diagnose a 400 that names a schema rather than a tool.

**Rewritten at Gate 16.** The previous version launched the backend as a child
process over stdio, which meant locating `backend/.venv/Scripts/python.exe` and
setting a working directory - thirty lines in which this script knew another
component's interpreter layout, for two services meant to share nothing but a
protocol. `backend/mcp_server/server.py` now has a Streamable HTTP mode, so all
of that is one URL. The deleted block is worth remembering as the concrete
argument for the transport choice in docs/AGENT-PLAN.md.

**The backend must already be running.** Two terminals:

    # terminal 1, from backend/ with its venv active
    python -m mcp_server.server --transport streamable-http

    # terminal 2, from agent/ with its venv active
    python scripts/check_mcp.py

A refused connection means terminal 1 is not up, or is on a different port than
`MCP_BASE_URL` in agent/.env.
"""

import asyncio
import sys
from pathlib import Path

from mcp.client import Client

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402  (must follow the sys.path line above)


async def main() -> None:
    print(f"connecting to {settings.mcp_base_url}")
    print()

    # This is the whole of connecting over Streamable HTTP: the URL selects the
    # transport inside the SDK. Compare `ErpToolset.__aenter__`, which is the
    # same line - deliberately, so that what this script proves is what the
    # agent actually does.
    try:
        async with Client(settings.mcp_base_url) as client:
            print(f"connected. protocol version: {client.protocol_version}")
            print()

            # tools/list is runtime discovery, not configuration. Add a seventh
            # @mcp.tool() to server.py and it appears here with no change.
            tools_result = await client.list_tools()

            print(f"=== {len(tools_result.tools)} tools ===")
            print()
            for tool in tools_result.tools:
                print(f"  {tool.name}")
                # First line of the docstring from server.py. These descriptions
                # are the entire basis on which a model chooses a tool, which is
                # why server.py treats them as interface rather than comment.
                print(f"    {(tool.description or '').strip().splitlines()[0]}")

                schema = tool.input_schema
                required = schema.get("required", [])
                for name, spec in schema.get("properties", {}).items():
                    marker = "*" if name in required else " "
                    if "anyOf" in spec:
                        kinds = "|".join(opt.get("type", "?") for opt in spec["anyOf"])
                        print(f"    {marker} {name}: anyOf[{kinds}]  <-- normalised")
                    else:
                        print(f"    {marker} {name}: {spec.get('type', '?')}")
                print()

            print("  (* = required)")
            print()

            # tools/call. Note who is choosing: we are. The name is a literal
            # string and the arguments a literal dict - in the agent both come
            # out of a function call the model produced, and this line is
            # otherwise the same.
            print("=== list_products(limit=5) ===")
            result = await client.call_tool("list_products", {"limit": 5})

            # A failing tool - "no product has that SKU" - comes back as a
            # normal result with is_error=True and the message in `content`, NOT
            # as a protocol error. Deliberate on MCP's part: a tool failure is
            # information the model should read and recover from, so it has to
            # travel back as content. `backend/mcp_server/errors.py` is the
            # layer that makes that translation.
            print(f"is_error: {result.is_error}")
            print()

            for block in result.content:
                text = getattr(block, "text", None)
                if text is not None:
                    print(text)

    except OSError as exc:
        # Narrowed to OSError on purpose: this catch is for "nothing is
        # listening", not for a protocol or tool failure. Swallowing those would
        # turn the diagnostic into a script that hides the thing it exists to
        # show.
        raise SystemExit(
            f"\nCould not reach {settings.mcp_base_url} ({exc}).\n\n"
            "Start the server first, from backend/ with its venv active:\n"
            "    python -m mcp_server.server --transport streamable-http\n\n"
            "If it is running, check the port and path match MCP_BASE_URL in "
            "agent/.env."
        ) from exc

    print()
    print("No model was involved - that was a program calling a program.")
    print("If the agent misbehaves and this passed, the tools are not why.")


asyncio.run(main())
