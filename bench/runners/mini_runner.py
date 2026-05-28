"""Benchmark runner wired to mini-swe-agent.

The runner is the glue between:

- the **benchmark dataset** (SWE-bench Verified, or a tiny synthetic
  dataset in `--dry-run` mode so the harness is testable without an
  LLM API key),
- the **agent harness** (`mini-swe-agent`, which uses bash as its sole
  tool surface),
- and the **per-config tool bundle** (baseline / lsp / code-graph),
  exposed to the agent as a `PATH` prefix containing `bench/cli/`
  scripts plus the relevant env vars.

For each (task, config) pair the runner:

1. Materializes the target repo at the task's base commit.
2. Builds the agent: LitellmModel + LocalEnvironment (cwd = repo, env =
   config-specific tool env vars) + system/instance templates assembled
   from `bench/tools/<config>/system_preamble.md` and the task body.
3. Runs the agent with the locked-in step/cost/wall-time limits.
4. Captures the trajectory (mini-swe-agent's `agent.serialize()` dict)
   and `git diff` of the repo as the proposed patch.
5. Hands the trajectory to `bench.metrics.task_metrics_from_trajectory`
   and appends a row to `bench/cache/results.jsonl`.

The `--dry-run` mode swaps the LLM model for a deterministic stub so
the entire pipeline can run with no Anthropic key — this is the mode
we exercise in CI and in `tests/test_bench_runner.py`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# mini-swe-agent imports are slow (litellm pre-import). Defer to call time.

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = REPO_ROOT / "bench"
CLI_DIR = BENCH_DIR / "cli"
TOOLS_DIR = BENCH_DIR / "tools"
DEFAULT_CACHE_DIR = BENCH_DIR / "cache"
DEFAULT_RESULTS = DEFAULT_CACHE_DIR / "results.jsonl"

VALID_CONFIGS = ("baseline", "lsp", "code_graph", "code_graph_mcp")


# ---------------------------------------------------------------------------
# Task model
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Task:
    """A single benchmark instance.

    `repo_path` is an absolute path to the prepared working tree at the
    correct base commit. `verify_cmd` is a shell command that must exit
    0 if the patch resolves the task; in dry-run mode it's the cheap
    synthetic check, in real SWE-bench mode it's the harness's test
    selection.
    """

    task_id: str
    repo_name: str
    repo_path: Path
    problem_statement: str
    verify_cmd: str | None = None


# ---------------------------------------------------------------------------
# Preamble + instance prompt assembly
# ---------------------------------------------------------------------------


# The instance prompt is identical across configs — only `system_preamble.md`
# changes. mini-swe-agent uses Jinja2 templating, so we pre-format with
# explicit placeholders the agent will see.
INSTANCE_TEMPLATE = """\
You are working in the repository at {{cwd}}.

The task to solve:

{{task}}

When you believe the task is complete, finish your turn with a final
message that contains a unified diff of your changes inside a fenced
``` block, then exit. Do not commit; the harness reads the diff via
`git diff`.
"""


# The lsp / code_graph configs use a sharper template that mandates an
# initial tool call. Smoke #2 showed Claude reads the system preamble's
# "use cg/lsp first" guidance and then ignores it; embedding the
# requirement in the per-instance task description is more obtrusive.

INSTANCE_TEMPLATE_LSP = """\
You are working in the repository at {{cwd}}.

The task to solve:

{{task}}

**Required workflow.** Before reading or editing any file, your first
two bash commands MUST be:

1. `grep -rn "<a symbol named in the task description>" --include='*.py' .`
   to locate a `file:line` for jedi to anchor on.
2. `lsp goto-definition --file <file> --line <line> --col <col>` to
   resolve the true definition.

Then use `lsp find-references` whenever you would have used a recursive
grep, and `lsp document-symbols` whenever you would have run a textual
outline pass. Reach for plain grep/sed/cat only after you've exhausted
the LSP for navigation.

When you believe the task is complete, finish your turn with a final
message that contains a unified diff of your changes inside a fenced
``` block, then exit. Do not commit; the harness reads the diff via
`git diff`.
"""

INSTANCE_TEMPLATE_CODE_GRAPH = """\
You are working in the repository at {{cwd}}.
The code-graph service has already indexed this repository under the
name `$REPO_NAME` (use the env var literally).

The task to solve:

{{task}}

**Required workflow.** Before reading or editing any file, your first
bash command MUST be:

  `cg find-symbol --repo "$REPO_NAME" --name <a symbol named in the task description>`

then use `cg get-neighbors --repo "$REPO_NAME" --ids <id>` to expand
relationships before doing any textual search. After every file edit,
run `cg note-edit --repo "$REPO_NAME" --path <relpath>` so subsequent
graph queries reflect your change. Reach for grep/sed/cat only for
content reading after `cg` has located the right place.

