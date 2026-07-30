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
