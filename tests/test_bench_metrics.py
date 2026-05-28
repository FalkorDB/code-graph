"""Tests for bench/metrics and bench/report — pure-function units."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.metrics import (
    TaskMetrics,
    extract_patch,
    extract_token_usage,
    extract_tool_calls,
    task_metrics_from_trajectory,
    write_jsonl,
)
from bench.report import aggregate_to_markdown, render_markdown, summarize


_TRAJ_FIXTURE = {
    "history": [
        {
            "action": {"command": "read_file"},
            "usage": {"prompt_tokens": 1200, "completion_tokens": 80},
        },
        {
            "action": {"command": "graph_entities"},
            "usage": {"prompt_tokens": 800, "completion_tokens": 40},
        },
        {
            "action": {"command": "read_file"},
            "usage": {"prompt_tokens": 1500, "completion_tokens": 90},
        },
        {
            "action": {"command": "submit"},
            "usage": {"prompt_tokens": 200, "completion_tokens": 30},
        },
    ],
    "model_patch": "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@\n-foo\n+bar\n",
}


def test_extract_token_usage_sums_history():
    tin, tout = extract_token_usage(_TRAJ_FIXTURE)
    assert tin == 1200 + 800 + 1500 + 200
    assert tout == 80 + 40 + 90 + 30


def test_extract_token_usage_falls_back_to_summary():
    traj = {"total_usage": {"input_tokens": 5000, "output_tokens": 300}}
    tin, tout = extract_token_usage(traj)
    assert (tin, tout) == (5000, 300)


def test_extract_tool_calls_buckets_by_name():
    total, by_name = extract_tool_calls(_TRAJ_FIXTURE)
    assert total == 4
    assert by_name == {"read_file": 2, "graph_entities": 1, "submit": 1}


def test_extract_tool_calls_supports_openai_shape():
    traj = {
        "history": [
            {"tool_calls": [{"function": {"name": "find_references"}}]},
            {"tool_calls": [{"function": {"name": "find_references"}}]},
            {"tool_calls": [{"function": {"name": "hover"}}]},
        ]
    }
    total, by_name = extract_tool_calls(traj)
    assert total == 3
    assert by_name == {"find_references": 2, "hover": 1}


def test_extract_patch():
    assert extract_patch(_TRAJ_FIXTURE).startswith("diff --git")
    assert extract_patch({}) is None


def test_task_metrics_from_trajectory_round_trip():
    m = task_metrics_from_trajectory(
        _TRAJ_FIXTURE,
        benchmark="swe_bench_verified",
        task_id="django__django-1",
        config="code_graph",
    )
    assert m.task_id == "django__django-1"
    assert m.config == "code_graph"
    assert m.input_tokens == 3700
    assert m.output_tokens == 240
    assert m.tool_calls_total == 4
    d = m.to_dict()
    assert json.loads(json.dumps(d))["task_id"] == "django__django-1"


def _row(config: str, tokens: int, resolved: bool, task_id: str = "t1") -> dict:
    return {
        "benchmark": "swe_bench_verified",
        "task_id": task_id,
        "config": config,
        "run_idx": 0,
        "input_tokens": tokens // 2,
        "output_tokens": tokens // 2,
        "tool_calls_total": 1,
        "tool_calls_by_name": {},
        "outcome": "resolved" if resolved else "failed",
        "patch": "diff" if resolved else None,
        "wall_clock_sec": None,
    }


def test_summarize_resolve_rate_and_medians():
    rows = [
        _row("baseline", 1000, True, "t1"),
        _row("baseline", 2000, False, "t2"),
        _row("baseline", 3000, True, "t3"),
        _row("code_graph", 800, True, "t1"),
        _row("code_graph", 900, True, "t2"),
        _row("code_graph", 1100, False, "t3"),
    ]
    summaries = summarize(rows)
    s = {s.config: s for s in summaries}

    assert s["baseline"].n_tasks == 3
    assert s["baseline"].n_resolved == 2
    assert pytest.approx(s["baseline"].resolve_rate) == 2 / 3
    assert s["baseline"].median_tokens == 2000

    assert s["code_graph"].n_resolved == 2
    assert s["code_graph"].median_tokens == 900


def test_summarize_prefers_resolved_run_for_retries():
    rows = [
        {**_row("lsp", 500, False, "t1"), "run_idx": 0},
        {**_row("lsp", 700, True, "t1"), "run_idx": 1},
    ]
    s = summarize(rows)[0]
    assert s.n_resolved == 1
    assert s.median_tokens == 700


def test_render_markdown_includes_delta():
    rows = [
        _row("baseline", 2000, True, "t1"),
        _row("baseline", 4000, True, "t2"),
        _row("code_graph", 1000, True, "t1"),
        _row("code_graph", 1200, True, "t2"),
    ]
    md = render_markdown(summarize(rows))
    assert "baseline" in md
    assert "code_graph" in md
    assert "Δ tokens vs baseline" in md
    # code_graph median (1100) vs baseline median (3000) → ~-63%
    assert "-63.3%" in md


def test_aggregate_to_markdown_writes_file(tmp_path: Path):
    rows = [_row("baseline", 1000, True), _row("lsp", 800, True)]
    jsonl = tmp_path / "results.jsonl"
    write_jsonl(jsonl, [TaskMetrics(**r) for r in rows])
    out = tmp_path / "results.md"
    aggregate_to_markdown(jsonl, out)
    assert out.exists()
    assert "lsp" in out.read_text()
