"""Semantic-embedding arm for the retrieval probe (Phase A fix #1).

Lexical retrieval (bm25/tfidf in retrieval_probe.py) ~2x the current name-prefix
interface but stays below the live agent's no-tool recall (0.61) on these
pretraining-saturated repos. The deciding question for fix #1 is whether a
SEMANTIC `description -> file` retriever closes that gap.

This embeds per-file text (path + symbol names + truncated bodies/docstrings)
with a small local HF model (no API, $0) and cosine-ranks files against the
problem statement. Same 20 instances, same scoring as retrieval_probe.
"""

from __future__ import annotations

import sys
from collections import Counter

import numpy as np
import redis
import torch
from transformers import AutoModel, AutoTokenizer

from bench.analysis.retrieval_probe import (
    FALKOR_PORT,
    KS,
    fetch_graph,
    score,
)
from bench.datasets import swe_bench

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MAX_LEN = 256
BATCH = 64
PER_FILE_CHARS = 1200  # natural-language-ish snippet per file


def build_file_text(files, bodytok, symbols) -> dict[str, str]:
    """Compose a compact NL-ish description per file: path words + symbol
    names + a bounded slice of body tokens (captures signatures/docstrings)."""
    sym_by_file: dict[str, list[str]] = {}
    for name, f in symbols:
        sym_by_file.setdefault(f, []).append(name)
    out = {}
    for f in files:
        path_words = f.replace("/", " ").replace("_", " ").replace(".py", "")
        names = " ".join(sym_by_file.get(f, [])[:80])
        body = " ".join(bodytok.get(f, [])[:300])
        out[f] = (path_words + " . " + names + " . " + body)[: PER_FILE_CHARS]
    return out


class Embedder:
    def __init__(self):
        self.tok = AutoTokenizer.from_pretrained(MODEL)
        self.model = AutoModel.from_pretrained(MODEL)
        self.model.eval()

    @torch.no_grad()
    def encode(self, texts: list[str]) -> np.ndarray:
        vecs = []
        for i in range(0, len(texts), BATCH):
            batch = texts[i : i + BATCH]
            enc = self.tok(batch, padding=True, truncation=True,
                           max_length=MAX_LEN, return_tensors="pt")
            out = self.model(**enc)
            mask = enc["attention_mask"].unsqueeze(-1).float()
            summed = (out.last_hidden_state * mask).sum(1)
            counts = mask.sum(1).clamp(min=1e-9)
            emb = (summed / counts).cpu().numpy()
            emb /= (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9)
            vecs.append(emb)
        return np.vstack(vecs) if vecs else np.zeros((0, 384))


def main():
    insts = swe_bench.load_instances()
    sel = swe_bench.select_structural(insts, n=20, no_leak=True)
    r = redis.Redis(host="localhost", port=FALKOR_PORT, decode_responses=True)
    emb = Embedder()

    rows = []
    for inst in sel:
        task = inst.instance_id
        gold = [g for g in swe_bench.gold_changed_files(inst.patch, source_only=True)
                if g.endswith(".py")]
        try:
            files, bodytok, symbols = fetch_graph(r, task)
        except Exception as e:  # noqa: BLE001
            print(f"!! {task}: {e}", file=sys.stderr)
            continue
        text = build_file_text(files, bodytok, symbols)
        doc_vecs = emb.encode([text[f] for f in files])
        qv = emb.encode([inst.problem_statement])[0]
        scores = doc_vecs @ qv
        order = np.argsort(-scores)
        ranked = [files[i] for i in order]
        sc = score(ranked, gold)
        rows.append(sc)
        print(f"{task:38s} gold={len(gold)} files={len(files):5d} "
              f"R@5={sc['recall@5']:.2f} hit@5={sc['hit@5']:.0f} "
              f"rk={sc['gold_best_rank']}")

    print("\n========= EMBEDDING (all-MiniLM-L6-v2) AGGREGATE n={} =========".format(len(rows)))
    line = "embed       "
    for k in KS:
        line += f"  R@{k}={np.mean([x[f'recall@{k}'] for x in rows]):.3f}"
    for k in KS:
        line += f"  hit@{k}={np.mean([x[f'hit@{k}'] for x in rows]):.3f}"
    line += f"  MRR={np.mean([x['mrr'] for x in rows]):.3f}"
    print(line)
    print("\nLexical ref: bm25 R@5=0.279 hit@5=0.500 MRR=0.230 ; "
          "tfidf R@5=0.312 hit@5=0.500 MRR=0.419 ; name_prefix R@5=0.175 MRR=0.176")
    print("Agent ref:   no_mcp recall=0.613 MRR=0.875 ; code_graph recall=0.512 MRR=0.800")


if __name__ == "__main__":
    main()
