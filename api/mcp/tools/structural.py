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


# ---------------------------------------------------------------------------
# T5 — get_callers / get_callees / get_dependencies
# ---------------------------------------------------------------------------


def _project_arg(project: str, branch: Optional[str]):
    """Return an :class:`AsyncGraphQuery` for ``(project, branch)``."""
    from api.graph import AsyncGraphQuery

    return AsyncGraphQuery(project, branch=branch)


def _node_summary(n: Any) -> dict[str, Any]:
    """Normalize a FalkorDB Node (or already-encoded dict) to a flat payload.

    ``encode_node`` returns ``{id, labels, properties: {...}}`` because Node
    properties live on a nested attribute. Agents want a flat record, and
    they also want a single ``label`` (the meaningful one — File, Class,
    Function — not the fulltext-index marker ``Searchable``).
    """
    if hasattr(n, "properties"):
        props = dict(n.properties or {})
        labels = list(n.labels or [])
        node_id = getattr(n, "id", None)
    else:
        d = dict(n)
        props = dict(d.get("properties") or {})
        labels = list(d.get("labels") or [])
        node_id = d.get("id")

    label = next((lbl for lbl in labels if lbl != "Searchable"), None)
    return {
        "id": node_id,
        "name": props.get("name"),
        "label": label,
        "file": props.get("path"),
        "line": props.get("src_start"),
    }


def _coerce_node_id(symbol_id: Any) -> int:
    """Accept int or stringified int; raise ValueError otherwise.

    The MCP wire format is JSON; agents sometimes hand back the id as a
    string. Be permissive on input, strict on type after parsing.
    """
    if isinstance(symbol_id, bool):  # bool is an int subclass; reject loudly
        raise ValueError(f"symbol_id must be an integer, got bool: {symbol_id!r}")
    if isinstance(symbol_id, int):
        return symbol_id
    if isinstance(symbol_id, str) and symbol_id.lstrip("-").isdigit():
        return int(symbol_id)
    raise ValueError(f"symbol_id must be an integer id, got: {symbol_id!r}")


