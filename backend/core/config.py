"""Application settings, loaded from the environment.

Why not just call `os.environ["DATABASE_URL"]` wherever we need it?

Because a missing or malformed setting would then blow up deep inside some
request handler at 2am, with a confusing error. `BaseSettings` reads everything
once at import time and validates it against the type hints. If DATABASE_URL is
absent, the program refuses to start and says exactly which field is missing.

That is the whole trick: fail loudly at the boundary, so the rest of the code
can assume the settings are valid.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The directory this file's parent lives in - i.e. backend/. We build an
# absolute path to .env from it rather than a relative one, because a relative
# path would resolve against whatever folder you happened to run python from.
BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Every configurable value the backend needs.

    Each attribute below is matched, case-insensitively, against a variable in
    backend/.env or the real environment. A field with no default (like
    `database_url`) is REQUIRED; one with a default is optional.
    """

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        # Ignore any extra variables in .env that we haven't declared here,
        # instead of raising. Keeps the file usable as a scratchpad.
        extra="ignore",
    )

    # No default => required. The `str` type hint is what pydantic validates.
    database_url: str

    # Has a default => optional. Note the type is `bool`: pydantic converts the
    # string "false" from the .env file into the Python value False for us.
    sql_echo: bool = False


# One shared instance, created when this module is first imported. Everything
# else in the codebase does `from core.config import settings`.
settings = Settings()  # type: ignore[call-arg]
