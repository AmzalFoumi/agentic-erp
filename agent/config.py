"""Settings for the agent service, loaded from agent/.env.

This is **production infrastructure, used from Gate 15 onward** - including by
the diagnostic in `scripts/check_mcp.py`. That is deliberate, and it is worth
saying why, because the alternative was tempting.

Gate 15's original teaching scripts could have read `os.environ["GEMINI_API_KEY"]`
directly and skipped this file. They did not, because then the first thing that
happens after the teaching gate is that the config mechanism changes underneath
code you have already read, and the loop you learned stops being the loop that
runs. The rule that produced this file was restated as **flatten the thinking,
not the plumbing** (docs/AGENT-PLAN.md, Gate 15) - flat agent logic, real
infrastructure.

It mirrors `backend/core/config.py` on purpose - same `BaseSettings` pattern,
same fail-loudly-at-the-boundary reasoning, same absolute-path trick for
locating `.env`. It is a **copy rather than an import**: `agent/` is a
separate directory with a separate virtualenv that reaches the ERP only over
MCP (docs/AGENT-PLAN.md, "Architecture"). Importing `backend.core.config`
would cross exactly the boundary the whole design exists to hold. Twelve
duplicated lines is the price of that boundary, and it is a good price.
"""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The directory this file lives in - i.e. agent/. Built as an absolute path so
# it resolves the same whether you run `python _learning/15a_raw_call.py` from
# agent/ or `python agent/_learning/15a_raw_call.py` from the repo root. A
# relative path would resolve against the current working directory and break
# depending on where you happened to be standing.
AGENT_DIR = Path(__file__).resolve().parent

# The three models this project actually uses, with short names for them.
#
# **Why aliases rather than just writing the full ID in .env.** The real IDs are
# long, easy to mistype, and a typo does not fail loudly - Google returns a 404
# for an unknown model, mid-turn, which is exactly the kind of late failure this
# file exists to prevent. A short name that resolves through this table cannot be
# half-right: either it is here or it is passed through untouched (see below).
#
# All three were read from the AI Studio model picker on 2026-08-11, not from
# documentation and not from memory - the exact Gemma strings are absent from
# ai.google.dev's model list, which is why AGENT-PLAN.md forbade guessing them.
#
# **Function calling is confirmed for all three.** Gemma's support was verified
# against https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api the same day,
# because a Gemma default would have been worthless otherwise: this project's
# entire use of a model is choosing and calling tools. Known caveat, also
# verified: Gemma is less inclined than Gemini to reach for a tool unprompted, so
# the system prompt says so explicitly and `scripts/ask.py` prints which tools
# were called before printing the answer.
MODELS: dict[str, str] = {
    # Default. Google DeepMind's flagship open-weight dense model, 256K context.
    # Chosen over Flash-Lite for development on daily-quota grounds: the
    # free-tier dashboard showed Flash-Lite at 500 requests/day against Gemma's
    # ~10-20k (AGENT-PLAN.md, "Free-tier limits").
    "gemma-31b": "gemma-4-31b-it",
    # Mixture-of-Experts, ~4B parameters active per inference. Faster and cheaper
    # than the 31B at some cost in reasoning quality - the one to try if turns
    # feel slow, before reaching for a different family.
    "gemma-26b": "gemma-4-26b-a4b-it",
    # The Gemini fallback, and the comparison case for Gate 16's open question:
    # if Gemma chooses tools badly, this is what it gets measured against.
    # Different family, different tokeniser, different function-calling
    # implementation - so it is a real second opinion, not a bigger version of
    # the same thing.
    "flash-lite": "gemini-3.5-flash-lite",
}


