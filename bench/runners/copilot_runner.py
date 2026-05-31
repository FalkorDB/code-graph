"""Benchmark harness driving the **real GitHub Copilot CLI** over SWE-bench.

Unlike `mini_runner` (a scripted ReAct loop with a hard step cap), this runner
invokes the production Copilot CLI headlessly so the measured token / accuracy
numbers reflect how people actually use the agent. It compares tracks that
differ ONLY in their MCP wiring:

    * ``copilot_no_mcp``  -- Copilot's native tools, no extra MCP servers.
    * ``code_graph``      -- same, plus our ``cgraph-mcp`` stdio server.
    * ``lsp``             -- (reserved) same, plus an LSP-backed MCP server.

For each ``(instance, track)`` it:
    1. prepares a fresh worktree at the instance base commit,
    2. (code_graph only) deletes any stale FalkorDB graph and re-indexes,
    3. builds a neutral prompt from the SWE-bench problem statement,
    4. runs ``copilot`` headless with a wall-clock timeout,
    5. parses tokens (summed from the debug process logs), premium requests and
       tool calls,
    6. extracts the patch via ``git diff <base_commit>`` (junk-excluded),
    7. writes a results row in the shared ``mini_runner`` schema so the existing
       Docker grader (``swebench_verify.py``) works unchanged.

Grading is intentionally deferred: run this to generate patches + token rows,
then grade with the official SWE-bench Docker harness.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from bench.datasets import swe_bench

RUNNER_VERSION = "copilot-runner/1"

# Tracks that only need different Copilot MCP wiring.
NO_MCP = "copilot_no_mcp"
CODE_GRAPH = "code_graph"
VALID_TRACKS = (NO_MCP, CODE_GRAPH)

DEFAULT_CACHE = Path(__file__).resolve().parents[1] / "cache" / "copilot"

# Dirs that must never end up in an extracted patch even if Copilot or a tool
# left them untracked in the worktree.
_PATCH_EXCLUDES = (
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".eggs",
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "build",
    "dist",
)

# The code-graph MCP server lives in a sibling worktree and is launched via a
# wrapper that fixes PYTHONPATH (see _write_mcp_config).
DEFAULT_MCP_SERVER_ROOT = Path(
    os.environ.get(
        "CGRAPH_MCP_SERVER_ROOT",
        "/Users/dvirdukhan/Code/code-graph/.worktrees/mcp-smoke",
    )
)


# ---------------------------------------------------------------------------
# Prompt assembly (symmetric across tracks; only the capability note differs)
# ---------------------------------------------------------------------------

_BASE_PROMPT = """\
You are fixing a bug in the Python repository checked out at {cwd}.

{problem}

