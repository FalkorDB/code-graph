"""Trajectory trace extractor for Copilot benchmark runs.

Each benchmark run persists the full Copilot event stream to
``<run_dir>/logs/stdout.jsonl``. The runner itself only derives scalar counts
from it. This module reconstructs the *decision loop* so we can analyse what
the agent did rather than guess:

    (tool_name, arguments)  ->  (success, result_content, size, empty?)
                            ->  (assistant reasoning/message that followed)

It emits, per run:
  * ``trace.jsonl`` -- one JSON object per tool step (machine-readable)
  * ``trace.md``    -- a readable timeline (human review)
  * a ``summary`` dict -- derived behaviour signals + per-file *attribution*
    (did a structural tool actually surface each correctly-predicted file, or
    did it come from the prompt / a builtin view-grep / the model's own prior?)

Standalone & post-hoc: it reads an existing ``run_dir`` (and the matching row
in ``results.jsonl`` for gold/pred), so it works on runs already on disk and
can also be wired into the runner for future runs.

Usage:
    python -m bench.analysis.trace <run_dir> [<run_dir> ...]
    python -m bench.analysis.trace --cache-dir bench/cache/phaseB-levers \
        --model claude-sonnet-4.6 [--mode localize]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Iterable, Optional

# Tool-name classification --------------------------------------------------
# MCP code-graph tools surface as ``code-graph-<tool>``; the LSP arm (when
# built) will surface as ``lsp-<tool>``. Builtin agent tools are everything
# else the CLI ships (view/str_replace/grep/glob/bash/report_intent/...).
GRAPH_PREFIX = "code-graph"
LSP_PREFIX = "lsp"
BUILTIN_READERS = {"view", "read", "cat", "grep", "glob", "search", "ripgrep"}
LOCALIZE_SENTINEL = "FINAL_LOCALIZATION_JSON:"

# Result payloads can be huge (whole file slices). Cap what we inline into the
# readable/structured trace; keep enough to see what the agent actually saw.
_RESULT_CHARS_MD = 800
_RESULT_CHARS_JSONL = 4000
_ARGS_CHARS = 600
_REACTION_CHARS_MD = 600


def _tool_kind(name: str) -> str:
    if not name:
        return "unknown"
    if name.startswith(GRAPH_PREFIX):
        return "graph"
    if name.startswith(LSP_PREFIX):
        return "lsp"
    base = name.split("-")[-1].lower()
    if base in BUILTIN_READERS:
        return "builtin_reader"
    return "builtin_other"


def _est_tokens(text: str) -> int:
    """Cheap token estimate (~4 chars/token) for result-size accounting."""
    return (len(text) + 3) // 4 if text else 0


def _load_events(stdout_path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not stdout_path.exists():
        return events
    with stdout_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _result_to_text(result: Any) -> str:
    """Flatten a tool.execution_complete ``result`` into displayable text."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ("content", "detailedContent"):
            val = result.get(key)
            if isinstance(val, str) and val.strip():
                return val
        # Fall back to a compact JSON dump of the whole result object.
        try:
            return json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(result)
    return str(result)


def _is_empty_result(text: str) -> bool:
    t = text.strip()
    return t in ("", "{}", "[]", '{"result":[]}', '{"result": []}', "null")


