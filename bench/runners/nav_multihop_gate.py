"""Agentless answerability/compression gate for the multi-hop nav experiment (Lane 2).

This is the FREE gate that runs BEFORE any premium agent spend. For each generated
question (callers / callees / blast_radius / path) it computes three things:

  (a) ORACLE gold        -- already embedded in the question record (jedi-based,
                            graph-independent; see nav_multihop_oracle.py).
  (b) CODE_GRAPH answer  -- a single Cypher query over the fixed-resolver CALLS
                            graph (1-hop reverse/forward, [:CALLS*1..3] closure, or
                            shortestPath) mapped to the SAME (relpath, qualname)
                            identity the oracle uses, plus the byte/token size of
                            that compact structured answer.
  (c) NO-TOOL grep       -- the raw `grep -rn "<leaf>"` evidence the un-tooled agent
                            must scan, plus the FILE set grep trivially yields.

We then score set-F1 (qualname-level AND file-level) of the graph answer vs the
oracle, and compare evidence-token compactness graph-vs-grep. The GATE DECISION:
if code_graph is not both compact AND correct -- especially on the >=2-hop
questions (blast_radius, path) where grep is expensive and wrong -- do NOT spend
premium on the agent arm.

Usage:
  .venv/bin/python -m bench.runners.nav_multihop_gate \
      --questions /tmp/ux_questions.json \
      --graph code:mh_uxarray:_default --worktree <path> [--port 6380] [--out gate.json]
"""
from __future__ import annotations

import argparse
import json
import re
import statistics as st
import subprocess
from pathlib import Path
from typing import Any, Optional

from bench.runners.struct_query_bench import _graph_query
from bench.runners.nav_oracle_bench import Scope, build_scopes, enclosing_qualname


# ---------------------------------------------------------------------------
# token estimate (chars/4 heuristic, consistent across graph & grep so the
# RELATIVE compactness comparison is fair regardless of the absolute tokenizer)
# ---------------------------------------------------------------------------

def _toks(s: str) -> int:
    return (len(s) + 3) // 4


# ---------------------------------------------------------------------------
# graph -> (relpath, qualname) mapping, shared by all query types
# ---------------------------------------------------------------------------

def _map_nodes(rows: list[list[Any]], worktree: Path,
               scope_cache: dict[Path, list[Scope]]) -> set[tuple[str, str]]:
    """rows are [name, path, src_start]; map each to (relpath, enclosing qualname)."""
    out: set[tuple[str, str]] = set()
    for row in rows:
        if len(row) < 2 or row[0] is None or row[1] is None:
            continue
        nm, pth = str(row[0]), str(row[1])
        start = int(row[2]) if len(row) > 2 and row[2] is not None else None
        mp = Path(pth)
        try:
            rel = str(mp.relative_to(worktree))
        except ValueError:
            rel = mp.name
        qual = nm
        if start is not None and mp.exists():
            if mp not in scope_cache:
                scope_cache[mp] = build_scopes(mp)
            q = enclosing_qualname(scope_cache[mp], start)
            if q != "<module>":
                qual = q
        out.add((rel, qual))
    return out


def _subject_match(leaf: str, subj_path: str) -> str:
    """Cypher predicate selecting the subject node by leaf name + def path suffix."""
    leaf_q = leaf.replace("'", "\\'")
    path_q = subj_path.replace("'", "\\'")
    return f"s.name = '{leaf_q}' AND s.path ENDS WITH '{path_q}'"


def graph_callers(graph, port, leaf, subj_path, worktree, sc):
    cy = (f"MATCH (c)-[:CALLS]->(s) WHERE {_subject_match(leaf, subj_path)} "
          "RETURN DISTINCT c.name, c.path, c.src_start")
    return _map_nodes(_graph_query(graph, cy, port), worktree, sc)


def graph_callees(graph, port, leaf, subj_path, worktree, sc):
    cy = (f"MATCH (s)-[:CALLS]->(c) WHERE {_subject_match(leaf, subj_path)} "
          "RETURN DISTINCT c.name, c.path, c.src_start")
    return _map_nodes(_graph_query(graph, cy, port), worktree, sc)


