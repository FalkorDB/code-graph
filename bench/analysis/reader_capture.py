"""Capture verbatim ``search_code`` calls (query + full result objects) per run.

This is the Stage-A "reader experiment" capture layer. Unlike
``exposure_adoption.surfaced_files`` (which flattens to a ``{file: rank}`` map),
here we keep the FULL, ORDERED, UNTRUNCATED result objects exactly as the agent
saw them, grouped per ``search_code`` call, together with the ``query`` argument
the agent passed. The reader harness re-annotates these captured objects via
``rel_explain.annotate_results`` (the EXACT production builder) so the offline
A/B exercises the real intervention, not a re-implementation.

Join rule (same as exposure_adoption): in ``stdout.jsonl`` join
``tool.execution_start`` -> ``tool.execution_complete`` by ``toolCallId``. The
untruncated payload is under ``result.contents`` (a list, one clean JSON object
per text entry); fall back to ``result.content`` only when ``contents`` is
absent (single-result case).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _parse_result_objs(res: dict) -> list[dict]:
    """Parse the list of primary result objects from a tool result payload."""
    items = res.get("contents")
    if not isinstance(items, list):
        c = res.get("content")
        items = c if isinstance(c, list) else [c]
    out: list[dict] = []
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
                out.append(prim)
    return out


def capture_search_calls(stdout_path: Path) -> list[dict[str, Any]]:
    """Return ordered ``[{query, results:[...]}]`` for every search_code call.

    ``results`` are the verbatim primary objects (with their nested
    ``likely_related_files``) the agent received for that call.
    """
    starts: dict[str, dict] = {}
    calls: list[dict[str, Any]] = []
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
            name = d.get("toolName") or d.get("mcpToolName") or ""
            if "search_code" in name:
                starts[d.get("toolCallId")] = d
        elif t == "tool.execution_complete":
            start = starts.get(d.get("toolCallId"))
            if start is None:
                continue
            query = (start.get("arguments") or {}).get("query") or ""
            results = _parse_result_objs(d.get("result") or {})
            calls.append({
                "tool_call_id": d.get("toolCallId"),
                "query": query,
                "results": results,
            })
    return calls
