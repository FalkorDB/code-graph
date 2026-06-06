"""Retrieval-exposure vs adoption metrics for the code_graph arm.

WHY (per rubber-duck): end-to-end ``file_recall`` conflates two very different
failure modes:
  1. RETRIEVAL miss  -- the graph never surfaced the gold file at all.
  2. ADOPTION miss   -- the graph surfaced the gold file, but the agent dropped
                        it from its final answer during reasoning.
Blaming the graph for (2) is unfair: that is an agent-reasoning property, not a
tool-retrieval property. This module separates them so we can say e.g. "graph
exposed 7/10 missed gold files; the agent adopted only N of them."

For each code_graph run we parse ``stdout.jsonl`` and, for every ``search_code``
call, join ``tool.execution_start`` -> ``tool.execution_complete`` by
``toolCallId`` to recover the UNTRUNCATED result (trace.md/trace.jsonl truncate
tool output). We collect every file the graph surfaced:
  * primary hits          (``file`` + ``score`` + rank position)
  * likely_related_files  (``file`` + ``via`` co_override/shared_method + confidence)

Then, per gold file, we classify exposure:
  * direct@<rank>     -- surfaced as a primary ranked hit
  * related:<via>     -- surfaced only as a likely_related sibling
  * not_surfaced      -- never surfaced by the graph (true retrieval miss)
and adoption: was the surfaced gold file in the run's final ``pred_files``?

Derived metrics (aggregated over runs):
  * exposure_recall = surfaced_gold / total_gold
  * adoption_rate   = adopted_gold / surfaced_gold   (of what the graph surfaced,
                      how much did the agent keep)
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def _iter_search_results(stdout_path: Path):
    """Yield parsed search_code result objects (one per primary) for a run."""
    names: dict[str, str] = {}
    for line in stdout_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        d = ev.get("data", {}) or {}
        if t == "tool.execution_start":
            names[d.get("toolCallId")] = d.get("toolName") or d.get("mcpToolName") or ""
        elif t == "tool.execution_complete":
            if "search_code" not in (names.get(d.get("toolCallId")) or ""):
                continue
            res = d.get("result") or {}
            # ``contents`` is the clean per-item list (one JSON object per text
            # entry). ``content`` is the same payload concatenated into a single
            # string and is NOT valid JSON when there is >1 result -- do not use
            # it. Fall back to ``content`` only when ``contents`` is absent.
            items = res.get("contents")
            if not isinstance(items, list):
                c = res.get("content")
                items = c if isinstance(c, list) else [c]
            for it in items:
                txt = it.get("text") if isinstance(it, dict) else it
                if not txt:
                    continue
                try:
                    obj = json.loads(txt)
                except (json.JSONDecodeError, TypeError):
                    continue
                for prim in (obj if isinstance(obj, list) else [obj]):
                    if isinstance(prim, dict):
                        yield prim


def surfaced_files(stdout_path: Path) -> dict[str, dict]:
    """Return ``{file: {best_rank, via, confidence}}`` for every file the graph
    surfaced across all search_code calls in a run. ``best_rank`` is the best
    primary rank (1-based) or None if only surfaced as a related sibling."""
    out: dict[str, dict] = {}

    def note(f: str, rank: int | None, via: str, conf: str | None):
        rec = out.setdefault(f, {"best_rank": None, "via": via, "confidence": conf})
        if rank is not None and (rec["best_rank"] is None or rank < rec["best_rank"]):
            rec["best_rank"] = rank
            rec["via"] = via
            rec["confidence"] = conf
        elif rec["best_rank"] is None and via == "direct":
            rec["via"] = "direct"

    rank = 0
    for prim in _iter_search_results(stdout_path):
        f = prim.get("file")
        if f:
            if prim.get("rank_kind") == "related":
                note(f, None, f"related:{prim.get('via', '?')}", prim.get("confidence"))
            else:
                rank += 1
                note(f, rank, "direct", None)
        for rel in prim.get("likely_related_files", []) or []:
            rf = rel.get("file")
            if rf:
                note(rf, None, f"related:{rel.get('via', '?')}", rel.get("confidence"))
    return out


def classify_run(stdout_path: Path, gold_files: list[str],
                 pred_files: list[str], edit_critical: list[str] | None = None) -> dict:
    """Exposure + adoption classification for a single code_graph run.

    ``edit_critical`` optionally restricts which gold files count toward the
    candidate-level TP/FN (prereg sec7 relabel). Defaults to all gold files.
    """
    surf = surfaced_files(stdout_path)
    pred = set(pred_files or [])
    per_gold = {}
    for g in gold_files:
        rec = surf.get(g)
        if rec is None:
            exposure = "not_surfaced"
        elif rec["best_rank"] is not None:
            exposure = f"direct@{rec['best_rank']}"
        else:
            exposure = rec["via"]
        per_gold[g] = {
            "exposure": exposure,
            "surfaced": rec is not None,
            "adopted": g in pred,
        }
    n_gold = len(gold_files)
    n_surf = sum(1 for v in per_gold.values() if v["surfaced"])
    n_surf_adopted = sum(1 for v in per_gold.values() if v["surfaced"] and v["adopted"])
    n_miss_not_surf = sum(1 for v in per_gold.values() if not v["surfaced"])

    # Candidate-level confusion matrix over EVERY surfaced candidate (the agent's
    # keep/drop DECISION quality, per prereg-adoption-calibration.md). A
    # not-surfaced gold file is a RETRIEVAL miss, not a decision, so it is
    # excluded here (it is already counted in n_not_surfaced above).
    #   TP = surfaced gold kept       FN = surfaced gold dropped
    #   FP = surfaced non-gold kept   TN = surfaced non-gold dropped
    # NOTE: every gold file is treated as edit-critical until the relabel rubric
    # (prereg sec7) supplies an ``incidental`` set; see ``edit_critical`` arg.
    gold_set = set(gold_files)
    crit = set(edit_critical) if edit_critical is not None else gold_set
    tp = fp = fn = tn = 0
    cand_detail = {}
    for f, rec in surf.items():
        kept = f in pred
        is_gold = f in gold_set
        # Only edit-critical gold counts toward TP/FN; incidental gold is excluded
        # from the decision matrix (keeping or dropping it is not penalized).
        if is_gold and f not in crit:
            cand_detail[f] = "incidental_gold"
            continue
        if is_gold:
            label = "TP" if kept else "FN"
            tp += kept
            fn += not kept
        else:
            label = "FP" if kept else "TN"
            fp += kept
            tn += not kept
        cand_detail[f] = label

    return {
        "n_gold": n_gold,
        "n_surfaced": n_surf,
        "n_surfaced_adopted": n_surf_adopted,
        "n_not_surfaced": n_miss_not_surf,
        "per_gold": per_gold,
        "cand": {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "detail": cand_detail},
    }


def row_stdout_path(batch_root: Path, model: str, row: dict) -> Path | None:
    """Locate the stdout.jsonl for a results row by its FULL identity.

    Uses (mode, prompt_mode, config, task_id, run_idx) so runs from different
    prompt_modes (e.g. ``adopt-ctrl`` vs ``adopt-sem``) are never cross-wired --
    the previous glob-first-match over ``runs/<model>/*/*/code_graph`` could
    classify a SEM row against a CTRL log when both coexist in one batch.

    Supports both the legacy layout (``<task>/logs``) and the run-indexed layout
    (``<task>/run<idx>/logs``) introduced for multi-run pilots.
    """
    mode = row.get("mode", "fix")
    prompt_mode = row.get("prompt_mode", "neutral")
    track = row.get("config")
    task = row.get("task_id")
    ridx = int(row.get("run_idx", 0) or 0)
    base = batch_root / "runs" / model / mode / prompt_mode / track / task
    for cand in (
        base / f"run{ridx}" / "logs" / "stdout.jsonl",
        base / "logs" / "stdout.jsonl",
    ):
        if cand.exists():
            return cand
    # Last resort: a single stdout under this exact (mode,prompt_mode,track,task)
    # subtree. Still identity-scoped, so no cross-prompt-mode leakage.
    hits = sorted(base.glob("**/stdout.jsonl"))
    return hits[0] if hits else None


def analyze_batch(
    results_path: Path,
    *,
    prompt_mode: str | None = None,
    mode: str | None = None,
) -> dict:
    """Analyze code_graph runs referenced by a results.jsonl.

    Locates each run's log by FULL row identity (see ``row_stdout_path``) rather
    than a first-match glob, so multiple prompt-mode arms in one batch are scored
    against their OWN logs. Pass ``prompt_mode``/``mode`` to restrict to a single
    arm (e.g. ``prompt_mode="adopt-sem"``).
    """
    rows = [json.loads(ln) for ln in results_path.read_text().splitlines() if ln.strip()]
    cg = [r for r in rows if r.get("config") == "code_graph"]
    if mode is not None:
        cg = [r for r in cg if r.get("mode") == mode]
    if prompt_mode is not None:
        cg = [r for r in cg if r.get("prompt_mode") == prompt_mode]
    model = results_path.parent.name
    batch_root = results_path.parent.parent
    per_run = []
    for r in cg:
        task = r.get("task_id")
        stdout = row_stdout_path(batch_root, model, r)
        if not stdout:
            per_run.append({"task": task, "run_idx": r.get("run_idx"),
                            "prompt_mode": r.get("prompt_mode"),
                            "error": "stdout not found"})
            continue
        cls = classify_run(stdout, r.get("gold_files", []), r.get("pred_files", []))
        cls["task"] = task
        cls["run_idx"] = r.get("run_idx")
        cls["prompt_mode"] = r.get("prompt_mode")
        cls["file_recall"] = r.get("file_recall")
        per_run.append(cls)
    return {"per_run": per_run}


def _prf(tp: int, fp: int, fn: int) -> tuple[float | None, float | None, float | None]:
    """Precision, recall, F1 from counts; None when the denominator is 0."""
    prec = tp / (tp + fp) if (tp + fp) else None
    rec = tp / (tp + fn) if (tp + fn) else None
    if prec is None or rec is None or (prec + rec) == 0:
        f1 = None
    else:
        f1 = 2 * prec * rec / (prec + rec)
    return prec, rec, f1


def candidate_calibration(runs: list[dict]) -> dict:
    """Macro (by task) + micro candidate-level precision/recall/F1.

    The unit of analysis is the TASK (files within a task are correlated). We sum
    a task's candidate counts across its runs, compute per-task P/R/F1, then macro
    average. Micro pools all candidates. Macro-F1 by task is the prereg PRIMARY.
    """
    by_task: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
    for r in runs:
        c = r.get("cand")
        if not c:
            continue
        t = by_task[r["task"]]
        for k in ("tp", "fp", "fn", "tn"):
            t[k] += c[k]

    per_task = {}
    precs, recs, f1s = [], [], []
    # macro_strict: a task where gold was SURFACED but ALL of it was dropped
    # (tp=0, fn>0) is a real adoption FAILURE, not a degenerate task -- score it
    # F1=0 instead of dropping it, so a conservative lever cannot inflate macro-F1
    # by silently removing the tasks it broke. Tasks with no surfaced gold at all
    # (fn=0 and tp=0) remain genuinely undefined and stay dropped.
    f1s_strict: list[float] = []
    n_dropped_undefined = 0
    n_dropped_gold_failures = 0
    for task, c in by_task.items():
        p, rc, f1 = _prf(c["tp"], c["fp"], c["fn"])
        per_task[task] = {**c, "precision": p, "recall": rc, "f1": f1}
        if p is not None:
            precs.append(p)
        if rc is not None:
            recs.append(rc)
        if f1 is not None:
            f1s.append(f1)
            f1s_strict.append(f1)
        elif c["tp"] == 0 and c["fn"] > 0:
            # surfaced gold, none kept -> adoption failure -> strict F1 = 0
            f1s_strict.append(0.0)
            n_dropped_gold_failures += 1
        else:
            n_dropped_undefined += 1

    tp = sum(c["tp"] for c in by_task.values())
    fp = sum(c["fp"] for c in by_task.values())
    fn = sum(c["fn"] for c in by_task.values())
    tn = sum(c["tn"] for c in by_task.values())
    mp, mr, mf1 = _prf(tp, fp, fn)

    def _avg(xs):
        return sum(xs) / len(xs) if xs else None

    return {
        "n_tasks": len(by_task),
        "n_tasks_scored_f1": len(f1s),
        "n_tasks_dropped_undefined": n_dropped_undefined,
        "n_tasks_gold_dropped_failures": n_dropped_gold_failures,
        "macro": {"precision": _avg(precs), "recall": _avg(recs), "f1": _avg(f1s)},
        "macro_strict": {"f1": _avg(f1s_strict), "n": len(f1s_strict)},
        "micro": {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                  "precision": mp, "recall": mr, "f1": mf1},
        "per_task": per_task,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results", type=Path)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    out = analyze_batch(args.results)
    runs = [r for r in out["per_run"] if "error" not in r]

    tot_gold = sum(r["n_gold"] for r in runs)
    tot_surf = sum(r["n_surfaced"] for r in runs)
    tot_surf_adopt = sum(r["n_surfaced_adopted"] for r in runs)
    tot_not_surf = sum(r["n_not_surfaced"] for r in runs)

    print(f"code_graph runs analyzed: {len(runs)}")
    print(f"\n{'task':34s} {'idx':3s} {'recall':6s}  exposure -> adoption (per gold)")
    for r in sorted(runs, key=lambda x: (x["task"], x["run_idx"] or 0)):
        bits = []
        for g, v in r["per_gold"].items():
            tag = v["exposure"]
            mark = "OK" if v["adopted"] else ("DROP" if v["surfaced"] else "MISS")
            bits.append(f"{Path(g).name}:{tag}/{mark}")
        print(f"{r['task']:34s} {str(r['run_idx']):3s} {r['file_recall']!s:6s}  " + "  ".join(bits))

    print("\n==== AGGREGATE (gold-file level, over code_graph runs) ====")
    print(f"total gold files (run x gold)      : {tot_gold}")
    print(f"surfaced by graph                  : {tot_surf}  "
          f"(exposure_recall = {tot_surf/tot_gold:.3f})")
    print(f"  of which adopted in final answer : {tot_surf_adopt}  "
          f"(adoption_rate = {tot_surf_adopt/tot_surf:.3f})" if tot_surf else "")
    print(f"  surfaced-but-DROPPED (adoption gap): {tot_surf - tot_surf_adopt}")
    print(f"never surfaced (true retrieval miss): {tot_not_surf}  "
          f"({tot_not_surf/tot_gold:.3f})")

    cal = candidate_calibration(runs)
    out["candidate_calibration"] = cal
    mac, mic = cal["macro"], cal["micro"]

    def _f(x):
        return f"{x:.3f}" if x is not None else "  n/a"

    print("\n==== CANDIDATE-LEVEL CALIBRATION (keep/drop over surfaced candidates) ====")
    print("  (TP surfaced-gold kept | FP non-gold kept | FN surfaced-gold dropped | TN non-gold dropped)")
    print(f"  micro: TP={mic['tp']} FP={mic['fp']} FN={mic['fn']} TN={mic['tn']}  "
          f"P={_f(mic['precision'])} R={_f(mic['recall'])} F1={_f(mic['f1'])}")
    print(f"  MACRO by task (PRIMARY, n_tasks={cal['n_tasks']}): "
          f"P={_f(mac['precision'])} R={_f(mac['recall'])} F1={_f(mac['f1'])}")

    if args.json:
        args.json.write_text(json.dumps(out, indent=2))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
