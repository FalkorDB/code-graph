"""Multi-hop navigation PREMIUM agent arm (Lane 2).

Drives the Copilot CLI over the validated multi-hop nav question set across the
three arms — ``no_mcp`` (baseline, builtin grep/view only), ``lsp`` (jedi MCP),
and ``code_graph`` (FalkorDB code-graph MCP) — and scores each answer against the
jedi oracle gold with set-F1 (file + qualname) and, for path questions, boolean
reachability correctness. Also records the realized token / tool-call / premium
cost per arm (prereg H2: median token reduction).

This is the agent counterpart to the FREE ``nav_multihop_gate.py`` answerability
gate. The gate proved the GRAPH DATA is compact + correct on uxarray; this runner
measures whether an AGENT wielding each tool actually reaches that answer, and at
what cost.

Design notes / invariants (see session checkpoint "Multi-hop nav gate"):
* The code_graph arm queries the PRE-BUILT fixed-resolver graph by project name
  (default ``mh_uxarray`` on FalkorDB :6380). It does NOT re-index — the running
  staging API server lacks the resolver fix (commit 8fa2a43), so re-indexing
  would silently rebuild a BROKEN graph and invalidate the comparison.
* All three arms run with cwd = the SAME uxarray worktree the graph was indexed
  from and the oracle gold is relative to, so paths align across arms.
* The MCP nav tools actually exposed are find_symbol / search_code /
  get_neighbors / impact_analysis / find_path (NOT get_callers/get_callees —
  those are internal helpers). The `ask` GraphRAG tool was dropped (it errored
  100% of the time without a Gemini key). find_symbol bridges a symbol name to
  its integer node id, which the relationship tools require. The code_graph
  capability note names the real tools.

Usage:
    .venv/bin/python -m bench.runners.nav_multihop_agent \
        --questions /tmp/ux_questions.json \
        --project mh_uxarray --port 6380 \
        --model claude-sonnet-4.6 \
        --arms no_mcp lsp code_graph \
        --out /tmp/ux_nav_agent.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from bench.runners.copilot_runner import (
    CODE_GRAPH,
    LSP,
    NO_MCP,
    DEFAULT_MCP_SERVER_ROOT,
    RUNNER_VERSION,
    extract_agent_text,
    nudge_compliance,
    parse_result_event,
    parse_tokens_from_logs,
    parse_tool_calls,
    run_copilot,
    _write_lsp_mcp_config,
    _write_lsp_wrapper,
    _write_mcp_config,
    _write_mcp_wrapper,
)
from bench.runners.nav_multihop_gate import _prf

ARMS = (NO_MCP, LSP, CODE_GRAPH)

# Question types whose answer is a SET of (path, qualname); the remaining type
# ("path") is a reachability boolean + an optional example chain.
SET_TYPES = ("callers", "callees", "blast_radius")

NAV_SENTINEL = "FINAL_NAV_JSON:"

# ---------------------------------------------------------------------------
# Capability notes — symmetric across arms; each names ONLY its own mechanism.
# The code_graph note lists the REAL exposed tools and the type->tool mapping.
# ---------------------------------------------------------------------------

_CAP_NO_MCP = (
    "No external MCP navigation tools are available. Use Copilot's built-in file "
    "reading and text search (grep/rg) tools to trace the call relationships "
    "yourself."
)

_CAP_LSP = (
    "An LSP MCP server is available exposing jedi-backed Python navigation tools "
    "(goto_definition, find_references, hover, document_symbols). Paths are "
    "repo-root-relative; line/character positions are 0-based (subtract 1 from "
    "the 1-based line numbers grep/view report). To find CALLERS of a function, "
    "use find_references on its definition; to find CALLEES, read the function "
    "body and goto_definition on each name it calls. Prefer these precise "
    "navigation tools over plain text search when they help."
)

_CAP_CODE_GRAPH = (
    "A code-graph MCP server is available, already indexed under "
    'project="{project}" (do NOT call index_repo). Workflow: (1) call '
    'find_symbol(name, project="{project}", file=<defining file>) to resolve a '
    "function/method/class to its integer symbol_id. The question gives you the "
    "exact qualname and file, so pass the leaf name (e.g. the part after the last "
    "dot) plus that file to disambiguate; the result with file_match=true is the "
    "one you want. (2) get_neighbors(symbol_id, project, relation=\"CALLS\", "
    "direction=\"IN\") returns the direct CALLERS, direction=\"OUT\" returns the "
    "direct CALLEES. (3) impact_analysis(symbol_id, project, direction=\"IN\", "
    "depth=3) returns the transitive callers (blast radius) up to 3 hops. (4) For "
    "a reachability question, resolve BOTH endpoints with find_symbol, then "
    "find_path(source_id, dest_id, project) returns a call chain between them (an "
    "empty result means unreachable). Each returned node carries its file and "
    "name, so you can answer directly from the graph without grepping. Prefer "
    "these precise graph tools over plain text search."
)


def _capability(track: str, project: str) -> str:
    if track == CODE_GRAPH:
        return _CAP_CODE_GRAPH.format(project=project)
    if track == LSP:
        return _CAP_LSP
    return _CAP_NO_MCP


_OUTPUT_SPEC_SET = (
    '{{"items": [{{"path": "pkg/module.py", "qualname": "ClassName.method"}}, '
    '{{"path": "pkg/other.py", "qualname": "module_level_function"}}]}}'
)
_OUTPUT_SPEC_PATH = (
    '{{"reachable": true, "path": [{{"path": "pkg/a.py", "qualname": "A.f"}}, '
    '{{"path": "pkg/b.py", "qualname": "B.g"}}]}}'
)

_PROMPT = """\
You are answering a CODE NAVIGATION question about the Python repository checked
out at {cwd}.

