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
# Prompt assembly: nudge + localize modes
# ---------------------------------------------------------------------------


def test_prompt_nudge_code_graph_mandates_search(tmp_path):
    p = cr.build_prompt(cr.CODE_GRAPH, tmp_path, "Fix it.", "proj", nudge=True)
    assert "MUST begin by calling search_code(project=\"proj\")" in p
    assert "Do not use the `ask` tool" in p


def test_prompt_nudge_no_mcp_is_matched_control(tmp_path):
    p = cr.build_prompt(cr.NO_MCP, tmp_path, "Fix it.", "proj", nudge=True)
    # Matched "search-first" control with no tool sales / no graph verbs.
    assert "Before resorting to plain text search" in p
    assert "search_code" not in p


def test_prompt_localize_emits_sentinel_contract(tmp_path):
    p = cr.build_prompt(cr.CODE_GRAPH, tmp_path, "Bug.", "proj", mode=cr.LOCALIZE)
    assert cr.LOCALIZE_SENTINEL in p
    assert "Do NOT modify any files" in p
    assert "Do NOT emit it through a" in p


# ---------------------------------------------------------------------------
# Lane 1 adoption-calibration arms (CTRL / SEM / RAT)
# ---------------------------------------------------------------------------


def test_adopt_ctrl_capability_equals_canonical_nudge(tmp_path):
    # CTRL must be byte-identical to the canonical nudge capability (prereg §2
    # amended: CTRL == _CAP_CODE_GRAPH_NUDGE), independent of env-gated variants.
    cap = cr._capability(cr.CODE_GRAPH, "proj", nudge=False, adopt_arm="ctrl")
    assert cap == cr._CAP_CODE_GRAPH_NUDGE.format(project="proj")


def test_adopt_arms_bypass_env_gates(tmp_path, monkeypatch):
    # The SUBST/SPIKE/TRAVERSE env gates must NOT affect arm capabilities.
    monkeypatch.setenv("CGRAPH_SUBST_NUDGE", "1")
    monkeypatch.setenv("CGRAPH_SPIKE_NUDGE", "1")
    monkeypatch.setenv("CGRAPH_TRAVERSE_NUDGE", "1")
    cap = cr._capability(cr.CODE_GRAPH, "proj", nudge=True, adopt_arm="ctrl")
    assert cap == cr._CAP_CODE_GRAPH_NUDGE.format(project="proj")
    assert "TRUST the ranked results" not in cap
    assert "get_importers" not in cap


def test_adopt_sem_appends_frozen_clause_only(monkeypatch, tmp_path):
    monkeypatch.delenv("BENCH_BLOCK_NETWORK", raising=False)
    p = cr.build_prompt(
        cr.CODE_GRAPH, tmp_path, "Bug.", "proj", mode=cr.LOCALIZE, adopt_arm="sem"
    )
    # SEM == CTRL (canonical nudge) + frozen edge-semantics clause.
    assert "MUST begin by calling search_code(project=\"proj\")" in p
    assert "Relatedness alone is not a reason to keep or to drop." in p
    assert "evidence that code is RELATED" in p
    # Rejected wording (benchmark prior) must never appear.
    assert "often a caller or a sibling" not in p
    # SEM has no extra keep/drop step (that is RAT's lever).
    assert "KEEP <file>" not in p


def test_adopt_rat_injects_keep_drop_step_before_sentinel(tmp_path):
    p = cr.build_prompt(
        cr.CODE_GRAPH, tmp_path, "Bug.", "proj", mode=cr.LOCALIZE, adopt_arm="rat"
    )
    assert "KEEP <file>" in p and "DROP <file>" in p
    assert "list every file the graph surfaced" in p
    # The keep/drop step must precede the FINAL sentinel instruction.
    assert p.index("list every file the graph surfaced") < p.index(cr.LOCALIZE_SENTINEL)
    # RAT shares the CTRL base, not the SEM clause.
    assert "MUST begin by calling search_code(project=\"proj\")" in p
    assert "Relatedness alone is not a reason" not in p


