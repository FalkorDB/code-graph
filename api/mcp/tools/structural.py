"""Structural MCP tools (T4-T8).

These tools wrap the existing ``Project`` / ``Graph`` / ``AsyncGraphQuery``
operations so MCP-capable agents (Claude Code, Cursor, Copilot, Cline)
can drive code-graph over the standard stdio transport.

Conventions shared by all tools in this module:

* Every tool accepts an optional ``branch`` so the agent can scope queries
  to a specific per-branch graph (see T17, issue #651). When omitted the
  branch is either auto-detected from a local checkout (``index_repo``)
  or defaults to ``_default``.
* Long-running synchronous operations are pushed into a thread via
  ``asyncio.get_running_loop().run_in_executor`` so the MCP event loop
  stays responsive.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import re
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..server import app


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hybrid ranking (search_code Step 3) — tunable weights
# ---------------------------------------------------------------------------
# Repo-wide file relevance = weighted sum of normalized component scores minus
# a path penalty. Each component is min-max normalized across files so the
# weights are directly comparable. Tune these after the smoke test.
_HYBRID_W_NAME = 2.0   # symbol name == a query identifier (exact)
_HYBRID_W_PATH = 1.5   # query tokens present in the file's path
_HYBRID_W_BM25 = 1.5   # BM25 over file body (symbol names + docstrings + path)
_HYBRID_W_CENT = 0.5   # log(1 + cross-file in-degree): structural centrality
_HYBRID_W_PEN = 1.0    # penalty for test/legacy/vendored/etc. paths
_HYBRID_BODY_TOKEN_CAP = 4000
_HYBRID_MIN_IDENT_LEN = 4
_HYBRID_BM25_K1 = 1.5
_HYBRID_BM25_B = 0.75

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+")
_PENALTY_RE = re.compile(
    r"(^|/)(tests?|testing|conftest|migrations?|legacy|vendor|vendored|"
    r"third_party|__pycache__|examples?|docs?|benchmarks?)(/|$)|_test\.py$|(^|/)test_",
    re.IGNORECASE,
)


def _subtokens(ident: str) -> list[str]:
    """Split an identifier into snake/camel sub-tokens (lowercased) plus itself."""
    out: list[str] = []
    for part in ident.split("_"):
        if not part:
            continue
        out.extend(m.group(0).lower() for m in _CAMEL_RE.finditer(part))
    out.append(ident.lower())
    return [t for t in out if t]


def _tokenize(text: str) -> list[str]:
    toks: list[str] = []
    for m in _WORD_RE.finditer(text or ""):
        toks.extend(_subtokens(m.group(0)))
    return toks


def _issue_identifiers(text: str) -> set[str]:
    """Candidate symbol names mentioned in the query (backticked or code-shaped)."""
    cands: set[str] = set()
    for m in re.finditer(r"`([^`]+)`", text or ""):
        for ident in _WORD_RE.findall(m.group(1)):
            if len(ident) >= _HYBRID_MIN_IDENT_LEN:
                cands.add(ident.lower())
    for ident in _WORD_RE.findall(text or ""):
        if len(ident) >= _HYBRID_MIN_IDENT_LEN and (
            "_" in ident or re.search(r"[a-z][A-Z]", ident) or ident[0].isupper()
        ):
            cands.add(ident.lower())
    return cands


def _minmax(d: dict[str, float]) -> dict[str, float]:
    if not d:
        return {}
    vals = list(d.values())
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-12:
        return {k: 0.0 for k in d}
    return {k: (v - lo) / (hi - lo) for k, v in d.items()}


def _rep_key(d: dict[str, Any]) -> tuple:
    """Stable ordering key for a file's representative-symbol candidate.

    Lower is better: exact query-id match first, then lowest ``src_start``,
    then ``name`` then ``src_end`` as deterministic tie-breakers so the chosen
    representative never depends on FalkorDB row order (even when ``src_start``
    ties or is missing).
    """
    return (
        0 if d.get("exact") else 1,
        d["src_start"] if d.get("src_start") is not None else math.inf,
        d.get("name") or "",
        d["src_end"] if d.get("src_end") is not None else math.inf,
    )


def _bm25(query_tokens: set[str], files: list[str],
          tokmap: dict[str, list[str]]) -> dict[str, float]:
    docs = [tokmap.get(f, []) for f in files]
    n = len(docs)
    if n == 0:
        return {}
    df: Counter = Counter()
    for d in docs:
        for t in set(d):
            df[t] += 1
    avgdl = (sum(len(d) for d in docs) / n) or 1.0
    idf = {t: math.log(1 + (n - k + 0.5) / (k + 0.5)) for t, k in df.items()}
    k1, b = _HYBRID_BM25_K1, _HYBRID_BM25_B
    out: dict[str, float] = {}
    for f, d in zip(files, docs):
        if not d:
            out[f] = 0.0
            continue
        tf = Counter(d)
        dl = len(d)
        s = 0.0
        for t in query_tokens:
            freq = tf.get(t)
            if not freq:
                continue
            s += idf.get(t, 0.0) * (freq * (k1 + 1)) / (
                freq + k1 * (1 - b + b * dl / avgdl)
            )
        out[f] = s
    return out


async def _hybrid_rank(g, query: str, project: Optional[str]) -> list[dict[str, Any]]:
    """Rank every indexed file by relevance to a free-text ``query``.

    Runs three aggregate Cypher reads (files, symbols, cross-file edge degree),
    scores files with the weighted hybrid above, and returns an ordered list of
    ``{abs_path, file, score, name, src_start, src_end}`` (best representative
    symbol per file, used for the snippet). Pure read; no graph mutation.
    """
    files, comps, rep, abs_of, file_id_of = await _hybrid_components(g, query, project)
    scored = _hybrid_score(files, comps, rep, abs_of, file_id_of)
    # Relevance floor: a query with no lexical overlap (e.g. a nonsense token)
    # would otherwise be ranked purely by query-independent centrality and
    # return noise. Drop files with no lexical signal so such queries yield [].
    return [r for r in scored if r.get("lex", 0.0) > 0]


async def _hybrid_components(g, query: str, project: Optional[str]):
    """Build the per-file, weight-independent components for ``query``.

    Returns ``(files, comps, rep, abs_of, file_id_of)`` where ``comps[f]`` holds
    the min-max-normalized ``name``/``path``/``bm25``/``cent`` scores plus the
    ``pen`` penalty, and ``file_id_of[f]`` is the File node id (handle the agent
    feeds to ``get_file_neighbors``). Separated from weighting so weight sweeps
    reuse the exact same normalized inputs as the live ranker.

    The expensive, query-INDEPENDENT half (three full-graph reads + tokenization)
    is built once by :func:`_build_corpus` and cached per ``(graph, project)``;
    only the cheap per-query overlay (:func:`_overlay`) runs on every call. See
    the corpus-cache block below for the latency rationale and invalidation.
    """
    corpus = await _get_corpus(g, project)
    return _overlay(corpus, query)


# ---------------------------------------------------------------------------
# Corpus cache (search_code hot path)
# ---------------------------------------------------------------------------
# ``search_code`` is the agent's most-called tool. Its ranker used to run three
# full-graph Cypher reads (every File, every Function/Class incl. ``n.doc``,
# every cross-file edge) and rebuild the BM25 corpus in Python on EVERY call.
# Measured latency scales ~linearly with graph size (77ms @2.3K nodes, 320ms
# @12K, ~1s extrapolated to a 41K-symbol repo), so on large repos that read +
# rebuild dominated harness wall-time (PR #701 review).
#
# Everything :func:`_build_corpus` produces is query-INDEPENDENT, so we cache it
# per ``(graph_name, project)`` and let :func:`_overlay` apply the cheap
# per-query scoring. Invalidation is two-layered:
#   * Explicit: ``reset_corpus_cache(graph_name)`` from ``index_repo`` after a
#     (re)index -- covers the in-process writer.
#   * Implicit: a ``(node_count, edge_count, commit)`` signature probe on every
#     hit (~1ms; FalkorDB ``count()`` is O(1) metadata, the commit marker is a
#     single Redis HGET). Covers cross-process mutation -- notably the web API's
#     ``/api/switch_commit``, which rewrites the Redis commit marker even when
#     node/edge counts are preserved. A rebuild whose graph mutates mid-build,
#     or that races an explicit reset, is detected (pre/post sig + generation
#     check) and served WITHOUT being cached, so a torn snapshot never persists.


@dataclass
class _Corpus:
    """Cached, query-independent search corpus for one ``(graph, project)``."""

    files: list[str]
    abs_of: dict[str, str]
    file_id_of: dict[str, Any]
    pathtok: dict[str, list[str]]
    bodytok: dict[str, list[str]]
    # name-bearing symbols per file: (name, name_lower, src_start, src_end).
    sym_by_file: dict[str, list[tuple[str, str, Any, Any]]]
    n_cent: dict[str, float]  # min-max centrality (query-independent)
    sig: tuple = field(default_factory=tuple)


_CORPUS_CACHE: "OrderedDict[tuple, _Corpus]" = OrderedDict()
_CORPUS_LOCKS: dict[tuple, asyncio.Lock] = {}
_CORPUS_GEN: dict[str, int] = defaultdict(int)
_CORPUS_META_LOCK = asyncio.Lock()  # guards lazy per-key lock creation
_REDIS_MARKER_CLIENT: Any = None  # lazily created, reused (connection pool)


def _corpus_cache_max() -> int:
    """Max number of corpora to retain (LRU). Each holds a full token corpus."""
    try:
        return max(1, int(os.getenv("CODE_GRAPH_SEARCH_CACHE_MAX", "8")))
    except ValueError:
        return 8


def _commit_marker(project: Optional[str], branch: Optional[str]) -> Optional[str]:
    """Best-effort, quiet read of the recorded commit for ``(project, branch)``.

    Folded into the corpus signature so a cross-process ``switch_commit`` /
    reindex (which rewrites the Redis commit marker) invalidates the cache even
    when node/edge counts happen to be preserved. Any failure -> ``None`` (the
    signature degrades to counts-only and never raises into ``search_code``).
    Reads Redis directly rather than via ``get_repo_commit`` so a missing marker
    (non-git folder) doesn't log a warning on every probe.
    """
    global _REDIS_MARKER_CLIENT
    if not project:
        return None
    try:
        from api.info import _repo_info_key, get_redis_connection

        if _REDIS_MARKER_CLIENT is None:
            _REDIS_MARKER_CLIENT = get_redis_connection()
        return _REDIS_MARKER_CLIENT.hget(_repo_info_key(project, branch), "commit")
    except Exception:
        return None


async def _graph_sig(g, project: Optional[str]) -> tuple:
    """Cheap (~1ms) cache-validity signature for the graph behind ``g``.

    On any probe failure returns a never-equal sentinel so the caller rebuilds
    (degrading to the always-fresh status quo) rather than serving a stale hit.
    """
    try:
        n = (await g._query("MATCH (n) RETURN count(n)")).result_set[0][0]
        e = (await g._query("MATCH ()-[r]->() RETURN count(r)")).result_set[0][0]
    except Exception:
        return (None, None, object())
    commit = _commit_marker(project, getattr(g, "branch", None))
    return (int(n or 0), int(e or 0), commit)


async def _corpus_lock(key: tuple) -> asyncio.Lock:
    async with _CORPUS_META_LOCK:
        lock = _CORPUS_LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _CORPUS_LOCKS[key] = lock
        return lock


def reset_corpus_cache(graph_name: Optional[str] = None) -> None:
    """Invalidate cached search corpora.

    Called by ``index_repo`` after a (re)index so the next ``search_code``
    rebuilds. ``graph_name`` ``None`` clears everything; otherwise clears
    entries for that graph identity. Bumps a per-graph generation counter so a
    rebuild that started before the reset won't store its now-stale corpus.
    """
    if graph_name is None:
        _CORPUS_CACHE.clear()
        for gname in list(_CORPUS_GEN.keys()):
            _CORPUS_GEN[gname] += 1
        return
    for key in [k for k in _CORPUS_CACHE if k[0] == graph_name]:
        del _CORPUS_CACHE[key]
    _CORPUS_GEN[graph_name] += 1


async def _get_corpus(g, project: Optional[str]) -> _Corpus:
    """Return a cached corpus for ``(g, project)`` or build (and maybe cache) one."""
    key = (g.name, project)
    sig = await _graph_sig(g, project)
    ent = _CORPUS_CACHE.get(key)
    if ent is not None and ent.sig == sig:
        _CORPUS_CACHE.move_to_end(key)
        return ent

    lock = await _corpus_lock(key)
    async with lock:
        # Re-check: another coroutine may have rebuilt while we waited.
        sig_before = await _graph_sig(g, project)
        ent = _CORPUS_CACHE.get(key)
        if ent is not None and ent.sig == sig_before:
            _CORPUS_CACHE.move_to_end(key)
            return ent

        gen_before = _CORPUS_GEN[g.name]
        corpus = await _build_corpus(g, project)
        sig_after = await _graph_sig(g, project)
        corpus.sig = sig_after

        # Only cache a corpus that is internally consistent (the graph did not
        # change across the reads) and was not invalidated by a reset mid-build.
        stable = sig_after == sig_before and _CORPUS_GEN[g.name] == gen_before
        if stable:
            _CORPUS_CACHE[key] = corpus
            _CORPUS_CACHE.move_to_end(key)
            while len(_CORPUS_CACHE) > _corpus_cache_max():
                _CORPUS_CACHE.popitem(last=False)
        return corpus


async def _build_corpus(g, project: Optional[str]) -> _Corpus:
    """Run the three graph reads + tokenization (the query-independent half).

    Mirrors the original ``_hybrid_components`` read/build logic exactly, minus
    the query-dependent ``name_exact``/``rep`` selection (moved to
    :func:`_overlay`). ``bodytok`` (path + symbol-name subtokens + capped doc
    tokens) and ``centrality`` are query-independent and built identically here.
    """
    def rel(p: Optional[str]) -> str:
        return _relativize(p, project) if p else ""

    pathtok: dict[str, list[str]] = {}
    bodytok: dict[str, list[str]] = defaultdict(list)
    abs_of: dict[str, str] = {}
    file_id_of: dict[str, Any] = {}
    sym_by_file: dict[str, list[tuple[str, str, Any, Any]]] = defaultdict(list)

    files_res = await g._query("MATCH (f:File) RETURN f.path, ID(f)")
    for row in files_res.result_set:
        ap = row[0]
        if not ap:
            continue
        rp = rel(ap)
        abs_of[rp] = ap
        file_id_of[rp] = row[1]
        pt = _tokenize(rp.replace("/", " "))
        pathtok[rp] = pt
        bodytok[rp].extend(pt)

    sym_res = await g._query(
        "MATCH (n) WHERE n:Function OR n:Class "
        "RETURN n.name, n.path, n.doc, n.src_start, n.src_end"
    )
    body_used: Counter = Counter()
    for name, path, doc, start, end in sym_res.result_set:
        if not path:
            continue
        rp = rel(path)
        # Rank only over real ``File`` nodes; symbols whose containing file was
        # not emitted as a File node would otherwise inflate the BM25 corpus and
        # skew min-max normalization.
        if rp not in abs_of:
            continue
        if name:
            bodytok[rp].extend(_subtokens(name))
            # Record name-bearing symbols so _overlay can recompute name_exact
            # and the representative symbol against the (query-dependent) ids.
            sym_by_file[rp].append((name, name.lower(), start, end))
        if doc and body_used[rp] < _HYBRID_BODY_TOKEN_CAP:
            toks = _tokenize(doc)[: _HYBRID_BODY_TOKEN_CAP - body_used[rp]]
            bodytok[rp].extend(toks)
            body_used[rp] += len(toks)

    deg_res = await g._query(
        "MATCH (a)-[:CALLS|IMPORTS|EXTENDS|OVERRIDES]->(b) "
        "WHERE a.path IS NOT NULL AND b.path IS NOT NULL AND a.path <> b.path "
        "RETURN b.path AS p, count(*) AS deg"
    )
    centrality: dict[str, float] = defaultdict(float)
    for bpath, deg in deg_res.result_set:
        centrality[rel(bpath)] += math.log1p(int(deg or 0))

    files = sorted(abs_of)
    n_cent = (
        _minmax({f: centrality.get(f, 0.0) for f in files}) if files else {}
    )

    return _Corpus(
        files=files,
        abs_of=dict(abs_of),
        file_id_of=dict(file_id_of),
        pathtok=dict(pathtok),
        bodytok=dict(bodytok),
        sym_by_file=dict(sym_by_file),
        n_cent=n_cent,
    )


def _overlay(corpus: _Corpus, query: str):
    """Apply the cheap, query-dependent scoring over a cached corpus.

    Reproduces the original ``_hybrid_components`` output exactly: name-exact
    counts and the representative symbol come from ``corpus.sym_by_file`` (the
    ``_rep_key`` ordering is row-order independent), BM25 and path overlap run
    over the cached corpus, and the ``n_name`` normalization preserves the
    original ``name_exact if name_exact else zeros`` quirk.
    """
    files = corpus.files
    if not files:
        return [], {}, {}, {}, {}

    qtok = set(_tokenize(query))
    qids = _issue_identifiers(query)

    name_exact: dict[str, float] = defaultdict(float)
    rep: dict[str, dict[str, Any]] = {}
    for f, syms in corpus.sym_by_file.items():
        best: Optional[dict[str, Any]] = None
        cnt = 0.0
        for (name, name_lower, start, end) in syms:
            is_exact = name_lower in qids
            if is_exact:
                cnt += 1.0
            cand = {"name": name, "src_start": start, "src_end": end,
                    "exact": is_exact}
            if best is None or _rep_key(cand) < _rep_key(best):
                best = cand
        if cnt:
            name_exact[f] = cnt
        if best is not None:
            rep[f] = best

    path_overlap = {
        f: float(len(qtok & set(corpus.pathtok.get(f, [])))) for f in files
    }
    raw_bm25 = _bm25(qtok, files, corpus.bodytok)
    n_name = _minmax(name_exact if name_exact else {f: 0.0 for f in files})
    n_path = _minmax(path_overlap)
    n_bm25 = _minmax(raw_bm25)
    n_cent = corpus.n_cent

    comps: dict[str, dict[str, float]] = {}
    for f in files:
        comps[f] = {
            "name": n_name.get(f, 0.0),
            "path": n_path.get(f, 0.0),
            "bm25": n_bm25.get(f, 0.0),
            "cent": n_cent.get(f, 0.0),
            "pen": _HYBRID_W_PEN if _PENALTY_RE.search(f) else 0.0,
            # Raw (un-normalized) query-dependent signal. A file with zero
            # lexical overlap (name/path/body) is not relevant to the query --
            # only query-independent centrality could rank it -- so search_code
            # drops it rather than returning noise for an unmatched query.
            "lex": (name_exact.get(f, 0.0)
                    + path_overlap.get(f, 0.0)
                    + raw_bm25.get(f, 0.0)),
        }

    return files, comps, rep, corpus.abs_of, corpus.file_id_of


def _hybrid_score(
    files: list[str],
    comps: dict[str, dict[str, float]],
    rep: dict[str, dict[str, Any]],
    abs_of: dict[str, str],
    file_id_of: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Apply the hybrid weights to pre-normalized per-file components.

    Split out from ``_hybrid_rank`` so the weighting can be exercised
    independently of the (expensive) graph reads and normalization.
    """
    file_id_of = file_id_of or {}
    scored: list[dict[str, Any]] = []
    for f in files:
        c = comps[f]
        score = (
            _HYBRID_W_NAME * c["name"]
            + _HYBRID_W_PATH * c["path"]
            + _HYBRID_W_BM25 * c["bm25"]
            + _HYBRID_W_CENT * c["cent"]
            - c["pen"]
        )
        r = rep.get(f, {})
        scored.append({
            "abs_path": abs_of[f],
            "file": f,
            "file_id": file_id_of.get(f),
            "score": round(score, 4),
            "name": r.get("name"),
            "src_start": r.get("src_start"),
            "src_end": r.get("src_end"),
            "lex": c.get("lex", 0.0),
        })
    scored.sort(key=lambda d: -d["score"])
    return scored


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _looks_like_url(spec: str) -> bool:
    """Return True for HTTP(S) / git URLs, False for local paths."""
    return spec.startswith(("http://", "https://", "git@", "ssh://", "git://"))


