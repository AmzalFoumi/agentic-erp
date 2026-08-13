"""Which tools need approval - the fail-closed rule, tested directly.

`get_tools()` cannot be called without a live MCP server, so the decision it
makes is extracted into `tool_kind()` and tested here. The turn-level
consequence of that decision - a turn actually pausing - is test_approval.py.
"""

from mcp_client import READ_ONLY, tool_kind


def test_read_tools_are_not_gated() -> None:
    """The three read tools run without approval.

    Gating reads would make the future agent panel unusable and protects
    nothing - see docs/AGENT-PLAN.md's Gate 19 section.
    """
    for name in ("list_products", "get_product", "get_product_by_sku"):
        assert tool_kind(name) == "function", name


def test_mutating_tools_are_gated() -> None:
    """The three tools that change data require approval."""
    for name in ("create_product", "update_product", "adjust_stock"):
        assert tool_kind(name) == "unapproved", name


def test_an_unknown_tool_is_gated() -> None:
    """**The reason the rule is an allowlist of reads, not a denylist of writes.**

    `delete_product` does not exist in backend/mcp_server/server.py today. If
    someone adds it - or any other data-changing tool - it must be gated by
    default, without anyone remembering to come back and edit this file. The
    cost of the allowlist being wrong is one unnecessary approval prompt; the
    cost of a denylist being wrong is a new mutating tool executing with no
    human check and nothing failing to indicate it.
    """
    assert tool_kind("delete_product") == "unapproved"
    assert tool_kind("drop_everything") == "unapproved"


def test_read_only_holds_exactly_the_three_read_tools() -> None:
    """Pins the contents of the allowlist.

    This is the one test that fails if someone widens READ_ONLY, which is the
    only edit that can quietly un-gate a mutating tool.
    """
    assert READ_ONLY == {"list_products", "get_product", "get_product_by_sku"}