def build_steps(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reconstruct ordered tool steps, each paired with the agent's reaction.

    A *step* = one ``tool.execution_start`` matched (by toolCallId) to its
    ``tool.execution_complete``, annotated with the assistant reasoning/message
    text that streamed *after* that completion and *before* the next tool
    started (the agent's reaction to the tool's output).
    """
    # Index completions by toolCallId for O(1) pairing.
    completions: dict[str, dict[str, Any]] = {}
    for ev in events:
        if ev.get("type") == "tool.execution_complete":
            d = ev.get("data", {})
            cid = d.get("toolCallId")
            if cid:
                completions[cid] = d

    steps: list[dict[str, Any]] = []
    # First pass: collect starts in order with their event index.
    starts: list[tuple[int, dict[str, Any]]] = []
    for i, ev in enumerate(events):
        if ev.get("type") == "tool.execution_start":
            starts.append((i, ev))

    for step_idx, (ev_idx, ev) in enumerate(starts):
        d = ev.get("data", {})
        cid = d.get("toolCallId")
        name = d.get("toolName") or d.get("name") or "unknown"
        comp = completions.get(cid, {})
        result_text = _result_to_text(comp.get("result"))

        # Thoughts BEFORE this tool call = assistant reasoning/message that
        # streamed AFTER the previous tool start (or stream start for step 0)
        # and BEFORE this tool's start. This is the chain-of-thought that led
        # to this action. Within one assistant turn the model emits one
        # reasoning + one message block then fires N tool starts, so the
        # before-block attaches to the FIRST tool of the turn; siblings get
        # empty before-blocks (honest — the thought happened once). The `turn`
        # field lets a reader regroup siblings.
        prev_ev_idx = starts[step_idx - 1][0] if step_idx > 0 else -1
        thinking_parts: list[str] = []
        narration_parts: list[str] = []
        for j in range(prev_ev_idx + 1, ev_idx):
            ej = events[j]
            etype = ej.get("type")
            content = ej.get("data", {}).get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            if etype == "assistant.reasoning":
                thinking_parts.append(content.strip())
            elif etype == "assistant.message":
                narration_parts.append(content.strip())
        thinking_before = "\n".join(thinking_parts)
        narration_before = "\n".join(narration_parts)

        # Reaction = assistant message/reasoning text between this step's event
        # index and the next step's event index (or end of stream). Kept for
        # backward-compat with programmatic consumers; equals the NEXT step's
        # before-block, so render_md uses the before-blocks instead.
        next_ev_idx = starts[step_idx + 1][0] if step_idx + 1 < len(starts) else len(events)
        reaction_parts: list[str] = []
        for j in range(ev_idx + 1, next_ev_idx):
            ej = events[j]
            if ej.get("type") in ("assistant.message", "assistant.reasoning"):
                content = ej.get("data", {}).get("content")
                if isinstance(content, str) and content.strip():
                    reaction_parts.append(content.strip())
        reaction = "\n".join(reaction_parts)

        steps.append({
            "step": step_idx,
            "turn": d.get("turnId"),
            "tool": name,
            "kind": _tool_kind(name),
            "mcp_server": d.get("mcpServerName"),
            "mcp_tool": d.get("mcpToolName"),
            "arguments": d.get("arguments"),
            "success": comp.get("success"),
            "result_text": result_text,
            "result_chars": len(result_text),
            "result_tokens_est": _est_tokens(result_text),
            "empty": _is_empty_result(result_text),
            "thinking_before": thinking_before,
            "narration_before": narration_before,
            "reaction": reaction,
        })
    return steps


def final_blocks(events: list[dict[str, Any]]) -> dict[str, str]:
    """Trailing thinking + narration AFTER the last tool call.

    This is the agent's closing reasoning and final answer (e.g. the
    ``FINAL_LOCALIZATION_JSON:`` payload) which streams after the last tool
    completes and would otherwise be dropped by the per-step windows.
    """
    last_start = -1
    for i, ev in enumerate(events):
        if ev.get("type") == "tool.execution_start":
            last_start = i
    thinking_parts: list[str] = []
    narration_parts: list[str] = []
    for j in range(last_start + 1, len(events)):
        ej = events[j]
        etype = ej.get("type")
        content = ej.get("data", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        if etype == "assistant.reasoning":
            thinking_parts.append(content.strip())
        elif etype == "assistant.message":
            narration_parts.append(content.strip())
    return {
        "thinking": "\n".join(thinking_parts),
        "narration": "\n".join(narration_parts),
    }


def _mentions(text: str, path: str) -> bool:
    """Does ``text`` reference this file by full relative path or basename?"""
    if not text or not path:
        return False
    base = os.path.basename(path)
    return (path in text) or (bool(base) and base in text)


def _iter_json_objects(text: str) -> Iterable[dict[str, Any]]:
    """Yield every top-level JSON object embedded in ``text``.

    Structural ``search_code`` results are a stream of concatenated JSON
    objects (NDJSON-like), not a single array, so a plain ``json.loads`` fails
    with "Extra data". This walks the string with ``raw_decode`` and yields
    each object it can decode, tolerating non-JSON noise between them.
    """
    if not text:
        return
    dec = json.JSONDecoder()
    i, n = 0, len(text)
    while i < n:
        # Skip to the next plausible object/array start.
        while i < n and text[i] not in "{[":
            i += 1
        if i >= n:
            return
        try:
            obj, end = dec.raw_decode(text, i)
        except json.JSONDecodeError:
            i += 1
            continue
        if isinstance(obj, dict):
            yield obj
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    yield item
        i = end


def _structural_surface_map(text: str) -> dict[str, str]:
    """Map every file path surfaced in a structural result to HOW it surfaced.

    Returns ``{path_or_basename: via}`` where ``via`` is ``"direct"`` for a
    genuinely ranked hit (a top-level object carrying a numeric ``score``), or
    the edge label (e.g. ``"co_override"``) for a file that only appears as a
    ``likely_related_files`` sibling. The tool also re-emits edge siblings as
    trailing *score-less* top-level objects; those are NOT counted as direct
    ranked hits. ``"direct"`` always wins when a file surfaces both ways. Both
    the full path and its basename are indexed so attribution can match either.
    """
    edges: dict[str, str] = {}
    direct: set[str] = set()
    for obj in _iter_json_objects(text):
        related = obj.get("likely_related_files")
        if isinstance(related, list):
            for rel in related:
                if isinstance(rel, dict):
                    path = rel.get("file")
                    if isinstance(path, str) and path:
                        for key in (path, os.path.basename(path)):
                            edges.setdefault(key, str(rel.get("via") or "edge"))
        path = obj.get("file")
        # Only a numeric-scored top-level object is a true ranked ("direct") hit;
        # score-less entries are the re-emitted edge siblings.
        if isinstance(path, str) and path and isinstance(obj.get("score"), (int, float)):
            for key in (path, os.path.basename(path)):
                direct.add(key)

    surfaces: dict[str, str] = dict(edges)
    for key in direct:
        surfaces[key] = "direct"  # direct ranked hit always wins
    return surfaces


def attribute_files(
    pred_files: list[str],
    gold_files: list[str],
    steps: list[dict[str, Any]],
    prompt_text: str,
) -> list[dict[str, Any]]:
    """For each predicted file, decide WHERE it first surfaced.

    Source precedence (earliest evidence wins):
      * ``prompt``          -- named in the problem statement (leak / given)
      * ``graph`` / ``lsp`` -- first appeared in a structural tool's result
      * ``builtin_reader``  -- first appeared via view/grep/glob output
      * ``model``           -- never seen in prompt or any tool result; the
                               agent produced it from its own prior knowledge

    This is the anti-guessing metric: it tells us whether the structural tool
    *actually contributed* the correct answer or was decorative.
    """
    gold_set = {g for g in gold_files}
    attded: list[dict[str, Any]] = []
    for p in pred_files:
        is_hit = p in gold_set
        source = "model"
        source_step: Optional[int] = None
        source_tool: Optional[str] = None
        via: Optional[str] = None
        if _mentions(prompt_text, p):
            source = "prompt"
        else:
            for s in steps:
                # Only successful, non-empty tool results count as a "surface".
                if s.get("success") is False or s.get("empty"):
                    continue
                if _mentions(s.get("result_text", ""), p):
                    kind = s["kind"]
                    if kind in ("graph", "lsp"):
                        source = kind
                        # Distinguish a direct ranked hit from an edge-derived
                        # one (e.g. co_override) so the structural mechanism that
                        # actually surfaced the file gets explicit credit.
                        surfaces = _structural_surface_map(s.get("result_text", ""))
                        via = surfaces.get(p) or surfaces.get(os.path.basename(p)) or "direct"
                    elif kind == "builtin_reader":
                        source = "builtin_reader"
                    else:
                        source = "builtin_other"
                    source_step = s["step"]
                    source_tool = s["tool"]
                    break
        attded.append({
            "file": p,
            "is_gold_hit": is_hit,
            "source": source,
            "source_step": source_step,
            "source_tool": source_tool,
            "via": via,
        })
    return attded


def summarize(steps: list[dict[str, Any]], attribution: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive behaviour signals from the reconstructed steps."""
    by_name: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    empty = 0
    errors = 0
    seen_calls: set[str] = set()
    redundant = 0
    structural_first: Optional[bool] = None
    first_tool: Optional[str] = None

    for s in steps:
        name = s["tool"]
        by_name[name] = by_name.get(name, 0) + 1
        by_kind[s["kind"]] = by_kind.get(s["kind"], 0) + 1
        if s.get("empty"):
            empty += 1
        if s.get("success") is False:
            errors += 1
        sig = f"{name}:{json.dumps(s.get('arguments'), sort_keys=True)}"
        if sig in seen_calls:
            redundant += 1
        else:
            seen_calls.add(sig)
        if first_tool is None:
            first_tool = name
            structural_first = s["kind"] in ("graph", "lsp")

    structural_calls = by_kind.get("graph", 0) + by_kind.get("lsp", 0)

    # Attribution rollup over correctly-predicted (gold-hit) files only.
    hit_sources: dict[str, int] = {}
    hit_via: dict[str, int] = {}
    for a in attribution:
        if a["is_gold_hit"]:
            hit_sources[a["source"]] = hit_sources.get(a["source"], 0) + 1
            if a["source"] in ("graph", "lsp"):
                key = f"{a['source']}:{a.get('via') or 'direct'}"
                hit_via[key] = hit_via.get(key, 0) + 1

    cost_without_benefit = _cost_without_benefit(steps, attribution)

    return {
        "tool_calls_total": len(steps),
        "tool_calls_by_name": by_name,
        "tool_calls_by_kind": by_kind,
        "structural_calls": structural_calls,
        "structural_adopted": structural_calls > 0,
        "first_tool": first_tool,
        "structural_first": structural_first,
        "empty_result_count": empty,
        "tool_error_count": errors,
        "redundant_call_count": redundant,
        "gold_hit_source_counts": hit_sources,
        "gold_hit_via_counts": hit_via,
        "cost_without_benefit": cost_without_benefit,
    }


