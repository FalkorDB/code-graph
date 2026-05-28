"""Tests for `bench.runners.mini_runner` and the bash-tool CLI shims.

These tests run **without** an LLM API key. They use the runner's
`--dry-run` mode (stub model) to validate:

- the full mini-swe-agent loop executes cleanly,
- the trajectory is captured and persisted,
- the metrics module extracts tokens + tool calls from the
  mini-swe-agent trajectory shape,
- the per-config env wiring (PATH for lsp/code_graph, baseline
  PATH untouched) reaches the bash subprocess.

We deliberately keep these tests off the network and off any LLM.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from bench.runners import mini_runner


def _make_repo(tmp_path: Path) -> mini_runner.Task:
    repo = tmp_path / "repo"
    return mini_runner._make_dry_run_task(repo)


# ---------------------------------------------------------------------------
# run_task
# ---------------------------------------------------------------------------


def test_dry_run_task_baseline_completes(tmp_path: Path) -> None:
    task = _make_repo(tmp_path)
    res = mini_runner.run_task(task, "baseline", dry_run=True, step_limit=2)
    assert res["exit_status"] == "ok"
    m = res["metrics"]
    assert m.benchmark == "dry_run"
    assert m.config == "baseline"
    assert m.input_tokens > 0
    assert m.output_tokens > 0
    assert m.tool_calls_total == 1
    # The stub submits via `printf ...COMPLETE_TASK...` so the bucket name
    # is `submit`, not the raw printf.
    assert "submit" in m.tool_calls_by_name


def test_dry_run_task_lsp_sets_repo_root(tmp_path: Path) -> None:
    task = _make_repo(tmp_path)
    res = mini_runner.run_task(task, "lsp", dry_run=True, step_limit=2)
    assert res["exit_status"] == "ok"
    # Trajectory must contain a bash output line with the cli dir on PATH.
    text = json.dumps(res["trajectory"])
    assert "bench/cli" in text


def test_dry_run_unknown_config_raises(tmp_path: Path) -> None:
    task = _make_repo(tmp_path)
    with pytest.raises(ValueError, match="unknown config"):
        mini_runner.run_task(task, "not_a_config", dry_run=True)


# ---------------------------------------------------------------------------
# config_env
# ---------------------------------------------------------------------------


def test_config_env_baseline_does_not_add_cli_dir(tmp_path: Path) -> None:
    env = mini_runner.config_env("baseline", tmp_path)
    assert str(mini_runner.CLI_DIR) not in env["PATH"]


def test_config_env_lsp_prepends_cli_dir_and_sets_repo_root(tmp_path: Path) -> None:
    env = mini_runner.config_env("lsp", tmp_path)
    assert env["PATH"].startswith(str(mini_runner.CLI_DIR))
    assert env["LSP_REPO_ROOT"] == str(tmp_path)
    assert env["LSP_LANGUAGE"] == "python"


def test_config_env_code_graph_prepends_cli_dir_and_sets_url(tmp_path: Path) -> None:
    env = mini_runner.config_env("code_graph", tmp_path)
    assert env["PATH"].startswith(str(mini_runner.CLI_DIR))
    assert "CODEGRAPH_URL" in env


# ---------------------------------------------------------------------------
# run_batch persistence
# ---------------------------------------------------------------------------


def test_run_batch_writes_results_jsonl_and_trajectories(tmp_path: Path) -> None:
    task = _make_repo(tmp_path)
    results = tmp_path / "results.jsonl"
    trajs = tmp_path / "trajs"
    rows = mini_runner.run_batch(
        [task],
        ["baseline", "lsp"],
        results_path=results,
        trajectories_dir=trajs,
        dry_run=True,
        step_limit=2,
    )
    assert len(rows) == 2
    assert results.exists()
    lines = results.read_text().strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        row = json.loads(line)
        assert row["benchmark"] == "dry_run"
        assert row["task_id"] == "dry-run-1"
    # Trajectories on disk, one per (task, config).
    assert (trajs / "dry-run-1__baseline.json").exists()
    assert (trajs / "dry-run-1__lsp.json").exists()


# ---------------------------------------------------------------------------
# CLI smoke tests (argparse only — no service contact)
# ---------------------------------------------------------------------------


def test_cg_cli_help_exits_zero() -> None:
    out = subprocess.run(
        ["uv", "run", "python", "-m", "bench.cli.cg", "--help"],
        capture_output=True, text=True, cwd=mini_runner.REPO_ROOT, check=False,
    )
    assert out.returncode == 0
    assert "graph-entities" in out.stdout
    assert "find-paths" in out.stdout


def test_lsp_cli_help_exits_zero() -> None:
    out = subprocess.run(
        ["uv", "run", "python", "-m", "bench.cli.lsp", "--help"],
        capture_output=True, text=True, cwd=mini_runner.REPO_ROOT, check=False,
    )
    assert out.returncode == 0
    assert "goto-definition" in out.stdout
    assert "document-symbols" in out.stdout


def test_cg_cli_rejects_unknown_subcommand() -> None:
    out = subprocess.run(
        ["uv", "run", "python", "-m", "bench.cli.cg", "nope"],
        capture_output=True, text=True, cwd=mini_runner.REPO_ROOT, check=False,
    )
    assert out.returncode != 0
