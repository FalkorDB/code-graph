"""Structural-query token-compression benchmark.

Answers the stakeholder question directly, without agent-in-the-loop variance:

    For graph-shaped questions ("who calls symbol S?", "what does S call?",
    "where is S defined?"), how many *context tokens* does the code-graph's
    structured answer consume, versus the raw file/grep evidence an agent
    would otherwise have to read into its context to derive the same answer?

This isolates the one thing a code graph can mechanically do — return compact,
precise structural facts — from the confounds that dominate the agent
benchmarks (the model ignoring the tool, non-convergence on large repos, issue
text leaking the answer). If the graph cannot beat grep on *evidence
compression* here, it cannot save tokens anywhere.

Method (deterministic, no LLM):
  * Connect straight to FalkorDB (the API's graph_entities endpoint caps the
    returned subgraph; the raw store is complete).
  * Sample distinctively-named Function/Class symbols with a meaningful but
    non-pathological caller fan-in.
  * For each symbol and each query type, compute:
      graph_tokens  = tiktoken size of the graph's structured answer
                      (caller/callee/definition list: "name @ relpath:line")
      raw_tokens    = tiktoken size of the evidence an agent reads WITHOUT the
                      graph: `rg -nw <symbol>` over the repo's .py files (the
                      lines it must scan and disambiguate)
      ratio         = raw_tokens / graph_tokens   (>1 => graph saves tokens)
  * Aggregate with paired statistics (median ratio, geometric mean, win-rate),
    never raw sums (one megahub symbol would dominate).

Token counts use tiktoken cl100k as a standard, reproducible proxy for context
size; absolute Claude token counts differ slightly but ratios are stable.

Usage:
    python -m bench.runners.struct_query_bench \
        --repo-graph code:conan-io__conan-16987__loc:_default \
        --worktree bench/cache/worktrees-localize/conan-io__conan-16987__loc \
        --sample 40 --out bench/cache/struct-query/conan.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import statistics as st
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_SEED = 20260526

# Generic method names whose name-based CALLS edges are too noisy to be a
# meaningful "callers of X" answer (every .run()/.get() in the repo links here).
_GENERIC = {
    "run", "get", "set", "__init__", "__call__", "__enter__", "__exit__",
    "setUp", "tearDown", "update", "add", "remove", "append", "load", "save",
    "main", "test", "name", "value", "data", "result", "items", "keys",
    "values", "format", "parse", "build", "make", "create", "close", "open",
    "read", "write", "start", "stop", "send", "recv", "copy", "clear",
}


def _tok(text: str) -> int:
    """tiktoken cl100k token count (reproducible context-size proxy)."""
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def _graph_query(graph: str, cypher: str, port: int) -> list[list[Any]]:
    """Run a Cypher query against FalkorDB, returning structured data rows.

    Uses the redis Python client and FalkorDB's RESP result framing: the reply
    is [header, data_rows, stats]; data_rows is a list of rows, each a list of
    column values. Far more robust than parsing redis-cli text output.
    """
    import redis

    r = redis.Redis(host="127.0.0.1", port=port, decode_responses=True)
    reply = r.execute_command("GRAPH.QUERY", graph, cypher)
    if not isinstance(reply, list) or len(reply) < 2:
        return []
    data = reply[1]
    rows: list[list[Any]] = []
    for row in data:
        rows.append(list(row) if isinstance(row, (list, tuple)) else [row])
    return rows


def _relpath(path: str, worktree: str) -> str:
    try:
        return str(Path(path).relative_to(worktree))
    except ValueError:
        return Path(path).name


def sample_symbols(
    graph: str, port: int, *, n: int, seed: int = DEFAULT_SEED,
    fanin_lo: int = 3, fanin_hi: int = 80,
) -> list[dict[str, Any]]:
    """Distinctively-named Function/Class symbols with meaningful fan-in.

    We band the fan-in: too low (1-2) means grep is already precise (no graph
    headroom); too high (generic megahubs) means the name-based caller list is
    noise. The 3..80 band targets symbols where 'who calls X' is both a real
    question and answerable precisely.
    """
    cypher = (
        "MATCH (c)-[:CALLS]->(s) WHERE s:Searchable "
        f"WITH s.name AS name, count(c) AS fanin "
        f"WHERE fanin >= {fanin_lo} AND fanin <= {fanin_hi} "
        "RETURN name, fanin ORDER BY name"
    )
    rows = _graph_query(graph, cypher, port)
    pairs: list[tuple[str, int]] = []
    for row in rows:
        if len(row) < 2:
            continue
        name, fan = row[0], row[1]
        if not name or name in _GENERIC or str(name).startswith("__"):
            continue
        if len(str(name)) < 4:
            continue
        try:
            pairs.append((str(name), int(fan)))
        except (ValueError, TypeError):
            continue
    rng = random.Random(seed)
    rng.shuffle(pairs)
    return [{"name": nm, "fanin": fn} for nm, fn in pairs[:n]]


def graph_callers_answer(graph: str, port: int, symbol: str, worktree: str) -> str:
    """The structured caller list the graph returns for `who calls <symbol>`."""
    cypher = (
        f"MATCH (c)-[:CALLS]->(s {{name:'{symbol}'}}) "
        "RETURN DISTINCT c.name, c.path ORDER BY c.name LIMIT 200"
    )
    rows = _graph_query(graph, cypher, port)
    lines = []
    for row in rows:
        if len(row) < 2:
            continue
        cname, cpath = row[0], row[1]
        lines.append(f"{cname} @ {_relpath(str(cpath), worktree)}")
    return f"callers of {symbol} ({len(lines)}):\n" + "\n".join(lines)


def grep_evidence(symbol: str, worktree: str) -> str:
    """The raw evidence an agent reads WITHOUT the graph: word-boundary grep
    of the symbol across the repo's Python files (the lines it must scan to
    find and disambiguate real call sites)."""
    out = subprocess.run(
        ["rg", "-nw", "--no-heading", "-g", "*.py", symbol, worktree],
        capture_output=True,
        text=True,
        timeout=120,
    )
    # Strip the absolute worktree prefix to mimic what the agent actually sees
    # (relative paths), so we don't inflate raw tokens with long abs paths.
    return out.stdout.replace(worktree.rstrip("/") + "/", "")


def run(
    graph: str, worktree: str, *, port: int, n: int, seed: int,
) -> list[dict[str, Any]]:
    syms = sample_symbols(graph, port, n=n, seed=seed)
    results = []
    for s in syms:
        name = s["name"]
        g = graph_callers_answer(graph, port, name, worktree)
        r = grep_evidence(name, worktree)
        gt, rt = _tok(g), _tok(r)
        results.append({
            "symbol": name,
            "fanin": s["fanin"],
            "graph_tokens": gt,
            "raw_tokens": rt,
            "ratio": round(rt / gt, 3) if gt else None,
            "grep_hits": r.count("\n"),
        })
    return results


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ratios = [r["ratio"] for r in rows if r["ratio"]]
    wins = sum(1 for x in ratios if x > 1.0)
    geomean = (
        st.geometric_mean(ratios) if ratios else None
    )
    return {
        "n": len(rows),
        "median_ratio": round(st.median(ratios), 3) if ratios else None,
        "geomean_ratio": round(geomean, 3) if geomean else None,
        "win_rate": f"{wins}/{len(ratios)}",
        "median_graph_tokens": int(st.median([r["graph_tokens"] for r in rows])) if rows else 0,
        "median_raw_tokens": int(st.median([r["raw_tokens"] for r in rows])) if rows else 0,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-graph", required=True, help="FalkorDB graph key")
    p.add_argument("--worktree", required=True, help="repo worktree path (for grep + relpaths)")
    p.add_argument("--port", type=int, default=6380)
    p.add_argument("--sample", type=int, default=40)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)

    wt = str(Path(args.worktree).resolve())
    rows = run(args.repo_graph, wt, port=args.port, n=args.sample, seed=args.seed)
    summ = summarize(rows)
    print(json.dumps({"summary": summ}, indent=2))
    for r in sorted(rows, key=lambda x: -(x["ratio"] or 0)):
        print(f"  {r['symbol']:32} fanin={r['fanin']:>4} "
              f"graph={r['graph_tokens']:>5} raw={r['raw_tokens']:>7} "
              f"ratio={r['ratio']}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w") as f:
            f.write(json.dumps({"summary": summ}) + "\n")
            for r in rows:
                f.write(json.dumps(r) + "\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
