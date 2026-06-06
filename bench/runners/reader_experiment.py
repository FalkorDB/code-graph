"""Stage A offline "reader experiment" for the relationship_explanation lever.

Background
----------
The corrected stratified measurement (files/benchmark-report-corrected-stratified.md)
found that on the cg-n10-hardened batch the code-graph search tool *surfaces* gold
files well (exposure 0.824) but the agent *adopts* them poorly (adoption 0.536):
~70% of the recall loss is surfaced-but-dropped gold, not retrieval misses.

This harness tests ONE cheap, non-overfitting lever before committing to an
expensive end-to-end factorial: does annotating each search_code result with a
FACTUAL ``relationship_explanation`` (WHY two files relate, e.g. "both override
``value_to_string``") increase how often a single-turn reader keeps a surfaced
gold file?

It is fully OFFLINE w.r.t. the graph: it re-uses the search_code outputs already
captured in the cg-n10-hardened run dirs, re-annotates them per arm, and presents
them to an isolated single-turn Copilot agent that has NO tools and NO repository
access — so the only thing that varies between arms is the annotation schema.

Arms (rubber-duck-mandated)
---------------------------
* ``off``     — captured results as-is (no relationship_explanation).
* ``placebo`` — length-matched neutral filler in the same field (controls for
                "more text in the result" rather than "the explanation content").
* ``explain`` — the factual relationship_explanation.

The surfaced set is IDENTICAL across arms ("fixed-opportunity adoption"): every
arm sees the same files; only the annotation differs.

Primary metric
--------------
Paired per-instance file_recall (NOT raw adoption). Secondary: fixed-opportunity
adoption (of gold files surfaced anywhere in the captures, how many the reader
predicts), acc@k, MRR, and tokens. Paired bootstrap CIs across the shared task
set.

Usage
-----
    python -m bench.runners.reader_experiment \
        --run-dir bench/cache/cg-n10-hardened \
        --model claude-opus-4.8 \
        --out bench/cache/reader-stageA

Add ``--dry-run`` to render prompts + arms without spending any LLM tokens.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import random
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

# --- repo-local imports -----------------------------------------------------
_THIS = Path(__file__).resolve()
_BENCH = _THIS.parents[1]            # .../bench
_REPO = _BENCH.parent               # .../mcp-t17
if str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

from runners import copilot_runner as cr  # noqa: E402
from analysis.reader_capture import capture_search_calls  # noqa: E402

# rel_explain lives in the mcp-smoke worktree (the live server the bench uses).
_REL_EXPLAIN_DIR = (
    _REPO.parent.parent / ".worktrees" / "mcp-smoke" / "api" / "mcp" / "tools"
)
if _REL_EXPLAIN_DIR.is_dir() and str(_REL_EXPLAIN_DIR) not in sys.path:
    sys.path.insert(0, str(_REL_EXPLAIN_DIR))
import rel_explain  # noqa: E402

ARMS = ("off", "placebo", "explain")

# Boundary markers in the captured prompt.txt (see plan + sample inspection).
_PROBLEM_END = "\nInvestigate the repository to determine"


# ---------------------------------------------------------------------------
# Loading captured tasks
# ---------------------------------------------------------------------------
def _load_gold(run_dir: Path, model: str) -> dict[str, list[str]]:
    """Map task_id -> gold_files for the code_graph config rows."""
    results = run_dir / model / "results.jsonl"
    gold: dict[str, list[str]] = {}
    for line in results.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("config") != "code_graph":
            continue
        tid = row.get("task_id")
        if tid and tid not in gold:
            gold[tid] = list(row.get("gold_files") or [])
    return gold


def _extract_problem(prompt_text: str) -> str:
    """Pull the bare problem statement out of the captured localize prompt."""
    # Everything after the first line ("You are localizing ... checked out at X.")
    nl = prompt_text.find("\n")
    body = prompt_text[nl + 1:] if nl != -1 else prompt_text
    end = body.find(_PROBLEM_END)
    if end != -1:
        body = body[:end]
    return body.strip()


def load_tasks(run_dir: Path, model: str) -> list[dict[str, Any]]:
    """Return ordered task records with problem statement, gold, and captures."""
    gold_map = _load_gold(run_dir, model)
    runs_root = run_dir / "runs" / model / "localize" / "nudged" / "code_graph"
    tasks: list[dict[str, Any]] = []
    for task_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        tid = task_dir.name
        prompt_f = task_dir / "prompt.txt"
        stdout_f = task_dir / "logs" / "stdout.jsonl"
        if not prompt_f.exists() or not stdout_f.exists():
            continue
        calls = capture_search_calls(stdout_f)
        if not calls:
            continue
        tasks.append(
            {
                "task_id": tid,
                "problem": _extract_problem(prompt_f.read_text()),
                "gold_files": [cr._norm_path(g) for g in gold_map.get(tid, [])],
                "calls": calls,
            }
        )
    return tasks


# ---------------------------------------------------------------------------
# Arm construction + prompt rendering
# ---------------------------------------------------------------------------
def annotate_calls(calls: list[dict[str, Any]], arm: str) -> list[dict[str, Any]]:
    """Deep-copy + re-annotate every call's results for the given arm."""
    out: list[dict[str, Any]] = []
    for call in calls:
        results = copy.deepcopy(call["results"])
        annotated = rel_explain.annotate_results(results, call["query"], arm)
        out.append({"query": call["query"], "results": annotated})
    return out


