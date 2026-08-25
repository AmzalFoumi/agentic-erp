"""How the MCP connection is built, and what must not silently fall off it.

One test, guarding one regression. Gate 25 started handing
`streamable_http_client` a pre-built `httpx2.AsyncClient`, because that is the
SDK's documented seam for attaching a credential. Doing so has a consequence the
SDK does not warn about: when a client is supplied, the SDK does **not** call
`create_mcp_http_client()`, so its recommended timeouts never apply and httpx's
own 5-seconds-for-everything default takes over instead.

An MCP call is a long phone call, not a knock at the door - the agent connects
and then waits while the model thinks and tools run - so a 5-second read timeout
severs any turn lasting longer than that. It went unnoticed for a day and was
found by CodeRabbit on PR #30. This test exists so it cannot go unnoticed twice.
"""

import sys
from pathlib import Path

import httpx2
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mcp_client as mcp_client_module  # noqa: E402
from actor import UserActor  # noqa: E402
from mcp_client import ErpToolset  # noqa: E402


async def test_the_authenticated_client_keeps_the_mcp_read_timeout(monkeypatch):
    """The supplied client must carry the SDK's recommended timeouts.

    Values checked against `mcp/shared/_httpx_utils.py::create_mcp_http_client`
    in mcp 2.0.0: 30s connect/write/pool, 300s read for long-lived streams. The
    read timeout is the one that matters - it is what a slow agent turn spends
    its time in - so it is asserted by value rather than merely "not the
    default".
    """
    built: list[httpx2.AsyncClient] = []
    real_client = httpx2.AsyncClient

    def _record(**kwargs):
        client = real_client(**kwargs)
        built.append(client)
        return client

    monkeypatch.setattr(mcp_client_module.httpx2, "AsyncClient", _record)
    monkeypatch.setattr(mcp_client_module.settings, "auth_enabled", True)

    async def _fake_exchange(user_token, **_kwargs):
        from auth import ScopedToken

        return ScopedToken(access_token="scoped", scopes=frozenset({"product.read"}))

    monkeypatch.setattr(mcp_client_module, "get_scoped_token", _fake_exchange)

    # Connecting for real would need a running MCP server. Only the client
    # construction above is under test, so the transport is stubbed and the
    # resulting failure ignored - `built` is filled by then either way.
    monkeypatch.setattr(
        mcp_client_module,
        "streamable_http_client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("stop here")),
    )

    toolset = ErpToolset(
        "http://127.0.0.1:8001/mcp",
        actor=UserActor("user-token", actor_id="someone"),
    )
    with pytest.raises(RuntimeError):
        await toolset.__aenter__()

    assert built, "no httpx client was built - the test's seam is wrong"
    timeout = built[0].timeout
    assert timeout.read == 300.0, (
        f"read timeout is {timeout.read}, not the SDK's 300s - a long agent "
        "turn would be cut off mid-call"
    )
    assert timeout.connect == 30.0

    for client in built:
        await client.aclose()