# Tool kinds that are "under test" — the navigation tools whose value we are
# trying to measure. Builtin grep/view/glob are the baseline the agent always
# has, so they are not charged as cost-without-benefit here.
_TESTED_KINDS = ("graph", "lsp")


def _cost_without_benefit(
    steps: list[dict[str, Any]],
    attribution: list[dict[str, Any]],
) -> dict[str, Any]:
    """Tokens the tool-under-test injected into context that did NOT surface a
    correctly-predicted (gold) file.

    A structural call "benefits" the run iff it is the step that first surfaced
    a gold-hit predicted file (per ``attribute_files`` precedence). Every other
    structural call — empty results, redundant queries, verbose dumps the agent
    never used, or surfaces of non-gold files — is charged as wasted context
    cost. This is the sharp "cost without benefit" indicator: high wasted_tokens
    with benefited=False means the tool spent context and contributed nothing to
    the answer.
    """
    beneficial_steps = {
        a["source_step"]
        for a in attribution
        if a.get("is_gold_hit")
        and a.get("source") in _TESTED_KINDS
        and a.get("source_step") is not None
    }
    by_kind: dict[str, dict[str, int]] = {}
    total_tokens = 0
    beneficial_tokens = 0
    wasted_tokens = 0
    wasted_calls = 0
    for s in steps:
        kind = s.get("kind")
        if kind not in _TESTED_KINDS:
            continue
        tok = int(s.get("result_tokens_est") or 0)
        slot = by_kind.setdefault(
            kind, {"calls": 0, "tokens": 0, "wasted_calls": 0, "wasted_tokens": 0}
        )
        slot["calls"] += 1
        slot["tokens"] += tok
        total_tokens += tok
        if s.get("step") in beneficial_steps:
            beneficial_tokens += tok
        else:
            wasted_tokens += tok
            wasted_calls += 1
            slot["wasted_calls"] += 1
            slot["wasted_tokens"] += tok
    return {
        "tested_kinds": [k for k in _TESTED_KINDS if k in by_kind],
        "structural_result_tokens": total_tokens,
        "beneficial_tokens": beneficial_tokens,
        "wasted_tokens": wasted_tokens,
        "wasted_calls": wasted_calls,
        "wasted_fraction": round(wasted_tokens / total_tokens, 4) if total_tokens else None,
        "benefited": bool(beneficial_steps),
        "by_kind": by_kind,
    }


