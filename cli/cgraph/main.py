"""Code Graph CLI — query code knowledge graphs stored in FalkorDB.

Machine-readable JSON goes to stdout; human status goes to stderr.

This is the lightweight CLI package (falkordb-cgraph). It only depends on
``falkordb`` and ``typer`` so ``pipx install falkordb-cgraph`` is fast.

For indexing commands (``index`` / ``index-repo``) install the full server
package instead::

    pip install falkordb-code-graph
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

import typer
from falkordb import FalkorDB, Node, Edge

app = typer.Typer(
    help="Query FalkorDB code-graph knowledge graphs.",
    no_args_is_help=True,
)

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _db() -> FalkorDB:
    return FalkorDB(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
        username=os.getenv("FALKORDB_USERNAME", None),
        password=os.getenv("FALKORDB_PASSWORD", None),
    )


def _check_connection(host: str, port: int) -> bool:
    """Check if FalkorDB/Redis is reachable via PING.

    ``redis`` is a direct dependency of ``falkordb`` and is always available.
    """
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


def _encode_node(n: Node) -> dict:
    if "Searchable" in n.labels:
        n.labels.remove("Searchable")
    return vars(n)


def _encode_edge(e: Edge) -> dict:
    return vars(e)


def _get_repos() -> list[str]:
    db = _db()
    graphs = db.list_graphs()
    return [g for g in graphs if not (g.endswith("_git") or g.endswith("_schema"))]


def _get_repo_info(repo_name: str) -> Optional[dict]:
    import redis as _redis

    r = _redis.Redis(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
        username=os.getenv("FALKORDB_USERNAME"),
        password=os.getenv("FALKORDB_PASSWORD"),
        decode_responses=True,
    )
    try:
        key = f"{{{repo_name}}}_info"
        info = r.hgetall(key)
        return info if info else None
    finally:
        r.close()


# ---------------------------------------------------------------------------
# ensure-db
# ---------------------------------------------------------------------------

@app.command("ensure-db")
def ensure_db() -> None:
    """Ensure FalkorDB is running, auto-starting a Docker container if needed."""

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

    if host not in _LOCAL_HOSTS:
        _json_error(
            f"FalkorDB not reachable on {host}:{port} "
            "and auto-start is only supported for localhost"
        )

    _stderr(f"FalkorDB not reachable on {host}:{port}, starting Docker container…")

    try:
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
            port_inspect = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{{(index (index .NetworkSettings.Ports "6379/tcp") 0).HostPort}}',
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

    for _ in range(30):
        if _check_connection(host, port):
            _stderr("FalkorDB is ready")
            _json_out({"status": "ok", "host": host, "port": port})
            return
        time.sleep(1)

    _stderr("Timed out waiting for FalkorDB to become ready")
    _json_error("timeout")


# ---------------------------------------------------------------------------
# index / index-repo  (stub — requires the full falkordb-code-graph package)
# ---------------------------------------------------------------------------

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
    """Index a local folder into the knowledge graph.

    Requires the full server package. Install it with:
    pip install falkordb-code-graph
    """
    _json_error(
        "The 'index' command requires the full falkordb-code-graph package. "
        "Install it with: pip install falkordb-code-graph"
    )


@app.command("index-repo")
def index_repo(
    url: str = typer.Argument(..., help="Git repository URL to clone and index"),
    ignore: Optional[List[str]] = typer.Option(
        None, "--ignore", help="Directories to ignore (repeatable)"
    ),
) -> None:
    """Clone a git repository and index it into the knowledge graph.

    Requires the full server package. Install it with:
    pip install falkordb-code-graph
    """
    _json_error(
        "The 'index-repo' command requires the full falkordb-code-graph package. "
        "Install it with: pip install falkordb-code-graph"
    )


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@app.command("list")
def list_repos() -> None:
    """List all indexed repositories."""
    try:
        repos = _get_repos()
    except Exception as e:
        _json_error(str(e))

    _json_out({"repos": repos})


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

@app.command()
def search(
    query: str = typer.Argument(..., help="Prefix to search for"),
    repo: Optional[str] = typer.Option(
        None, "--repo", help="Repository name (defaults to CWD name)"
    ),
) -> None:
    """Search for entities by prefix (full-text search)."""
    name = _default_repo(repo)
    try:
        db = _db()
        g = db.select_graph(name)
        search_prefix = f"{query}*"
        cypher = """
            CALL db.idx.fulltext.queryNodes('Searchable', $prefix)
            YIELD node
            WITH node
            RETURN node
            LIMIT 10
        """
        result_set = g.query(cypher, {"prefix": search_prefix}).result_set
        results = [_encode_node(row[0]) for row in result_set]
    except Exception as e:
        _json_error(str(e))

    _json_out({"repo": name, "results": results})


# ---------------------------------------------------------------------------
# neighbors
# ---------------------------------------------------------------------------

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
    name = _default_repo(repo)
    try:
        db = _db()
        g = db.select_graph(name)

        rel_query = f":{rel}" if rel else ""
        lbl_query = f":{label}" if label else ""
        cypher = f"""
            MATCH (n)-[e{rel_query}]->(dest{lbl_query})
            WHERE ID(n) IN $node_ids
            RETURN e, dest
        """
        result_set = g.query(cypher, {"node_ids": node_ids}).result_set

        result = {"nodes": [], "edges": []}
        for edge, dest_node in result_set:
            result["nodes"].append(_encode_node(dest_node))
            result["edges"].append(_encode_edge(edge))
    except Exception as e:
        _json_error(str(e))

    _json_out({"repo": name, **result})


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------

@app.command()
def paths(
    src: int = typer.Argument(..., help="Source node ID"),
    dest: int = typer.Argument(..., help="Destination node ID"),
    repo: Optional[str] = typer.Option(
        None, "--repo", help="Repository name (defaults to CWD name)"
    ),
) -> None:
    """Find call-chain paths between two nodes."""
    name = _default_repo(repo)
    try:
        db = _db()
        g = db.select_graph(name)

        cypher = """
            MATCH (src), (dest)
            WHERE ID(src) = $src_id AND ID(dest) = $dest_id
            WITH src, dest
            MATCH p = (src)-[:CALLS*]->(dest)
            RETURN p
        """
        result_set = g.query(cypher, {"src_id": src, "dest_id": dest}).result_set

        found_paths = []
        for row in result_set:
            path = []
            p = row[0]
            nodes = p.nodes()
            edges = p.edges()
            for n, e in zip(nodes, edges):
                path.append(_encode_node(n))
                path.append(_encode_edge(e))
            if nodes:
                path.append(_encode_node(nodes[-1]))
            found_paths.append(path)
    except Exception as e:
        _json_error(str(e))

    _json_out({"repo": name, "paths": found_paths})


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------

@app.command()
def info(
    repo: Optional[str] = typer.Option(
        None, "--repo", help="Repository name (defaults to CWD name)"
    ),
) -> None:
    """Show repository statistics and metadata."""
    name = _default_repo(repo)
    try:
        db = _db()
        g = db.select_graph(name)

        node_count = g.query("MATCH (n) RETURN count(n)").result_set[0][0]
        edge_count = g.query("MATCH ()-[e]->() RETURN count(e)").result_set[0][0]
        stats = {"node_count": node_count, "edge_count": edge_count}
        metadata = _get_repo_info(name) or {}
    except Exception as e:
        _json_error(str(e))

    _json_out({"repo": name, **stats, "metadata": metadata})


if __name__ == "__main__":
    app()
