"""Retroactively grade existing trajectories via the SWE-bench Docker harness.

Usage:
    python -m bench.cli.regrade \
        --trajectories bench/cache/trajectories \
        --results bench/cache/results.jsonl \
        [--instance-id pytest-dev__pytest-6202] \
        [--config code_graph_mcp]

For each trajectory file found, extracts the agent's submitted patch from
`info.submission` (and falls back to scanning messages), invokes the
official swebench harness via `bench.datasets.swe_bench.verify_with_swebench_harness`,
and updates the matching row in `results.jsonl` with `outcome=resolved|failed|verifier_unavailable`
plus a `verify_summary`.

Requires Docker on the host. Without it every row will end up flagged
`verifier_unavailable` (which is still strictly more honest than the
old verifier's silent `failed`).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bench.datasets.swe_bench import (
    SweBenchInstance,
    load_instances,
    verify_with_swebench_harness,
    _docker_available,
)


def _patch_from_trajectory(path: Path) -> str:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return ""
    info = data.get("info", {})
    sub = info.get("submission") or info.get("patch") or ""
    if sub:
        return sub
    # Fallback: look for a `git diff` in trailing assistant messages.
    msgs = data.get("messages", [])
    for m in reversed(msgs):
        content = m.get("content") or ""
        if isinstance(content, str) and content.startswith("diff --git"):
            return content
    return ""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--trajectories", type=Path, required=True)
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--instance-id", default=None)
    p.add_argument("--config", default=None)
    p.add_argument("--namespace", default="swebench",
                   help="Docker image namespace. 'swebench' = prebuilt; "
                        "None = local build.")
    p.add_argument("--timeout", type=int, default=1800)
    args = p.parse_args(argv)

    if not _docker_available():
        print("[regrade] docker not available — every row will be marked "
              "verifier_unavailable")

    insts_by_id = {i.instance_id: i for i in load_instances()}

    # Index existing results by (task_id, config) so we can patch them.
    rows = []
    for line in args.results.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    index = {(r["task_id"], r["config"]): r for r in rows}

    updated = 0
    for traj_path in sorted(args.trajectories.glob("*.json")):
        stem = traj_path.stem  # "<instance>__<cfg>"
        if "__" not in stem:
            continue
        instance_id, _, cfg = stem.rpartition("__")
        if args.instance_id and instance_id != args.instance_id:
            continue
        if args.config and cfg != args.config:
            continue
        inst = insts_by_id.get(instance_id)
        if not inst:
            print(f"[regrade] {stem}: not in dataset, skip")
            continue
        patch = _patch_from_trajectory(traj_path)
        if not patch.strip():
            print(f"[regrade] {stem}: empty patch")
            row = index.get((instance_id, cfg))
            if row:
                row["outcome"] = "failed"
                row["verify_summary"] = "empty patch"
                updated += 1
            continue
        resolved, summary = verify_with_swebench_harness(
            inst, patch,
            run_id=f"regrade-{instance_id}-{cfg}",
            namespace=(None if args.namespace.lower() == "none" else args.namespace),
            timeout=args.timeout,
        )
        if resolved is None:
            outcome = "verifier_unavailable"
        else:
            outcome = "resolved" if resolved else "failed"
        print(f"[regrade] {stem}: {outcome} — {summary[:120]}")
        row = index.get((instance_id, cfg))
        if row:
            row["outcome"] = outcome
            row["verify_summary"] = summary[-300:]
            updated += 1

    with args.results.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"[regrade] updated {updated} rows in {args.results}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
