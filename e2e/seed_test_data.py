#!/usr/bin/env python3
"""Seed FalkorDB with test data for Playwright e2e tests."""

import os
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

from falkordb import FalkorDB
from api.project import Project

REPOS = [
    "https://github.com/FalkorDB/GraphRAG-SDK",
    "https://github.com/pallets/flask",
]

# CALLS edges required by E2E path tests (caller → callee)
REQUIRED_CALLS_EDGES = [
    ("merge_with", "combine"),
    ("ask", "runner"),
]


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
        proj = Project.from_git_repository(url)
        proj.analyze_sources()
        logger.info("Done seeding %s", url)

    ensure_calls_edges("GraphRAG-SDK")

    logger.info("All test data seeded successfully.")


if __name__ == "__main__":
    main()
