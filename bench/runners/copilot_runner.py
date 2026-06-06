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
import traceback
import uuid
from pathlib import Path
from typing import Any

from bench.datasets import swe_bench

RUNNER_VERSION = "copilot-runner/2"

# Marks the measurement epoch for answer-leakage hardening + thinking-on +
# full-trace capture. Recorded on every row so rows from different harness
# generations are never silently pooled.
#
# harden/2: closed the git-walk-up leak. Stripping the worktree's own ``.git``
# did NOT stop ``git`` (run by the agent or by the indexer's branch detection)
# from traversing UP to the enclosing harness repo, which leaked its branch name
# and commit messages (revealing the benchmark intent) and mis-keyed the index
# under the parent branch. Fixed by recursively stripping ``.git``, pinning the
# index to the ``_default`` branch, scrubbing inherited ``GIT_*`` vars, and
# fencing the agent's git with ``GIT_CEILING_DIRECTORIES``. harden/1 rows where
# the agent ran git are suspect and must not be pooled with harden/2.
HARNESS_HARDENING_VERSION = "harden/2"

# Reasoning effort for scored runs. Thinking is now ENABLED by default so the
# agent's deliberation is captured in the trace; the reasoning-token cost is
# accounted SEPARATELY (see parse_tokens_from_logs -> reasoning_tokens) so the
# base token comparison across arms stays interpretable. All arms in an epoch
# share one effort level. Override with COPILOT_REASONING_EFFORT.
DEFAULT_REASONING_EFFORT = os.environ.get("BENCH_REASONING_EFFORT", "medium")


def _resolve_reasoning_effort() -> str | None:
    """Effort level to pass to copilot, or None to omit the flag entirely."""
    effort = os.environ.get("COPILOT_REASONING_EFFORT", DEFAULT_REASONING_EFFORT)
    if not effort or effort.lower() == "off":
        return None
    return effort


# Tracks that only need different Copilot MCP wiring.
NO_MCP = "copilot_no_mcp"
CODE_GRAPH = "code_graph"
LSP = "lsp"
VALID_TRACKS = (NO_MCP, CODE_GRAPH, LSP)

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

# The LSP-backed MCP server (bench/mcp/lsp_server.py) lives in THIS bench tree
# (mcp-t17), but must be launched with the mcp-smoke venv python because that is
# the only environment with BOTH `mcp`/FastMCP AND `multilspy`. Its wrapper also
# prepends the mcp-smoke venv `bin/` to PATH so the `jedi-language-server`
# console script multilspy launches by bare name is found.
LSP_BENCH_ROOT = Path(
    os.environ.get("LSP_BENCH_ROOT", str(Path(__file__).resolve().parents[2]))
)
DEFAULT_LSP_SERVER_PYTHON_ROOT = Path(
    os.environ.get("LSP_SERVER_PYTHON_ROOT", str(DEFAULT_MCP_SERVER_ROOT))
)


# ---------------------------------------------------------------------------
# Prompt assembly (symmetric across tracks; only the capability note differs)
# ---------------------------------------------------------------------------

FIX = "fix"
LOCALIZE = "localize"
VALID_MODES = (FIX, LOCALIZE)

# The strict line the localization agent must end on. Re-used by the parser.
LOCALIZE_SENTINEL = "FINAL_LOCALIZATION_JSON:"

_BASE_PROMPT = """\
You are fixing a bug in the Python repository checked out at {cwd}.

{problem}

Inspect the repository to understand the relevant code before editing, then
make the minimal source change that fixes the issue. Do not modify test files.
{capability}
When you are done, stop and give a one-line summary of what you changed."""

_LOCALIZE_PROMPT = """\
You are localizing (not fixing) a bug in the Python repository checked out at {cwd}.

{problem}

Investigate the repository to determine which SOURCE files must be edited to fix
this issue. Do NOT modify any files. Do NOT run or edit tests.
{capability}
When you are confident, finish your FINAL assistant message with a single line in
EXACTLY this format (most-likely file first, repo-root-relative paths, Python
source files only, no test or doc files):

{sentinel} ["pkg/module_a.py", "pkg/module_b.py"]

Write that line as plain text in your own final message. Do NOT emit it through a
shell command, `echo`, a file write, or any tool call."""

# Lane 1 adoption-calibration frozen text (prereg §5). Do NOT edit without
# amending the pre-registration; the experiment's validity depends on the exact
# wording (negative-control / non-overfitting requirement).
#
# SEM (lever a): edge-semantics clause appended verbatim to the code_graph
# capability preamble. NO frequency/benchmark prior (the rejected wording "the
# edit site is often a caller or a sibling, not the matched symbol" is forbidden).
_ADOPT_SEM_CLAUSE = (
    "Graph edges (calls, imports, inheritance, overrides, definitions) are "
    "evidence that code is RELATED — not evidence that a connected file is the "
    "location you must change. Treat every graph result as a hypothesis. Keep a "
    "candidate in your final answer only when the code you have read supports "
    "that the file participates directly in the behavior the task asks you to "
    "change; drop it otherwise. Relatedness alone is not a reason to keep or to "
    "drop."
)
# RAT (lever b): mandatory keep/drop-with-reason step injected into the localize
# prompt body, BEFORE the FINAL sentinel instruction.
_ADOPT_RAT_STEP = (
    "Before your final answer, list every file the graph surfaced and, for each, "
    "write one line: `KEEP <file> — <reason from code you read>` or "
    "`DROP <file> — <reason>`. Your final answer must be consistent with these "
    "decisions. You may add files the graph did not surface."
)
# RAT localize variant: identical to _LOCALIZE_PROMPT but with _ADOPT_RAT_STEP
# inserted after the capability note and before the FINAL sentinel instruction.
_LOCALIZE_PROMPT_RAT = """\
You are localizing (not fixing) a bug in the Python repository checked out at {cwd}.

{problem}

Investigate the repository to determine which SOURCE files must be edited to fix
this issue. Do NOT modify any files. Do NOT run or edit tests.
{capability}
{rat_step}
When you are confident, finish your FINAL assistant message with a single line in
EXACTLY this format (most-likely file first, repo-root-relative paths, Python
source files only, no test or doc files):

{sentinel} ["pkg/module_a.py", "pkg/module_b.py"]

Write that line as plain text in your own final message. Do NOT emit it through a
shell command, `echo`, a file write, or any tool call."""

# Valid Lane 1 arm names. CTRL == canonical nudge base (prereg §2 amended: a
# neutral preamble yields ~0% spontaneous adoption on strong models, leaving
# nothing to calibrate, so CTRL is pinned to _CAP_CODE_GRAPH_NUDGE).
ADOPT_ARMS = ("ctrl", "sem", "rat")

