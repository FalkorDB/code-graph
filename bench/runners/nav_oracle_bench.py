"""Deterministic graph-vs-oracle navigation accuracy bench (Lane 2, the FREE half).

Fixes the circular-validation flaw of ``struct_query_bench`` (which grades the graph
against its own CALLS edges). Here the GROUND TRUTH for "who calls S" comes from an
INDEPENDENT oracle -- jedi find-references -- run on the same worktree source, never
from the graph. We then score the graph's CALLS answer against that oracle.

Independence discipline (prereg-multihop-nav §2, §6):
  * Symbol definitions are located via ``ast`` over the source, NOT via the graph.
  * Symbols with 0 or >1 definitions in the worktree are DROPPED (oracle-uncertain);
    we log how many, keeping the gold clean at the stated cost of generalization.
  * jedi references are filtered to CALL sites and mapped to their enclosing function
    via ``ast`` (source-only), so the comparison unit -- (relpath, caller_qualname) --
    is computed without consulting the graph.

Comparison unit: the SET of caller functions, identified by (relpath, qualname).
Module-level call sites map to qualname ``"<module>"``. We report per-symbol set
precision / recall / F1 of GRAPH vs ORACLE, macro-averaged, plus the raw disagreement
lists (graph-only and oracle-only callers) for hand audit.

Usage:
  .venv/bin/python -m bench.runners.nav_oracle_bench \
      --graph code:loc-<hash>:_default --worktree <path> [--n 30] [--port 6380] [--json out.json]
"""
from __future__ import annotations

import argparse
import ast
import json
import statistics as st
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from bench.runners.struct_query_bench import _GENERIC, _graph_query


# ---------------------------------------------------------------------------
# Source-side (graph-independent) helpers: definitions + enclosing scopes via ast
# ---------------------------------------------------------------------------

@dataclass
class Scope:
    start: int          # 1-based first line (the def/class line)
    end: int            # 1-based last line (inclusive)
    qualname: str


def _iter_py(worktree: Path):
    for p in worktree.rglob("*.py"):
        # Skip typical vendored / test-noise dirs that pollute the oracle.
        parts = set(p.parts)
        if parts & {".git", "node_modules", ".tox", "build", "dist", ".venv"}:
            continue
        yield p


def _parse(path: Path) -> Optional[ast.AST]:
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError):
        return None


def find_definitions(worktree: Path, name: str) -> list[tuple[Path, int, int]]:
    """All (path, lineno, name_col) where a function/class `name` is DEFINED.

    Source-only (ast), independent of the graph. name_col is the 0-based column of
    the identifier itself (not the `def`/`class` keyword), suitable for seeding jedi.
    """
    out: list[tuple[Path, int, int]] = []
    for p in _iter_py(worktree):
        tree = _parse(p)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name != name:
                    continue
                kw = "class " if isinstance(node, ast.ClassDef) else "def "
                out.append((p, node.lineno, node.col_offset + len(kw)))
    return out


def build_scopes(path: Path) -> list[Scope]:
    """Flat list of every function/class scope in a file with line ranges + qualname."""
    tree = _parse(path)
    if tree is None:
        return []
    scopes: list[Scope] = []

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qual = f"{prefix}{child.name}"
                end = getattr(child, "end_lineno", None) or child.lineno
                scopes.append(Scope(child.lineno, end, qual))
                walk(child, qual + ".")
            else:
                walk(child, prefix)

    walk(tree, "")
    return scopes


def enclosing_qualname(scopes: list[Scope], line: int) -> str:
    """Innermost scope containing `line`, or '<module>' if none."""
    best: Optional[Scope] = None
    for s in scopes:
        if s.start <= line <= s.end:
            if best is None or s.start > best.start:  # innermost = latest start
                best = s
    return best.qualname if best else "<module>"


# ---------------------------------------------------------------------------
# Oracle (jedi) caller set
# ---------------------------------------------------------------------------

def _is_call_site(line_text: str, col: int, name: str) -> bool:
    """Heuristic: the reference at `col` is a CALL if `name` is immediately
    followed (modulo whitespace) by '('. Excludes imports, attribute reads,
    type hints, decorators-without-call."""
    after = line_text[col + len(name):]
    stripped = after.lstrip()
    return stripped.startswith("(")


