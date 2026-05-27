"""T6 — impact_analysis MCP tool tests."""

from __future__ import annotations

import json
import uuid

import pytest


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Unit tests — no FalkorDB required
# ---------------------------------------------------------------------------


def test_clamp_depth_normalizes():
    from api.mcp.tools.structural import _clamp_depth, IMPACT_MAX_DEPTH

    assert _clamp_depth(1) == 1
    assert _clamp_depth(5) == 5
    assert _clamp_depth(IMPACT_MAX_DEPTH) == IMPACT_MAX_DEPTH
    assert _clamp_depth(999) == IMPACT_MAX_DEPTH
    assert _clamp_depth(0) == 1
    assert _clamp_depth(-3) == 1
    assert _clamp_depth("4") == 4
    assert _clamp_depth("999") == IMPACT_MAX_DEPTH


def test_clamp_depth_rejects_garbage():
    from api.mcp.tools.structural import _clamp_depth

    with pytest.raises(ValueError, match="depth"):
        _clamp_depth("not-a-number")
    with pytest.raises(ValueError, match="depth"):
        _clamp_depth(True)  # bool would silently pass the int check
    with pytest.raises(ValueError, match="depth"):
        _clamp_depth(None)


async def test_impact_analysis_rejects_invalid_direction():
    from api.mcp.tools.structural import impact_analysis

    with pytest.raises(ValueError, match="direction"):
        await impact_analysis(
            symbol_id=1,
            project="any",
            direction="BOTH",
        )


async def test_impact_analysis_registered_via_app():
    from api.mcp.server import app

    names = {t.name for t in await app.list_tools()}
    assert "impact_analysis" in names


# ---------------------------------------------------------------------------
# Integration — sample_project fixture (T3)
# ---------------------------------------------------------------------------


async def _find_id(indexed_fixture, name: str) -> int:
    from api.mcp.tools.structural import search_code

    rows = await search_code(
        prefix=name,
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    for r in rows:
        if r["name"] == name:
            return r["id"]
    raise AssertionError(f"symbol {name!r} not found")


async def test_impact_upstream_of_db(indexed_fixture, expected_contract):
    from api.mcp.tools.structural import impact_analysis

    db_id = await _find_id(indexed_fixture, "db")
    upstream = await impact_analysis(
        symbol_id=db_id,
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
        direction="IN",
        depth=5,
    )
    names = {r["name"] for r in upstream}
    expected = set(
        expected_contract["impact"]["db"]["upstream_includes_any_of"]
    )
    assert names & expected, (
        f"db upstream {names} disjoint from expected {expected}"
    )
    # DISTINCT enforces no duplicate ids.
    ids = [r["id"] for r in upstream]
    assert len(ids) == len(set(ids))
    for r in upstream:
        assert r["direction"] == "IN"


async def test_impact_downstream_of_entrypoint(indexed_fixture, expected_contract):
    from api.mcp.tools.structural import impact_analysis

    entry_id = await _find_id(indexed_fixture, "entrypoint")
    downstream = await impact_analysis(
        symbol_id=entry_id,
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
        direction="OUT",
        depth=5,
    )
    names = {r["name"] for r in downstream}
    expected = set(
        expected_contract["impact"]["entrypoint"]["downstream_includes_any_of"]
    )
    assert names & expected, (
        f"entrypoint downstream {names} disjoint from expected {expected}"
    )
    for r in downstream:
        assert r["direction"] == "OUT"


async def test_impact_depth_one_only_immediate_callers(indexed_fixture):
    """depth=1 returns only direct callers — service for db's caller chain,
    not transitive ancestors like entrypoint."""
    from api.mcp.tools.structural import impact_analysis

    db_id = await _find_id(indexed_fixture, "db")
    upstream = await impact_analysis(
        symbol_id=db_id,
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
        direction="IN",
        depth=1,
    )
    names = {r["name"] for r in upstream}
    # entrypoint is 3 hops away — must NOT appear at depth=1.
    assert "entrypoint" not in names


async def test_impact_response_serialisable(indexed_fixture):
    from api.mcp.tools.structural import impact_analysis

    entry_id = await _find_id(indexed_fixture, "entrypoint")
    rows = await impact_analysis(
        symbol_id=entry_id,
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
        direction="OUT",
        depth=3,
    )
    json.dumps(rows)


# ---------------------------------------------------------------------------
# Cycle safety — small purpose-built graph
# ---------------------------------------------------------------------------


@pytest.fixture
async def cycle_graph():
    """Build a tiny graph with a 2-cycle (A↔B) plus an unrelated C → A edge.

    Created with a unique branch so it's isolated from the shared
    sample-project fixture. Not torn down (matches the pattern used by
    ``indexed_fixture``).
    """
    from api.graph import Graph

    project = "impact_cycle_test"
    branch = f"cycle-{uuid.uuid4().hex[:8]}"
    g = Graph(project, branch=branch)
    # CREATE three Function nodes with name + path; add CALLS edges
    # A → B, B → A (cycle), C → A.
    g.g.query(
        """
        CREATE
          (a:Function:Searchable {name: 'A', path: '/tmp/cycle.py', src_start: 1}),
          (b:Function:Searchable {name: 'B', path: '/tmp/cycle.py', src_start: 2}),
          (c:Function:Searchable {name: 'C', path: '/tmp/cycle.py', src_start: 3}),
          (a)-[:CALLS]->(b),
          (b)-[:CALLS]->(a),
          (c)-[:CALLS]->(a)
        """
    )
    yield project, branch


async def test_impact_handles_cycles(cycle_graph):
    """Variable-depth Cypher with DISTINCT must return each node once
    even when the graph has a cycle (A↔B). Without DISTINCT a *...*
    traversal would loop infinitely or emit duplicates."""
    from api.graph import AsyncGraphQuery
    from api.mcp.tools.structural import impact_analysis

    project, branch = cycle_graph

    # Resolve A's id via Cypher (no Searchable index in this throwaway graph)
    g = AsyncGraphQuery(project, branch=branch)
    try:
        res = await g._query("MATCH (n:Function {name: 'A'}) RETURN ID(n)")
        a_id = res.result_set[0][0]
    finally:
        await g.close()

    upstream = await impact_analysis(
        symbol_id=a_id,
        project=project,
        branch=branch,
        direction="IN",
        depth=5,
    )
    names = [r["name"] for r in upstream]
    # DISTINCT collapses the A->B->A->B->... cycle into single entries.
    # B (direct caller) and C (direct caller) must both be present;
    # A may also appear because A is reachable from itself through the
    # cycle. The crucial guarantee is no duplicates and no infinite loop.
    assert "B" in names and "C" in names
    assert len(names) == len(set(names)), f"duplicates in {names}"
