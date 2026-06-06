"""Runtime NOISY negative-control injection for ``search_code`` results.

This module is the SINGLE source of truth for the adoption-calibration pilot's
NOISY arm (prereg §6): after the real graph result, append K deterministic
"distractor" files (verified-non-gold siblings, pre-computed offline into a
manifest) so the experiment can measure whether the agent KEEPS a plausible but
wrong graph-surfaced candidate (a false positive) or correctly DROPS it (a true
negative).

Design constraints (mirrors ``rel_explain`` and validated with rubber-duck):
  * The injection lives INSIDE the registered tool, before FastMCP serializes
    the return value, so distractors flow through the exact same schema and
    output path as real results (no JSON-RPC proxy, no registry surgery).
  * It is ENV-GATED and DEFAULT-OFF: with ``BENCH_NOISY_MANIFEST`` /
    ``BENCH_NOISY_TASK`` unset, ``maybe_inject`` is a no-op and ``search_code``
    output is byte-identical to production. Only the NOISY arm sets the env.
  * PURE core (``inject``) so the no-LLM dry-run / unit tests can exercise the
    real intervention against a canned result list with no FalkorDB, no agent.
  * Distractors are appended AFTER the real result and never duplicate a file
    already present, so they cannot displace a genuine hit.

Env contract (set by the bench runner only for the NOISY condition):
  * ``BENCH_NOISY_MANIFEST`` -- path to the JSON manifest produced by
    ``bench.analysis.adopt_controls.build_noisy_manifest`` (top-level
    ``{"k", "seed", "coverage", "manifest": {task -> {... "distractors": [...]}}}``).
  * ``BENCH_NOISY_TASK``     -- the task id key for THIS run's instance.
  * ``BENCH_NOISY_K``        -- optional override of how many distractors to
    append (default: the manifest's ``k``, else ``DEFAULT_K``).
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ENV_MANIFEST = "BENCH_NOISY_MANIFEST"
ENV_TASK = "BENCH_NOISY_TASK"
ENV_K = "BENCH_NOISY_K"

DEFAULT_K = 2

# Provenance marker stamped on every injected record so the offline diagnostic
# can distinguish a NOISY distractor from a genuine co-override sibling.
VIA_NOISY = "noisy_inject"


def build_distractor_record(file: str) -> dict[str, Any]:
    """A single injected distractor in the flat ``rank_kind:"related"`` schema.

    Mirrors the shape ``search_code`` already uses for flat-appended siblings so
    the agent and the offline scorer see a uniform candidate list. ``file_id`` is
    ``None`` (a distractor is identified by path, not a query-relevant node id).
    """
    return {
        "file": file,
        "file_id": None,
        "score": None,
        "name": None,
        "line": None,
        "label": "File",
        "rank_kind": "related",
        "confidence": "medium",
        "via": VIA_NOISY,
        "related_to": None,
        "shared_methods": [],
    }


def inject(
    out: list[dict[str, Any]],
    distractors: list[dict[str, Any]],
    k: int,
) -> list[dict[str, Any]]:
    """Append up to ``k`` distractor records to ``out`` (pure, in place).

    Skips any distractor whose ``file`` already appears in ``out`` (a real hit is
    never duplicated/displaced). Returns ``out`` for convenience.
    """
    if k <= 0 or not distractors:
        return out
    present = {r.get("file") for r in out}
    appended = 0
    for d in distractors:
        if appended >= k:
            break
        f = d.get("file")
        if not f or f in present:
            continue
        present.add(f)
        out.append(build_distractor_record(f))
        appended += 1
    return out


@lru_cache(maxsize=8)
def _load_manifest(path: str) -> dict[str, Any]:
    """Load + cache the manifest JSON (cache keyed by path string)."""
    return json.loads(Path(path).read_text())


def distractors_for_task(manifest: dict[str, Any], task: str) -> list[dict[str, Any]]:
    """The ``distractors`` list for ``task`` from a loaded manifest, or ``[]``."""
    entry = manifest.get("manifest", {}).get(task)
    if not entry:
        return []
    return entry.get("distractors", []) or []


def _resolve_k(manifest: dict[str, Any]) -> int:
    raw = os.getenv(ENV_K)
    if raw is not None and raw.strip():
        try:
            return max(0, int(raw))
        except ValueError:
            log.warning("noisy_inject: bad %s=%r, falling back to manifest k", ENV_K, raw)
    mk = manifest.get("k")
    if isinstance(mk, int) and mk >= 0:
        return mk
    return DEFAULT_K


def maybe_inject(out: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Env-gated entry point called by ``search_code`` before returning.

    No-op (byte-identical output) unless BOTH ``BENCH_NOISY_MANIFEST`` and
    ``BENCH_NOISY_TASK`` are set. A misconfiguration (missing file, unknown task,
    fewer than K distractors) is logged and otherwise tolerated so a NOISY run
    degrades to "fewer distractors" rather than crashing the agent mid-task.
    """
    manifest_path = os.getenv(ENV_MANIFEST)
    task = os.getenv(ENV_TASK)
    if not manifest_path or not task:
        return out
    try:
        manifest = _load_manifest(manifest_path)
    except (OSError, ValueError) as e:
        log.warning("noisy_inject: cannot load manifest %s: %s", manifest_path, e)
        return out
    distractors = distractors_for_task(manifest, task)
    if not distractors:
        log.warning("noisy_inject: no distractors for task %r in %s", task, manifest_path)
        return out
    k = _resolve_k(manifest)
    return inject(out, distractors, k)