def _fmt_block(text: str, cap: int) -> str:
    if not text:
        return "(none)"
    t = text.strip()
    if len(t) > cap:
        t = t[:cap] + f"\n… [+{len(t) - cap} chars truncated]"
    return t


def render_md(meta: dict[str, Any], steps: list[dict[str, Any]],
              attribution: list[dict[str, Any]], summary: dict[str, Any],
              final: Optional[dict[str, str]] = None) -> str:
    lines: list[str] = []
    lines.append(f"# Trace — {meta.get('task_id')} [{meta.get('config')}] ({meta.get('prompt_mode')})")
    lines.append("")
    lines.append(f"- model: {meta.get('model')}  mode: {meta.get('mode')}  run_idx: {meta.get('run_idx')}")
    lines.append(f"- outcome: {meta.get('outcome')}  recall: {meta.get('file_recall')}  "
                 f"precision: {meta.get('file_precision')}  acc@1: {meta.get('acc_at_1')}  mrr: {meta.get('file_mrr')}")
    _rt = meta.get("reasoning_tokens")
    _rt_str = f" (of which reasoning: {_rt})" if _rt not in (None, 0) else ""
    lines.append(f"- tokens: in={meta.get('input_tokens')} out={meta.get('output_tokens')}{_rt_str} "
                 f"total={meta.get('total_tokens')}  turns≈{meta.get('usage_blocks')}  wall={meta.get('wall_clock_sec')}s")
    lines.append(f"- gold: {meta.get('gold_files')}")
    lines.append(f"- pred: {meta.get('pred_files')}")
    lines.append("")
    lines.append("## Behaviour summary")
    lines.append(f"- tool calls: {summary['tool_calls_total']}  by kind: {summary['tool_calls_by_kind']}")
    lines.append(f"- structural adopted: {summary['structural_adopted']}  "
                 f"structural calls: {summary['structural_calls']}  first tool: {summary['first_tool']}")
    lines.append(f"- empty results: {summary['empty_result_count']}  errors: {summary['tool_error_count']}  "
                 f"redundant calls: {summary['redundant_call_count']}")
    lines.append(f"- **gold-hit attribution**: {summary['gold_hit_source_counts'] or '(no gold hits)'}")
    via_counts = summary.get("gold_hit_via_counts")
    if via_counts:
        lines.append(f"- **structural gold-hits by surface**: {via_counts} "
                     f"(direct = ranked hit; co_override/other = edge-derived)")
    cwb = summary.get("cost_without_benefit")
    if cwb and cwb.get("structural_result_tokens"):
        frac = cwb.get("wasted_fraction")
        frac_str = f"{frac:.0%}" if frac is not None else "n/a"
        benefit_str = "yes" if cwb.get("benefited") else "**NO — tool contributed nothing**"
        lines.append(
            f"- **cost without benefit**: wasted ~{cwb['wasted_tokens']} of "
            f"{cwb['structural_result_tokens']} structural tokens ({frac_str}) "
            f"across {cwb['wasted_calls']} call(s); benefited: {benefit_str}"
        )
        for kind, slot in (cwb.get("by_kind") or {}).items():
            lines.append(
                f"    - {kind}: {slot['wasted_calls']}/{slot['calls']} calls wasted, "
                f"~{slot['wasted_tokens']}/{slot['tokens']} tok wasted"
            )
    lines.append("")
    lines.append("## Predicted-file attribution")
    for a in attribution:
        tag = "✓gold" if a["is_gold_hit"] else " miss"
        where = a["source"]
        if a["source"] in ("graph", "lsp") and a.get("via"):
            where += f"/{a['via']}"
        if a["source_tool"]:
            where += f" (step {a['source_step']} {a['source_tool']})"
        lines.append(f"- [{tag}] {a['file']}  ←  {where}")
    lines.append("")
    lines.append("## Step-by-step trajectory")
    lines.append("")
    lines.append("_Each step shows the agent's thinking and narration **before** the "
                 "tool call (the reasoning that led to the action), then the call and "
                 "its result._")
    lines.append("")
    for s in steps:
        args = _fmt_block(json.dumps(s.get("arguments"), ensure_ascii=False), _ARGS_CHARS)
        flags = []
        if s.get("empty"):
            flags.append("EMPTY")
        if s.get("success") is False:
            flags.append("ERROR")
        flag_str = (" [" + ",".join(flags) + "]") if flags else ""
        lines.append(f"### Step {s['step']} · turn {s['turn']} · {s['tool']} ({s['kind']}){flag_str}")
        thinking = s.get("thinking_before", "")
        narration = s.get("narration_before", "")
        if thinking:
            lines.append(f"**thinking (before call):** {_fmt_block(thinking, _REACTION_CHARS_MD)}")
        if narration:
            lines.append(f"**narration (before call):** {_fmt_block(narration, _REACTION_CHARS_MD)}")
        lines.append(f"**call:** `{args}`")
        lines.append(f"**tool returned** ({s['result_chars']} chars, ~{s['result_tokens_est']} tok):")
        lines.append("```")
        lines.append(_fmt_block(s.get("result_text", ""), _RESULT_CHARS_MD))
        lines.append("```")
        lines.append("")
    if final and (final.get("thinking") or final.get("narration")):
        lines.append("## Final (after last tool call)")
        if final.get("thinking"):
            lines.append(f"**thinking:** {_fmt_block(final['thinking'], _RESULT_CHARS_MD)}")
        if final.get("narration"):
            lines.append(f"**narration / answer:** {_fmt_block(final['narration'], _RESULT_CHARS_MD)}")
        lines.append("")
    return "\n".join(lines)


