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

    # Origins the browser is allowed to call this API from. A setting rather
    # than a literal in api/main.py because the value is environment-specific
    # by nature: localhost in development, a real domain in production. Code
    # that has to be edited to deploy is code that will be edited wrongly.
    #
    # The default is the Next.js dev server under both spellings of localhost.
    # Browsers treat `localhost` and `127.0.0.1` as different origins even
    # though they resolve to the same place, so both are listed or the frontend
    # breaks depending on which URL the developer happened to type.
    #
    # Deliberately not `["*"]`, and deliberately not overridable to it by
    # accident: a wildcard is harmless only while there is no authentication,
    # and this project has an auth gate coming. See the note in api/main.py.
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # ---------- Authentication (gate 24) ----------
    #
    # Everything below describes the ThunderID instance that issues access
    # tokens. The backend is a *resource server*: it never talks to ThunderID
    # to log anyone in, it only fetches the public signing keys and checks the
    # tokens that arrive. That is why there is no client id or secret here -
    # those belong to the frontend, which is the OAuth client.

    # The `iss` claim every token must carry. Checked, not trusted: a token
    # from a different issuer is refused even if its signature is valid,
    # because "valid signature" only means *someone* signed it.
    thunderid_issuer: str = "https://localhost:8090"

    # Where the public signing keys live. Derived from the issuer by
    # convention, but overridable, because the two come apart the moment
    # ThunderID sits behind a different hostname than the one it advertises.
    thunderid_jwks_url: str = "https://localhost:8090/oauth2/jwks"

    # The `aud` claim every token must carry: the identifier of the
    # `Agentic ERP API` resource server registered in the ThunderID console.
    #
    # This is a NAME, not an address - nothing ever fetches it. It deliberately
    # does not mention localhost:8000, so that the value survives deployment
    # and tokens minted today keep verifying tomorrow. Verified against a real
    # token on 2026-08-23.
    thunderid_audience: str = "https://api.agentic-erp.local"

    # ⚠️ LOCAL ONLY. ThunderID's development certificate is self-signed, so
    # fetching the JWKS over HTTPS fails certificate validation. Setting this
    # False disables that check for the JWKS fetch *only* - never for anything
    # else, and never in a deployed environment. The counterpart to
    # NODE_TLS_REJECT_UNAUTHORIZED=0 on the frontend; gate 26 removes both by
    # giving ThunderID a real certificate.
    thunderid_verify_tls: bool = True

    # Escape hatch for running the API with no identity provider at all: every
    # request becomes the all-powerful SystemActor again, exactly as it was
    # before gate 24.
    #
    # It exists for one honest reason - the test suite and any local work that
    # has nothing to do with auth should not require a running ThunderID
    # container. It defaults to True so that *forgetting* to configure auth
    # fails closed rather than silently opening the API. See api/deps.py.
    auth_enabled: bool = True


# One shared instance, created when this module is first imported. Everything
# else in the codebase does `from core.config import settings`.
settings = Settings()  # type: ignore[call-arg]