def _count_nodes(graph) -> int:
    """Total node count for the graph.

    Counts every node generically (``MATCH (n)``) rather than summing a
    fixed label list, so non-Python repos -- whose analyzers emit Method,
    Interface, Enum, Constructor, ... nodes -- aren't under-reported. This
    mirrors :func:`_count_edges`, which already counts edges generically.
    """
    try:
        rows = graph.g.query("MATCH (n) RETURN count(n) AS c").result_set
        return int(rows[0][0]) if rows else 0
    except Exception:
        return 0


def _languages_detected(graph) -> list[str]:
    """Best-effort enumeration of distinct ``File.ext`` values.

    Returns a sorted list of extension strings (without the leading dot).
    Empty when no files were indexed.
    """
    try:
        rows = graph.g.query(
            "MATCH (f:File) RETURN DISTINCT f.ext AS ext"
        ).result_set
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("languages_detected query failed: %s", e)
        return []
    seen: set[str] = set()
    for row in rows or []:
        ext = (row[0] or "").lstrip(".")
        if ext:
            seen.add(ext)
    return sorted(seen)


def _count_edges(graph) -> int:
    try:
        rows = graph.g.query("MATCH ()-[r]->() RETURN count(r) AS c").result_set
        return int(rows[0][0]) if rows else 0
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# T4 — index_repo
# ---------------------------------------------------------------------------


