"""`lsp` — bash-callable CLI exposing LSP primitives.

mini-swe-agent only uses bash, so we surface multilspy/jedi as a small
CLI the agent can invoke. Wraps bench/agents/lsp_adapter.

Usage examples (run inside the agent's bash environment):

  lsp goto-definition  --file path/to/x.py --line 12 --col 4
  lsp find-references  --file path/to/x.py --line 12 --col 4
  lsp hover            --file path/to/x.py --line 12 --col 4
  lsp document-symbols --file path/to/x.py

Required env vars (set by the runner):
  LSP_REPO_ROOT   absolute path to the repo being analyzed
  LSP_LANGUAGE    optional; defaults to "python"

Startup cost: each invocation spawns its own LSP subprocess (~1-3s
warm). For tasks where the agent makes many LSP calls, the runner can
keep a long-lived server by setting LSP_SERVER_FIFO; that's a future
optimization — for now we accept the per-call cost in exchange for the
simpler subprocess.run model mini-swe-agent uses.
"""

from __future__ import annotations

import argparse
import json
import sys

from bench.agents.lsp_adapter import _client_from_env


def _print(obj: object) -> None:
    json.dump(obj, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lsp", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_pos(p: argparse.ArgumentParser) -> None:
        p.add_argument("--file", required=True)
        p.add_argument("--line", type=int, required=True)
        p.add_argument("--col", type=int, required=True)

    gd = sub.add_parser("goto-definition")
    add_pos(gd)

    fr = sub.add_parser("find-references")
    add_pos(fr)

    hv = sub.add_parser("hover")
    add_pos(hv)

    ds = sub.add_parser("document-symbols")
    ds.add_argument("--file", required=True)

    args = parser.parse_args(argv)

    client = _client_from_env()
    with client.server_running() as c:
        if args.cmd == "goto-definition":
            _print(c.goto_definition(args.file, args.line, args.col))
        elif args.cmd == "find-references":
            _print(c.find_references(args.file, args.line, args.col))
        elif args.cmd == "hover":
            _print(c.hover(args.file, args.line, args.col))
        elif args.cmd == "document-symbols":
            _print(c.document_symbols(args.file))
        else:
            parser.error(f"unknown command {args.cmd}")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
