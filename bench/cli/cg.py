"""`cg` — bash-callable CLI exposing code-graph primitives.

mini-swe-agent only uses bash, so each "tool" we want the agent to have is
just a CLI it can invoke. This script wraps bench/agents/code_graph_adapter
behind a small argparse interface and prints JSON results to stdout, one
JSON document per call.

Usage examples (run inside the agent's bash environment):

  cg graph-entities --repo django
  cg get-neighbors  --repo django --ids 12 14 17
  cg find-paths     --repo django --src 12 --dst 88
  cg auto-complete  --repo django --prefix get_user
  cg find-symbol    --repo django --name get_user_model
  cg note-edit      --repo django --path src/django/contrib/auth/models.py

Required env vars (set by the runner):
  CODEGRAPH_URL    base URL of the code-graph service
  SECRET_TOKEN     bearer token (omit if the server has CODE_GRAPH_PUBLIC=1)
"""

from __future__ import annotations

import argparse
import json
import sys

from bench.agents.code_graph_adapter import CodeGraphClient


def _print(obj: object) -> None:
    json.dump(obj, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cg", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_repo(p: argparse.ArgumentParser) -> None:
        p.add_argument("--repo", required=True, help="repository name in the graph")

    ge = sub.add_parser("graph-entities")
    add_repo(ge)

    gn = sub.add_parser("get-neighbors")
    add_repo(gn)
    gn.add_argument("--ids", type=int, nargs="+", required=True)

    fp = sub.add_parser("find-paths")
    add_repo(fp)
    fp.add_argument("--src", type=int, required=True)
    fp.add_argument("--dst", type=int, required=True)

    ac = sub.add_parser("auto-complete")
    add_repo(ac)
    ac.add_argument("--prefix", required=True)

    fs = sub.add_parser("find-symbol")
    add_repo(fs)
    fs.add_argument("--name", required=True)

    ne = sub.add_parser("note-edit")
    add_repo(ne)
    ne.add_argument("--path", required=True)

    args = parser.parse_args(argv)

    with CodeGraphClient() as c:
        if args.cmd == "graph-entities":
            _print(c.graph_entities(args.repo))
        elif args.cmd == "get-neighbors":
            _print(c.get_neighbors(args.repo, args.ids))
        elif args.cmd == "find-paths":
            _print(c.find_paths(args.repo, args.src, args.dst))
        elif args.cmd == "auto-complete":
            _print(c.auto_complete(args.repo, args.prefix))
        elif args.cmd == "find-symbol":
            _print(c.find_symbol(args.repo, args.name))
        elif args.cmd == "note-edit":
            _print(c.note_edit(args.repo, args.path))
        else:
            parser.error(f"unknown command {args.cmd}")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
