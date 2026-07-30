"""The HTTP adapter - one of two front doors onto `services/`.

This package translates between HTTP and Python. That is *all* it does. The
rules it must not break, in the same spirit as the ones in services/__init__.py:

  1. No business logic. If a rule about products lives here, the MCP server
     cannot honour it, and the two front doors have started to disagree. Every
     handler in routes/ should be short enough to read in one glance: get a
     session, call one service function, return.

  2. Never catch a domain exception in a handler. The translation from
     `NotFoundError` to `404` happens once, in errors.py, registered on the app.
     Repeating a try/except in twelve handlers is how one of them ends up
     returning 500 for a missing row.

  3. Schemas here are the *public contract*, not the ORM model. api/schemas.py
     defines what JSON goes in and out. It is deliberately a separate thing from
     core/models.py, so that renaming a database column is not automatically a
     breaking change for the Next.js frontend.

The direction of dependency is one-way and enforced by import-linter:
`api` imports `services` and `core`. Nothing imports `api`.
"""
