"""Code Graph CLI — index and query code knowledge graphs.

Machine-readable JSON goes to stdout; human status goes to stderr.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

import typer

app = typer.Typer(
    help="Index codebases and query their knowledge graphs.",
    no_args_is_help=True,
)

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _stderr(msg: str) -> None:
    print(msg, file=sys.stderr)


def _json_out(data: object) -> None:
    print(json.dumps(data, default=str))


def _json_error(message: str, code: int = 1) -> None:
    """Emit a JSON error to stdout and exit."""
    _json_out({"status": "error", "message": message})
    raise typer.Exit(code=code)


def _default_repo(repo: Optional[str]) -> str:
    return repo if repo else Path.cwd().name


def _check_connection(host: str, port: int) -> bool:
    """Check if FalkorDB/Redis is reachable via PING."""
    import redis

    r: Optional[redis.Redis] = None
    try:
        r = redis.Redis(host=host, port=port, socket_connect_timeout=2)
        r.ping()
        return True
    except Exception:
        return False
    finally:
        if r is not None:
            r.close()


# ── ensure-db ──────────────────────────────────────────────────────────


@app.command("ensure-db")
def ensure_db() -> None:
    """Ensure FalkorDB is running, auto-starting a Docker container if needed."""

    from .db import create_falkordb, is_lite_backend

    if is_lite_backend():
        try:
            db = create_falkordb()
            db.connection.ping()
        except Exception as e:
            _json_error(f"Failed to initialize FalkorDBLite: {e}")
        _stderr("FalkorDBLite embedded backend is ready")
        _json_out({"status": "ok", "backend": "lite"})
        return

    host = os.getenv("FALKORDB_HOST", "localhost")
    try:
        port = int(os.getenv("FALKORDB_PORT", "6379"))
    except ValueError:
        _json_error(f"Invalid FALKORDB_PORT: {os.getenv('FALKORDB_PORT')!r} — must be an integer")
    if not 1 <= port <= 65535:
        _json_error(f"FALKORDB_PORT must be between 1 and 65535, got {port}")

    if _check_connection(host, port):
        _stderr(f"FalkorDB already running on {host}:{port}")
        _json_out({"status": "ok", "host": host, "port": port})
        return

    # Only auto-start Docker for local hosts
    if host not in _LOCAL_HOSTS:
        _json_error(
            f"FalkorDB not reachable on {host}:{port} "
            "and auto-start is only supported for localhost"
        )

    _stderr(
        f"FalkorDB not reachable on {host}:{port}, starting Docker container…"
    )

    try:
        # Reuse existing stopped container if present
        inspect = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Running}}",
                "falkordb-cgraph",
            ],
            capture_output=True,
            text=True,
        )

        if inspect.returncode == 0:
            # Check that the existing container maps to the expected port
            port_inspect = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{(index (index .NetworkSettings.Ports \"6379/tcp\") 0).HostPort}}",
                    "falkordb-cgraph",
                ],
                capture_output=True,
                text=True,
            )
            existing_port = port_inspect.stdout.strip() if port_inspect.returncode == 0 else None
            if existing_port and existing_port != str(port):
                _json_error(
                    f"Existing falkordb-cgraph container is bound to port {existing_port}, "
                    f"but FALKORDB_PORT is {port}. Remove the container and retry."
                )

            if inspect.stdout.strip() == "false":
                subprocess.run(
                    ["docker", "start", "falkordb-cgraph"],
                    check=True,
                    capture_output=True,
                )
                _stderr("Started existing falkordb-cgraph container")
        else:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    "falkordb-cgraph",
                    "-p",
                    f"{port}:6379",
                    "falkordb/falkordb:latest",
                ],
                check=True,
                capture_output=True,
            )
            _stderr("Created and started falkordb-cgraph container")
    except FileNotFoundError:
        _json_error("Docker is not installed or not on PATH")
    except subprocess.CalledProcessError as e:
        _json_error(f"Docker command failed: {e.stderr.strip() if e.stderr else e}")

    # Wait up to 30 s for connectivity
    for _ in range(30):
        if _check_connection(host, port):
            _stderr("FalkorDB is ready")
            _json_out({"status": "ok", "host": host, "port": port})
            return
        time.sleep(1)

    _stderr("Timed out waiting for FalkorDB to become ready")
    _json_error("timeout")


# ── index ──────────────────────────────────────────────────────────────


@app.command()
def index(
    path: str = typer.Argument(".", help="Local folder to index"),
    ignore: Optional[List[str]] = typer.Option(
        None, "--ignore", help="Directories to ignore (repeatable)"
    ),
    repo: Optional[str] = typer.Option(
        None, "--repo", help="Graph name (defaults to folder name)"
    ),
    branch: Optional[str] = typer.Option(
        None, "--branch", help="Branch to associate with this index (auto-detected from git checkout when omitted; '_default' for non-git paths)"
    ),
) -> None:
    """Index a local folder into the knowledge graph."""
    from .project import Project

    folder = Path(path).resolve()
    if not folder.exists():
        _json_error(f"path does not exist: {folder}")
    if not folder.is_dir():
        _json_error(f"path is not a directory: {folder}")

    name = repo or folder.name

    # Try to detect git remote URL for metadata (non-critical)
    url = None
    try:
        from pygit2.repository import Repository as GitRepo
        import re as _re

        remote_url = GitRepo(str(folder)).remotes[0].url
        # Convert SSH-style URLs (git@host:org/repo.git) to HTTPS
        ssh_match = _re.match(r'^git@([^:]+):(.+?)(?:\.git)?$', remote_url)
        if ssh_match:
            url = f"https://{ssh_match.group(1)}/{ssh_match.group(2)}"
        else:
            # Already HTTPS — just strip trailing .git
            url = _re.sub(r'\.git$', '', remote_url)
    except Exception:
        # Not a git repo or no remote configured — metadata will be skipped
        pass

    _stderr(f"Indexing {folder} as '{name}'…")
    try:
        project = Project(name, folder, url, branch=branch)
        graph = project.analyze_sources(ignore=list(ignore) if ignore else [])
        stats = graph.stats()
    except Exception as e:
        _json_error(str(e))

    _stderr(f"Done — {stats['node_count']} nodes, {stats['edge_count']} edges (branch={project.branch})")
    _json_out({"status": "ok", "repo": name, "branch": project.branch, **stats})


# ── index-repo ─────────────────────────────────────────────────────────


@app.command("index-repo")
def index_repo(
    url: str = typer.Argument(..., help="Git repository URL to clone and index"),
    ignore: Optional[List[str]] = typer.Option(
        None, "--ignore", help="Directories to ignore (repeatable)"
    ),
    branch: Optional[str] = typer.Option(
        None, "--branch", help="Branch to associate with this index (auto-detected from the cloned checkout when omitted)"
    ),
) -> None:
    """Clone a git repository and index it into the knowledge graph."""
    from .project import Project

    _stderr(f"Cloning and indexing {url}…")
    try:
        # Redirect stdout to suppress clone output (keep JSON-only stdout)
        import io
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            project = Project.from_git_repository(url, branch=branch)
        graph = project.analyze_sources(ignore=list(ignore) if ignore else [])
        stats = graph.stats()
    except Exception as e:
        _json_error(str(e))

    _stderr(f"Done — {stats['node_count']} nodes, {stats['edge_count']} edges (branch={project.branch})")
    _json_out({"status": "ok", "repo": project.name, "branch": project.branch, **stats})


# ── list ───────────────────────────────────────────────────────────────


@app.command("list")
def list_repos() -> None:
    """List all indexed (project, branch) pairs."""
    from .graph import get_repos

    try:
        repos = get_repos()
    except Exception as e:
        _json_error(str(e))

    _json_out({"repos": repos})


# ── migrate ────────────────────────────────────────────────────────────


@app.command("migrate")
def migrate(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without performing them"),
) -> None:
    """Promote legacy (pre-T17) graphs and Redis keys into the per-branch namespace.

    Renames each legacy ``<project>`` graph to ``code:<project>:_default``,
    each ``{project}_info`` Redis key to ``{project}:_default_info``, and
    each ``{project}_git`` graph to ``{project}:_default_git``. Idempotent.
    """

    from .migrations.per_branch import run_migration

    try:
        result = run_migration(dry_run=dry_run)
    except Exception as e:
        _json_error(str(e))

    _json_out(result)


# ── search ─────────────────────────────────────────────────────────────


@app.command()
def search(
    query: str = typer.Argument(..., help="Prefix to search for"),
    repo: Optional[str] = typer.Option(
        None, "--repo", help="Repository name (defaults to CWD name)"
    ),
    branch: Optional[str] = typer.Option(
        None, "--branch", help="Branch (auto-detected from CWD; '_default' for non-git paths)"
    ),
) -> None:
    """Search for entities by prefix (full-text search)."""
    from .graph import Graph
    from .project import detect_branch

    name = _default_repo(repo)
    if branch is None:
        branch = detect_branch(Path.cwd())
    try:
        g = Graph(name, branch=branch)
        results = g.prefix_search(query)
    except Exception as e:
        _json_error(str(e))

    _json_out({"repo": name, "branch": branch, "results": results})


# ── neighbors ──────────────────────────────────────────────────────────


@app.command()
def neighbors(
    node_ids: List[int] = typer.Argument(..., help="Node IDs to query"),
    repo: Optional[str] = typer.Option(
        None, "--repo", help="Repository name (defaults to CWD name)"
    ),
    rel: Optional[str] = typer.Option(
        None, "--rel", help="Filter by relationship type (e.g. CALLS, DEFINES)"
    ),
    label: Optional[str] = typer.Option(
        None, "--label", help="Filter by destination label (e.g. Function, Class)"
    ),
    branch: Optional[str] = typer.Option(
        None, "--branch", help="Branch (auto-detected from CWD; '_default' for non-git paths)"
    ),
) -> None:
    """Get neighboring entities of the given node(s)."""
    from .graph import Graph
    from .project import detect_branch

    name = _default_repo(repo)
    if branch is None:
        branch = detect_branch(Path.cwd())
    try:
        g = Graph(name, branch=branch)
        result = g.get_neighbors(node_ids, rel=rel, lbl=label)
    except Exception as e:
        _json_error(str(e))

    _json_out({"repo": name, "branch": branch, **result})


# ── paths ──────────────────────────────────────────────────────────────


@app.command()
def paths(
    src: int = typer.Argument(..., help="Source node ID"),
    dest: int = typer.Argument(..., help="Destination node ID"),
    repo: Optional[str] = typer.Option(
        None, "--repo", help="Repository name (defaults to CWD name)"
    ),
    branch: Optional[str] = typer.Option(
        None, "--branch", help="Branch (auto-detected from CWD; '_default' for non-git paths)"
    ),
) -> None:
    """Find call-chain paths between two nodes."""
    from .graph import Graph
    from .project import detect_branch

    name = _default_repo(repo)
    if branch is None:
        branch = detect_branch(Path.cwd())
    try:
        g = Graph(name, branch=branch)
        result = g.find_paths(src, dest)
    except Exception as e:
        _json_error(str(e))

    _json_out({"repo": name, "branch": branch, "paths": result})


# ── info ───────────────────────────────────────────────────────────────


@app.command()
def info(
    repo: Optional[str] = typer.Option(
        None, "--repo", help="Repository name (defaults to CWD name)"
    ),
    branch: Optional[str] = typer.Option(
        None, "--branch", help="Branch (auto-detected from CWD; '_default' for non-git paths)"
    ),
) -> None:
    """Show repository statistics and metadata."""
    from .graph import Graph
    from .info import get_repo_info
    from .project import detect_branch

    name = _default_repo(repo)
    if branch is None:
        branch = detect_branch(Path.cwd())
    try:
        g = Graph(name, branch=branch)
        stats = g.stats()
        metadata = get_repo_info(name, branch) or {}
    except Exception as e:
        _json_error(str(e))

    _json_out({"repo": name, "branch": branch, **stats, "metadata": metadata})


# ── init-agent ─────────────────────────────────────────────────────────


_TEMPLATES_DIR = Path(__file__).parent / "mcp" / "templates"


@app.command("init-agent")
def init_agent(
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing CLAUDE.md / .cursorrules."
    ),
) -> None:
    """Drop AI-agent guidance files (CLAUDE.md, .cursorrules) into CWD.

    Copies the canonical code-graph MCP guidance bundled with this
    package so any repo can announce the tools to Cursor and Claude
    Code with one command.
    """
    targets = {
        "CLAUDE.md": _TEMPLATES_DIR / "claude_mcp_section.md",
        ".cursorrules": _TEMPLATES_DIR / "cursorrules.template",
    }

    cwd = Path.cwd()
    if not force:
        existing = [name for name in targets if (cwd / name).exists()]
        if existing:
            _json_error(
                f"Refusing to overwrite existing files: {', '.join(existing)}. "
                "Re-run with --force to clobber."
            )

    written: List[str] = []
    for name, template in targets.items():
        dest = cwd / name
        dest.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        written.append(str(dest))
        _stderr(f"Wrote {dest}")

    _json_out({"status": "ok", "written": written, "force": force})


if __name__ == "__main__":
    app()
