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


def main() -> None:
    """Run the MCP server over stdio.

    Console-script entry point for ``cgraph-mcp``.
    """
    app.run()


if __name__ == "__main__":
    main()
