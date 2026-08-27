"""The service layer: every business rule in this application, written once.

This package is the whole point of the architecture. `api/` and `mcp_server/`
are thin translators that call into here; neither owns a single rule.

Three constraints hold for every module in this package, and `import-linter`
enforces the first two mechanically (see backend/pyproject.toml):

  1. Never import from `api/` or `mcp_server/`. The arrow points one way.
  2. Never import a web or protocol framework - no `fastapi`, no `mcp`, no
     `starlette`. Not even for a type hint.
  3. Never speak in HTTP. No status codes, no "404", no `HTTPException`.
     Raise from `core.exceptions` instead and let each adapter translate.

Rule 3 is the one a linter cannot see - it can be broken without an import, by
returning a bare `409` as an integer. It stays a rule you keep in your head.
"""

# --- draft type registration -----------------------------------------------
#
# Draft types register themselves as a side effect of their module being
# imported. Something has to guarantee that import happens, or the type
# silently does not exist - and `drafts.approve_draft` refuses an unknown type,
# so the symptom would be a feature that looks broken rather than absent.
#
# Importing here means the registry is complete for anyone who imports the
# service layer at all, which both adapters and every test do.
#
# ⚠️ The import is unused by name on purpose. Do not "clean it up" - the flake8
# noqa below says so to the linter, and this comment says so to you.
from services import spoilage  # noqa: F401,E402
