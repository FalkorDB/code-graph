"""Compare two model runs of the SWE-bench fix benchmark (e.g. Opus vs Sonnet).

Reads two results.jsonl files (same instance set, same 4 configs) and reports,
per config: resolved accuracy, summed input/output tokens, and estimated USD
cost under list pricing. Prints a paired Opus-vs-Sonnet table and the overall
price delta.

Token accounting note: `input_tokens` here is the cumulative count the agent
loop sends across all steps (history is re-sent each turn), so it is "tokens
processed", not unique context. We price it as-is and apply the SAME accounting
to both models, so the *ratio* is the honest comparison; absolute dollars are
an upper bound for a no-prompt-caching setup.

Usage:
    python -m bench.runners.compare_models \
        --a bench/cache/opus/results.jsonl --a-name opus --a-model opus \
        --b bench/cache/sonnet-n40/results.jsonl --b-name sonnet --b-model sonnet
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

# List price per 1M tokens (USD), input / output.
PRICING = {
    "opus": (15.0, 75.0),      # Claude Opus 4.x
    "sonnet": (3.0, 15.0),     # Claude Sonnet 4.5
    "haiku": (0.80, 4.0),
}

CONFIG_ORDER = ["baseline", "lsp", "code_graph", "code_graph_mcp"]


def load(path: Path) -> dict[str, list[dict[str, Any]]]:
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        by[r.get("config", "?")].append(r)
    return by


def cost_usd(in_tok: int, out_tok: int, model: str) -> float:
    pin, pout = PRICING[model]
    return in_tok / 1e6 * pin + out_tok / 1e6 * pout


def config_stats(rows: list[dict[str, Any]], model: str) -> dict[str, Any]:
    n = len(rows)
    in_sum = sum(r.get("input_tokens", 0) for r in rows)
    out_sum = sum(r.get("output_tokens", 0) for r in rows)
    resolved = sum(1 for r in rows if r.get("outcome") == "resolved")
    return {
        "n": n,
        "in_sum": in_sum,
        "out_sum": out_sum,
        "resolved": resolved,
        "acc": round(100 * resolved / n, 1) if n else 0.0,
        "usd": round(cost_usd(in_sum, out_sum, model), 2),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a", type=Path, required=True)
    p.add_argument("--a-name", default="A")
    p.add_argument("--a-model", default="opus", choices=list(PRICING))
    p.add_argument("--b", type=Path, required=True)
    p.add_argument("--b-name", default="B")
    p.add_argument("--b-model", default="sonnet", choices=list(PRICING))
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)

    a = load(args.a)
    b = load(args.b)
    configs = [c for c in CONFIG_ORDER if c in a or c in b]

    report: dict[str, Any] = {"a": args.a_name, "b": args.b_name, "configs": {}}
    print(f"\n{'config':>16} | {args.a_name:>26} | {args.b_name:>26} | price")
    print(f"{'':>16} | {'acc   in_tok   out_tok    $':>26} | "
          f"{'acc   in_tok   out_tok    $':>26} | A/B$")
    print("-" * 92)
    tot_a_usd = tot_b_usd = 0.0
    for c in configs:
        sa = config_stats(a.get(c, []), args.a_model)
        sb = config_stats(b.get(c, []), args.b_model)
        tot_a_usd += sa["usd"]
        tot_b_usd += sb["usd"]
        ratio = round(sa["usd"] / sb["usd"], 2) if sb["usd"] else None
        report["configs"][c] = {"a": sa, "b": sb, "price_ratio_a_over_b": ratio}
        print(f"{c:>16} | {sa['acc']:>4}% {sa['in_sum']:>9} {sa['out_sum']:>7} "
              f"${sa['usd']:>7} | {sb['acc']:>4}% {sb['in_sum']:>9} "
              f"{sb['out_sum']:>7} ${sb['usd']:>7} | {ratio}x")

    print("-" * 92)
    print(f"{'TOTAL $':>16} | {'':>19}${tot_a_usd:>7.2f} | "
          f"{'':>19}${tot_b_usd:>7.2f} | "
          f"{round(tot_a_usd / tot_b_usd, 2) if tot_b_usd else None}x")
    report["total"] = {
        "a_usd": round(tot_a_usd, 2),
        "b_usd": round(tot_b_usd, 2),
        "a_over_b": round(tot_a_usd / tot_b_usd, 2) if tot_b_usd else None,
    }

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2))
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