_CAP_NO_MCP = (
    "No external MCP tools are available; use Copilot's built-in file, search "
    "and edit tools."
)
# Matched no-MCP nudge: parallels the code_graph search-first mandate without
# naming any specific tool, so the comparison isolates the graph, not the
# "search before grep" instruction.
_CAP_NO_MCP_NUDGE = (
    "No external MCP tools are available. Before resorting to plain text search "
    "(grep/rg), begin by broadly mapping the repository structure to locate the "
    "relevant symbols and how they relate; use Copilot's built-in file, search "
    "and edit tools."
)
_CAP_CODE_GRAPH = (
    "A code-graph MCP server is available exposing code-navigation tools "
    "(search_code, get_callers, get_callees, get_dependencies, impact_analysis, "
    "find_path). The repository has ALREADY been indexed under project=\"{project}\" "
    "and is ready to query immediately — do NOT call index_repo; call the "
    "navigation tools directly with project=\"{project}\". Prefer precise "
    "code-navigation tools over plain text search when they help. Do not use the "
    "`ask` tool."
)
# Nudged code_graph: mandate an initial search_code call to measure the tool's
# value when the model is forced to engage it (the neutral prompt yields ~0%
# spontaneous adoption on strong models).
_CAP_CODE_GRAPH_NUDGE = (
    "A code-graph MCP server is available exposing code-navigation tools "
    "(search_code, get_callers, get_callees, get_dependencies, impact_analysis, "
    "find_path). The repository has ALREADY been indexed under project=\"{project}\" "
    "and is ready to query — do NOT call index_repo. You MUST begin by calling "
    "search_code(project=\"{project}\") to "
    "locate the relevant symbols BEFORE any plain text search, and prefer these "
    "graph tools over grep throughout your investigation. Do not use the `ask` tool."
)


# Traversal-mandate variant: gated by CGRAPH_TRAVERSE_NUDGE=1 + --nudge. Forces the
# model to actually traverse (get_callers/get_callees/find_path) from candidate
# symbols, isolating whether traversal — not just search-first — helps localization.
_CAP_CODE_GRAPH_TRAVERSE = (
    "A code-graph MCP server is available exposing code-navigation tools "
    "(search_code, get_callers, get_callees, get_dependencies, impact_analysis, "
    "find_path). The repository has ALREADY been indexed under project=\"{project}\" "
    "— do NOT call index_repo. You MUST follow this workflow: (1) call search_code(project=\"{project}\") "
    "to locate candidate symbols; (2) for your top candidate symbol(s) you MUST call "
    "get_callers AND get_callees (and find_path between candidates when relevant), and "
    "inspect the files those calls surface, BEFORE finalizing your answer; (3) prefer "
    "these graph tools over grep throughout. Do not use the `ask` tool."
)


# Spike variant (Spike 1a: IMPORTS + OVERRIDES edges): gated by CGRAPH_SPIKE_NUDGE=1
# + --nudge. Forces the model to exercise the NEW edge types — get_importers
# (file<-file IMPORTS) and get_overrides (subclass.method->ancestor.method) — which
# can bridge to gold files that the CALLS/DEFINES/EXTENDS call-graph never reached.
_CAP_CODE_GRAPH_SPIKE = (
    "A code-graph MCP server is available exposing code-navigation tools "
    "(search_code, get_callers, get_callees, get_dependencies, impact_analysis, "
    "find_path, get_importers, get_overrides). The repository has ALREADY been "
    "indexed under project=\"{project}\" — do NOT call index_repo. You MUST follow this workflow: "
    "(1) call search_code(project=\"{project}\") to locate candidate symbols and "
    "their files; (2) for your top candidate file(s) you MUST call "
    "get_importers (to find which other source files import them) AND, for any "
    "candidate class/method, get_overrides (to find ancestor or subclass methods "
    "that share its behavior); inspect the files those calls surface BEFORE "
    "finalizing your answer; (3) prefer these graph tools over grep throughout. "
    "Do not use the `ask` tool."
)


# Substitution+stop variant: gated by CGRAPH_SUBST_NUDGE=1 + --nudge. Targets the
# observed thrash failure mode (agent ignores a correct high-confidence rank-1 hit,
# chases a wrong hypothesis with broad grep sweeps, and never stops). Instructs the
# agent to TRUST the ranked search_code output (the top hits and their
# likely_related_files) as the candidate answer set, confirm with at most 1-2 file
# views, then STOP — substituting the graph for grep rather than running both.
_CAP_CODE_GRAPH_SUBST = (
    "A code-graph MCP server is available exposing code-navigation tools "
    "(search_code, get_callers, get_callees, get_dependencies, impact_analysis, "
    "find_path). The repository has ALREADY been indexed under project=\"{project}\" "
    "— do NOT call index_repo. You MUST follow this workflow: (1) call "
    "search_code(project=\"{project}\") with a CONCEPTUAL free-text query describing "
    "the buggy behavior and area; (2) TRUST the ranked results — the top-ranked files "
    "and the likely_related_files attached to them ARE your candidate answer set. "
    "Confirm with AT MOST 1-2 targeted file views; (3) do NOT run broad grep/find "
    "sweeps to second-guess a confident high-ranked hit, and do NOT keep searching "
    "once the ranked results plus a quick view agree — STOP and answer. Substitute "
    "the graph for grep; do not run both. Do not use the `ask` tool."
)


# LSP capability note. The LSP MCP server exposes jedi-backed navigation tools
# (goto_definition, find_references, hover, document_symbols). Positions are
# 0-based (LSP convention) while grep/view are 1-based — the agent must adjust.
_CAP_LSP = (
    "An LSP MCP server is available exposing jedi-backed Python navigation tools "
    "(goto_definition, find_references, hover, document_symbols). Paths are "
    "repo-root-relative; line/character positions are 0-based (subtract 1 from "
    "the 1-based line numbers grep/view report). Prefer these precise "
    "navigation tools over plain text search when they help."
)
# Nudged LSP: mandate an initial navigation call to measure the tool's value
# when the model is forced to engage it.
_CAP_LSP_NUDGE = (
    "An LSP MCP server is available exposing jedi-backed Python navigation tools "
    "(goto_definition, find_references, hover, document_symbols). Paths are "
    "repo-root-relative; line/character positions are 0-based (subtract 1 from "
    "the 1-based line numbers grep/view report). You MUST begin by calling "
    "document_symbols on a likely-relevant file (or goto_definition on a symbol "
    "from the problem statement) BEFORE any plain text search, and prefer these "
    "LSP tools over grep throughout your investigation."
)


# Appended to the prompt under hardening (default ON; BENCH_BLOCK_NETWORK=0 to opt out). Tells the agent
# to derive the answer from the code only — not from the network, GitHub, the
# issue/PR number, git remotes, or the harness's own files.
_HARDEN_PROMPT_LINE = (
    "IMPORTANT: Determine the answer ONLY from the source code in the working "
    "directory. Do NOT access the network or fetch any URL; do NOT consult "
    "GitHub, pull requests, commits, patches, or diffs; do NOT read or infer "
    "anything from a git remote, `origin`, the issue/PR number, or files "
    "outside the working directory. Any attempt to look up the fix externally "
    "invalidates the result."
)


def _capability(track: str, project: str, *, nudge: bool, adopt_arm: str | None = None) -> str:
    if track == CODE_GRAPH:
        if adopt_arm is not None:
            # Lane 1 arms bypass the env-gated nudge variants entirely. CTRL,
            # SEM and RAT all share the canonical nudge base (prereg §2 amended);
            # SEM additionally appends the frozen edge-semantics clause.
            cap = _CAP_CODE_GRAPH_NUDGE.format(project=project)
            if adopt_arm == "sem":
                cap = f"{cap} {_ADOPT_SEM_CLAUSE}"
            return cap
        if nudge and os.environ.get("CGRAPH_SUBST_NUDGE") == "1":
            tmpl = _CAP_CODE_GRAPH_SUBST
        elif nudge and os.environ.get("CGRAPH_SPIKE_NUDGE") == "1":
            tmpl = _CAP_CODE_GRAPH_SPIKE
        elif nudge and os.environ.get("CGRAPH_TRAVERSE_NUDGE") == "1":
            tmpl = _CAP_CODE_GRAPH_TRAVERSE
        elif nudge:
            tmpl = _CAP_CODE_GRAPH_NUDGE
        else:
            tmpl = _CAP_CODE_GRAPH
        return tmpl.format(project=project)
    if track == LSP:
        return _CAP_LSP_NUDGE if nudge else _CAP_LSP
    return _CAP_NO_MCP_NUDGE if nudge else _CAP_NO_MCP