When you believe the task is complete, finish your turn with a final
message that contains a unified diff of your changes inside a fenced
``` block, then exit. Do not commit; the harness reads the diff via
`git diff`.
"""


INSTANCE_TEMPLATE_CODE_GRAPH_MCP = """\
You are working in the repository at {{cwd}}.
The code-graph MCP server has already indexed this repository under the
project name `$PROJECT_NAME` on branch `$BRANCH` (use the env vars
literally).

The task to solve:

{{task}}

**Required workflow.** Before reading or editing any file, your first
bash command MUST be:

  `cg-mcp search_code --project "$PROJECT_NAME" --branch "$BRANCH" --prefix <a symbol named in the task description>`

Then use `cg-mcp get_callers --project "$PROJECT_NAME" --branch "$BRANCH" --symbol-id <id>`
to expand relationships before doing any textual search. Use
`cg-mcp impact_analysis ... --symbol-id <id> --depth 3` before
non-trivial edits.

When you believe the task is complete, finish your turn with a final
message that contains a unified diff of your changes inside a fenced
``` block, then exit. Do not commit; the harness reads the diff via
`git diff`.
"""


def load_instance_template(config: str) -> str:
    if config == "lsp":
        return INSTANCE_TEMPLATE_LSP
    if config == "code_graph":
        return INSTANCE_TEMPLATE_CODE_GRAPH
    if config == "code_graph_mcp":
        return INSTANCE_TEMPLATE_CODE_GRAPH_MCP
    return INSTANCE_TEMPLATE


def load_preamble(config: str) -> str:
    """Read the per-config system preamble; fall back to a generic stub."""
    path = TOOLS_DIR / config / "system_preamble.md"
    if path.exists():
        return path.read_text()
    # Fallback so dry-run tests can run before all preambles are authored.
    return (
        f"You are an autonomous coding agent. Configuration: {config}.\n"
        "You have one tool: bash. Run commands to read files, search, and "
        "edit. Available helpers depend on the configuration.\n"
    )


# ---------------------------------------------------------------------------
# Per-config environment
# ---------------------------------------------------------------------------


def config_env(config: str, repo_path: Path) -> dict[str, str]:
    """Build the environment variables the agent's bash sees.

    The key trick: each config prepends `bench/cli` to PATH only when
    the helper scripts are part of the bundle. For the `baseline`
    config we deliberately do NOT add the helpers — that's the whole
    point of the baseline.
    """
    env = dict(os.environ)
    # Don't leak the user's PATH editor / shell aliases into the agent.
    env["PATH"] = (
        f"{CLI_DIR}:{env.get('PATH', '/usr/bin:/bin')}"
        if config != "baseline"
        else env.get("PATH", "/usr/bin:/bin")
    )
    # Make `python -m bench.cli.cg ...` work too, regardless of cwd.
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    # Pin the python the bash shims invoke to this process's interpreter so
    # the bench deps (requests, multilspy, ...) are available.
    env["BENCH_PYTHON"] = sys.executable
    if config == "lsp":
        env["LSP_REPO_ROOT"] = str(repo_path)
        env.setdefault("LSP_LANGUAGE", "python")
    elif config == "code_graph":
        # The runner is responsible for ensuring the service is up.
        env.setdefault("CODEGRAPH_URL", "http://127.0.0.1:5000")
        # The agent's preamble references $REPO_NAME — set it to the
        # worktree dirname, which is what analyze_folder used as the id.
        env["REPO_NAME"] = repo_path.name
    elif config == "code_graph_mcp":
        # MCP transport: agent calls `cg-mcp …` which spawns the
        # `cgraph-mcp` stdio server per call. FalkorDB coordinates
        # are passed through verbatim.
        env.setdefault("FALKORDB_HOST", os.environ.get("FALKORDB_HOST", "127.0.0.1"))
        env.setdefault("FALKORDB_PORT", os.environ.get("FALKORDB_PORT", "6379"))
        # `cgraph-mcp` must be on PATH; the runner installs the
        # falkordb-code-graph package into the same interpreter, so
        # prepending the venv bin gives us the entry point.
        venv_bin = str(Path(sys.executable).parent)
        env["PATH"] = f"{venv_bin}:{env['PATH']}"
        # The preamble references $PROJECT_NAME and $BRANCH; project
        # name matches what `index_repo` derives from the folder
        # (= worktree dirname), and branch is the per-instance tag we
        # used when indexing.
        env["PROJECT_NAME"] = repo_path.name
        env["BRANCH"] = os.environ.get("CGRAPH_MCP_BRANCH", "_default")
    return env


def _ensure_indexed(repo_path: Path) -> float:
    """Trigger /api/analyze_folder so `cg --repo <dirname>` returns data.

    The code-graph backend uses `Path(folder).name` as the repo identifier;
    each (instance, config) worktree has a unique directory name like
    `pytest-dev__pytest-6202__code_graph`, which becomes the `--repo` value
    the agent passes to `cg`. We skip indexing if the graph already exists
    in FalkorDB (cheap GRAPH.LIST scan, matches the MCP-track behavior).

    Returns wall-clock seconds spent indexing (0.0 if cache hit / skip).
    """
    import httpx
    import redis
    start = time.monotonic()

    base = os.environ.get("CODEGRAPH_URL", "http://127.0.0.1:5000").rstrip("/")
    repo_name = repo_path.name
    token = os.environ.get("SECRET_TOKEN") or os.environ.get("CODEGRAPH_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    # Cheap precheck via FalkorDB GRAPH.LIST. The HTTP /api/list_repos
    # path returned a list of names historically; it now returns dicts
    # ({project, branch, graph}), so the old `name in repositories`
    # match silently failed and every run re-indexed. GRAPH.LIST avoids
    # that schema churn.
    host = os.environ.get("FALKORDB_HOST", "127.0.0.1")
    port = int(os.environ.get("FALKORDB_PORT", "6379"))
    expected_graph = repo_name  # the HTTP path uses bare folder name as graph key
    try:
        r = redis.Redis(host=host, port=port, decode_responses=True, socket_timeout=2)
        graphs = r.execute_command("GRAPH.LIST") or []
        # Match either bare name (legacy) or "code:<name>:<branch>" pattern.
        if expected_graph in graphs or any(
            g == repo_name or g.startswith(f"code:{repo_name}:") for g in graphs
        ):
            print(f"[index] {repo_name} already in FalkorDB; skip")
            return 0.0
    except Exception as exc:  # noqa: BLE001
        print(f"[index] WARN GRAPH.LIST precheck failed ({exc!r}); attempting index anyway")

    print(f"[index] analyzing {repo_path} ...")
    default_ignore = [
        ".git", "venv", ".venv", "node_modules", "__pycache__",
        "rubi/rules",  # sympy: blocks indexing for ~hours otherwise
        "build", "dist", ".tox", ".eggs",
    ]
    # Bounded timeout so a server-side hang surfaces instead of stalling
    # the entire benchmark. 30 min is generous for any sane repo and
    # well below the previous 7200s that masked failures for an hour.
    try:
        with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=1800.0, write=30.0, pool=10.0),
                          headers=headers) as c:
            r = c.post(
                f"{base}/api/analyze_folder",
                json={"path": str(repo_path), "ignore": default_ignore},
            )
            if r.status_code != 200:
                raise RuntimeError(
                    f"analyze_folder returned {r.status_code}: {r.text[:300]}. "
                    f"Check ALLOWED_ANALYSIS_DIR on the API server covers {repo_path}."
                )
        elapsed = time.monotonic() - start
        print(f"[index] indexed {repo_name} in {elapsed:.1f}s")
        return elapsed
    except httpx.ReadTimeout as exc:
        elapsed = time.monotonic() - start
        raise RuntimeError(
            f"analyze_folder read-timeout after {elapsed:.0f}s on {repo_name} — "
            f"API server likely hung indexing. Check uvicorn logs."
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"failed to index {repo_name} at {repo_path}: {exc}") from exc


def _ensure_indexed_mcp(repo_path: Path) -> float:
    """MCP-track equivalent of _ensure_indexed.

    Drives the `index_repo` MCP tool in-process via the bench adapter
    (avoids spawning a second cgraph-mcp just to bootstrap; the agent
    will spawn its own per call). Same skip-if-present optimization
    as the HTTP path: cheap GRAPH.LIST scan against FalkorDB.

    Returns wall-clock seconds spent indexing (0.0 if cache hit / skip).
    """
    from bench.agents import code_graph_mcp_adapter as cgm
    import redis
    start = time.monotonic()

    repo_name = repo_path.name
    branch = os.environ.get("CGRAPH_MCP_BRANCH", "_default")
    host = os.environ.get("FALKORDB_HOST", "127.0.0.1")
    port = int(os.environ.get("FALKORDB_PORT", "6379"))
    expected_graph = f"code:{repo_name}:{branch}"
    try:
        r = redis.Redis(host=host, port=port, decode_responses=True, socket_timeout=2)
        if expected_graph in (r.execute_command("GRAPH.LIST") or []):
            print(f"[index-mcp] {expected_graph} already indexed; skip")
            return 0.0
    except Exception as exc:  # noqa: BLE001
        print(f"[index-mcp] WARN list_graphs failed ({exc!r}); will attempt index anyway")

    print(f"[index-mcp] indexing {repo_path} as {expected_graph} ...")
    try:
        payload = cgm.index_repo(str(repo_path), branch=branch)
        if isinstance(payload, dict) and payload.get("error"):
            print(f"[index-mcp] WARN index_repo error: {payload['error']!r}")
        else:
            print(f"[index-mcp] indexed in {time.monotonic() - start:.1f}s: {payload}")
    except Exception as exc:  # noqa: BLE001
        print(f"[index-mcp] WARN failed to index {repo_name}: {exc!r}")
    return time.monotonic() - start


# ---------------------------------------------------------------------------
# Dry-run stub model
# ---------------------------------------------------------------------------


class _DryRunModel:
    """A stand-in for a real LLM. Exercises mini-swe-agent's full loop
    without making any network calls.

    Returns a single fake "tool call" that submits the task immediately
    using mini-swe-agent's `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`
    bash protocol. The bash command itself echoes a tiny payload that
    proves the per-config env is wired correctly (e.g. PATH for lsp /
    code-graph configs contains `bench/cli/`).

    This is the v2 tool-calls shape: `extra.actions` is a list of dicts
    with a `"command"` key, which is what `LocalEnvironment.execute`
    consumes.
    """

    def __init__(self, *, marker: str = "dry-run-ok") -> None:
        self.n_calls = 0
        self.cost = 0.0
        self.config = type("cfg", (), {
            "model_name": "dry-run-stub",
            "model_dump": lambda self_, **_: {"model_name": "dry-run-stub"},
            "multimodal_regex": "",
        })()
        self._marker = marker

    def query(self, messages: list[dict[str, Any]], **_: Any) -> dict[str, Any]:
        self.n_calls += 1
        usage = {"prompt_tokens": 10 * self.n_calls,
                 "completion_tokens": 5,
                 "total_tokens": 10 * self.n_calls + 5}
        # Bash payload: first line of stdout = sentinel; subsequent lines
        # = final answer. The sentinel makes LocalEnvironment raise
        # Submitted, which the agent treats as a clean exit.
        cmd = (
            "printf 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\\n%s\\n' "
            f"'{self._marker}: PATH=$PATH'"
        )
        return {
            "role": "assistant",
            "content": f"Submitting ({self._marker}).",
            "extra": {
                "actions": [{"command": cmd}],
                "cost": 0.0,
                "response": {"usage": usage},
            },
        }

    # The agent calls these helpers on the model; provide minimal stubs.
    def format_message(self, **kwargs: Any) -> dict[str, Any]:
        return dict(kwargs)

    def format_observation_messages(
        self, message: dict[str, Any], outputs: list[dict[str, Any]],
        template_vars: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return [{"role": "user", "content": str(o.get("output", ""))} for o in outputs]

    def get_template_vars(self, **_: Any) -> dict[str, Any]:
        return {"model_name": "dry-run-stub"}

    def serialize(self) -> dict[str, Any]:
        return {"info": {"config": {"model": {"model_name": "dry-run-stub"},
                                    "model_type": "dry-run-stub"}}}


# ---------------------------------------------------------------------------
# Single-task execution
# ---------------------------------------------------------------------------


def _capture_diff(repo_path: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "diff"], cwd=repo_path, capture_output=True, text=True, check=False,
        )
        return out.stdout
    except FileNotFoundError:
        return ""


def verify_tool_available(config: str, env: dict[str, str], cwd: Path) -> tuple[bool, str]:
    """Smoke-test the agent's primary tool before launching the trajectory.

    Returns (ok, message). When the tool is missing or crashes at startup,
    the agent will silently fall back to plain bash and we'd attribute its
    cheaper trajectory to the "tool" — invalidating the experiment. This
    precheck makes that failure mode loud.
    """
    if config == "baseline":
        return True, "baseline: no tool"
    cmd_map = {
        "lsp": ["lsp", "--help"],
        "code_graph": ["cg", "--help"],
        "code_graph_mcp": ["cg-mcp", "--help"],
    }
    cmd = cmd_map.get(config)
    if cmd is None:
        return True, f"no precheck for config {config!r}"
    try:
        res = subprocess.run(
            cmd, cwd=str(cwd), env=env,
            capture_output=True, text=True, timeout=15,
        )
    except FileNotFoundError as e:
        return False, f"{cmd[0]} not on PATH: {e}"
    except subprocess.TimeoutExpired:
        return False, f"{cmd[0]} --help timed out (>15s)"
    if res.returncode != 0:
        tail = (res.stderr or res.stdout)[-300:]
        return False, f"{cmd[0]} --help returncode={res.returncode}: {tail}"
    return True, f"{cmd[0]} ok"


TOOL_KEYWORDS = {
    "baseline": (),
    "lsp": ("lsp",),
    "code_graph": ("cg ",),
    "code_graph_mcp": ("cg-mcp",),
}

# Bash search commands the agent might fall back to instead of using the
# configured code-navigation tool. Matched as whole tokens against the
# bash command string. Tracked passively as a "fallback_rate" metric so
# we can quantify how often each tool track silently degrades to grep.
_FALLBACK_RE = re.compile(r"(?:^|[\s;&|`(])(grep|rg|find|ack|ag)(?:\s|$)")


def compute_tool_usage(messages: list[dict[str, Any]], config: str) -> dict[str, Any]:
    """Count assistant bash commands that invoke the configured tool vs
    fall back to plain text search.

    Returns {turns, tool_turns, fallback_turns, rate, fallback_rate}.
    - rate = tool_turns / turns (None for baseline)
    - fallback_rate = fallback_turns / turns (always reported; baseline's
      fallback_rate is its raw grep/find usage and serves as a reference
      point — tool tracks should be meaningfully below it).

    A low tool rate combined with a high fallback rate on a tool track
    means the agent abandoned the tool and is operating as a baseline
    with extra preamble.
    """
    kws = TOOL_KEYWORDS.get(config, ())
    turns = 0
    tool_turns = 0
    fallback_turns = 0
    for m in messages:
        if m.get("role") != "assistant":
            continue
        # mini-swe-agent v2 puts the bash command in tool_calls[*].function.arguments
        tcs = m.get("tool_calls") or []
        for tc in tcs:
            fn = tc.get("function") or {}
            if fn.get("name") != "bash":
                continue
            args = fn.get("arguments") or ""
            if isinstance(args, dict):
                args = args.get("command", "")
            if not isinstance(args, str):
                args = str(args)
            turns += 1
            if kws and any(kw in args for kw in kws):
                tool_turns += 1
            if _FALLBACK_RE.search(args):
                fallback_turns += 1
    rate = (tool_turns / turns) if (turns and kws) else None
    fallback_rate = (fallback_turns / turns) if turns else None
    return {
        "turns": turns,
        "tool_turns": tool_turns,
        "rate": rate,
        "fallback_turns": fallback_turns,
        "fallback_rate": fallback_rate,
    }


def run_task(
    task: Task,
    config: str,
    *,
    benchmark: str = "dry_run",
    run_idx: int = 0,
    model_name: str = "anthropic/claude-sonnet-4-5",
    step_limit: int = 50,
    cost_limit: float = 3.0,
    wall_time_limit_seconds: int = 1200,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute a single (task, config) pair.

    Returns a dict with keys:
      metrics       — a `bench.metrics.TaskMetrics` instance.
      trajectory    — the full mini-swe-agent `agent.serialize()` dict.
      exit_status   — "ok" | "error".
      exit_reason   — exception detail if exit_status == "error".
      diff          — `git diff` of the working tree after the run.
    """
    if config not in VALID_CONFIGS:
        raise ValueError(f"unknown config {config!r}; expected one of {VALID_CONFIGS}")

    # Late imports — they trigger litellm side effects.
    from minisweagent.agents.default import DefaultAgent
    from minisweagent.environments.local import LocalEnvironment

    env_vars = config_env(config, task.repo_path)

    # PRECHECK: verify the tool actually launches before spending model $$.
    # If the tool crashes (e.g. cg shim hits "Bad file descriptor" on Python
    # init), the agent will silently fall back to bash for the entire
    # trajectory and we'd attribute its behaviour to the tool. Hard-fail here
    # so the issue is visible.
    if not dry_run:
        tool_ok, tool_msg = verify_tool_available(config, env_vars, task.repo_path)
        if not tool_ok:
            from bench.metrics import TaskMetrics
            return {
                "metrics": TaskMetrics(
                    benchmark=benchmark, task_id=task.task_id, config=config,
                    run_idx=run_idx, outcome="tool_unavailable",
                    wall_clock_sec=0.0,
                ),
                "trajectory": {"info": {"tool_precheck": tool_msg}},
                "exit_status": "error",
                "exit_reason": f"tool precheck failed for {config}: {tool_msg}",
                "diff": "",
            }

    env = LocalEnvironment(cwd=str(task.repo_path), env=env_vars, timeout=120)
    preamble = load_preamble(config)

    if dry_run:
        model: Any = _DryRunModel()
    else:
        from minisweagent.models.litellm_model import LitellmModel

        model = LitellmModel(model_name=model_name)

    agent = DefaultAgent(
        model,
        env,
        system_template=preamble,
        instance_template=load_instance_template(config),
        step_limit=step_limit,
        cost_limit=cost_limit,
        wall_time_limit_seconds=wall_time_limit_seconds,
    )

    started = time.time()
    exit_status = "ok"
    exit_reason = ""
    try:
        agent.run(task=task.problem_statement)
    except Exception as exc:  # noqa: BLE001 — runner classifies all failures
        exit_status = "error"
        exit_reason = f"{type(exc).__name__}: {exc}"
    wall = time.time() - started

    diff = _capture_diff(task.repo_path)
    trajectory = agent.serialize()
    # Ensure the diff is part of the trajectory so the metrics module's
    # patch extractor can find it even if the agent's final message
    # didn't embed it.
    trajectory.setdefault("info", {})["submission"] = diff

    # Tool-usage instrumentation: surface trajectories where the agent
    # silently abandoned the configured tool. Stored on the trajectory
    # and on the metrics row so report.py can flag low-usage runs.
    tool_usage = compute_tool_usage(trajectory.get("messages", []), config)
    trajectory["info"]["tool_usage"] = tool_usage

    from bench.metrics import TaskMetrics, task_metrics_from_trajectory

    metrics: TaskMetrics = task_metrics_from_trajectory(
        trajectory,
        benchmark=benchmark,
        task_id=task.task_id,
        config=config,
        run_idx=run_idx,
        wall_clock_sec=round(wall, 3),
    )
    metrics.tool_usage_rate = tool_usage["rate"]
    metrics.tool_usage_turns = tool_usage["tool_turns"]
    metrics.tool_usage_total = tool_usage["turns"]
    metrics.fallback_turns = tool_usage["fallback_turns"]
    metrics.fallback_rate = tool_usage["fallback_rate"]
    if exit_status == "error":
        metrics.outcome = "error"

    return {
        "metrics": metrics,
        "trajectory": trajectory,
        "exit_status": exit_status,
        "exit_reason": exit_reason,
        "diff": diff,
    }


