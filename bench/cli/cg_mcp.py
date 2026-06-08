"""`cg-mcp` — bash-callable CLI exposing code-graph's 7 MCP tools.

This is the MCP-transport sibling of `cg`. Where `cg` calls the host
FastAPI service over HTTP, `cg-mcp` spawns the `cgraph-mcp` stdio
server (via the official MCP Python SDK) for every invocation and
dispatches one tool call.

The MCP track is what external agents (Claude Code, Cursor, …) use
in production; benchmarking through it tells us how the *real-world*
integration behaves under SWE-bench, not just the in-process FastAPI
adapter.

Subcommands mirror the MCP tool names:

  cg-mcp index_repo       --path-or-url . [--branch B] [--ignore PAT ...]
  cg-mcp search_code      --project P --prefix STR [--branch B] [--limit N]
  cg-mcp get_callers      --project P --symbol-id ID [--branch B] [--limit N]
  cg-mcp get_callees      --project P --symbol-id ID [--branch B] [--limit N]
  cg-mcp get_dependencies --project P --symbol-id ID [--branch B] [--limit N]
  cg-mcp impact_analysis  --project P --symbol-id ID [--direction IN|OUT] [--depth N]
  cg-mcp find_path        --project P --source-id ID --dest-id ID [--branch B]

Output: one JSON document per call on stdout. Errors print to stderr
and exit non-zero.

Env: FALKORDB_HOST / FALKORDB_PORT are passed through to the spawned
server. Optionally set CGRAPH_MCP_TIMEOUT_SEC to override the
default 900s timeout.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from bench.agents import code_graph_mcp_adapter as cgm


# ---------------------------------------------------------------------------
# Output compaction (iter2): keep token budget bounded
# ---------------------------------------------------------------------------
#
# Iter1 (chunk-fix) un-broke list returns from the MCP layer. That exposed
# two unbounded payload sources that re-feed every LLM turn:
#
#   1. `impact_analysis` has no `--limit` — a depth=3 traversal on a
#      large project (sympy: 142k edges) routinely returns 500+ nodes.
#   2. Every node's `file` field is an absolute worktree path
#      (`/Users/.../worktrees/<project>/sympy/printing/latex.py`,
#      ~130 chars). The 100+-char prefix is repeated for every entry and
#      contributes nothing the agent can act on.
#
# We strip the worktree prefix and cap list outputs at the CLI layer so the
# MCP server tools stay unchanged. Caps default to 50 (matches the other
# tool CLIs) and can be overridden per call.

# Heuristic worktree-prefix patterns we want to strip from `file` fields.
# We match in order; first hit wins. The "/<project>/" segment is added
# dynamically at call time because the project name is per-invocation.
_WORKTREE_FRAGMENTS = (
    "/.worktrees/",         # git worktree layout
    "/bench/cache/worktrees/",  # bench harness layout
)


def _strip_worktree_prefix(path: Any, project: str | None) -> Any:
    """Convert an absolute file path under a project worktree to repo-relative.

    Returns the input unchanged for non-strings or paths we don't recognize.
    """
    if not isinstance(path, str) or not project:
        return path
    needle = f"/{project}/"
    idx = path.find(needle)
    if idx < 0:
        return path
    return path[idx + len(needle):]


def _compact_entry(entry: Any, project: str | None) -> Any:
    """Drop noise from a single node-summary dict."""
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
    """Apply `_compact_entry` + truncate to `limit`."""
    if not isinstance(items, list):
        return items
    compacted = [_compact_entry(x, project) for x in items]
    if limit is not None and limit > 0:
        compacted = compacted[:limit]
    return compacted


def _print(obj: Any) -> None:
    # Compact JSON: agents don't care about indentation, and every byte we
    # save here is re-fed to the LLM every subsequent turn.
    json.dump(obj, sys.stdout, separators=(",", ":"), sort_keys=True, default=str)
    sys.stdout.write("\n")


def _timeout() -> float:
    try:
        return float(os.getenv("CGRAPH_MCP_TIMEOUT_SEC", "900"))
    except ValueError:
        return 900.0


def _add_project(p: argparse.ArgumentParser) -> None:
    p.add_argument("--project", required=True)
    p.add_argument("--branch", default=None)


def _add_symbol(p: argparse.ArgumentParser) -> None:
    p.add_argument("--symbol-id", type=int, required=True, dest="symbol_id")
    p.add_argument("--limit", type=int, default=50)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cg-mcp", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

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
    # Iter2: cap output. impact_analysis on large graphs (sympy: 142k edges)
    # routinely returns 500+ entries. Default 50 matches the other tools.
    ia.add_argument("--limit", type=int, default=50)

    fp = sub.add_parser("find_path")
    _add_project(fp)
    fp.add_argument("--source-id", type=int, required=True, dest="source_id")
    fp.add_argument("--dest-id", type=int, required=True, dest="dest_id")

    args = parser.parse_args(argv)
    timeout = _timeout()

    # Inject timeout for adapter calls.
    cgm.DEFAULT_TIMEOUT_SEC = timeout

    try:
        proj = getattr(args, "project", None)
        if args.cmd == "index_repo":
            _print(cgm.index_repo(args.path_or_url, branch=args.branch, ignore=args.ignore))
        elif args.cmd == "search_code":
            _print(_compact_list(
                cgm.search_code(args.prefix, args.project, branch=args.branch, limit=args.limit),
                proj, args.limit,
            ))
        elif args.cmd == "get_callers":
            _print(_compact_list(
                cgm.get_callers(args.symbol_id, args.project, branch=args.branch, limit=args.limit),
                proj, args.limit,
            ))
        elif args.cmd == "get_callees":
            _print(_compact_list(
                cgm.get_callees(args.symbol_id, args.project, branch=args.branch, limit=args.limit),
                proj, args.limit,
            ))
        elif args.cmd == "get_dependencies":
            _print(_compact_list(
                cgm.get_dependencies(args.symbol_id, args.project, branch=args.branch, limit=args.limit),
                proj, args.limit,
            ))
        elif args.cmd == "impact_analysis":
            # impact_analysis has no server-side `limit`; cap + compact in CLI.
            _print(_compact_list(
                cgm.impact_analysis(
                    args.symbol_id,
                    args.project,
                    branch=args.branch,
                    direction=args.direction,
                    depth=args.depth,
                ),
                proj, args.limit,
            ))
        elif args.cmd == "find_path":
            _print(_compact_entry(
                cgm.find_path(args.source_id, args.dest_id, args.project, branch=args.branch),
                proj,
            ))
        else:  # pragma: no cover — argparse already enforces this
            parser.error(f"unknown subcommand: {args.cmd}")
    except Exception as e:  # noqa: BLE001 — surface everything to the agent
        print(f"cg-mcp error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
