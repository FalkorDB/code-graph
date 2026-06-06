"""Factual relationship/provenance explanations for ``search_code`` results.

This module is the SINGLE source of truth for the optional, env-gated
``relationship_explanation`` / ``match_provenance`` strings attached to
``search_code`` output. It is deliberately PURE (no FastMCP, no graph, no I/O)
and dependency-free so that:

  * the production tool (``structural.py``) can call it at query time, and
  * the offline A/B "reader" harness (bench tree, a *different* worktree/venv)
    can import it and re-annotate captured ``search_code`` outputs with the
    EXACT same logic — guaranteeing the offline mechanism test exercises the
    real intervention, not a re-implementation that could drift.

Design constraints (validated with rubber-duck):
  * FACTUAL, not directive. Strings describe the STRUCTURAL relationship or the
    matched query provenance. They never tell the agent what to answer
    ("you should include this file"), which would overfit/game the benchmark.
  * Derived only from data already present in the result entry (``via``,
    ``shared_methods``, ``related_to``) or trivially verifiable against the
    query (token overlap with ``name``/``file``).
  * A length-matched, semantically EMPTY ``placebo`` is provided so the A/B can
    isolate "explanation content" from "extra prose / salience".

Modes (string, case-insensitive):
  * ``"off"``      -- no annotation (control arm; current production default).
  * ``"explain"``  -- attach the real factual explanation/provenance.
  * ``"placebo"``  -- attach a length-matched neutral filler (salience control).
"""

from __future__ import annotations

import re
from typing import Any, Optional

OFF = "off"
EXPLAIN = "explain"
PLACEBO = "placebo"
VALID_MODES = (OFF, EXPLAIN, PLACEBO)

# Field names attached to result entries.
RELATED_FIELD = "relationship_explanation"
DIRECT_FIELD = "match_provenance"

_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+")
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_MIN_TOK = 4  # ignore short/common tokens when reporting query provenance


def normalize_mode(value: Optional[str]) -> str:
    """Coerce an env value to a valid mode; unknown/empty -> ``off``."""
    if not value:
        return OFF
    v = str(value).strip().lower()
    if v in ("1", "true", "yes", "on"):
        return EXPLAIN
    if v in ("0", "false", "no"):
        return OFF
    return v if v in VALID_MODES else OFF


def _subtokens(ident: str) -> set[str]:
    out: set[str] = set()
    for part in re.split(r"[_\s]+", ident or ""):
        for m in _CAMEL_RE.findall(part):
            if m:
                out.add(m.lower())
    return out


def _query_tokens(query: str) -> set[str]:
    toks: set[str] = set()
    for w in _WORD_RE.findall(query or ""):
        toks |= _subtokens(w)
        toks.add(w.lower())
    return {t for t in toks if len(t) >= _MIN_TOK}


def _fmt_methods(methods: Any) -> str:
    if not methods:
        return ""
    if isinstance(methods, str):
        methods = [methods]
    parts = [f"`{m}`" for m in methods if m]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def related_explanation(entry: dict[str, Any], related_to: Optional[str]) -> Optional[str]:
    """Factual explanation of WHY a related file is coupled to ``related_to``.

    ``entry`` is a ``likely_related_files`` item or a flat ``rank_kind=related``
    object carrying ``via`` (co_override|shared_method) and ``shared_methods``.
    ``related_to`` is the primary (seed) file this sibling attaches to; for flat
    entries it is the entry's own ``related_to`` field.
    """
    via = entry.get("via")
    methods = _fmt_methods(entry.get("shared_methods"))
    seed = related_to or entry.get("related_to")
    seed_s = f"`{seed}`" if seed else "a top-ranked file"
    if via == "co_override":
        base = (
            f"Overrides the same base method {methods} as {seed_s}"
            if methods
            else f"Overrides the same base method as {seed_s}"
        )
        return (
            f"{base} (co-override sibling). Files that override a shared base "
            f"method are frequent co-edit candidates that a textual search misses."
        )
    if via == "shared_method":
        base = (
            f"Defines the same method name {methods} as {seed_s}"
            if methods
            else f"Defines a same-named method as {seed_s}"
        )
        return (
            f"{base} (shared-method sibling, often a co-change companion). "
            f"Not linked by a resolved inheritance edge, so a name lookup would "
            f"not connect them."
        )
    # Unknown channel: fall back to a minimal factual statement.
    if seed:
        return f"Structurally coupled to {seed_s} in the code graph."
    return None


