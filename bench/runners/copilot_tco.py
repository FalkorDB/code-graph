"""Total-cost-of-ownership (TCO) accounting for the Copilot benchmark tracks.

Copilot's own token accounting captures only the **agent model** spend. For the
``code_graph`` track the *true* cost has three more components that the agent's
token count never sees:

    1. **Indexing** -- one-time CPU to build the FalkorDB graph. With the
       tree-sitter resolver (``CODE_GRAPH_PY_RESOLVER=tree_sitter``) this is
       **LLM-free**, so it is pure compute that amortizes across every later
       query of the same repo. We report it as wall-seconds (and an optional
       compute-$ estimate), never blended into the per-task model cost.
    2. **FalkorDB hosting** -- a standing graph DB. Amortizable infra, reported
       as a flat note, not a per-task charge.
    3. **GraphRAG ``ask`` side-LLM** -- the ONLY code-graph tool that calls an
       LLM (NL->Cypher via ``MODEL_NAME``, default gemini-flash-lite). The
       headline tracks exclude ``ask`` so this is normally **$0**; if a run does
       call it, ``graphrag_*`` fields on the row meter it and it is added here.

So the headline takeaway: with ``ask`` excluded and tree-sitter indexing, the
code-graph track adds **zero per-task side-LLM cost** over the no-MCP control --
its only delta is amortizable infra. This module makes that explicit and prices
any ``ask`` usage when present.

Usage:
    uv run python -m bench.runners.copilot_tco --results <results.jsonl>
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

# List price per 1M tokens (USD): input / output. Illustrative (non-billing).
AGENT_PRICING = {
    "opus": (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku": (0.80, 4.0),
}

# GraphRAG `ask` underlying model price per 1M tokens (input/output).
# Default MODEL_NAME is gemini/gemini-flash-lite-latest. Illustrative.
GRAPHRAG_PRICING = {
    "gemini-flash-lite": (0.075, 0.30),
    "gemini-flash": (0.15, 0.60),
}
DEFAULT_GRAPHRAG_MODEL = "gemini-flash-lite"

# Rough on-demand compute price for indexing wall-time (1 vCPU-hour). Illustrative.
INDEX_CPU_USD_PER_HOUR = 0.05


def agent_key(model: str) -> str:
    """Map a Copilot model id (or shorthand) to an AGENT_PRICING key."""
    m = model.lower()
    if "opus" in m:
        return "opus"
    if "sonnet" in m:
        return "sonnet"
    if "haiku" in m:
        return "haiku"
    return "sonnet"


def agent_cost_usd(in_tok: int, out_tok: int, model: str) -> float:
    pin, pout = AGENT_PRICING[agent_key(model)]
    return in_tok / 1e6 * pin + out_tok / 1e6 * pout


def graphrag_cost_usd(in_tok: int, out_tok: int, model: str = DEFAULT_GRAPHRAG_MODEL) -> float:
    pin, pout = GRAPHRAG_PRICING.get(model, GRAPHRAG_PRICING[DEFAULT_GRAPHRAG_MODEL])
    return in_tok / 1e6 * pin + out_tok / 1e6 * pout


def index_cost_usd(index_sec: float | None) -> float:
    if not index_sec:
        return 0.0
    return index_sec / 3600.0 * INDEX_CPU_USD_PER_HOUR


def row_tco(row: dict[str, Any]) -> dict[str, Any]:
    """Full TCO breakdown for a single result row."""
    model = row.get("model", "claude-sonnet-4.6")
    in_tok = int(row.get("input_tokens", 0) or 0)
    out_tok = int(row.get("output_tokens", 0) or 0)
    agent_usd = agent_cost_usd(in_tok, out_tok, model)

    g_in = int(row.get("graphrag_input_tokens", 0) or 0)
    g_out = int(row.get("graphrag_output_tokens", 0) or 0)
    g_calls = int(row.get("graphrag_ask_calls", 0) or 0)
    g_usd = graphrag_cost_usd(g_in, g_out) if (g_in or g_out) else 0.0

    idx_usd = index_cost_usd(row.get("index_sec"))

    return {
        "task_id": row.get("task_id"),
        "config": row.get("config"),
        "model": model,
        "agent_input_tokens": in_tok,
        "agent_output_tokens": out_tok,
        "agent_usd": round(agent_usd, 4),
        "premium_requests": int(row.get("premium_requests", 0) or 0),
        "graphrag_ask_calls": g_calls,
        "graphrag_tokens": g_in + g_out,
        "graphrag_usd": round(g_usd, 4),
        "index_sec": row.get("index_sec"),
        "index_usd_amortized_once": round(idx_usd, 4),
        # Per-task TCO = agent model + any ask side-LLM. Indexing is reported
        # separately because it amortizes across all queries of the repo.
        "per_task_tco_usd": round(agent_usd + g_usd, 4),
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if not r.get("completed"):
            continue
        by[r.get("config", "?")].append(r)

    out: dict[str, dict[str, Any]] = {}
    for cfg, crows in by.items():
        n = len(crows)
        tcos = [row_tco(r) for r in crows]
        agent = sum(t["agent_usd"] for t in tcos)
        graphrag = sum(t["graphrag_usd"] for t in tcos)
        index = sum(t["index_usd_amortized_once"] for t in tcos)
        premium = sum(t["premium_requests"] for t in tcos)
        ask_calls = sum(t["graphrag_ask_calls"] for t in tcos)
        resolved = sum(1 for r in crows if r.get("outcome") == "resolved")
        out[cfg] = {
            "n": n,
            "resolved": resolved,
            "agent_usd": round(agent, 2),
            "graphrag_ask_calls": ask_calls,
            "graphrag_usd": round(graphrag, 4),
            "index_usd_one_time": round(index, 4),
            "premium_requests": premium,
            "per_task_tco_usd_sum": round(agent + graphrag, 2),
            "per_task_tco_usd_mean": round((agent + graphrag) / n, 4) if n else 0.0,
        }
    return out


def _load(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="TCO accounting for Copilot benchmark runs.")
    p.add_argument("--results", required=True, help="results jsonl")
    p.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = p.parse_args(argv)

    rows = _load(Path(args.results))
    agg = aggregate(rows)

    if args.json:
        print(json.dumps(agg, indent=2))
        return 0

    print(f"\nTCO by track  ({Path(args.results).name})\n")
    hdr = (
        f"{'track':>16} | {'n':>3} | {'resolved':>8} | {'agent $':>9} | "
        f"{'ask calls':>9} | {'ask $':>7} | {'index $ (1x)':>12} | "
        f"{'premium':>7} | {'TCO $/task':>10}"
    )
    print(hdr)
    print("-" * len(hdr))
    for cfg in sorted(agg):
        s = agg[cfg]
        print(
            f"{cfg:>16} | {s['n']:>3} | {s['resolved']:>8} | "
            f"{s['agent_usd']:>9.2f} | {s['graphrag_ask_calls']:>9} | "
            f"{s['graphrag_usd']:>7.4f} | {s['index_usd_one_time']:>12.4f} | "
            f"{s['premium_requests']:>7} | {s['per_task_tco_usd_mean']:>10.4f}"
        )
    print(
        "\nNotes: agent $ = Copilot model tokens (list price). ask $ = GraphRAG "
        "side-LLM (0 when `ask` excluded). index $ = one-time tree-sitter "
        "indexing CPU, amortizes across all queries (LLM-free). FalkorDB hosting "
        "is standing infra, not charged per task. Premium requests are Copilot's "
        "real billing unit -- reported separately, never blended into $."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