async def _neighbors_payload(
    project: str,
    branch: Optional[str],
    symbol_id: Any,
    rel: str,
    direction: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Shared implementation for caller/callee/dependency tools.

    ``direction`` is ``IN`` (incoming edges, e.g. callers) or ``OUT``
    (outgoing edges, e.g. callees). When ``IN`` we run the inverse Cypher
    ``(neighbor)-[:rel]->(target)``; ``AsyncGraphQuery.get_neighbors`` only
    walks outgoing edges, so we inline the Cypher here for symmetry.
    """
    node_id = _coerce_node_id(symbol_id)
    g = _project_arg(project, branch)
    try:
        if direction == "OUT":
            q = (
                f"MATCH (n)-[e:{rel}]->(dest) "
                f"WHERE ID(n) = $sid "
                f"RETURN dest, type(e) AS rel "
                f"LIMIT $limit"
            )
        elif direction == "IN":
            q = (
                f"MATCH (src)-[e:{rel}]->(n) "
                f"WHERE ID(n) = $sid "
                f"RETURN src AS dest, type(e) AS rel "
                f"LIMIT $limit"
            )
        else:
            raise ValueError(f"direction must be IN or OUT, got: {direction!r}")

        res = await g._query(q, {"sid": node_id, "limit": int(limit)})
        out: list[dict[str, Any]] = []
        for row in res.result_set:
            entry = _node_summary(row[0])
            entry["relation"] = row[1]
            entry["direction"] = direction
            out.append(entry)
        return out
    finally:
        await g.close()


@app.tool(
    name="get_callers",
    description=(
        "Return functions that call the given symbol (incoming CALLS edges). "
        "`symbol_id` is the integer node id returned by `search_code` or "
        "other tools."
    ),
)
async def get_callers(
    symbol_id: Any,
    project: str,
    branch: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return await _neighbors_payload(project, branch, symbol_id, "CALLS", "IN", limit)


@app.tool(
    name="get_callees",
    description=(
        "Return functions that the given symbol calls (outgoing CALLS edges)."
    ),
)
async def get_callees(
    symbol_id: Any,
    project: str,
    branch: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return await _neighbors_payload(project, branch, symbol_id, "CALLS", "OUT", limit)


@app.tool(
    name="get_dependencies",
    description=(
        "Return outgoing neighbors of the given symbol across any of the "
        "specified relation types (default: IMPORTS, CALLS, DEFINES). "
        "Useful for 'what does this depend on' queries."
    ),
)
async def get_dependencies(
    symbol_id: Any,
    project: str,
    branch: Optional[str] = None,
    rels: Optional[list[str]] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if rels is None:
        rels = ["IMPORTS", "CALLS", "DEFINES"]
    # Aggregate across relations; preserve ordering and dedupe by id.
    seen: set[Any] = set()
    out: list[dict[str, Any]] = []
    for rel in rels:
        rows = await _neighbors_payload(project, branch, symbol_id, rel, "OUT", limit)
        for row in rows:
            key = (row.get("id"), row.get("relation"))
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
            if len(out) >= limit:
                return out
    return out


# ---------------------------------------------------------------------------
# T7 — find_path
# ---------------------------------------------------------------------------


@app.tool(
    name="find_path",
    description=(
        "Return up to `max_paths` CALLS-path sequences from `source_id` to "
        "`dest_id`. Useful for 'how does A reach B' questions. Returns an "
        "empty list when no path exists."
    ),
)
async def find_path(
    source_id: Any,
    dest_id: Any,
    project: str,
    branch: Optional[str] = None,
    max_paths: int = 10,
) -> list[dict[str, Any]]:
    src = _coerce_node_id(source_id)
    dst = _coerce_node_id(dest_id)
    g = _project_arg(project, branch)
    try:
        raw = await g.find_paths(src, dst)
    finally:
        await g.close()

    # ``AsyncGraphQuery.find_paths`` returns each path as an alternating
    # [node, edge, node, edge, ..., node] list; we strip edges and surface
    # only the node sequence — that's what agents typically want.
    paths: list[dict[str, Any]] = []
    for entry in raw[:max_paths]:
        node_seq = [
            _node_summary(x)
            for x in entry
            # Edges in the alternating list carry a top-level ``relation``
            # key (from ``encode_edge``); nodes carry ``properties``.
            if isinstance(x, dict) and "properties" in x
        ]
        paths.append({"path": node_seq})
    return paths


# ---------------------------------------------------------------------------
# T8 — search_code
# ---------------------------------------------------------------------------


@app.tool(
    name="search_code",
    description=(
        "Prefix-search for symbols (functions, classes, files) whose name "
        "starts with `prefix`. Backed by FalkorDB's full-text index. The "
        "agent typically calls this first to discover symbol ids for the "
        "navigation tools (`get_callers`, `find_path`, ...)."
    ),
)
async def search_code(
    prefix: str,
    project: str,
    branch: Optional[str] = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    g = _project_arg(project, branch)
    try:
        raw = await g.prefix_search(prefix)
    finally:
        await g.close()
    return [_node_summary(node) for node in raw[:limit]]


# ---------------------------------------------------------------------------
# T6 — impact_analysis (variable-depth Cypher with DISTINCT for cycle safety)
# ---------------------------------------------------------------------------


IMPACT_MAX_DEPTH = 10
"""Hard cap on traversal depth — passed values above this are silently
clamped. Prevents pathological queries (e.g. depth=999) from hammering
FalkorDB while still letting agents request "deep" impact without
hitting an error."""


def _clamp_depth(depth: Any) -> int:
    """Coerce ``depth`` to ``1..IMPACT_MAX_DEPTH``. Strings accepted."""
    if isinstance(depth, bool):
        raise ValueError(f"depth must be an integer, got bool: {depth!r}")
    if isinstance(depth, str) and depth.lstrip("-").isdigit():
        depth = int(depth)
    if not isinstance(depth, int):
        raise ValueError(f"depth must be an integer, got: {depth!r}")
    if depth < 1:
        return 1
    if depth > IMPACT_MAX_DEPTH:
        return IMPACT_MAX_DEPTH
    return depth


@app.tool(
    name="impact_analysis",
    description=(
        "Transitive call-graph impact for refactoring: "
        "`direction='IN'` returns all upstream callers (what breaks if you "
        "change this symbol); `direction='OUT'` returns all downstream "
        "callees (what this symbol indirectly depends on). Traverses only "
        f"CALLS edges. Depth is clamped to {IMPACT_MAX_DEPTH}; cycles are "
        "deduplicated via Cypher DISTINCT (each node appears at most once)."
    ),
)
async def impact_analysis(
    symbol_id: Any,
    project: str,
    branch: Optional[str] = None,
    direction: str = "IN",
    depth: int = 3,
) -> list[dict[str, Any]]:
    node_id = _coerce_node_id(symbol_id)
    eff_depth = _clamp_depth(depth)

    if direction == "IN":
        # Upstream callers: (impacted) -[:CALLS*]-> (n)
        q = (
            f"MATCH (n)<-[:CALLS*1..{eff_depth}]-(impacted) "
            f"WHERE ID(n) = $sid "
            f"RETURN DISTINCT impacted"
        )
    elif direction == "OUT":
        # Downstream callees: (n) -[:CALLS*]-> (impacted)
        q = (
            f"MATCH (n)-[:CALLS*1..{eff_depth}]->(impacted) "
            f"WHERE ID(n) = $sid "
            f"RETURN DISTINCT impacted"
        )
    else:
        raise ValueError(
            f"direction must be 'IN' (upstream) or 'OUT' (downstream), "
            f"got: {direction!r}"
        )

    g = _project_arg(project, branch)
    try:
        res = await g._query(q, {"sid": node_id})
    finally:
        await g.close()

    out: list[dict[str, Any]] = []
    for row in res.result_set:
        entry = _node_summary(row[0])
        entry["direction"] = direction
        out.append(entry)
    return out
