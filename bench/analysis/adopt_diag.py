"""Per-arm diagnostics for the Lane 1 adoption-calibration pilot.

Compares the CTRL / SEM / RAT arms (``prompt_mode`` in ``adopt-ctrl`` /
``adopt-sem`` / ``adopt-rat``) on one results.jsonl, all on the code_graph +
localize track. Reports, side by side per arm:

* candidate-level calibration (macro, **macro_strict** = prereg PRIMARY, micro)
  over ALL surfaced candidates, plus the same restricted to the **GRAPH-WRONG**
  control subset (rank-1 graph hit verified non-gold);
* exposure / adoption aggregates and **per-arm exposure drift** (the harness is
  agent-driven, so SEM/RAT may surface different candidate sets than CTRL --
  prereg amendment "identical candidate sets is measured, not forced");
* token deltas (median total / output / **visible_output = output - reasoning**
  / input / premium_requests / turns) so the RAT thinking-vs-calibration
  confound is attributable;
* a **RAT compliance audit**: did the agent emit the mandated ``KEEP``/``DROP``
  lines, and is the final answer consistent with them (no DROP file kept).

The GRAPH-WRONG subset is selected ONCE from a reference arm (default
``adopt-ctrl``) and the SAME task set is applied to every arm, so the control is
fixed across arms rather than re-derived per arm.

Run:
    uv run python -m bench.analysis.adopt_diag <results.jsonl> [--json out.json]
        [--ref-arm adopt-ctrl]
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path

from bench.analysis.adopt_controls import select_graph_wrong
from bench.analysis.exposure_adoption import (
    analyze_batch,
    candidate_calibration,
    row_stdout_path,
)

ARM_PROMPT_MODES = ("adopt-ctrl", "adopt-sem", "adopt-rat")

# A KEEP/DROP decision line from the RAT step. The prompt format is
# ``KEEP <file> — <reason>`` / ``DROP <file> — <reason>``; the file may be
# wrapped in backticks and the dash is an em dash, en dash or hyphen. We only
# need the decision verb and the path token, so we accept any leading list
# marker / bullet and stop at the first whitespace, backtick, em/en dash or colon.
_RAT_LINE = re.compile(
    r"^\s*[-*>\d.)\]\s]*`?\s*(KEEP|DROP)\b[\s:`]*([^\s`—–:]+)",
    re.IGNORECASE,
)


def _norm(path: str) -> str:
    """Repo-root-relative posix-ish normalization (mirrors copilot_runner)."""
    p = path.strip().strip("'\"`").strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    for prefix in ("a/", "b/"):
        if p.startswith(prefix):
            p = p[len(prefix):]
    return p.lstrip("/")


def parse_rat_decisions(agent_text: str) -> dict[str, str]:
    """Map normalized file -> final decision ("keep"/"drop") from RAT lines.

    Last decision for a file wins (the agent may revise). Only lines that match
    the KEEP/DROP contract are considered; prose mentioning the words is ignored
    because the verb must be line-initial (after optional list markers).
    """
    decisions: dict[str, str] = {}
    for line in agent_text.splitlines():
        m = _RAT_LINE.match(line)
        if not m:
            continue
        verb = m.group(1).lower()
        f = _norm(m.group(2))
        if f:
            decisions[f] = "keep" if verb == "keep" else "drop"
    return decisions


def rat_audit(agent_text: str, pred_files: list[str]) -> dict:
    """Did the agent run the keep/drop step, and is the answer consistent?

    * ``compliant`` -- emitted at least one KEEP/DROP decision line.
    * ``consistent`` -- no file the agent marked DROP appears in the final
      answer (the prereg requires the final answer to honor the decisions).
    * ``kept_omitted`` -- files marked KEEP but absent from the final answer
      (allowed by the prompt, but tracked: silent erosion after deciding keep).
    """
    decisions = parse_rat_decisions(agent_text)
    pred = {_norm(p) for p in (pred_files or [])}
    kept = {f for f, d in decisions.items() if d == "keep"}
    dropped = {f for f, d in decisions.items() if d == "drop"}
    dropped_but_kept = sorted(dropped & pred)
    kept_omitted = sorted(kept - pred)
    return {
        "compliant": bool(decisions),
        "n_keep": len(kept),
        "n_drop": len(dropped),
        "consistent": not dropped_but_kept,
        "dropped_but_kept": dropped_but_kept,
        "kept_omitted": kept_omitted,
    }


def _median(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def token_summary(rows: list[dict]) -> dict:
    """Median token / step usage across an arm's completed rows.

    ``visible_output`` excludes hidden reasoning tokens so a RAT calibration win
    can be separated from "the model just thought/typed more".
    """
    def col(key: str) -> list[float]:
        return [r[key] for r in rows if r.get(key) is not None]

    visible = [
        r.get("output_tokens", 0) - r.get("reasoning_tokens", 0)
        for r in rows
        if r.get("output_tokens") is not None
    ]
    return {
        "n_rows": len(rows),
        "median_total_tokens": _median(col("total_tokens")),
        "median_output_tokens": _median(col("output_tokens")),
        "median_visible_output_tokens": _median(visible),
        "median_reasoning_tokens": _median(col("reasoning_tokens")),
        "median_input_tokens": _median(col("input_tokens")),
        "median_premium_requests": _median(col("premium_requests")),
        "median_num_turns": _median(col("num_turns")),
    }


def _agent_text_for(batch_root: Path, model: str, row: dict) -> str:
    """Read the saved agent_text.txt for a localize row (fallback: empty)."""
    sp = row_stdout_path(batch_root, model, row)
    if sp is None:
        return ""
    # run_dir/logs/stdout.jsonl -> run_dir/agent_text.txt
    cand = sp.parent.parent / "agent_text.txt"
    if cand.exists():
        return cand.read_text(errors="replace")
    return ""


def _subset_calibration(runs: list[dict], tasks: set[str]) -> dict:
    return candidate_calibration([r for r in runs if r.get("task") in tasks])


def arm_diagnostics(
    results_path: Path,
    arm: str,
    *,
    gold_by_task: dict[str, list[str]],
    graph_wrong_tasks: set[str],
) -> dict:
    """All per-arm diagnostics for one ``adopt-<arm>`` prompt_mode."""
    rows = [json.loads(ln) for ln in results_path.read_text().splitlines() if ln.strip()]
    model = results_path.parent.name
    batch_root = results_path.parent.parent

    arm_rows = [
        r
        for r in rows
        if r.get("config") == "code_graph"
        and r.get("mode") == "localize"
        and r.get("prompt_mode") == arm
        and r.get("completed")
    ]

    batch = analyze_batch(results_path, prompt_mode=arm, mode="localize")
    runs = [r for r in batch["per_run"] if "error" not in r]

    cal_all = candidate_calibration(runs)
    cal_gw = _subset_calibration(runs, graph_wrong_tasks)

    tot_gold = sum(r["n_gold"] for r in runs)
    tot_surf = sum(r["n_surfaced"] for r in runs)
    tot_surf_adopt = sum(r["n_surfaced_adopted"] for r in runs)

    out: dict = {
        "arm": arm,
        "n_runs": len(runs),
        "exposure": {
            "gold_run_x_gold": tot_gold,
            "surfaced": tot_surf,
            "surfaced_adopted": tot_surf_adopt,
            "exposure_recall": round(tot_surf / tot_gold, 4) if tot_gold else None,
            "adoption_rate": round(tot_surf_adopt / tot_surf, 4) if tot_surf else None,
        },
        "calibration_clean": cal_all,
        "calibration_graph_wrong": cal_gw,
        "tokens": token_summary(arm_rows),
    }

    if arm == "adopt-rat":
        audits = []
        for r in arm_rows:
            a = rat_audit(_agent_text_for(batch_root, model, r), r.get("pred_files", []))
            a["task"] = r.get("task_id")
            a["run_idx"] = r.get("run_idx")
            audits.append(a)
        n = len(audits) or 1
        out["rat_audit"] = {
            "n": len(audits),
            "compliance_rate": round(sum(a["compliant"] for a in audits) / n, 4),
            "consistency_rate": round(sum(a["consistent"] for a in audits) / n, 4),
            "n_dropped_but_kept": sum(len(a["dropped_but_kept"]) for a in audits),
            "n_kept_omitted": sum(len(a["kept_omitted"]) for a in audits),
            "per_run": audits,
        }
    return out


def _build_gold_by_task(rows: list[dict]) -> dict[str, list[str]]:
    gold: dict[str, list[str]] = {}
    for r in rows:
        t = r.get("task_id")
        g = r.get("gold_files")
        if t and g and t not in gold:
            gold[t] = list(g)
    return gold


def diagnose(results_path: Path, *, ref_arm: str = "adopt-ctrl") -> dict:
    """Full per-arm diagnostic report for every arm present in the results."""
    rows = [json.loads(ln) for ln in results_path.read_text().splitlines() if ln.strip()]
    model = results_path.parent.name
    batch_root = results_path.parent.parent
    gold_by_task = _build_gold_by_task(rows)

    present = [
        a
        for a in ARM_PROMPT_MODES
        if any(
            r.get("prompt_mode") == a and r.get("config") == "code_graph"
            for r in rows
        )
    ]

    # Freeze the GRAPH-WRONG control task set ONCE from the reference arm so the
    # same tasks are scored across all arms. Fall back to the first present arm.
    sel_arm = ref_arm if ref_arm in present else (present[0] if present else ref_arm)
    ref_batch = analyze_batch(results_path, prompt_mode=sel_arm, mode="localize")
    ref_runs = [r for r in ref_batch["per_run"] if "error" not in r]
    gw = select_graph_wrong(
        ref_runs, gold_by_task, batch_root, model, prompt_mode=sel_arm
    )
    graph_wrong_tasks = {g["task"] for g in gw}

    arms = {
        a: arm_diagnostics(
            results_path, a,
            gold_by_task=gold_by_task, graph_wrong_tasks=graph_wrong_tasks,
        )
        for a in present
    }
    return {
        "results": str(results_path),
        "model": model,
        "arms_present": present,
        "graph_wrong": {"ref_arm": sel_arm, "tasks": sorted(graph_wrong_tasks)},
        "arms": arms,
    }


def _f(x) -> str:
    return f"{x:.3f}" if isinstance(x, (int, float)) else "  n/a"


def _print_report(rep: dict) -> None:
    present = rep["arms_present"]
    if not present:
        print("no adopt-* arms found in results")
        return
    gw = rep["graph_wrong"]
    print(f"model: {rep['model']}   arms: {', '.join(present)}")
    print(f"GRAPH-WRONG subset ({len(gw['tasks'])} tasks, ref={gw['ref_arm']}): "
          f"{gw['tasks']}")

    hdr = f"\n{'metric':32s} " + " ".join(f"{a.replace('adopt-',''):>10s}" for a in present)
    print(hdr)
    print("-" * len(hdr))

    def row(label: str, getter) -> None:
        cells = " ".join(f"{getter(rep['arms'][a]):>10s}" for a in present)
        print(f"{label:32s} {cells}")

    row("runs", lambda d: str(d["n_runs"]))
    row("exposure_recall", lambda d: _f(d["exposure"]["exposure_recall"]))
    row("adoption_rate", lambda d: _f(d["exposure"]["adoption_rate"]))
    row("CLEAN macro_strict F1 (PRIMARY)",
        lambda d: _f(d["calibration_clean"]["macro_strict"]["f1"]))
    row("CLEAN macro F1", lambda d: _f(d["calibration_clean"]["macro"]["f1"]))
    row("CLEAN macro precision",
        lambda d: _f(d["calibration_clean"]["macro"]["precision"]))
    row("CLEAN macro recall",
        lambda d: _f(d["calibration_clean"]["macro"]["recall"]))
    row("GRAPH-WRONG macro precision",
        lambda d: _f(d["calibration_graph_wrong"]["macro"]["precision"]))
    row("GRAPH-WRONG macro_strict F1",
        lambda d: _f(d["calibration_graph_wrong"]["macro_strict"]["f1"]))
    row("median total tokens",
        lambda d: _f(d["tokens"]["median_total_tokens"]))
    row("median visible-output tokens",
        lambda d: _f(d["tokens"]["median_visible_output_tokens"]))
    row("median reasoning tokens",
        lambda d: _f(d["tokens"]["median_reasoning_tokens"]))
    row("median turns", lambda d: _f(d["tokens"]["median_num_turns"]))

    if "adopt-rat" in present:
        ra = rep["arms"]["adopt-rat"].get("rat_audit", {})
        print("\nRAT keep/drop audit:")
        print(f"  compliance (emitted KEEP/DROP) : {_f(ra.get('compliance_rate'))}"
              f"  over n={ra.get('n')}")
        print(f"  consistency (no DROP kept)     : {_f(ra.get('consistency_rate'))}")
        print(f"  dropped-but-kept conflicts     : {ra.get('n_dropped_but_kept')}")
        print(f"  kept-then-omitted (erosion)    : {ra.get('n_kept_omitted')}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results", type=Path)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--ref-arm", default="adopt-ctrl",
                    help="arm whose runs fix the GRAPH-WRONG task subset")
    args = ap.parse_args()

    rep = diagnose(args.results, ref_arm=args.ref_arm)
    _print_report(rep)
    if args.json:
        args.json.write_text(json.dumps(rep, indent=2))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
