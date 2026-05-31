"""Unit tests for the Copilot benchmark runner parsers + TCO accounting.

These run unconditionally (no FalkorDB / Copilot needed): they exercise the
log/JSONL parsing and cost math against synthetic inputs plus the captured
spike fixtures when present.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.runners import copilot_runner as cr
from bench.runners import copilot_tco as tco


# ---------------------------------------------------------------------------
# Token-block parsing
# ---------------------------------------------------------------------------


def _write_log(tmp_path: Path, name: str, text: str) -> Path:
    d = tmp_path / "logs"
    d.mkdir(exist_ok=True)
    (d / name).write_text(text)
    return d


_USAGE_BLOCK = """\
some preamble line
  "usage": {
    "prompt_tokens": 1000,
    "completion_tokens": 50,
    "total_tokens": 1050,
    "prompt_tokens_details": {
      "cached_tokens": 200,
      "cache_creation_tokens": 800
    },
    "completion_tokens_details": { "reasoning_tokens": 0 }
  }
trailing
"""


def test_parse_tokens_sums_multiple_blocks(tmp_path):
    text = _USAGE_BLOCK + "\n" + _USAGE_BLOCK
    d = _write_log(tmp_path, "process-1.log", text)
    out = cr.parse_tokens_from_logs(d)
    assert out["input_tokens"] == 2000
    assert out["output_tokens"] == 100
    assert out["total_tokens"] == 2100
    assert out["cached_input_tokens"] == 400
    assert out["cache_creation_tokens"] == 1600
    assert out["usage_blocks"] == 2


def test_parse_tokens_ignores_non_model_usage(tmp_path):
    # An MCP tool result or stray JSON with a "usage" key but missing the
    # required model-response fields must NOT be counted.
    stray = '{ "usage": { "premiumRequests": 15, "totalApiDurationMs": 100 } }'
    text = _USAGE_BLOCK + "\n" + stray
    d = _write_log(tmp_path, "process-1.log", text)
    out = cr.parse_tokens_from_logs(d)
    assert out["usage_blocks"] == 1
    assert out["input_tokens"] == 1000


def test_parse_tokens_multiple_log_files(tmp_path):
    d = _write_log(tmp_path, "process-1.log", _USAGE_BLOCK)
    (d / "process-2.log").write_text(_USAGE_BLOCK)
    out = cr.parse_tokens_from_logs(d)
    assert out["usage_blocks"] == 2
    assert out["input_tokens"] == 2000


# ---------------------------------------------------------------------------
# Result-event + tool-call parsing
# ---------------------------------------------------------------------------


def test_parse_result_event():
    stdout = "\n".join([
        json.dumps({"type": "assistant", "data": {}}),
        json.dumps({
            "type": "result",
            "data": {
                "usage": {
                    "premiumRequests": 12,
                    "codeChanges": {"filesModified": ["a.py", "b.py"]},
                },
                "isError": False,
                "numTurns": 7,
            },
        }),
    ])
    out = cr.parse_result_event(stdout)
    assert out["premium_requests"] == 12
    assert out["files_modified"] == ["a.py", "b.py"]
    assert out["is_error"] is False
    assert out["num_turns"] == 7


def test_parse_tool_calls_counts_mcp_and_shell():
    stdout = "\n".join([
        json.dumps({"type": "tool.execution_start", "data": {"name": "bash"}}),
        json.dumps({"type": "tool.execution_start", "data": {"name": "bash"}}),
        json.dumps({"type": "tool.execution_start", "data": {"name": "code-graph-search_code"}}),
        json.dumps({"type": "tool.execution_complete", "data": {}}),
    ])
    total, by_name = cr.parse_tool_calls(stdout)
    assert total == 3
    assert by_name == {"bash": 2, "code-graph-search_code": 1}


def test_parsers_tolerate_garbage_lines():
    stdout = "not json\n\n" + json.dumps({"type": "result", "data": {"usage": {"premiumRequests": 1}}})
    assert cr.parse_result_event(stdout)["premium_requests"] == 1
    assert cr.parse_tool_calls("garbage\n{bad") == (0, {})


# ---------------------------------------------------------------------------
# Patch helpers
# ---------------------------------------------------------------------------


def test_patched_files_extraction():
    patch = (
        "diff --git a/x/y.py b/x/y.py\n"
        "--- a/x/y.py\n"
        "+++ b/x/y.py\n"
        "@@ -1 +1 @@\n-a\n+b\n"
        "diff --git a/tests/test_z.py b/tests/test_z.py\n"
        "--- a/tests/test_z.py\n"
        "+++ b/tests/test_z.py\n"
        "@@ -1 +1 @@\n-c\n+d\n"
    )
    assert cr._patched_files(patch) == ["x/y.py", "tests/test_z.py"]


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


def test_prompt_excludes_ask_for_code_graph(tmp_path):
    p = cr.build_prompt(cr.CODE_GRAPH, tmp_path, "Fix the bug.", "django__django-10973")
    assert "django__django-10973" in p
    assert "Do not use the `ask` tool" in p
    assert "search_code" in p


def test_prompt_no_mcp_has_no_tool_sales():
    p = cr.build_prompt(cr.NO_MCP, Path("/tmp/x"), "Fix it.", "proj")
    assert "MCP" in p  # capability note present
    assert "search_code" not in p


# ---------------------------------------------------------------------------
# TCO accounting
# ---------------------------------------------------------------------------


def test_tco_no_ask_is_agent_only():
    row = {
        "task_id": "t1", "config": "code_graph", "model": "claude-opus-4.8",
        "input_tokens": 1_000_000, "output_tokens": 100_000,
        "premium_requests": 20, "index_sec": 60.0, "completed": True,
    }
    out = tco.row_tco(row)
    # opus: 1M in * $15 + 0.1M out * $75 = 15 + 7.5 = 22.5
    assert out["agent_usd"] == pytest.approx(22.5, abs=0.01)
    assert out["graphrag_usd"] == 0.0
    assert out["per_task_tco_usd"] == pytest.approx(22.5, abs=0.01)
    assert out["index_usd_amortized_once"] > 0


def test_tco_meters_ask_when_present():
    row = {
        "task_id": "t1", "config": "code_graph_ask", "model": "claude-sonnet-4.6",
        "input_tokens": 0, "output_tokens": 0,
        "graphrag_ask_calls": 3, "graphrag_input_tokens": 1_000_000,
        "graphrag_output_tokens": 100_000, "completed": True,
    }
    out = tco.row_tco(row)
    # gemini-flash-lite: 1M * 0.075 + 0.1M * 0.30 = 0.075 + 0.03 = 0.105
    assert out["graphrag_usd"] == pytest.approx(0.105, abs=1e-4)
    assert out["graphrag_ask_calls"] == 3


def test_tco_aggregate_groups_by_config():
    rows = [
        {"config": "copilot_no_mcp", "model": "claude-opus-4.8", "input_tokens": 100, "output_tokens": 10, "outcome": "resolved", "completed": True},
        {"config": "code_graph", "model": "claude-opus-4.8", "input_tokens": 100, "output_tokens": 10, "outcome": "failed", "completed": True},
        {"config": "code_graph", "model": "claude-opus-4.8", "input_tokens": 0, "output_tokens": 0, "outcome": "x", "completed": False},  # skipped
    ]
    agg = tco.aggregate(rows)
    assert agg["copilot_no_mcp"]["n"] == 1
    assert agg["copilot_no_mcp"]["resolved"] == 1
    assert agg["code_graph"]["n"] == 1  # incomplete row excluded


def test_agent_key_mapping():
    assert tco.agent_key("claude-opus-4.8") == "opus"
    assert tco.agent_key("claude-sonnet-4.6") == "sonnet"
    assert tco.agent_key("claude-haiku-4.5") == "haiku"


# ---------------------------------------------------------------------------
# Real captured fixture (when present)
# ---------------------------------------------------------------------------

_FIXTURE = Path(__file__).resolve().parents[1].parent / "bench" / "cache" / "copilot-spike" / "logs" / "mcp-probe3"


@pytest.mark.skipif(not (_FIXTURE / "..").exists() or not _FIXTURE.exists(), reason="spike fixture absent")
def test_real_fixture_tokens_parse():
    out = cr.parse_tokens_from_logs(_FIXTURE)
    assert out["usage_blocks"] >= 1
    assert out["input_tokens"] > 0
