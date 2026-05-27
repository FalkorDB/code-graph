"""FastMCP server for code-graph.

This is the scaffold (T1). It instantiates a single FastMCP app, exposes it
as ``app`` for tests and embedders, and registers a ``main()`` entry point
that runs the server over stdio. Tools are registered in later tickets
(T4-T8, T11) by importing this module's ``app`` and decorating functions
with ``@app.tool(...)``.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

app: FastMCP = FastMCP("code-graph")

# Register tools on import so both direct ``import api.mcp.server`` and the
# stdio entry point see the same tool list. Imported below ``app`` because
# the tool modules need a reference to it.
from . import tools  # noqa: F401, E402


def main() -> None:
    """Run the MCP server over stdio.

    Console-script entry point for ``cgraph-mcp``. Runs the T12
    auto-init helpers first so a freshly-cloned user gets a working
    FalkorDB without manual `cgraph ensure-db`, and (opt-in via
    ``CODE_GRAPH_AUTO_INDEX``) an indexed CWD without manual
    `index_repo`.
    """
    from .auto_init import ensure_falkordb, maybe_auto_index

    ensure_falkordb()
    maybe_auto_index()
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
