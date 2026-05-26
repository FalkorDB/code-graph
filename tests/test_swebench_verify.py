"""Unit tests for the SWE-bench Docker verification adapter (no Docker)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.runners import swebench_verify as sv


def _write_results(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_export_predictions_filters_by_benchmark_and_patch(tmp_path: Path):
    results = tmp_path / "results.jsonl"
    _write_results(results, [
        # swe-bench rows with patches → exported
        {"benchmark": "swe_bench_verified", "config": "baseline",
         "task_id": "django__django-1", "patch": "diff a"},
        {"benchmark": "swe_bench_verified", "config": "lsp",
         "task_id": "django__django-1", "patch": "diff b"},
        # missing patch → skipped
        {"benchmark": "swe_bench_verified", "config": "baseline",
         "task_id": "django__django-2", "patch": ""},
        # wrong benchmark → skipped
        {"benchmark": "synthetic_smoke", "config": "baseline",
         "task_id": "smoke-1", "patch": "diff c"},
    ])
    out_dir = tmp_path / "preds"
    paths = sv.export_predictions(results, out_dir)
    assert set(paths) == {"baseline", "lsp"}

    baseline = [json.loads(l) for l in paths["baseline"].read_text().splitlines()]
    assert len(baseline) == 1
    row = baseline[0]
    assert row["instance_id"] == "django__django-1"
    assert row["model_name_or_path"] == "code-graph-bench-baseline"
    assert row["model_patch"] == "diff a"


def test_export_predictions_returns_empty_when_no_matching_rows(tmp_path: Path):
    results = tmp_path / "results.jsonl"
    _write_results(results, [
        {"benchmark": "synthetic_smoke", "config": "baseline",
         "task_id": "smoke-1", "patch": "diff"}
    ])
    paths = sv.export_predictions(results, tmp_path / "preds")
    assert paths == {}


def test_patch_outcomes_from_report(tmp_path: Path):
    results = tmp_path / "results.jsonl"
    _write_results(results, [
        {"benchmark": "swe_bench_verified", "config": "baseline",
         "task_id": "x-1", "patch": "p", "outcome": None},
        {"benchmark": "swe_bench_verified", "config": "baseline",
         "task_id": "x-2", "patch": "p", "outcome": None},
        {"benchmark": "swe_bench_verified", "config": "lsp",
         "task_id": "x-1", "patch": "p", "outcome": None},
    ])
    report = tmp_path / "r.json"
    report.write_text(json.dumps({
        "resolved_ids": ["x-1"], "unresolved_ids": ["x-2"],
    }))

    n = sv.patch_outcomes_from_report(report, results, config="baseline")
    assert n == 2

    rows = [json.loads(l) for l in results.read_text().splitlines()]
    assert rows[0]["outcome"] == "resolved"
    assert rows[1]["outcome"] == "failed"
    # lsp row untouched
    assert rows[2]["outcome"] is None


def test_run_harness_raises_when_docker_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sv.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="docker not found"):
        sv.run_harness(tmp_path / "preds.jsonl", run_id="x")
