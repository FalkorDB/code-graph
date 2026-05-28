"""`cg-mcp` — bash-callable CLI exposing code-graph's 8 MCP tools.

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
  cg-mcp ask              --project P --question "..." [--branch B]

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


def _print(obj: Any) -> None:
    json.dump(obj, sys.stdout, indent=2, sort_keys=True, default=str)
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

    fp = sub.add_parser("find_path")
    _add_project(fp)
    fp.add_argument("--source-id", type=int, required=True, dest="source_id")
    fp.add_argument("--dest-id", type=int, required=True, dest="dest_id")

    aq = sub.add_parser("ask")
    _add_project(aq)
    aq.add_argument("--question", required=True)

    args = parser.parse_args(argv)
    timeout = _timeout()

    # Inject timeout for adapter calls.
    cgm.DEFAULT_TIMEOUT_SEC = timeout

    try:
        if args.cmd == "index_repo":
            _print(cgm.index_repo(args.path_or_url, branch=args.branch, ignore=args.ignore))
        elif args.cmd == "search_code":
            _print(cgm.search_code(args.prefix, args.project, branch=args.branch, limit=args.limit))
        elif args.cmd == "get_callers":
            _print(cgm.get_callers(args.symbol_id, args.project, branch=args.branch, limit=args.limit))
        elif args.cmd == "get_callees":
            _print(cgm.get_callees(args.symbol_id, args.project, branch=args.branch, limit=args.limit))
        elif args.cmd == "get_dependencies":
            _print(cgm.get_dependencies(args.symbol_id, args.project, branch=args.branch, limit=args.limit))
        elif args.cmd == "impact_analysis":
            _print(
                cgm.impact_analysis(
                    args.symbol_id,
                    args.project,
                    branch=args.branch,
                    direction=args.direction,
                    depth=args.depth,
                )
            )
        elif args.cmd == "find_path":
            _print(cgm.find_path(args.source_id, args.dest_id, args.project, branch=args.branch))
        elif args.cmd == "ask":
            _print(cgm.ask(args.question, args.project, branch=args.branch))
        else:  # pragma: no cover — argparse already enforces this
            parser.error(f"unknown subcommand: {args.cmd}")
    except Exception as e:  # noqa: BLE001 — surface everything to the agent
        print(f"cg-mcp error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
