"""MCP tool implementations for code-graph.

Each submodule registers tools against the shared FastMCP app exposed by
``api.mcp.server``. Import this package to register all tools.
"""

# NOTE: the GraphRAG-backed ``ask`` tool is intentionally NOT part of the MCP
# surface. In benchmarking it failed on every call ("Missing GOOGLE_API_KEY/
# GEMINI_API_KEY") because the spawned MCP server env carries only FalkorDB
# coordinates, and even when keyed it returned File-level fuzzy matches rather
# than the structural answers the nav workflow needs. Burning an LLM round-trip
# per call for no signal, so we expose only the deterministic structural tools.
# GraphRAG ask remains available on the HTTP /api/chat path.
from . import structural  # noqa: F401  (registers tools on import)