QUESTION:
{question}

Investigate the repository to determine the answer. Do NOT modify any files. Do
NOT run or edit tests.
{capability}
When you are confident, finish your FINAL assistant message with a single line in
EXACTLY this format:

{sentinel} {output_spec}

Rules for that line:
- Use repo-root-relative POSIX paths to .py source files.
- `qualname` is the dotted name of the function/method, e.g. `ClassName.method`
  or `module_level_function` (no file path, no parentheses, no arguments).
{type_rule}
- Write that line as plain text in your OWN final message. Do NOT emit it through
  a shell command, `echo`, a file write, or any tool call."""

_TYPE_RULE_SET = (
    "- List EVERY matching function. Include both source and test functions."
)
_TYPE_RULE_PATH = (
    "- If a call chain exists, set reachable=true and give ONE such ordered chain "
    "from source to target in `path`. If NO chain exists, set reachable=false and "
    "path=[]."
)


def build_nav_prompt(track: str, cwd: Path, q: dict, project: str) -> str:
    is_path = q["type"] == "path"
    return _PROMPT.format(
        cwd=cwd,
        question=q["question"].strip(),
        capability=_capability(track, project),
        sentinel=NAV_SENTINEL,
        output_spec=_OUTPUT_SPEC_PATH if is_path else _OUTPUT_SPEC_SET,
        type_rule=_TYPE_RULE_PATH if is_path else _TYPE_RULE_SET,
    )


# ---------------------------------------------------------------------------
# Answer parsing + scoring
# ---------------------------------------------------------------------------


def _norm_path(p: str) -> str:
    p = (p or "").strip().strip("'\"").strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def _norm_qual(s: str) -> str:
    return (s or "").strip().strip("'\"").strip()


def _extract_json_object(text: str) -> tuple[dict | None, str | None]:
    """Pull the JSON object that follows the last NAV_SENTINEL occurrence."""
    idx = text.rfind(NAV_SENTINEL)
    if idx == -1:
        return None, "sentinel_missing"
    tail = text[idx + len(NAV_SENTINEL):]
    start = tail.find("{")
    if start == -1:
        return None, "no_object"
    depth = 0
    end = -1
    in_str = False
    esc = False
    for i in range(start, len(tail)):
        c = tail[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        return None, "unbalanced_object"
    try:
        return json.loads(tail[start:end + 1]), None
    except json.JSONDecodeError as exc:
        return None, f"json_error:{exc.msg}"


def parse_nav_answer(text: str, qtype: str) -> tuple[dict, str | None]:
    obj, err = _extract_json_object(text)
    if obj is None:
        if qtype == "path":
            return {"reachable": None, "path": []}, err
        return {"items": []}, err
    if qtype == "path":
        reachable = obj.get("reachable")
        if isinstance(reachable, str):
            reachable = reachable.strip().lower() == "true"
        path = obj.get("path") or []
        items = [
            (_norm_path(it.get("path", "")), _norm_qual(it.get("qualname", "")))
            for it in path
            if isinstance(it, dict)
        ]
        return {"reachable": bool(reachable), "path": items}, None
    raw = obj.get("items")
    if not isinstance(raw, list):
        return {"items": []}, "items_not_a_list"
    items = [
        (_norm_path(it.get("path", "")), _norm_qual(it.get("qualname", "")))
        for it in raw
        if isinstance(it, dict)
    ]
    return {"items": items}, None


def _leaf(qual: str) -> str:
    return _norm_qual(qual).split(".")[-1]


def _gold_set(q: dict) -> set[tuple[str, str]]:
    return {(_norm_path(g["path"]), _norm_qual(g["qualname"])) for g in q["gold"]}


def _loose_set(items: list[tuple[str, str]]) -> set[tuple[str, str]]:
    """Lenient identity: (path, last dotted component) — tolerates agents that
    emit a bare leaf or a different qualname prefix than the oracle."""
    return {(p, _leaf(qn)) for p, qn in items if p}


def _endpoint_match(item: tuple[str, str], spec: dict) -> bool:
    """A predicted (path, qual) matches a path-question endpoint spec when the
    file matches and EITHER the full qualname or just the leaf agrees."""
    p, qn = item
    sp = _norm_path(spec["path"])
    if p != sp:
        return False
    return _norm_qual(qn) == _norm_qual(spec["qualname"]) or _leaf(qn) == _leaf(spec["qualname"])


def score_nav(q: dict, pred: dict) -> dict[str, Any]:
    qtype = q["type"]
    if qtype == "path":
        gold_reachable = bool(q["gold"]["reachable"])
        pred_reachable = pred.get("reachable")
        boolean_correct = (pred_reachable is not None) and (pred_reachable == gold_reachable)
        ppath = pred.get("path", [])
        # For a claimed-reachable answer, demand a non-empty chain whose
        # endpoints are the requested source and target (beyond a lucky bool).
        endpoints_correct = False
        if pred_reachable and ppath:
            src = q["symbol"]["source"]
            tgt = q["symbol"]["target"]
            endpoints_correct = _endpoint_match(ppath[0], src) and _endpoint_match(ppath[-1], tgt)
        # The scored credit: negatives need only the correct boolean; positives
        # additionally need a well-formed chain with correct endpoints.
        if gold_reachable:
            path_correct = bool(boolean_correct and endpoints_correct)
        else:
            path_correct = bool(boolean_correct)
        return {
            "gold_reachable": gold_reachable,
            "pred_reachable": pred_reachable,
            "boolean_correct": bool(boolean_correct),
            "endpoints_correct": bool(endpoints_correct),
            "path_correct": path_correct,
            "pred_path_len": len(ppath),
        }
    gold = _gold_set(q)
    pred_set = {(p, qn) for p, qn in pred.get("items", []) if p}
    gold_files = {p for p, _ in gold}
    pred_files = {p for p, _ in pred_set}
    return {
        "qual_prf": _prf(pred_set, gold),
        "loose_qual_prf": _prf(_loose_set(pred.get("items", [])), _loose_set(list(gold))),
        "file_prf": _prf(pred_files, gold_files),
        "pred_n": len(pred_set),
        "gold_n": len(gold),
    }


# ---------------------------------------------------------------------------
# Per-(question, arm) run
# ---------------------------------------------------------------------------


def _nav_calls(tool_by_name: dict[str, int], track: str) -> int:
    prefix = "lsp" if track == LSP else "code-graph"
    return sum(n for k, n in tool_by_name.items() if k.startswith(prefix))


def _gate_caps(gate_path: Path | None) -> dict[str, dict]:
    """Load per-question GRAPH answerability caps from the agentless gate output.

    The gate computed the graph's Cypher answer vs gold for every question, so its
    per-question file/qual F1 is the CEILING a code_graph agent can reach by
    perfectly transcribing the tool output. Folding it in lets us attribute a
    code_graph agent shortfall to either the agent (below cap) or the data (low
    cap) — the rubber-duck's #1 must-fix.
    """
    if not gate_path or not gate_path.exists():
        return {}
    caps: dict[str, dict] = {}
    for r in json.loads(gate_path.read_text()).get("rows", []):
        if r["type"] == "path":
            caps[r["id"]] = {
                "graph_reachable": r.get("graph_reachable"),
                "graph_path_correct": r.get("correct"),
            }
        else:
            caps[r["id"]] = {
                "graph_file_f1": r.get("file_prf", {}).get("f1"),
                "graph_qual_f1": r.get("qual_prf", {}).get("f1"),
                "graph_file_recall": r.get("file_prf", {}).get("recall"),
                "grep_file_recall": r.get("grep_file_recall"),
            }
    return caps


def run_one_nav(
    q: dict,
    *,
    track: str,
    model: str,
    worktree: Path,
    project: str,
    port: int,
    server_root: Path,
    out_dir: Path,
    wall_time: float,
    cap: dict | None = None,
) -> dict[str, Any]:
    run_dir = out_dir / "runs" / track / q["id"].replace("/", "_").replace("::", "__")
    if run_dir.exists():
        import shutil

        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    mcp_config = None
    if track == CODE_GRAPH:
        wrapper = _write_mcp_wrapper(run_dir, server_root)
        mcp_config = _write_mcp_config(run_dir, wrapper, "127.0.0.1", port)
    elif track == LSP:
        wrapper = _write_lsp_wrapper(run_dir, worktree)
        mcp_config = _write_lsp_mcp_config(run_dir, wrapper)

    prompt = build_nav_prompt(track, worktree, q, project)
    (run_dir / "prompt.txt").write_text(prompt)

    print(f"\n=== {q['id']} [{track}] type={q['type']} model={model} ===")
    result = run_copilot(
        prompt=prompt,
        model=model,
        cwd=worktree,
        log_dir=run_dir / "logs",
        mcp_config=mcp_config,
        wall_time=wall_time,
    )

    tokens = parse_tokens_from_logs(run_dir / "logs")
    result_ev = parse_result_event(result["stdout"])
    tool_total, tool_by_name = parse_tool_calls(result["stdout"])
    compliance = nudge_compliance(result["stdout"], track)
    agent_text = extract_agent_text(result["stdout"])
    (run_dir / "agent_text.txt").write_text(agent_text)

    pred, parse_error = parse_nav_answer(agent_text, q["type"])

    base = {
        "id": q["id"],
        "type": q["type"],
        "hop": q["hop"],
        "config": track,
        "model": model,
        "runner": RUNNER_VERSION,
        **(cap or {}),
    }

    if result.get("startup_failed"):
        print(f"[error] {q['id']} [{track}] copilot startup failed")
        return {
            **base,
            "outcome": "error",
            "error": (result.get("stderr") or "").strip()[:200],
            "completed": False,
        }

    scores = score_nav(q, pred)
    row = {
        **base,
        **scores,
        "parse_error": parse_error,
        "input_tokens": tokens["input_tokens"],
        "output_tokens": tokens["output_tokens"],
        "total_tokens": tokens["total_tokens"],
        "premium_requests": result_ev["premium_requests"],
        "tool_calls_total": tool_total,
        "tool_calls_by_name": tool_by_name,
        "nav_tool_calls": _nav_calls(tool_by_name, track),
        "first_tool": compliance["first_tool"],
        "timed_out": result["timed_out"],
        "wall_clock_sec": round(result["wall"], 2),
        "outcome": "answered",
        "completed": True,
    }
    _print_row(row)
    return row


def _print_row(row: dict) -> None:
    if row["type"] == "path":
        verdict = "OK" if row.get("path_correct") else "X"
        detail = (
            f"reach pred={row.get('pred_reachable')} gold={row.get('gold_reachable')} "
            f"ends={row.get('endpoints_correct')} {verdict}"
        )
    else:
        f = row.get("file_prf", {})
        qf = row.get("qual_prf", {})
        cap = row.get("graph_file_f1")
        detail = (
            f"fileF1={f.get('f1')} qualF1={qf.get('f1')} pred_n={row.get('pred_n')} "
            f"cap(graph_fileF1)={cap}"
        )
    print(
        f"[nav] {row['id']} [{row['config']}] {detail} "
        f"in={row['input_tokens']} out={row['output_tokens']} "
        f"navtools={row['nav_tool_calls']} tools={row['tool_calls_total']} "
        f"parse_err={row.get('parse_error')} wall={row['wall_clock_sec']}s"
    )


# ---------------------------------------------------------------------------
# Aggregate report
# ---------------------------------------------------------------------------


def _mean(xs: list[float]) -> float:
    return round(sum(xs) / len(xs), 4) if xs else 0.0


def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return round((s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2), 2)


def aggregate(rows: list[dict]) -> dict[str, Any]:
    report: dict[str, Any] = {}
    arms = sorted({r["config"] for r in rows if r.get("completed")})
    for arm in arms:
        ar = [r for r in rows if r["config"] == arm and r.get("completed")]
        per_type: dict[str, Any] = {}
        for typ in ("callers", "callees", "blast_radius", "path"):
            tr = [r for r in ar if r["type"] == typ]
            if not tr:
                continue
            if typ == "path":
                per_type[typ] = {
                    "n": len(tr),
                    "path_acc": _mean([1.0 if r.get("path_correct") else 0.0 for r in tr]),
                    "boolean_acc": _mean([1.0 if r.get("boolean_correct") else 0.0 for r in tr]),
                    "median_total_tokens": _median([r["total_tokens"] for r in tr]),
                    "median_nav_calls": _median([r["nav_tool_calls"] for r in tr]),
                }
            else:
                row = {
                    "n": len(tr),
                    "file_f1": _mean([r["file_prf"]["f1"] for r in tr]),
                    "qual_f1": _mean([r["qual_prf"]["f1"] for r in tr]),
                    "loose_qual_f1": _mean([r["loose_qual_prf"]["f1"] for r in tr]),
                    "file_recall": _mean([r["file_prf"]["recall"] for r in tr]),
                    "median_total_tokens": _median([r["total_tokens"] for r in tr]),
                    "median_nav_calls": _median([r["nav_tool_calls"] for r in tr]),
                }
                caps = [r["graph_file_f1"] for r in tr if r.get("graph_file_f1") is not None]
                if caps:
                    row["graph_file_f1_cap"] = _mean(caps)
                per_type[typ] = row
        multihop = [r for r in ar if r["hop"] == "multihop" and r["type"] != "path"]
        report[arm] = {
            "n": len(ar),
            "by_type": per_type,
            "median_total_tokens": _median([r["total_tokens"] for r in ar]),
            "median_input_tokens": _median([r["input_tokens"] for r in ar]),
            "median_output_tokens": _median([r["output_tokens"] for r in ar]),
            "median_premium": _median([r["premium_requests"] for r in ar]),
            "multihop_file_f1": _mean([r["file_prf"]["f1"] for r in multihop]) if multihop else None,
            "parse_errors": sum(1 for r in ar if r.get("parse_error")),
        }
    report["_paired"] = _paired_deltas(rows)
    return report


def _paired_deltas(rows: list[dict]) -> dict[str, Any]:
    """Per-question paired file-F1 (set types) and path_correct deltas with a
    bootstrap 90% CI — small-n honesty (rubber-duck #5)."""
    import random

    by_arm: dict[str, dict[str, float]] = {}
    for r in rows:
        if not r.get("completed"):
            continue
        if r["type"] == "path":
            val = 1.0 if r.get("path_correct") else 0.0
        else:
            val = r["file_prf"]["f1"]
        by_arm.setdefault(r["config"], {})[r["id"]] = val
    out: dict[str, Any] = {}
    arms = sorted(by_arm)
    if CODE_GRAPH not in arms:
        return out
    for other in [a for a in arms if a != CODE_GRAPH]:
        common = sorted(set(by_arm[CODE_GRAPH]) & set(by_arm[other]))
        diffs = [by_arm[CODE_GRAPH][i] - by_arm[other][i] for i in common]
        if not diffs:
            continue
        rng = random.Random(13)
        boot = []
        for _ in range(2000):
            sample = [diffs[rng.randrange(len(diffs))] for _ in diffs]
            boot.append(sum(sample) / len(sample))
        boot.sort()
        out[f"code_graph_minus_{other}"] = {
            "n_paired": len(diffs),
            "mean_delta": round(sum(diffs) / len(diffs), 4),
            "ci90": [round(boot[int(0.05 * len(boot))], 4), round(boot[int(0.95 * len(boot))], 4)],
            "wins": sum(1 for d in diffs if d > 1e-9),
            "losses": sum(1 for d in diffs if d < -1e-9),
            "ties": sum(1 for d in diffs if abs(d) <= 1e-9),
        }
    return out


def _print_report(report: dict) -> None:
    print("\n" + "=" * 78)
    print("MULTI-HOP NAV — PREMIUM AGENT ARM")
    print("=" * 78)
    for arm, a in report.items():
        if arm == "_paired":
            continue
        mh = a["multihop_file_f1"]
        print(f"\n### {arm}  (n={a['n']}, parse_errors={a['parse_errors']})")
        print(
            f"  median_tokens total={a['median_total_tokens']} "
            f"in={a['median_input_tokens']} out={a['median_output_tokens']}  "
            f"median_premium={a['median_premium']}  "
            f"multihop_file_f1={mh}"
        )
        for typ, t in a["by_type"].items():
            if typ == "path":
                print(
                    f"    {typ:<13} n={t['n']} path_acc={t['path_acc']} "
                    f"bool_acc={t['boolean_acc']} med_tok={t['median_total_tokens']} "
                    f"med_navcalls={t['median_nav_calls']}"
                )
            else:
                cap = t.get("graph_file_f1_cap")
                print(
                    f"    {typ:<13} n={t['n']} fileF1={t['file_f1']} qualF1={t['qual_f1']} "
                    f"looseQ={t['loose_qual_f1']} fileRec={t['file_recall']} "
                    f"med_tok={t['median_total_tokens']} med_navcalls={t['median_nav_calls']}"
                    + (f" [graph_cap_fileF1={cap}]" if cap is not None else "")
                )
    paired = report.get("_paired") or {}
    if paired:
        print("\n### paired deltas (code_graph minus other; file-F1 / path_correct)")
        for k, v in paired.items():
            print(
                f"    {k}: mean_delta={v['mean_delta']} ci90={v['ci90']} "
                f"W/L/T={v['wins']}/{v['losses']}/{v['ties']} (n={v['n_paired']})"
            )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_done(results_path: Path) -> set[tuple]:
    done: set[tuple] = set()
    if not results_path.exists():
        return done
    for line in results_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("completed") and r.get("runner") == RUNNER_VERSION:
            done.add((r["id"], r["config"], r.get("model", "")))
    return done


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Multi-hop nav premium agent arm.")
    p.add_argument("--questions", required=True)
    p.add_argument("--worktree", default=None,
                   help="repo cwd for all arms (default: questions JSON 'worktree')")
    p.add_argument("--project", default="mh_uxarray",
                   help="code_graph project name of the PRE-BUILT fixed graph")
    p.add_argument("--port", type=int, default=6380, help="FalkorDB port")
    p.add_argument("--model", default="claude-sonnet-4.6")
    p.add_argument("--arms", nargs="*", default=list(ARMS), choices=list(ARMS))
    p.add_argument("--types", nargs="*", default=None,
                   choices=["callers", "callees", "blast_radius", "path"])
    p.add_argument("--ids", nargs="*", default=None, help="restrict to these question ids")
    p.add_argument("--limit", type=int, default=None, help="first N questions (post-filter)")
    p.add_argument("--server-root", default=str(DEFAULT_MCP_SERVER_ROOT))
    p.add_argument("--gate", default="/tmp/ux_gate.json",
                   help="agentless gate output for per-question graph caps")
    p.add_argument("--seed", type=int, default=13, help="run-order shuffle seed")
    p.add_argument("--wall-time", type=float, default=900.0)
    p.add_argument("--out", default="/tmp/ux_nav_agent.json")
    p.add_argument("--results", default=None,
                   help="append-only jsonl for resume (default: <out>.jsonl)")
    p.add_argument("--no-resume", action="store_true")
    args = p.parse_args(argv)

    data = json.loads(Path(args.questions).read_text())
    worktree = Path(args.worktree or data["worktree"]).resolve()
    if not worktree.exists():
        raise SystemExit(f"worktree not found: {worktree}")

    qs = data["questions"]
    if args.types:
        qs = [q for q in qs if q["type"] in args.types]
    if args.ids:
        idset = set(args.ids)
        qs = [q for q in qs if q["id"] in idset]
    if args.limit:
        qs = qs[: args.limit]

    out_path = Path(args.out)
    out_dir = out_path.with_suffix("")
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = Path(args.results) if args.results else out_path.with_suffix(".jsonl")

    done = set() if args.no_resume else _load_done(results_path)
    server_root = Path(args.server_root)
    caps = _gate_caps(Path(args.gate) if args.gate else None)

    print(
        f"worktree={worktree}\nproject={args.project} port={args.port} "
        f"model={args.model}\narms={args.arms} questions={len(qs)} "
        f"caps_loaded={len(caps)} already_done={len(done)}"
    )

    rows: list[dict] = []
    if results_path.exists():
        for line in results_path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    # Randomize (question, arm) order with a fixed seed so provider-side prompt
    # caching / drift can't systematically favor whichever arm always runs first
    # (rubber-duck #7).
    import random

    worklist = [(q, arm) for q in qs for arm in args.arms]
    random.Random(args.seed).shuffle(worklist)

    for q, arm in worklist:
        key = (q["id"], arm, args.model)
        if key in done:
            continue
        row = run_one_nav(
            q,
            track=arm,
            model=args.model,
            worktree=worktree,
            project=args.project,
            port=args.port,
            server_root=server_root,
            out_dir=out_dir,
            wall_time=args.wall_time,
            cap=caps.get(q["id"]),
        )
        rows.append(row)
        with results_path.open("a") as f:
            f.write(json.dumps(row) + "\n")

    completed = [r for r in rows if r.get("completed")]
    report = aggregate(completed)
    _print_report(report)
    out_path.write_text(json.dumps(
        {
            "worktree": str(worktree),
            "project": args.project,
            "model": args.model,
            "n_rows": len(completed),
            "report": report,
            "rows": rows,
        },
        indent=2,
    ))
    print(f"\nwrote {out_path}  (jsonl: {results_path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