def graph_blast(graph, port, leaf, subj_path, worktree, sc, depth=3):
    cy = (f"MATCH (c)-[:CALLS*1..{depth}]->(s) WHERE {_subject_match(leaf, subj_path)} "
          "RETURN DISTINCT c.name, c.path, c.src_start")
    return _map_nodes(_graph_query(graph, cy, port), worktree, sc)


def graph_reachable(graph, port, src_leaf, src_path, dst_leaf, dst_path, depth=8):
    cy = (
        f"MATCH (a) WHERE a.name='{src_leaf}' AND a.path ENDS WITH '{src_path}' "
        f"MATCH (b) WHERE b.name='{dst_leaf}' AND b.path ENDS WITH '{dst_path}' "
        f"WITH a, b MATCH p = (a)-[:CALLS*1..{depth}]->(b) RETURN count(p) > 0 LIMIT 1"
    )
    rows = _graph_query(graph, cy, port)
    if rows and rows[0]:
        v = rows[0][0]
        if isinstance(v, str):
            return v.strip().lower() == "true"
        return bool(v)
    return False


# ---------------------------------------------------------------------------
# no-tool grep baseline
# ---------------------------------------------------------------------------

def grep_evidence(leaf: str, worktree: Path) -> tuple[str, set[str]]:
    """Return (raw grep output the agent must scan, set of files containing `leaf`)."""
    try:
        res = subprocess.run(
            ["grep", "-rn", "--include=*.py", r"\b" + re.escape(leaf) + r"\b", str(worktree)],
            capture_output=True, text=True, timeout=60,
        )
        raw = res.stdout
    except Exception:
        raw = ""
    files: set[str] = set()
    for ln in raw.splitlines():
        fp = ln.split(":", 1)[0]
        try:
            files.add(str(Path(fp).relative_to(worktree)))
        except ValueError:
            files.add(Path(fp).name)
    return raw, files


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

def _prf(pred: set, gold: set) -> dict[str, float]:
    tp = len(pred & gold)
    fp = len(pred - gold)
    fn = len(gold - pred)
    p = tp / (tp + fp) if (tp + fp) else (1.0 if not fn else 0.0)
    r = tp / (tp + fn) if (tp + fn) else (1.0 if not fp else 0.0)
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": round(p, 3), "recall": round(r, 3), "f1": round(f1, 3)}


def _gold_set(q: dict) -> set[tuple[str, str]]:
    return {(g["path"], g["qualname"]) for g in q["gold"]}


def _files(s: set[tuple[str, str]]) -> set[str]:
    return {p for p, _ in s}


