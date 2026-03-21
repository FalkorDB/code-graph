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

    host = os.getenv("FALKORDB_HOST", "localhost")
    try:
        port = int(os.getenv("FALKORDB_PORT", "6379"))
    except ValueError:
        _json_error(f"Invalid FALKORDB_PORT: {os.getenv('FALKORDB_PORT')!r} — must be an integer")

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
        project = Project(name, folder, url)
        graph = project.analyze_sources(ignore=list(ignore) if ignore else [])
        stats = graph.stats()
    except Exception as e:
        _json_error(str(e))

    _stderr(f"Done — {stats['node_count']} nodes, {stats['edge_count']} edges")
    _json_out({"status": "ok", "repo": name, **stats})


# ── index-repo ─────────────────────────────────────────────────────────


@app.command("index-repo")
def index_repo(
    url: str = typer.Argument(..., help="Git repository URL to clone and index"),
    ignore: Optional[List[str]] = typer.Option(
        None, "--ignore", help="Directories to ignore (repeatable)"
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
            project = Project.from_git_repository(url)
        graph = project.analyze_sources(ignore=list(ignore) if ignore else [])
        stats = graph.stats()
    except Exception as e:
        _json_error(str(e))

    _stderr(f"Done — {stats['node_count']} nodes, {stats['edge_count']} edges")
    _json_out({"status": "ok", "repo": project.name, **stats})


# ── list ───────────────────────────────────────────────────────────────


@app.command("list")
def list_repos() -> None:
    """List all indexed repositories."""
    from .graph import get_repos

    try:
        repos = get_repos()
    except Exception as e:
        _json_error(str(e))

    _json_out({"repos": repos})


# ── search ─────────────────────────────────────────────────────────────


@app.command()
def search(
    query: str = typer.Argument(..., help="Prefix to search for"),
    repo: Optional[str] = typer.Option(
        None, "--repo", help="Repository name (defaults to CWD name)"
    ),
) -> None:
    """Search for entities by prefix (full-text search)."""
    from .graph import Graph

    name = _default_repo(repo)
    try:
        g = Graph(name)
        results = g.prefix_search(query)
    except Exception as e:
        _json_error(str(e))

    _json_out({"repo": name, "results": results})


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
) -> None:
    """Get neighboring entities of the given node(s)."""
    from .graph import Graph

    name = _default_repo(repo)
    try:
        g = Graph(name)
        result = g.get_neighbors(node_ids, rel=rel, lbl=label)
    except Exception as e:
        _json_error(str(e))

    _json_out({"repo": name, **result})


# ── paths ──────────────────────────────────────────────────────────────


@app.command()
def paths(
    src: int = typer.Argument(..., help="Source node ID"),
    dest: int = typer.Argument(..., help="Destination node ID"),
    repo: Optional[str] = typer.Option(
        None, "--repo", help="Repository name (defaults to CWD name)"
    ),
) -> None:
    """Find call-chain paths between two nodes."""
    from .graph import Graph

    name = _default_repo(repo)
    try:
        g = Graph(name)
        result = g.find_paths(src, dest)
    except Exception as e:
        _json_error(str(e))

    _json_out({"repo": name, "paths": result})


# ── info ───────────────────────────────────────────────────────────────


@app.command()
def info(
    repo: Optional[str] = typer.Option(
        None, "--repo", help="Repository name (defaults to CWD name)"
    ),
) -> None:
    """Show repository statistics and metadata."""
    from .graph import Graph
    from .info import get_repo_info

    name = _default_repo(repo)
    try:
        g = Graph(name)
        stats = g.stats()
        metadata = get_repo_info(name) or {}
    except Exception as e:
        _json_error(str(e))

    _json_out({"repo": name, **stats, "metadata": metadata})


if __name__ == "__main__":
    app()