def extract_run(run_dir: Path, row: Optional[dict[str, Any]] = None,
                write: bool = True) -> dict[str, Any]:
    """Extract trace + summary for a single run directory.

    ``row`` is the matching results.jsonl record (for gold/pred/tokens). If
    omitted, gold/pred attribution falls back to empty lists but the
    trajectory + behaviour summary are still produced.
    """
    stdout_path = run_dir / "logs" / "stdout.jsonl"
    prompt_path = run_dir / "prompt.txt"
    events = _load_events(stdout_path)
    steps = build_steps(events)
    final = final_blocks(events)
    prompt_text = prompt_path.read_text() if prompt_path.exists() else ""

    row = row or {}
    pred_files = row.get("pred_files") or []
    gold_files = row.get("gold_files") or []
    attribution = attribute_files(pred_files, gold_files, steps, prompt_text)
    summary = summarize(steps, attribution)

    meta = {
        "task_id": row.get("task_id"),
        "config": row.get("config"),
        "model": row.get("model"),
        "mode": row.get("mode"),
        "prompt_mode": row.get("prompt_mode"),
        "run_idx": row.get("run_idx"),
        "outcome": row.get("outcome"),
        "file_recall": row.get("file_recall"),
        "file_precision": row.get("file_precision"),
        "acc_at_1": row.get("acc_at_1"),
        "file_mrr": row.get("file_mrr"),
        "input_tokens": row.get("input_tokens"),
        "output_tokens": row.get("output_tokens"),
        "reasoning_tokens": row.get("reasoning_tokens"),
        "total_tokens": row.get("total_tokens"),
        "usage_blocks": row.get("usage_blocks"),
        "wall_clock_sec": row.get("wall_clock_sec"),
        "gold_files": gold_files,
        "pred_files": pred_files,
    }

    if write:
        with (run_dir / "trace.jsonl").open("w") as f:
            f.write(json.dumps({"_meta": meta, "_summary": summary,
                                "_attribution": attribution, "_final": final}) + "\n")
            for s in steps:
                rec = dict(s)
                # Cap inline result text in the structured file too.
                rt = rec.get("result_text", "")
                if len(rt) > _RESULT_CHARS_JSONL:
                    rec["result_text"] = rt[:_RESULT_CHARS_JSONL]
                    rec["result_truncated"] = True
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        (run_dir / "trace.md").write_text(render_md(meta, steps, attribution, summary, final))

    return {"meta": meta, "summary": summary, "attribution": attribution,
            "steps": steps, "final": final, "run_dir": str(run_dir)}


