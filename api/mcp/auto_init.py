"""Zero-config startup helpers for the MCP server (T12).

Two automation behaviours:

1. :func:`ensure_falkordb` — at server boot, ping FalkorDB; if it's
   unreachable on a localhost host, run ``cgraph ensure-db`` to spin up
   the existing Docker container. Reuses ``api.cli.ensure_db`` rather
   than duplicating Docker logic.

2. :func:`maybe_auto_index` — when ``CODE_GRAPH_AUTO_INDEX=true`` is set
   (opt-in, off by default), index the current working directory into a
   per-branch graph so the agent doesn't have to call ``index_repo``
   first. Idempotent within a single process — the second call for the
   same ``(project, branch)`` is a no-op.

Both are deliberately conservative: ensure-db only acts on localhost
hosts, and auto-index requires explicit opt-in because indexing a
large repo can take minutes and surprising the user with that on
first tool call is bad UX.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
from pathlib import Path
from typing import Iterable, Optional


logger = logging.getLogger(__name__)


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_AUTO_INDEXED: set[tuple[str, str]] = set()


# ---------------------------------------------------------------------------
# ensure_falkordb
# ---------------------------------------------------------------------------


def _falkordb_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_falkordb() -> dict:
    """Make sure FalkorDB is reachable; bootstrap Docker if not.

    Returns a small status dict so the caller can log it. Never raises —
    the goal is to start the MCP server even if the bootstrap fails;
    individual tools will then surface their own errors.
    """
    host = os.getenv("FALKORDB_HOST", "localhost")
    try:
        port = int(os.getenv("FALKORDB_PORT", "6379"))
    except ValueError:
        return {"status": "error", "message": "invalid FALKORDB_PORT"}

    if _falkordb_reachable(host, port):
        return {"status": "ok", "host": host, "port": port, "action": "none"}

    if host not in _LOCAL_HOSTS:
        return {
            "status": "error",
            "host": host,
            "port": port,
            "message": "FalkorDB unreachable; auto-start only supports localhost",
        }

    logger.info("FalkorDB unreachable on %s:%s — running `cgraph ensure-db`", host, port)
    try:
        # Subprocess so the CLI's stdout (which prints JSON) doesn't pollute
        # the MCP server's own stdio transport.
        result = subprocess.run(
            ["cgraph", "ensure-db"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return {"status": "error", "message": "cgraph CLI not on PATH"}

    return {
        "status": "ok" if result.returncode == 0 else "error",
        "host": host,
        "port": port,
        "action": "started",
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


# ---------------------------------------------------------------------------
# maybe_auto_index
# ---------------------------------------------------------------------------


def _truthy(val: Optional[str]) -> bool:
    return (val or "").strip().lower() in {"1", "true", "yes", "on"}


def _detect_branch(cwd: Path) -> str:
    """Best-effort current-branch detection. Falls back to ``_default``."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return "_default"


def maybe_auto_index(
    cwd: Optional[Path] = None,
    *,
    project: Optional[str] = None,
    branch: Optional[str] = None,
) -> dict:
    """If opt-in env var is set, index ``cwd`` into the per-branch graph.

    Caches "already auto-indexed this session" per ``(project, branch)``
    in the module-level :data:`_AUTO_INDEXED` set so subsequent calls
    are no-ops.
    """
    if not _truthy(os.getenv("CODE_GRAPH_AUTO_INDEX")):
        return {"status": "skipped", "reason": "CODE_GRAPH_AUTO_INDEX not set"}

    cwd_path = (cwd or Path.cwd()).resolve()
    project_name = project or cwd_path.name
    branch_name = branch or _detect_branch(cwd_path)

    key = (project_name, branch_name)
    if key in _AUTO_INDEXED:
        return {"status": "skipped", "reason": "already auto-indexed", "key": key}

    # Local imports so the MCP server can import this module without paying
    # the analyzer-stack import cost at module load.
    from api.analyzers.source_analyzer import SourceAnalyzer
    from api.graph import Graph

    logger.info("Auto-indexing %s @ %s into code:%s:%s", cwd_path, branch_name, project_name, branch_name)
    graph = Graph(project_name, branch=branch_name)
    SourceAnalyzer().analyze_local_folder(str(cwd_path), graph)

    _AUTO_INDEXED.add(key)
    return {
        "status": "indexed",
        "project": project_name,
        "branch": branch_name,
        "path": str(cwd_path),
    }


def reset_auto_index_cache(keys: Optional[Iterable[tuple[str, str]]] = None) -> None:
    """Drop the auto-index session cache. Tests only."""
    if keys is None:
        _AUTO_INDEXED.clear()
    else:
        for k in keys:
            _AUTO_INDEXED.discard(k)
