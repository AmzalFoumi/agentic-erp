"""Run the agent's HTTP service. Gate 20's equivalent of `uvicorn main:app`.

    python scripts/serve.py

**A script rather than a bare uvicorn command line, for one reason:** the bind
address. `uvicorn app:app --reload` would bind 127.0.0.1 by default, which is
correct today and silent about it - and a default nobody chose is a default
nobody defends. HOST and PORT live in app.py with the comment explaining why,
and this script passes them, so there is no second place where the answer could
differ. See app.py's HOST comment before changing where this binds; it is not a
configuration question.

**The backend must be running** (both halves - the MCP server on 8001 for tools,
and Postgres reachable for persistence). See scripts/check_mcp.py's docstring for
the MCP command.

`--reload` is deliberately off. It watches the filesystem and restarts on a save,
which would silently drop a turn mid-stream; with a real conversation open in a
browser that reads as the agent breaking rather than as the server restarting.
Restart by hand.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402  (must follow the sys.path line above)

from app import HOST, PORT  # noqa: E402


def main() -> None:
    print(f"agent service on http://{HOST}:{PORT}")
    print("  GET  /health")
    print("  POST /conversations")
    print("  GET  /conversations/{id}")
    print("  POST /conversations/{id}/turns   (streams)")
    print()

    # The import string "app:app" rather than the imported object, so uvicorn's
    # own startup logging and lifespan handling behave the way its documentation
    # describes. sys.path already has agent/ on it from above, which is what
    # makes the bare module name resolve.
    uvicorn.run("app:app", host=HOST, port=PORT)


if __name__ == "__main__":
    main()
