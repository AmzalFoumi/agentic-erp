"""Adapter #2: the MCP server, exposing the product services as agent tools.

An empty `__init__.py` is what makes a directory a *package* - something
`import mcp_server.server` can find. Node has no equivalent because it resolves
by file path; Python resolves by package, and this file is the marker.

It is not strictly required in modern Python (PEP 420 allows namespace
packages), but leaving it out causes confusing shadowing bugs, so it stays.
"""