def direct_provenance(entry: dict[str, Any], query: str) -> Optional[str]:
    """Honest provenance for a DIRECT (primary ranked) hit.

    Reports which query terms verifiably appear in the hit's representative
    symbol ``name`` or its ``file`` path. Makes no claim of relevance beyond the
    literal token overlap; when there is none, it states the ranking was driven
    by symbol/docstring relevance (BM25/centrality) rather than inventing a
    match. This keeps direct-hit annotations FACTUAL, not directive.
    """
    name = entry.get("name") or ""
    file = entry.get("file") or ""
    qtok = _query_tokens(query)
    if not qtok:
        return None
    name_hits = sorted(qtok & _subtokens(name))
    path_hits = sorted(qtok & _subtokens(file.replace("/", " ").replace(".", " ")))
    if name_hits:
        terms = _fmt_methods(name_hits)
        where = f"symbol `{name}`" if name else "a symbol in this file"
        return f"Query term {terms} appears in {where}."
    if path_hits:
        terms = _fmt_methods(path_hits)
        return f"Query term {terms} appears in the file path."
    return (
        "Ranked by symbol-name/docstring relevance to the query "
        "(no exact query term in the file path or representative symbol)."
    )


# ---------------------------------------------------------------------------
# Length-matched placebo (salience control)
# ---------------------------------------------------------------------------

# A neutral vocabulary with NO file names, symbol names, or structural-coupling
# terms. Used to build filler of comparable length to a real explanation so the
# A/B can attribute any adoption change to explanation CONTENT, not to the mere
# presence of extra prose near the entry.
_PLACEBO_WORDS = (
    "this entry is part of the indexed repository and was returned by the "
    "search operation along with other candidate entries for your review at "
    "this time as additional general information about the result listing here"
).split()


def placebo_for(real_text: Optional[str]) -> Optional[str]:
    """Return a neutral filler string of length comparable to ``real_text``."""
    if not real_text:
        return None
    target = len(real_text)
    words: list[str] = []
    n = 0
    i = 0
    while n < target:
        w = _PLACEBO_WORDS[i % len(_PLACEBO_WORDS)]
        words.append(w)
        n += len(w) + 1
        i += 1
    s = " ".join(words)
    return s[:target].rstrip()


# ---------------------------------------------------------------------------
# Top-level annotators (operate IN PLACE on a list of search_code result objs)
# ---------------------------------------------------------------------------


def annotate_results(results: list[dict[str, Any]], query: str, mode: str) -> list[dict[str, Any]]:
    """Attach explanation/provenance fields to a list of search_code objects.

    Mutates and returns ``results``. ``mode`` is one of ``VALID_MODES``. In
    ``placebo`` mode the SAME fields are attached but with length-matched
    neutral filler, so the two arms differ only in CONTENT, not in which entries
    carry a field or roughly how many tokens they add.
    """
    mode = normalize_mode(mode)
    if mode == OFF:
        return results
    explain = mode == EXPLAIN

    for prim in results:
        if not isinstance(prim, dict):
            continue
        is_related = prim.get("rank_kind") == "related"
        if is_related:
            real = related_explanation(prim, prim.get("related_to"))
            prim[RELATED_FIELD] = real if explain else placebo_for(real)
        else:
            real = direct_provenance(prim, query)
            if real is not None:
                prim[DIRECT_FIELD] = real if explain else placebo_for(real)
            for rel in prim.get("likely_related_files", []) or []:
                if isinstance(rel, dict):
                    r = related_explanation(rel, prim.get("file"))
                    rel[RELATED_FIELD] = r if explain else placebo_for(r)
    return results