def oracle_callers(
    worktree: Path, defs: list[tuple[Path, int, int]], name: str,
    scope_cache: dict[Path, list[Scope]],
) -> Optional[set[tuple[str, str]]]:
    """jedi find-references -> set of (relpath, caller_qualname) call sites.

    Returns None if jedi can't resolve (oracle failure -> caller drops the symbol).
    Unions references across all definition sites (already gated to a single def by
    the caller, but kept general)."""
    import jedi

    callers: set[tuple[str, str]] = set()
    project = jedi.Project(str(worktree))
    for dpath, dline, dcol in defs:
        try:
            script = jedi.Script(path=str(dpath), project=project)
            refs = script.get_references(line=dline, column=dcol, include_builtins=False)
        except Exception:
            return None
        for r in refs:
            if r.is_definition():
                continue
            mod = r.module_path
            if mod is None:
                continue
            mp = Path(mod)
            try:
                rel = str(mp.relative_to(worktree))
            except ValueError:
                continue  # reference outside the worktree (stdlib/site-packages)
            try:
                line_text = mp.read_text(encoding="utf-8", errors="replace").splitlines()[r.line - 1]
            except (OSError, IndexError):
                continue
            if not _is_call_site(line_text, r.column, name):
                continue
            if mp not in scope_cache:
                scope_cache[mp] = build_scopes(mp)
            qual = enclosing_qualname(scope_cache[mp], r.line)
            callers.add((rel, qual))
    return callers


# ---------------------------------------------------------------------------
# Graph caller set
# ---------------------------------------------------------------------------

def graph_callers(graph: str, port: int, name: str, worktree: Path) -> set[tuple[str, str]]:
    """The graph's CALLS answer as a set of (relpath, caller_qualname).

    The graph stores caller functions directly (c)-[:CALLS]->(s{name}). We map each
    caller's (path, name) to the SAME (relpath, qualname) identity the oracle uses by
    re-deriving qualname from src_start via the source ast, so the two sets are
    comparable. Falls back to the bare caller name if scope lookup misses."""
    cypher = (
        f"MATCH (c)-[:CALLS]->(s {{name:'{name}'}}) "
        "RETURN DISTINCT c.name, c.path, c.src_start"
    )
    rows = _graph_query(graph, cypher, port)
    out: set[tuple[str, str]] = set()
    scope_cache: dict[Path, list[Scope]] = {}
    for row in rows:
        if len(row) < 2 or row[0] is None or row[1] is None:
            continue
        cname, cpath = str(row[0]), str(row[1])
        start = int(row[2]) if len(row) > 2 and row[2] is not None else None
        mp = Path(cpath)
        try:
            rel = str(mp.relative_to(worktree))
        except ValueError:
            rel = mp.name
        qual = cname
        if start is not None and mp.exists():
            if mp not in scope_cache:
                scope_cache[mp] = build_scopes(mp)
            q = enclosing_qualname(scope_cache[mp], start)
            if q != "<module>":
                qual = q
        out.add((rel, qual))
    return out


# ---------------------------------------------------------------------------
# Sampling + scoring
# ---------------------------------------------------------------------------

def sample_caller_symbols(
    graph: str, port: int, *, n: int, seed: int,
    fanin_lo: int = 3, fanin_hi: int = 80,
) -> list[dict[str, Any]]:
    """Distinctively-named callees with banded fan-in (reuses struct_query_bench
    rationale: 3..80 avoids precise-grep-already and generic-megahub extremes)."""
    import random
    cypher = (
        "MATCH (c)-[:CALLS]->(s) WHERE s:Searchable "
        "WITH s.name AS name, count(c) AS fanin "
        f"WHERE fanin >= {fanin_lo} AND fanin <= {fanin_hi} "
        "RETURN name, fanin ORDER BY name"
    )
    rows = _graph_query(graph, cypher, port)
    pairs = []
    for row in rows:
        if len(row) < 2:
            continue
        name, fan = row[0], row[1]
        if not name or name in _GENERIC or str(name).startswith("__") or len(str(name)) < 4:
            continue
        pairs.append((str(name), int(fan)))
    rng = random.Random(seed)
    rng.shuffle(pairs)
    return [{"name": nm, "fanin": fn} for nm, fn in pairs[:n]]