# Discovery -----------------------------------------------------------------


def _load_rows(results_path: Path) -> dict[tuple, dict[str, Any]]:
    """Index results.jsonl rows by (task_id, config, prompt_mode, run_idx)."""
    rows: dict[tuple, dict[str, Any]] = {}
    if not results_path.exists():
        return rows
    for line in results_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = (r.get("task_id"), r.get("config"), r.get("prompt_mode", "neutral"),
               int(r.get("run_idx", 0)))
        rows[key] = r
    return rows


def iter_run_dirs(cache_dir: Path, model: str, mode: Optional[str] = None) -> Iterable[Path]:
    """Yield every run dir under ``cache_dir/runs/model[/mode]``."""
    base = cache_dir / "runs" / model
    if not base.exists():
        return
    modes = [mode] if mode else [p.name for p in base.iterdir() if p.is_dir()]
    for m in modes:
        mdir = base / m
        if not mdir.is_dir():
            continue
        for prompt_mode_dir in mdir.iterdir():
            if not prompt_mode_dir.is_dir():
                continue
            for track_dir in prompt_mode_dir.iterdir():
                if not track_dir.is_dir():
                    continue
                for inst_dir in track_dir.iterdir():
                    if (inst_dir / "logs" / "stdout.jsonl").exists():
                        yield inst_dir


