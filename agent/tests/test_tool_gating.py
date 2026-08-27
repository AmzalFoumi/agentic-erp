"""Which tools need approval - the fail-closed rule, tested directly.

`get_tools()` cannot be called without a live MCP server, so the decision it
makes is extracted into `tool_kind()` and tested here. The turn-level
consequence of that decision - a turn actually pausing - is test_approval.py.
"""

from mcp_client import READ_ONLY, STAGING_ONLY, tool_kind


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


def test_staging_tools_run_without_an_in_conversation_prompt() -> None:
    """Gate 27. A draft changes nothing operational, so proposing one is free.

    The human approval did not disappear - it moved to /approvals, where the
    whole proposal can be read and edited before it runs. Interrupting the
    conversation to confirm "may I write down a suggestion?" would be a prompt
    with no decision behind it. See docs/FEATURES-PLAN.md, decision 1.
    """
    for name in ("create_action_draft", "list_pending_drafts"):
        assert tool_kind(name) == "function", name


def test_staging_only_holds_exactly_the_two_draft_tools() -> None:
    """Pins the second allowlist, for the same reason the first one is pinned.

    STAGING_ONLY is now the other edit that can quietly un-gate a mutating
    tool, and it is the more tempting one: its name suggests "things that are
    nearly safe", which is exactly the reasoning that would let a real write
    slip in.
    """
    assert STAGING_ONLY == {"create_action_draft", "list_pending_drafts"}


def test_the_two_allowlists_do_not_overlap() -> None:
    """An overlap would mean one tool described two ways.

    Harmless today - the function checks both - but it would make the sets stop
    documenting what they claim to, and removing a name from one would then
    silently do nothing.
    """
    assert READ_ONLY.isdisjoint(STAGING_ONLY)


def test_a_tool_that_decides_a_draft_would_still_be_gated() -> None:
    """No such tool exists, and the backend has a test keeping it that way.

    This is the belt to that braces: if one ever did appear, it would need
    approval by default rather than inheriting the staging tools' freedom
    because its name happens to start with the same word.
    """
    for name in ("approve_action_draft", "reject_action_draft"):
        assert tool_kind(name) == "unapproved", name
