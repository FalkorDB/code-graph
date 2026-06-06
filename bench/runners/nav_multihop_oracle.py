"""Independent (graph-blind) multi-hop call-graph oracle for Lane 2.

Builds a FORWARD call graph ``caller -> callee`` for a worktree using **jedi**
(goto on every call site) + ``ast`` (scopes / call-site enumeration), with ZERO
input from FalkorDB / the tree-sitter analyzer under test. From that one graph we
derive all four question types' ground truth:

  * callers(S)      = reverse 1-hop  -> {u : u -> S}
  * callees(S)      = forward 1-hop  -> {v : S -> v}
  * blast_radius(S) = reverse transitive closure, depth<=D -> who is affected if S changes
  * path(A, B)      = forward reachability + one valid path (edges all in the oracle)

Independence discipline (prereg-multihop-nav §2): the oracle never reads the
graph; jedi is a different engine from the tree-sitter resolver we benchmark, so
grading the graph/agent against it is non-circular. Node identity is
``(relpath, qualname)`` -- the SAME identity ``nav_oracle_bench`` uses -- so graph
and agent answers are directly comparable.

The forward graph is expensive (one jedi goto per call site) so it is cached to
``<worktree>/.nav_oracle_cache.json`` keyed by a digest of the .py file set +
mtimes; pass ``--rebuild`` to force.

Usage:
  .venv/bin/python -m bench.runners.nav_multihop_oracle --worktree <path> [--rebuild] [--depth 3]
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from bench.runners.nav_oracle_bench import (
    Scope,
    build_scopes,
    enclosing_qualname,
    find_definitions,
    _iter_py,
    _parse,
)

# A node in the call graph: (relpath, qualname). qualname uses dotted scope path
# (e.g. "Grid.calculate_face_areas"); module-level call sites are "<module>".
Node = tuple[str, str]


# ---------------------------------------------------------------------------
# Call-site enumeration (ast, source-only)
# ---------------------------------------------------------------------------

@dataclass
class CallSite:
    caller_qual: str        # enclosing function/class qualname, or "<module>"
    callee_name: str        # the identifier being called (attr or bare name)
    line: int               # 1-based line of the callee identifier
    col: int                # 0-based column of the callee identifier (jedi seed)


def _callee_ident(func: ast.AST) -> Optional[tuple[str, int, int]]:
    """For a Call.func node return (name, line, col0) pointing AT the callee
    identifier, suitable for seeding jedi.goto. Handles bare ``foo(`` (Name) and
    method ``obj.bar(`` (Attribute). Returns None for unresolvable forms
    (subscripts, calls-of-calls, lambdas)."""
    if isinstance(func, ast.Name):
        return func.id, func.lineno, func.col_offset
    if isinstance(func, ast.Attribute):
        # The attribute name sits at the END of the attribute expression.
        end_line = getattr(func, "end_lineno", func.lineno)
        end_col = getattr(func, "end_col_offset", None)
        if end_col is None:
            return None
        return func.attr, end_line, end_col - len(func.attr)
    return None


def enumerate_call_sites(path: Path, scopes: list[Scope]) -> list[CallSite]:
    tree = _parse(path)
    if tree is None:
        return []
    out: list[CallSite] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        ident = _callee_ident(node.func)
        if ident is None:
            continue
        name, line, col = ident
        caller = enclosing_qualname(scopes, node.func.lineno)
        out.append(CallSite(caller_qual=caller, callee_name=name, line=line, col=col))
    return out


# ---------------------------------------------------------------------------
# Forward call graph (jedi-resolved)
# ---------------------------------------------------------------------------

@dataclass
class CallGraph:
    worktree: str
    fwd: dict[Node, set[Node]] = field(default_factory=dict)   # caller -> {callee}
    rev: dict[Node, set[Node]] = field(default_factory=dict)   # callee -> {caller}
    nodes: set[Node] = field(default_factory=set)
    # def_index: qualname-leaf -> set of Nodes defining it (for question phrasing)
    by_name: dict[str, set[Node]] = field(default_factory=dict)

    def add_edge(self, u: Node, v: Node) -> None:
        if u == v:
            return
        self.fwd.setdefault(u, set()).add(v)
        self.rev.setdefault(v, set()).add(u)
        self.nodes.add(u)
        self.nodes.add(v)

    def successors(self, s: Node) -> set[Node]:
        return set(self.fwd.get(s, set()))

    def predecessors(self, s: Node) -> set[Node]:
        return set(self.rev.get(s, set()))

    def reverse_closure(self, s: Node, depth: int) -> set[Node]:
        """All nodes that transitively reach s within <=depth hops (excl. s)."""
        seen: set[Node] = set()
        frontier = deque([(s, 0)])
        while frontier:
            cur, d = frontier.popleft()
            if d >= depth:
                continue
            for u in self.rev.get(cur, set()):
                if u not in seen and u != s:
                    seen.add(u)
                    frontier.append((u, d + 1))
        return seen

    def forward_path(self, a: Node, b: Node, max_depth: int = 8) -> Optional[list[Node]]:
        """One shortest forward path a->...->b (BFS), or None if unreachable."""
        if a == b:
            return [a]
        prev: dict[Node, Node] = {a: a}
        frontier = deque([(a, 0)])
        while frontier:
            cur, d = frontier.popleft()
            if d >= max_depth:
                continue
            for v in self.fwd.get(cur, set()):
                if v not in prev:
                    prev[v] = cur
                    if v == b:
                        path = [b]
                        while path[-1] != a:
                            path.append(prev[path[-1]])
                        return list(reversed(path))
                    frontier.append((v, d + 1))
        return None


def _def_node_for(name_obj, worktree: Path, scope_cache: dict[Path, list[Scope]]) -> Optional[Node]:
    """Map a jedi goto result to a (relpath, qualname) node, or None if outside
    the worktree / not a func/class definition."""
    mod = getattr(name_obj, "module_path", None)
    if mod is None:
        return None
    mp = Path(mod)
    try:
        rel = str(mp.relative_to(worktree))
    except ValueError:
        return None  # stdlib / site-packages
    typ = getattr(name_obj, "type", None)
    if typ not in ("function", "class"):
        return None
    line = getattr(name_obj, "line", None)
    if line is None:
        return None
    if mp not in scope_cache:
        scope_cache[mp] = build_scopes(mp)
    qual = enclosing_qualname(scope_cache[mp], line)
    if qual == "<module>":
        # def at module top: enclosing scope IS the def, so this should not happen;
        # guard by using the leaf name.
        qual = getattr(name_obj, "name", "<module>")
    return (rel, qual)


def build_call_graph(worktree: Path, *, progress: bool = True) -> CallGraph:
    import jedi

    cg = CallGraph(worktree=str(worktree))
    project = jedi.Project(str(worktree))
    scope_cache: dict[Path, list[Scope]] = {}
    files = list(_iter_py(worktree))
    t0 = time.time()
    for i, path in enumerate(files):
        if path not in scope_cache:
            scope_cache[path] = build_scopes(path)
        scopes = scope_cache[path]
        try:
            rel = str(path.relative_to(worktree))
        except ValueError:
            continue
        # register every defined scope as a node (so isolated defs still exist)
        for s in scopes:
            node = (rel, s.qualname)
            cg.nodes.add(node)
            leaf = s.qualname.rsplit(".", 1)[-1]
            cg.by_name.setdefault(leaf, set()).add(node)
        sites = enumerate_call_sites(path, scopes)
        try:
            script = jedi.Script(path=str(path), project=project)
        except Exception:
            continue
        for cs in sites:
            try:
                targets = script.goto(cs.line, cs.col, follow_imports=True,
                                       follow_builtin_imports=False)
            except Exception:
                continue
            for t in targets:
                callee = _def_node_for(t, worktree, scope_cache)
                if callee is None:
                    continue
                cg.add_edge((rel, cs.caller_qual), callee)
        if progress and (i + 1) % 20 == 0:
            print(f"  [oracle] {i + 1}/{len(files)} files  "
                  f"edges={sum(len(v) for v in cg.fwd.values())}  "
                  f"{time.time() - t0:.0f}s", flush=True)
    if progress:
        print(f"  [oracle] DONE {len(files)} files  nodes={len(cg.nodes)}  "
              f"edges={sum(len(v) for v in cg.fwd.values())}  {time.time() - t0:.0f}s",
              flush=True)
    return cg


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _digest(worktree: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(_iter_py(worktree)):
        try:
            st = p.stat()
            h.update(str(p).encode())
            h.update(str(int(st.st_mtime)).encode())
            h.update(str(st.st_size).encode())
        except OSError:
            continue
    return h.hexdigest()[:16]


def _cache_path(worktree: Path) -> Path:
    return worktree / ".nav_oracle_cache.json"


def load_or_build(worktree: Path, *, rebuild: bool = False) -> CallGraph:
    cp = _cache_path(worktree)
    dig = _digest(worktree)
    if cp.exists() and not rebuild:
        try:
            raw = json.loads(cp.read_text())
            if raw.get("digest") == dig:
                cg = CallGraph(worktree=str(worktree))
                for u, v in raw["edges"]:
                    cg.add_edge(tuple(u), tuple(v))
                for n in raw.get("nodes", []):
                    cg.nodes.add(tuple(n))
                    leaf = tuple(n)[1].rsplit(".", 1)[-1]
                    cg.by_name.setdefault(leaf, set()).add(tuple(n))
                print(f"  [oracle] loaded cache {cp.name} "
                      f"(nodes={len(cg.nodes)} edges={sum(len(v) for v in cg.fwd.values())})")
                return cg
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
    cg = build_call_graph(worktree)
    edges = [[list(u), list(v)] for u, vs in cg.fwd.items() for v in vs]
    cp.write_text(json.dumps({
        "digest": dig,
        "nodes": [list(n) for n in sorted(cg.nodes)],
        "edges": edges,
    }))
    print(f"  [oracle] wrote cache {cp.name} ({len(edges)} edges)")
    return cg


def _distinctive(qual: str, generic: set[str]) -> bool:
    leaf = qual.rsplit(".", 1)[-1]
    return (len(leaf) >= 5 and not leaf.startswith("_")
            and leaf not in generic and leaf.lower() not in generic)


def generate_questions(
    cg: CallGraph, worktree: Path, *, seed: int, per_type: int, depth: int = 3,
) -> list[dict]:
    """Graph-blind question universe sampled from the INDEPENDENT oracle (never
    from FalkorDB). One question per symbol/type with cardinality bands so we
    measure navigation, not list-enumeration (prereg + rubber-duck §3).

      callers      1-hop : gold-set size 3..30
      callees      1-hop : gold-set size 3..30
      blast_radius >=2hop: reverse closure(<=depth) size 5..50 AND > indeg
                           (genuine multi-hop, not just the 1-hop caller set)
      path         >=2hop: B reachable from A with path length >=3 nodes;
                           plus a few unreachable negatives.

    Single-definition gate (find_definitions) keeps the question referent
    unambiguous and the leaf name usable as a graph/agent lookup key.
    """
    import random
    from bench.runners.struct_query_bench import _GENERIC

    rng = random.Random(seed)
    # cache single-def leaf names to avoid repeated ast scans
    def_cache: dict[str, int] = {}

    def single_def(leaf: str) -> bool:
        if leaf not in def_cache:
            def_cache[leaf] = len(find_definitions(worktree, leaf))
        return def_cache[leaf] == 1

    nodes = sorted(cg.nodes)
    rng.shuffle(nodes)

    def _is_test(node: Node) -> bool:
        rel, qual = node
        leaf = qual.rsplit(".", 1)[-1]
        return ("/test" in rel or rel.startswith("test")
                or "/tests/" in rel or leaf.startswith("test_")
                or "conftest" in rel)

    # subject pool excludes test/fixture nodes — graph value lives in library code
    nodes = [n for n in nodes if not _is_test(n)]

    def phrase_set(node: Node) -> dict:
        return {"path": node[0], "qualname": node[1]}

    out: list[dict] = []

    # ---- callers (1-hop reverse) ----
    picked = 0
    for n in nodes:
        if picked >= per_type:
            break
        rel, qual = n
        leaf = qual.rsplit(".", 1)[-1]
        if not _distinctive(qual, _GENERIC):
            continue
        callers = cg.predecessors(n)
        if not (3 <= len(callers) <= 30):
            continue
        if not single_def(leaf):
            continue
        out.append({
            "id": f"callers::{rel}::{qual}",
            "type": "callers", "hop": "1hop",
            "symbol": {"path": rel, "qualname": qual, "leaf": leaf},
            "question": (f"List every function that directly CALLS the function "
                         f"`{qual}` (defined in `{rel}`). Return the caller functions."),
            "gold": [phrase_set(c) for c in sorted(callers)],
        })
        picked += 1

    # ---- callees (1-hop forward) ----
    picked = 0
    for n in nodes:
        if picked >= per_type:
            break
        rel, qual = n
        leaf = qual.rsplit(".", 1)[-1]
        if not _distinctive(qual, _GENERIC):
            continue
        callees = cg.successors(n)
        if not (3 <= len(callees) <= 30):
            continue
        if not single_def(leaf):
            continue
        out.append({
            "id": f"callees::{rel}::{qual}",
            "type": "callees", "hop": "1hop",
            "symbol": {"path": rel, "qualname": qual, "leaf": leaf},
            "question": (f"List every function that the function `{qual}` "
                         f"(defined in `{rel}`) directly CALLS. Return the callee functions."),
            "gold": [phrase_set(c) for c in sorted(callees)],
        })
        picked += 1

    # ---- blast_radius (>=2-hop reverse closure) ----
    picked = 0
    for n in nodes:
        if picked >= per_type:
            break
        rel, qual = n
        leaf = qual.rsplit(".", 1)[-1]
        if not _distinctive(qual, _GENERIC):
            continue
        indeg = len(cg.predecessors(n))
        closure = cg.reverse_closure(n, depth)
        if not (5 <= len(closure) <= 50):
            continue
        if len(closure) <= indeg:  # must extend beyond the 1-hop caller set
            continue
        if not single_def(leaf):
            continue
        out.append({
            "id": f"blast::{rel}::{qual}",
            "type": "blast_radius", "hop": "multihop",
            "symbol": {"path": rel, "qualname": qual, "leaf": leaf},
            "question": (f"If the signature/behaviour of `{qual}` (defined in `{rel}`) "
                         f"changes, which functions are potentially AFFECTED? Include all "
                         f"functions that reach `{qual}` through up to {depth} levels of "
                         f"calls (transitive callers)."),
            "gold": [phrase_set(c) for c in sorted(closure)],
            "depth": depth,
        })
        picked += 1

    # ---- path (>=2-hop forward reachability) — ~half positive, ~half negative ----
    n_pos = (per_type + 1) // 2
    n_neg = per_type - n_pos
    picked = 0
    src_pool = [n for n in nodes if cg.successors(n) and _distinctive(n[1], _GENERIC)]
    attempts = 0
    seen_pairs: set[tuple[Node, Node]] = set()
    while picked < n_pos and attempts < len(src_pool) * 4 and src_pool:
        attempts += 1
        a = rng.choice(src_pool)
        # forward reachable nodes within a few hops
        reach: list[Node] = []
        frontier = deque([(a, 0)])
        seen = {a}
        while frontier:
            cur, d = frontier.popleft()
            if d >= 5:
                continue
            for v in cg.fwd.get(cur, set()):
                if v not in seen:
                    seen.add(v)
                    if d + 1 >= 2:
                        reach.append(v)
                    frontier.append((v, d + 1))
        reach = [b for b in reach if _distinctive(b[1], _GENERIC) and not _is_test(b)]
        if not reach:
            continue
        b = rng.choice(reach)
        if (a, b) in seen_pairs:
            continue
        path = cg.forward_path(a, b)
        if path is None or len(path) < 3:
            continue
        if not (single_def(a[1].rsplit(".", 1)[-1]) and single_def(b[1].rsplit(".", 1)[-1])):
            continue
        seen_pairs.add((a, b))
        out.append({
            "id": f"path::{a[0]}::{a[1]}->{b[0]}::{b[1]}",
            "type": "path", "hop": "multihop",
            "symbol": {"source": {"path": a[0], "qualname": a[1], "leaf": a[1].rsplit('.', 1)[-1]},
                       "target": {"path": b[0], "qualname": b[1], "leaf": b[1].rsplit('.', 1)[-1]}},
            "question": (f"Is there a chain of function calls starting from `{a[1]}` "
                         f"(in `{a[0]}`) that eventually reaches `{b[1]}` (in `{b[0]}`)? "
                         f"If yes, give one such call path."),
            "gold": {"reachable": True, "path": [phrase_set(p) for p in path]},
        })
        picked += 1

    # negatives: A,B both real symbols with NO forward path A->B
    picked_neg = 0
    cand = [n for n in nodes if _distinctive(n[1], _GENERIC) and not _is_test(n)]
    attempts = 0
    while picked_neg < n_neg and attempts < len(cand) * 8 and len(cand) > 2:
        attempts += 1
        a = rng.choice(cand)
        b = rng.choice(cand)
        if a == b or (a, b) in seen_pairs:
            continue
        # require a has outgoing edges (otherwise trivially unreachable)
        if not cg.successors(a):
            continue
        if cg.forward_path(a, b) is not None:
            continue
        if not (single_def(a[1].rsplit(".", 1)[-1]) and single_def(b[1].rsplit(".", 1)[-1])):
            continue
        seen_pairs.add((a, b))
        out.append({
            "id": f"path::{a[0]}::{a[1]}->{b[0]}::{b[1]}",
            "type": "path", "hop": "multihop",
            "symbol": {"source": {"path": a[0], "qualname": a[1], "leaf": a[1].rsplit('.', 1)[-1]},
                       "target": {"path": b[0], "qualname": b[1], "leaf": b[1].rsplit('.', 1)[-1]}},
            "question": (f"Is there a chain of function calls starting from `{a[1]}` "
                         f"(in `{a[0]}`) that eventually reaches `{b[1]}` (in `{b[0]}`)? "
                         f"If yes, give one such call path."),
            "gold": {"reachable": False, "path": []},
        })
        picked_neg += 1

    return out


def _stats(cg: CallGraph, depth: int) -> dict:
    indeg = [len(cg.rev.get(n, set())) for n in cg.nodes]
    outdeg = [len(cg.fwd.get(n, set())) for n in cg.nodes]
    import statistics as st
    nz_in = [d for d in indeg if d]
    nz_out = [d for d in outdeg if d]
    return {
        "nodes": len(cg.nodes),
        "edges": sum(outdeg),
        "nodes_with_callers": len(nz_in),
        "nodes_with_callees": len(nz_out),
        "median_indeg_nz": st.median(nz_in) if nz_in else 0,
        "median_outdeg_nz": st.median(nz_out) if nz_out else 0,
        "max_indeg": max(indeg) if indeg else 0,
        "max_outdeg": max(outdeg) if outdeg else 0,
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--worktree", required=True, type=Path)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--questions", type=int, default=0,
                    help="if >0, generate this many questions PER TYPE and write --out")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    wt = args.worktree.resolve()
    cg = load_or_build(wt, rebuild=args.rebuild)
    print(json.dumps(_stats(cg, args.depth), indent=2, default=str))
    if args.questions:
        qs = generate_questions(cg, wt, seed=args.seed, per_type=args.questions, depth=args.depth)
        from collections import Counter
        byt = Counter(q["type"] for q in qs)
        byh = Counter(q["hop"] for q in qs)
        print(f"\ngenerated {len(qs)} questions  by_type={dict(byt)}  by_hop={dict(byh)}")
        for q in qs:
            if q["type"] == "path":
                gold = "reachable" if q["gold"]["reachable"] else "no-path"
                print(f"  [{q['type']:12} {q['hop']:8}] {q['id'][:70]}  gold={gold}")
            else:
                print(f"  [{q['type']:12} {q['hop']:8}] {q['symbol']['qualname']:32} gold_n={len(q['gold'])}")
        if args.out:
            Path(args.out).write_text(json.dumps({"worktree": str(wt), "questions": qs}, indent=2))
            print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
