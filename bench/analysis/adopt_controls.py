"""Negative-control + relabel infrastructure for the adoption-calibration
experiment (Lane 1). All FREE / offline -- no API, no network.

This module implements the prereg controls (see
``files/prereg-adoption-calibration.md`` ss3, ss6, ss7) that make the
"overfitting boundary" *sufficient* rather than merely necessary:

  1. edit-critical relabel (ss7) -- only EDIT-CRITICAL gold count as FN, so a
     lever is not rewarded for reproducing the patch footprint. Path/type
     heuristic first guess + a frozen manual-override JSON.

  2. GRAPH-WRONG selection (ss3) -- the subset of tasks whose top-ranked (rank-1)
     graph hit is verified non-gold. Tests whether a lever can still correctly
     DROP under a misleading #1. Pure offline scan of cached runs.

  3. NOISY distractor manifest (ss3, ss6) -- a deterministic, seeded set of K
     plausible-but-false sibling candidates per task, for injection into the
     LIVE MCP output at pilot run-time. On CACHED data the agent never saw these
     files, so they would always score TN; therefore the FREE deliverable here
     is the *manifest generator* + validity assertions + a coverage report, NOT
     an offline NOISY score. The live NOISY arm is deferred to the pilot.

Scoping note (per rubber-duck): NOISY is a ROBUSTNESS PROBE, not evidence that
the injected junk matches the graph's real false-positive distribution (the
hardened cache has only FP=2/213 real FPs -- too few to characterize). Report
the real FPs alongside any NOISY result so a reader can judge the gap.

Offline mapping trick: the per-task worktrees under
``<batch>/worktrees/code_graph/loc-<hash>`` are git-sanitized (no .git), but each
code_graph run's ``stdout.jsonl`` references its own ``loc-<hash>`` exactly once.
So task -> worktree is recovered by grepping the run log (unique per task, no
same-repo collision), and the gold file's *directory siblings at base_commit*
are read straight off the worktree filesystem. No base_commit SHA or HF load
needed.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import re
from pathlib import Path

from bench.analysis.exposure_adoption import (
    analyze_batch,
    candidate_calibration,
    classify_run,
    row_stdout_path,
    surfaced_files,
)

DEFAULT_SEED = 1234
DEFAULT_K = 2

_LOC_RE = re.compile(r"loc-[0-9a-f]{16}")

# Incidental-gold path markers (prereg ss7): test-only, fixture, migration,
# generated, or docs files. A gold file matching any of these is INCIDENTAL
# unless an override says otherwise. Everything else defaults to EDIT-CRITICAL.
_INCIDENTAL_PATH_RE = re.compile(
    r"(^|/)(tests?|testing|test_[^/]*|[^/]*_test\.py|conftest\.py|fixtures?|"
    r"migrations?|_generated|generated|\.pb\.py|docs?|examples?)(/|$|\.)",
    re.IGNORECASE,
)
# Files we never inject as distractors (not real "plausible source siblings"):
# tests/fixtures/migrations, caches, and package markers (__init__.py / dunder
# files) which are near-universal and not credible edit locations.
_NONSOURCE_DISTRACTOR_RE = re.compile(
    r"(^|/)(tests?|conftest\.py|fixtures?|migrations?|__pycache__|"
    r"[^/]*_test\.py|test_[^/]*\.py|__[a-z0-9_]+__\.py|_?version\.py|setup\.py)(/|$)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# task -> worktree mapping (offline, via the run log)
# ---------------------------------------------------------------------------
def _run_stdout(batch_root: Path, model: str, task: str,
                prompt_mode: str = "nudged") -> Path | None:
    base = batch_root / "runs" / model / "localize" / prompt_mode / "code_graph"
    cand = base / task / "logs" / "stdout.jsonl"
    if cand.exists():
        return cand
    hits = list(base.glob(f"{task}/**/stdout.jsonl"))
    if hits:
        return hits[0]
    # fall back to any mode dir
    hits = list((batch_root / "runs" / model).glob(f"*/*/code_graph/{task}/**/stdout.jsonl"))
    return hits[0] if hits else None


def map_task_worktree(batch_root: Path, model: str, task: str,
                      prompt_mode: str = "nudged") -> Path | None:
    """Return the on-disk worktree dir for ``task`` at base_commit, or None.

    Recovered by reading the unique ``loc-<hash>`` referenced in the task's
    code_graph run log. Asserts uniqueness (raises on >1 distinct hash).
    """
    sp = _run_stdout(batch_root, model, task, prompt_mode)
    if sp is None:
        return None
    locs = sorted(set(_LOC_RE.findall(sp.read_text())))
    if len(locs) != 1:
        return None
    wt = batch_root / "worktrees" / "code_graph" / locs[0]
    return wt if wt.exists() else None


# ---------------------------------------------------------------------------
# edit-critical relabel (prereg ss7)
# ---------------------------------------------------------------------------
def load_overrides(path: Path | None) -> dict[str, dict[str, str]]:
    """Load the frozen manual-audit override file.

    Schema: ``{task_id: {gold_file: "critical"|"incidental"}}``. Missing file
    or None -> empty (heuristic-only).
    """
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {k: dict(v) for k, v in data.items()}


def edit_critical_split(
    gold_files: list[str],
    task: str | None = None,
    overrides: dict[str, dict[str, str]] | None = None,
) -> tuple[list[str], list[str]]:
    """Split gold into (edit_critical, incidental).

    Heuristic: a gold file whose path matches ``_INCIDENTAL_PATH_RE`` is
    INCIDENTAL; otherwise EDIT-CRITICAL. The manual override for ``task`` (if
    present) wins over the heuristic, per gold file.
    """
    ov = (overrides or {}).get(task or "", {})
    critical, incidental = [], []
    for g in gold_files:
        label = ov.get(g)
        if label is None:
            label = "incidental" if _INCIDENTAL_PATH_RE.search(g) else "critical"
        (incidental if label == "incidental" else critical).append(g)
    return critical, incidental


# ---------------------------------------------------------------------------
# GRAPH-WRONG selection (prereg ss3)
# ---------------------------------------------------------------------------
def select_graph_wrong(runs: list[dict], gold_by_task: dict[str, list[str]],
                       batch_root: Path, model: str,
                       prompt_mode: str = "nudged") -> list[dict]:
    """Tasks whose rank-1 surfaced file is verified non-gold.

    ``runs`` are the per-run dicts from ``analyze_batch`` (carry ``task``). We
    re-read surfaced_files to find rank-1, then mark a task GRAPH-WRONG if, in at
    least one of its runs, the best (rank-1) primary hit is not in that task's
    gold set. Returns ``[{task, run_idx, rank1, is_wrong}]`` for wrong runs.
    """
    out = []
    for r in runs:
        task = r.get("task")
        gold = set(gold_by_task.get(task, []))
        sp = _run_stdout(batch_root, model, task, prompt_mode)
        if sp is None:
            continue
        surf = surfaced_files(sp)
        rank1 = min((f for f, v in surf.items() if v["best_rank"] is not None),
                    key=lambda f: surf[f]["best_rank"], default=None)
        if rank1 is not None and rank1 not in gold:
            out.append({"task": task, "run_idx": r.get("run_idx"),
                        "rank1": rank1, "is_wrong": True})
    return out


# ---------------------------------------------------------------------------
# NOISY distractor manifest (prereg ss3, ss6)
# ---------------------------------------------------------------------------
def gold_symbols_offline(worktree: Path, gold_file: str) -> list[str]:
    """Top-level + class-method symbol names from the gold file on disk.

    Parsed with ``ast`` straight off the base_commit worktree -- no HF instance
    needed. Returns [] for non-Python or unparseable files.
    """
    if not gold_file.endswith(".py"):
        return []
    p = worktree / gold_file
    try:
        tree = ast.parse(p.read_text())
    except (OSError, SyntaxError, ValueError):
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
            # dunder methods (__init__, __repr__, ...) are near-universal and
            # would spuriously match package files / generic stems -- skip them.
            if name.startswith("__") and name.endswith("__"):
                continue
            out.append(name)
    return out


def _similarity(stem: str, targets: list[str]) -> float:
    stem = stem.lower()
    return max((difflib.SequenceMatcher(None, stem, t.lower()).ratio()
                for t in targets if t), default=0.0)


def sibling_distractors(
    worktree: Path,
    gold_files: list[str],
    incidental: list[str],
    k: int = DEFAULT_K,
    seed: int = DEFAULT_SEED,
) -> list[dict]:
    """Deterministic K plausible-but-false sibling distractors for a task.

    Pool = source-file siblings in every gold file's directory (base_commit
    on-disk tree), excluding all gold + incidental files and any test/fixture/
    generated file. Ranked by max name-similarity to a gold stem OR gold AST
    symbol. Ties broken by a seeded but reproducible key, then by path. Returns
    the top-k as ``[{file, score, similar_to}]``.
    """
    gold_set = set(gold_files) | set(incidental)
    # similarity targets: gold stems + gold symbols
    targets: list[str] = []
    for g in gold_files:
        targets.append(Path(g).stem)
        targets.extend(gold_symbols_offline(worktree, g))

    pool: dict[str, float] = {}
    for g in gold_files:
        gdir = str(Path(g).parent)
        ddir = worktree / gdir
        if not ddir.is_dir():
            continue
        for child in sorted(ddir.iterdir()):
            if not child.is_file() or not child.name.endswith(".py"):
                continue
            rel = str(Path(gdir) / child.name) if gdir != "." else child.name
            if rel in gold_set:
                continue
            if _NONSOURCE_DISTRACTOR_RE.search(rel):
                continue
            score = _similarity(child.stem, targets)
            # keep the best score if a file is reachable from >1 gold dir
            if rel not in pool or score > pool[rel]:
                pool[rel] = score

    def _tiebreak(item: tuple[str, float]) -> tuple:
        rel, score = item
        # seeded, deterministic, path-stable ordering for equal scores
        h = difflib.SequenceMatcher(None, f"{seed}", rel).ratio()
        return (-score, -h, rel)

    ranked = sorted(pool.items(), key=_tiebreak)
    chosen = ranked[:k]
    return [{"file": rel, "score": round(score, 4),
             "similar_to": _closest_target(Path(rel).stem, targets)}
            for rel, score in chosen]


def _closest_target(stem: str, targets: list[str]) -> str | None:
    if not targets:
        return None
    return max(targets, key=lambda t: difflib.SequenceMatcher(
        None, stem.lower(), t.lower()).ratio())


def build_noisy_manifest(
    results_path: Path,
    *,
    k: int = DEFAULT_K,
    seed: int = DEFAULT_SEED,
    overrides_path: Path | None = None,
) -> dict:
    """Build the deterministic NOISY injection manifest + coverage report.

    For every code_graph task, emit K verified-non-gold sibling distractors. The
    manifest is keyed by task and is reproducible across runs. Validity
    assertions (non-gold, distinct, on-disk) are enforced and surfaced in the
    report so a frozen artifact is auditable.
    """
    batch_root = results_path.parent.parent
    model = results_path.parent.name
    rows = [json.loads(ln) for ln in results_path.read_text().splitlines() if ln.strip()]
    cg = [r for r in rows if r.get("config") == "code_graph"]
    overrides = load_overrides(overrides_path)

    seen_tasks: set[str] = set()
    manifest: dict[str, dict] = {}
    coverage = {"tasks": 0, "full_k": 0, "partial": 0, "empty": 0, "no_worktree": 0}
    for r in cg:
        task = r["task_id"]
        if task in seen_tasks:
            continue
        seen_tasks.add(task)
        coverage["tasks"] += 1
        gold = r.get("gold_files", [])
        _crit, incidental = edit_critical_split(gold, task, overrides)
        wt = map_task_worktree(batch_root, model, task)
        if wt is None:
            coverage["no_worktree"] += 1
            manifest[task] = {"distractors": [], "note": "no_worktree"}
            continue
        distractors = sibling_distractors(wt, gold, incidental, k=k, seed=seed)
        # validity assertions
        gold_set = set(gold)
        files = [d["file"] for d in distractors]
        assert len(files) == len(set(files)), f"dup distractor for {task}"
        assert not (set(files) & gold_set), f"gold leaked into distractors for {task}"
        for d in distractors:
            assert (wt / d["file"]).is_file(), f"distractor not on disk: {d['file']}"
        n = len(distractors)
        coverage["full_k" if n >= k else ("empty" if n == 0 else "partial")] += 1
        manifest[task] = {"worktree": wt.name, "distractors": distractors,
                          "gold_files": gold, "incidental": incidental}
    return {"k": k, "seed": seed, "coverage": coverage, "manifest": manifest}


# ---------------------------------------------------------------------------
# edit-critical recall sensitivity (heuristic-only vs +overrides)
# ---------------------------------------------------------------------------
def _rescore_with_labels(results_path: Path,
                         overrides: dict[str, dict[str, str]] | None,
                         prompt_mode: str | None = None) -> dict:
    """Re-run the candidate metric, passing per-task edit_critical labels.

    Locates each run's log by FULL row identity (``row_stdout_path``) so coexisting
    prompt-mode arms are never cross-wired. Pass ``prompt_mode`` to restrict to one
    arm.
    """
    batch_root = results_path.parent.parent
    model = results_path.parent.name
    rows = [json.loads(ln) for ln in results_path.read_text().splitlines() if ln.strip()]
    cg = [r for r in rows if r.get("config") == "code_graph"]
    if prompt_mode is not None:
        cg = [r for r in cg if r.get("prompt_mode") == prompt_mode]
    per_run = []
    for r in cg:
        task = r.get("task_id")
        stdout = row_stdout_path(batch_root, model, r)
        if not stdout:
            continue
        gold = r.get("gold_files", [])
        crit, _inc = edit_critical_split(gold, task, overrides)
        cls = classify_run(stdout, gold, r.get("pred_files", []), edit_critical=crit)
        cls["task"] = task
        cls["run_idx"] = r.get("run_idx")
        per_run.append(cls)
    return candidate_calibration(per_run)


def recall_sensitivity(results_path: Path, overrides_path: Path | None) -> dict:
    """Macro P/R/F1 under (a) all-gold-critical, (b) heuristic-only,
    (c) heuristic+overrides. Surfaces how much the relabel moves recall so a
    skeptic can see labels weren't tuned to taste."""
    overrides = load_overrides(overrides_path)
    # (a) baseline: every gold critical -> use analyze_batch (edit_critical=None)
    base = candidate_calibration(
        [r for r in analyze_batch(results_path)["per_run"] if "error" not in r])
    heur = _rescore_with_labels(results_path, None)
    audit = _rescore_with_labels(results_path, overrides)
    return {"all_critical": base["macro"], "heuristic_only": heur["macro"],
            "heuristic_plus_audit": audit["macro"], "n_overrides": sum(
                len(v) for v in overrides.values())}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results", type=Path, help="path to a code_graph results.jsonl")
    ap.add_argument("--overrides", type=Path,
                    default=Path(__file__).parent / "adopt_audit" / "edit_critical_overrides.json")
    ap.add_argument("--k", type=int, default=DEFAULT_K)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--json", type=Path, help="write full manifest+report JSON here")
    args = ap.parse_args()

    out = analyze_batch(args.results)
    runs = [r for r in out["per_run"] if "error" not in r]
    rows = [json.loads(ln) for ln in args.results.read_text().splitlines() if ln.strip()]
    gold_by_task = {r["task_id"]: r.get("gold_files", [])
                    for r in rows if r.get("config") == "code_graph"}

    model = args.results.parent.name
    batch_root = args.results.parent.parent

    print("==== EDIT-CRITICAL RELABEL (recall sensitivity) ====")
    sens = recall_sensitivity(args.results, args.overrides)

    def _m(d):
        f = lambda x: f"{x:.3f}" if x is not None else " n/a"  # noqa: E731
        return f"P={f(d['precision'])} R={f(d['recall'])} F1={f(d['f1'])}"

    print(f"  all-gold-critical    : {_m(sens['all_critical'])}")
    print(f"  heuristic-only       : {_m(sens['heuristic_only'])}")
    print(f"  heuristic+audit (n={sens['n_overrides']:>2}): {_m(sens['heuristic_plus_audit'])}")

    print("\n==== GRAPH-WRONG SUBSET (rank-1 surfaced file is non-gold) ====")
    gw = select_graph_wrong(runs, gold_by_task, batch_root, model)
    gw_tasks = sorted({g["task"] for g in gw})
    print(f"  graph-wrong runs: {len(gw)}  |  distinct tasks: {len(gw_tasks)}")
    for g in gw:
        print(f"    {g['task']:34s} idx={g['run_idx']}  rank1={g['rank1']}")

    print("\n==== NOISY DISTRACTOR MANIFEST (deterministic, for run-time injection) ====")
    noisy = build_noisy_manifest(args.results, k=args.k, seed=args.seed,
                                 overrides_path=args.overrides)
    cov = noisy["coverage"]
    print(f"  k={noisy['k']} seed={noisy['seed']}  tasks={cov['tasks']}  "
          f"full_k={cov['full_k']} partial={cov['partial']} "
          f"empty={cov['empty']} no_worktree={cov['no_worktree']}")
    for task, m in noisy["manifest"].items():
        ds = ", ".join(f"{Path(d['file']).name}({d['score']})" for d in m.get("distractors", []))
        print(f"    {task:34s} -> {ds or m.get('note', '(none)')}")

    if args.json:
        payload = {"recall_sensitivity": sens, "graph_wrong": gw,
                   "noisy": noisy}
        args.json.write_text(json.dumps(payload, indent=2))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
