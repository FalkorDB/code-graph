"""`cg` — bash-callable CLI exposing code-graph's 7 agent primitives over HTTP.

This is the HTTP-transport sibling of `cg-mcp`. Both CLIs expose the **same
verb surface** (search_code, get_callers, get_callees, get_dependencies,
impact_analysis, find_path, index_repo) over **the same underlying
async tool functions** (api.mcp.tools.structural), so a benchmark comparison
between them measures transport overhead, not API differences.

The agent calls these via bash:

  cg index_repo       --path-or-url . [--branch B] [--ignore PAT ...]
  cg search_code      --project P --prefix STR [--branch B] [--limit N]
  cg get_callers      --project P --symbol-id ID [--branch B] [--limit N]
  cg get_callees      --project P --symbol-id ID [--branch B] [--limit N]
  cg get_dependencies --project P --symbol-id ID [--branch B] [--limit N]
  cg impact_analysis  --project P --symbol-id ID [--direction IN|OUT] [--depth N] [--limit N]
  cg find_path        --project P --source-id ID --dest-id ID [--branch B]

Legacy verbs (graph-entities, get-neighbors, find-paths, auto-complete,
find-symbol, note-edit) remain for the React UI's backing tests but are
not exposed to the agent preamble.

Required env vars (set by the runner):
  CODEGRAPH_URL    base URL of the code-graph service
  SECRET_TOKEN     bearer token (omit if the server has CODE_GRAPH_PUBLIC=1)
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from bench.agents.code_graph_adapter import CodeGraphClient


# ---------------------------------------------------------------------------
# Output compaction — must match bench/cli/cg_mcp.py exactly for parity.
# ---------------------------------------------------------------------------
#
# Iter2 finding: every node returned by the v2 endpoints has an absolute
# worktree path under `file` (~130 chars). Stripping the project-name
# prefix saves ~100 chars × N entries, which compounds badly when the
# agent re-feeds tool output across 30-50 turns.

def _strip_worktree_prefix(path: Any, project: str | None) -> Any:
    if not isinstance(path, str) or not project:
        return path
    needle = f"/{project}/"
    idx = path.find(needle)
    if idx < 0:
        return path
    return path[idx + len(needle):]


def _compact_entry(entry: Any, project: str | None) -> Any:
    if not isinstance(entry, dict):
        return entry
    out: dict[str, Any] = {}
    for k, v in entry.items():
        if v in (None, "", [], {}):
            continue
        if k == "file":
            v = _strip_worktree_prefix(v, project)
        out[k] = v
    return out


def _compact_list(items: Any, project: str | None, limit: int | None) -> Any:
    if not isinstance(items, list):
        return items
    compacted = [_compact_entry(x, project) for x in items]
    if limit is not None and limit > 0:
        compacted = compacted[:limit]
    return compacted


# ---------------------------------------------------------------------------
# Legacy UI-verb compaction (kept so existing tests keep passing).
# ---------------------------------------------------------------------------

_NODE_KEEP = ("id", "label", "labels", "name", "file", "src", "line", "start_line", "end_line")
_EDGE_KEEP = ("id", "src_node", "dest_node", "relation")


def _compact_node(n: Any) -> Any:
    if not isinstance(n, dict):
        return n
    out: dict[str, Any] = {}
    props = n.get("properties") or {}
    for k in _NODE_KEEP:
        if k in n and n[k] not in (None, "", [], {}):
            out[k] = n[k]
        elif k in props and props[k] not in (None, "", [], {}):
            out[k] = props[k]
    return out


def _compact_edge(e: Any) -> Any:
    if not isinstance(e, dict):
        return e
    out: dict[str, Any] = {}
    for k in _EDGE_KEEP:
        v = e.get(k)
        if v not in (None, "", [], {}):
            out[k] = v
    return out


def _compact_neighbors(payload: dict[str, Any], limit: int | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    n = payload.get("neighbors") or payload
    nodes = [_compact_node(x) for x in (n.get("nodes") or [])]
    edges = [_compact_edge(x) for x in (n.get("edges") or [])]
    if limit is not None and limit > 0:
        nodes = nodes[:limit]
        edges = edges[:limit]
    out: dict[str, Any] = {"nodes": nodes, "edges": edges}
    if "branch" in payload:
        out["branch"] = payload["branch"]
    return out


def _compact_symbols(payload: Any) -> Any:
    if isinstance(payload, list):
        return [_compact_node(x) for x in payload]
    if isinstance(payload, dict):
        for key in ("completions", "results", "matches", "items"):
            if key in payload:
                out = {k: v for k, v in payload.items() if k != key}
                out[key] = [_compact_node(x) for x in (payload[key] or [])]
                return out
    return payload


def _print(obj: object) -> None:
    json.dump(obj, sys.stdout, separators=(",", ":"), sort_keys=True, default=str)
    sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# index_repo over HTTP. Hits /api/analyze_folder; for parity we keep the
# same kwargs as cg-mcp.
# ---------------------------------------------------------------------------

def _index_repo(c: CodeGraphClient, path_or_url: str,
                branch: str | None, ignore: list[str] | None) -> dict[str, Any]:
    """Mirror cg-mcp index_repo but go through HTTP /api/analyze_folder."""
    body: dict[str, Any] = {"path": path_or_url, "ignore": ignore or []}
    if branch:
        body["branch"] = branch
    r = c._client.post("/api/analyze_folder", json=body)
    r.raise_for_status()
    return r.json()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cg", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def _add_project(p: argparse.ArgumentParser) -> None:
        p.add_argument("--project", required=True)
        p.add_argument("--branch", default=None)

    def _add_symbol(p: argparse.ArgumentParser) -> None:
        p.add_argument("--symbol-id", type=int, required=True, dest="symbol_id")
        p.add_argument("--limit", type=int, default=50)

    # ---- v2 (MCP-parity) verbs ----
    ir = sub.add_parser("index_repo")
    ir.add_argument("--path-or-url", required=True, dest="path_or_url")
    ir.add_argument("--branch", default=None)
    ir.add_argument("--ignore", nargs="*", default=None)

    sc = sub.add_parser("search_code")
    _add_project(sc)
    sc.add_argument("--prefix", required=True)
    sc.add_argument("--limit", type=int, default=10)

    for name in ("get_callers", "get_callees", "get_dependencies"):
        p = sub.add_parser(name)
        _add_project(p)
        _add_symbol(p)

    ia = sub.add_parser("impact_analysis")
    _add_project(ia)
    ia.add_argument("--symbol-id", type=int, required=True, dest="symbol_id")
    ia.add_argument("--direction", choices=["IN", "OUT"], default="IN")
    ia.add_argument("--depth", type=int, default=3)
    ia.add_argument("--limit", type=int, default=50)

    fp2 = sub.add_parser("find_path")
    _add_project(fp2)
    fp2.add_argument("--source-id", type=int, required=True, dest="source_id")
    fp2.add_argument("--dest-id", type=int, required=True, dest="dest_id")

    # ---- legacy UI verbs (kept for existing tests) ----
    def add_repo(p: argparse.ArgumentParser) -> None:
        p.add_argument("--repo", required=True)

    ge = sub.add_parser("graph-entities"); add_repo(ge)
    gn = sub.add_parser("get-neighbors"); add_repo(gn)
    gn.add_argument("--ids", type=int, nargs="+", required=True)
    gn.add_argument("--limit", type=int, default=50)
    fp = sub.add_parser("find-paths"); add_repo(fp)
    fp.add_argument("--src", type=int, required=True)
    fp.add_argument("--dst", type=int, required=True)
    ac = sub.add_parser("auto-complete"); add_repo(ac)
    ac.add_argument("--prefix", required=True)
    fs = sub.add_parser("find-symbol"); add_repo(fs)
    fs.add_argument("--name", required=True)
    ne = sub.add_parser("note-edit"); add_repo(ne)
    ne.add_argument("--path", required=True)

    args = parser.parse_args(argv)

    with CodeGraphClient() as c:
        proj = getattr(args, "project", None)
        # ---- v2 verbs ----
        if args.cmd == "index_repo":
            _print(_index_repo(c, args.path_or_url, args.branch, args.ignore))
        elif args.cmd == "search_code":
            _print(_compact_list(
                c.search_code(args.project, args.prefix, branch=args.branch, limit=args.limit),
                proj, args.limit,
            ))
        elif args.cmd == "get_callers":
            _print(_compact_list(
                c.get_callers(args.project, args.symbol_id, branch=args.branch, limit=args.limit),
                proj, args.limit,
            ))
        elif args.cmd == "get_callees":
            _print(_compact_list(
                c.get_callees(args.project, args.symbol_id, branch=args.branch, limit=args.limit),
                proj, args.limit,
            ))
        elif args.cmd == "get_dependencies":
            _print(_compact_list(
                c.get_dependencies(args.project, args.symbol_id, branch=args.branch, limit=args.limit),
                proj, args.limit,
            ))
        elif args.cmd == "impact_analysis":
            _print(_compact_list(
                c.impact_analysis(
                    args.project, args.symbol_id, branch=args.branch,
                    direction=args.direction, depth=args.depth,
                ),
                proj, args.limit,
            ))
        elif args.cmd == "find_path":
            _print(_compact_entry(
                c.find_path_v2(args.project, args.source_id, args.dest_id, branch=args.branch),
                proj,
            ))
        # ---- legacy verbs ----
        elif args.cmd == "graph-entities":
            _print(c.graph_entities(args.repo))
        elif args.cmd == "get-neighbors":
            limit = args.limit if args.limit > 0 else None
            _print(_compact_neighbors(c.get_neighbors(args.repo, args.ids), limit))
        elif args.cmd == "find-paths":
            _print(c.find_paths(args.repo, args.src, args.dst))
        elif args.cmd == "auto-complete":
            _print(_compact_symbols(c.auto_complete(args.repo, args.prefix)))
        elif args.cmd == "find-symbol":
            _print(_compact_symbols(c.find_symbol(args.repo, args.name)))
        elif args.cmd == "note-edit":
            _print(c.note_edit(args.repo, args.path))
        else:
            parser.error(f"unknown command {args.cmd}")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