class Settings(BaseSettings):
    """Every configurable value the agent service needs.

    Fields are matched case-insensitively against agent/.env or the real
    environment. No default => required, and the process refuses to start
    without it.
    """

    model_config = SettingsConfigDict(
        env_file=AGENT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required. An AI Studio key for the Gemini Developer API - see
    # .env.example for where to get one.
    #
    # Note this is named to match what `google.genai.Client()` would look for
    # in the environment on its own. We pass it explicitly rather than relying
    # on that auto-detection, so that a missing key fails here, at startup,
    # naming the field - instead of surfacing as a 401 from Google in the
    # middle of a turn.
    gemini_api_key: str

    # Which model to call. A setting rather than a literal because the model
    # lines move fast (Flash went 2.5 -> 3.1 -> 3.5 -> 3.6 in roughly a year)
    # and swapping models is a thing we will actually want to do while tuning
    # tool-calling behaviour.
    #
    # **Accepts either a short name from MODELS above or a full model ID.**
    # Unset falls back to the default below. Set it in agent/.env as one of:
    #
    #     GEMINI_MODEL=gemma-31b      # the default; same as leaving it out
    #     GEMINI_MODEL=gemma-26b      # faster, cheaper, slightly weaker
    #     GEMINI_MODEL=flash-lite     # the Gemini comparison
    #
    # The default is a short name, not a full ID, so that this line and the .env
    # line are written in the same vocabulary. It changed from
    # "gemini-3.5-flash-lite" to Gemma at Gate 16 on the quota grounds recorded
    # in MODELS - a development default should be the one you can run all day.
    #
    # **A pin, not a `-latest` alias — set at Gate 15a after the alias returned
    # 503 UNAVAILABLE on the first real call.** The alias points at the newest
    # release, which is exactly the one under load; "always current" and
    # "actually available" pull in opposite directions on a free tier.
    # Availability won, because a script that fails intermittently teaches
    # nothing.
    #
    # The cost of pinning is real: a dated model eventually retires, and this is
    # what breaks when it does. What makes that acceptable is that it is a
    # *setting* - one .env line to fix, and the error names the model plainly.
    gemini_model: str = "gemma-31b"

    @field_validator("gemini_model")
    @classmethod
    def _resolve_model_alias(cls, value: str) -> str:
        """Turn a short name into the real model ID; leave anything else alone.

        **Passing unknown values through is deliberate, and it is the one
        judgement call in this file.** Rejecting them would catch typos, at the
        cost of making every new model Google ships a code change here - and the
        Flash line moved 2.5 -> 3.1 -> 3.5 -> 3.6 in about a year. Since the
        point of `gemini_model` being a setting is that trying a model is not a
        commit, a validator that blocks unlisted models would defeat the field.

        So: a short name is checked, a full ID is trusted. The failure mode for a
        mistyped full ID is a 404 from Google naming the model, which is
        survivable; the failure mode for a mistyped short name is caught here,
        because `MODELS` is the exhaustive list of names this project invented and
        can therefore be authoritative about.
        """
        value = value.strip()

        if value in MODELS:
            return MODELS[value]

        # A bare short-name-shaped mistake - "gemma-4" or "flash" - would sail
        # past as a "full ID" and 404 later. Catch the near-misses: anything
        # without a version-ish digit is far likelier to be a fumbled alias than
        # a real model ID, all three of which carry one.
        if not any(char.isdigit() for char in value):
            raise ValueError(
                f"Unknown model {value!r}. Use a short name "
                f"({', '.join(sorted(MODELS))}) or a full model ID from the AI "
                f"Studio model picker."
            )

        return value

    # Which provider class in model_provider.py builds the Model - keyed by
    # name rather than guessed from `gemini_model`, so a Gemma name and a
    # Gemini name can both route through "google" (they share one API) while
    # a future provider (e.g. Anthropic) is a new registry entry, not a
    # branch on what the model string looks like.
    #
    # At Gate 16 (2026-08-06) the free-tier dashboard showed Gemini
    # Flash-Lite capped at 500 requests/day against Gemma 4's ~10-20k, making
    # Gemma 4 the intended model for development (docs/AGENT-PLAN.md,
    # "Free-tier limits"). Both are served by Google's API, so switching
    # models never touches this field - only `gemini_model` below does.
    #
    # **Closed 2026-08-11:** the exact Gemma model-ID strings were previously
    # unknown - ai.google.dev's model list and Gemma's own model card both omit
    # them - so this file carried an instruction not to guess them. They have now
    # been read from the AI Studio picker and are in MODELS above, and
    # `gemini_model` defaults to Gemma accordingly.
    model_provider: str = "google"

    # Where the backend's MCP server is listening. Used from Gate 15c onward.
    #
    # **This URL is load-bearing for the auth deferral.** The agent runs
    # unauthenticated only because this is loopback. Pointing it at anything
    # that is not 127.0.0.1 - a LAN address, a tunnel, a deployed host - trips
    # the first of the two conditions that expire the auth deferral and
    # triggers the auth gate before any further agent work. The full list of
    # what counts is in docs/AGENT-PLAN.md under "The stop condition"; it is a
    # list rather than a principle because the dangerous version of this
    # mistake is a thirty-second convenience, not a decision.
    mcp_base_url: str = "http://127.0.0.1:8001/mcp"


# One shared instance, created when this module is first imported. Everything
# else in agent/ does `from config import settings` (or `from agent.config
# import settings` once there is a package to import from - Gate 17).
settings = Settings()  # type: ignore[call-arg]
