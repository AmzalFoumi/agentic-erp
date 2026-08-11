"""The adapter seam between config.py's model settings and Pydantic AI's Model objects.

**Why this file exists rather than folding the one call into conversation.py.**
Model construction (settings in, a configured `pydantic_ai.models.Model` out) is
a distinct responsibility from running a turn, and keeping it separate is what
lets `docs/AGENT-PLAN.md`'s model-agnostic goal be more than a sentence: trying a
different model, or a different *provider*, is a change here, never a change to
the loop that runs turns.

**Where this sits relative to the isolation rule.** `docs/AGENT-PLAN.md` says
conversation.py is the only module that may import `pydantic_ai` - true in
spirit, not in the letter of this file. `model_provider.py` is grouped with
conversation.py as part of the same runtime cluster: it exists solely to hand
conversation.py a `Model`, never a request/response type, and the enforced
`lint-imports` contract (Gate 17) forbids `pydantic_ai` in config.py and
scripts/, not here. `mcp_client.py` is grouped in the same allowed cluster -
it implements Pydantic AI's `AbstractToolset` directly and cannot avoid the
import. So: conversation.py imports this module; this module
imports pydantic_ai; nothing downstream of conversation.py sees either.

**The pattern, and why it is sized the way it is.** This is a Strategy
(one interface, one implementation per provider) selected by a Factory
(`build_model`, keyed by name). Both Gemini and Gemma are called through the
same Google Gemini Developer API today, so there is exactly one concrete
class - GoogleAgentModelProvider covers both, since the split between them is
just which model-ID string is in settings, not which SDK object builds it.
Adding a second real provider (Anthropic, OpenAI) means one new class and one
new registry line; conversation.py's call to build_model() does not change.
"""

from abc import ABC, abstractmethod

from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from config import Settings


class AgentModelProvider(ABC):
    """One implementation per underlying provider SDK.

    `build()` takes the whole Settings object, not individual fields, because
    a provider may eventually need more than one setting (a project ID, a
    region) and the call site should not have to grow with it.
    """

    @abstractmethod
    def build(self, settings: Settings) -> Model:
        raise NotImplementedError


class GoogleAgentModelProvider(AgentModelProvider):
    """Gemini and Gemma both go through this class - one Google API, one key.

    Which model actually gets called is entirely `settings.gemini_model`; this
    class does not branch on the name, and should not start to. If a model
    family ever needs different construction (a different provider type, a
    different auth mode), that is a signal for a new AgentModelProvider, not
    a conditional inside this one.
    """

    def build(self, settings: Settings) -> Model:
        return GoogleModel(
            settings.gemini_model,
            provider=GoogleProvider(api_key=settings.gemini_api_key),
        )


# The registry the factory below reads. Adding a provider is one class above
# plus one line here - never a change to build_model()'s body.
_PROVIDERS: dict[str, AgentModelProvider] = {
    "google": GoogleAgentModelProvider(),
}


def build_model(settings: Settings) -> Model:
    """The one call conversation.py makes to get a configured Model.

    Keyed by `settings.model_provider`, not inferred from `settings.gemini_model` -
    inferring from the model string ("starts with gemini- or gemma- => google")
    is exactly the kind of implicit rule that breaks quietly the day a model
    name does not match the pattern anyone wrote it against.
    """

    try:
        provider = _PROVIDERS[settings.model_provider]
    except KeyError:
        raise ValueError(
            f"Unknown model_provider {settings.model_provider!r}. "
            f"Registered providers: {sorted(_PROVIDERS)}"
        ) from None
    return provider.build(settings)