def build_prompt(
    track: str,
    cwd: Path,
    problem: str,
    project: str,
    *,
    nudge: bool = False,
    mode: str = FIX,
    adopt_arm: str | None = None,
) -> str:
    if adopt_arm is not None and (track != CODE_GRAPH or mode != LOCALIZE):
        raise ValueError(
            f"adopt_arm={adopt_arm!r} requires track={CODE_GRAPH} and mode={LOCALIZE}; "
            f"got track={track!r} mode={mode!r}"
        )
    if adopt_arm is not None and adopt_arm not in ADOPT_ARMS:
        raise ValueError(f"unknown adopt_arm={adopt_arm!r}; expected one of {ADOPT_ARMS}")
    capability = _capability(track, project, nudge=nudge, adopt_arm=adopt_arm)
    if swe_bench.network_block_enabled():
        capability = f"{capability}\n{_HARDEN_PROMPT_LINE}"
    if mode == LOCALIZE:
        if adopt_arm == "rat":
            return _LOCALIZE_PROMPT_RAT.format(
                cwd=cwd,
                problem=problem.strip(),
                capability=capability,
                rat_step=_ADOPT_RAT_STEP,
                sentinel=LOCALIZE_SENTINEL,
            )
        return _LOCALIZE_PROMPT.format(
            cwd=cwd,
            problem=problem.strip(),
            capability=capability,
            sentinel=LOCALIZE_SENTINEL,
        )
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


def _write_mcp_config(
    run_dir: Path,
    wrapper: Path,
    falkor_host: str,
    falkor_port: int,
    extra_env: dict[str, str] | None = None,
) -> Path:
    cfg = run_dir / "cg-mcp-config.json"
    env = {
        "FALKORDB_HOST": falkor_host,
        "FALKORDB_PORT": str(falkor_port),
    }
    if extra_env:
        env.update(extra_env)
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "code-graph": {
                        "command": str(wrapper),
                        "args": [],
                        "env": env,
                    }
                }
            },
            indent=2,
        )
    )
    return cfg


def _write_lsp_wrapper(run_dir: Path, repo_path: Path) -> Path:
    """Write the stdio launcher for the LSP MCP server (bench/mcp/lsp_server.py).

    The server module lives in this bench tree (LSP_BENCH_ROOT) but must run on
    the mcp-smoke venv python (the only env with both `mcp` and `multilspy`). The
    wrapper also prepends that venv's `bin/` to PATH so multilspy can exec the
    `jedi-language-server` console script by bare name, and points the adapter at
    the target repo via LSP_REPO_ROOT.
    """
    py = DEFAULT_LSP_SERVER_PYTHON_ROOT / ".venv" / "bin" / "python"
    if not py.exists():
        raise FileNotFoundError(f"lsp-mcp server python not found: {py}")
    venv_bin = DEFAULT_LSP_SERVER_PYTHON_ROOT / ".venv" / "bin"
    wrapper = run_dir / "lsp-mcp-wrapper.sh"
    wrapper.write_text(
        "#!/bin/bash\n"
        f'cd "{LSP_BENCH_ROOT}"\n'
        f'export PATH="{venv_bin}:$PATH"\n'
        f'export PYTHONPATH="{LSP_BENCH_ROOT}:$PYTHONPATH"\n'
        f'export LSP_REPO_ROOT="{repo_path}"\n'
        'export LSP_LANGUAGE="python"\n'
        f'exec "{py}" -c "from bench.mcp.lsp_server import main; main()"\n'
    )
    wrapper.chmod(0o755)
    return wrapper


def _write_lsp_mcp_config(run_dir: Path, wrapper: Path) -> Path:
    cfg = run_dir / "lsp-mcp-config.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "lsp": {
                        "command": str(wrapper),
                        "args": [],
                        "env": {},
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

    ``branch="_default"`` is passed EXPLICITLY so the index lands on the exact
    key the agent (which omits ``branch``) reads. Without it the API falls back
    to ``detect_branch(worktree)`` = ``git rev-parse``; when the hardened path
    has stripped the worktree's ``.git``, git walks UP to the enclosing harness
    repo and returns ITS branch, so the index would land under that branch key
    while the agent queries an empty ``_default`` graph.
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
            json={"path": str(repo_path), "ignore": default_ignore, "branch": "_default"},
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

COPILOT_MAX_ATTEMPTS = 3
COPILOT_RETRY_BACKOFF_SEC = 15.0

# Substrings that mark a transient startup/network failure (token validation
# fetch failed, connection resets) rather than a real model run.
_TRANSIENT_STARTUP_MARKERS = (
    "could not be validated",
    "fetch failed",
    "econnreset",
    "etimedout",
    "enotfound",
    "socket hang up",
    "network",
    "getaddrinfo",
)


def _is_transient_startup_failure(
    returncode: int | None, stdout: str, stderr: str
) -> bool:
    """True when Copilot exited early without producing any result stream.

    A genuine run always emits at least one JSON line on stdout. A transient
    auth/network failure exits non-zero with empty stdout and a recognizable
    error on stderr; those rows must be retried, not scored as recall=0.
    """
    if returncode in (0, None):
        return False
    if stdout and stdout.strip():
        return False
    blob = (stderr or "").lower()
    return any(marker in blob for marker in _TRANSIENT_STARTUP_MARKERS)


# ---------------------------------------------------------------------------
# Answer-leakage hardening (default ON; opt out with BENCH_BLOCK_NETWORK=0)
# ---------------------------------------------------------------------------
# Shell commands that can exfiltrate the gold answer from the network or from a
# git remote. Denied as ``shell(<cmd>:*)`` so the agent's tool layer refuses
# them outright (deny takes precedence over --allow-all-tools). These are a
# defense-in-depth layer, NOT a hermetic jail: a determined agent can still
# reach the network via python/node/etc., which is why detect_network_leak()
# backstops every run and trips signals are quarantined from scored numbers.
_DENY_SHELL_CMDS = (
    "curl", "wget", "gh", "nc", "ncat", "ssh", "scp", "telnet",
    "git fetch", "git pull", "git clone", "git remote",
    "git ls-remote", "git push",
)

# GitHub domains that serve merged-PR file lists / patches / commits. Denied via
# --deny-url (precedence over allow). The model endpoint (*.githubcopilot.com)
# and localhost (code-graph API :5000, FalkorDB) are deliberately NOT blocked.
_DENY_URLS = (
    "github.com",
    "*.github.com",
    "api.github.com",
    "raw.githubusercontent.com",
    "*.githubusercontent.com",
    "codeload.github.com",
    "patch-diff.githubusercontent.com",
    "objects.githubusercontent.com",
)