def run(questions_path: Path, graph: str, worktree: Path, port: int) -> dict:
    data = json.loads(questions_path.read_text())
    qs = data["questions"]
    sc: dict[Path, list[Scope]] = {}
    rows: list[dict] = []

    for q in qs:
        typ = q["type"]
        rec: dict[str, Any] = {"id": q["id"], "type": typ, "hop": q["hop"]}

        if typ == "path":
            srt, dst = q["symbol"]["source"], q["symbol"]["target"]
            gold_reach = q["gold"]["reachable"]
            pred_reach = graph_reachable(
                graph, port, srt["leaf"], srt["path"], dst["leaf"], dst["path"])
            rec["gold_reachable"] = gold_reach
            rec["graph_reachable"] = pred_reach
            rec["correct"] = (pred_reach == gold_reach)
            # graph evidence = a single bool + the path; grep cannot answer reachability
            rec["graph_tokens"] = _toks(json.dumps({"reachable": pred_reach}))
            graw, _ = grep_evidence(srt["leaf"], worktree)
            graw2, _ = grep_evidence(dst["leaf"], worktree)
            rec["grep_tokens"] = _toks(graw) + _toks(graw2)
            rows.append(rec)
            continue

        leaf = q["symbol"]["leaf"]
        subj_path = q["symbol"]["path"]
        gold = _gold_set(q)

        if typ == "callers":
            pred = graph_callers(graph, port, leaf, subj_path, worktree, sc)
        elif typ == "callees":
            pred = graph_callees(graph, port, leaf, subj_path, worktree, sc)
        elif typ == "blast_radius":
            pred = graph_blast(graph, port, leaf, subj_path, worktree, sc,
                               depth=q.get("depth", 3))
        else:
            continue

        rec["qual_prf"] = _prf(pred, gold)
        rec["file_prf"] = _prf(_files(pred), _files(gold))
        # graph evidence the agent reads = the compact structured answer
        graph_ans = json.dumps(sorted([{"path": p, "qualname": qn} for p, qn in pred],
                                      key=lambda d: (d["path"], d["qualname"])))
        rec["graph_tokens"] = _toks(graph_ans)
        rec["graph_n"] = len(pred)
        rec["gold_n"] = len(gold)
        # grep baseline: raw evidence size + the file recall it trivially yields
        graw, gfiles = grep_evidence(leaf, worktree)
        rec["grep_tokens"] = _toks(graw)
        rec["grep_file_recall"] = round(
            len(gfiles & _files(gold)) / len(_files(gold)), 3) if _files(gold) else 1.0
        rows.append(rec)

    return {"graph": graph, "worktree": str(worktree),
            "n": len(rows), "rows": rows}


def _agg(rows, types, key, sub=None):
    vals = []
    for r in rows:
        if r["type"] not in types:
            continue
        v = r.get(key)
        if sub and isinstance(v, dict):
            v = v.get(sub)
        if isinstance(v, (int, float)):
            vals.append(v)
    return round(st.mean(vals), 3) if vals else None


def report(res: dict) -> None:
    rows = res["rows"]
    print(f"\n=== AGENTLESS MULTI-HOP GATE === graph={res['graph']}  n={res['n']}\n")

    setq = ["callers", "callees", "blast_radius"]
    print("SET QUESTIONS (graph CALLS answer vs jedi oracle):")
    print(f"{'type':<14}{'qF1':>7}{'fileF1':>8}{'qRec':>7}{'qPrec':>7}"
          f"{'gTok':>8}{'grepTok':>9}{'grepFRec':>9}")
    for t in setq:
        trows = [r for r in rows if r["type"] == t]
        if not trows:
            continue
        print(f"{t:<14}"
              f"{_agg(rows,[t],'qual_prf','f1'):>7}"
              f"{_agg(rows,[t],'file_prf','f1'):>8}"
              f"{_agg(rows,[t],'qual_prf','recall'):>7}"
              f"{_agg(rows,[t],'qual_prf','precision'):>7}"
              f"{_agg(rows,[t],'graph_tokens'):>8.0f}"
              f"{_agg(rows,[t],'grep_tokens'):>9.0f}"
              f"{_agg(rows,[t],'grep_file_recall'):>9}")

    prows = [r for r in rows if r["type"] == "path"]
    if prows:
        corr = sum(1 for r in prows if r["correct"])
        print(f"\nPATH QUESTIONS (reachability bool, graph shortestPath vs oracle):")
        print(f"  correct {corr}/{len(prows)}  "
              f"avg graph_tokens={_agg(rows,['path'],'graph_tokens'):.0f}  "
              f"avg grep_tokens={_agg(rows,['path'],'grep_tokens'):.0f}")

    # gate signal: compactness ratio + correctness on >=2-hop
    multihop = [r for r in rows if r["hop"] == "multihop" and "qual_prf" in r]
    if multihop:
        print(f"\n>=2-HOP (blast_radius) qF1={_agg(rows,['blast_radius'],'qual_prf','f1')} "
              f"fileF1={_agg(rows,['blast_radius'],'file_prf','f1')}")
    print()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--worktree", required=True)
    ap.add_argument("--port", type=int, default=6380)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    res = run(Path(a.questions), a.graph, Path(a.worktree), a.port)
    report(res)
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1))
        print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
