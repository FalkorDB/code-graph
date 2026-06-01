"""Offline intrinsic-retrieval probe (Phase A fix #1 go/no-go).

Question: is the gold file findable from the graph's CONTENT, and how much
better is a `description -> file` retriever than today's name-prefix interface?

This isolates RETRIEVAL QUALITY from AGENT BEHAVIOR. No agent, no LLM, no API
tokens. For each of the 20 no-leak structural-hard SWE-bench instances we take
the problem statement as the query and rank the repo's files using retrievers
built directly over the already-indexed FalkorDB graph (port 6380), then score
recall@k / MRR against the gold (patched) files.

Retriever arms:
  - name_prefix : emulates current `auto_complete`/`find-symbol` interface --
                  pull identifier-ish tokens from the issue, prefix-match symbol
                  names, rank files by # matching symbols. (current floor)
  - bm25        : Okapi BM25 over per-file text (path + symbol names + bodies).
  - tfidf       : TF-IDF cosine over the same per-file text.

All retrievers are pure-numpy, deterministic, $0. BM25/TF-IDF are the proxy for
the candidate `search_semantic` primitive (production could use embeddings for
additional lift; lexical already establishes the ceiling/floor gap).
"""

from __future__ import annotations

import math
import re
import sys
from collections import Counter, defaultdict

import numpy as np
import redis

from bench.datasets import swe_bench

FALKOR_PORT = 6380
GRAPH_FMT = "code:{task}__loc:_default"
KS = (1, 3, 5, 10)
PER_FILE_BODY_TOKEN_CAP = 4000  # cap body tokens contributed per file
MIN_PREFIX_LEN = 4              # identifier length floor for name_prefix arm

_word_re = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_camel_re = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+")


def subtokens(ident: str) -> list[str]:
    """Split an identifier into lowercased camelCase/snake_case subtokens
    AND keep the whole lowercased identifier."""
    out: list[str] = []
    for part in ident.split("_"):
        if not part:
            continue
        out.extend(m.group(0).lower() for m in _camel_re.finditer(part))
    out.append(ident.lower())
    return [t for t in out if t]


def tokenize(text: str) -> list[str]:
    toks: list[str] = []
    for m in _word_re.finditer(text or ""):
        toks.extend(subtokens(m.group(0)))
    return toks


def issue_identifiers(text: str) -> list[str]:
    """Candidate code symbols an agent would prefix-search: backticked names,
    dotted paths, and CamelCase / snake_case identifiers in the issue."""
    cands: set[str] = set()
    for m in re.finditer(r"`([^`]+)`", text or ""):
        for ident in _word_re.findall(m.group(1)):
            if len(ident) >= MIN_PREFIX_LEN:
                cands.add(ident)
    for ident in _word_re.findall(text or ""):
        if len(ident) >= MIN_PREFIX_LEN and (
            "_" in ident or re.search(r"[a-z][A-Z]", ident) or ident[0].isupper()
        ):
            cands.add(ident)
    return sorted(cands)


def fetch_graph(r: redis.Redis, task: str):
    """Return (files: list[relpath], file_text: {relpath: token list},
    symbols: list[(name, relpath)]). relpath is repo-relative."""
    g = GRAPH_FMT.format(task=task)
    split_key = f"{task}__loc/"

    def rel(p: str) -> str:
        return p.split(split_key, 1)[-1] if split_key in p else p

    files: list[str] = []
    bodytok: dict[str, list[str]] = defaultdict(list)
    symbols: list[tuple[str, str]] = []

    res = r.execute_command("GRAPH.QUERY", g, "MATCH (f:File) RETURN f.path")
    for row in res[1]:
        rp = rel(row[0])
        files.append(rp)
        bodytok[rp].extend(tokenize(rp.replace("/", " ")))

    # Symbols: name + body (doc). Bodies are source; cap per-file contribution.
    q = "MATCH (n) WHERE n:Function OR n:Class RETURN n.name, n.path, n.doc"
    res = r.execute_command("GRAPH.QUERY", g, q)
    bodycount: Counter = Counter()
    for name, path, doc in res[1]:
        if not path:
            continue
        rp = rel(path)
        if name:
            symbols.append((name, rp))
            bodytok[rp].extend(subtokens(name))
        if doc and bodycount[rp] < PER_FILE_BODY_TOKEN_CAP:
            toks = tokenize(doc)
            take = toks[: PER_FILE_BODY_TOKEN_CAP - bodycount[rp]]
            bodytok[rp].extend(take)
            bodycount[rp] += len(take)

    files = sorted(set(files))
    return files, bodytok, symbols


# ---------- retrievers: return ranked list of relpaths ----------

def rank_name_prefix(query: str, files, bodytok, symbols) -> list[str]:
    cands = [c.lower() for c in issue_identifiers(query)]
    by_file: Counter = Counter()
    # prefix match against symbol names (emulates auto_complete prefix search)
    names = [(n.lower(), f) for n, f in symbols]
    for c in cands:
        for nl, f in names:
            if nl.startswith(c):
                by_file[f] += 1
    return [f for f, _ in by_file.most_common()]


def _build_index(files, bodytok):
    docs = [bodytok[f] for f in files]
    df: Counter = Counter()
    for d in docs:
        for t in set(d):
            df[t] += 1
    return docs, df