Inspect the repository to understand the relevant code before editing, then
make the minimal source change that fixes the issue. Do not modify test files.
{capability}
When you are done, stop and give a one-line summary of what you changed."""

_CAP_NO_MCP = (
    "No external MCP tools are available; use Copilot's built-in file, search "
    "and edit tools."
)
_CAP_CODE_GRAPH = (
    "A code-graph MCP server is available exposing code-navigation tools "
    "(search_code, get_callers, get_callees, get_dependencies, impact_analysis, "
    "find_path). When calling them, pass project=\"{project}\". Prefer precise "
    "code-navigation tools over plain text search when they help. Do not use the "
    "`ask` tool."
)


def build_prompt(track: str, cwd: Path, problem: str, project: str) -> str:
    if track == CODE_GRAPH:
        capability = _CAP_CODE_GRAPH.format(project=project)
    else:
        capability = _CAP_NO_MCP
    return _BASE_PROMPT.format(cwd=cwd, problem=problem.strip(), capability=capability)


# ---------------------------------------------------------------------------
# code-graph MCP wiring
# ---------------------------------------------------------------------------


def _write_mcp_wrapper(run_dir: Path, server_root: Path) -> Path:
    """Write the stdio launcher for cgraph-mcp.

    The server's editable install is only importable with the server worktree
    on PYTHONPATH, so the wrapper cd's there and sets PYTHONPATH before exec'ing
    the server's venv python. Validated to start in ~1.7s from any cwd.
    """
    py = server_root / ".venv" / "bin" / "python"
    if not py.exists():
        raise FileNotFoundError(f"cgraph-mcp server python not found: {py}")
    wrapper = run_dir / "cgraph-mcp-wrapper.sh"
    wrapper.write_text(
        "#!/bin/bash\n"
        f'cd "{server_root}"\n'
        f'export PYTHONPATH="{server_root}:$PYTHONPATH"\n'
        f'exec "{py}" -c "from api.mcp.server import main; main()"\n'
    )
    wrapper.chmod(0o755)
    return wrapper


def _write_mcp_config(run_dir: Path, wrapper: Path, falkor_host: str, falkor_port: int) -> Path:
    cfg = run_dir / "cg-mcp-config.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "code-graph": {
                        "command": str(wrapper),
                        "args": [],
                        "env": {
                            "FALKORDB_HOST": falkor_host,
                            "FALKORDB_PORT": str(falkor_port),
                        },
                    }
                }
            },
            indent=2,
        )
    )
    return cfg


def _falkor_settings() -> tuple[str, int]:
    return (
        os.environ.get("FALKORDB_HOST", "127.0.0.1"),
        int(os.environ.get("FALKORDB_PORT", "6379")),
    )


def ensure_indexed(repo_path: Path, *, fresh: bool = True) -> float:
    """Delete any stale graph for this worktree and (re)index it.

    Returns indexing wall-clock seconds. Indexes via the running code-graph
    HTTP API (``/api/analyze_folder``); the agent's cgraph-mcp reads the same
    FalkorDB instance, so the graph ``code:{repo_path.name}:_default`` is what
    the agent will query with ``project=repo_path.name``.
    """
    import httpx
    import redis

    host, port = _falkor_settings()
    repo_name = repo_path.name
    graph = f"code:{repo_name}:_default"

    if fresh:
        try:
            r = redis.Redis(host=host, port=port, decode_responses=True, socket_timeout=2)
            if graph in (r.execute_command("GRAPH.LIST") or []):
                r.execute_command("GRAPH.DELETE", graph)
                print(f"[index] dropped stale {graph}")
        except Exception as exc:  # noqa: BLE001
            print(f"[index] WARN could not drop {graph}: {exc!r}")

    base = os.environ.get("CODEGRAPH_URL", "http://127.0.0.1:5000").rstrip("/")
    token = os.environ.get("SECRET_TOKEN") or os.environ.get("CODEGRAPH_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    default_ignore = [
        ".git", "venv", ".venv", "node_modules", "__pycache__",
        "rubi/rules", "build", "dist", ".tox", ".eggs",
    ]
    t0 = time.time()
    with httpx.Client(timeout=7200.0, headers=headers) as c:
        # Preflight: confirm the API server points at the same FalkorDB the
        # agent's MCP server will read, else the agent queries an empty graph.
        try:
            h = c.get(f"{base}/api/_health", timeout=10.0)
            if h.status_code == 200:
                hp = int(h.json().get("falkordb_port", port))
                if hp != port:
                    raise RuntimeError(
                        f"API server FalkorDB port {hp} != runner port {port}; "
                        "agent and indexer would see different graphs."
                    )
        except httpx.HTTPError:
            pass  # _health is best-effort
        resp = c.post(
            f"{base}/api/analyze_folder",
            json={"path": str(repo_path), "ignore": default_ignore},
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"analyze_folder {resp.status_code}: {resp.text[:300]}. "
                f"Check ALLOWED_ANALYSIS_DIR covers {repo_path}."
            )
    dt = time.time() - t0
    print(f"[index] indexed {repo_name} in {dt:.1f}s")
    return dt


# ---------------------------------------------------------------------------
# Copilot invocation
# ---------------------------------------------------------------------------


def run_copilot(
    *,
    prompt: str,
    model: str,
    cwd: Path,
    log_dir: Path,
    mcp_config: Path | None,
    wall_time: float,
) -> dict[str, Any]:
    """Invoke Copilot headless. Returns {stdout_jsonl, returncode, timed_out, wall}."""
    # Copilot runs with cwd=worktree and resolves a relative --log-dir against
    # THAT cwd, which would scatter process logs under the worktree. Force
    # absolute so logs land where the parser reads them.
    log_dir = log_dir.resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    session_id = str(uuid.uuid4())
    cmd = [
        "copilot", "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--no-remote",
        "--disable-builtin-mcps",
        "--allow-all-tools",
        "--allow-all-paths",
        "--add-dir", str(cwd),
        "--log-level", "debug",
        "--log-dir", str(log_dir),
        "--session-id", session_id,
    ]
    if mcp_config is not None:
        cmd += ["--additional-mcp-config", f"@{mcp_config}"]

    env = dict(os.environ)
    t0 = time.time()
    timed_out = False
    # start_new_session=True puts Copilot + its children (MCP server, shells)
    # in a fresh process group we can signal as a unit on timeout.
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=wall_time)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group(proc.pid)
        try:
            stdout, stderr = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
    wall = time.time() - t0
    (log_dir / "stdout.jsonl").write_text(stdout or "")
    (log_dir / "stderr.txt").write_text(stderr or "")
    return {
        "stdout": stdout or "",
        "returncode": proc.returncode,
        "timed_out": timed_out,
        "wall": wall,
    }


def _kill_group(pid: int) -> None:
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return
        time.sleep(2)


# ---------------------------------------------------------------------------
# Parsing: tokens (debug logs), premium / files (result event), tool calls
# ---------------------------------------------------------------------------

# A genuine Copilot model-response usage block. We require all of these keys so
# stray JSON (e.g. an MCP tool result or the server's own stderr) can't be
# mis-counted as token usage.
_USAGE_REQUIRED = ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_tokens_details")


def parse_tokens_from_logs(log_dir: Path) -> dict[str, int]:
    """Sum token usage across every model-response block in this run's logs.

    Copilot fans out multiple requests per turn; each writes a pretty-printed
    ``"usage": { ... }`` block to ``process-*.log``. We sum them all. The log
    dir is per-run, so there is no cross-run contamination.
    """
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cached_input_tokens": 0,
        "cache_creation_tokens": 0,
        "usage_blocks": 0,
    }
    for log in sorted(log_dir.glob("process-*.log")):
        text = log.read_text(errors="replace")
        for block in _iter_usage_blocks(text):
            if not all(k in block for k in _USAGE_REQUIRED):
                continue
            totals["input_tokens"] += int(block.get("prompt_tokens", 0))
            totals["output_tokens"] += int(block.get("completion_tokens", 0))
            totals["total_tokens"] += int(block.get("total_tokens", 0))
            details = block.get("prompt_tokens_details") or {}
            totals["cached_input_tokens"] += int(details.get("cached_tokens", 0))
            totals["cache_creation_tokens"] += int(details.get("cache_creation_tokens", 0))
            totals["usage_blocks"] += 1
    return totals


def _iter_usage_blocks(text: str):
    """Yield parsed JSON objects for each ``"usage": {...}`` in the log text.

    Brace-balanced scan from the opening ``{`` so multi-line pretty-printed
    blocks parse correctly.
    """
    for m in re.finditer(r'"usage"\s*:\s*\{', text):
        start = m.end() - 1  # position of the opening brace
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    blob = text[start : i + 1]
                    try:
                        yield json.loads(blob)
                    except json.JSONDecodeError:
                        pass
                    break


def parse_result_event(stdout: str) -> dict[str, Any]:
    """Extract premium-request count + files modified from the result event."""
    out = {"premium_requests": 0, "files_modified": [], "is_error": None, "num_turns": None}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") != "result":
            continue
        data = ev.get("data", ev)
        usage = data.get("usage") or {}
        out["premium_requests"] = int(usage.get("premiumRequests", 0) or 0)
        code_changes = usage.get("codeChanges") or data.get("codeChanges") or {}
        out["files_modified"] = list(code_changes.get("filesModified", []) or [])
        out["is_error"] = data.get("isError")
        out["num_turns"] = data.get("numTurns")
    return out


def parse_tool_calls(stdout: str) -> tuple[int, dict[str, int]]:
    """Count tool invocations by name from execution-start events."""
    by_name: dict[str, int] = {}
    total = 0
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = ev.get("type", "")
        if not etype.startswith("tool.execution_start"):
            continue
        data = ev.get("data", {})
        name = data.get("name") or data.get("toolName") or "unknown"
        if name is None:
            name = "unknown"
        by_name[name] = by_name.get(name, 0) + 1
        total += 1
    return total, by_name


# ---------------------------------------------------------------------------
# Patch extraction
# ---------------------------------------------------------------------------


def extract_patch(repo_path: Path, base_commit: str) -> dict[str, Any]:
    """Capture all changes vs base as a single unified diff (junk-excluded).

    ``git add -A`` then ``git diff --cached <base>`` captures committed, staged,
    unstaged and untracked changes regardless of how Copilot left the tree.
    Build/cache dirs are excluded via pathspec.
    """
    excludes = [f":(exclude){d}" for d in _PATCH_EXCLUDES]
    excludes += [f":(exclude)*/{d}/*" for d in _PATCH_EXCLUDES]
    swe_bench._git(["add", "-A"], cwd=repo_path, check=False)
    res = swe_bench._git(
        ["diff", "--cached", base_commit, "--", ".", *excludes],
        cwd=repo_path,
        check=False,
    )
    patch = res.stdout
    files = _patched_files(patch)
    touched_tests = any(not swe_bench.is_source_file(f) and f.endswith(".py") for f in files) or any(
        swe_bench._TEST_PATH_RE.search(f) for f in files
    )
    return {"patch": patch, "patched_files": files, "touched_tests": touched_tests}


def _patched_files(patch: str) -> list[str]:
    files = []
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[6:])
    return files


# ---------------------------------------------------------------------------
# Per-instance driver
# ---------------------------------------------------------------------------


def run_one(
    inst: swe_bench.SweBenchInstance,
    *,
    track: str,
    model: str,
    cache_dir: Path,
    wall_time: float,
    server_root: Path,
    run_idx: int = 0,
) -> dict[str, Any]:
    work_root = cache_dir / "worktrees" / track
    work_root.mkdir(parents=True, exist_ok=True)
    run_dir = cache_dir / "runs" / model / track / inst.instance_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== {inst.instance_id} [{track}] model={model} ===")
    repo_path = swe_bench.prepare_worktree(
        inst, worktrees_dir=work_root.resolve(), apply_test_patch=True
    )

    index_sec = None
    mcp_config = None
    if track == CODE_GRAPH:
        index_sec = ensure_indexed(repo_path, fresh=True)
        host, port = _falkor_settings()
        wrapper = _write_mcp_wrapper(run_dir, server_root)
        mcp_config = _write_mcp_config(run_dir, wrapper, host, port)

    prompt = build_prompt(track, repo_path, inst.problem_statement, inst.instance_id)
    (run_dir / "prompt.txt").write_text(prompt)

    result = run_copilot(
        prompt=prompt,
        model=model,
        cwd=repo_path,
        log_dir=run_dir / "logs",
        mcp_config=mcp_config,
        wall_time=wall_time,
    )

    tokens = parse_tokens_from_logs(run_dir / "logs")
    result_ev = parse_result_event(result["stdout"])
    tool_total, tool_by_name = parse_tool_calls(result["stdout"])
    patch_info = extract_patch(repo_path, inst.base_commit)

    row = {
        "benchmark": "swe_bench_verified",
        "task_id": inst.instance_id,
        "config": track,
        "model": model,
        "run_idx": run_idx,
        "runner": RUNNER_VERSION,
        "input_tokens": tokens["input_tokens"],
        "output_tokens": tokens["output_tokens"],
        "total_tokens": tokens["total_tokens"],
        "cached_input_tokens": tokens["cached_input_tokens"],
        "cache_creation_tokens": tokens["cache_creation_tokens"],
        "usage_blocks": tokens["usage_blocks"],
        "premium_requests": result_ev["premium_requests"],
        "tool_calls_total": tool_total,
        "tool_calls_by_name": tool_by_name,
        "files_modified": result_ev["files_modified"],
        "touched_tests": patch_info["touched_tests"],
        "index_sec": index_sec,
        "timed_out": result["timed_out"],
        "returncode": result["returncode"],
        "outcome": "ungraded",
        "patch": patch_info["patch"],
        "wall_clock_sec": round(result["wall"], 2),
        "completed": True,
    }
    print(
        f"[done] {inst.instance_id} [{track}] in={row['input_tokens']} "
        f"out={row['output_tokens']} premium={row['premium_requests']} "
        f"tools={tool_total} patch_files={len(patch_info['patched_files'])} "
        f"timed_out={result['timed_out']} wall={row['wall_clock_sec']}s"
    )
    return row


# ---------------------------------------------------------------------------
# Resume / IO
# ---------------------------------------------------------------------------


def _load_done(results_path: Path) -> set[tuple[str, str, int]]:
    done: set[tuple[str, str, int]] = set()
    if not results_path.exists():
        return done
    for line in results_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("completed") and r.get("runner") == RUNNER_VERSION:
            done.add((r["task_id"], r["config"], int(r.get("run_idx", 0))))
    return done


def _append_row(results_path: Path, row: dict[str, Any]) -> None:
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with results_path.open("a") as f:
        f.write(json.dumps(row) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_instance_ids(args) -> list[str]:
    if args.instances_file:
        ids = [
            ln.strip()
            for ln in Path(args.instances_file).read_text().splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
        return ids
    if args.instance:
        return list(args.instance)
    raise SystemExit("provide --instance ID [ID ...] or --instances-file FILE")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Drive Copilot CLI over SWE-bench Verified.")
    p.add_argument("--instance", nargs="*", help="explicit instance id(s)")
    p.add_argument("--instances-file", help="file with one instance id per line")
    p.add_argument(
        "--track", action="append", choices=VALID_TRACKS, default=None,
        help="track(s) to run (default: both)",
    )
    p.add_argument("--model", default="claude-opus-4.8")
    p.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    p.add_argument("--results", default=None, help="results jsonl (default: <cache>/<model>/results.jsonl)")
    p.add_argument("--wall-time", type=float, default=1200.0, help="per-run wall-clock seconds")
    p.add_argument("--server-root", default=str(DEFAULT_MCP_SERVER_ROOT))
    p.add_argument("--run-idx", type=int, default=0)
    args = p.parse_args(argv)

    tracks = args.track or list(VALID_TRACKS)
    cache_dir = Path(args.cache_dir).resolve()
    results_path = (
        Path(args.results)
        if args.results
        else cache_dir / args.model / "results.jsonl"
    )
    server_root = Path(args.server_root)

    ids = _load_instance_ids(args)
    all_insts = {i.instance_id: i for i in swe_bench.load_instances()}
    missing = [i for i in ids if i not in all_insts]
    if missing:
        raise SystemExit(f"unknown instance ids: {missing}")
    insts = [all_insts[i] for i in ids]

    done = _load_done(results_path)
    print(f"[plan] {len(insts)} instances x {len(tracks)} tracks; "
          f"{len(done)} rows already complete; results -> {results_path}")

    for inst in insts:
        for track in tracks:
            key = (inst.instance_id, track, args.run_idx)
            if key in done:
                print(f"[skip] {inst.instance_id} [{track}] already complete")
                continue
            try:
                row = run_one(
                    inst,
                    track=track,
                    model=args.model,
                    cache_dir=cache_dir,
                    wall_time=args.wall_time,
                    server_root=server_root,
                    run_idx=args.run_idx,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[error] {inst.instance_id} [{track}]: {exc!r}", file=sys.stderr)
                row = {
                    "benchmark": "swe_bench_verified",
                    "task_id": inst.instance_id,
                    "config": track,
                    "model": args.model,
                    "run_idx": args.run_idx,
                    "runner": RUNNER_VERSION,
                    "outcome": "error",
                    "error": repr(exc),
                    "patch": "",
                    "completed": False,
                }
            _append_row(results_path, row)

    print("[plan] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