def test_adopt_arm_guard_rejects_non_code_graph(tmp_path):
    with pytest.raises(ValueError):
        cr.build_prompt(
            cr.NO_MCP, tmp_path, "Bug.", "proj", mode=cr.LOCALIZE, adopt_arm="ctrl"
        )


def test_adopt_arm_guard_rejects_non_localize(tmp_path):
    with pytest.raises(ValueError):
        cr.build_prompt(
            cr.CODE_GRAPH, tmp_path, "Bug.", "proj", mode=cr.FIX, adopt_arm="ctrl"
        )


def test_adopt_arm_guard_rejects_unknown_value(tmp_path):
    # Programmatic callers bypass argparse choices; an unknown arm must not
    # silently fall through to CTRL behavior while logging prompt_mode=adopt-bad.
    with pytest.raises(ValueError):
        cr.build_prompt(
            cr.CODE_GRAPH, tmp_path, "Bug.", "proj", mode=cr.LOCALIZE, adopt_arm="bad"
        )


# ---------------------------------------------------------------------------
# NOISY/GRAPH-WRONG distractor injection wiring
# ---------------------------------------------------------------------------


class _Inst:
    def __init__(self, instance_id):
        self.instance_id = instance_id


def test_compute_prompt_mode_suffixes_only_when_injecting():
    assert cr._compute_prompt_mode(adopt_arm="sem", nudge=True, inject_label=None) == "adopt-sem"
    assert (
        cr._compute_prompt_mode(adopt_arm="sem", nudge=True, inject_label="noisy")
        == "adopt-sem-noisy"
    )
    assert cr._compute_prompt_mode(adopt_arm=None, nudge=True, inject_label=None) == "nudged"
    assert (
        cr._compute_prompt_mode(adopt_arm=None, nudge=False, inject_label="gwrong")
        == "neutral-gwrong"
    )


def test_inject_env_pins_task_and_manifest():
    inst = _Inst("django__django-1")
    env = cr._inject_env(inst, inject_manifest=Path("/tmp/m.json"), inject_k=3)
    assert env == {
        "BENCH_NOISY_MANIFEST": "/tmp/m.json",
        "BENCH_NOISY_TASK": "django__django-1",
        "BENCH_NOISY_K": "3",
    }


def test_inject_env_omits_k_when_unset():
    env = cr._inject_env(_Inst("t1"), inject_manifest=Path("/tmp/m.json"), inject_k=None)
    assert "BENCH_NOISY_K" not in env
    assert env["BENCH_NOISY_TASK"] == "t1"


def test_inject_env_none_when_disabled():
    assert cr._inject_env(_Inst("t1"), inject_manifest=None, inject_k=None) is None


def test_write_mcp_config_clean_is_falkor_only(tmp_path):
    w = tmp_path / "wrap.sh"
    w.write_text("#!/bin/bash\n")
    cfg = cr._write_mcp_config(tmp_path, w, "h", 6379)
    env = json.loads(cfg.read_text())["mcpServers"]["code-graph"]["env"]
    assert env == {"FALKORDB_HOST": "h", "FALKORDB_PORT": "6379"}


def test_write_mcp_config_threads_extra_env(tmp_path):
    w = tmp_path / "wrap.sh"
    w.write_text("#!/bin/bash\n")
    cfg = cr._write_mcp_config(
        tmp_path, w, "h", 6379, extra_env={"BENCH_NOISY_TASK": "t1"}
    )
    env = json.loads(cfg.read_text())["mcpServers"]["code-graph"]["env"]
    assert env["FALKORDB_HOST"] == "h"
    assert env["BENCH_NOISY_TASK"] == "t1"


def test_run_one_inject_guard_rejects_non_localize(tmp_path):
    with pytest.raises(ValueError):
        cr.run_one(
            _Inst("x"), track=cr.CODE_GRAPH, model="m", cache_dir=tmp_path,
            wall_time=1.0, server_root=tmp_path, mode=cr.FIX,
            inject_manifest=Path("/tmp/m.json"), inject_label="noisy",
        )


