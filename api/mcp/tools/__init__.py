"""MCP tool implementations for code-graph.

Each submodule registers tools against the shared FastMCP app exposed by
``api.mcp.server``. Import this package to register all tools.
"""

from . import structural  # noqa: F401  (registers tools on import)
