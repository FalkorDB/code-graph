"""CLI: render bench/cache/results.jsonl as a markdown summary.

Usage:
    uv run python -m bench.report \\
        --input bench/cache/results.jsonl \\
        --output bench/cache/report.md

Defaults to bench/cache/results.jsonl → bench/cache/report.md. Also
prints the rendered markdown to stdout so it can be piped to a PR
body or pasted into an issue.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from bench.report import aggregate_to_markdown, load_jsonl, render_markdown, summarize

DEFAULT_INPUT = Path(__file__).resolve().parents[1] / "cache" / "results.jsonl"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "cache" / "report.md"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="render benchmark results as markdown")
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--quiet", action="store_true", help="don't echo markdown to stdout")
    args = p.parse_args(argv)

    if not args.input.exists():
        print(f"error: input not found: {args.input}")
        return 1

    rows = load_jsonl(args.input)
    if not rows:
        print("error: input has no rows")
        return 1
    md = render_markdown(summarize(rows))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(md)
    if not args.quiet:
        print(md)
    print(f"\n[report] {len(rows)} row(s) -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
