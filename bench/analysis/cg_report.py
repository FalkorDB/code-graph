"""Per-instance code_graph-vs-reference reporter for the cg-n5 micro-cycle.

Given the code_graph cache dir and a task_id, prints:
  * the code_graph result row (recall / acc@1 / tokens / tool usage)
  * the FROZEN reference rows (copilot_no_mcp + lsp) for the same task
  * a compact agent trace (tool steps) reconstructed via bench.analysis.trace

Usage:
    python -m bench.analysis.cg_report <task_id>
    python -m bench.analysis.cg_report --list      # show which tasks have results
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

CG_RESULTS = Path("bench/cache/cg-n5-cooverride/claude-opus-4.8/results.jsonl")
REF_RESULTS = Path("bench/cache/ref-n5-baseline-lsp/claude-opus-4.8/results.jsonl")
CG_RUNS = Path("bench/cache/cg-n5-cooverride/runs/claude-opus-4.8/localize/nudged/code_graph")


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _fmt_row(r: dict) -> str:
    tools = r.get("tool_calls_by_name") or {}
    tool_str = ", ".join(f"{k}={v}" for k, v in sorted(tools.items())) or "(none)"
    return (
        f"  config={r.get('config'):<16} recall={r.get('file_recall')!s:<5} "
        f"acc@1={r.get('acc_at_1')!s:<5} acc@5={r.get('acc_at_5')!s:<5} "
        f"in_tok={r.get('input_tokens'):<8} out_tok={r.get('output_tokens'):<6} "
        f"premium={r.get('premium_requests')!s:<4} wall={r.get('wall_clock_sec')}s\n"
        f"      tools: {tool_str}  first={r.get('first_tool')} "
        f"graph_calls={r.get('graph_calls')} "
        f"outcome={r.get('outcome')} timed_out={r.get('timed_out')} "
        f"leak={r.get('network_leak')}"
    )


def _recall(r: dict) -> str:
    v = r.get("file_recall")
    return "?" if v is None else str(v)


def report(task_id: str) -> None:
    cg = [r for r in _load(CG_RESULTS) if r.get("task_id") == task_id]
    ref = [r for r in _load(REF_RESULTS) if r.get("task_id") == task_id]
    print("=" * 78)
    print(f"INSTANCE: {task_id}")
    print("=" * 78)
    if cg:
        gold = cg[0].get("gold_files") or cg[0].get("gold")
        print(f"gold_files: {gold}")
    print("\n--- code_graph (THIS run, co-override) ---")
    for r in cg:
        print(_fmt_row(r))
        pred = r.get("pred_files")
        print(f"      pred: {pred}")
    print("\n--- FROZEN reference ---")
    for r in sorted(ref, key=lambda x: x.get("config", "")):
        print(_fmt_row(r))

    # Trace
    run_dir = CG_RUNS / task_id
    print(f"\n--- agent trace ({run_dir}) ---")
    tr = run_dir / "trace.md"
    if tr.exists():
        print(tr.read_text())
    else:
        print(f"  (no trace.md yet at {tr}; run: python -m bench.analysis.trace {run_dir})")


def list_done() -> None:
    cg = _load(CG_RESULTS)
    print(f"code_graph results so far: {len(cg)}")
    for r in cg:
        print(f"  {r.get('task_id'):<40} recall={_recall(r)} outcome={r.get('outcome')}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task_id", nargs="?")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.list or not args.task_id:
        list_done()
        return
    report(args.task_id)


if __name__ == "__main__":
    main()
