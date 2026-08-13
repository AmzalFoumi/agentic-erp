"""Test doubles for the model. Fakes live here rather than in conftest.py.

conftest.py is for fixtures and pytest hooks, which pytest discovers and
injects; it is not an importable module for shared helpers. `tests/` has an
__init__.py (needed so import-linter can name `agent.tests`), which makes it a
real package - so `from conftest import ...` cannot resolve, and importing
conftest by name is an anti-pattern besides. A plain module the test files
import is the right home.
"""

from collections.abc import AsyncIterator

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import (
    AgentInfo,
    DeltaToolCall,
    DeltaToolCalls,
    FunctionModel,
)


def scripted_model(*responses: ModelResponse) -> FunctionModel:
    """A FunctionModel that returns the given responses in order, once each.

    This is how a test decides what the model "thinks" - no network, no Gemini,
    no nondeterminism. `responses` is consumed across every agent.run() call
    made with this same FunctionModel instance, which is what lets one instance
    script a turn that pauses for approval AND the resumed turn that follows it:
    pass the same object to run_turn and then to resume_turn.

    **Both a `function` and a `stream_function`, sharing one `remaining` list.**
    Gate 19 only needed the former, because `run_turn` calls `agent.run`. Gate 20
    needs the latter: the HTTP route hands the agent to `VercelAIAdapter`, which
    streams, and a FunctionModel without a `stream_function` does not fail with a
    `TypeError` at construction - it streams one `{"type":"error"}` SSE frame
    saying so, which is easy to mistake for a bug in app.py. Sharing the list is
    what keeps a turn scriptable across a pause: a streamed run and a streamed
    resume consume responses 1 and 2 of the same script.
    """

    remaining = list(responses)

    def _next() -> ModelResponse:
        if not remaining:
            raise AssertionError(
                "The model was called more times than the test scripted responses "
                "for. Either the agent looped unexpectedly, or the test needs "
                "another ModelResponse."
            )
        return remaining.pop(0)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return _next()

    async def stream_respond(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | DeltaToolCalls]:
        """Re-emit the same scripted response as deltas.

        One chunk per part rather than character-by-character: the tests assert on
        what arrives, never on how finely it was chopped, and a coarse chunking
        keeps the two code paths obviously equivalent. Text and tool calls are
        never mixed in one yield sequence because `StreamFunctionDef`'s docstring
        forbids it - which holds here since every scripted response in this suite
        is homogeneous.
        """
        response = _next()

        tool_calls = [part for part in response.parts if isinstance(part, ToolCallPart)]
        if tool_calls:
            for index, part in enumerate(tool_calls):
                yield {
                    index: DeltaToolCall(
                        name=part.tool_name,
                        json_args=part.args_as_json_str(),
                        tool_call_id=part.tool_call_id,
                    )
                }
            return

        for part in response.parts:
            if isinstance(part, TextPart):
                yield part.content

    return FunctionModel(respond, stream_function=stream_respond)
