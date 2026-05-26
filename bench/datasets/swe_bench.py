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
) -> list[SweBenchInstance]:
    """Load all SWE-bench Verified instances from HuggingFace."""
    from datasets import load_dataset  # local import — heavy

    kwargs: dict[str, Any] = {"split": split}
    if cache_dir is not None:
        kwargs["cache_dir"] = str(cache_dir)
    ds = load_dataset(DATASET_NAME, **kwargs)

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
