"""SWE-bench Verified dataset loader.

Loads `princeton-nlp/SWE-bench_Verified` via the `datasets` library,
samples instances deterministically by seed, prepares each repo as a
git working tree at the task's base commit, and exposes them as
`bench.runners.mini_runner.Task` objects.

Repo clones are cached under `bench/cache/repos/{owner__name}/`
(bare-ish clone with all refs). For each task we materialize a
disposable worktree at `bench/cache/worktrees/{instance_id}/` and
hard-reset it to `base_commit`. The test_patch (which adds/modifies
the FAIL_TO_PASS tests but NOT the source patch) is applied so the
agent can actually run the tests; this matches the official
SWE-bench evaluation harness.

Verification follows SWE-bench's protocol: after the agent submits a
patch, run the FAIL_TO_PASS + PASS_TO_PASS test selection and check
that all FAIL_TO_PASS go from fail→pass and all PASS_TO_PASS stay
passing. We approximate this with `pytest <test ids>` since the
official harness needs Docker per-instance environments.

NOTE: This loader prepares repos for the agent but does NOT set up
per-repo Python dependencies. Real SWE-bench evaluation requires
constructing the exact conda environment specified in the dataset
row's `environment_setup_commit`. For an open evaluation we'll need
to either (a) use the official `swebench` harness for verification
or (b) build per-repo conda envs on the fly. This module flags
verification as "skipped" until that path is wired up.
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from bench.runners.mini_runner import Task

DATASET_NAME = "princeton-nlp/SWE-bench_Verified"
DEFAULT_CACHE_ROOT = Path(__file__).resolve().parents[1] / "cache"
REPOS_DIR = DEFAULT_CACHE_ROOT / "repos"
WORKTREES_DIR = DEFAULT_CACHE_ROOT / "worktrees"

# Locked-in seed from plan / configs/default.yaml.
DEFAULT_SEED = 20260526

# Per-stage sample sizes (locked-in from plan).
STAGE_SIZES = {"smoke": 3, "calibration": 10, "headline": 37}


@dataclass(slots=True)
class SweBenchInstance:
    """Subset of SWE-bench Verified fields we use."""

    instance_id: str
    repo: str  # "owner/name"
    base_commit: str
    problem_statement: str
    test_patch: str
    fail_to_pass: list[str]
    pass_to_pass: list[str]
    environment_setup_commit: str
    version: str
    patch: str = ""  # gold source patch (localization ground truth)


def _git(args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=check,
    )


def _parse_list_field(value: Any) -> list[str]:
    """SWE-bench stores FAIL_TO_PASS / PASS_TO_PASS as JSON strings."""
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str):
        return list(json.loads(value))
    raise TypeError(f"unsupported list field: {type(value)!r}")


def load_instances(
    *,
    split: str = "test",
    cache_dir: Path | None = None,
    dataset_name: str | None = None,
) -> list[SweBenchInstance]:
    """Load SWE-bench instances from HuggingFace.

    Defaults to `princeton-nlp/SWE-bench_Verified`. Pass `dataset_name` (e.g.
    `SWE-bench-Live/SWE-bench-Live`, which is schema-compatible and exposes a
    `verified` split) to evaluate a contamination-free / less-pretraining-
    saturated corpus.
    """
    from datasets import load_dataset  # local import — heavy

    kwargs: dict[str, Any] = {"split": split}
    if cache_dir is not None:
        kwargs["cache_dir"] = str(cache_dir)
    ds = load_dataset(dataset_name or DATASET_NAME, **kwargs)

    out: list[SweBenchInstance] = []
    for row in ds:
        out.append(
            SweBenchInstance(
                instance_id=row["instance_id"],
                repo=row["repo"],
                base_commit=row["base_commit"],
                problem_statement=row["problem_statement"],
                test_patch=row["test_patch"],
                fail_to_pass=_parse_list_field(row["FAIL_TO_PASS"]),
                pass_to_pass=_parse_list_field(row["PASS_TO_PASS"]),
                environment_setup_commit=row.get("environment_setup_commit") or "",
                version=row.get("version") or "",
                patch=row.get("patch") or "",
            )
        )
    return out


def sample_instances(
    instances: Iterable[SweBenchInstance],
    *,
    stage: str = "smoke",
    seed: int = DEFAULT_SEED,
    n: int | None = None,
) -> list[SweBenchInstance]:
    """Deterministic stratified sample.

    `stage` selects a size from `STAGE_SIZES` unless `n` is given.
    Sampling is plain `random.sample` with the locked-in seed so runs
    are reproducible across machines.
    """
    size = n if n is not None else STAGE_SIZES[stage]
    pool = list(instances)
    rng = random.Random(seed)
    return rng.sample(pool, k=min(size, len(pool)))


# ---------------------------------------------------------------------------
# Repo materialization
# ---------------------------------------------------------------------------


def _repo_cache_path(repo: str, repos_dir: Path) -> Path:
    safe = repo.replace("/", "__")
    return repos_dir / safe


def _ensure_repo_clone(repo: str, repos_dir: Path) -> Path:
    """Ensure we have a local clone of `owner/name`. Returns its path."""
    dest = _repo_cache_path(repo, repos_dir)
    if (dest / ".git").exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{repo}.git"
    _git(["clone", url, str(dest)])
    return dest


def prepare_worktree(
    inst: SweBenchInstance,
    *,
    repos_dir: Path = REPOS_DIR,
    worktrees_dir: Path = WORKTREES_DIR,
    apply_test_patch: bool = True,
) -> Path:
    """Materialize a fresh working tree at `inst.base_commit`.

    Uses `git clone` of the cached repo (cheap because clones share
    objects). The test_patch is applied unless `apply_test_patch` is
    False so the agent can actually run the FAIL_TO_PASS tests.
    """
    src = _ensure_repo_clone(inst.repo, repos_dir)

    dest = worktrees_dir / inst.instance_id
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Make a local clone (shares objects via --shared-style alternates).
    _git(["clone", str(src), str(dest)])
    _git(["fetch", "origin", inst.base_commit], cwd=dest, check=False)
    _git(["checkout", "--detach", inst.base_commit], cwd=dest)

    if apply_test_patch and inst.test_patch.strip():
        patch_file = dest / ".swebench-test.patch"
        patch_file.write_text(inst.test_patch)
        try:
            _git(["apply", "--allow-empty", str(patch_file)], cwd=dest)
        except subprocess.CalledProcessError as exc:
            # Some test_patches need 3-way merge; retry with -3.
            res = subprocess.run(
                ["git", "apply", "--3way", str(patch_file)],
                cwd=dest, capture_output=True, text=True,
            )
            if res.returncode != 0:
                raise RuntimeError(
                    f"failed to apply test_patch for {inst.instance_id}: {exc.stderr}"
                )
        patch_file.unlink(missing_ok=True)

    return dest


def instance_to_task(inst: SweBenchInstance, repo_path: Path) -> Task:
    """Wrap a SWE-bench instance as a bench.runners Task."""
    return Task(
        task_id=inst.instance_id,
        repo_name=inst.repo,
        repo_path=repo_path,
        problem_statement=inst.problem_statement,
        verify_cmd=None,  # verification done via swe_bench.verify_instance
    )


# ---------------------------------------------------------------------------
# Localization ground truth (LocAgent-style)
# ---------------------------------------------------------------------------

# Paths we exclude from the "files to modify" gold set: tests, docs, and
# anything that isn't Python source. Localization asks for the *implementation*
# files, so an agent that correctly avoids tests shouldn't be penalized.
_TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|testing|test)(/|$)"          # tests/ dir
    r"|(^|/)conftest\.py$"                        # pytest conftest
    r"|(^|/)test_[^/]*\.py$"                       # test_*.py
    r"|[^/]*_test\.py$"                            # *_test.py
)
_DOC_PATH_RE = re.compile(r"(^|/)docs?(/|$)|\.(rst|md|txt|cfg|ini|toml)$")


def is_source_file(path: str) -> bool:
    """True for non-test, non-doc Python source files."""
    if not path.endswith(".py"):
        return False
    if _TEST_PATH_RE.search(path):
        return False
    if _DOC_PATH_RE.search(path):
        return False
    return True


def gold_changed_files(patch: str, *, source_only: bool = True) -> list[str]:
    """Repo-relative files touched by a unified diff, in patch order.

    Reads `+++ b/<path>` headers (skips /dev/null deletions). When
    `source_only`, filters to non-test non-doc Python files.
    """
    files: list[str] = []
    for line in patch.splitlines():
        if not line.startswith("+++ "):
            continue
        target = line[4:].strip()
        if target == "/dev/null":
            continue
        # strip the leading "b/" git prefix if present
        if target.startswith("b/"):
            target = target[2:]
        if target in files:
            continue
        if source_only and not is_source_file(target):
            continue
        files.append(target)
    return files


def _patch_hunk_ranges(patch: str) -> dict[str, list[tuple[int, int]]]:
    """Map each target file -> list of (start, end) NEW-file line ranges
    that the gold patch modifies. Used for symbol-level localization."""
    ranges: dict[str, list[tuple[int, int]]] = {}
    cur: str | None = None
    for line in patch.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            if target.startswith("b/"):
                target = target[2:]
            cur = None if target == "/dev/null" else target
            if cur is not None:
                ranges.setdefault(cur, [])
            continue
        if line.startswith("@@"):
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if m and cur is not None:
                start = int(m.group(1))
                count = int(m.group(2) or "1")
                ranges[cur].append((start, start + max(count - 1, 0)))
            continue
    return ranges


def gold_symbols(inst: SweBenchInstance, repo_path: Path) -> dict[str, list[str]]:
    """Best-effort Python symbol-level gold: for each gold source file,
    the set of enclosing top-level/def/class symbol names whose body the
    gold patch modifies. Maps NEW-file hunk line ranges to enclosing
    ast.FunctionDef/AsyncFunctionDef/ClassDef. Files that don't parse or
    don't map are silently skipped (reported as unmappable upstream).
    """
    import ast

    out: dict[str, list[str]] = {}
    ranges = _patch_hunk_ranges(inst.patch)
    for rel, rngs in ranges.items():
        if not is_source_file(rel):
            continue
        fpath = repo_path / rel
        if not fpath.exists():
            continue
        try:
            tree = ast.parse(fpath.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue
        # Build (start,end,qualname) for every def/class.
        spans: list[tuple[int, int, str]] = []

        def _walk(node: ast.AST, prefix: str) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    qual = f"{prefix}{child.name}"
                    start = child.lineno
                    end = getattr(child, "end_lineno", start)
                    spans.append((start, end, qual))
                    _walk(child, qual + ".")
                else:
                    _walk(child, prefix)

        _walk(tree, "")
        hit: list[str] = []
        for (hs, he) in rngs:
            # innermost enclosing symbol per hunk
            best: tuple[int, str] | None = None
            for (s, e, q) in spans:
                if s <= hs <= e or s <= he <= e or (hs <= s and he >= e):
                    size = e - s
                    if best is None or size < best[0]:
                        best = (size, q)
            if best and best[1] not in hit:
                hit.append(best[1])
        if hit:
            out[rel] = hit
    return out


def leakage_flags(inst: SweBenchInstance, gold_files: list[str]) -> dict[str, bool]:
    """Annotate whether the issue text trivially leaks the gold location."""
    text = inst.problem_statement or ""
    basenames = {Path(f).name for f in gold_files}
    return {
        "mentions_gold_path": any(f in text for f in gold_files),
        "mentions_gold_basename": any(b in text for b in basenames),
        "contains_traceback": ("Traceback (most recent call last)" in text)
        or ("\n  File \"" in text),
    }


def is_structural(inst: SweBenchInstance) -> bool:
    """A task stresses structural navigation if its gold source patch
    spans >=2 source files OR >=2 distinct directories."""
    files = gold_changed_files(inst.patch, source_only=True)
    if len(files) >= 2:
        return True
    dirs = {str(Path(f).parent) for f in files}
    return len(dirs) >= 2


def select_structural(
    instances: Iterable[SweBenchInstance],
    *,
    seed: int = DEFAULT_SEED,
    n: int | None = None,
    repos: set[str] | None = None,
    python_only: bool = False,
) -> list[SweBenchInstance]:
    """Deterministically sample instances whose gold patch is multi-file/
    multi-dir (structural-navigation stressors).

    `repos`: if given, restrict to these `owner/name` repos (used to target
    large, less-pretraining-saturated codebases on the SWE-bench-Live corpus).
    `python_only`: require at least one `.py` gold source file (the navigation
    tools — tree-sitter / jedi — are Python-only).
    """
    pool = [i for i in instances if is_structural(i)]
    if repos is not None:
        pool = [i for i in pool if i.repo in repos]
    if python_only:
        pool = [
            i
            for i in pool
            if any(f.endswith(".py") for f in gold_changed_files(i.patch, source_only=True))
        ]
    rng = random.Random(seed)
    rng.shuffle(pool)
    return pool[:n] if n is not None else pool


def prepare_localize_worktree(
    inst: SweBenchInstance,
    *,
    repos_dir: Path = REPOS_DIR,
    worktrees_dir: Path | None = None,
) -> Path:
    """Materialize a TEST-FREE worktree under a distinct name (`{id}__loc`).

    The distinct dirname matters: the code-graph backend keys its index on
    the worktree dirname, so a fresh name forces a clean re-index that does
    NOT contain the test_patch files (which would leak the bug location).
    """
    wt_dir = worktrees_dir or (DEFAULT_CACHE_ROOT / "worktrees-localize")
    src = _ensure_repo_clone(inst.repo, repos_dir)
    dest = wt_dir / f"{inst.instance_id}__loc"
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    if dest.exists():
        # A locked/partial dir survived rmtree (e.g. an open handle from a
        # prior interrupted run). Move it aside so the clone can proceed.
        import time as _t
        dest.rename(dest.with_name(f"{dest.name}.stale.{int(_t.time())}"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Clone with a single retry. We have observed a transient `git clone`
    # exit-128 on the *first* clone of a freshly-cleaned worktree dir (the
    # next config's clone of the same instance then succeeds). Re-clean and
    # retry once; surface git's stderr if it still fails so it's diagnosable.
    last_err = ""
    for attempt in range(2):
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        res = _git(["clone", str(src), str(dest)], check=False)
        if res.returncode == 0:
            break
        last_err = (res.stderr or res.stdout or "").strip()
        print(
            f"[warn] git clone {dest.name} failed (attempt {attempt + 1}/2): "
            f"{last_err}",
            flush=True,
        )
    else:
        raise RuntimeError(f"git clone failed for {dest}: {last_err}")
    _git(["fetch", "origin", inst.base_commit], cwd=dest, check=False)
    _git(["checkout", "--detach", inst.base_commit], cwd=dest)
    return dest


# ---------------------------------------------------------------------------
# Verification (approximate — official harness needs Docker)
# ---------------------------------------------------------------------------


def verify_instance(
    inst: SweBenchInstance,
    repo_path: Path,
    *,
    python: str | None = None,
) -> tuple[bool, str]:
    """Run FAIL_TO_PASS + PASS_TO_PASS tests against the patched repo.

    Returns (passed, summary). Best-effort: many SWE-bench repos need
    bespoke conda envs we don't build here. If pytest itself fails to
    collect, returns (False, "<error>") so the runner records `failed`
    and we know to investigate.
    """
    py = python or os.environ.get("BENCH_REPO_PYTHON") or "python"
    test_ids = list(inst.fail_to_pass) + list(inst.pass_to_pass)
    if not test_ids:
        return False, "no test ids in dataset row"

    cmd = [py, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *test_ids]
    res = subprocess.run(cmd, cwd=str(repo_path), capture_output=True, text=True)
    ok = res.returncode == 0
    summary = res.stdout[-500:] + res.stderr[-500:]
    return ok, summary