@app.tool(
    name="index_repo",
    description=(
        "Index a code repository into code-graph for subsequent navigation. "
        "Accepts a local path or an http(s) git URL. When `branch` is "
        "omitted, auto-detects the current branch from the local checkout "
        "(defaults to '_default' for non-git folders). Returns the indexed "
        "graph's node/edge counts, detected languages, and the (project, "
        "branch) identity callers should pass to other code-graph tools."
    ),
)
async def index_repo(
    path_or_url: str,
    branch: Optional[str] = None,
    incremental: bool = True,  # accepted now, fully honored once T18 lands
    ignore: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Implementation for the ``index_repo`` MCP tool.

    Args:
        path_or_url: Filesystem path to a local repository **or** a clonable
            http(s) git URL (``https://host/org/repo.git``). SSH/scp specs
            (``git@host:org/repo.git``, ``ssh://...``) are not supported by
            the cloner -- clone such repos locally and pass the checkout path
            instead.
        branch: Branch identity for the indexed graph. When ``None``:
            auto-detect from the checkout via ``git rev-parse --abbrev-ref
            HEAD``; falls back to ``_default`` if not a git checkout.
        incremental: Accepted for forward-compatibility with T18; the
            current path always performs a full reindex and ignores this
            flag (the response ``mode`` is always ``"full"``).
        ignore: List of relative paths to skip during analysis.
    """

    from api.project import Project, detect_branch

    if ignore is None:
        ignore = []

    loop = asyncio.get_running_loop()

    def _do_index() -> dict[str, Any]:
        if _looks_like_url(path_or_url):
            # Project.from_git_repository validates with validators.url(),
            # which only accepts http(s) URLs -- scp-style (git@host:...) and
            # ssh:// specs would raise a confusing "invalid url". Reject them
            # up front with an actionable message instead. (Silently rewriting
            # them to https would change auth semantics for private repos.)
            if not path_or_url.startswith(("http://", "https://")):
                raise ValueError(
                    "index_repo only supports http(s) git URLs, got "
                    f"{path_or_url!r}. For SSH/scp specs, clone the repository "
                    "locally and pass the checkout path instead."
                )
            project = Project.from_git_repository(path_or_url, branch=branch)
        else:
            local_path = Path(path_or_url).expanduser().resolve()
            if not local_path.exists():
                raise ValueError(f"path does not exist: {local_path}")

            # Reject paths outside the allow-list when one is configured.
            allowed_root = os.getenv("ALLOWED_ANALYSIS_DIR")
            if allowed_root:
                allowed = Path(allowed_root).expanduser().resolve()
                try:
                    local_path.relative_to(allowed)
                except ValueError as e:
                    raise ValueError(
                        f"path {local_path} is outside ALLOWED_ANALYSIS_DIR={allowed}"
                    ) from e

            # Use Project for git-repo paths so commit metadata is saved,
            # otherwise drive SourceAnalyzer directly so non-git folders work.
            if (local_path / ".git").is_dir():
                try:
                    project = Project.from_local_repository(local_path, branch=branch)
                except IndexError:
                    # from_local_repository reads remotes[0].url, which raises
                    # IndexError for a git repo with no configured remote.
                    # Index it anyway, just without url/repo-info metadata.
                    project = Project(
                        local_path.name, local_path, url=None, branch=branch
                    )
            else:
                # Synthesize a Project-like object so the return shape is uniform.
                from api.analyzers.source_analyzer import SourceAnalyzer
                from api.graph import Graph

                detected = branch if branch is not None else detect_branch(local_path)
                graph = Graph(local_path.name, branch=detected)
                analyzer = SourceAnalyzer()
                analyzer.analyze_local_folder(str(local_path), graph, ignore)

                class _Synth:  # tiny shim to mirror Project's surface
                    name = local_path.name

                    def __init__(self, g, b):
                        self.graph = g
                        self.branch = b

                return _payload(_Synth(graph, detected))

        project.analyze_sources(ignore)
        return _payload(project)

    def _payload(project) -> dict[str, Any]:
        g = project.graph
        return {
            "project_name": project.name,
            "branch": getattr(project, "branch", None),
            "graph_name": g.name,
            "num_nodes": _count_nodes(g),
            "num_edges": _count_edges(g),
            "languages_detected": _languages_detected(g),
            # T18 will flip this to "incremental" when only changed files
            # were re-analyzed.
            "mode": "full",
        }

    result = await loop.run_in_executor(None, _do_index)
    # A (re)index invalidates any cached search corpus for this graph so the
    # next search_code rebuilds against the new contents (covers the in-process
    # writer; cross-process mutation is caught by the signature probe).
    reset_corpus_cache(result.get("graph_name"))
    return result


# ---------------------------------------------------------------------------
# T5 — get_callers / get_callees / get_dependencies
# ---------------------------------------------------------------------------


def _project_arg(project: str, branch: Optional[str]):
    """Return an :class:`AsyncGraphQuery` for ``(project, branch)``."""
    from api.graph import AsyncGraphQuery

    return AsyncGraphQuery(project, branch=branch)


def _relativize(path: Optional[str], rel_to: Optional[str]) -> Optional[str]:
    """Strip the indexing-root prefix so file paths are repo-relative.

    Stored paths are absolute and include the worktree root whose final
    segment equals the ``project`` identifier
    (e.g. ``/<root>/<project>/pkg/mod.py``). We strip up to and including the
    FIRST ``/<project>/`` occurrence so the result is the repo-relative path.
    ``find`` (first match) is deliberate: a nested directory may legitimately
    repeat the project name and must be preserved in the relative path.

    Absolute worktree prefixes are ~150 chars/row of pure noise that the agent
    re-reads on every cached turn; relativizing is the cheapest token win.
    """
    if not path or not rel_to:
        return path
    marker = f"/{rel_to}/"
    idx = path.find(marker)
    if idx == -1:
        return path
    return path[idx + len(marker):]


def _raw_name(n: Any) -> Optional[str]:
    """Extract the ``name`` property from a Node or already-encoded dict."""
    if hasattr(n, "properties"):
        return (n.properties or {}).get("name")
    return (dict(n).get("properties") or {}).get("name")


# Snippet windows (lines) attached to results so the agent can judge relevance
# without a follow-up full-file ``view`` — the dominant token cost. Neighbor
# tools return small, high-relevance result sets, so they carry a real window;
# search_code can return many name matches, so it carries only a signature.
NEIGHBOR_SNIPPET_LINES = 12
SEARCH_SNIPPET_LINES = 2
_SNIPPET_LINE_CHARS = 200
"""Per-line char cap so a single minified line cannot blow up the payload."""


def _is_within(path: str, root: str) -> bool:
    """True when ``path`` is ``root`` or lives inside it (both absolute)."""
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        # Different drives / mixed absolute-relative -> not contained.
        return False


def _snippet_path_allowed(abs_path: str, project: Optional[str]) -> bool:
    """Symlink-safe guard for snippet file reads.

    Snippet paths come from indexed ``File.path`` values, i.e. ultimately from
    repo content. A malicious repo could store (or symlink) a path resolving
    outside the indexed worktree, turning a snippet read into an arbitrary
    host-file read. We resolve the real path (following symlinks) and require it
    to live inside an allowed root: ``ALLOWED_ANALYSIS_DIR`` when set, and/or the
    indexed repo root derived from the first ``/<project>/`` marker in the
    stored path. When neither root is derivable (no allow-list and no project
    marker in the path) we preserve the legacy read rather than block a
    legitimate snippet.
    """
    try:
        real = os.path.realpath(abs_path)
    except OSError:
        return False

    roots: list[str] = []
    allowed_env = os.getenv("ALLOWED_ANALYSIS_DIR")
    if allowed_env:
        try:
            roots.append(os.path.realpath(os.path.expanduser(allowed_env)))
        except OSError:
            pass
    if project:
        marker = f"/{project}/"
        idx = abs_path.find(marker)
        if idx != -1:
            try:
                roots.append(os.path.realpath(abs_path[: idx + len(marker)]))
            except OSError:
                pass

    if not roots:
        return True
    return any(_is_within(real, root) for root in roots)


def _read_snippet(
    abs_path: Optional[str],
    src_start: Any,
    src_end: Any,
    max_lines: int,
    project: Optional[str] = None,
) -> Optional[str]:
    """Read up to ``max_lines`` leading source lines for an entity from disk.

    Paths and line numbers are stored on nodes but the source text is not, so
    we read the file lazily. Returns the entity's leading lines (signature plus
    the start of the body) joined by newlines, or ``None`` when the file/line
    info is missing or unreadable. Each line is capped at
    ``_SNIPPET_LINE_CHARS``. Carrying a snippet in the result lets a single
    tool call replace a follow-up ``view`` of a large file.

    ``project`` (the indexed repo identifier) enables a symlink-safe allow-list
    check via :func:`_snippet_path_allowed` so a snippet read can't escape the
    indexed worktree.
    """
    if not abs_path or max_lines <= 0:
        return None
    if not _snippet_path_allowed(abs_path, project):
        return None
    try:
        start = int(src_start)
    except (TypeError, ValueError):
        return None
    if start < 1:
        return None
    try:
        end = int(src_end)
    except (TypeError, ValueError):
        end = start
    # Read a slightly larger window than ``max_lines`` (bounded by the entity's
    # own extent) so leading blank / decorator-only lines can be skipped without
    # starving the substantive output.
    hard_end = end if end >= start else start
    read_until = min(hard_end, start + max_lines + 5)
    raw_lines: list[str] = []
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
            for i, raw in enumerate(fh, start=1):
                if i < start:
                    continue
                if i > read_until:
                    break
                raw_lines.append(raw.rstrip("\n"))
    except OSError:
        return None
    # Skip leading blank / decorator-only lines so the limited window lands on
    # the substantive signature + body rather than being wasted on a blank line
    # or a bare ``@decorator``.
    while raw_lines and (
        not raw_lines[0].strip() or raw_lines[0].lstrip().startswith("@")
    ):
        raw_lines.pop(0)
    lines = [ln[:_SNIPPET_LINE_CHARS] for ln in raw_lines[:max_lines]]
    if not lines:
        return None
    return "\n".join(lines)


def _node_summary(
    n: Any,
    rel_to: Optional[str] = None,
    snippet_lines: int = 0,
    with_label: bool = True,
) -> dict[str, Any]:
    """Normalize a FalkorDB Node (or already-encoded dict) to a flat payload.

    ``encode_node`` returns ``{id, labels, properties: {...}}`` because Node
    properties live on a nested attribute. Agents want a flat record. We keep
    the single meaningful ``label`` (File, Class, Function — not the fulltext
    marker ``Searchable``) for ``search_code`` (File-vs-Function disambiguation)
    and for ``find_path`` (a path is bare nodes with no per-hop relation, so the
    label is the only type signal). Single-hop neighbor results omit it via
    ``with_label`` since the relation already implies the node type.

    When ``rel_to`` is given (the project/worktree identifier), ``file`` is
    relativized to drop the absolute worktree prefix.
    """
    if hasattr(n, "properties"):
        props = dict(n.properties or {})
        labels = list(n.labels or [])
        node_id = getattr(n, "id", None)
    else:
        d = dict(n)
        props = dict(d.get("properties") or {})
        labels = list(d.get("labels") or [])
        node_id = d.get("id")

    label = next((lbl for lbl in labels if lbl != "Searchable"), None)
    summary: dict[str, Any] = {
        "id": node_id,
        "name": props.get("name"),
    }
    if with_label:
        summary["label"] = label
    summary["file"] = _relativize(props.get("path"), rel_to)
    summary["line"] = props.get("src_start")
    if snippet_lines > 0:
        snip = _read_snippet(
            props.get("path"),
            props.get("src_start"),
            props.get("src_end"),
            snippet_lines,
            project=rel_to,
        )
        if snip:
            summary["snippet"] = snip
    return summary


# Relationship-type names are graph labels (SCREAMING_SNAKE_CASE, e.g. CALLS,
# IMPORTS, DEFINES). FalkorDB cannot parameterize relationship types, so any
# ``rel`` interpolated into Cypher must be validated against this pattern to
# prevent Cypher injection via agent-controlled input.
_REL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_relation(rel: str) -> str:
    """Return ``rel`` if it is a safe relationship-type name, else raise.

    Guards the relationship types that are string-interpolated into Cypher
    (``-[e:{rel}]->``) — parameter binding is not available for relation
    types in FalkorDB.
    """
    if not isinstance(rel, str) or not _REL_NAME_RE.match(rel):
        raise ValueError(f"invalid relation type: {rel!r}")
    return rel


def _coerce_node_id(symbol_id: Any) -> int:
    """Accept int or stringified int; raise ValueError otherwise.

    The MCP wire format is JSON; agents sometimes hand back the id as a
    string. Be permissive on input, strict on type after parsing.
    """
    if isinstance(symbol_id, bool):  # bool is an int subclass; reject loudly
        raise ValueError(f"symbol_id must be an integer, got bool: {symbol_id!r}")
    if isinstance(symbol_id, int):
        return symbol_id
    if isinstance(symbol_id, str) and symbol_id.lstrip("-").isdigit():
        return int(symbol_id)
    raise ValueError(f"symbol_id must be an integer id, got: {symbol_id!r}")


async def _neighbors_payload(
    project: str,
    branch: Optional[str],
    symbol_id: Any,
    rel: str,
    direction: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Shared implementation for caller/callee/dependency tools.

    ``direction`` is ``IN`` (incoming edges, e.g. callers) or ``OUT``
    (outgoing edges, e.g. callees). When ``IN`` we run the inverse Cypher
    ``(neighbor)-[:rel]->(target)``; ``AsyncGraphQuery.get_neighbors`` only
    walks outgoing edges, so we inline the Cypher here for symmetry.
    """
    node_id = _coerce_node_id(symbol_id)
    rel = _validate_relation(rel)
    g = _project_arg(project, branch)
    try:
        if direction == "OUT":
            q = (
                f"MATCH (n)-[e:{rel}]->(dest) "
                f"WHERE ID(n) = $sid "
                f"RETURN dest, type(e) AS rel "
                f"LIMIT $limit"
            )
        elif direction == "IN":
            q = (
                f"MATCH (src)-[e:{rel}]->(n) "
                f"WHERE ID(n) = $sid "
                f"RETURN src AS dest, type(e) AS rel "
                f"LIMIT $limit"
            )
        else:
            raise ValueError(f"direction must be IN or OUT, got: {direction!r}")

        res = await g._query(q, {"sid": node_id, "limit": int(limit)})
        out: list[dict[str, Any]] = []
        for row in res.result_set:
            entry = _node_summary(
                row[0],
                rel_to=project,
                snippet_lines=NEIGHBOR_SNIPPET_LINES,
                with_label=False,
            )
            entry["relation"] = row[1]
            entry["direction"] = direction
            out.append(entry)
        return out
    finally:
        await g.close()


FIND_SYMBOL_SNIPPET_LINES = 4
FIND_SYMBOL_DB_LIMIT = 200


def _clamp_find_symbol_limit(limit: Any) -> int:
    """Coerce ``limit`` to ``1..FIND_SYMBOL_DB_LIMIT``.

    Agents may hand back a stringified or out-of-range ``limit``; a negative
    value would otherwise flip ``rows[:limit]`` into a surprising tail slice and
    a non-integer would fail deep in the slice with an opaque error. Strings of
    digits are accepted; anything else is rejected up front.
    """
    if isinstance(limit, bool):
        raise ValueError(f"limit must be an integer, got bool: {limit!r}")
    if isinstance(limit, str) and limit.lstrip("-").isdigit():
        limit = int(limit)
    if not isinstance(limit, int):
        raise ValueError(f"limit must be an integer, got: {limit!r}")
    if limit < 1:
        return 1
    if limit > FIND_SYMBOL_DB_LIMIT:
        return FIND_SYMBOL_DB_LIMIT
    return limit


@app.tool(
    name="find_symbol",
    description=(
        "Resolve a Function/Class NAME to its integer symbol node id — the "
        "bridge from a human-readable name to the `symbol_id` that "
        "`get_neighbors`, `impact_analysis` and `find_path` require (those tools "
        "take an id, NOT a name; `search_code` returns FILES, not symbol ids, so "
        "start here for relationship questions). Pass the simple name "
        "(e.g. `normalize_cartesian_coordinates`); a dotted qualname "
        "(`Grid.normalize_cartesian_coordinates`) is accepted and its last "
        "segment is used. Optionally pass `file` (repo-relative path or a "
        "substring of it) to disambiguate same-named symbols — matches in that "
        "file are flagged `file_match: true` and listed first. Returns "
        "[{symbol_id, name, label, file, line, file_match, snippet}] ordered "
        "best-scoped first; when more than one remains, disambiguate by `file` "
        "and `snippet`. Feed the chosen `symbol_id` to the relationship tools."
    ),
)
async def find_symbol(
    name: str,
    project: str,
    file: Optional[str] = None,
    branch: Optional[str] = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Look up Function/Class nodes by their simple name.

    Symbol nodes store only the SIMPLE name (``foo``), never the qualname
    (``Bar.foo``), so a dotted input is reduced to its last segment. Every
    candidate carries a ``file_match`` flag (always ``False`` when no ``file``
    filter is requested); when ``file`` is given we do not silently widen the
    search — the in-file ones sort first, so a wrong/empty file filter degrades
    visibly (the agent still sees the global matches but knows none were in the
    requested file) rather than routing a relationship query to an arbitrary
    same-named symbol.
    """
    simple = str(name).strip().split(".")[-1].strip()
    if not simple:
        raise ValueError(
            f"name must be a non-empty symbol name, got: {name!r}"
        )
    eff_limit = _clamp_find_symbol_limit(limit)
    g = _project_arg(project, branch)
    try:
        res = await g._query(
            "MATCH (n) WHERE (n:Function OR n:Class) AND n.name = $name "
            "RETURN n LIMIT $limit",
            {"name": simple, "limit": FIND_SYMBOL_DB_LIMIT},
        )
        rows = [
            _node_summary(
                r[0],
                rel_to=project,
                snippet_lines=FIND_SYMBOL_SNIPPET_LINES,
            )
            for r in res.result_set
        ]
    finally:
        await g.close()

    for r in rows:
        r["symbol_id"] = r.pop("id")

    needle = str(file).strip().lstrip("/") if file is not None else ""

    def _matches(r: dict[str, Any]) -> bool:
        fp = r.get("file") or ""
        return bool(needle) and (fp == needle or fp.endswith(needle) or needle in fp)

    # ``file_match`` is part of the documented response shape, so set it on
    # every row (False when no ``file`` filter is requested) rather than only
    # when ``file`` is given. Sort deterministically — in-file matches first,
    # then by file/line/name/id — so ordering never depends on FalkorDB row
    # order between runs.
    for r in rows:
        r["file_match"] = _matches(r)
    rows.sort(key=lambda r: (
        not r["file_match"],
        r.get("file") or "",
        r["line"] if r.get("line") is not None else math.inf,
        r.get("name") or "",
        r["symbol_id"],
    ))

    return rows[:eff_limit]


@app.tool(
    name="get_neighbors",
    description=(
        "Adjacent symbols of a SYMBOL node (Function/Class) via graph edges, by "
        "its integer node id. Pick relation+direction: "
        "`CALLS`+`IN`=callers (upstream co-change sites); `CALLS`+`OUT`=callees; "
        "`IMPORTS`+`IN`=importers of a File; `OVERRIDES`+`BOTH`=polymorphic "
        "dispatch that plain CALLS miss; `[IMPORTS,CALLS,DEFINES]`+`OUT`="
        "dependencies. `relation` is one name or a list; `direction` is IN, OUT, "
        "or BOTH. Each result carries a code `snippet`, so you rarely need to "
        "`view` the file. To navigate from a `search_code` hit (a FILE), use "
        "`get_file_neighbors` with its `file_id` instead — this tool expects a "
        "symbol id."
    ),
)
async def get_neighbors(
    symbol_id: Any,
    project: str,
    relation: Any = "CALLS",
    direction: str = "OUT",
    branch: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Unified single-hop neighbor traversal (replaces the per-edge tools).

    ``relation`` accepts a single edge type or a list of them; results are
    aggregated across relations and deduped. ``direction`` is ``IN``
    (incoming edges), ``OUT`` (outgoing), or ``BOTH`` (union of IN+OUT).
    """
    rels = [relation] if isinstance(relation, str) else list(relation)
    direction = (direction or "OUT").upper()
    if direction == "BOTH":
        dirs = ["OUT", "IN"]
    elif direction in ("IN", "OUT"):
        dirs = [direction]
    else:
        raise ValueError(
            f"direction must be 'IN', 'OUT', or 'BOTH', got: {direction!r}"
        )

    seen: set[Any] = set()
    out: list[dict[str, Any]] = []
    for d in dirs:
        for rel in rels:
            rows = await _neighbors_payload(project, branch, symbol_id, rel, d, limit)
            for row in rows:
                key = (row.get("id"), row.get("relation"), row.get("direction"))
                if key in seen:
                    continue
                seen.add(key)
                out.append(row)
                if len(out) >= limit:
                    return out
    return out


async def get_callers(
    symbol_id: int | str,
    project: str,
    branch: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return await _neighbors_payload(project, branch, symbol_id, "CALLS", "IN", limit)


async def get_callees(
    symbol_id: int | str,
    project: str,
    branch: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return await _neighbors_payload(project, branch, symbol_id, "CALLS", "OUT", limit)


async def get_dependencies(
    symbol_id: int | str,
    project: str,
    branch: Optional[str] = None,
    rels: Optional[list[str]] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if rels is None:
        rels = ["IMPORTS", "CALLS", "DEFINES"]
    # Aggregate across relations; preserve ordering and dedupe by id.
    seen: set[Any] = set()
    out: list[dict[str, Any]] = []
    for rel in rels:
        # Only fetch the rows we can still accept, so total DB work is
        # bounded by ``limit`` rather than ``limit * len(rels)``.
        remaining = limit - len(out)
        if remaining <= 0:
            break
        rows = await _neighbors_payload(
            project, branch, symbol_id, rel, "OUT", remaining
        )
        for row in rows:
            key = (row.get("id"), row.get("relation"))
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
            if len(out) >= limit:
                return out
    return out


# ---------------------------------------------------------------------------
# Spike 1a — get_importers (incoming IMPORTS) / get_overrides (OVERRIDES)
# ---------------------------------------------------------------------------


async def get_importers(
    symbol_id: Any,
    project: str,
    branch: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return await _neighbors_payload(
        project, branch, symbol_id, "IMPORTS", "IN", limit
    )


async def get_overrides(
    symbol_id: Any,
    project: str,
    branch: Optional[str] = None,
    direction: str = "BOTH",
    limit: int = 50,
) -> list[dict[str, Any]]:
    direction = (direction or "BOTH").upper()
    if direction in ("IN", "OUT"):
        return await _neighbors_payload(
            project, branch, symbol_id, "OVERRIDES", direction, limit
        )
    if direction != "BOTH":
        raise ValueError(
            f"direction must be 'IN', 'OUT', or 'BOTH', got: {direction!r}"
        )
    seen: set[Any] = set()
    out: list[dict[str, Any]] = []
    for d in ("OUT", "IN"):
        rows = await _neighbors_payload(
            project, branch, symbol_id, "OVERRIDES", d, limit
        )
        for row in rows:
            key = (row.get("id"), row.get("direction"))
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
            if len(out) >= limit:
                return out
    return out


# ---------------------------------------------------------------------------
# T7 — find_path
# ---------------------------------------------------------------------------


@app.tool(
    name="find_path",
    description=(
        "Return up to `max_paths` CALLS-path sequences from `source_id` to "
        "`dest_id` ('how does A reach B'). Use to confirm whether a suspected "
        "entry point actually reaches a suspected buggy function, and through "
        "which intermediaries. Returns an empty list when no STATIC path exists "
        "(dynamic dispatch is not captured)."
    ),
)
async def find_path(
    source_id: int | str,
    dest_id: int | str,
    project: str,
    branch: Optional[str] = None,
    max_paths: int = 10,
) -> list[dict[str, Any]]:
    src = _coerce_node_id(source_id)
    dst = _coerce_node_id(dest_id)
    g = _project_arg(project, branch)
    try:
        # Bound DB work by ``max_paths`` so large graphs don't enumerate an
        # unbounded number of paths before we slice in Python.
        raw = await g.find_paths(src, dst, limit=max_paths)
    finally:
        await g.close()

    # ``AsyncGraphQuery.find_paths`` returns each path as an alternating
    # [node, edge, node, edge, ..., node] list; we strip edges and surface
    # only the node sequence — that's what agents typically want.
    paths: list[dict[str, Any]] = []
    for entry in raw:
        node_seq = [
            _node_summary(x, rel_to=project, with_label=True)
            for x in entry
            # Discriminate on ``labels``: ``encode_node`` emits a top-level
            # ``labels`` key, while ``encode_edge`` does not (edges carry
            # ``relation``/``src_node``/``dest_node`` instead). Filtering on
            # ``properties`` would be wrong because FalkorDB's Edge also has a
            # ``properties`` attribute, so edges would slip through as bogus
            # all-null node entries.
            if isinstance(x, dict) and "labels" in x
        ]
        paths.append({"path": node_seq})
    return paths


# ---------------------------------------------------------------------------
# T8 — search_code
# ---------------------------------------------------------------------------


@app.tool(
    name="search_code",
    description=(
        "Localize a bug/feature to its files from a CONCEPTUAL free-text query. "
        "Phrase it as a natural-language description of the behavior and area "
        "involved (e.g. 'face centroid computation uses node connectivity' or "
        "'tagging a library entry duplicates tags') — the issue title plus a "
        "phrase about what the code DOES. Backticked symbol/error names are fine "
        "as seasoning, but DO NOT pass a bare list of identifiers: a pile of exact "
        "symbol names collapses the ranking onto their single definition file and "
        "hides the related files you didn't know to name (use grep if you already "
        "know the exact symbol). "
        "Ranks every indexed file by a hybrid of (exact symbol-name match, "
        "path-token overlap, BM25 over symbol names + docstrings, and call-graph "
        "centrality), de-prioritizing test/vendored paths. Returns the top files "
        "as {file, file_id, score, name, line, snippet} — best candidates first, "
        "so the usual top 3-5 are where to start. Unlike a name lookup, it "
        "surfaces the right file even when you don't know the exact symbol. Feed a "
        "result's `file_id` to `get_file_neighbors` to reveal the files "
        "structurally coupled to it (imports/calls) — co-change candidates a "
        "textual search misses."
    ),
)
async def search_code(
    query: str,
    project: str,
    branch: Optional[str] = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    g = _project_arg(project, branch)
    try:
        ranked = await _hybrid_rank(g, query, project)
    finally:
        await g.close()
    out: list[dict[str, Any]] = []
    for r in ranked[:limit]:
        rec: dict[str, Any] = {
            "file": r["file"],
            "file_id": r["file_id"],
            "score": r["score"],
            "name": r["name"],
            "line": r["src_start"],
            "label": "File",
        }
        snip = _read_snippet(
            r["abs_path"],
            r["src_start"] if r["src_start"] is not None else 1,
            r["src_end"] if r["src_end"] is not None else r["src_start"],
            SEARCH_SNIPPET_LINES,
            project=project,
        )
        if snip:
            rec["snippet"] = snip
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# T8b — get_file_neighbors (file-level structural coupling)
# ---------------------------------------------------------------------------

FILE_NEIGHBOR_RELS = ("IMPORTS", "CALLS", "EXTENDS", "OVERRIDES")
FILE_NEIGHBOR_MAX = 100
"""Hard cap on returned neighbor files. The default is intentionally high:
the value of this tool is a candidate set GUARANTEED to contain the coupled
file, so truncating it (and possibly dropping that file) defeats the purpose.
``truncated`` is surfaced so the agent knows when the cap bit."""


async def _resolve_file(
    g, file: Any, project: Optional[str]
) -> tuple[Optional[int], Optional[str]]:
    """Resolve a File handle to ``(file_node_id, abs_path)``.

    ``file`` is either the integer File-node id that ``search_code`` returns,
    or a repo-relative path. Path resolution compares ``_relativize`` of each
    stored ``File.path`` rather than reconstructing an absolute path (worktree
    roots vary), so a relative path matches regardless of the indexing root.
    """
    try:
        fid = _coerce_node_id(file)
    except ValueError:
        fid = None
    if fid is not None:
        res = await g._query(
            "MATCH (f:File) WHERE ID(f) = $id RETURN f.path", {"id": fid}
        )
        if res.result_set and res.result_set[0][0]:
            return fid, res.result_set[0][0]
        return None, None
    target = str(file).strip().lstrip("/")
    res = await g._query("MATCH (f:File) RETURN ID(f), f.path")
    for nid, ap in res.result_set:
        if ap and (_relativize(ap, project) == target or ap == file):
            return nid, ap
    return None, None


@app.tool(
    name="get_file_neighbors",
    description=(
        "Files structurally coupled to a FILE — the import/call/inheritance "
        "dependencies that a textual search misses and that must often change "
        "together. Run after `search_code`, passing a hit's `file_id` (or a "
        "repo-relative path). Expands EVERY symbol in the file (not just the "
        "representative one) and unions 1-hop IMPORTS/CALLS/EXTENDS/OVERRIDES "
        "edges in both directions, deduped to files and ordered by coupling "
        "strength (edge count). Returns {file, total_neighbors, truncated, "
        "neighbors:[{file, file_id, edge_count, relations, snippet}]}. Each "
        "neighbor carries a `file_id` you can recurse on and a code `snippet`. "
        "Use this to reach co-change files after localizing the primary hit."
    ),
)
async def get_file_neighbors(
    file: Any,
    project: str,
    branch: Optional[str] = None,
    limit: int = FILE_NEIGHBOR_MAX,
) -> dict[str, Any]:
    g = _project_arg(project, branch)
    try:
        fid, abs_path = await _resolve_file(g, file, project)
        if abs_path is None:
            return {
                "file": _relativize(str(file), project),
                "file_id": None,
                "total_neighbors": 0,
                "truncated": False,
                "neighbors": [],
            }

        sres = await g._query(
            "MATCH (n) WHERE (n:Function OR n:Class) AND n.path = $p RETURN ID(n)",
            {"p": abs_path},
        )
        ids = [row[0] for row in sres.result_set]
        if fid is not None:
            ids.append(fid)
        if not ids:
            return {
                "file": _relativize(abs_path, project),
                "file_id": fid,
                "total_neighbors": 0,
                "truncated": False,
                "neighbors": [],
            }

        relq = "|".join(FILE_NEIGHBOR_RELS)
        # Aggregate first (group by neighbor file), sort second, limit last — so
        # high-degree symbols can't crowd the coupled file out before ranking.
        agg: dict[str, dict[str, Any]] = {}
        for direction in ("OUT", "IN"):
            if direction == "OUT":
                q = (
                    f"MATCH (n)-[e:{relq}]->(d) WHERE ID(n) IN $ids "
                    "AND d.path IS NOT NULL AND d.path <> $self "
                    "RETURN d.path AS p, type(e) AS rel"
                )
            else:
                q = (
                    f"MATCH (s)-[e:{relq}]->(n) WHERE ID(n) IN $ids "
                    "AND s.path IS NOT NULL AND s.path <> $self "
                    "RETURN s.path AS p, type(e) AS rel"
                )
            res = await g._query(q, {"ids": ids, "self": abs_path})
            for ap, rel in res.result_set:
                rp = _relativize(ap, project)
                slot = agg.get(rp)
                if slot is None:
                    slot = {"abs": ap, "count": 0, "rels": Counter()}
                    agg[rp] = slot
                slot["count"] += 1
                slot["rels"][f"{rel}:{direction}"] += 1

        total = len(agg)
        eff_limit = min(int(limit or FILE_NEIGHBOR_MAX), FILE_NEIGHBOR_MAX)
        ordered = sorted(agg.items(), key=lambda kv: (-kv[1]["count"], kv[0]))
        kept = ordered[:eff_limit]
        kept_abs = [slot["abs"] for _, slot in kept]

        # Batch the File-id and representative-symbol (lowest src_start) lookups
        # for only the kept neighbors.
        fid_of: dict[str, int] = {}
        if kept_abs:
            fres = await g._query(
                "MATCH (f:File) WHERE f.path IN $paths RETURN f.path, ID(f)",
                {"paths": kept_abs},
            )
            fid_of = {row[0]: row[1] for row in fres.result_set}
        rep_of: dict[str, tuple] = {}
        if kept_abs:
            rres = await g._query(
                "MATCH (n) WHERE (n:Function OR n:Class) AND n.path IN $paths "
                "RETURN n.path, n.src_start, n.src_end ORDER BY n.src_start",
                {"paths": kept_abs},
            )
            for ap, s0, s1 in rres.result_set:
                rep_of.setdefault(ap, (s0, s1))

        neighbors: list[dict[str, Any]] = []
        for rp, slot in kept:
            ap = slot["abs"]
            entry: dict[str, Any] = {
                "file": rp,
                "file_id": fid_of.get(ap),
                "edge_count": slot["count"],
                "relations": dict(slot["rels"]),
            }
            rep = rep_of.get(ap)
            if rep:
                snip = _read_snippet(
                    ap, rep[0], rep[1], NEIGHBOR_SNIPPET_LINES, project=project
                )
                if snip:
                    entry["snippet"] = snip
            neighbors.append(entry)

        return {
            "file": _relativize(abs_path, project),
            "file_id": fid,
            "total_neighbors": total,
            "truncated": total > eff_limit,
            "neighbors": neighbors,
        }
    finally:
        await g.close()


# Hard cap on traversal depth — passed values above this are silently
# clamped. Prevents pathological queries (e.g. depth=999) from hammering
# FalkorDB while still letting agents request "deep" impact without
# hitting an error.
IMPACT_MAX_DEPTH = 10


def _clamp_depth(depth: Any) -> int:
    """Coerce ``depth`` to ``1..IMPACT_MAX_DEPTH``. Strings accepted."""
    if isinstance(depth, bool):
        raise ValueError(f"depth must be an integer, got bool: {depth!r}")
    if isinstance(depth, str) and depth.lstrip("-").isdigit():
        depth = int(depth)
    if not isinstance(depth, int):
        raise ValueError(f"depth must be an integer, got: {depth!r}")
    if depth < 1:
        return 1
    if depth > IMPACT_MAX_DEPTH:
        return IMPACT_MAX_DEPTH
    return depth


@app.tool(
    name="impact_analysis",
    description=(
        "Find the files/functions connected to a symbol through the call graph "
        "— the files that must change TOGETHER when fixing or modifying it. "
        "`direction='IN'` = upstream callers (who depends on this); "
        "`direction='OUT'` = downstream callees (what this relies on). "
        f"Traverses only CALLS edges (static; dynamic dispatch not captured); "
        f"depth clamped to {IMPACT_MAX_DEPTH}; cycles deduplicated via Cypher "
        "DISTINCT. `limit` bounds the number of impacted symbols returned. "
        "For localization, run IN on a confirmed-buggy symbol to "
        "surface co-change files."
    ),
)
async def impact_analysis(
    symbol_id: int | str,
    project: str,
    branch: Optional[str] = None,
    direction: str = "IN",
    depth: int = 3,
    limit: int = 50,
) -> list[dict[str, Any]]:
    node_id = _coerce_node_id(symbol_id)
    eff_depth = _clamp_depth(depth)

    if direction == "IN":
        # Upstream callers: (impacted) -[:CALLS*]-> (n)
        q = (
            f"MATCH (n)<-[:CALLS*1..{eff_depth}]-(impacted) "
            f"WHERE ID(n) = $sid "
            f"RETURN DISTINCT impacted "
            f"LIMIT $limit"
        )
    elif direction == "OUT":
        # Downstream callees: (n) -[:CALLS*]-> (impacted)
        q = (
            f"MATCH (n)-[:CALLS*1..{eff_depth}]->(impacted) "
            f"WHERE ID(n) = $sid "
            f"RETURN DISTINCT impacted "
            f"LIMIT $limit"
        )
    else:
        raise ValueError(
            f"direction must be 'IN' (upstream) or 'OUT' (downstream), "
            f"got: {direction!r}"
        )

    g = _project_arg(project, branch)
    try:
        res = await g._query(q, {"sid": node_id, "limit": int(limit)})
    finally:
        await g.close()

    out: list[dict[str, Any]] = []
    for row in res.result_set:
        entry = _node_summary(row[0], rel_to=project, with_label=False)
        entry["direction"] = direction
        out.append(entry)
    return out
