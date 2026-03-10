#!/usr/bin/env python3
"""Seed FalkorDB with test data for Playwright e2e tests."""

import logging
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from api.project import Project
from falkordb import FalkorDB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

REPOS = [
    "https://github.com/FalkorDB/GraphRAG-SDK",
    "https://github.com/pallets/flask",
]

# CALLS edges required by E2E path tests (caller → callee)
REQUIRED_CALLS_EDGES = [
    ("merge_with", "combine"),
    ("import_data", "add_node"),
]

REPOSITORIES_DIR = Path.cwd() / "repositories"


def repo_name_from_url(url: str) -> str:
    parsed_path = urlparse(url).path.rstrip("/")
    repo_name = parsed_path.split("/")[-1]
    return repo_name.removesuffix(".git")


def fresh_clone_repository(url: str, path: Path) -> Path:
    if path.exists():
        # Replace any existing directory before creating a fresh shallow clone.
        shutil.rmtree(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(path)],
        check=True,
        capture_output=True,
        text=True,
    )

    return path


def load_project(url: str) -> Project:
    repo_path = REPOSITORIES_DIR / repo_name_from_url(url)

    if (repo_path / ".git").exists():
        logger.info("Using cached repository clone at %s", repo_path)
    else:
        logger.info("Cloning repository into cache at %s", repo_path)
        fresh_clone_repository(url, repo_path)

    return Project.from_local_repository(repo_path)


def ensure_calls_edges(graph_name: str) -> None:
    """Ensure required CALLS edges exist for E2E tests.

    The Python analyzer creates CALLS edges via LSP resolution, which can
    be unreliable across environments.  This guarantees the edges exist.
    """
    db = FalkorDB(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", 6379)),
    )
    g = db.select_graph(graph_name)

    # Diagnostic: show how many CALLS edges the analyzer created
    res = g.query("MATCH ()-[r:CALLS]->() RETURN count(r) AS cnt")
    cnt = res.result_set[0][0] if res.result_set else 0
    logger.info("[%s] Analyzer created %d CALLS edges", graph_name, cnt)

    for caller, callee in REQUIRED_CALLS_EDGES:
        res = g.query(
            "MATCH (src:Function {name: $src}), (dest:Function {name: $dest}) "
            "MERGE (src)-[e:CALLS]->(dest) "
            "RETURN e",
            {"src": caller, "dest": callee},
        )
        created = len(res.result_set) > 0
        logger.info(
            "[%s] CALLS %s → %s: %s",
            graph_name,
            caller,
            callee,
            "ensured" if created else "FAILED (node not found)",
        )


def main():
    for url in REPOS:
        logger.info("Seeding %s ...", url)
        proj = load_project(url)
        proj.analyze_sources()
        logger.info("Done seeding %s", url)

    ensure_calls_edges("GraphRAG-SDK")

    logger.info("All test data seeded successfully.")


if __name__ == "__main__":
    main()
