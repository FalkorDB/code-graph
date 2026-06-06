"""LocAgent-style code-localization benchmark.

Where the full SWE-bench *fix* task ties all configs on accuracy (because
fixes are localized and grep suffices), this benchmark isolates the
**navigation** problem: given only the issue text, the agent must name the
source file(s) that need to change — without editing anything. We then score
file-level localization (recall / precision / Acc@k / MRR) and the token /
command cost each tool incurs to get there.

Design (see plan.md 2026-05-30 23:30):
  * Test-free worktree under a distinct name `{id}__loc` -> a FRESH FalkorDB
    index that does NOT contain the test_patch (which would leak the answer).
  * One shared, free-form instance template for every config (tools are
    advertised by the per-config preamble; no forced first command).
  * Strict `FINAL_LOCALIZATION_JSON:` sentinel parsing with an explicit
    `parse_error` flag; a regex fallback is recorded for diagnostics only and
    never feeds the headline metric.
  * Gold = non-test, non-doc Python files from the gold patch.

Run:
  uv run python -m bench.runners.localize_runner --set structural \
      --config baseline --config lsp --config code_graph --config code_graph_mcp \
      --limit 30 --model anthropic/claude-opus-4-... \
      --results bench/cache/opus-localize/results.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from bench.runners.mini_runner import (
    DEFAULT_CACHE_DIR,
    VALID_CONFIGS,
    _ensure_indexed,
    _ensure_indexed_mcp,
    config_env,
    load_preamble,
)

LOCALIZE_RESULTS = DEFAULT_CACHE_DIR / "opus-localize" / "results.jsonl"
LOCALIZE_TRAJECTORIES = DEFAULT_CACHE_DIR / "opus-localize" / "trajectories"

SENTINEL = "FINAL_LOCALIZATION_JSON:"

from minisweagent.environments.local import LocalEnvironment  # noqa: E402


class SafeLocalEnvironment(LocalEnvironment):
    """LocalEnvironment whose timeout reliably reaps the whole process tree.

    The stock implementation runs ``subprocess.run(shell=True, timeout=...)``.
    When a command spawns a grandchild that inherits the stdout pipe (e.g. a
    jedi/multilspy language server that hangs while indexing a large repo such
    as Django), the timeout kills only the shell and ``communicate()`` then
    blocks *forever* waiting for the inherited pipe to close — wedging the whole
    agent. We launch each command in its own session and ``SIGKILL`` the entire
    process group on timeout, which closes the pipe and unblocks the read.

    Everything else (the ``COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`` completion
    check, template vars, serialization, pydantic config) is inherited.
    """

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict[str, Any]:
        command = action.get("command", "")
        run_cwd = cwd or self.config.cwd or os.getcwd()
        tmo = timeout or self.config.timeout
        proc = subprocess.Popen(
            command,
            shell=True,
            text=True,
            cwd=run_cwd,
            env=os.environ | self.config.env,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            out, _ = proc.communicate(timeout=tmo)
            output = {"output": out, "returncode": proc.returncode, "exception_info": ""}
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                out, _ = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                out = ""
            output = {
                "output": (out or "") + f"\n[command timed out after {tmo}s; process group killed]",
                "returncode": -1,
                "exception_info": f"TimeoutExpired after {tmo}s",
                "extra": {"exception_type": "TimeoutExpired", "exception": "timeout"},
            }
        self._check_finished(output)
        return output


class TimeoutRetryModel:
    """Wrap a minisweagent model so each API call is bounded by a hard timeout.

    litellm's own ``timeout`` does not reliably interrupt the Azure Anthropic
    passthrough — we have observed an ESTABLISHED socket stall with the Python
    process blocked in a C-level read for 20+ min, CPU frozen, never returning.
    ``SIGALRM`` interrupts even a blocked syscall (PEP 475 re-raises from the
    handler), so we arm it around each ``query`` and retry on stall. The agent's
    own between-step wall-time check then actually becomes reachable.

    All other attributes/methods (cost, n_calls, serialize, format_message, …)
    are delegated to the wrapped model.
    """

    def __init__(self, inner: Any, *, per_call_timeout: int = 180, retries: int = 3):
        self._inner = inner
        self._per_call_timeout = per_call_timeout
        self._retries = retries

    def query(self, messages: list[dict[str, str]], **kwargs) -> dict:
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            def _on_alarm(signum, frame):  # noqa: ARG001
                raise TimeoutError(
                    f"model.query stalled > {self._per_call_timeout}s"
                )

            prev = signal.signal(signal.SIGALRM, _on_alarm)
            signal.alarm(self._per_call_timeout)
            try:
                return self._inner.query(messages, **kwargs)
            except TimeoutError as exc:
                last_exc = exc
                print(
                    f"[warn] model stalled (attempt {attempt + 1}/"
                    f"{self._retries + 1}); retrying",
                    flush=True,
                )
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, prev)
        raise last_exc if last_exc else RuntimeError("model.query failed")

    def __getattr__(self, name: str) -> Any:
        # Delegate everything we don't override (cost, n_calls, serialize, …).
        return getattr(self._inner, name)


# One template for ALL configs. The per-config preamble already advertises the
# available navigation tool (cg / lsp / none); we deliberately do NOT force a
# first command here so the comparison measures *natural* tool usage.
LOCALIZE_INSTANCE_TEMPLATE = f"""\
You are working in the repository at {{{{cwd}}}}.

