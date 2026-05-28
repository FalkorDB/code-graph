"""Convert our results.jsonl into SWE-bench predictions and run the
official Docker-based evaluation harness.

The SWE-bench harness expects predictions in the form:

    {"instance_id": "...", "model_name_or_path": "...", "model_patch": "..."}

one per line. We have one row per (instance_id, config) in
results.jsonl with `metrics.patch` already populated as a `git diff`.
This module:

1. Exports per-config predictions JSONL files from results.jsonl.
2. Optionally shells out to `python -m swebench.harness.run_evaluation`
   (requires the `swebench` package and Docker) for each config.
3. Reads the harness report JSON back and patches outcomes in
   results.jsonl so the report aggregator picks them up.

Usage:
    # Export only (no harness invocation):
    uv run python -m bench.runners.swebench_verify --export-only

    # Full eval (needs swebench + Docker):
    uv run python -m bench.runners.swebench_verify --run-id smoke1
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS = REPO_ROOT / "bench" / "cache" / "results.jsonl"
DEFAULT_PRED_DIR = REPO_ROOT / "bench" / "cache" / "predictions"
DEFAULT_REPORT_DIR = REPO_ROOT / "bench" / "cache" / "harness_reports"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _dump_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def export_predictions(
    results_path: Path = DEFAULT_RESULTS,
    out_dir: Path = DEFAULT_PRED_DIR,
    *,
    benchmark: str = "swe_bench_verified",
) -> dict[str, Path]:
    """Write per-config predictions JSONL files. Returns {config: path}."""
    rows = _load_jsonl(results_path)
    by_cfg: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r.get("benchmark") != benchmark:
            continue
        if not r.get("patch"):
            continue
        by_cfg[r["config"]].append({
            "instance_id": r["task_id"],
            "model_name_or_path": f"code-graph-bench-{r['config']}",
            "model_patch": r["patch"],
        })

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for cfg, preds in by_cfg.items():
        p = out_dir / f"{cfg}.jsonl"
        _dump_jsonl(preds, p)
        paths[cfg] = p
    return paths


def run_harness(
    predictions: Path,
    *,
    run_id: str,
    dataset_name: str = "princeton-nlp/SWE-bench_Verified",
    report_dir: Path = DEFAULT_REPORT_DIR,
    max_workers: int = 4,
    timeout: int = 1800,
) -> Path:
    """Invoke swebench.harness.run_evaluation. Returns path to report JSON."""
    if shutil.which("docker") is None:
        raise RuntimeError("docker not found in PATH — SWE-bench harness needs Docker")
    report_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "swebench.harness.run_evaluation",
        "--dataset_name", dataset_name,
        "--predictions_path", str(predictions),
        "--max_workers", str(max_workers),
        "--run_id", run_id,
        "--timeout", str(timeout),
    ]
    print(f"[harness] $ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=str(report_dir))
    # Harness writes reports to ./logs/run_evaluation/{run_id}/... and a
    # top-level <model>.<run_id>.json with the rolled-up verdict.
    candidates = list(report_dir.glob(f"*.{run_id}.json"))
    if not candidates:
        raise RuntimeError(f"no report json found under {report_dir} for run_id={run_id}")
    return candidates[0]


def patch_outcomes_from_report(
    report_path: Path,
    results_path: Path = DEFAULT_RESULTS,
    *,
    config: str,
) -> int:
    """Read a harness report and rewrite outcomes for `config` rows in results.jsonl.

    Report shape (rolled-up):
        {"resolved_ids": [...], "unresolved_ids": [...], ...}
    Returns the number of rows patched.
    """
    report = json.loads(report_path.read_text())
    resolved = set(report.get("resolved_ids", []))
    unresolved = set(report.get("unresolved_ids", []))

    rows = _load_jsonl(results_path)
    n = 0
    for r in rows:
        if r.get("config") != config:
            continue
        if r["task_id"] in resolved:
            r["outcome"] = "resolved"; n += 1
        elif r["task_id"] in unresolved:
            r["outcome"] = "failed"; n += 1
    _dump_jsonl(rows, results_path)
    return n


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="SWE-bench Docker-based verification")
    p.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    p.add_argument("--pred-dir", type=Path, default=DEFAULT_PRED_DIR)
    p.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    p.add_argument("--run-id", default="bench-smoke",
                   help="harness run id (used as a logs/ subdir)")
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--export-only", action="store_true",
                   help="just write per-config predictions JSONL; don't run harness")
    args = p.parse_args(argv)

    if not args.results.exists():
        print(f"error: results not found: {args.results}")
        return 1

    paths = export_predictions(args.results, args.pred_dir)
    if not paths:
        print("[export] no swe_bench_verified rows with patches in results.jsonl")
        return 1
    print(f"[export] wrote predictions for configs: {sorted(paths)}")
    for cfg, path in paths.items():
        n = sum(1 for _ in path.open())
        print(f"  - {cfg}: {n} predictions -> {path}")

    if args.export_only:
        return 0

    for cfg, pred_path in paths.items():
        run_id = f"{args.run_id}-{cfg}"
        try:
            report = run_harness(
                pred_path, run_id=run_id, report_dir=args.report_dir,
                max_workers=args.max_workers, timeout=args.timeout,
            )
        except Exception as exc:
            print(f"[harness] {cfg}: FAILED — {exc}")
            continue
        n = patch_outcomes_from_report(report, args.results, config=cfg)
        print(f"[harness] {cfg}: patched {n} outcomes from {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
