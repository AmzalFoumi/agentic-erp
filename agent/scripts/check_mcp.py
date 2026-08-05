"""Diagnostic: exercise the MCP tools with no model involved.

**What this is for.** When the agent misbehaves, the first question is whether
the fault is in the tools or in the model and loop above them. This script
answers it: it connects to `backend/mcp_server/server.py`, lists the tools, and
calls one - with no Gemini, no Pydantic AI, and no agent code in the path.

If this passes and the agent still fails, the tools are not why. That halves the
search space without guessing, which is the whole reason it is kept.

**It also prints the schema the model actually receives.** `@mcp.tool()` renders
an optional parameter like `search: str | None` as a union of string and null,
which Gemini's function-calling schema handles unreliably - so `agent/`
normalises tool schemas before declaring them. Seeing the raw shape here is how
you diagnose a 400 that names a schema rather than a tool.

Run it (from agent/, venv active). The backend does not need to be running -
this starts it as a child process:

    python scripts/check_mcp.py
"""

import asyncio
import sys
from pathlib import Path

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402  (must follow the sys.path line above)

# ---------------------------------------------------------------------------
# Locating the backend.
# ---------------------------------------------------------------------------
#
# stdio transport means *we* start the server as a child process and talk to it
# over its stdin/stdout, so we need the path to the backend's own Python - not
# ours. The two venvs hold different packages, and the server needs sqlalchemy
# and psycopg, neither of which is installed in agent/.
#
# This block is the concrete reason docs/AGENT-PLAN.md chose HTTP over stdio for
# the real agent: it reaches across a directory boundary and hardcodes another
# component's interpreter layout, for two services meant to share nothing but a
# protocol.
#
# **Replace it at Gate 16**, once `mcp_server/server.py` has an HTTP run mode.
# Everything below collapses into `Client(settings.mcp_base_url)` and this
# script stops knowing anything about the backend beyond a URL.
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"

if sys.platform == "win32":
    BACKEND_PYTHON = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
else:
    BACKEND_PYTHON = BACKEND_DIR / ".venv" / "bin" / "python"

if not BACKEND_PYTHON.exists():
    raise SystemExit(
        f"Cannot find the backend's Python at {BACKEND_PYTHON}.\n"
        "This script starts the MCP server as a child process using the "
        "BACKEND's venv (it needs sqlalchemy and psycopg, which agent/ does "
        "not have). Create it with, from backend/:\n"
        "    python -m venv .venv\n"
        "    source .venv/Scripts/activate\n"
        "    pip install -r requirements.txt"
    )


async def main() -> None:
    # `cwd=BACKEND_DIR` is load-bearing. `python -m mcp_server.server` resolves
    # `mcp_server` relative to where the process starts, and the server also has
    # to find `backend/.env` for DATABASE_URL. Run it from the wrong directory
    # and you get an import error or a missing-settings error, neither of which
    # mentions the working directory.
    server_params = StdioServerParameters(
        command=str(BACKEND_PYTHON),
        args=["-m", "mcp_server.server"],
        cwd=str(BACKEND_DIR),
    )

    print(f"starting: {BACKEND_PYTHON} -m mcp_server.server")
    print(f"     cwd: {BACKEND_DIR}")
    print()

    # `stdio_client(...)` is called but NOT entered - it has no `async with` of
    # its own. `Client` enters it on its own exit stack, so the client owns the
    # subprocess lifetime and shuts it down when the session ends.
    #
    # Entering it here and passing the result reads as more careful and is
    # wrong: you get a tuple of streams, and the failure is
    # `TypeError: 'builtins.tuple' object does not support the asynchronous
    # context manager protocol`, which names neither MCP nor stdio.
    async with Client(stdio_client(server_params)) as client:
        print(f"connected. protocol version: {client.protocol_version}")
        print()

        # tools/list is runtime discovery, not configuration. Add a seventh
        # @mcp.tool() to server.py and it appears here with no change.
        tools_result = await client.list_tools()

        print(f"=== {len(tools_result.tools)} tools ===")
        print()
        for tool in tools_result.tools:
            print(f"  {tool.name}")
            # First line of the docstring from server.py. These descriptions are
            # the entire basis on which a model chooses a tool, which is why
            # server.py treats them as interface rather than comment.
            print(f"    {(tool.description or '').strip().splitlines()[0]}")

            schema = tool.input_schema
            required = schema.get("required", [])
            for name, spec in schema.get("properties", {}).items():
                marker = "*" if name in required else " "
                if "anyOf" in spec:
                    kinds = "|".join(opt.get("type", "?") for opt in spec["anyOf"])
                    print(f"    {marker} {name}: anyOf[{kinds}]  <-- needs flattening")
                else:
                    print(f"    {marker} {name}: {spec.get('type', '?')}")
            print()

        print("  (* = required)")
        print()

        # tools/call. Note who is choosing: we are. The name is a literal string
        # and the arguments a literal dict - in the agent both come out of a
        # function call the model produced, and this line is otherwise the same.
        print("=== list_products(limit=5) ===")
        result = await client.call_tool("list_products", {"limit": 5})

        # A failing tool - "no product has that SKU" - comes back as a normal
        # result with is_error=True and the message in `content`, NOT as a
        # protocol error. Deliberate on MCP's part: a tool failure is
        # information the model should read and recover from, so it has to
        # travel back as content. `backend/mcp_server/errors.py` is the layer
        # that makes that translation.
        print(f"is_error: {result.is_error}")
        print()

        for block in result.content:
            text = getattr(block, "text", None)
            if text is not None:
                print(text)

    print()
    print("No model was involved - that was a program calling a program.")
    print("If the agent misbehaves and this passed, the tools are not why.")
    print(f"(the agent itself will use {settings.mcp_base_url} from Gate 16)")


asyncio.run(main())