You are doing CODE LOCALIZATION ONLY. Read the issue below and determine
which source file(s) must be modified to resolve it. **Do NOT edit, create,
or patch any file.** Investigate the codebase with the tools available to
you, then report your answer PROMPTLY — do not over-explore. As soon as you
are reasonably confident of the file(s), submit.

The issue:

{{{{task}}}}

To submit, run a single bash command whose stdout is exactly these two lines
(this is how you end the task):

    echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT
    echo '{SENTINEL} ["pkg/module/foo.py", "pkg/other.py"]'

Replace the array with the real repo-relative source file paths you believe
must change, most-likely first. List only implementation files (exclude
tests). The text after `{SENTINEL}` MUST be a valid JSON array of strings.
"""

_PY_PATH_RE = re.compile(r"[A-Za-z0-9_./-]+\.py")

# Optional forced-workflow ablation. The free-form primary measures *natural*
# tool adoption (which on this model is near-zero — the agent defaults to
# grep/find). To measure the tool's *intrinsic* value when adoption is
# guaranteed, prepend a per-config mandate to invoke the navigation tool first.
_FORCE_TOOL_SNIPPET = {
    "lsp": (
        "MANDATORY WORKFLOW: Before running any grep/find/cat, you MUST use the "
        "`lsp` tool at least once to locate a relevant symbol's definition or "
        "references (e.g. `lsp goto-definition <file> <line> <col>` or "
        "`lsp find-references ...`). Prefer `lsp` over text search throughout.\n\n"
    ),
    "code_graph": (
        "MANDATORY WORKFLOW: Before running any grep/find/cat, you MUST use the "
        "`cg` tool at least once to locate candidate symbols "
        "(`cg search_code --prefix <name>`) and trace cross-file structure "
        "(`cg get-callers` / `cg get-dependencies` / `cg impact-analysis`). "
        "Prefer `cg` over text search throughout.\n\n"
    ),
    "code_graph_mcp": (
        "MANDATORY WORKFLOW: Before running any grep/find/cat, you MUST use the "
        "`cg-mcp` tool at least once to locate candidate symbols "
        "(`cg-mcp search_code --prefix <name>`) and trace cross-file structure "
        "(`cg-mcp get_callers` / `cg-mcp get_dependencies` / "
        "`cg-mcp impact_analysis`). Prefer `cg-mcp` over text search throughout.\n\n"
    ),
}


def build_instance_template(config: str, *, force_tool: bool) -> str:
    """Return the instance template, optionally prefixed with a per-config
    mandate to use the navigation tool first (forced-workflow ablation)."""
    if not force_tool:
        return LOCALIZE_INSTANCE_TEMPLATE
    snippet = _FORCE_TOOL_SNIPPET.get(config)
    if not snippet:  # baseline has no tool; nothing to force.
        return LOCALIZE_INSTANCE_TEMPLATE
    return snippet + LOCALIZE_INSTANCE_TEMPLATE


# ---------------------------------------------------------------------------
# Prediction parsing
# ---------------------------------------------------------------------------

def _all_text(traj: dict[str, Any]) -> str:
    """Concatenate ONLY the model's own outputs (assistant + exit/submission).

    System/user/tool messages are excluded so the example sentinel in the
    instance prompt can never be mistaken for the agent's answer.
    """
    parts: list[str] = []
    for m in traj.get("messages", []):
        if m.get("role") not in ("assistant", "exit"):
            continue
        c = m.get("content", "")
        if isinstance(c, str):
            parts.append(c)
        elif isinstance(c, list):
            for seg in c:
                if isinstance(seg, dict) and isinstance(seg.get("text"), str):
                    parts.append(seg["text"])
    # Also include the captured submission text if present.
    sub = traj.get("info", {}).get("submission")
    if isinstance(sub, str):
        parts.append(sub)
    return "\n".join(parts)


def _norm_path(p: str) -> str:
    p = p.strip().strip('"').strip("'")
    if p.startswith("./"):
        p = p[2:]
    if p.startswith("b/") or p.startswith("a/"):
        p = p[2:]
    return p


def parse_prediction(traj: dict[str, Any]) -> tuple[list[str], bool, list[str]]:
    """Return (pred_files, parse_error, fallback_files).

    Primary: the LAST `FINAL_LOCALIZATION_JSON:` sentinel followed by a JSON
    array. `parse_error` is True when no sentinel+valid-array is found.
    `fallback_files` is a diagnostic regex scan (NOT used for headline).
    """
    text = _all_text(traj)
    fallback: list[str] = []
    seen: set[str] = set()
    for m in _PY_PATH_RE.finditer(text):
        fp = _norm_path(m.group(0))
        if fp not in seen:
            seen.add(fp)
            fallback.append(fp)

    idx = text.rfind(SENTINEL)
    if idx == -1:
        return [], True, fallback
    after = text[idx + len(SENTINEL):]
    # find the first balanced [...] JSON array
    start = after.find("[")
    if start == -1:
        return [], True, fallback
    depth = 0
    end = -1
    for i in range(start, len(after)):
        if after[i] == "[":
            depth += 1
        elif after[i] == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        return [], True, fallback
    blob = after[start : end + 1]
    try:
        arr = json.loads(blob)
        if not isinstance(arr, list):
            return [], True, fallback
    except json.JSONDecodeError:
        return [], True, fallback
    pred: list[str] = []
    pseen: set[str] = set()
    for item in arr:
        if not isinstance(item, str):
            continue
        fp = _norm_path(item)
        if fp and fp not in pseen:
            pseen.add(fp)
            pred.append(fp)
    return pred, False, fallback


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_localization(pred: list[str], gold: list[str]) -> dict[str, Any]:
    gold_set = set(gold)
    pred_set = set(pred)
    inter = gold_set & pred_set
    recall = len(inter) / len(gold_set) if gold_set else 0.0
    precision = len(inter) / len(pred_set) if pred_set else 0.0
    all_found = gold_set.issubset(pred_set) if gold_set else False

    def acc_at_k(k: int) -> bool:
        return gold_set.issubset(set(pred[:k])) if gold_set else False

    # MRR: reciprocal rank of the first gold hit in the predicted order.
    mrr = 0.0
    for rank, fp in enumerate(pred, start=1):
        if fp in gold_set:
            mrr = 1.0 / rank
            break
    return {
        "file_recall": round(recall, 4),
        "file_precision": round(precision, 4),
        "file_all_found": all_found,
        "acc_at_1": acc_at_k(1),
        "acc_at_3": acc_at_k(3),
        "acc_at_5": acc_at_k(5),
        "file_mrr": round(mrr, 4),
    }


# ---------------------------------------------------------------------------
# Single run
# ---------------------------------------------------------------------------

def run_localize_task(
    inst: Any,
    config: str,
    *,
    model_name: str,
    step_limit: int = 30,
    cost_limit: float = 2.0,
    wall_time_limit_seconds: int = 900,
    force_tool: bool = False,
) -> dict[str, Any]:
    from bench.datasets import swe_bench as sb

    if config not in VALID_CONFIGS:
        raise ValueError(f"unknown config {config!r}")

    repo_path = sb.prepare_localize_worktree(inst)
    gold_files = sb.gold_changed_files(inst.patch, source_only=True)
    gold_syms = sb.gold_symbols(inst, repo_path)
    leak = sb.leakage_flags(inst, gold_files)

    # Fresh, test-free index for the graph configs.
    if config == "code_graph":
        _ensure_indexed(repo_path)
    elif config == "code_graph_mcp":
        _ensure_indexed_mcp(repo_path)

    from minisweagent.agents.default import DefaultAgent
    from minisweagent.models.litellm_model import LitellmModel

    env_vars = config_env(config, repo_path)
    env = SafeLocalEnvironment(cwd=str(repo_path), env=env_vars, timeout=120)
    agent = DefaultAgent(
        TimeoutRetryModel(
            LitellmModel(
                model_name=model_name,
                model_kwargs={"timeout": 180},
            ),
            per_call_timeout=180,
            retries=3,
        ),
        env,
        system_template=load_preamble(config),
        instance_template=build_instance_template(config, force_tool=force_tool),
        step_limit=step_limit,
        cost_limit=cost_limit,
        wall_time_limit_seconds=wall_time_limit_seconds,
    )

    started = time.time()
    exit_status = "ok"
    try:
        agent.run(task=inst.problem_statement)
    except Exception as exc:  # noqa: BLE001
        exit_status = f"error:{type(exc).__name__}"
    wall = round(time.time() - started, 3)
    traj = agent.serialize()

    pred, parse_error, fallback = parse_prediction(traj)
    sc = score_localization(pred, gold_files)

    from bench.metrics import task_metrics_from_trajectory

    tm = task_metrics_from_trajectory(
        traj, benchmark="swe_localize", task_id=inst.instance_id,
        config=config, wall_clock_sec=wall,
    )

    row = {
        "benchmark": "swe_localize",
        "task_id": inst.instance_id,
        "config": config,
        "force_tool": force_tool,
        "input_tokens": tm.input_tokens,
        "output_tokens": tm.output_tokens,
        "tool_calls_total": tm.tool_calls_total,
        "tool_calls_by_name": tm.tool_calls_by_name,
        "wall_clock_sec": wall,
        "exit_status": exit_status,
        "gold_files": gold_files,
        "gold_files_count": len(gold_files),
        "gold_dirs_count": len({str(Path(f).parent) for f in gold_files}),
        "gold_symbols": gold_syms,
        "symbol_mappable": bool(gold_syms),
        "predicted_files": pred,
        "predicted_files_fallback": fallback[:20],
        "parse_error": parse_error,
        "is_structural": sb.is_structural(inst),
        **leak,
        **sc,
    }
    return {"row": row, "trajectory": traj}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _write_trajectory(task_id: str, config: str, traj: dict[str, Any], d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{task_id}__{config}.json").write_text(
        json.dumps(traj, indent=2, sort_keys=True, default=str)
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LocAgent-style localization benchmark")
    p.add_argument("--config", choices=VALID_CONFIGS, action="append",
                   help="repeatable; defaults to baseline/lsp/code_graph "
                        "(code_graph_mcp omitted by default: HTTP/MCP transport "
                        "parity already established at n=40, and this worktree's "
                        "venv lacks the mcp module)")
    p.add_argument("--set", choices=("cached", "structural", "all"), default="structural",
                   help="cached=prior n=40 ids (pilot); structural=multi-file/dir gold")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--model", default="anthropic/claude-opus-4-5")
    p.add_argument("--results", type=Path, default=LOCALIZE_RESULTS)
    p.add_argument("--trajectories", type=Path, default=LOCALIZE_TRAJECTORIES)
    p.add_argument("--step-limit", type=int, default=40)
    p.add_argument("--cost-limit", type=float, default=2.0)
    p.add_argument("--wall-time", type=int, default=900)
    p.add_argument("--cached-ids", type=Path, default=None,
                   help="JSONL/txt of task_ids to use when --set cached")
    p.add_argument("--force-tool", action="store_true",
                   help="forced-workflow ablation: prepend a per-config mandate "
                        "to invoke the navigation tool (cg/lsp) before any "
                        "grep/find. Measures the tool's intrinsic value when "
                        "adoption is guaranteed (free-form adoption is ~0).")
    p.add_argument("--dataset", default=None,
                   help="HF dataset name (default: princeton-nlp/SWE-bench_Verified). "
                        "Use SWE-bench-Live/SWE-bench-Live for a contamination-free, "
                        "less-pretraining-saturated corpus.")
    p.add_argument("--split", default="test",
                   help="dataset split (SWE-bench-Live exposes test/lite/verified/full)")
    p.add_argument("--repos", default=None,
                   help="comma-separated owner/name allowlist for --set structural "
                        "(target large, less-saturated repos)")
    p.add_argument("--python-only", action="store_true",
                   help="require >=1 .py gold file (tools are Python-only)")
    args = p.parse_args(argv)

    configs = args.config or ["baseline", "lsp", "code_graph"]

    from bench.datasets import swe_bench as sb

    all_insts = sb.load_instances(split=args.split, dataset_name=args.dataset)
    by_id = {i.instance_id: i for i in all_insts}

    if args.set == "cached":
        ids: list[str] = []
        src = args.cached_ids
        if src and src.exists():
            for line in src.read_text().splitlines():
                line = line.strip()
                if line:
                    ids.append(json.loads(line)["task_id"] if line.startswith("{") else line)
        else:
            # derive from the prior fix-run results file
            prior = DEFAULT_CACHE_DIR / "opus" / "results.jsonl"
            seen: set[str] = set()
            for line in prior.read_text().splitlines():
                tid = json.loads(line)["task_id"]
                if tid not in seen:
                    seen.add(tid)
                    ids.append(tid)
        insts = [by_id[i] for i in ids if i in by_id]
    elif args.set == "structural":
        repo_allow = (
            {r.strip() for r in args.repos.split(",") if r.strip()}
            if args.repos
            else None
        )
        insts = sb.select_structural(
            all_insts, n=args.limit, repos=repo_allow, python_only=args.python_only
        )
    else:
        insts = all_insts

    if args.limit is not None:
        insts = insts[: args.limit]

    # Drop instances with no source-file gold (e.g. test/doc-only patches).
    insts = [i for i in insts if sb.gold_changed_files(i.patch, source_only=True)]

    print(f"[localize] {len(insts)} instances x {len(configs)} configs "
          f"({args.set} set), model={args.model}")
    args.results.parent.mkdir(parents=True, exist_ok=True)

    done: set[tuple[str, str]] = set()
    if args.results.exists():
        for line in args.results.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            done.add((r["task_id"], r["config"]))

    with args.results.open("a") as out:
        for inst in insts:
            for cfg in configs:
                if (inst.instance_id, cfg) in done:
                    print(f"[resume] {inst.instance_id}/{cfg} exists; skip")
                    continue
                print(f"[run] {inst.instance_id}/{cfg} ...", flush=True)
                try:
                    res = run_localize_task(
                        inst, cfg, model_name=args.model,
                        step_limit=args.step_limit, cost_limit=args.cost_limit,
                        wall_time_limit_seconds=args.wall_time,
                        force_tool=args.force_tool,
                    )
                except Exception as exc:  # noqa: BLE001
                    print(f"[error] {inst.instance_id}/{cfg}: {exc!r}", flush=True)
                    continue
                out.write(json.dumps(res["row"]) + "\n")
                out.flush()
                _write_trajectory(inst.instance_id, cfg, res["trajectory"], args.trajectories)
                r = res["row"]
                print(f"[done] {inst.instance_id}/{cfg} "
                      f"acc@1={r['acc_at_1']} recall={r['file_recall']} "
                      f"in={r['input_tokens']} parse_err={r['parse_error']}", flush=True)
    print("[localize] DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