def rank_bm25(query, files, bodytok, symbols, k1=1.5, b=0.75) -> list[str]:
    docs, df = _build_index(files, bodytok)
    N = len(docs)
    if N == 0:
        return []
    avgdl = sum(len(d) for d in docs) / N or 1.0
    idf = {t: math.log(1 + (N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
    qtok = set(tokenize(query))
    scores = np.zeros(N)
    for i, d in enumerate(docs):
        if not d:
            continue
        tf = Counter(d)
        dl = len(d)
        s = 0.0
        for t in qtok:
            f = tf.get(t)
            if not f:
                continue
            s += idf.get(t, 0.0) * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
        scores[i] = s
    order = np.argsort(-scores)
    return [files[i] for i in order if scores[i] > 0]


def rank_tfidf(query, files, bodytok, symbols) -> list[str]:
    docs, df = _build_index(files, bodytok)
    N = len(docs)
    if N == 0:
        return []
    vocab = {t: j for j, t in enumerate(df)}
    idf = np.array([math.log((1 + N) / (1 + df[t])) + 1 for t in vocab])
    rows = []
    for d in docs:
        v = np.zeros(len(vocab))
        if d:
            tf = Counter(d)
            for t, c in tf.items():
                j = vocab.get(t)
                if j is not None:
                    v[j] = c / len(d)
        v *= idf
        nrm = np.linalg.norm(v)
        rows.append(v / nrm if nrm else v)
    mat = np.array(rows)
    qv = np.zeros(len(vocab))
    qtf = Counter(tokenize(query))
    for t, c in qtf.items():
        j = vocab.get(t)
        if j is not None:
            qv[j] = c
    qv *= idf
    qn = np.linalg.norm(qv)
    if qn:
        qv /= qn
    scores = mat @ qv
    order = np.argsort(-scores)
    return [files[i] for i in order if scores[i] > 0]


RETRIEVERS = {
    "name_prefix": rank_name_prefix,
    "bm25": rank_bm25,
    "tfidf": rank_tfidf,
}


def score(ranked: list[str], gold: list[str]):
    goldset = set(gold)
    pos = {f: i for i, f in enumerate(ranked)}
    ranks = [pos[g] + 1 for g in gold if g in pos]
    out = {}
    for k in KS:
        topk = set(ranked[:k])
        out[f"recall@{k}"] = len(topk & goldset) / len(goldset) if goldset else 0.0
        out[f"hit@{k}"] = 1.0 if (topk & goldset) else 0.0
    out["mrr"] = 1.0 / min(ranks) if ranks else 0.0
    out["gold_best_rank"] = min(ranks) if ranks else None
    out["gold_found"] = sum(1 for g in gold if g in pos)
    out["n_gold"] = len(gold)
    out["n_files"] = len(ranked)
    return out


def main():
    insts = swe_bench.load_instances()
    sel = swe_bench.select_structural(insts, n=20, no_leak=True)
    r = redis.Redis(host="localhost", port=FALKOR_PORT, decode_responses=True)

    agg: dict[str, list[dict]] = {a: [] for a in RETRIEVERS}
    per_task = []
    for inst in sel:
        task = inst.instance_id
        gold = swe_bench.gold_changed_files(inst.patch, source_only=True)
        gold = [g for g in gold if g.endswith(".py")]
        try:
            files, bodytok, symbols = fetch_graph(r, task)
        except Exception as e:  # noqa: BLE001
            print(f"!! {task}: graph fetch failed: {e}", file=sys.stderr)
            continue
        gold_in_graph = sum(1 for g in gold if g in set(files))
        row = {"task": task, "n_gold": len(gold), "gold_in_graph": gold_in_graph,
               "n_files": len(files)}
        for arm, fn in RETRIEVERS.items():
            ranked = fn(inst.problem_statement, files, bodytok, symbols)
            sc = score(ranked, gold)
            agg[arm].append(sc)
            row[arm] = sc
        per_task.append(row)
        gp = " ".join(
            f"{a}:R@5={row[a]['recall@5']:.2f}/rk={row[a]['gold_best_rank']}"
            for a in RETRIEVERS
        )
        print(f"{task:38s} gold={len(gold)} in_graph={gold_in_graph}/{len(gold)} "
              f"files={len(files):5d} | {gp}")

    print("\n================ AGGREGATE (n={}) ================".format(len(per_task)))
    hdr = f"{'arm':12s}"
    for k in KS:
        hdr += f"  R@{k:<4}"
    for k in KS:
        hdr += f"  hit@{k:<2}"
    hdr += "   MRR"
    print(hdr)
    for arm in RETRIEVERS:
        rows = agg[arm]
        line = f"{arm:12s}"
        for k in KS:
            line += f"  {np.mean([x[f'recall@{k}'] for x in rows]):.3f}"
        for k in KS:
            line += f"  {np.mean([x[f'hit@{k}'] for x in rows]):.3f}"
        line += f"   {np.mean([x['mrr'] for x in rows]):.3f}"
        print(line)

    tot_gold = sum(p["n_gold"] for p in per_task)
    tot_in = sum(p["gold_in_graph"] for p in per_task)
    print(f"\ngold-file coverage in graph: {tot_in}/{tot_gold} "
          f"({100*tot_in/tot_gold:.1f}%)")
    print("\nReference (live agent, Phase A Sonnet): no_mcp recall=0.613 "
          "acc@3=0.95 MRR=0.875 ; code_graph recall=0.512 MRR=0.800")


if __name__ == "__main__":
    main()
