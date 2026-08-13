"""Gate 19's proof: a turn stops before a data-changing tool runs, and resumes
correctly on both approve and deny.

**No network and no Gemini.** FunctionModel (conftest's `scripted_model`)
decides what the model "says", and RecordingToolset below stands in for the MCP
connection while recording which tools actually executed. Determinism is the
point: a denial cannot be demonstrated against a live model at all, since the
model does not choose whether it is denied.
"""

from typing import Any

import pytest
from pydantic_ai import RunContext, ToolDefinition
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.toolsets import AbstractToolset, ToolsetTool

from conversation import PendingApproval, resume_turn, run_turn

# `_ARGS_VALIDATOR` is private to mcp_client, imported here deliberately: the
# fake toolset needs the same "a dict with string keys" validator the real one
# uses, and rebuilding it in the test would be a second copy that could drift.
from mcp_client import _ARGS_VALIDATOR, tool_kind

# Relative, because tests/ is a real package (see fakes.py's docstring) - this
# resolves regardless of what pytest put on sys.path.
from .fakes import scripted_model

# The six tools backend/mcp_server/server.py actually exposes. Named here
# rather than fetched, because a test that asked a live server what tools exist
# would not be deterministic.
TOOL_NAMES = (
    "list_products",
    "get_product",
    "get_product_by_sku",
    "create_product",
    "update_product",
    "adjust_stock",
)


class RecordingToolset(AbstractToolset[Any]):
    """A stand-in for ErpToolset that records executions instead of doing them.

    **It gates its tools through mcp_client.tool_kind(), not a copy of the
    rule.** That is what makes these tests evidence about the real gating
    decision rather than about a duplicate of it - if someone widened
    READ_ONLY, these tests would go green and test_tool_gating.py would go red,
    which is the correct division: that file owns the rule, this one owns the
    behaviour built on it.
    """

    def __init__(self) -> None:
        # (tool_name, arguments) for every tool that actually ran. The
        # assertions that matter in this file are about this list: "resumes
        # correctly on approve and deny" is a claim about whether the tool ran,
        # not about whether a string came back.
        self.executed: list[tuple[str, dict[str, Any]]] = []

    @property
    def id(self) -> str | None:
        return "erp"

    async def get_tools(self, ctx: RunContext[Any]) -> dict[str, ToolsetTool[Any]]:
        return {
            name: ToolsetTool(
                toolset=self,
                tool_def=ToolDefinition(
                    name=name,
                    description=f"Fake {name} for tests.",
                    # Deliberately permissive: the real schemas live in
                    # backend/, and this file is testing approval flow, not
                    # argument validation.
                    parameters_json_schema={"type": "object", "properties": {}},
                    kind=tool_kind(name),
                ),
                max_retries=ctx.max_retries,
                args_validator=_ARGS_VALIDATOR,
            )
            for name in TOOL_NAMES
        }

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[Any],
        tool: ToolsetTool[Any],
    ) -> Any:
        self.executed.append((name, tool_args))
        return f"{name} ran with {tool_args}"


async def test_a_read_tool_runs_without_approval(settings, actor) -> None:
    """The control case: nothing about this gate changes a read question.

    Without this test, a bug that gated everything would look identical to a
    passing approval suite.
    """
    model = scripted_model(
        ModelResponse(parts=[ToolCallPart("list_products", {})]),
        ModelResponse(parts=[TextPart("Nine products are low on stock.")]),
    )
    toolset = RecordingToolset()

    result = await run_turn(
        [], "What's low on stock?", settings=settings, actor=actor, model=model, toolset=toolset
    )

    assert result.answer == "Nine products are low on stock."
    assert result.pending == []
    assert result.resume_state is None
    assert [name for name, _ in toolset.executed] == ["list_products"]
    # A completed turn contributes both halves to history, exactly as before
    # this gate - store.py's contract is unchanged.
    assert [m.role for m in result.new_messages] == ["user", "assistant"]


