"""Settings for the agent service, loaded from agent/.env.

This is **production infrastructure, used from Gate 15 onward** - including by
the teaching scripts in `_learning/`. That is deliberate, and it is worth
saying why, because the alternative was tempting.

The teaching scripts could have read `os.environ["GEMINI_API_KEY"]` directly
and saved this file. They do not, because then the first thing that happens
after the teaching gate is that the config mechanism changes underneath code
you have already read, and the loop you learned stops being the loop that
runs. The point of `_learning/` is to be *the same system with fewer layers*,
not a different system. So: flat agent logic, real infrastructure.

It mirrors `backend/core/config.py` on purpose - same `BaseSettings` pattern,
same fail-loudly-at-the-boundary reasoning, same absolute-path trick for
locating `.env`. It is a **copy rather than an import**: `agent/` is a
separate directory with a separate virtualenv that reaches the ERP only over
MCP (docs/AGENT-PLAN.md, "Architecture"). Importing `backend.core.config`
would cross exactly the boundary the whole design exists to hold. Twelve
duplicated lines is the price of that boundary, and it is a good price.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The directory this file lives in - i.e. agent/. Built as an absolute path so
# it resolves the same whether you run `python _learning/15a_raw_call.py` from
# agent/ or `python agent/_learning/15a_raw_call.py` from the repo root. A
# relative path would resolve against the current working directory and break
# depending on where you happened to be standing.
AGENT_DIR = Path(__file__).resolve().parent


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

    # Which model to call. A setting rather than a literal because the Flash
    # line moves fast (2.5 -> 3.1 -> 3.5 -> 3.6 within roughly a year) and
    # swapping models is a thing we will actually want to do while tuning
    # tool-calling behaviour.
    #
    # **A pin, not the `gemini-flash-latest` alias - changed at Gate 15a after
    # the alias returned 503 UNAVAILABLE on the first real call.** The alias
    # points at the newest Flash release, which is exactly the one under load;
    # "always current" and "actually available" turn out to pull in opposite
    # directions on a free tier. Availability won, because a teaching script
    # that fails intermittently teaches nothing.
    #
    # The cost of pinning is real and unmitigated by cleverness: a dated model
    # eventually retires, and this line is what will break when it does. What
    # makes that acceptable is that it is a *setting* - the failure is one
    # .env line to fix, not a code change, and the error message names the
    # model plainly.
    #
    # Flash-Lite specifically: the fastest and cheapest of the 3.5 line, and
    # the free tier is scoped to Flash-class models anyway (docs/AGENT-PLAN.md).
    # Tool-calling quality gets re-checked at Gate 16 against the real loop -
    # if Lite proves too weak at choosing tools, move up to gemini-3.5-flash.
    gemini_model: str = "gemini-3.5-flash-lite"

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
