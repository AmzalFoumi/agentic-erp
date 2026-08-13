"""Shared test setup: the import path, and the Settings every test needs.

**The sys.path line is load-bearing and must come before any agent import.**
agent/ modules are flat and import each other bare (`from config import
settings`), which works for scripts/ because scripts/ask.py inserts agent/ on
sys.path first. Tests need the identical fix, and they need it more urgently:
agent/__init__.py exists (added at Gate 17 for import-linter), so without this
line pytest resolves these tests as `agent.tests.test_approval` from the repo
root, and then `from config import ...` inside conversation.py fails with
ModuleNotFoundError. conftest.py is imported before any test module, which is
what makes this the right place for it.

Fakes live in tests/fakes.py, not here - see that file's docstring for why.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from actor import SystemActor  # noqa: E402  (must follow the sys.path line above)
from config import Settings  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    """A Settings object built in the test, not read from agent/.env.

    Both fields are required by config.py and both are unused by these tests -
    the model and the toolset are injected directly, so nothing here ever
    builds a real GoogleModel or opens a real database connection. Constructing
    our own instance rather than importing config.settings keeps a test from
    depending on which model the developer happens to have configured.

    Note that importing config at all still requires a valid agent/.env,
    because config.py creates a module-level `settings = Settings()` at import
    time. That is a pre-existing property of the module, not something Gate 19
    introduced.
    """
    return Settings(
        gemini_api_key="test-key-not-used",
        database_url="postgresql+psycopg://unused/unused",
    )


@pytest.fixture
def actor() -> SystemActor:
    """The actor every turn runs as. Gate 20 made this a required parameter.

    SystemActor is still the only implementation (docs/AUTH-PLAN.md), so this
    fixture asserts nothing interesting today. It exists so that the day a
    second implementation appears, every test names which one it meant - rather
    than inheriting whatever a default happened to be.
    """
    return SystemActor()