def surfaced_files(calls: list[dict[str, Any]]) -> set[str]:
    """Every file the captures put in front of the agent (primary + related)."""
    files: set[str] = set()
    for call in calls:
        for r in call["results"]:
            f = r.get("file")
            if f:
                files.add(cr._norm_path(f))
            for rel in r.get("likely_related_files") or []:
                rf = rel.get("file")
                if rf:
                    files.add(cr._norm_path(rf))
    return files


_READER_INSTRUCTIONS = (
    "You are localizing (not fixing) a bug in a Python repository. You do NOT "
    "have access to the repository or any tools. Below is the bug report followed "
    "by the complete output of a code-navigation search tool that was run against "
    "the repository during an earlier investigation. Each result lists a file, a "
    "matched symbol, and (where available) related files with an explanation of "
    "how they relate.\n\n"
    "Determine which SOURCE files must be edited to fix the issue, reasoning ONLY "
    "from the bug report and the search results shown. Prefer files that the "
    "evidence most directly implicates. List Python source files only (no tests, "
    "no docs).\n"
)

_READER_SENTINEL_INSTR = (
    "\nFinish your final message with a single line in EXACTLY this format "
    "(most-likely file first, repo-root-relative paths):\n\n"
    f"{cr.LOCALIZE_SENTINEL} [\"pkg/module_a.py\", \"pkg/module_b.py\"]\n\n"
    "Write that line as plain text in your own message."
)


def render_prompt(problem: str, calls: list[dict[str, Any]]) -> str:
    parts = [_READER_INSTRUCTIONS, "\n=== BUG REPORT ===\n", problem, "\n"]
    parts.append("\n=== CODE-NAVIGATION SEARCH RESULTS ===\n")
    for i, call in enumerate(calls, start=1):
        parts.append(f"\n--- search_code call {i}: query={call['query']!r} ---\n")
        parts.append(json.dumps(call["results"], indent=1, ensure_ascii=False))
        parts.append("\n")
    parts.append(_READER_SENTINEL_INSTR)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Isolated single-turn invocation (NO tools, NO repo)
