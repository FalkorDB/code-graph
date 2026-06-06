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

import hashlib
import hmac
import json
import os
import random
import re
import secrets
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from bench.runners.mini_runner import Task

DATASET_NAME = "princeton-nlp/SWE-bench_Verified"
# Loc-Bench (LocAgent, ACL 2025): curated multi-hop code-localization benchmark.
# Schema-compatible subset; localization-only (no FAIL_TO_PASS / PASS_TO_PASS).
LOC_BENCH_DATASET = "czlll/Loc-Bench_V1"
DEFAULT_CACHE_ROOT = Path(__file__).resolve().parents[1] / "cache"
REPOS_DIR = DEFAULT_CACHE_ROOT / "repos"
WORKTREES_DIR = DEFAULT_CACHE_ROOT / "worktrees"

# Locked-in seed from plan / configs/default.yaml.
DEFAULT_SEED = 20260526

# ---------------------------------------------------------------------------
# Answer-leakage hardening (default ON; opt out with BENCH_BLOCK_NETWORK=0)
# ---------------------------------------------------------------------------
# The localize worktree was historically named ``{instance_id}__loc``. The
# instance_id embeds the upstream GitHub PR/issue number, so that name leaked
# into the prompt cwd, ``--add-dir`` and the code-graph ``project=`` key — the
# agent could read the PR number off the path and fetch the merged PR's file
# list (the gold answer), or read the cloned ``.git`` (origin + post-fix
# default-branch ref) fully offline. When hardening is enabled we (a) name the
# worktree with an opaque salted HMAC of the instance_id and (b) strip ``.git``.
#
# The salt defaults to a per-process random value; pin BENCH_LEAK_SALT only if
# a stable mapping across processes is needed (it is NOT required for resume,
# since localize worktrees are rmtree'd per run). The salt must never reach the
# agent process env (the runner scrubs it from the Copilot child environment).
_RUN_SALT = os.environ.get("BENCH_LEAK_SALT") or secrets.token_hex(16)

# Env vars scrubbed from the agent's process environment under hardening, so the
# agent cannot recover the opaque-name salt or use ambient GitHub credentials.
LEAK_SCRUB_ENV_VARS = (
    "BENCH_LEAK_SALT",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_PAT",
    "GH_PAT",
)


def network_block_enabled() -> bool:
    """Whether answer-leakage hardening is active for this run.

    Default ON. Tracing repeatedly caught the agent fetching the gold file list
    from GitHub (``gh pr view``, ``web_fetch`` of the issue/PR) and reading the
    cloned ``.git`` post-fix ref, which silently turned localization misses into
    fake recall=1.0 wins. Hardening is therefore enabled unless explicitly
    disabled with ``BENCH_BLOCK_NETWORK`` set to a falsy value
    (``0``/``false``/``no``/``off``).
    """
    val = os.environ.get("BENCH_BLOCK_NETWORK")
    if val is None:
        return True
    return val.strip().lower() not in ("0", "false", "no", "off", "")


def opaque_worktree_name(instance_id: str) -> str:
    """Opaque, salted worktree dir name that does not embed the PR/issue number.

    HMAC-SHA256(salt, instance_id) truncated to 16 hex chars, ``loc-`` prefixed.
    Deterministic within a process (stable salt) so a single run's index/prompt/
    query all agree, but reveals nothing about the upstream instance.
    """
    digest = hmac.new(
        _RUN_SALT.encode(), instance_id.encode(), hashlib.sha256
    ).hexdigest()[:16]
    return f"loc-{digest}"

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
    category: str = ""  # Loc-Bench issue category (Bug, Feature, Performance, ...)


def _git(args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=check,
    )


def _parse_list_field(value: Any) -> list[str]:
    """SWE-bench stores FAIL_TO_PASS / PASS_TO_PASS as JSON strings.

    Localization-only datasets (e.g. Loc-Bench) omit these; treat missing /
    empty values as an empty list rather than raising.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        return list(json.loads(s))
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
                test_patch=row.get("test_patch") or "",
                fail_to_pass=_parse_list_field(row.get("FAIL_TO_PASS")),
                pass_to_pass=_parse_list_field(row.get("PASS_TO_PASS")),
                environment_setup_commit=row.get("environment_setup_commit") or "",
                version=row.get("version") or "",
                patch=row.get("patch") or "",
                category=row.get("category") or "",
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
    no_leak: bool = False,
) -> list[SweBenchInstance]:
    """Deterministically sample instances whose gold patch is multi-file/
    multi-dir (structural-navigation stressors).

    `repos`: if given, restrict to these `owner/name` repos (used to target
    large, less-pretraining-saturated codebases on the SWE-bench-Live corpus).
    `python_only`: require at least one `.py` gold source file (the navigation
    tools — tree-sitter / jedi — are Python-only).
    `no_leak`: drop instances whose problem statement names a gold file's path
    or basename (the "structural-hard" gate — forces real multi-hop navigation
    rather than single-hop lookup of an explicitly-named file).
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
    if no_leak:
        kept = []
        for i in pool:
            gold = gold_changed_files(i.patch, source_only=True)
            lf = leakage_flags(i, gold)
            if not lf["mentions_gold_path"] and not lf["mentions_gold_basename"]:
                kept.append(i)
        pool = kept
    rng = random.Random(seed)
    rng.shuffle(pool)
    return pool[:n] if n is not None else pool


