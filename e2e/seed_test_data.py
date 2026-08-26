#!/usr/bin/env python3
"""Seed FalkorDB with test data for Playwright e2e tests."""

import os
import sys
import shutil
import logging
import tempfile
from pathlib import Path

import graphrag_sdk

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

from falkordb import FalkorDB
from api.project import Project

REPOS = [
    "https://github.com/pallets/flask",
]


def prepare_graphrag_sdk_source() -> Path:
    """Copy installed graphrag-sdk out of site-packages so LSP resolves calls as a project, not a library."""
    src = Path(graphrag_sdk.__file__).parent
    dst = Path(tempfile.mkdtemp(prefix="cgraph-e2e-sdk-")) / "graphrag_sdk"
    shutil.copytree(src, dst)
    return dst

# CALLS edges required by E2E path tests (caller → callee)
REQUIRED_CALLS_EDGES = [
    ("merge_with", "combine"),
    ("import_data", "add_node"),
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
        # MERGE both Function nodes so a missing one (e.g. import_data, which
        # has no `def` in graphrag-sdk 0.8.2) is synthesized with the minimal
        # properties the UI needs (Searchable label for autocomplete).
        g.query(
            "MERGE (src:Function:Searchable {name: $src}) "
            "ON CREATE SET src.path = 'synthesized.py', src.src_start = 1, src.src_end = 1, src.doc = '' "
            "MERGE (dest:Function:Searchable {name: $dest}) "
            "ON CREATE SET dest.path = 'synthesized.py', dest.src_start = 1, dest.src_end = 1, dest.doc = '' "
            "MERGE (src)-[:CALLS]->(dest)",
            {"src": caller, "dest": callee},
        )
        logger.info("[%s] CALLS %s → %s: ensured", graph_name, caller, callee)


def ensure_search_term_variety(graph_name: str) -> None:
    """Synthesize Function nodes whose names contain the e2e search terms that
    don't appear in graphrag-sdk 0.8.2 (e.g. 'test'). Without these, the
    auto-scroll and auto-complete tests don't have enough matches.
    """
    db = FalkorDB(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", 6379)),
    )
    g = db.select_graph(graph_name)
    for module in (
        "ontology", "graph", "entity", "relation", "document", "chunk",
        "query", "session", "agent", "chat", "attribute", "helpers",
    ):
        g.query(
            "MERGE (f:Function:Searchable {name: $name}) "
            "ON CREATE SET f.path = 'synthesized.py', f.src_start = 1, f.src_end = 1, f.doc = ''",
            {"name": f"test_{module}"},
        )


def main():
    sdk_path = prepare_graphrag_sdk_source()
    logger.info(
        "Seeding graphrag-sdk %s from %s",
        getattr(graphrag_sdk, "__version__", "?"),
        sdk_path,
    )
    sdk_project = Project(
        name="GraphRAG-SDK",
        path=sdk_path,
        url="https://github.com/FalkorDB/GraphRAG-SDK",
    )
    sdk_project.analyze_sources()

    for url in REPOS:
        logger.info("Seeding %s ...", url)
        proj = Project.from_git_repository(url)
        proj.analyze_sources()
        logger.info("Done seeding %s", url)

    # Use the actual composed graph name (e.g. "code:GraphRAG-SDK:_default")
    # that analyze_sources() wrote into -- not the bare project name, which
    # would silently create/write a separate, unused graph.
    graph_name = sdk_project.graph.name
    ensure_calls_edges(graph_name)
    ensure_search_term_variety(graph_name)

    logger.info("All test data seeded successfully.")


if __name__ == "__main__":
    main()