def _network_deny_flags() -> list[str]:
    """copilot CLI flags that block network/remote exfiltration of the gold answer."""
    flags = ["--excluded-tools=web_fetch"]
    for cmd in _DENY_SHELL_CMDS:
        flags.append(f"--deny-tool=shell({cmd}:*)")
    for url in _DENY_URLS:
        flags.append(f"--deny-url={url}")
    return flags


def _git_ceiling_dirs(cwd: Path) -> str:
    """``GIT_CEILING_DIRECTORIES`` value that fences git inside the worktree.

    Lists the worktree's parent (both resolved and lexical, to defeat symlinked
    paths) so git's upward repo discovery stops there: from inside the
    history-free worktree it then finds no repository instead of walking up to
    the enclosing harness repo. Listed dirs are NOT themselves crossed.
    """
    cwd_resolved = cwd.resolve()
    ceilings = {str(cwd_resolved.parent), str(cwd.parent)}
    return os.pathsep.join(sorted(ceilings))


def _harden_env(env: dict[str, str]) -> dict[str, str]:
    """Strip leak-enabling vars (opaque-name salt, GitHub creds) from the agent env.

    Also removes inherited ``GIT_*`` discovery overrides (``GIT_DIR``,
    ``GIT_WORK_TREE``, ``GIT_COMMON_DIR``, ``GIT_CONFIG``) which would otherwise
    let the agent's git escape the worktree regardless of ``GIT_CEILING_DIRECTORIES``,
    and sets ``GIT_CONFIG_NOSYSTEM=1`` so host git config can't re-point discovery.
    The actual upward fence (``GIT_CEILING_DIRECTORIES``) is set in ``run_copilot``
    where the worktree path is known.
    """
    for var in swe_bench.LEAK_SCRUB_ENV_VARS:
        env.pop(var, None)
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_CONFIG"):
        env.pop(var, None)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


# Substrings in a bash command that indicate an attempt to reach the gold answer
# via the network or a git remote / the cloned-repo offline oracle.
# NOTE: "/.git/" is handled separately (see _git_read_is_suspicious) because it
# legitimately appears in benign `find -not -path '*/.git/*'` / grep
# `--exclude-dir=.git` exclusions, which must NOT be flagged.
_LEAK_CMD_PATTERNS = (
    "github.com", "githubusercontent", "/pull/", "pull/", "/commit/",
    ".patch", ".diff", "curl", "wget", " gh ", "gh pr", "gh api",
    "git fetch", "git pull", "git ls-remote", "git remote",
    "log origin", "diff origin", "rev-parse origin", "show origin",
    # git-escape attempts: explicitly re-pointing git past the GIT_CEILING
    # fence to reach the enclosing harness repo (branch name + commit messages).
    "git -c ", "git --git-dir", "--git-dir=", "--work-tree",
    "env -u git", "git_ceiling", "git_dir=", "git_work_tree",
    "cache/repos", "urllib", "requests.get", "http.client",
    "socket.", "urlopen", "httpx", "fetch(",
)
# Regexes that strip BENIGN ``.git`` references (path-exclusion filters) from a
# command before we test for a genuine ``.git`` *read*. Without this, every
# ``find . -not -path '*/.git/*'`` directory listing trips a false leak.
_GIT_EXCLUSION_RE = re.compile(
    r"""(?:!\s*)?-?-?(?:not\s+)?              # optional ! / - / --not
        (?:-path|-ipath|exclude(?:-dir)?)\s*  # find -path / grep --exclude-dir
        =?\s*['"]?[^'"\s]*\.git[^'"\s]*['"]?  # a token containing .git
     """,
    re.VERBOSE,
)
# Verbs/redirections that indicate an actual READ of git internals (the oracle).
# Deliberately excludes grep/rg/sed/awk: those are directory searchers that take
# benign ``.git`` exclusion globs (e.g. ``rg --glob '!**/.git/**'``); a genuine
# git-internal read through them is still caught by the specific-file alternative
# below (``.git/HEAD`` etc.).
_GIT_READ_RE = re.compile(
    r"(?:cat|less|more|head|tail|strings|xxd|od|"
    r"open\(|cp|rsync)\b[^|;&]*\.git/"
    r"|<\s*[^|;&]*\.git/"          # input redirection from a .git file
    r"|\.git/(?:HEAD|refs|logs|objects|COMMIT_EDITMSG|ORIG_HEAD|packed-refs)"
)
# Path substrings whose READ would leak the answer or the harness's own state.
_LEAK_PATH_PATTERNS = (
    "cache/repos", "/.git/", "results.jsonl", "gold", "mapping",
    "trace.jsonl", "trace.md",
)


def _scan_leak_arguments(name: str, args: dict[str, Any]) -> list[str]:
    """Return leak signals for a single tool-execution-start event."""
    signals: list[str] = []
    lname = (name or "").lower()
    if lname in ("web_fetch", "fetch") or lname.endswith("-fetch"):
        url = str(args.get("url") or args.get("uri") or "")
        signals.append(f"{name}:url={url[:120]}")
        return signals
    # Shell / bash: inspect the command string.
    cmd = args.get("command") or args.get("cmd") or args.get("script")
    if isinstance(cmd, str) and cmd:
        low = cmd.lower()
        for pat in _LEAK_CMD_PATTERNS:
            if pat in low:
                signals.append(f"bash:{pat.strip()}")
        # ".git" needs context: ignore benign path-exclusion filters
        # (find -not -path '*/.git/*', grep --exclude-dir=.git) and only flag a
        # genuine READ of git internals (the offline gold oracle).
        if ".git" in low:
            stripped = _GIT_EXCLUSION_RE.sub(" ", low)
            if _GIT_READ_RE.search(stripped):
                signals.append("bash:.git-read")
    # File-reader tools: inspect the path. Skip benign .github/.gitignore.
    path = args.get("path") or args.get("file") or args.get("filename")
    if isinstance(path, str) and path:
        low = path.lower()
        for pat in _LEAK_PATH_PATTERNS:
            if pat in low:
                signals.append(f"path:{pat.strip()}")
    return signals


def detect_network_leak(stdout: str) -> dict[str, Any]:
    """Scan the event stream for attempts to reach the gold answer off-task.

    Inspects every ``tool.execution_start`` event (both ``data.*`` and flat
    top-level shapes; ``arguments`` is a dict). Flags web_fetch, GitHub/PR/
    commit/patch URLs, network shell commands, git-remote / origin reads, and
    reads of the cloned ``.git`` oracle, the shared repos cache, or the
    harness's own results/gold/trace files. Returns a bool + de-duplicated
    signal list recorded on the row so tripped runs can be quarantined.
    """
    signals: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not str(ev.get("type", "")).startswith("tool.execution_start"):
            continue
        data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
        name = data.get("name") or data.get("toolName") or ev.get("toolName") or ""
        args = data.get("arguments")
        if not isinstance(args, dict):
            top = ev.get("arguments")
            args = top if isinstance(top, dict) else {}
        signals.extend(_scan_leak_arguments(name, args))
    deduped = sorted(set(signals))
    return {"network_leak": bool(deduped), "leak_signals": deduped}