def prepare_localize_worktree(
    inst: SweBenchInstance,
    *,
    repos_dir: Path = REPOS_DIR,
    worktrees_dir: Path | None = None,
) -> Path:
    """Materialize a TEST-FREE worktree under a distinct name.

    The distinct dirname matters: the code-graph backend keys its index on
    the worktree dirname, so a fresh name forces a clean re-index that does
    NOT contain the test_patch files (which would leak the bug location).

    Naming:
      * unhardened (``BENCH_BLOCK_NETWORK=0``): ``{instance_id}__loc``
        (preserves prior-run provenance).
      * hardened (default): ``loc-<salted HMAC>`` so the
        dirname does NOT embed the upstream PR/issue number, and the cloned
        ``.git`` is stripped so the post-fix oracle is unreachable offline.
    """
    hardened = network_block_enabled()
    wt_dir = worktrees_dir or (DEFAULT_CACHE_ROOT / "worktrees-localize")
    src = _ensure_repo_clone(inst.repo, repos_dir)
    name = opaque_worktree_name(inst.instance_id) if hardened else f"{inst.instance_id}__loc"
    dest = wt_dir / name
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
    # The cached clone (origin) only has commits reachable from the default
    # branch. Loc-Bench base_commits are sometimes unreachable from it (PR
    # bases, rewritten history). GitHub serves any reachable SHA directly, so
    # fall back to fetching the commit straight from the upstream URL.
    if _git(["cat-file", "-e", inst.base_commit], cwd=dest, check=False).returncode != 0:
        url = f"https://github.com/{inst.repo}.git"
        _git(["fetch", "--depth", "1", url, inst.base_commit], cwd=dest, check=False)
    _git(["checkout", "--detach", inst.base_commit], cwd=dest)
    if hardened:
        # Strip the offline oracle: the cloned ``.git`` retains ``origin`` plus a
        # local default-branch ref at the post-fix tip, so ``git log/diff
        # origin/<branch>`` would reveal the gold change with no network. The
        # localize path needs no git history (gold comes from the dataset patch;
        # analyze_folder ignores ``.git``), so removing it is safe.
        strip_git_oracle(dest)
    return dest


def strip_git_oracle(root: Path) -> None:
    """Remove every ``.git`` (directory OR gitdir-pointer file) under ``root``.

    A bare ``rmtree(root/'.git')`` only handles the top-level repo dir. It misses
    (a) submodule checkouts, whose ``.git`` is a *file* containing a
    ``gitdir: ...`` pointer back into the superproject, and (b) any nested git
    checkout. Any surviving ``.git`` lets ``git`` rediscover history from inside
    the worktree, re-exposing the post-fix oracle. Remove them all so the
    worktree is genuinely history-free.
    """
    for git_path in sorted(root.rglob(".git"), key=lambda p: len(p.parts), reverse=True):
        if git_path.is_dir() and not git_path.is_symlink():
            shutil.rmtree(git_path, ignore_errors=True)
        else:
            try:
                git_path.unlink()
            except OSError:
                pass


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
    summary = res.stdout[-500:] + res.stderr[-500:]
    # Distinguish "tests ran and failed" (authoritative-ish negative) from
    # "we could not run tests at all" (no pytest in env, collection crash).
    # The latter must NOT be reported as a real failure — the authoritative
    # grade comes from the SWE-bench Docker harness (bench.runners.
    # swebench_verify). pytest uses returncode 2-5 for usage/collection/internal
    # errors, and 1 for genuine test failures; 0 is pass.
    could_not_run = (
        "No module named pytest" in summary
        or "no tests ran" in summary
        or res.returncode >= 2
    )
    if could_not_run and res.returncode != 1:
        return False, "UNGRADED: " + summary
    ok = res.returncode == 0
    return ok, summary
