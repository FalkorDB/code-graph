"""Unit tests for the adoption-calibration controls + candidate metric.

Covers the FREE/offline pieces (no API, no live graph):
  * candidate-level confusion matrix scores an injected NOISY distractor as FP
    when the agent keeps it and TN when it drops it (the run-time NOISY arm's
    correctness hinge);
  * edit-critical relabel heuristic + manual override precedence;
  * the degenerate-task convention for macro precision/recall (undefined tasks
    are dropped from the macro average, not imputed).
"""

from __future__ import annotations

import json

from bench.analysis import adopt_controls as ac
from bench.analysis.exposure_adoption import candidate_calibration, classify_run


def _write_stdout(path, primaries):
    """Write a minimal Copilot-CLI stdout.jsonl with one search_code call that
    surfaces ``primaries`` (list of file paths) as ranked primary hits."""
    contents = [{"type": "text", "text": json.dumps({"file": f})} for f in primaries]
    events = [
        {"type": "tool.execution_start",
         "data": {"toolCallId": "c1", "mcpToolName": "search_code"}},
        {"type": "tool.execution_complete",
         "data": {"toolCallId": "c1", "result": {"contents": contents}}},
    ]
    path.write_text("\n".join(json.dumps(e) for e in events))
    return path


def test_kept_distractor_scores_fp(tmp_path):
    sp = _write_stdout(tmp_path / "s.jsonl", ["pkg/gold.py", "pkg/distractor.py"])
    cls = classify_run(sp, gold_files=["pkg/gold.py"],
                       pred_files=["pkg/gold.py", "pkg/distractor.py"])
    c = cls["cand"]
    assert c["tp"] == 1  # surfaced gold kept
    assert c["fp"] == 1  # surfaced non-gold (distractor) kept
    assert c["fn"] == 0 and c["tn"] == 0


def test_dropped_distractor_scores_tn(tmp_path):
    sp = _write_stdout(tmp_path / "s.jsonl", ["pkg/gold.py", "pkg/distractor.py"])
    cls = classify_run(sp, gold_files=["pkg/gold.py"], pred_files=["pkg/gold.py"])
    c = cls["cand"]
    assert c["tp"] == 1 and c["tn"] == 1  # gold kept, distractor correctly dropped
    assert c["fp"] == 0 and c["fn"] == 0


def test_dropped_gold_scores_fn(tmp_path):
    sp = _write_stdout(tmp_path / "s.jsonl", ["pkg/gold.py"])
    cls = classify_run(sp, gold_files=["pkg/gold.py"], pred_files=[])
    assert cls["cand"]["fn"] == 1 and cls["cand"]["tp"] == 0


def test_incidental_gold_excluded_from_matrix(tmp_path):
    # gold surfaced but marked NOT edit-critical -> neither TP nor FN when dropped
    sp = _write_stdout(tmp_path / "s.jsonl", ["pkg/gold.py"])
    cls = classify_run(sp, gold_files=["pkg/gold.py"], pred_files=[],
                       edit_critical=[])
    c = cls["cand"]
    assert c["tp"] == 0 and c["fn"] == 0
    assert cls["cand"]["detail"]["pkg/gold.py"] == "incidental_gold"


def test_edit_critical_heuristic_and_override():
    gold = ["pkg/core.py", "tests/test_core.py", "pkg/migrations/0001_init.py"]
    crit, inc = ac.edit_critical_split(gold)
    assert crit == ["pkg/core.py"]
    assert set(inc) == {"tests/test_core.py", "pkg/migrations/0001_init.py"}

    # override flips core.py to incidental and the test file to critical
    ov = {"t1": {"pkg/core.py": "incidental", "tests/test_core.py": "critical"}}
    crit2, inc2 = ac.edit_critical_split(gold, task="t1", overrides=ov)
    assert "pkg/core.py" in inc2
    assert "tests/test_core.py" in crit2


def test_macro_drops_undefined_tasks():
    # task A: one TP, one TN -> P=1.0 R=1.0; task B: all TN (no kept, no surfaced
    # gold) -> precision & recall undefined -> must be DROPPED from macro, not 0.
    runs = [
        {"task": "A", "cand": {"tp": 1, "fp": 0, "fn": 0, "tn": 1}},
        {"task": "B", "cand": {"tp": 0, "fp": 0, "fn": 0, "tn": 3}},
    ]
    cal = candidate_calibration(runs)
    # only task A contributes to the macro average (B is undefined on both axes)
    assert cal["macro"]["precision"] == 1.0
    assert cal["macro"]["recall"] == 1.0


