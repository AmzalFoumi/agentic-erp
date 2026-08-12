"""Test doubles for the model. Fakes live here rather than in conftest.py.

conftest.py is for fixtures and pytest hooks, which pytest discovers and
injects; it is not an importable module for shared helpers. `tests/` has an
__init__.py (needed so import-linter can name `agent.tests`), which makes it a
real package - so `from conftest import ...` cannot resolve, and importing
conftest by name is an anti-pattern besides. A plain module the test files
import is the right home.
"""

from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel


def scripted_model(*responses: ModelResponse) -> FunctionModel:
    """A FunctionModel that returns the given responses in order, once each.

    This is how a test decides what the model "thinks" - no network, no Gemini,
    no nondeterminism. `responses` is consumed across every agent.run() call
    made with this same FunctionModel instance, which is what lets one instance
    script a turn that pauses for approval AND the resumed turn that follows it:
    pass the same object to run_turn and then to resume_turn.
    """

    remaining = list(responses)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if not remaining:
            raise AssertionError(
                "The model was called more times than the test scripted responses "
                "for. Either the agent looped unexpectedly, or the test needs "
                "another ModelResponse."
            )
        return remaining.pop(0)

    return FunctionModel(respond)