async def test_a_mutating_tool_pauses_the_turn(settings, actor) -> None:
    """The gate itself: adjust_stock stops before running."""
    model = scripted_model(
        ModelResponse(
            parts=[
                ToolCallPart(
                    "adjust_stock",
                    {"sku": "RICE-5KG", "quantity": 20},
                    tool_call_id="call-1",
                )
            ]
        ),
    )
    toolset = RecordingToolset()

    result = await run_turn(
        [], "Set rice stock to 20.", settings=settings, actor=actor, model=model, toolset=toolset
    )

    # The whole point: the tool did NOT run.
    assert toolset.executed == []

    assert result.pending == [
        PendingApproval(
            tool_name="adjust_stock",
            arguments={"sku": "RICE-5KG", "quantity": 20},
            call_id="call-1",
        )
    ]
    # A paused turn has no answer yet. None rather than "" so a caller that
    # forgets to check `pending` prints something obviously wrong instead of
    # something plausibly empty.
    assert result.answer is None
    # A half-finished turn is not conversation history, so nothing is appended
    # until the resume completes it. This is what keeps store.py untouched by
    # this gate.
    assert result.new_messages == []
    assert result.resume_state is not None


async def _pause_on_adjust_stock(settings, actor) -> tuple[Any, RecordingToolset, Any]:
    """Drive a turn to the paused state, and hand back the pieces to resume it.

    The same FunctionModel instance is returned alongside the paused result
    because `scripted_model` consumes its responses across every run made with
    it - so the second scripted response below is what the model says AFTER the
    decision arrives.
    """
    model = scripted_model(
        ModelResponse(
            parts=[
                ToolCallPart(
                    "adjust_stock",
                    {"sku": "RICE-5KG", "quantity": 20},
                    tool_call_id="call-1",
                )
            ]
        ),
        ModelResponse(parts=[TextPart("Done.")]),
    )
    toolset = RecordingToolset()
    paused = await run_turn(
        [], "Set rice stock to 20.", settings=settings, actor=actor, model=model, toolset=toolset
    )
    assert paused.resume_state is not None
    return paused, toolset, model


async def test_approving_runs_the_tool(settings, actor) -> None:
    """**Approve: the tool actually executes, with the original arguments.**

    Asserting on `toolset.executed` rather than on the answer string is the
    whole point. A resume that returned nice text without running the tool
    would pass an answer-only assertion and be completely broken.
    """
    paused, toolset, model = await _pause_on_adjust_stock(settings, actor)

    result = await resume_turn(
        [],
        paused.resume_state,
        {"call-1": True},
        settings=settings,
        actor=actor,
        model=model,
        toolset=toolset,
    )

    assert toolset.executed == [("adjust_stock", {"sku": "RICE-5KG", "quantity": 20})]
    assert result.answer == "Done."
    assert result.pending == []
    assert result.resume_state is None
    # A resumed turn is a completed turn, so store.py persists it exactly like
    # any other - no special case for "this one was approved".
    assert [m.role for m in result.new_messages] == ["user", "assistant"]
    # The user half is recovered from resume_state, not passed in again.
    assert result.new_messages[0].content == "Set rice stock to 20."


async def test_denying_does_not_run_the_tool(settings, actor) -> None:
    """**Deny: the tool never executes, and the turn still completes.**

    Both halves matter. A denial that left the turn stuck would be as broken as
    one that ran the tool anyway - the model needs to be told it was refused so
    it can reply to the person.
    """
    paused, toolset, model = await _pause_on_adjust_stock(settings, actor)

    result = await resume_turn(
        [],
        paused.resume_state,
        {"call-1": False},
        settings=settings,
        actor=actor,
        model=model,
        toolset=toolset,
    )

    assert toolset.executed == []
    assert result.answer == "Done."
    assert result.pending == []


async def test_an_unknown_or_missing_decision_is_rejected(settings, actor) -> None:
    """Both halves of the decision map are checked before the model is called.

    An unknown id means the caller is answering a call that was never pending -
    a bug worth surfacing rather than ignoring. A missing id means a call was
    left unanswered, which is exactly the parallel-batch failure Gate 15's
    finding 5 warned about: a batch that half-resolves would leave the run
    stuck with no indication why.
    """
    paused, toolset, model = await _pause_on_adjust_stock(settings, actor)

    with pytest.raises(ValueError, match="not pending"):
        await resume_turn(
            [],
            paused.resume_state,
            {"call-1": True, "call-does-not-exist": True},
            settings=settings,
            actor=actor,
            model=model,
            toolset=toolset,
        )

    with pytest.raises(ValueError, match="no decision"):
        await resume_turn(
            [], paused.resume_state, {}, settings=settings, actor=actor, model=model, toolset=toolset
        )

    # Neither rejection reached the tool or the model.
    assert toolset.executed == []
