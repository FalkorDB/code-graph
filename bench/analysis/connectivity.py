"""Graph-connectivity stratification for the localization benchmark.

WHY: ``swe_bench.is_structural`` only checks that the gold patch spans >=2 files
or >=2 directories. It does NOT verify that those gold files are actually
connected in the code graph. So an instance like ``jupyterhub__oauthenticator-764``
(gold = ``oauthenticator/google.py`` + ``setup.py``) counts as "structural" even
though ``setup.py`` has no code edges to the auth module — code_graph cannot
surface it via structure by construction. Evaluating a graph-traversal tool on
such instances dilutes signal and makes false negatives uninterpretable.

This module assigns each instance a ``graph_connected_gold`` label computed from
the STATIC graph edges (independent of ``search_code`` ranking, to avoid
circularity). The label answers: "does the graph even contain a structural path
between the gold files?" — i.e. is there structural signal available for the
tool to exploit, separate from whether the agent adopts it.

PRE-REGISTERED DEFINITION (fixed before reading results):
  * Edge set for file<->file adjacency (undirected):
      - direct:        File -[IMPORTS]- File
      - symbol-bridge: File -[DEFINES]-> sym -[CALLS|EXTENDS|OVERRIDES]- sym <-[DEFINES]- File
  * Max depth: D = 2 file-hops.
  * Labels:
      - gold_missing      : >=1 gold file is not present as a File node in the graph
      - all_connected     : all present gold files fall in ONE connected component
                            (reachable within <=D hops) -- full structural signal
      - partial_connected : >=1 gold-gold pair connected, but not all -- partial signal
      - unconnected       : >=2 gold files present, no gold-gold pair connected -- NO signal
      - single            : only 1 gold file (no multi-file structure to traverse)

Framing (per rubber-duck): the label means "graph has structural signal
available", NOT "task is inherently structural". Using the same graph that is
under test is acceptable under that framing.

Offline: reads gold files from the benchmark results.jsonl; queries the already
-indexed FalkorDB graphs on port 6380. No HuggingFace reload, no LLM, $0.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import redis

FALKOR_HOST = "localhost"
FALKOR_PORT = 6380
GRAPH_FMT = "code:{task}__loc:_default"

# Pre-registered traversal parameters.
MAX_DEPTH = 2          # file-level hops
NEIGHBOR_CAP = 500     # per-query fanout cap (guards hub files); flagged if hit
VISIT_CAP = 8000       # total BFS frontier cap per source file

_IMPORTS_Q = (
    "MATCH (a:File)-[:IMPORTS]-(b:File) WHERE a.path = $p AND b.path <> $p "
    "RETURN DISTINCT b.path LIMIT $cap"
)
_BRIDGE_Q = (
    "MATCH (a:File)-[:DEFINES]->(s)-[:CALLS|EXTENDS|OVERRIDES]-(t)"
    "<-[:DEFINES]-(b:File) WHERE a.path = $p AND b.path <> a.path "
    "RETURN DISTINCT b.path LIMIT $cap"
)


def _graph_query(r: redis.Redis, graph: str, cypher: str, params: dict):
    """Run a parameterized GRAPH.QUERY (FalkorDB ``CYPHER k=v`` prefix)."""
    parts = []
    for k, v in params.items():
        if isinstance(v, str):
            esc = v.replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'{k}="{esc}"')
        else:
            parts.append(f"{k}={v}")
    prefix = ("CYPHER " + " ".join(parts) + " ") if parts else ""
    return r.execute_command("GRAPH.QUERY", graph, prefix + cypher)


def _all_file_paths(r: redis.Redis, graph: str) -> list[str]:
    res = _graph_query(r, graph, "MATCH (f:File) RETURN f.path", {})
    return [row[0] for row in res[1]]


def _resolve_gold(gold_files: list[str], file_paths: list[str]) -> dict[str, str | None]:
    """Map each repo-relative gold path to its absolute File-node path.

    File nodes store absolute paths ending in ``.../<task>__loc/<relpath>``; we
    match by suffix ``/<relpath>``. If multiple nodes match (shouldn't for a
    full relpath), prefer the shortest. Returns ``{gold: node_path | None}``.
    """
    out: dict[str, str | None] = {}
    for g in gold_files:
        suffix = "/" + g.lstrip("/")
        cands = [p for p in file_paths if p.endswith(suffix)]
        out[g] = min(cands, key=len) if cands else None
    return out


def _file_neighbors(r: redis.Redis, graph: str, fpath: str,
                    cap: int = NEIGHBOR_CAP) -> tuple[set[str], bool]:
    """1-hop file neighbors of ``fpath`` (IMPORTS + symbol-bridge). Returns
    ``(neighbors, capped)`` where ``capped`` flags a fanout-limit hit."""
    out: set[str] = set()
    capped = False
    for cypher in (_IMPORTS_Q, _BRIDGE_Q):
        res = _graph_query(r, graph, cypher, {"p": fpath, "cap": cap})
        rows = res[1]
        if len(rows) >= cap:
            capped = True
        out.update(row[0] for row in rows)
    out.discard(fpath)
    return out, capped


def _reachable(r: redis.Redis, graph: str, src: str, targets: set[str],
               depth: int = MAX_DEPTH) -> set[str]:
    """BFS up to ``depth`` file-hops from ``src``; return the subset of
    ``targets`` reached. Early-exits once all targets are found."""
    found: set[str] = set()
    visited = {src}
    frontier = {src}
    for _ in range(depth):
        nxt: set[str] = set()
        for node in frontier:
            neigh, _capped = _file_neighbors(r, graph, node)
            for n in neigh:
                if n in targets:
                    found.add(n)
                if n not in visited:
                    visited.add(n)
                    nxt.add(n)
            if len(visited) > VISIT_CAP:
                break
        if found >= targets or len(visited) > VISIT_CAP:
            break
        frontier = nxt
    return found


class _UF:
    def __init__(self, items):
        self.p = {i: i for i in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)

    def groups(self):
        g = defaultdict(list)
        for i in self.p:
            g[self.find(i)].append(i)
        return list(g.values())


def classify_instance(r: redis.Redis, task: str, gold_files: list[str]) -> dict:
    """Compute the connectivity stratum for one instance."""
    graph = GRAPH_FMT.format(task=task)
    py_gold = [g for g in gold_files if g.endswith(".py")]
    result = {
        "task": task,
        "gold_files": gold_files,
        "n_gold": len(gold_files),
        "n_gold_py": len(py_gold),
    }
    try:
        file_paths = _all_file_paths(r, graph)
    except redis.exceptions.ResponseError as e:
        result["label"] = "graph_missing"
        result["error"] = str(e)
        return result

    resolved = _resolve_gold(gold_files, file_paths)
    present = {g: p for g, p in resolved.items() if p}
    missing = [g for g, p in resolved.items() if not p]
    result["gold_present"] = sorted(present)
    result["gold_missing_from_graph"] = sorted(missing)

    if len(gold_files) < 2:
        result["label"] = "single"
        return result
    if missing:
        # Still compute connectivity among the present ones for context, but the
        # instance cannot be fully won via structure.
        result["label"] = "gold_missing"

    # pairwise connectivity among present gold files via union-find
    present_paths = present  # {gold_rel: node_path}
    target_by_node = {p: g for g, p in present_paths.items()}
    uf = _UF(list(present_paths))
    edges: list[tuple[str, str]] = []
    glist = list(present_paths.items())
    for i, (g_a, p_a) in enumerate(glist):
        others = {p for _, p in glist if p != p_a}
        if not others:
            continue
        reached = _reachable(r, graph, p_a, others)
        for node in reached:
            g_b = target_by_node[node]
            uf.union(g_a, g_b)
            edges.append((g_a, g_b))
    comps = uf.groups()
    result["components"] = [sorted(c) for c in comps]
    result["connected_pairs"] = sorted({tuple(sorted(e)) for e in edges})
    result["isolated_gold"] = sorted(
        g for c in comps if len(c) == 1 for g in c
    )

    if missing:
        return result  # label already 'gold_missing'
    if len(comps) == 1:
        result["label"] = "all_connected"
    elif edges:
        result["label"] = "partial_connected"
    else:
        result["label"] = "unconnected"
    return result


def load_gold_from_results(results_path: Path) -> dict[str, list[str]]:
    """Extract ``{task_id: gold_files}`` from a benchmark results.jsonl."""
    gold: dict[str, list[str]] = {}
    for line in results_path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        tid = row.get("task_id") or row.get("instance_id")
        if tid and row.get("gold_files"):
            gold[tid] = row["gold_files"]
    return gold


def classify_results(results_path: Path,
                     host: str = FALKOR_HOST, port: int = FALKOR_PORT) -> list[dict]:
    r = redis.Redis(host=host, port=port, decode_responses=True)
    gold = load_gold_from_results(results_path)
    return [classify_instance(r, task, g) for task, g in sorted(gold.items())]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results", type=Path, help="path to results.jsonl")
    ap.add_argument("--json", type=Path, help="write full classification JSON here")
    ap.add_argument("--port", type=int, default=FALKOR_PORT)
    args = ap.parse_args()

    rows = classify_results(args.results, port=args.port)

    print(f"{'task':34s} {'label':18s} {'gold':4s} present/connected")
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["label"]] += 1
        present = len(row.get("gold_present", []))
        comps = row.get("components", [])
        conn = "-" if not comps else "+".join(str(len(c)) for c in sorted(comps, key=len, reverse=True))
        miss = row.get("gold_missing_from_graph", [])
        flag = f"  MISSING:{','.join(Path(m).name for m in miss)}" if miss else ""
        print(f"{row['task']:34s} {row['label']:18s} {row['n_gold']:<4d} "
              f"{present}/[{conn}]{flag}")
    print("\nstratum counts:")
    for label, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {label:18s} {n}")

    if args.json:
        args.json.write_text(json.dumps(rows, indent=2))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
