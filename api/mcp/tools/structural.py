"""Structural MCP tools (T4-T8).

These tools wrap the existing ``Project`` / ``Graph`` / ``AsyncGraphQuery``
operations so MCP-capable agents (Claude Code, Cursor, Copilot, Cline)
can drive code-graph over the standard stdio transport.

Conventions shared by all tools in this module:

* Every tool accepts an optional ``branch`` so the agent can scope queries
  to a specific per-branch graph (see T17, issue #651). When omitted the
  branch is either auto-detected from a local checkout (``index_repo``)
  or defaults to ``_default``.
* Long-running synchronous operations are pushed into a thread via
  ``asyncio.get_running_loop().run_in_executor`` so the MCP event loop
  stays responsive.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Optional

from ..server import app


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _looks_like_url(spec: str) -> bool:
    """Return True for HTTP(S) / git URLs, False for local paths."""
    return spec.startswith(("http://", "https://", "git@", "ssh://", "git://"))


def _languages_detected(graph) -> list[str]:
    """Best-effort enumeration of distinct ``File.ext`` values.

    Returns a sorted list of extension strings (without the leading dot).
    Empty when no files were indexed.
    """
    try:
        rows = graph.g.query(
            "MATCH (f:File) RETURN DISTINCT f.ext AS ext"
        ).result_set
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("languages_detected query failed: %s", e)
        return []
    seen: set[str] = set()
    for row in rows or []:
        ext = (row[0] or "").lstrip(".")
        if ext:
            seen.add(ext)
    return sorted(seen)


def _count(graph, label: str) -> int:
    try:
        rows = graph.g.query(
            f"MATCH (n:{label}) RETURN count(n) AS c"
        ).result_set
        return int(rows[0][0]) if rows else 0
    except Exception:
        return 0


def _count_edges(graph) -> int:
    try:
        rows = graph.g.query("MATCH ()-[r]->() RETURN count(r) AS c").result_set
        return int(rows[0][0]) if rows else 0
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# T4 — index_repo
# ---------------------------------------------------------------------------


@app.tool(
    name="index_repo",
    description=(
        "Index a code repository into code-graph for subsequent navigation. "
        "Accepts a local path or a git URL. When `branch` is omitted, "
        "auto-detects the current branch from the local checkout (defaults "
        "to '_default' for non-git folders). Returns the indexed graph's "
        "node/edge counts, detected languages, and the (project, branch) "
        "identity callers should pass to other code-graph tools."
    ),
)
async def index_repo(
    path_or_url: str,
    branch: Optional[str] = None,
    incremental: bool = True,  # accepted now, fully honored once T18 lands
    ignore: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Implementation for the ``index_repo`` MCP tool.

    Args:
        path_or_url: Filesystem path to a local repository **or** a clonable
            git URL (``https://...``, ``git@host:...``, ``ssh://...``).
        branch: Branch identity for the indexed graph. When ``None``:
            auto-detect from the checkout via ``git rev-parse --abbrev-ref
            HEAD``; falls back to ``_default`` if not a git checkout.
        incremental: Accepted for forward-compatibility with T18; the
            current full-reindex path ignores it.
        ignore: List of relative paths to skip during analysis.
    """

    from api.project import Project, detect_branch

    if ignore is None:
        ignore = []

    loop = asyncio.get_running_loop()

    def _do_index() -> dict[str, Any]:
        if _looks_like_url(path_or_url):
            project = Project.from_git_repository(path_or_url, branch=branch)
        else:
            local_path = Path(path_or_url).expanduser().resolve()
            if not local_path.exists():
                raise ValueError(f"path does not exist: {local_path}")

            # Reject paths outside the allow-list when one is configured.
            allowed_root = os.getenv("ALLOWED_ANALYSIS_DIR")
            if allowed_root:
                allowed = Path(allowed_root).expanduser().resolve()
                try:
                    local_path.relative_to(allowed)
                except ValueError as e:
                    raise ValueError(
                        f"path {local_path} is outside ALLOWED_ANALYSIS_DIR={allowed}"
                    ) from e

            # Use Project for git-repo paths so commit metadata is saved,
            # otherwise drive SourceAnalyzer directly so non-git folders work.
            if (local_path / ".git").is_dir():
                project = Project.from_local_repository(local_path, branch=branch)
            else:
                # Synthesize a Project-like object so the return shape is uniform.
                from api.analyzers.source_analyzer import SourceAnalyzer
                from api.graph import Graph

                detected = branch if branch is not None else detect_branch(local_path)
                graph = Graph(local_path.name, branch=detected)
                analyzer = SourceAnalyzer()
                analyzer.analyze_local_folder(str(local_path), graph, ignore)

                class _Synth:  # tiny shim to mirror Project's surface
                    name = local_path.name

                    def __init__(self, g, b):
                        self.graph = g
                        self.branch = b

                return _payload(_Synth(graph, detected))

        project.analyze_sources(ignore)
        return _payload(project)

    def _payload(project) -> dict[str, Any]:
        g = project.graph
        return {
            "project_name": project.name,
            "branch": getattr(project, "branch", None),
            "graph_name": g.name,
            "num_nodes": (
                _count(g, "File") + _count(g, "Class") + _count(g, "Function")
            ),
            "num_edges": _count_edges(g),
            "languages_detected": _languages_detected(g),
            # T18 will flip this to "incremental" when only changed files
            # were re-analyzed.
            "mode": "full",
        }

    return await loop.run_in_executor(None, _do_index)