def test_gold_symbols_skip_dunders(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("class C:\n    def __init__(self): pass\n    def real_method(self): pass\n"
                 "def top_fn(): pass\n")
    syms = ac.gold_symbols_offline(tmp_path, "m.py")
    assert "__init__" not in syms
    assert {"C", "real_method", "top_fn"} <= set(syms)


# --- identity-aware log lookup (no cross-wiring across prompt_modes) ----------
def _write_batch_run(batch_root, model, mode, prompt_mode, task, primaries,
                     run_idx=0):
    """Materialize a runs/<model>/<mode>/<prompt_mode>/code_graph/<task>[/run<idx>]
    /logs/stdout.jsonl with the given surfaced primaries."""
    base = batch_root / "runs" / model / mode / prompt_mode / "code_graph" / task
    if run_idx:
        base = base / f"run{run_idx}"
    logs = base / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    _write_stdout(logs / "stdout.jsonl", primaries)


def test_row_stdout_path_does_not_cross_wire_prompt_modes(tmp_path):
    from bench.analysis.exposure_adoption import row_stdout_path
    model = "m"
    batch = tmp_path / "batch"
    # Same task under two arms, each surfacing a DISTINCT file.
    _write_batch_run(batch, model, "localize", "adopt-ctrl", "task-1", ["pkg/ctrl.py"])
    _write_batch_run(batch, model, "localize", "adopt-sem", "task-1", ["pkg/sem.py"])
    ctrl_row = {"config": "code_graph", "mode": "localize",
                "prompt_mode": "adopt-ctrl", "task_id": "task-1", "run_idx": 0}
    sem_row = {**ctrl_row, "prompt_mode": "adopt-sem"}
    ctrl_log = row_stdout_path(batch, model, ctrl_row).read_text()
    sem_log = row_stdout_path(batch, model, sem_row).read_text()
    assert "pkg/ctrl.py" in ctrl_log and "pkg/sem.py" not in ctrl_log
    assert "pkg/sem.py" in sem_log and "pkg/ctrl.py" not in sem_log


def test_row_stdout_path_separates_run_idx(tmp_path):
    from bench.analysis.exposure_adoption import row_stdout_path
    model = "m"
    batch = tmp_path / "batch"
    _write_batch_run(batch, model, "localize", "adopt-ctrl", "task-1", ["pkg/r0.py"], run_idx=0)
    _write_batch_run(batch, model, "localize", "adopt-ctrl", "task-1", ["pkg/r1.py"], run_idx=1)
    r0 = {"config": "code_graph", "mode": "localize", "prompt_mode": "adopt-ctrl",
          "task_id": "task-1", "run_idx": 0}
    r1 = {**r0, "run_idx": 1}
    assert "pkg/r0.py" in row_stdout_path(batch, model, r0).read_text()
    assert "pkg/r1.py" in row_stdout_path(batch, model, r1).read_text()


def test_macro_strict_scores_drop_everything_as_zero():
    # task A: clean keep -> F1=1. task B: gold SURFACED but ALL dropped
    # (tp=0, fn>0) -> a real adoption failure -> macro_strict must include it as
    # F1=0 (not silently drop it), while the lenient macro drops it.
    runs = [
        {"task": "A", "cand": {"tp": 1, "fp": 0, "fn": 0, "tn": 1}},
        {"task": "B", "cand": {"tp": 0, "fp": 0, "fn": 2, "tn": 0}},
    ]
    cal = candidate_calibration(runs)
    assert cal["macro"]["f1"] == 1.0           # B dropped from lenient macro
    assert cal["macro_strict"]["f1"] == 0.5    # B counted as F1=0 -> (1+0)/2
    assert cal["n_tasks_gold_dropped_failures"] == 1


def test_macro_strict_keeps_dropping_no_surfaced_gold_tasks():
    # task with no surfaced gold (tp=0, fn=0) is genuinely undefined and stays
    # dropped from BOTH macros.
    runs = [
        {"task": "A", "cand": {"tp": 1, "fp": 0, "fn": 0, "tn": 1}},
        {"task": "B", "cand": {"tp": 0, "fp": 0, "fn": 0, "tn": 3}},
    ]
    cal = candidate_calibration(runs)
    assert cal["macro_strict"]["f1"] == 1.0
    assert cal["macro_strict"]["n"] == 1
    assert cal["n_tasks_dropped_undefined"] == 1