def hardening_meta(repo_path: Path, stdout: str, reasoning_tokens: int) -> dict[str, Any]:
    """Per-row leak-hardening + thinking provenance, recorded on every run.

    Marks which harness generation produced the row (so generations are never
    pooled), whether the network/opaque-path/.git defenses were active, the
    reasoning effort + separately-accounted thinking tokens, and any leak
    signals the detector tripped (so contaminated runs can be quarantined).
    """
    hardened = swe_bench.network_block_enabled()
    leak = detect_network_leak(stdout)
    return {
        "harness_hardening_version": HARNESS_HARDENING_VERSION,
        "network_block_mode": hardened,
        "opaque_path_mode": hardened,
        "git_sanitized": hardened and not (repo_path / ".git").exists(),
        "git_walk_up_blocked": hardened,
        "reasoning_effort": _resolve_reasoning_effort(),
        "reasoning_tokens": int(reasoning_tokens or 0),
        "network_leak": leak["network_leak"],
        "leak_signals": leak["leak_signals"],
    }


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
    env = dict(os.environ)
    hardened = swe_bench.network_block_enabled()
    if hardened:
        # Remove the opaque-name salt and any GitHub credentials so the agent
        # process cannot recover them.
        env = _harden_env(env)
        # Fence the agent's git: with the worktree's own .git stripped, a bare
        # `git log`/`git status` would otherwise walk UP to the enclosing harness
        # repo and leak its branch name + commit messages (which reveal the
        # benchmark intent). GIT_CEILING_DIRECTORIES stops the upward search at
        # the worktree's parent. Listed dirs are NOT crossed, so git sees no
        # repository from inside the (history-free) worktree. Both the resolved
        # and lexical parent are listed to defeat symlinked paths.
        env["GIT_CEILING_DIRECTORIES"] = _git_ceiling_dirs(cwd)
    t0 = time.time()
    timed_out = False
    stdout, stderr, returncode = "", "", None
    # Transient startup failures (OAuth token validation hitting a network blip,
    # connection resets) make Copilot exit in ~1s with empty stdout. Those rows
    # would otherwise be scored as recall=0 false negatives, so retry them.
    for attempt in range(1, COPILOT_MAX_ATTEMPTS + 1):
        session_id = str(uuid.uuid4())
        cmd = [
            "copilot", "-p", prompt,
            "--model", model,
            "--output-format", "json",
            "--no-remote",
            "--disable-builtin-mcps",
            "--allow-all-tools",
        ]
        # Under hardening, confine the `view` file tool to the worktree (via
        # --add-dir alone) instead of --allow-all-paths, so it cannot read the
        # sibling cloned-repo `.git` oracle or the harness's own results/gold
        # files. Shell reads are backstopped by deny-globs + the leak detector.
        if not hardened:
            cmd.append("--allow-all-paths")
        cmd += [
            "--add-dir", str(cwd),
            "--log-level", "debug",
            "--log-dir", str(log_dir),
            "--session-id", session_id,
        ]
        # Thinking is ENABLED for scored runs so the agent's tool-choice
        # deliberation is captured in the trace. The reasoning-token cost is
        # accounted separately (parse_tokens_from_logs -> reasoning_tokens) so
        # the base token comparison across arms stays interpretable. Set
        # COPILOT_REASONING_EFFORT=off to disable.
        _effort = _resolve_reasoning_effort()
        if _effort:
            cmd += ["--effort", _effort]
        # Network/remote exfiltration block (defense-in-depth; detector backstops).
        if hardened:
            cmd += _network_deny_flags()
        if mcp_config is not None:
            cmd += ["--additional-mcp-config", f"@{mcp_config}"]

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
        returncode = proc.returncode

        if timed_out or not _is_transient_startup_failure(returncode, stdout, stderr):
            break
        if attempt < COPILOT_MAX_ATTEMPTS:
            print(
                f"[retry] copilot startup failure (rc={returncode}, attempt "
                f"{attempt}/{COPILOT_MAX_ATTEMPTS}); backing off "
                f"{COPILOT_RETRY_BACKOFF_SEC}s. stderr={stderr.strip()[:160]!r}"
            )
            time.sleep(COPILOT_RETRY_BACKOFF_SEC)

    wall = time.time() - t0
    (log_dir / "stdout.jsonl").write_text(stdout or "")
    (log_dir / "stderr.txt").write_text(stderr or "")
    startup_failed = _is_transient_startup_failure(returncode, stdout, stderr) and not timed_out
    return {
        "stdout": stdout or "",
        "stderr": stderr or "",
        "returncode": returncode,
        "timed_out": timed_out,
        "startup_failed": startup_failed,
        "wall": wall,
    }


def _kill_group(pid: int) -> None:
    """Best-effort terminate a process and its group.

    On macOS ``os.killpg`` can raise ``PermissionError`` (EPERM) when a child
    has changed session/owner or is mid-reap. That must never turn a recoverable
    timeout into a fatal exception, so all signalling errors are swallowed and we
    fall back to signalling the direct pid.
    """
    try:
        pgid = os.getpgid(pid)
    except (ProcessLookupError, PermissionError, OSError):
        pgid = None
    for sig in (signal.SIGTERM, signal.SIGKILL):
        signalled = False
        if pgid is not None:
            try:
                os.killpg(pgid, sig)
                signalled = True
            except ProcessLookupError:
                return
            except (PermissionError, OSError):
                pgid = None
        if not signalled:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                return
            except (PermissionError, OSError):
                pass
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
        "reasoning_tokens": 0,
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
            # Thinking tokens are a subset of completion_tokens; surfaced
            # separately so the base (non-reasoning) output is comparable across
            # arms even with thinking enabled.
            cdetails = block.get("completion_tokens_details") or {}
            totals["reasoning_tokens"] += int(cdetails.get("reasoning_tokens", 0) or 0)
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


# A code-graph MCP tool call shows up with this prefix in the tool name
# (e.g. ``code-graph-search_code``). Used for nudge-compliance metrics.
_GRAPH_TOOL_PREFIX = "code-graph"


def parse_tool_sequence(stdout: str) -> list[str]:
    """Return tool names in invocation order (for first-tool / compliance)."""
    seq: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not ev.get("type", "").startswith("tool.execution_start"):
            continue
        data = ev.get("data", {})
        name = data.get("name") or data.get("toolName") or "unknown"
        seq.append(name or "unknown")
    return seq


def _tool_prefix_for_track(track: str) -> str:
    """The MCP server name prefix that identifies the track's nav tool calls."""
    if track == LSP:
        return "lsp"
    return _GRAPH_TOOL_PREFIX


def _is_graph_tool(name: str, prefix: str = _GRAPH_TOOL_PREFIX) -> bool:
    return bool(name) and name.startswith(prefix)


def nudge_compliance(stdout: str, track: str = CODE_GRAPH) -> dict[str, Any]:
    """Measure whether/how the agent engaged the track's MCP nav tools."""
    prefix = _tool_prefix_for_track(track)
    seq = parse_tool_sequence(stdout)
    first = seq[0] if seq else None
    graph_calls = sum(1 for n in seq if _is_graph_tool(n, prefix))
    return {
        "first_tool": first,
        "first_is_graph": bool(first and _is_graph_tool(first, prefix)),
        "graph_calls": graph_calls,
    }


# ---------------------------------------------------------------------------
# Localization (LocAgent-style): extract the agent's predicted files
# ---------------------------------------------------------------------------


