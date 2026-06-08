"""FastMCP server for code-graph.

This is the scaffold (T1). It instantiates a single FastMCP app, exposes it
as ``app`` for tests and embedders, and registers a ``main()`` entry point
that runs the server over stdio. Tools are registered in later tickets
(T4-T8, T11) by importing this module's ``app`` and decorating functions
with ``@app.tool(...)``.
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

app: FastMCP = FastMCP("code-graph")

# Register tools on import so both direct ``import api.mcp.server`` and the
# stdio entry point see the same tool list. Imported below ``app`` because
# the tool modules need a reference to it.
from . import tools  # noqa: F401, E402


def _start_background_auto_index() -> None:
    """Run opt-in auto-index off the startup path.

    Indexing a large repo can take minutes; doing it synchronously before
    ``app.run`` would block the MCP stdio handshake until it finished. A daemon
    thread keeps the server responsive immediately — the analyzer logs to
    stderr only, so it can't corrupt the stdio JSON-RPC stream. ``maybe_auto_index``
    is a no-op when ``CODE_GRAPH_AUTO_INDEX`` is unset and caches success so the
    work happens at most once per ``(project, branch)``.
    """
    import threading

    from .auto_init import maybe_auto_index

    def _run() -> None:
        try:
            maybe_auto_index()
        except Exception:  # never let a background failure take down the server
            logger.exception("background auto-index failed")

    threading.Thread(target=_run, name="cgraph-auto-index", daemon=True).start()


def main() -> None:
    """Run the MCP server over stdio.

    Console-script entry point for ``cgraph-mcp``. Ensures FalkorDB is
    reachable (bootstrapping the Docker container if needed) before
    serving, then kicks off opt-in auto-indexing (via
    ``CODE_GRAPH_AUTO_INDEX``) in the background so a freshly-cloned user
    gets an indexed CWD without manual ``index_repo`` — without blocking
    the stdio handshake.
    """
    from .auto_init import ensure_falkordb

    ensure_falkordb()
    _start_background_auto_index()
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
