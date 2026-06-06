"""Unit tests for the deterministic structural-query compression benchmark.

Only the pure (FalkorDB-free) helpers are covered here; the graph/grep paths
are integration-tested by running the module against a live indexed repo.
"""

from __future__ import annotations

import pytest

from bench.runners import struct_query_bench as sqb


def test_relpath_strips_worktree():
    assert sqb._relpath("/wt/pkg/mod.py", "/wt") == "pkg/mod.py"


def test_relpath_falls_back_to_basename_outside_worktree():
    assert sqb._relpath("/other/pkg/mod.py", "/wt") == "mod.py"


def test_tok_counts_tokens():
    pytest.importorskip("tiktoken")
    assert sqb._tok("hello world") > 0
    # longer text => more tokens
    assert sqb._tok("a b c d e f g h") > sqb._tok("a b")


def test_summarize_paired_ratio_stats():
    rows = [
        {"ratio": 4.0, "graph_tokens": 100, "raw_tokens": 400},
        {"ratio": 2.0, "graph_tokens": 50, "raw_tokens": 100},
        {"ratio": 0.5, "graph_tokens": 200, "raw_tokens": 100},
        {"ratio": 1.0, "graph_tokens": 80, "raw_tokens": 80},
    ]
    s = sqb.summarize(rows)
    assert s["n"] == 4
    # median of [0.5, 1.0, 2.0, 4.0] = 1.5
    assert s["median_ratio"] == 1.5
    # 2 of 4 strictly above 1.0
    assert s["win_rate"] == "2/4"
    assert s["geomean_ratio"] is not None


def test_summarize_handles_empty():
    s = sqb.summarize([])
    assert s["n"] == 0
    assert s["median_ratio"] is None
    assert s["win_rate"] == "0/0"


def test_generic_names_excluded_constant():
    # sanity: the common-name filter contains the obvious megahub offenders
    for n in ("run", "get", "__init__", "update"):
        assert n in sqb._GENERIC