# ---------------------------------------------------------------------------
def run_isolated_reader(
    *, prompt: str, model: str, log_dir: Path, wall_time: float
) -> dict[str, Any]:
    """Invoke Copilot single-turn with ZERO tools; answer purely from the prompt.

    ``--available-tools=`` (empty) is the key: the model gets no tools and must
    answer from the prompt-embedded evidence only. ``--log-level debug`` is
    required for ``process-*.log`` files (token usage) to be written.
    """
    log_dir = log_dir.resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    stdout, stderr, returncode = "", "", None
    timed_out = False
    for attempt in range(1, cr.COPILOT_MAX_ATTEMPTS + 1):
        session_id = str(uuid.uuid4())
        cmd = [
            "copilot", "-p", prompt,
            "--model", model,
            "--output-format", "json",
            "--no-remote",
            "--disable-builtin-mcps",
            "--available-tools=",
            "--log-level", "debug",
            "--log-dir", str(log_dir),
            "--session-id", session_id,
        ]
        _effort = cr._resolve_reasoning_effort()
        if _effort:
            cmd += ["--effort", _effort]
        timed_out = False
        proc = subprocess.Popen(
            cmd,
            cwd=str(log_dir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=wall_time)
        except subprocess.TimeoutExpired:
            timed_out = True
            cr._kill_group(proc.pid)
            try:
                stdout, stderr = proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                stdout, stderr = "", ""
        returncode = proc.returncode
        if timed_out or not cr._is_transient_startup_failure(returncode, stdout, stderr):
            break
        if attempt < cr.COPILOT_MAX_ATTEMPTS:
            time.sleep(cr.COPILOT_RETRY_BACKOFF_SEC)
    (log_dir / "stdout.jsonl").write_text(stdout or "")
    (log_dir / "stderr.txt").write_text(stderr or "")
    return {"stdout": stdout or "", "returncode": returncode, "timed_out": timed_out}


def _final_text(stdout: str) -> str:
    """Extract assistant-visible text from the Copilot CLI JSONL event stream.

    The CLI emits one JSON object per line, each shaped
    ``{type, data, id, timestamp, ...}``. The assistant's final visible text
    (carrying the ``FINAL_LOCALIZATION_JSON:`` sentinel) lives in
    ``assistant.message`` events under ``data.content`` (a string). Streaming
    deltas arrive as ``assistant.message_delta`` events; we fall back to
    assembling those, and finally to a terminal ``result`` event, if no
    consolidated message is present.
    """
    messages: list[str] = []
    deltas: list[str] = []
    result_text = ""
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue
        t = ev.get("type")
        data = ev.get("data")
        if t == "assistant.message" and isinstance(data, dict):
            content = data.get("content")
            if isinstance(content, str) and content:
                messages.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and isinstance(block.get("text"), str):
                        messages.append(block["text"])
        elif t == "assistant.message_delta" and isinstance(data, dict):
            for key in ("content", "delta", "text"):
                val = data.get(key)
                if isinstance(val, str) and val:
                    deltas.append(val)
                    break
        elif t == "result":
            if isinstance(data, str):
                result_text = data
            elif isinstance(data, dict):
                for key in ("content", "text", "result"):
                    val = data.get(key)
                    if isinstance(val, str) and val:
                        result_text = val
                        break
        # Legacy single-object shape (older CLI): {type:"assistant", message:{content:[...]}}
        elif t == "assistant" and isinstance(ev.get("message"), dict):
            for block in ev["message"].get("content") or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    messages.append(block.get("text") or "")

    if messages:
        return "\n".join(messages)
    if deltas:
        return "".join(deltas)
    return result_text


# ---------------------------------------------------------------------------
# Scoring + paired bootstrap
# ---------------------------------------------------------------------------
def adoption(pred: list[str], surfaced_gold: set[str]) -> float | None:
    if not surfaced_gold:
        return None
    keep = surfaced_gold & {cr._norm_path(p) for p in pred}
    return len(keep) / len(surfaced_gold)


def paired_bootstrap(
    deltas: list[float], n: int = 10000, seed: int = 20260604
) -> dict[str, float]:
    """Mean delta + 95% bootstrap CI over paired per-instance deltas."""
    if not deltas:
        return {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0, "n": 0}
    rng = random.Random(seed)
    means = []
    m = len(deltas)
    for _ in range(n):
        sample = [deltas[rng.randrange(m)] for _ in range(m)]
        means.append(sum(sample) / m)
    means.sort()
    return {
        "mean": sum(deltas) / m,
        "ci_low": means[int(0.025 * n)],
        "ci_high": means[int(0.975 * n)],
        "n": m,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Stage A reader experiment")
    ap.add_argument("--run-dir", required=True, type=Path,
                    help="cg-n10-hardened cache dir (contains <model>/results.jsonl + runs/)")
    ap.add_argument("--model", default="claude-opus-4.8")
    ap.add_argument("--out", required=True, type=Path, help="output cache dir")
    ap.add_argument("--arms", default=",".join(ARMS),
                    help="comma-separated subset of off,placebo,explain")
    ap.add_argument("--wall-time", type=float, default=420.0)
    ap.add_argument("--limit", type=int, default=0, help="limit #tasks (0=all)")
    ap.add_argument("--dry-run", action="store_true",
                    help="render arms+prompts, write them, no LLM calls")
    args = ap.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    for a in arms:
        if rel_explain.normalize_mode(a) != a:
            print(f"WARNING: arm {a!r} normalizes to {rel_explain.normalize_mode(a)!r}")

    tasks = load_tasks(args.run_dir, args.model)
    if args.limit:
        tasks = tasks[: args.limit]
    if not tasks:
        print("No tasks loaded — check --run-dir/--model.", file=sys.stderr)
        return 2
    print(f"Loaded {len(tasks)} tasks; arms={arms}; model={args.model}")

    args.out.mkdir(parents=True, exist_ok=True)
    results_path = args.out / "reader_results.jsonl"
    rows: list[dict[str, Any]] = []

    with results_path.open("w") as out_f:
        for ti, task in enumerate(tasks, start=1):
            tid = task["task_id"]
            gold = set(task["gold_files"])
            surf = surfaced_files(task["calls"])
            surf_gold = surf & gold
            for arm in arms:
                acalls = annotate_calls(task["calls"], arm)
                prompt = render_prompt(task["problem"], acalls)
                log_dir = args.out / "runs" / tid / arm
                log_dir.mkdir(parents=True, exist_ok=True)
                (log_dir / "prompt.txt").write_text(prompt)
                tag = f"[{ti}/{len(tasks)}] {tid} :: {arm}"
                if args.dry_run:
                    print(f"{tag}  (dry-run) prompt={len(prompt)}B "
                          f"surfaced_gold={len(surf_gold)}/{len(gold)}")
                    continue
                t0 = time.time()
                rr = run_isolated_reader(
                    prompt=prompt, model=args.model,
                    log_dir=log_dir, wall_time=args.wall_time,
                )
                final = _final_text(rr["stdout"])
                pred, perr, fallback = cr.parse_localization(final)
                score = cr.score_localization(pred, sorted(gold))
                toks = cr.parse_tokens_from_logs(log_dir)
                row = {
                    "task_id": tid,
                    "arm": arm,
                    "model": args.model,
                    "gold_files": sorted(gold),
                    "surfaced_gold": sorted(surf_gold),
                    "pred_files": pred,
                    "file_recall": score["file_recall"],
                    "file_precision": score["file_precision"],
                    "file_all_found": score["file_all_found"],
                    "acc_at_1": score["acc_at_1"],
                    "acc_at_3": score["acc_at_3"],
                    "acc_at_5": score["acc_at_5"],
                    "file_mrr": score["file_mrr"],
                    "adoption": adoption(pred, surf_gold),
                    "parse_error": perr,
                    "parse_fallback": fallback,
                    "input_tokens": toks["input_tokens"],
                    "output_tokens": toks["output_tokens"],
                    "reasoning_tokens": toks["reasoning_tokens"],
                    "usage_blocks": toks["usage_blocks"],
                    "timed_out": rr["timed_out"],
                    "returncode": rr["returncode"],
                    "wall_sec": round(time.time() - t0, 1),
                    "prompt_bytes": len(prompt),
                }
                rows.append(row)
                out_f.write(json.dumps(row) + "\n")
                out_f.flush()
                print(f"{tag}  recall={score['file_recall']} "
                      f"adopt={row['adoption']} in={toks['input_tokens']} "
                      f"err={perr} wall={row['wall_sec']}s")

    if args.dry_run or not rows:
        print(f"\nWrote prompts under {args.out/'runs'}. Done (dry-run={args.dry_run}).")
        return 0

    _summarize(rows, arms, args.out)
    return 0


def _summarize(rows: list[dict[str, Any]], arms: list[str], out: Path) -> None:
    by: dict[str, dict[str, dict[str, Any]]] = {a: {} for a in arms}
    for r in rows:
        by[r["arm"]][r["task_id"]] = r

    def col(arm: str, key: str) -> list[float]:
        return [v[key] for v in by[arm].values() if v.get(key) is not None]

    print("\n================ STAGE A SUMMARY ================")
    hdr = f"{'arm':10s} {'recall':>8s} {'adopt':>8s} {'acc@1':>7s} {'mrr':>7s} {'in_med':>9s}"
    print(hdr)
    import statistics as st
    for a in arms:
        rec = col(a, "file_recall")
        ado = col(a, "adoption")
        a1 = col(a, "acc_at_1")
        mrr = col(a, "file_mrr")
        intok = col(a, "input_tokens")
        print(f"{a:10s} {st.mean(rec):8.3f} "
              f"{(st.mean(ado) if ado else 0):8.3f} "
              f"{st.mean(a1):7.3f} {st.mean(mrr):7.3f} "
              f"{int(st.median(intok)) if intok else 0:9d}")

    # Paired deltas vs 'off' baseline.
    base = "off" if "off" in arms else arms[0]
    print(f"\nPaired deltas vs {base!r} (95% bootstrap CI):")
    for a in arms:
        if a == base:
            continue
        common = sorted(set(by[a]) & set(by[base]))
        for metric in ("file_recall", "adoption"):
            deltas = []
            for t in common:
                va, vb = by[a][t].get(metric), by[base][t].get(metric)
                if va is None or vb is None:
                    continue
                deltas.append(va - vb)
            bs = paired_bootstrap(deltas)
            print(f"  {a:8s} Δ{metric:13s} "
                  f"mean={bs['mean']:+.3f} CI[{bs['ci_low']:+.3f},{bs['ci_high']:+.3f}] n={bs['n']}")

    summary_path = out / "summary.json"
    summary_path.write_text(json.dumps(
        {"arms": arms, "n_tasks": len(by[arms[0]]), "rows": rows}, indent=1))
    print(f"\nWrote {summary_path}")


if __name__ == "__main__":
    raise SystemExit(main())