# ---------------------------------------------------------------------------
# Batch driver
# ---------------------------------------------------------------------------


def _write_trajectory(task_id: str, config: str, trajectory: dict[str, Any],
                      traj_dir: Path) -> Path:
    traj_dir.mkdir(parents=True, exist_ok=True)
    path = traj_dir / f"{task_id}__{config}.json"
    path.write_text(json.dumps(trajectory, indent=2, sort_keys=True, default=str))
    return path


def run_batch(
    tasks: list[Task],
    configs: list[str],
    *,
    benchmark: str = "dry_run",
    results_path: Path = DEFAULT_RESULTS,
    trajectories_dir: Path = DEFAULT_CACHE_DIR / "trajectories",
    **run_kwargs: Any,
) -> list[dict[str, Any]]:
    """Run every (task, config) combination and append rows to a JSONL file."""
    from bench.metrics import append_jsonl

    defer_jsonl = run_kwargs.pop("defer_jsonl", False)
    results_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for task in tasks:
        for cfg in configs:
            res = run_task(task, cfg, benchmark=benchmark, **run_kwargs)
            _write_trajectory(task.task_id, cfg, res["trajectory"], trajectories_dir)
            if not defer_jsonl:
                append_jsonl(results_path, res["metrics"])
            rows.append(res)
    return rows


