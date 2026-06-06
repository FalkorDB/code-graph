"""Unit tests for the Lane 1 per-arm diagnostics (``adopt_diag``).

Covers the FREE/offline pieces (no API, no live graph):
  * RAT keep/drop parsing + consistency audit (compliant, consistent,
    dropped-but-kept conflict, kept-then-omitted erosion);
  * end-to-end ``diagnose`` over a tiny CTRL/RAT batch: arm detection, exposure
    recall, GRAPH-WRONG subset freezing, and token summary.
"""

from __future__ import annotations

import json
from pathlib import Path

from bench.analysis import adopt_diag as ad


def test_parse_rat_decisions_keep_drop_and_backticks():
    text = (
        "Here are my decisions:\n"
        "KEEP pkg/a.py — directly implements the save path\n"
        "- `DROP` `pkg/b.py` — only a caller, not the edit site\n"
        "DROP pkg/c.py: unrelated sibling\n"
        "I also note keep is a verb used in prose but not line-initial here.\n"
    )
    d = ad.parse_rat_decisions(text)
    assert d == {"pkg/a.py": "keep", "pkg/b.py": "drop", "pkg/c.py": "drop"}


def test_rat_audit_consistent_when_no_dropped_file_kept():
    text = "KEEP pkg/a.py — yes\nDROP pkg/b.py — no\n"
    a = ad.rat_audit(text, pred_files=["pkg/a.py"])
    assert a["compliant"] and a["consistent"]
    assert a["n_keep"] == 1 and a["n_drop"] == 1
    assert a["dropped_but_kept"] == []
    assert a["kept_omitted"] == []


def test_rat_audit_flags_dropped_but_kept_conflict():
    text = "KEEP pkg/a.py — yes\nDROP pkg/b.py — no\n"
    a = ad.rat_audit(text, pred_files=["pkg/a.py", "pkg/b.py"])
    assert not a["consistent"]
    assert a["dropped_but_kept"] == ["pkg/b.py"]


def test_rat_audit_flags_kept_then_omitted():
    text = "KEEP pkg/a.py — yes\nKEEP pkg/b.py — yes\n"
    a = ad.rat_audit(text, pred_files=["pkg/a.py"])
    assert a["consistent"]  # nothing dropped-then-kept
    assert a["kept_omitted"] == ["pkg/b.py"]


def test_rat_audit_non_compliant_when_no_decisions():
    a = ad.rat_audit("I think the answer is pkg/a.py.", pred_files=["pkg/a.py"])
    assert not a["compliant"]
    assert a["n_keep"] == 0 and a["n_drop"] == 0


# ---------------------------------------------------------------------------
# End-to-end batch fixture
# ---------------------------------------------------------------------------

MODEL = "test-model"


def _write_run(batch_root: Path, arm: str, task: str, primaries: list[str],
               agent_text: str) -> None:
    run_dir = batch_root / "runs" / MODEL / "localize" / arm / "code_graph" / task
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    contents = [{"type": "text", "text": json.dumps({"file": f})} for f in primaries]
    events = [
        {"type": "tool.execution_start",
         "data": {"toolCallId": "c1", "mcpToolName": "search_code"}},
        {"type": "tool.execution_complete",
         "data": {"toolCallId": "c1", "result": {"contents": contents}}},
    ]
    (run_dir / "logs" / "stdout.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events)
    )
    (run_dir / "agent_text.txt").write_text(agent_text)


def _row(arm: str, task: str, gold: list[str], pred: list[str], **extra) -> dict:
    base = {
        "benchmark": "swe_bench_verified",
        "task_id": task,
        "config": "code_graph",
        "model": MODEL,
        "mode": "localize",
        "prompt_mode": arm,
        "run_idx": 0,
        "runner": "copilot-runner/2",
        "completed": True,
        "gold_files": gold,
        "pred_files": pred,
        "total_tokens": 1000,
        "output_tokens": 400,
        "reasoning_tokens": 150,
        "input_tokens": 600,
        "premium_requests": 1,
        "num_turns": 5,
    }
    base.update(extra)
    return base


