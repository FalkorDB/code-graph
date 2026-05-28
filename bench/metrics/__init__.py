"""Trajectory parsing and per-task metrics for the benchmark.

SWE-agent emits a trajectory JSON per task. We extract the headline numbers:

- token usage (input + output, per-call sum)
- tool calls (count + per-tool breakdown)
- patch (the agent's final diff submission)
- outcome (resolved / failed / budget_exceeded), evaluated externally
  by SWE-bench's official scorer

The functions in this module are pure and trajectory-shape-agnostic to the
extent possible: each is defensive about missing/renamed fields because
SWE-agent's exact JSON schema has drifted between versions. The tests in
`tests/test_bench_metrics.py` lock the contract for a small synthetic
trajectory.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TaskMetrics:
    """One row of the results JSONL: per-task per-config measurement."""

    benchmark: str           # "swe_bench_verified"
    task_id: str             # e.g. "django__django-12345"
    config: str              # "baseline" | "lsp" | "code_graph"
    run_idx: int             # 0 for pass@1, 1+ for retries

    # token cost (LLM only — never combined with indexing)
    input_tokens: int
    output_tokens: int

    # tool-call sanity check
    tool_calls_total: int
    tool_calls_by_name: dict[str, int] = field(default_factory=dict)
    # Tool-usage rate: fraction of bash commands that actually invoke the
    # configured tool (cg / cg-mcp / lsp). Low rate = agent abandoned the
    # tool and ran on plain bash. None for baseline (no tool expected).
    tool_usage_rate: float | None = None
    tool_usage_turns: int = 0
    tool_usage_total: int = 0
    # Fallback rate: fraction of bash commands that are plain text search
    # (grep / rg / find / ack / ag) instead of the configured tool.
    # Always populated (incl. baseline as a reference point).
    fallback_rate: float | None = None
    fallback_turns: int = 0
    # One-time indexing wall-clock (only on first run per worktree). None
    # for baseline/lsp (no indexing) and 0.0 when the graph was already
    # built (cache hit on subsequent retries).
    index_sec: float | None = None

    # outcome (set after scoring; None until then)
    outcome: str | None = None   # "resolved" | "failed" | "budget_exceeded" | "error" | "tool_unavailable"
    patch: str | None = None
    wall_clock_sec: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_TOKEN_KEYS_IN = ("prompt_tokens", "input_tokens", "tokens_in")
_TOKEN_KEYS_OUT = ("completion_tokens", "output_tokens", "tokens_out")


def _first_int(d: dict[str, Any], keys: tuple[str, ...]) -> int:
    for k in keys:
        v = d.get(k)
        if isinstance(v, int):
            return v
    return 0


def _iter_history_steps(traj: dict[str, Any]) -> list[dict[str, Any]]:
    """SWE-agent has flipped between top-level `history`, `trajectory`, and
    `steps`. mini-swe-agent uses `messages`. Return whichever list is
    present, else [].
    """
    for key in ("history", "trajectory", "steps", "messages"):
        v = traj.get(key)
        if isinstance(v, list):
            return v
    return []


def _step_usage(step: dict[str, Any]) -> dict[str, Any] | None:
    """Find an OpenAI/Anthropic-style usage dict on a step, across schemas."""
    if not isinstance(step, dict):
        return None
    # SWE-agent: step.usage
    usage = step.get("usage")
    if isinstance(usage, dict):
        return usage
    # mini-swe-agent: step.extra.response.usage
    extra = step.get("extra")
    if isinstance(extra, dict):
        resp = extra.get("response")
        if isinstance(resp, dict):
            u = resp.get("usage")
            if isinstance(u, dict):
                return u
        u = extra.get("usage")
        if isinstance(u, dict):
            return u
    return None


def extract_token_usage(traj: dict[str, Any]) -> tuple[int, int]:
    """Sum input + output tokens across all LLM calls in the trajectory.

    Looks for `usage` sub-objects on each step (the conventional shape for
    OpenAI/Anthropic-style responses passed through LiteLLM).
    """
    total_in = 0
    total_out = 0
    for step in _iter_history_steps(traj):
        usage = _step_usage(step)
        if isinstance(usage, dict):
            total_in += _first_int(usage, _TOKEN_KEYS_IN)
            total_out += _first_int(usage, _TOKEN_KEYS_OUT)
    summary = traj.get("total_usage") or traj.get("usage")
    if (total_in == 0 and total_out == 0) and isinstance(summary, dict):
        total_in = _first_int(summary, _TOKEN_KEYS_IN)
        total_out = _first_int(summary, _TOKEN_KEYS_OUT)
    return total_in, total_out


def _action_name(cmd: str) -> str:
    """Bucket a bash command line into a friendly tool-call name.

    The first non-redirection token is good enough — `cg`, `lsp`, `git`,
    `grep`, `sed`, etc. Falls back to `bash` for empty or odd shapes.
    """
    if not isinstance(cmd, str):
        return "bash"
    tokens = cmd.strip().split()
    if not tokens:
        return "bash"
    head = tokens[0]
    if head in ("printf", "echo") and "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" in cmd:
        return "submit"
    return head


def extract_tool_calls(traj: dict[str, Any]) -> tuple[int, dict[str, int]]:
    """Count every tool/action invocation and bucket by tool name."""
    by_name: dict[str, int] = {}
    total = 0
    for step in _iter_history_steps(traj):
        if not isinstance(step, dict):
            continue
        # mini-swe-agent: step.extra.actions[*].command (bash-only).
        extra = step.get("extra") if isinstance(step.get("extra"), dict) else None
        if extra and isinstance(extra.get("actions"), list):
            for act in extra["actions"]:
                if isinstance(act, dict):
                    by_name_key = _action_name(act.get("command", ""))
                    by_name[by_name_key] = by_name.get(by_name_key, 0) + 1
                    total += 1
            continue
        # SWE-agent shapes: action.command, tool_calls[*].function.name, action.name
        name = None
        action = step.get("action")
        if isinstance(action, dict):
            name = action.get("command") or action.get("name") or action.get("tool")
        if not name:
            tcs = step.get("tool_calls")
            if isinstance(tcs, list) and tcs:
                fn = tcs[0].get("function") if isinstance(tcs[0], dict) else None
                if isinstance(fn, dict):
                    name = fn.get("name")
        if not name:
            continue
        by_name[name] = by_name.get(name, 0) + 1
        total += 1
    return total, by_name


def extract_patch(traj: dict[str, Any]) -> str | None:
    """The final diff the agent submitted, if any."""
    for key in ("model_patch", "submission", "patch"):
        v = traj.get(key)
        if isinstance(v, str) and v.strip():
            return v
    info = traj.get("info") if isinstance(traj.get("info"), dict) else None
    if info:
        for key in ("model_patch", "submission", "patch"):
            v = info.get(key)
            if isinstance(v, str) and v.strip():
                return v
    return None


def task_metrics_from_trajectory(
    traj: dict[str, Any],
    *,
    benchmark: str,
    task_id: str,
    config: str,
    run_idx: int = 0,
    wall_clock_sec: float | None = None,
) -> TaskMetrics:
    tin, tout = extract_token_usage(traj)
    n_calls, by_name = extract_tool_calls(traj)
    return TaskMetrics(
        benchmark=benchmark,
        task_id=task_id,
        config=config,
        run_idx=run_idx,
        input_tokens=tin,
        output_tokens=tout,
        tool_calls_total=n_calls,
        tool_calls_by_name=by_name,
        patch=extract_patch(traj),
        wall_clock_sec=wall_clock_sec,
    )


def load_trajectory(path: str | Path) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def write_jsonl(path: str | Path, rows: list[TaskMetrics]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r.to_dict()) + "\n")


def append_jsonl(path: str | Path, row: TaskMetrics) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(row.to_dict()) + "\n")