def test_run_one_inject_guard_requires_label(tmp_path):
    with pytest.raises(ValueError):
        cr.run_one(
            _Inst("x"), track=cr.CODE_GRAPH, model="m", cache_dir=tmp_path,
            wall_time=1.0, server_root=tmp_path, mode=cr.LOCALIZE,
            inject_manifest=Path("/tmp/m.json"), inject_label=None,
        )


# ---------------------------------------------------------------------------
# Localization extraction + scoring
# ---------------------------------------------------------------------------


def _msg(content):
    return json.dumps({"type": "assistant.message", "data": {"content": content}})


def test_extract_agent_text_concats_messages():
    stdout = "\n".join([
        _msg("first thought"),
        json.dumps({"type": "tool.execution_start", "data": {"name": "bash"}}),
        json.dumps({"type": "user.message", "data": {"content": "IGNORE ME"}}),
        _msg(""),  # empty tool-only turn
        _msg("final answer"),
    ])
    text = cr.extract_agent_text(stdout)
    assert "first thought" in text
    assert "final answer" in text
    assert "IGNORE ME" not in text


def test_parse_localization_strict_sentinel():
    text = 'Reasoning...\nFINAL_LOCALIZATION_JSON: ["a/pkg/x.py", "./pkg/y.py"]'
    pred, err, fallback = cr.parse_localization(text)
    assert pred == ["pkg/x.py", "pkg/y.py"]
    assert err is None
    assert fallback is False


def test_parse_localization_uses_last_sentinel():
    text = (
        'FINAL_LOCALIZATION_JSON: ["wrong.py"]\n'
        'on reflection...\n'
        'FINAL_LOCALIZATION_JSON: ["right.py"]'
    )
    pred, err, fallback = cr.parse_localization(text)
    assert pred == ["right.py"]
    assert err is None


def test_parse_localization_missing_sentinel_flags_fallback():
    pred, err, fallback = cr.parse_localization("no marker here")
    assert pred == []
    assert err == "sentinel_missing"
    assert fallback is True


def test_parse_localization_malformed_array():
    pred, err, fallback = cr.parse_localization("FINAL_LOCALIZATION_JSON: [oops")
    assert pred == []
    assert fallback is True
    assert err == "unbalanced_array"


def test_score_localization_recall_and_mrr():
    scores = cr.score_localization(
        pred=["pkg/b.py", "pkg/a.py"], gold=["pkg/a.py", "pkg/c.py"]
    )
    assert scores["file_recall"] == 0.5
    assert scores["file_precision"] == 0.5
    assert scores["file_all_found"] is False
    assert scores["acc_at_1"] == 0.0  # first pred (b.py) not gold
    assert scores["acc_at_3"] == 1.0
    assert scores["file_mrr"] == 0.5  # a.py at rank 2


def test_score_localization_all_found():
    scores = cr.score_localization(pred=["a.py", "b.py"], gold=["a.py", "b.py"])
    assert scores["file_all_found"] is True
    assert scores["file_recall"] == 1.0
    assert scores["acc_at_1"] == 1.0
    assert scores["file_mrr"] == 1.0


# ---------------------------------------------------------------------------
# Nudge compliance metrics
# ---------------------------------------------------------------------------


def test_nudge_compliance_first_is_graph():
    stdout = "\n".join([
        json.dumps({"type": "tool.execution_start", "data": {"name": "code-graph-search_code"}}),
        json.dumps({"type": "tool.execution_start", "data": {"name": "bash"}}),
        json.dumps({"type": "tool.execution_start", "data": {"name": "code-graph-get_callers"}}),
    ])
    c = cr.nudge_compliance(stdout)
    assert c["first_tool"] == "code-graph-search_code"
    assert c["first_is_graph"] is True
    assert c["graph_calls"] == 2