def _build_batch(tmp_path: Path) -> Path:
    batch_root = tmp_path / "cache"
    results_path = batch_root / MODEL / "results.jsonl"
    results_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    # task t1: graph surfaces gold at rank-1 (CLEAN, not graph-wrong).
    # CTRL drops the gold (adoption failure); RAT keeps it.
    _write_run(batch_root, "adopt-ctrl", "t1", ["pkg/gold.py"], "")
    _write_run(batch_root, "adopt-rat", "t1", ["pkg/gold.py"],
               "KEEP pkg/gold.py — implements it\n")
    rows.append(_row("adopt-ctrl", "t1", ["pkg/gold.py"], []))            # FN
    rows.append(_row("adopt-rat", "t1", ["pkg/gold.py"], ["pkg/gold.py"]))  # TP

    # task t2: rank-1 hit is non-gold (GRAPH-WRONG). CTRL keeps the wrong rank-1
    # (FP); RAT drops it and keeps the real gold surfaced at rank-2.
    _write_run(batch_root, "adopt-ctrl", "t2", ["pkg/wrong.py", "pkg/real.py"], "")
    _write_run(batch_root, "adopt-rat", "t2", ["pkg/wrong.py", "pkg/real.py"],
               "DROP pkg/wrong.py — only related\nKEEP pkg/real.py — the edit site\n")
    rows.append(_row("adopt-ctrl", "t2", ["pkg/real.py"], ["pkg/wrong.py"]))
    rows.append(_row("adopt-rat", "t2", ["pkg/real.py"], ["pkg/real.py"]))

    results_path.write_text("\n".join(json.dumps(r) for r in rows))
    return results_path


def test_diagnose_detects_arms_and_exposure(tmp_path):
    results_path = _build_batch(tmp_path)
    rep = ad.diagnose(results_path, ref_arm="adopt-ctrl")
    assert rep["arms_present"] == ["adopt-ctrl", "adopt-rat"]
    # Every gold file was surfaced in both arms -> exposure_recall == 1.0.
    assert rep["arms"]["adopt-ctrl"]["exposure"]["exposure_recall"] == 1.0
    assert rep["arms"]["adopt-rat"]["exposure"]["exposure_recall"] == 1.0
    # CTRL dropped both surfaced golds; RAT kept both.
    assert rep["arms"]["adopt-ctrl"]["exposure"]["adoption_rate"] == 0.0
    assert rep["arms"]["adopt-rat"]["exposure"]["adoption_rate"] == 1.0


def test_diagnose_graph_wrong_subset_frozen_from_ref(tmp_path):
    results_path = _build_batch(tmp_path)
    rep = ad.diagnose(results_path, ref_arm="adopt-ctrl")
    # t2's rank-1 (pkg/wrong.py) is non-gold -> GRAPH-WRONG; t1 is not.
    assert rep["graph_wrong"]["tasks"] == ["t2"]
    assert rep["graph_wrong"]["ref_arm"] == "adopt-ctrl"


def test_diagnose_rat_audit_and_consistency(tmp_path):
    results_path = _build_batch(tmp_path)
    rep = ad.diagnose(results_path, ref_arm="adopt-ctrl")
    ra = rep["arms"]["adopt-rat"]["rat_audit"]
    assert ra["n"] == 2
    assert ra["compliance_rate"] == 1.0   # both RAT runs emitted decisions
    assert ra["consistency_rate"] == 1.0  # no dropped file was kept
    assert ra["n_dropped_but_kept"] == 0


def test_diagnose_rat_calibration_beats_ctrl(tmp_path):
    results_path = _build_batch(tmp_path)
    rep = ad.diagnose(results_path, ref_arm="adopt-ctrl")
    ctrl_f1 = rep["arms"]["adopt-ctrl"]["calibration_clean"]["macro_strict"]["f1"]
    rat_f1 = rep["arms"]["adopt-rat"]["calibration_clean"]["macro_strict"]["f1"]
    assert rat_f1 > ctrl_f1


def test_token_summary_visible_output_excludes_reasoning(tmp_path):
    rows = [_row("adopt-rat", "t1", ["g.py"], ["g.py"])]
    ts = ad.token_summary(rows)
    # output 400 - reasoning 150 = 250 visible
    assert ts["median_visible_output_tokens"] == 250
    assert ts["median_total_tokens"] == 1000
