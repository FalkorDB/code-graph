"""Iter2 regression tests: cg-mcp CLI must compact list outputs.

Two failure modes from iter1 that this exists to catch:

1. ``impact_analysis`` returns 500+ entries on large graphs (sympy: 142k
   edges). The CLI must apply a default ``--limit 50``.
2. Every returned node carries an absolute worktree path
   (``/Users/.../worktrees/<project>/sympy/printing/latex.py``). The
   100+-char prefix is identical across entries and contributes nothing
   actionable. The CLI must strip everything up to and including
   ``/<project>/`` so ``file`` is repo-relative.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from unittest.mock import patch

from bench.cli import cg_mcp


# ---- helpers --------------------------------------------------------------


def _entry(idx: int) -> dict:
    return {
        "id": idx,
        "name": f"sym_{idx}",
        "label": "Function",
        "file": (
            "/Users/x/Code/code-graph/.worktrees/bench-combined/"
            "bench/cache/worktrees/sympy__sympy-12481__code_graph_mcp/"
            f"sympy/printing/latex_{idx}.py"
        ),
        "line": 100 + idx,
        "direction": "IN",
    }


# ---- unit tests for helpers ----------------------------------------------


def test_strip_worktree_prefix_makes_path_repo_relative():
    p = (
        "/Users/x/Code/code-graph/.worktrees/bench-combined/"
        "bench/cache/worktrees/sympy__sympy-12481__code_graph_mcp/"
        "sympy/printing/latex.py"
    )
    out = cg_mcp._strip_worktree_prefix(p, "sympy__sympy-12481__code_graph_mcp")
    assert out == "sympy/printing/latex.py"


def test_strip_worktree_prefix_no_op_when_project_missing_from_path():
    p = "/tmp/somewhere/else.py"
    out = cg_mcp._strip_worktree_prefix(p, "sympy__sympy-12481__code_graph_mcp")
    # No matching project segment, leave untouched.
    assert out == p


def test_strip_worktree_prefix_handles_none_project():
    p = "/abs/path.py"
    assert cg_mcp._strip_worktree_prefix(p, None) == p


def test_compact_entry_drops_empty_fields_and_strips_path():
    e = _entry(7)
    e["empty_list"] = []
    e["empty_str"] = ""
    e["none_field"] = None
    out = cg_mcp._compact_entry(e, "sympy__sympy-12481__code_graph_mcp")
    assert out["file"] == "sympy/printing/latex_7.py"
    # empties dropped
    assert "empty_list" not in out
    assert "empty_str" not in out
    assert "none_field" not in out
    # kept fields intact
    assert out["id"] == 7
    assert out["name"] == "sym_7"


def test_compact_list_caps_at_limit_and_strips_paths():
    items = [_entry(i) for i in range(200)]
    out = cg_mcp._compact_list(items, "sympy__sympy-12481__code_graph_mcp", 50)
    assert len(out) == 50
    assert out[0]["file"] == "sympy/printing/latex_0.py"
    assert out[49]["file"] == "sympy/printing/latex_49.py"


def test_compact_list_no_limit_keeps_all_but_still_strips():
    items = [_entry(i) for i in range(3)]
    out = cg_mcp._compact_list(items, "sympy__sympy-12481__code_graph_mcp", None)
    assert len(out) == 3
    for o in out:
        assert "worktrees" not in o["file"]


# ---- CLI integration ------------------------------------------------------


def _run_cli(argv: list[str]) -> dict | list:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cg_mcp.main(argv)
    assert rc == 0, f"CLI returned {rc}; stdout={buf.getvalue()!r}"
    return json.loads(buf.getvalue())


def test_cli_impact_analysis_applies_default_limit_50():
    # Adapter returns the raw list (already chunk-fix-corrected); CLI must cap.
    fake_response = [_entry(i) for i in range(120)]
    with patch.object(cg_mcp.cgm, "impact_analysis", return_value=fake_response):
        out = _run_cli([
            "impact_analysis",
            "--project", "sympy__sympy-12481__code_graph_mcp",
            "--symbol-id", "7417",
        ])
    assert isinstance(out, list)
    assert len(out) == 50, f"expected default limit 50, got {len(out)}"
    # Path stripped
    assert out[0]["file"] == "sympy/printing/latex_0.py"


def test_cli_impact_analysis_respects_explicit_limit():
    fake_response = [_entry(i) for i in range(120)]
    with patch.object(cg_mcp.cgm, "impact_analysis", return_value=fake_response):
        out = _run_cli([
            "impact_analysis",
            "--project", "sympy__sympy-12481__code_graph_mcp",
            "--symbol-id", "7417",
            "--limit", "10",
        ])
    assert len(out) == 10


def test_cli_get_callers_strips_paths():
    fake_response = [_entry(i) for i in range(5)]
    with patch.object(cg_mcp.cgm, "get_callers", return_value=fake_response):
        out = _run_cli([
            "get_callers",
            "--project", "sympy__sympy-12481__code_graph_mcp",
            "--symbol-id", "42",
        ])
    assert all("worktrees" not in e["file"] for e in out)


def test_cli_payload_size_shrinks_substantially():
    """End-to-end smoke: 200 entries through impact_analysis should be
    much smaller than the raw chunk-fix output (80KB+ on real sympy data)."""
    fake_response = [_entry(i) for i in range(200)]
    raw = json.dumps(fake_response, separators=(",", ":"))
    raw_size = len(raw)

    buf = io.StringIO()
    with redirect_stdout(buf), patch.object(cg_mcp.cgm, "impact_analysis", return_value=fake_response):
        cg_mcp.main([
            "impact_analysis",
            "--project", "sympy__sympy-12481__code_graph_mcp",
            "--symbol-id", "7417",
        ])
    capped_size = len(buf.getvalue())

    # Default cap (50) + path strip should cut output to a small fraction.
    assert capped_size < raw_size * 0.30, (
        f"compaction insufficient: raw={raw_size}B capped={capped_size}B"
    )
