"""Aggregate per-task metrics into a per-config summary table.

Reads the JSONL emitted by bench/metrics and produces:
- a markdown table grouped by (benchmark, config) with accuracy + tokens
- a token-savings Δ column vs the baseline config
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ConfigSummary:
    benchmark: str
    config: str
    n_tasks: int
    n_resolved: int
    median_tokens: int
    p90_tokens: int
    median_tool_usage: float | None = None  # fraction in [0,1] or None for baseline
    median_fallback: float | None = None  # fraction in [0,1] of bash cmds that were grep/find/rg

    @property
    def resolve_rate(self) -> float:
        return self.n_resolved / self.n_tasks if self.n_tasks else 0.0

    @property
    def total_tokens(self) -> int:
        return self.median_tokens * self.n_tasks  # not perfectly accurate, replaced below


def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return int(s[f] + (s[c] - s[f]) * (k - f))


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def summarize(rows: list[dict[str, Any]]) -> list[ConfigSummary]:
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_key[(r["benchmark"], r["config"])].append(r)

    summaries: list[ConfigSummary] = []
    for (bench, cfg), task_rows in sorted(by_key.items()):
        # Pick the best run per (task_id) — pass@1 with retries.
        best_by_task: dict[str, dict[str, Any]] = {}
        for r in task_rows:
            tid = r["task_id"]
            prev = best_by_task.get(tid)
            if prev is None:
                best_by_task[tid] = r
                continue
            # prefer a resolved outcome
            if prev.get("outcome") != "resolved" and r.get("outcome") == "resolved":
                best_by_task[tid] = r

        token_sums = [
            (r["input_tokens"] + r["output_tokens"]) for r in best_by_task.values()
        ]
        usage_rates = [
            r["tool_usage_rate"] for r in best_by_task.values()
            if r.get("tool_usage_rate") is not None
        ]
        fallback_rates = [
            r["fallback_rate"] for r in best_by_task.values()
            if r.get("fallback_rate") is not None
        ]
        n_resolved = sum(1 for r in best_by_task.values() if r.get("outcome") == "resolved")
        summaries.append(
            ConfigSummary(
                benchmark=bench,
                config=cfg,
                n_tasks=len(best_by_task),
                n_resolved=n_resolved,
                median_tokens=int(statistics.median(token_sums)) if token_sums else 0,
                p90_tokens=_percentile(token_sums, 0.9),
                median_tool_usage=statistics.median(usage_rates) if usage_rates else None,
                median_fallback=statistics.median(fallback_rates) if fallback_rates else None,
            )
        )
    return summaries


def render_markdown(summaries: list[ConfigSummary]) -> str:
    lines: list[str] = []
    lines.append("# Benchmark results\n")
    by_bench: dict[str, list[ConfigSummary]] = defaultdict(list)
    for s in summaries:
        by_bench[s.benchmark].append(s)

    for bench, group in sorted(by_bench.items()):
        baseline = next((s for s in group if s.config == "baseline"), None)
        baseline_med = baseline.median_tokens if baseline else 0

        lines.append(f"## {bench}\n")
        lines.append("| config | tasks | resolved | resolve rate | median tokens | p90 tokens | Δ tokens vs baseline | tool-usage rate | fallback rate |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for s in sorted(group, key=lambda x: x.config):
            delta = "—"
            if baseline_med and s.config != "baseline":
                pct = (s.median_tokens - baseline_med) / baseline_med * 100
                delta = f"{pct:+.1f}%"
            usage = "—" if s.median_tool_usage is None else f"{s.median_tool_usage * 100:.0f}%"
            fb = "—" if s.median_fallback is None else f"{s.median_fallback * 100:.0f}%"
            lines.append(
                f"| {s.config} | {s.n_tasks} | {s.n_resolved} | "
                f"{s.resolve_rate * 100:.1f}% | {s.median_tokens:,} | "
                f"{s.p90_tokens:,} | {delta} | {usage} | {fb} |"
            )
        lines.append("")
    return "\n".join(lines)


def aggregate_to_markdown(jsonl_path: str | Path, out_path: str | Path) -> None:
    rows = load_jsonl(jsonl_path)
    summaries = summarize(rows)
    md = render_markdown(summaries)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
