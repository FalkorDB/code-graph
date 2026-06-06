"""Unit tests for the trace extractor's before-call thoughts + final blocks.

These cover the post-benchmark behaviour-analysis requirements: surface the
agent's thinking/narration BEFORE each tool call, capture the trailing
reasoning/answer after the last call, and thread reasoning_tokens into meta.
"""
from __future__ import annotations

from bench.analysis.trace import build_steps, final_blocks, render_md


def _ev(etype: str, **data):
    return {"type": etype, "data": data}


def _make_events():
    # Turn 0: reason + narrate, then fire TWO sibling tool calls.
    # Turn 1: narrate, then one tool call.
    # Trailing: closing reasoning + final answer after the last tool.
    return [
        _ev("assistant.reasoning", content="I should find the symbol first."),
        _ev("assistant.message", content="Searching the graph."),
        _ev("tool.execution_start", toolName="code-graph-search_code",
            toolCallId="c1", turnId=0, arguments={"query": "foo"}),
        _ev("tool.execution_start", toolName="grep",
            toolCallId="c2", turnId=0, arguments={"pattern": "foo"}),
        _ev("tool.execution_complete", toolCallId="c1", success=True,
            result={"content": [{"type": "text", "text": "hit"}]}),
        _ev("tool.execution_complete", toolCallId="c2", success=True,
            result={"content": [{"type": "text", "text": "match"}]}),
        _ev("assistant.reasoning", content="Now I narrow down the file."),
        _ev("assistant.message", content="Reading the file."),
        _ev("tool.execution_start", toolName="view",
            toolCallId="c3", turnId=1, arguments={"path": "a.py"}),
        _ev("tool.execution_complete", toolCallId="c3", success=True,
            result={"content": [{"type": "text", "text": "src"}]}),
        _ev("assistant.reasoning", content="The fix lives in a.py."),
        _ev("assistant.message", content="FINAL_LOCALIZATION_JSON: [\"a.py\"]"),
    ]


def test_thinking_before_attaches_to_first_tool_of_turn():
    steps = build_steps(_make_events())
    assert len(steps) == 3
    # Step 0 (first tool of turn 0) carries the turn's thinking + narration.
    assert steps[0]["thinking_before"] == "I should find the symbol first."
    assert steps[0]["narration_before"] == "Searching the graph."
    # Step 1 is a sibling in the same turn -> before-window is empty.
    assert steps[1]["thinking_before"] == ""
    assert steps[1]["narration_before"] == ""
    assert steps[0]["turn"] == steps[1]["turn"] == 0
    # Step 2 (turn 1) carries turn 1's thinking + narration.
    assert steps[2]["thinking_before"] == "Now I narrow down the file."
    assert steps[2]["narration_before"] == "Reading the file."


def test_final_blocks_capture_trailing_answer():
    final = final_blocks(_make_events())
    assert final["thinking"] == "The fix lives in a.py."
    assert "FINAL_LOCALIZATION_JSON" in final["narration"]


def test_render_md_shows_thoughts_before_call_and_reasoning_tokens():
    events = _make_events()
    steps = build_steps(events)
    final = final_blocks(events)
    meta = {"input_tokens": 100, "output_tokens": 10,
            "reasoning_tokens": 42, "total_tokens": 110}
    md = render_md(meta, steps, [], {
        "tool_calls_total": 3, "tool_calls_by_kind": {}, "structural_adopted": True,
        "structural_calls": 1, "first_tool": "code-graph-search_code",
        "empty_result_count": 0, "tool_error_count": 0, "redundant_call_count": 0,
        "gold_hit_source_counts": {},
    }, final)
    assert "of which reasoning: 42" in md
    assert "thinking (before call):" in md
    assert "narration (before call):" in md
    # The thought renders before the call line for step 0.
    assert md.index("I should find the symbol first.") < md.index('"query": "foo"')
    assert "## Final (after last tool call)" in md


def test_final_blocks_empty_when_no_trailing_content():
    events = [
        _ev("tool.execution_start", toolName="grep", toolCallId="c1",
            turnId=0, arguments={}),
        _ev("tool.execution_complete", toolCallId="c1", success=True,
            result={"content": [{"type": "text", "text": "x"}]}),
    ]
    final = final_blocks(events)
    assert final["thinking"] == ""
    assert final["narration"] == ""


def test_cost_without_benefit_charges_unused_structural_tokens():
    """A structural tool that surfaces a gold file is beneficial; an empty or
    unused structural call is charged as cost-without-benefit."""
    from bench.analysis.trace import attribute_files, summarize

    steps = [
        # Step 0: graph call that surfaces the gold file -> beneficial.
        {"step": 0, "turn": 0, "tool": "code-graph-search_code", "kind": "graph",
         "arguments": {"query": "centroid"}, "success": True, "empty": False,
         "result_text": "uxarray/grid/coordinates.py prepare_points",
         "result_tokens_est": 50},
        # Step 1: graph call returning empty -> wasted (0 tokens but a wasted call).
        {"step": 1, "turn": 0, "tool": "code-graph-search_code", "kind": "graph",
         "arguments": {"query": "nope"}, "success": True, "empty": True,
         "result_text": "", "result_tokens_est": 0},
        # Step 2: verbose lsp dump never tied to a gold prediction -> wasted.
        {"step": 2, "turn": 1, "tool": "lsp-document_symbols", "kind": "lsp",
         "arguments": {"file": "x.py"}, "success": True, "empty": False,
         "result_text": "lots of symbols", "result_tokens_est": 2714},
        # Step 3: builtin grep -> not under test, not charged.
        {"step": 3, "turn": 2, "tool": "grep", "kind": "builtin_reader",
         "arguments": {"pattern": "y"}, "success": True, "empty": False,
         "result_text": "noise", "result_tokens_est": 100},
    ]
    pred = ["uxarray/grid/coordinates.py"]
    gold = ["uxarray/grid/coordinates.py"]
    attribution = attribute_files(pred, gold, steps, prompt_text="")
    cwb = summarize(steps, attribution)["cost_without_benefit"]

    assert cwb["benefited"] is True
    # graph step 0 (50 tok) benefited; step 1 empty wasted; lsp 2714 wasted.
    assert cwb["beneficial_tokens"] == 50
    assert cwb["wasted_tokens"] == 2714
    assert cwb["wasted_calls"] == 2  # empty graph + unused lsp
    assert cwb["structural_result_tokens"] == 50 + 0 + 2714
    assert cwb["by_kind"]["lsp"]["wasted_tokens"] == 2714
    assert cwb["by_kind"]["graph"]["wasted_calls"] == 1
    # builtin grep tokens are NOT counted as structural cost.
    assert "builtin_reader" not in cwb["by_kind"]


def test_cost_without_benefit_flags_zero_contribution():
    """Structural tool used but it never surfaced the gold file -> benefited False
    and all its tokens are wasted."""
    from bench.analysis.trace import attribute_files, summarize

    steps = [
        {"step": 0, "turn": 0, "tool": "code-graph-search_code", "kind": "graph",
         "arguments": {"query": "q"}, "success": True, "empty": False,
         "result_text": "some/other/file.py", "result_tokens_est": 300},
    ]
    # Agent predicted the gold from its own prior / builtin, not the graph.
    pred = ["the/gold.py"]
    gold = ["the/gold.py"]
    attribution = attribute_files(pred, gold, steps, prompt_text="")
    cwb = summarize(steps, attribution)["cost_without_benefit"]

    assert cwb["benefited"] is False
    assert cwb["wasted_tokens"] == 300
    assert cwb["wasted_fraction"] == 1.0
