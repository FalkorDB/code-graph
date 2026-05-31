"""Shared fixtures for the MCP test suite.

Every per-tool integration test from T4 onward reuses the
``indexed_fixture`` fixture below: it indexes ``fixtures/sample_project``
into a uniquely named FalkorDB graph once per test session and yields a
descriptor (project name, branch, graph name) the test can pass straight
to the MCP tool under test.

The integration fixture is opt-in — it requires a reachable FalkorDB
(see ``api/graph.py``) and the optional language analyzers. Tests that
only need the static contract (counts, named callers / callees / paths)
can depend on ``expected_contract`` alone, which is pure-Python and
always available.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml


FIXTURE_DIR = Path(__file__).parent / "fixtures"
SAMPLE_PROJECT = FIXTURE_DIR / "sample_project"
EXPECTED_PATH = FIXTURE_DIR / "expected.yaml"


# ---------------------------------------------------------------------------
# Pure-Python contract (no FalkorDB required)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndexedFixture:
    """Descriptor for an indexed fixture graph."""

    project: str
    branch: str
    graph_name: str
    path: Path


@pytest.fixture(scope="session")
def expected_contract() -> dict[str, Any]:
    """Load ``fixtures/expected.yaml`` once per session."""
    with EXPECTED_PATH.open() as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="session")
def sample_project_path() -> Path:
    """Filesystem path to the fixture project."""
    return SAMPLE_PROJECT


# ---------------------------------------------------------------------------
# Integration fixture — indexes into a real FalkorDB
# ---------------------------------------------------------------------------


def _falkordb_reachable() -> bool:
    """Cheap probe so the integration fixture can self-skip in dev.

    Uses the falkordb-py client (rather than a raw TCP socket) so the
    check exercises the same connection settings the rest of the test
    suite uses, and surfaces auth / protocol failures — not just
    "something is listening on that port".
    """
    try:
        from falkordb import FalkorDB

        host = os.getenv("FALKORDB_HOST", "localhost")
        port = int(os.getenv("FALKORDB_PORT", 6379))
        db = FalkorDB(host=host, port=port, socket_timeout=1)
        return bool(db.connection.ping())
    except Exception:
        return False


@pytest.fixture(scope="session")
def indexed_fixture(sample_project_path: Path):
    """Index the sample project into a unique per-session graph.

    Each test session creates a new graph named
    ``code:sample_project:test-<uuid>`` so parallel CI shards never
    contend on the same graph. The graph is deleted on teardown so
    long-lived FalkorDB deployments (developer machines, shared CI)
    don't accumulate orphan ``test-*`` graphs across runs.

    Set ``MCP_KEEP_TEST_GRAPHS=1`` to skip teardown — useful for
    post-mortem debugging when a test fails and you want to poke at
    the graph by hand.

    Uses :class:`api.analyzers.SourceAnalyzer` directly (instead of
    ``Project.from_local_repository``) so the fixture doesn't need to
    be a git repository — analyzing a plain directory is exactly the
    code path the ``index_repo`` MCP tool exercises for non-git
    folders.
    """

    if not _falkordb_reachable():
        pytest.skip("FalkorDB not reachable on $FALKORDB_HOST:$FALKORDB_PORT")

    # Import locally so unit-only tests don't pay the import cost.
    from api.analyzers.source_analyzer import SourceAnalyzer
    from api.graph import Graph

    project_name = sample_project_path.name  # "sample_project"
    branch = f"test-{uuid.uuid4().hex[:8]}"
    graph = Graph(project_name, branch=branch)

    analyzer = SourceAnalyzer()
    # Belt-and-suspenders: jedi/multilspy used to create venv/ inside the
    # fixture during resolution, which polluted the tree with hundreds of
    # site-packages files. Tree-sitter doesn't do this, but we still pass
    # an explicit ignore list so a stray venv on a contributor's machine
    # can never break the exact-count contract.
    analyzer.analyze_local_folder(
        str(sample_project_path),
        graph,
        ignore=["venv", "__pycache__", ".venv"],
    )

    yield IndexedFixture(
        project=project_name,
        branch=branch,
        graph_name=graph.name,
        path=sample_project_path,
    )

    # Teardown — drop the graph so we don't leak ``test-<uuid>`` graphs
    # across runs. Opt out with MCP_KEEP_TEST_GRAPHS=1 when debugging.
    if os.getenv("MCP_KEEP_TEST_GRAPHS") == "1":
        return
    try:
        graph.delete()
    except Exception:
        # Best-effort cleanup: never fail a test session because
        # teardown couldn't reach FalkorDB.
        pass
