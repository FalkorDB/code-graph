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
# Verification — official SWE-bench harness path
# ---------------------------------------------------------------------------
#
# The original verify_instance implementation ran modern pytest from the
# bench venv against the SWE-bench worktree's legacy code, which collected
# zero tests on most instances (e.g. pytest-6202 INTERNALERRORs on removed
# config keys like `rsyncdirs`). Every trajectory was graded `failed`
# regardless of patch correctness, invalidating the Sonnet calibration's
# 0/10 resolve rate.
#
# The replacement defers to the official swebench harness, which builds /
# pulls per-instance Docker images with the right Python + dependencies
# and runs FAIL_TO_PASS + PASS_TO_PASS exactly the way the leaderboard
# does. Requires Docker on the host; when Docker is absent we return a
# `verifier_unavailable` outcome so we never silently grade wrongly again.


def _docker_available() -> bool:
    """Cheap probe — does `docker info` succeed?"""
    try:
        r = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def verify_with_swebench_harness(
    inst: SweBenchInstance,
    patch: str,
    *,
    run_id: str | None = None,
    namespace: str | None = "swebench",
    timeout: int = 1800,
    report_dir: Path | None = None,
) -> tuple[bool | None, str]:
    """Grade a single (instance, patch) via the official swebench harness.

    Returns (resolved, summary):
      - (True, "..." ) — FAIL_TO_PASS flipped + PASS_TO_PASS held
      - (False, "...") — patch did not resolve
      - (None,  "verifier_unavailable: <reason>") — could not grade (no
        Docker, harness exception). Caller should record outcome=
        `verifier_unavailable` rather than `failed`.

    `namespace="swebench"` pulls prebuilt images from Docker Hub (the
    `swebench/sweb.eval.x86_64.<instance>` family) and avoids the 30+
    minute per-instance build step. Pass `namespace=None` to force a
    local build instead.
    """
    if not _docker_available():
        return None, "verifier_unavailable: docker not available on host"

    if not patch.strip():
        return False, "empty patch"

    run_id = run_id or f"code-graph-bench-{inst.instance_id}"
    report_dir = report_dir or (DEFAULT_CACHE_ROOT / "verify" / run_id)
    report_dir.mkdir(parents=True, exist_ok=True)

    # predictions.jsonl in the format the harness expects
    model_tag = "code-graph-bench"
    pred_path = report_dir / "predictions.jsonl"
    with pred_path.open("w") as f:
        f.write(json.dumps({
            "instance_id": inst.instance_id,
            "model_name_or_path": model_tag,
            "model_patch": patch,
        }) + "\n")

    try:
        from swebench.harness.run_evaluation import main as run_eval
    except Exception as e:  # pragma: no cover — bench extra missing
        return None, f"verifier_unavailable: swebench import failed: {e}"

    try:
        run_eval(
            dataset_name=DATASET_NAME,
            split="test",
            instance_ids=[inst.instance_id],
            predictions_path=str(pred_path),
            max_workers=1,
            force_rebuild=False,
            cache_level="env",
            clean=False,
            open_file_limit=4096,
            run_id=run_id,
            timeout=timeout,
            namespace=namespace,
            rewrite_reports=False,
            modal=False,
            report_dir=str(report_dir),
        )
    except Exception as e:
        return None, f"verifier_unavailable: harness raised {type(e).__name__}: {e}"

    # The harness writes per-instance reports under
    # logs/run_evaluation/<run_id>/<model>/<instance>/report.json
    # but the path is CWD-relative. Find the resulting report.
    candidates = list(Path.cwd().glob(
        f"logs/run_evaluation/{run_id}/{model_tag}/{inst.instance_id}/report.json"
    ))
    if not candidates:
        # Fallback: the harness writes a top-level run report too.
        top = list(report_dir.glob(f"*.{run_id}.json"))
        if top:
            try:
                data = json.loads(top[0].read_text())
                resolved_ids = set(data.get("resolved_ids", []))
                ok = inst.instance_id in resolved_ids
                return ok, f"top-level report: resolved={ok}"
            except Exception:
                pass
        return None, "verifier_unavailable: no per-instance report produced"

    try:
        data = json.loads(candidates[0].read_text())
        # The per-instance report nests under the instance_id.
        inst_data = data.get(inst.instance_id, data)
        resolved = bool(inst_data.get("resolved"))
        tests_status = inst_data.get("tests_status", {})
        f2p = tests_status.get("FAIL_TO_PASS", {})
        p2p = tests_status.get("PASS_TO_PASS", {})
        summary = (
            f"resolved={resolved} "
            f"F2P: success={len(f2p.get('success', []))} "
            f"failure={len(f2p.get('failure', []))} "
            f"P2P: success={len(p2p.get('success', []))} "
            f"failure={len(p2p.get('failure', []))}"
        )
        return resolved, summary
    except Exception as e:
        return None, f"verifier_unavailable: report parse failed: {e}"


def verify_instance(
    inst: SweBenchInstance,
    repo_path: Path,
    *,
    python: str | None = None,
) -> tuple[bool, str]:
    """DEPRECATED — runs modern pytest against legacy repos and returns
    bogus results. Kept as a thin shim that fails loud so any caller
    still using it gets a clear message instead of a silent wrong grade.

    Real verification goes through `verify_with_swebench_harness(inst,
    patch)`, which uses the official swebench Docker harness.
    """
    return False, (
        "verify_instance is deprecated; use verify_with_swebench_harness "
        "with the agent's submitted patch and a Docker-enabled host."
    )