def test_nudge_compliance_no_graph():
    stdout = json.dumps({"type": "tool.execution_start", "data": {"name": "bash"}})
    c = cr.nudge_compliance(stdout)
    assert c["first_tool"] == "bash"
    assert c["first_is_graph"] is False
    assert c["graph_calls"] == 0


# ---------------------------------------------------------------------------
# Resume identity includes mode / prompt_mode / model
# ---------------------------------------------------------------------------


def test_load_done_keys_include_mode_and_prompt(tmp_path):
    results = tmp_path / "results.jsonl"
    rows = [
        {"task_id": "t1", "config": "code_graph", "model": "claude-opus-4.8",
         "mode": "fix", "prompt_mode": "neutral", "run_idx": 0,
         "runner": cr.RUNNER_VERSION, "completed": True},
        {"task_id": "t1", "config": "code_graph", "model": "claude-opus-4.8",
         "mode": "localize", "prompt_mode": "nudged", "run_idx": 0,
         "runner": cr.RUNNER_VERSION, "completed": True},
    ]
    results.write_text("\n".join(json.dumps(r) for r in rows))
    done = cr._load_done(results)
    assert ("t1", "code_graph", "claude-opus-4.8", "fix", "neutral", 0) in done
    assert ("t1", "code_graph", "claude-opus-4.8", "localize", "nudged", 0) in done
    # A different prompt_mode is NOT considered done.
    assert ("t1", "code_graph", "claude-opus-4.8", "fix", "nudged", 0) not in done


# ---------------------------------------------------------------------------
# Real captured fixture (when present)
# ---------------------------------------------------------------------------

_FIXTURE = Path(__file__).resolve().parents[1].parent / "bench" / "cache" / "copilot-spike" / "logs" / "mcp-probe3"


@pytest.mark.skipif(not (_FIXTURE / "..").exists() or not _FIXTURE.exists(), reason="spike fixture absent")
def test_real_fixture_tokens_parse():
    out = cr.parse_tokens_from_logs(_FIXTURE)
    assert out["usage_blocks"] >= 1
    assert out["input_tokens"] > 0


# ---------------------------------------------------------------------------
# Leak hardening: git-walk-up fence + index branch pin (harden/2)
# ---------------------------------------------------------------------------

import os  # noqa: E402

from bench.datasets import swe_bench  # noqa: E402


def test_strip_git_oracle_removes_nested_git(tmp_path):
    root = tmp_path / "wt"
    (root / "pkg").mkdir(parents=True)
    # top-level repo .git directory
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[remote]\n")
    # submodule .git is a FILE holding a gitdir pointer, not a directory
    (root / "pkg" / ".git").write_text("gitdir: ../../.git/modules/pkg\n")
    # real source must survive
    (root / "pkg" / "mod.py").write_text("x = 1\n")

    swe_bench.strip_git_oracle(root)

    assert not (root / ".git").exists()
    assert not (root / "pkg" / ".git").exists()
    assert (root / "pkg" / "mod.py").read_text() == "x = 1\n"


