"""Robust, task-weighted aggregation for the localization benchmark.

WHY (per rubber-duck): the raw per-row means are confounded and outlier-driven:

  1. REPLICATE confound -- decision instances are run multiple times (run_idx
     0/1/2) while controls run once, so a naive mean over rows weights some
     tasks 3x. Fix: average replicates WITHIN each (task, config) first
     ("per-task cell"), then take the macro-mean ACROSS tasks. Every task then
     carries equal weight regardless of replicate count.

  2. TOKEN tail -- a single runaway trajectory (>1M input tokens) dominates the
     arithmetic mean. Fix: report median + mean + p90 + max + #runaways(>500k)
     + a winsorized mean (p90 cap) for SENSITIVITY ONLY (never as the headline,
     never silently dropping data).

  3. CONNECTIVITY stratum -- recall on graph-connected gold is the only stratum
     where the graph can mechanically help. Fix: join the connectivity label
     (all_connected / partial / unconnected) per task and report recall per
     stratum per arm.

Headline accuracy metric = task-weighted macro-mean of ``file_recall`` (and the
strict ``file_all_found`` set-exact metric) per config. Headline token metric =
per-task median input tokens + the robust tail stats.

CLI:
    python -m bench.analysis.aggregate <results.jsonl> [--conn conn.json] \
        [--json out.json] [--runaway 500000]
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def _percentile(xs: list[float], q: float) -> float:
    """Linear-interpolation percentile (q in [0,1]). Empty -> 0.0."""
    if not xs:
        return 0.0
    s = sorted(xs)
    if len(s) == 1:
        return float(s[0])
    pos = q * (len(s) - 1)
    lo = int(pos)
    frac = pos - lo
    if lo + 1 >= len(s):
        return float(s[-1])
    return float(s[lo] + (s[lo + 1] - s[lo]) * frac)


def _winsorized_mean(xs: list[float], cap_q: float = 0.90) -> float:
    """Mean after clamping values above the cap_q percentile down to it."""
    if not xs:
        return 0.0
    cap = _percentile(xs, cap_q)
    return statistics.fmean(min(x, cap) for x in xs)


def _cells(rows: list[dict], field: str) -> dict[tuple[str, str], float]:
    """Average ``field`` over replicates within each (config, task) cell."""
    buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        v = r.get(field)
        if v is None:
            continue
        buckets[(r["config"], r["task_id"])].append(float(v))
    return {k: statistics.fmean(v) for k, v in buckets.items() if v}


def _per_config(cells: dict[tuple[str, str], float]) -> dict[str, list[float]]:
    out: dict[str, list[float]] = defaultdict(list)
    for (config, _task), v in cells.items():
        out[config].append(v)
    return out


def aggregate(results_path: Path, conn_path: Path | None,
              runaway: float = 500_000) -> dict:
    rows = [json.loads(l) for l in results_path.read_text().splitlines() if l.strip()]
    configs = sorted({r["config"] for r in rows})

    conn_label: dict[str, str] = {}
    if conn_path and conn_path.exists():
        for c in json.loads(conn_path.read_text()):
            conn_label[c["task"]] = c.get("label", "unknown")

    # --- task-weighted accuracy (recall + strict all-found) ---
    recall_cells = _cells(rows, "file_recall")
    allfound_cells = _cells(rows, "file_all_found")
    recall_by_cfg = _per_config(recall_cells)
    allfound_by_cfg = _per_config(allfound_cells)

    # --- token cell means (per task) for robust stats ---
    intok_cells = _cells(rows, "input_tokens")
    intok_by_cfg = _per_config(intok_cells)

    # raw per-row input tokens (for tail stats that should see every runaway)
    intok_rows_by_cfg: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        v = r.get("input_tokens")
        if v is not None:
            intok_rows_by_cfg[r["config"]].append(float(v))

    summary = {}
    for cfg in configs:
        rec = recall_by_cfg.get(cfg, [])
        allf = allfound_by_cfg.get(cfg, [])
        intask = intok_by_cfg.get(cfg, [])
        inrows = intok_rows_by_cfg.get(cfg, [])
        summary[cfg] = {
            "n_tasks": len(rec),
            "n_rows": sum(1 for r in rows if r["config"] == cfg),
            "recall_task_weighted": round(statistics.fmean(rec), 4) if rec else None,
            "all_found_task_weighted": round(statistics.fmean(allf), 4) if allf else None,
            "tokens": {
                "median_per_task": round(statistics.median(intask)) if intask else None,
                "mean_per_task": round(statistics.fmean(intask)) if intask else None,
                "p90_per_task": round(_percentile(intask, 0.90)) if intask else None,
                "max_row": round(max(inrows)) if inrows else None,
                "n_runaways": sum(1 for x in inrows if x > runaway),
                "winsorized_mean_per_task": round(_winsorized_mean(intask)) if intask else None,
            },
        }

    # --- recall per connectivity stratum per config ---
    strata: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for (cfg, task), v in recall_cells.items():
        strata[conn_label.get(task, "unknown")][cfg].append(v)
    by_stratum = {
        stratum: {
            cfg: {"n": len(vals), "recall": round(statistics.fmean(vals), 4)}
            for cfg, vals in cfgmap.items()
        }
        for stratum, cfgmap in strata.items()
    }

    return {
        "configs": configs,
        "runaway_threshold": runaway,
        "summary": summary,
        "by_connectivity_stratum": by_stratum,
        "connectivity_labels": conn_label,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results", type=Path)
    ap.add_argument("--conn", type=Path, help="connectivity.py json output")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--runaway", type=float, default=500_000)
    args = ap.parse_args()

    out = aggregate(args.results, args.conn, args.runaway)

    print("=== TASK-WEIGHTED ACCURACY + ROBUST TOKENS (per config) ===")
    hdr = (f"{'config':16s} {'tasks':5s} {'rows':4s} {'recall':7s} {'allfnd':7s} "
           f"{'tok_med':9s} {'tok_mean':9s} {'tok_p90':9s} {'tok_max':10s} {'runaway':7s}")
    print(hdr)
    for cfg in out["configs"]:
        s = out["summary"][cfg]
        t = s["tokens"]
        print(f"{cfg:16s} {s['n_tasks']!s:5s} {s['n_rows']!s:4s} "
              f"{s['recall_task_weighted']!s:7s} {s['all_found_task_weighted']!s:7s} "
              f"{t['median_per_task']!s:9s} {t['mean_per_task']!s:9s} "
              f"{t['p90_per_task']!s:9s} {t['max_row']!s:10s} {t['n_runaways']!s:7s}")

    print("\n=== RECALL BY CONNECTIVITY STRATUM ===")
    for stratum, cfgmap in sorted(out["by_connectivity_stratum"].items()):
        print(f"\n[{stratum}]")
        for cfg in out["configs"]:
            d = cfgmap.get(cfg)
            if d:
                print(f"  {cfg:16s} n={d['n']:<3d} recall={d['recall']}")

    if args.json:
        args.json.write_text(json.dumps(out, indent=2))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