def extract_agent_text(stdout: str) -> str:
    """Concatenate the agent's own message text (not tool output) in order.

    Scans both ``assistant.message`` (finalized) and ``assistant.message_delta``
    (streaming) so the sentinel is recoverable across CLI versions. Finalized
    messages stream after their deltas, so the last sentinel occurrence (which
    the parser keys on) lands in a complete message.
    """
    parts: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") in ("assistant.message", "assistant.message_delta"):
            content = ev.get("data", {}).get("content")
            if isinstance(content, str) and content.strip():
                parts.append(content)
    return "\n".join(parts)


def _norm_path(path: str) -> str:
    """Normalize a predicted path to a repo-root-relative posix form."""
    p = path.strip().strip("'\"").strip()
    p = p.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    for prefix in ("a/", "b/"):
        if p.startswith(prefix):
            p = p[len(prefix):]
    return p.lstrip("/")


def parse_localization(text: str) -> tuple[list[str], str | None, bool]:
    """Parse the predicted file list from the agent's final message.

    Returns ``(pred_files, parse_error, fallback)``. The strict path looks for
    the ``FINAL_LOCALIZATION_JSON:`` sentinel followed by a JSON array. If the
    sentinel is missing/malformed, ``fallback`` is True and ``parse_error``
    carries the reason (headline numbers should drop / stratify these).
    """
    idx = text.rfind(LOCALIZE_SENTINEL)
    if idx == -1:
        return [], "sentinel_missing", True
    tail = text[idx + len(LOCALIZE_SENTINEL):]
    start = tail.find("[")
    if start == -1:
        return [], "no_array", True
    depth = 0
    end = -1
    for i in range(start, len(tail)):
        c = tail[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        return [], "unbalanced_array", True
    blob = tail[start:end + 1]
    try:
        arr = json.loads(blob)
    except json.JSONDecodeError as exc:
        return [], f"json_error:{exc.msg}", True
    if not isinstance(arr, list):
        return [], "not_a_list", True
    pred: list[str] = []
    for item in arr:
        if not isinstance(item, str):
            continue
        norm = _norm_path(item)
        if norm and norm not in pred:
            pred.append(norm)
    return pred, None, False


def score_localization(pred: list[str], gold: list[str]) -> dict[str, Any]:
    """Score predicted files vs gold (order-sensitive for acc@k / MRR)."""
    gold_set = {_norm_path(g) for g in gold}
    pred_norm = [_norm_path(p) for p in pred]
    pred_set = set(pred_norm)
    hits = gold_set & pred_set
    recall = len(hits) / len(gold_set) if gold_set else 0.0
    precision = len(hits) / len(pred_set) if pred_set else 0.0
    all_found = bool(gold_set) and gold_set.issubset(pred_set)

    def acc_at(k: int) -> float:
        topk = set(pred_norm[:k])
        return 1.0 if gold_set and (gold_set & topk) else 0.0

    mrr = 0.0
    for rank, path in enumerate(pred_norm, start=1):
        if path in gold_set:
            mrr = 1.0 / rank
            break
    return {
        "gold_files": sorted(gold_set),
        "pred_files": pred_norm,
        "file_recall": round(recall, 4),
        "file_precision": round(precision, 4),
        "file_all_found": all_found,
        "acc_at_1": acc_at(1),
        "acc_at_3": acc_at(3),
        "acc_at_5": acc_at(5),
        "file_mrr": round(mrr, 4),
    }


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


def _resolve_run_dir(
    cache_dir: Path,
    *,
    model: str,
    mode: str,
    prompt_mode: str,
    track: str,
    instance_id: str,
    run_idx: int,
) -> Path:
    """Build the run_dir for one trajectory.

    For multi-run pilots (run_idx>0) each repeat is nested under ``run<idx>`` so
    logs are not overwritten; run_idx==0 keeps the bare layout for
    backwards-compat with existing single-run caches. ``row_stdout_path()``
    resolves both layouts.
    """
    run_dir = cache_dir / "runs" / model / mode / prompt_mode / track / instance_id
    if run_idx > 0:
        run_dir = run_dir / f"run{run_idx}"
    return run_dir


def _compute_prompt_mode(
    *, adopt_arm: str | None, nudge: bool, inject_label: str | None = None
) -> str:
    """Single source of truth for prompt_mode so main() and run_one() agree.

    The NOISY/GRAPH-WRONG distractor condition is orthogonal to the prompt arm,
    so it is encoded as a suffix (e.g. ``adopt-sem-noisy``). CLEAN runs carry no
    suffix and stay byte-identical to the plain arm prompt_mode.
    """
    if adopt_arm is not None:
        base = f"adopt-{adopt_arm}"
    else:
        base = "nudged" if nudge else "neutral"
    if inject_label:
        return f"{base}-{inject_label}"
    return base


def _inject_env(
    inst: swe_bench.SweBenchInstance,
    *,
    inject_manifest: Path | None,
    inject_k: int | None,
) -> dict[str, str] | None:
    """Build the env that gates server-side NOISY distractor injection.

    The keyed-by-task manifest is read inside the MCP server; here we just point
    it at the manifest path and pin BENCH_NOISY_TASK to this instance so only
    this task's distractors are injected. Returns None when injection is off.
    """
    if inject_manifest is None:
        return None
    env = {
        "BENCH_NOISY_MANIFEST": str(inject_manifest),
        "BENCH_NOISY_TASK": inst.instance_id,
    }
    if inject_k is not None:
        env["BENCH_NOISY_K"] = str(inject_k)
    return env


def run_one(
    inst: swe_bench.SweBenchInstance,
    *,
    track: str,
    model: str,
    cache_dir: Path,
    wall_time: float,
    server_root: Path,
    run_idx: int = 0,
    nudge: bool = False,
    mode: str = FIX,
    adopt_arm: str | None = None,
    inject_manifest: Path | None = None,
    inject_label: str | None = None,
    inject_k: int | None = None,
) -> dict[str, Any]:
    if adopt_arm is not None and (track != CODE_GRAPH or mode != LOCALIZE):
        raise ValueError(
            f"adopt_arm={adopt_arm!r} requires track={CODE_GRAPH} and mode={LOCALIZE}; "
            f"got track={track!r} mode={mode!r}"
        )
    if adopt_arm is not None and adopt_arm not in ADOPT_ARMS:
        raise ValueError(f"unknown adopt_arm={adopt_arm!r}; expected one of {ADOPT_ARMS}")
    if inject_manifest is not None:
        if track != CODE_GRAPH or mode != LOCALIZE:
            raise ValueError(
                f"inject_manifest requires track={CODE_GRAPH} and mode={LOCALIZE}; "
                f"got track={track!r} mode={mode!r}"
            )
        if not inject_label:
            raise ValueError("inject_manifest requires a non-empty inject_label")
    prompt_mode = _compute_prompt_mode(
        adopt_arm=adopt_arm, nudge=nudge, inject_label=inject_label
    )
    work_root = cache_dir / "worktrees" / track
    work_root.mkdir(parents=True, exist_ok=True)
    run_dir = _resolve_run_dir(
        cache_dir,
        model=model,
        mode=mode,
        prompt_mode=prompt_mode,
        track=track,
        instance_id=inst.instance_id,
        run_idx=run_idx,
    )
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== {inst.instance_id} [{track}] model={model} mode={mode} prompt={prompt_mode} ===")

    # Common base row fields (identity).
    base_row = {
        "benchmark": "swe_bench_verified",
        "task_id": inst.instance_id,
        "config": track,
        "model": model,
        "mode": mode,
        "prompt_mode": prompt_mode,
        "run_idx": run_idx,
        "runner": RUNNER_VERSION,
    }

    if mode == LOCALIZE:
        return _run_localize(
            inst, track=track, model=model, run_dir=run_dir, work_root=work_root,
            wall_time=wall_time, server_root=server_root, nudge=nudge, base_row=base_row,
            adopt_arm=adopt_arm, inject_manifest=inject_manifest, inject_k=inject_k,
        )

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
    elif track == LSP:
        wrapper = _write_lsp_wrapper(run_dir, repo_path)
        mcp_config = _write_lsp_mcp_config(run_dir, wrapper)

    prompt = build_prompt(
        track, repo_path, inst.problem_statement, repo_path.name, nudge=nudge, mode=mode
    )
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
    compliance = nudge_compliance(result["stdout"], track)
    patch_info = extract_patch(repo_path, inst.base_commit)

    if result.get("startup_failed"):
        print(
            f"[error] {inst.instance_id} [{track}] copilot startup failed after "
            f"{COPILOT_MAX_ATTEMPTS} attempts (rc={result['returncode']}); "
            f"marking incomplete for re-run"
        )
        return {
            **base_row,
            "index_sec": index_sec,
            "timed_out": result["timed_out"],
            "returncode": result["returncode"],
            "outcome": "error",
            "error": f"copilot_startup_failed: {result.get('stderr', '').strip()[:200]}",
            "wall_clock_sec": round(result["wall"], 2),
            "completed": False,
        }

    row = {
        **base_row,
        "input_tokens": tokens["input_tokens"],
        "output_tokens": tokens["output_tokens"],
        "total_tokens": tokens["total_tokens"],
        "cached_input_tokens": tokens["cached_input_tokens"],
        "cache_creation_tokens": tokens["cache_creation_tokens"],
        "usage_blocks": tokens["usage_blocks"],
        "premium_requests": result_ev["premium_requests"],
        "tool_calls_total": tool_total,
        "tool_calls_by_name": tool_by_name,
        "first_tool": compliance["first_tool"],
        "first_is_graph": compliance["first_is_graph"],
        "graph_calls": compliance["graph_calls"],
        "files_modified": result_ev["files_modified"],
        "touched_tests": patch_info["touched_tests"],
        "index_sec": index_sec,
        "timed_out": result["timed_out"],
        "returncode": result["returncode"],
        "outcome": "ungraded",
        "patch": patch_info["patch"],
        "wall_clock_sec": round(result["wall"], 2),
        "completed": True,
        **hardening_meta(repo_path, result["stdout"], tokens["reasoning_tokens"]),
    }
    _maybe_write_trace(run_dir, row)
    print(
        f"[done] {inst.instance_id} [{track}] in={row['input_tokens']} "
        f"out={row['output_tokens']} premium={row['premium_requests']} "
        f"tools={tool_total} graph={compliance['graph_calls']} "
        f"patch_files={len(patch_info['patched_files'])} "
        f"timed_out={result['timed_out']} wall={row['wall_clock_sec']}s"
    )
    return row


def _run_localize(
    inst: swe_bench.SweBenchInstance,
    *,
    track: str,
    model: str,
    run_dir: Path,
    work_root: Path,
    wall_time: float,
    server_root: Path,
    nudge: bool,
    base_row: dict[str, Any],
    adopt_arm: str | None = None,
    inject_manifest: Path | None = None,
    inject_k: int | None = None,
) -> dict[str, Any]:
    """Localization driver: no edits, no Docker; score predicted files vs gold."""
    gold = swe_bench.gold_changed_files(inst.patch, source_only=True)
    if not gold:
        print(f"[skip] {inst.instance_id} [{track}] no source-only gold files")
        return {
            **base_row,
            "outcome": "skipped_no_gold",
            "completed": True,
            "gold_files": [],
        }

    # Distinct, test-free worktree forces a clean re-index with no test_patch
    # leakage into the graph.
    repo_path = swe_bench.prepare_localize_worktree(
        inst, worktrees_dir=work_root.resolve()
    )

    index_sec = None
    mcp_config = None
    if track == CODE_GRAPH:
        index_sec = ensure_indexed(repo_path, fresh=True)
        host, port = _falkor_settings()
        wrapper = _write_mcp_wrapper(run_dir, server_root)
        extra_env = _inject_env(inst, inject_manifest=inject_manifest, inject_k=inject_k)
        mcp_config = _write_mcp_config(run_dir, wrapper, host, port, extra_env=extra_env)
    elif track == LSP:
        wrapper = _write_lsp_wrapper(run_dir, repo_path)
        mcp_config = _write_lsp_mcp_config(run_dir, wrapper)

    prompt = build_prompt(
        track, repo_path, inst.problem_statement, repo_path.name,
        nudge=nudge, mode=LOCALIZE, adopt_arm=adopt_arm,
    )
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
    compliance = nudge_compliance(result["stdout"], track)

    agent_text = extract_agent_text(result["stdout"])
    (run_dir / "agent_text.txt").write_text(agent_text)
    pred, parse_error, fallback = parse_localization(agent_text)
    scores = score_localization(pred, gold)
    leak = swe_bench.leakage_flags(inst, gold)

    # A transient startup/network failure produces no model output; record it as
    # an error (completed=False) so it is re-run rather than scored as recall=0.
    if result.get("startup_failed"):
        print(
            f"[error] {inst.instance_id} [{track}] copilot startup failed after "
            f"{COPILOT_MAX_ATTEMPTS} attempts (rc={result['returncode']}); "
            f"marking incomplete for re-run"
        )
        return {
            **base_row,
            "index_sec": index_sec,
            "index_fresh": track == CODE_GRAPH,
            "timed_out": result["timed_out"],
            "returncode": result["returncode"],
            "outcome": "error",
            "error": f"copilot_startup_failed: {result.get('stderr', '').strip()[:200]}",
            "wall_clock_sec": round(result["wall"], 2),
            "completed": False,
        }

    row = {
        **base_row,
        "input_tokens": tokens["input_tokens"],
        "output_tokens": tokens["output_tokens"],
        "total_tokens": tokens["total_tokens"],
        "cached_input_tokens": tokens["cached_input_tokens"],
        "cache_creation_tokens": tokens["cache_creation_tokens"],
        "usage_blocks": tokens["usage_blocks"],
        "premium_requests": result_ev["premium_requests"],
        "tool_calls_total": tool_total,
        "tool_calls_by_name": tool_by_name,
        "first_tool": compliance["first_tool"],
        "first_is_graph": compliance["first_is_graph"],
        "graph_calls": compliance["graph_calls"],
        "index_sec": index_sec,
        "index_fresh": track == CODE_GRAPH,
        "timed_out": result["timed_out"],
        "returncode": result["returncode"],
        "parse_error": parse_error,
        "parse_fallback": fallback,
        "is_structural": swe_bench.is_structural(inst),
        "mentions_gold_path": leak.get("mentions_gold_path"),
        "mentions_gold_basename": leak.get("mentions_gold_basename"),
        "contains_traceback": leak.get("contains_traceback"),
        "outcome": "localized",
        "wall_clock_sec": round(result["wall"], 2),
        "completed": True,
        **scores,
        **hardening_meta(repo_path, result["stdout"], tokens["reasoning_tokens"]),
    }
    _maybe_write_trace(run_dir, row)
    print(
        f"[loc] {inst.instance_id} [{track}] recall={scores['file_recall']} "
        f"acc@1={scores['acc_at_1']} mrr={scores['file_mrr']} "
        f"pred={len(pred)} gold={len(scores['gold_files'])} "
        f"graph={compliance['graph_calls']} parse_err={parse_error} "
        f"in={row['input_tokens']} wall={row['wall_clock_sec']}s"
    )
    return row


def _maybe_write_trace(run_dir: Path, row: dict[str, Any]) -> None:
    """Best-effort decision-loop trace extraction; never break a run on error."""
    try:
        from bench.analysis.trace import extract_run

        extract_run(run_dir, row=row, write=True)
    except Exception as exc:  # noqa: BLE001 - trace is diagnostic, not critical
        print(f"[trace] extraction failed for {run_dir.name}: {exc}")


# ---------------------------------------------------------------------------
# Resume / IO
# ---------------------------------------------------------------------------


def _load_done(results_path: Path) -> set[tuple]:
    done: set[tuple] = set()
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
            done.add((
                r["task_id"],
                r["config"],
                r.get("model", ""),
                r.get("mode", FIX),
                r.get("prompt_mode", "neutral"),
                int(r.get("run_idx", 0)),
            ))
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
    if args.select_structural:
        return []  # resolved later against the loaded dataset
    raise SystemExit(
        "provide --instance ID [ID ...], --instances-file FILE, or --select-structural N"
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Drive Copilot CLI over SWE-bench Verified.")
    p.add_argument("--instance", nargs="*", help="explicit instance id(s)")
    p.add_argument("--instances-file", help="file with one instance id per line")
    p.add_argument(
        "--select-structural", type=int, default=0,
        help="auto-select N structural instances (>=2 source files/dirs) for localization",
    )
    p.add_argument(
        "--track", action="append", choices=VALID_TRACKS, default=None,
        help="track(s) to run (default: both)",
    )
    p.add_argument("--model", default="claude-opus-4.8")
    p.add_argument("--mode", choices=VALID_MODES, default=FIX, help="fix or localize")
    p.add_argument(
        "--nudge", action="store_true",
        help="use the nudged prompt variant (forces structured search-first)",
    )
    p.add_argument(
        "--adopt-arm", choices=ADOPT_ARMS, default=None,
        help="Lane 1 adoption-calibration arm (code_graph + localize only): "
             "ctrl (=nudge base), sem (edge-semantics clause), rat (keep/drop step)",
    )
    p.add_argument(
        "--inject-manifest", default=None,
        help="path to a NOISY/GRAPH-WRONG distractor manifest (code_graph + localize only); "
             "enables server-side injection of verified non-gold candidates",
    )
    p.add_argument(
        "--inject-label", default=None,
        help="condition label suffixed onto prompt_mode when injecting (e.g. 'noisy', 'gwrong')",
    )
    p.add_argument(
        "--inject-k", type=int, default=None,
        help="override number of distractors to inject (default: manifest k)",
    )
    p.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    p.add_argument("--results", default=None, help="results jsonl (default: <cache>/<model>/results.jsonl)")
    p.add_argument("--wall-time", type=float, default=1200.0, help="per-run wall-clock seconds")
    p.add_argument("--server-root", default=str(DEFAULT_MCP_SERVER_ROOT))
    p.add_argument("--run-idx", type=int, default=0)
    p.add_argument("--seed", type=int, default=swe_bench.DEFAULT_SEED, help="seed for --select-structural")
    p.add_argument(
        "--dataset", default=None,
        help="HuggingFace dataset name (default: SWE-bench_Verified). "
             "Use 'loc-bench' shorthand or a full id like czlll/Loc-Bench_V1.",
    )
    p.add_argument(
        "--no-leak", action="store_true",
        help="with --select-structural: drop instances whose problem statement names a gold file (structural-hard gate)",
    )
    args = p.parse_args(argv)

    tracks = args.track or list(VALID_TRACKS)
    if args.adopt_arm is not None:
        # Lane 1 arms are code_graph + localize only; pin the track/mode so the
        # dedup key, run_dir and prompt all agree with run_one's guard.
        if args.mode != LOCALIZE:
            raise SystemExit(f"--adopt-arm requires --mode {LOCALIZE}")
        if tracks != [CODE_GRAPH]:
            raise SystemExit(f"--adopt-arm requires --track {CODE_GRAPH} (only)")
    cache_dir = Path(args.cache_dir).resolve()
    inject_manifest: Path | None = None
    if args.inject_manifest is not None:
        if args.mode != LOCALIZE:
            raise SystemExit(f"--inject-manifest requires --mode {LOCALIZE}")
        if tracks != [CODE_GRAPH]:
            raise SystemExit(f"--inject-manifest requires --track {CODE_GRAPH} (only)")
        if not args.inject_label:
            raise SystemExit("--inject-manifest requires --inject-label")
        inject_manifest = Path(args.inject_manifest).resolve()
        if not inject_manifest.is_file():
            raise SystemExit(f"--inject-manifest not found: {inject_manifest}")
    results_path = (
        Path(args.results)
        if args.results
        else cache_dir / args.model / "results.jsonl"
    )
    server_root = Path(args.server_root)
    # Only suffix prompt_mode when injection is actually active.
    effective_inject_label = args.inject_label if inject_manifest is not None else None
    prompt_mode = _compute_prompt_mode(
        adopt_arm=args.adopt_arm, nudge=args.nudge, inject_label=effective_inject_label,
    )

    ids = _load_instance_ids(args)
    dataset_name = args.dataset
    if dataset_name and dataset_name.lower() in ("loc-bench", "locbench"):
        dataset_name = swe_bench.LOC_BENCH_DATASET
    all_insts = {i.instance_id: i for i in swe_bench.load_instances(dataset_name=dataset_name)}
    if ids:
        missing = [i for i in ids if i not in all_insts]
        if missing:
            raise SystemExit(f"unknown instance ids: {missing}")
        insts = [all_insts[i] for i in ids]
    else:
        insts = swe_bench.select_structural(
            list(all_insts.values()), seed=args.seed, n=args.select_structural,
            python_only=True, no_leak=args.no_leak,
        )
        print(f"[plan] selected {len(insts)} structural instances: "
              f"{[i.instance_id for i in insts]}")

    done = _load_done(results_path)
    print(f"[plan] {len(insts)} instances x {len(tracks)} tracks; mode={args.mode} "
          f"prompt={prompt_mode}; {len(done)} rows already complete; results -> {results_path}")

    for inst in insts:
        for track in tracks:
            key = (inst.instance_id, track, args.model, args.mode, prompt_mode, args.run_idx)
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
                    nudge=args.nudge,
                    mode=args.mode,
                    adopt_arm=args.adopt_arm,
                    inject_manifest=inject_manifest,
                    inject_label=effective_inject_label,
                    inject_k=args.inject_k,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[error] {inst.instance_id} [{track}]: {exc!r}", file=sys.stderr)
                traceback.print_exc()
                row = {
                    "benchmark": "swe_bench_verified",
                    "task_id": inst.instance_id,
                    "config": track,
                    "model": args.model,
                    "mode": args.mode,
                    "prompt_mode": prompt_mode,
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