def test_harden_env_scrubs_git_and_creds(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    monkeypatch.setenv("GIT_DIR", "/somewhere/.git")
    monkeypatch.setenv("GIT_WORK_TREE", "/somewhere")
    monkeypatch.setenv("GIT_COMMON_DIR", "/somewhere/.git")
    out = cr._harden_env(dict(os.environ))
    assert "GITHUB_TOKEN" not in out
    assert "GIT_DIR" not in out
    assert "GIT_WORK_TREE" not in out
    assert "GIT_COMMON_DIR" not in out
    assert out["GIT_CONFIG_NOSYSTEM"] == "1"


def test_git_ceiling_dirs_points_at_worktree_parent(tmp_path):
    wt = tmp_path / "worktrees" / "code_graph" / "loc-abc123"
    wt.mkdir(parents=True)
    ceiling = cr._git_ceiling_dirs(wt)
    parent = str((tmp_path / "worktrees" / "code_graph").resolve())
    assert parent in ceiling.split(os.pathsep)


def test_hardening_meta_harden2_flags(monkeypatch, tmp_path):
    monkeypatch.setenv("BENCH_BLOCK_NETWORK", "1")
    meta = cr.hardening_meta(tmp_path, "", 0)  # tmp_path has no .git
    assert meta["harness_hardening_version"] == "harden/2"
    assert meta["git_walk_up_blocked"] is True
    assert meta["git_sanitized"] is True
    assert meta["network_block_mode"] is True
    assert meta["opaque_path_mode"] is True


def test_hardening_meta_on_by_default(monkeypatch, tmp_path):
    # Hardening is default-ON: tracing repeatedly caught the agent fetching the
    # gold file list from GitHub, turning localization misses into fake recall=1.0.
    monkeypatch.delenv("BENCH_BLOCK_NETWORK", raising=False)
    meta = cr.hardening_meta(tmp_path, "", 0)
    assert meta["git_walk_up_blocked"] is True
    assert meta["network_block_mode"] is True


def test_hardening_meta_explicit_opt_out(monkeypatch, tmp_path):
    # Hardening only disengages when explicitly set to a falsy value.
    monkeypatch.setenv("BENCH_BLOCK_NETWORK", "0")
    meta = cr.hardening_meta(tmp_path, "", 0)
    assert meta["git_walk_up_blocked"] is False
    assert meta["network_block_mode"] is False


def test_leak_scan_flags_git_escape_attempts():
    # `git -C ..` re-points discovery above the ceiling fence.
    sig = cr._scan_leak_arguments("bash", {"command": "git -C .. log --oneline -1"})
    assert sig, "git -C escape should be flagged"
    # Explicit --git-dir bypass.
    sig2 = cr._scan_leak_arguments("bash", {"command": "git --git-dir=/x/.git log"})
    assert sig2, "git --git-dir escape should be flagged"
    # Unsetting the ceiling env before running git.
    sig3 = cr._scan_leak_arguments("bash", {"command": "env -u GIT_CEILING_DIRECTORIES git log"})
    assert sig3, "env -u GIT_CEILING escape should be flagged"
    # A benign in-worktree command is NOT flagged.
    assert cr._scan_leak_arguments("bash", {"command": "ls -la && cat README.md"}) == []


def test_resolve_run_dir_layout_matches_row_stdout_path(tmp_path):
    # The producer (_resolve_run_dir) and the consumer (exposure_adoption.
    # row_stdout_path) must agree on the on-disk layout, including the run<idx>
    # nesting introduced for multi-run pilots. This pins that contract so a
    # change to one side can't silently desync log lookup.
    from bench.analysis import exposure_adoption as ea

    cache_dir = tmp_path / "batch"
    model = "claude-opus-4.8"
    common = dict(
        model=model,
        mode="localize",
        prompt_mode="adopt-sem",
        track="code_graph",
        instance_id="django__django-12345",
    )
    for run_idx in (0, 1, 3):
        run_dir = cr._resolve_run_dir(cache_dir, run_idx=run_idx, **common)
        log_dir = run_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "stdout.jsonl").write_text("{}\n")

        row = {
            "mode": common["mode"],
            "prompt_mode": common["prompt_mode"],
            "config": common["track"],
            "task_id": common["instance_id"],
            "run_idx": run_idx,
        }
        resolved = ea.row_stdout_path(cache_dir, model, row)
        assert resolved == log_dir / "stdout.jsonl"


def test_resolve_run_dir_nests_only_for_nonzero_idx(tmp_path):
    base = dict(
        model="m",
        mode="fix",
        prompt_mode="neutral",
        track="lsp",
        instance_id="t-1",
    )
    bare = cr._resolve_run_dir(tmp_path, run_idx=0, **base)
    nested = cr._resolve_run_dir(tmp_path, run_idx=2, **base)
    assert bare.name == "t-1"
    assert nested.name == "run2" and nested.parent.name == "t-1"