# ---------------------------------------------------------------------------
# Dry-run dataset
# ---------------------------------------------------------------------------


def _make_dry_run_task(tmp: Path) -> Task:
    """A trivially tiny synthetic repo used by --dry-run.

    The dry-run stub model just submits immediately, so this repo
    doesn't need to be solvable — it only needs to be a valid git
    working tree so `git diff` and `LocalEnvironment` cwd work.
    """
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "hello.py").write_text("print('hi')\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp, check=False)
    subprocess.run(["git", "add", "."], cwd=tmp, check=False)
    subprocess.run(
        ["git", "-c", "user.email=b@b", "-c", "user.name=b", "commit", "-q", "-m", "init"],
        cwd=tmp, check=False,
    )
    return Task(
        task_id="dry-run-1",
        repo_name="dry-run",
        repo_path=tmp,
        problem_statement="No-op task: just confirm the harness works end to end.",
    )


def _make_synthetic_smoke_task(tmp: Path) -> Task:
    """A tiny but **non-trivial** synthetic task used by --real-run.

    Unlike `_make_dry_run_task` (no-op for the stub model), this task
    requires the agent to actually *do* something: read a file, find
    a bug, and submit a patch. It's deliberately ~2-minute work for a
    competent LLM — enough to exercise the trajectory, tool-call,
    token-accounting, and diff-capture paths end-to-end, without the
    cost or time of a SWE-bench task.
    """
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "math_utils.py").write_text(
        "def add(a, b):\n"
        "    # BUG: should return a + b\n"
        "    return a - b\n"
        "\n"
        "def multiply(a, b):\n"
        "    return a * b\n"
    )
    (tmp / "test_math_utils.py").write_text(
        "from math_utils import add, multiply\n"
        "\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n"
        "    assert add(0, 0) == 0\n"
        "    assert add(-1, 1) == 0\n"
        "\n"
        "def test_multiply():\n"
        "    assert multiply(2, 3) == 6\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp, check=False)
    subprocess.run(["git", "add", "."], cwd=tmp, check=False)
    subprocess.run(
        ["git", "-c", "user.email=b@b", "-c", "user.name=b", "commit", "-q", "-m", "init"],
        cwd=tmp, check=False,
    )
    return Task(
        task_id="smoke-add-bug",
        repo_name="smoke-synthetic",
        repo_path=tmp,
        problem_statement=(
            "The `add` function in math_utils.py is buggy: it subtracts "
            "instead of adding. Fix it so that `pytest test_math_utils.py` "
            "passes. Do not modify the tests."
        ),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _verify_smoke_task(repo_path: Path) -> tuple[bool, str]:
    """Run the smoke task's pytest. Returns (resolved, output)."""
    res = subprocess.run(
        ["python", "-m", "pytest", "test_math_utils.py", "-q"],
        cwd=repo_path, capture_output=True, text=True, check=False, timeout=60,
    )
    return res.returncode == 0, res.stdout + res.stderr


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    # Load .env from repo root if present, so users don't have to export
    # provider creds manually. litellm picks up ANTHROPIC_API_KEY /
    # ANTHROPIC_API_BASE / AZURE_API_KEY / GITHUB_API_KEY from process env.
    try:
        from dotenv import load_dotenv

        env_path = REPO_ROOT / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass

    p = argparse.ArgumentParser(description="code-graph benchmark runner")
    p.add_argument("--config", choices=VALID_CONFIGS, action="append",
                   help="one of baseline / lsp / code_graph / code_graph_mcp; repeatable. "
                        "Default: all three.")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true",
                      help="Stub LLM + no-op synthetic task. No API key needed.")
    mode.add_argument("--real-run", action="store_true",
                      help="Real LLM + a tiny synthetic 'add' bug task. "
                           "Validates real token accounting and the actual "
                           "model loop without paying for SWE-bench. "
                           "Requires an LLM API key for the chosen --model.")
    mode.add_argument("--swe-bench", action="store_true",
                      help="Real LLM + SWE-bench Verified instances. "
                           "Use --stage smoke|calibration|headline to pick the "
                           "sample size. Each instance: real clone + checkout "
                           "+ test_patch apply + agent run + FAIL_TO_PASS/"
                           "PASS_TO_PASS pytest verification.")
    p.add_argument("--stage", choices=("smoke", "calibration", "headline"),
                   default="smoke",
                   help="SWE-bench stage (sample size). Only used with --swe-bench.")
    p.add_argument("--limit", type=int, default=None,
                   help="Cap number of instances sampled. Overrides --stage size "
                        "for quick checks (e.g. --limit 1).")
    p.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    p.add_argument("--trajectories", type=Path, default=DEFAULT_CACHE_DIR / "trajectories")
    p.add_argument("--model", default="anthropic/claude-sonnet-4-5",
                   help="litellm model name. Examples: "
                        "'anthropic/claude-sonnet-4-5' (needs ANTHROPIC_API_KEY); "
                        "'github/openai/gpt-4o-mini' (free GitHub Models, "
                        "needs GITHUB_TOKEN with models:read scope); "
                        "'github_copilot/gpt-4o' (uses your Copilot session, "
                        "device-code OAuth on first call).")
    p.add_argument("--step-limit", type=int, default=50)
    p.add_argument("--cost-limit", type=float, default=3.0)
    p.add_argument("--wall-time", type=int, default=1200)
    p.add_argument("--skip-verify", action="store_true",
                   help="Skip SWE-bench Docker verification; record "
                        "outcome=verify_skipped. Useful on hosts without "
                        "Docker for token-cost / tool-usage measurement runs.")
    p.add_argument("--verify-timeout", type=int, default=1800,
                   help="Per-instance verification timeout in seconds "
                        "passed to swebench.harness (default 1800).")
    args = p.parse_args(argv)

    configs = args.config or list(VALID_CONFIGS)

    import tempfile

    rows: list[dict[str, Any]] = []

    if args.swe_bench:
        from bench.datasets.swe_bench import (
            load_instances, sample_instances, prepare_worktree,
            instance_to_task, verify_with_swebench_harness,
        )
        from bench.metrics import append_jsonl

        insts = sample_instances(load_instances(), stage=args.stage)
        if args.limit is not None:
            insts = insts[: args.limit]
        print(f"[swe-bench] stage={args.stage} running {len(insts)} instances "
              f"x {len(configs)} configs = {len(insts) * len(configs)} trajectories")
        for inst in insts:
            for cfg in configs:
                # Resume support: if a trajectory file for this (instance, cfg)
                # already exists, skip the run entirely. Lets us recover from
                # crashes / kills without re-spending tokens on completed work.
                existing_traj = args.trajectories / f"{inst.instance_id}__{cfg}.json"
                if existing_traj.exists():
                    print(f"[resume] {inst.instance_id}/{cfg}: trajectory exists, skip")
                    continue
                # Fresh worktree per (instance, config) to avoid cross-talk.
                wt = prepare_worktree(inst)
                # Rename so each cfg gets a distinct path.
                cfg_wt = wt.parent / f"{inst.instance_id}__{cfg}"
                if cfg_wt.exists():
                    import shutil
                    shutil.rmtree(cfg_wt)
                wt.rename(cfg_wt)
                task = instance_to_task(inst, cfg_wt)
                # For the code-graph track, the agent's `cg` commands query
                # FalkorDB by repo name (= worktree dir name). The graph must
                # exist before the task runs, otherwise every `cg find-symbol`
                # call returns nothing and the agent abandons the tool.
                if cfg == "code_graph":
                    index_sec = _ensure_indexed(cfg_wt)
                elif cfg == "code_graph_mcp":
                    index_sec = _ensure_indexed_mcp(cfg_wt)
                else:
                    index_sec = None
                cfg_rows = run_batch(
                    [task],
                    [cfg],
                    benchmark="swe_bench_verified",
                    results_path=args.results,
                    trajectories_dir=args.trajectories,
                    model_name=args.model,
                    step_limit=args.step_limit,
                    cost_limit=args.cost_limit,
                    wall_time_limit_seconds=args.wall_time,
                    dry_run=False,
                    defer_jsonl=True,
                )
                rows.extend(cfg_rows)
                if cfg_rows and index_sec is not None:
                    cfg_rows[-1]["metrics"].index_sec = index_sec
                # Official SWE-bench harness verification. The agent's
                # patch is on the trajectory metrics; pass it to the
                # Docker-backed harness. When Docker is missing the
                # outcome is recorded as `verifier_unavailable` rather
                # than silently graded `failed`.
                patch = (cfg_rows[-1]["metrics"].patch or "") if cfg_rows else ""
                if args.skip_verify:
                    cfg_rows[-1]["metrics"].outcome = "verify_skipped"
                else:
                    resolved, summary = verify_with_swebench_harness(
                        inst, patch, timeout=args.verify_timeout,
                    )
                    if resolved is None:
                        cfg_rows[-1]["metrics"].outcome = "verifier_unavailable"
                    else:
                        cfg_rows[-1]["metrics"].outcome = (
                            "resolved" if resolved else "failed"
                        )
                    cfg_rows[-1]["verify_summary"] = summary[-300:]
                append_jsonl(args.results, cfg_rows[-1]["metrics"])
    else:
        with tempfile.TemporaryDirectory() as td:
            if args.dry_run:
                task_fn = _make_dry_run_task
                benchmark = "dry_run"
                dry_run = True
            else:
                task_fn = _make_synthetic_smoke_task
                benchmark = "synthetic_smoke"
                dry_run = False

            verify_results: dict[str, bool] = {}
            for cfg in configs:
                repo_path = Path(td) / f"repo-{cfg}"
                task = task_fn(repo_path)
                cfg_rows = run_batch(
                    [task],
                    [cfg],
                    benchmark=benchmark,
                    results_path=args.results,
                    trajectories_dir=args.trajectories,
                    model_name=args.model,
                    step_limit=args.step_limit,
                    cost_limit=args.cost_limit,
                    wall_time_limit_seconds=args.wall_time,
                    dry_run=dry_run,
                    defer_jsonl=args.real_run,
                )
                rows.extend(cfg_rows)
                if args.real_run:
                    from bench.metrics import append_jsonl

                    ok, _ = _verify_smoke_task(repo_path)
                    verify_results[cfg] = ok
                    cfg_rows[-1]["metrics"].outcome = "resolved" if ok else "failed"
                    append_jsonl(args.results, cfg_rows[-1]["metrics"])

    for row in rows:
        m = row["metrics"]
        verdict = f" outcome={m.outcome}" if m.outcome else ""
        print(
            f"[{m.config:>10}] {m.task_id} "
            f"exit={row['exit_status']} "
            f"in={m.input_tokens} out={m.output_tokens} "
            f"tool_calls={m.tool_calls_total} wall={m.wall_clock_sec}s{verdict}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