def _prf(graph_set: set, oracle_set: set) -> dict[str, float]:
    tp = len(graph_set & oracle_set)
    fp = len(graph_set - oracle_set)
    fn = len(oracle_set - graph_set)
    prec = tp / (tp + fp) if (tp + fp) else (1.0 if not fn else 0.0)
    rec = tp / (tp + fn) if (tp + fn) else (1.0 if not fp else 0.0)
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(prec, 4),
            "recall": round(rec, 4), "f1": round(f1, 4)}


@dataclass
class Result:
    rows: list[dict] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)


def run(graph: str, worktree: Path, *, n: int, seed: int, port: int) -> Result:
    syms = sample_caller_symbols(graph, port, n=n, seed=seed)
    res = Result()
    scope_cache: dict[Path, list[Scope]] = {}
    for s in syms:
        name = s["name"]
        defs = find_definitions(worktree, name)
        if len(defs) != 1:  # oracle-reliability gate
            res.dropped.append({"symbol": name, "reason": f"{len(defs)} defs", "fanin": s["fanin"]})
            continue
        oset = oracle_callers(worktree, defs, name, scope_cache)
        if oset is None:
            res.dropped.append({"symbol": name, "reason": "jedi failed", "fanin": s["fanin"]})
            continue
        gset = graph_callers(graph, port, name, worktree)
        prf = _prf(gset, oset)
        res.rows.append({
            "symbol": name,
            "fanin": s["fanin"],
            "n_graph": len(gset),
            "n_oracle": len(oset),
            **prf,
            "graph_only": sorted(f"{q} @ {p}" for p, q in (gset - oset))[:10],
            "oracle_only": sorted(f"{q} @ {p}" for p, q in (oset - gset))[:10],
        })
    return res


def summarize(rows: list[dict]) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    def macro(k: str) -> float:
        return round(st.mean(r[k] for r in rows), 4)
    return {
        "n_scored": len(rows),
        "macro_precision": macro("precision"),
        "macro_recall": macro("recall"),
        "macro_f1": macro("f1"),
        "median_f1": round(st.median(r["f1"] for r in rows), 4),
        "exact_match_rate": round(sum(1 for r in rows if r["fp"] == 0 and r["fn"] == 0) / len(rows), 4),
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", required=True, help="FalkorDB graph key, e.g. code:loc-<hash>:_default")
    ap.add_argument("--worktree", required=True, type=Path)
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--port", type=int, default=6380)
    ap.add_argument("--json")
    args = ap.parse_args(argv)

    wt = args.worktree.resolve()
    res = run(args.graph, wt, n=args.n, seed=args.seed, port=args.port)
    summary = summarize(res.rows)

    print(f"graph={args.graph}  worktree={wt.name}")
    print(f"sampled n={args.n}  scored={summary.get('n_scored', 0)}  dropped={len(res.dropped)}")
    print(f"  GRAPH-vs-ORACLE (callers, 1-hop reverse CALLS):")
    for k in ("macro_precision", "macro_recall", "macro_f1", "median_f1", "exact_match_rate"):
        print(f"    {k:18} = {summary.get(k)}")
    print(f"\n  per-symbol (sorted by f1):")
    for r in sorted(res.rows, key=lambda x: x["f1"]):
        print(f"    {r['symbol']:28} fanin={r['fanin']:>3} "
              f"P={r['precision']:.2f} R={r['recall']:.2f} F1={r['f1']:.2f} "
              f"(g={r['n_graph']} o={r['n_oracle']} tp={r['tp']} fp={r['fp']} fn={r['fn']})")
    if res.dropped:
        from collections import Counter
        dc = Counter(d["reason"] for d in res.dropped)
        print(f"\n  dropped: {dict(dc)}")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"graph": args.graph, "worktree": str(wt), "summary": summary,
             "rows": res.rows, "dropped": res.dropped}, indent=2))
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