def _row_for_run(run_dir: Path, rows: dict[tuple, dict[str, Any]]) -> Optional[dict[str, Any]]:
    # Path layout: .../runs/<model>/<mode>/<prompt_mode>/<track>/<task_id>
    parts = run_dir.parts
    try:
        task_id = parts[-1]
        track = parts[-2]
        prompt_mode = parts[-3]
    except IndexError:
        return None
    for run_idx in range(0, 8):
        key = (task_id, track, prompt_mode, run_idx)
        if key in rows:
            return rows[key]
    # Fallback: match on task_id+config only.
    for (t, c, _pm, _ri), r in rows.items():
        if t == task_id and c == track:
            return r
    return None


def _auto_results_path(run_dir: Path) -> Optional[Path]:
    """Locate the results.jsonl for a positional run dir.

    Layout is ``<cache>/runs/<model>/<mode>/<prompt_mode>/<track>/<task_id>``
    and results live at ``<cache>/<model>/results.jsonl``. Walk up to the
    ``runs`` anchor, recover ``<cache>`` and ``<model>``, and return that path
    if it exists. This means a bare ``trace.py <run_dir>`` still joins gold/pred
    (otherwise attribution runs blind and falsely reports "contributed nothing").
    """
    parts = run_dir.parts
    if "runs" not in parts:
        return None
    ri = len(parts) - 1 - parts[::-1].index("runs")
    if ri + 1 >= len(parts):
        return None
    cache_dir = Path(*parts[:ri]) if ri > 0 else Path(parts[0])
    model = parts[ri + 1]
    candidate = cache_dir / model / "results.jsonl"
    return candidate if candidate.exists() else None


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Extract decision-loop traces from benchmark runs.")
    p.add_argument("run_dirs", nargs="*", help="explicit run dir(s) to extract")
    p.add_argument("--cache-dir", help="extract every run under this cache dir")
    p.add_argument("--model", default="claude-sonnet-4.6")
    p.add_argument("--mode", default=None, help="restrict to one mode (e.g. localize)")
    p.add_argument("--results", default=None, help="results.jsonl (default: <cache>/<model>/results.jsonl)")
    args = p.parse_args(argv)

    targets: list[tuple[Path, Optional[dict[str, Any]]]] = []
    if args.cache_dir:
        cache_dir = Path(args.cache_dir).resolve()
        results_path = Path(args.results) if args.results else cache_dir / args.model / "results.jsonl"
        rows = _load_rows(results_path)
        for rd in iter_run_dirs(cache_dir, args.model, args.mode):
            targets.append((rd, _row_for_run(rd, rows)))
    for rd in args.run_dirs:
        rdp = Path(rd).resolve()
        row = None
        results_path = Path(args.results) if args.results else _auto_results_path(rdp)
        if results_path:
            row = _row_for_run(rdp, _load_rows(results_path))
        targets.append((rdp, row))

    if not targets:
        print("no run dirs found")
        return 1

    print(f"extracting {len(targets)} run(s)…")
    for rd, row in targets:
        out = extract_run(rd, row=row, write=True)
        s = out["summary"]
        m = out["meta"]
        print(f"  {m.get('task_id')} [{m.get('config')}/{m.get('prompt_mode')}] "
              f"recall={m.get('file_recall')} tools={s['tool_calls_total']} "
              f"kinds={s['tool_calls_by_kind']} empty={s['empty_result_count']} "
              f"err={s['tool_error_count']} hit_src={s['gold_hit_source_counts']} "
              f"-> {rd}/trace.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
