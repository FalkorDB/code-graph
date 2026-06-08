"""T5/T7/T8 — query MCP tools tests.

Bundled because all three tools are thin async wrappers around existing
``AsyncGraphQuery`` operations and share the same fixture.
"""

from __future__ import annotations

import json

import pytest


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# search_code (T8) — runs first because callers/find_path need the ids it
# returns.
# ---------------------------------------------------------------------------


async def test_search_code_finds_entrypoint(indexed_fixture, expected_contract):
    from api.mcp.tools.structural import search_code

    results = await search_code(
        prefix="ent",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    names = {r["name"] for r in results}
    for required in expected_contract["search_prefixes"]["ent"]["must_include"]:
        assert required in names, f"expected {required} in {names}"


async def test_search_code_honors_limit(indexed_fixture):
    from api.mcp.tools.structural import search_code

    results = await search_code(
        prefix="r",  # broad prefix
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
        limit=1,
    )
    assert len(results) <= 1


async def test_search_code_empty_for_nonsense(indexed_fixture):
    from api.mcp.tools.structural import search_code

    results = await search_code(
        prefix="zzz_no_such_symbol_zzz",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    assert results == []


async def test_search_code_result_serialisable(indexed_fixture):
    from api.mcp.tools.structural import search_code

    results = await search_code(
        prefix="serv",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    json.dumps(results)  # must not raise


# ---------------------------------------------------------------------------
# get_callers / get_callees / get_dependencies (T5)
# ---------------------------------------------------------------------------


async def _find_id(indexed_fixture, name: str) -> int:
    """Helper: resolve a symbol name to its int node id via search_code."""
    from api.mcp.tools.structural import search_code

    rows = await search_code(
        prefix=name,
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    for r in rows:
        if r["name"] == name:
            return r["id"]
    raise AssertionError(f"symbol {name!r} not found via search_code")


async def test_get_callees_of_entrypoint(indexed_fixture, expected_contract):
    from api.mcp.tools.structural import get_callees

    entry_id = await _find_id(indexed_fixture, "entrypoint")
    callees = await get_callees(
        symbol_id=entry_id,
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    names = {c["name"] for c in callees}
    expected = set(expected_contract["calls"]["entrypoint"]["callees"])
    assert names & expected, (
        f"entrypoint callees {names} disjoint from expected {expected}"
    )

    for c in callees:
        assert c["relation"] == "CALLS"
        assert c["direction"] == "OUT"


async def test_get_callers_of_service(indexed_fixture, expected_contract):
    from api.mcp.tools.structural import get_callers

    service_id = await _find_id(indexed_fixture, "service")
    callers = await get_callers(
        symbol_id=service_id,
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    names = {c["name"] for c in callers}
    for required in expected_contract["calls"]["service"]["callers"]:
        assert required in names, f"expected caller {required} in {names}"

    for c in callers:
        assert c["relation"] == "CALLS"
        assert c["direction"] == "IN"


async def test_get_dependencies_aggregates_relations(indexed_fixture):
    from api.mcp.tools.structural import get_dependencies

    entry_id = await _find_id(indexed_fixture, "entrypoint")
    deps = await get_dependencies(
        symbol_id=entry_id,
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    # Default relations include CALLS, IMPORTS, DEFINES — at minimum the
    # CALLS edge to ``service`` must be present.
    rels = {d["relation"] for d in deps}
    assert "CALLS" in rels


async def test_get_dependencies_rejects_injected_relation(indexed_fixture):
    """Relation types are string-interpolated into Cypher, so agent-supplied
    values must be validated to prevent Cypher injection."""
    from api.mcp.tools.structural import get_dependencies

    entry_id = await _find_id(indexed_fixture, "entrypoint")
    with pytest.raises(ValueError, match="invalid relation type"):
        await get_dependencies(
            symbol_id=entry_id,
            project=indexed_fixture.project,
            branch=indexed_fixture.branch,
            rels=["CALLS]->() DETACH DELETE n //"],
        )


async def test_neighbor_tools_accept_string_ids(indexed_fixture):
    """Agents sometimes hand back ids as strings — must work."""
    from api.mcp.tools.structural import get_callees

    entry_id = await _find_id(indexed_fixture, "entrypoint")
    callees = await get_callees(
        symbol_id=str(entry_id),  # ← string!
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    assert isinstance(callees, list)


async def test_neighbor_tools_reject_garbage_ids(indexed_fixture):
    from api.mcp.tools.structural import get_callers

    with pytest.raises(ValueError, match="symbol_id"):
        await get_callers(
            symbol_id="not-a-number",
            project=indexed_fixture.project,
            branch=indexed_fixture.branch,
        )


# ---------------------------------------------------------------------------
# find_path (T7)
# ---------------------------------------------------------------------------


async def test_find_path_entrypoint_to_db(indexed_fixture, expected_contract):
    from api.mcp.tools.structural import find_path

    entry_id = await _find_id(indexed_fixture, "entrypoint")
    db_id = await _find_id(indexed_fixture, "db")

    paths = await find_path(
        source_id=entry_id,
        dest_id=db_id,
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    # The contract requires at least one path entrypoint -> ... -> db
    expected_min = next(
        p["paths_count"] for p in expected_contract["paths"]
        if p["source"] == "entrypoint" and p["dest"] == "db"
    )
    assert len(paths) >= expected_min

    # Each path must have entrypoint first, db last, in a non-empty node
    # sequence.
    for entry in paths:
        seq = entry["path"]
        assert len(seq) >= 2
        assert seq[0]["name"] == "entrypoint"
        assert seq[-1]["name"] == "db"
        # Every element must be a real node, not an edge that leaked through
        # the alternating [node, edge, node, ...] list as a bogus all-null
        # entry. Real nodes always resolve a name and a label.
        for node in seq:
            assert node["name"] is not None, f"edge leaked into path: {node}"
            assert node["label"] is not None, f"edge leaked into path: {node}"


async def test_find_path_no_path_returns_empty(indexed_fixture):
    """db -> entrypoint has no CALLS path (graph is acyclic)."""
    from api.mcp.tools.structural import find_path

    entry_id = await _find_id(indexed_fixture, "entrypoint")
    db_id = await _find_id(indexed_fixture, "db")

    paths = await find_path(
        source_id=db_id,
        dest_id=entry_id,
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    assert paths == []


async def test_find_path_honors_max_paths(indexed_fixture):
    from api.mcp.tools.structural import find_path

    entry_id = await _find_id(indexed_fixture, "entrypoint")
    db_id = await _find_id(indexed_fixture, "db")

    paths = await find_path(
        source_id=entry_id,
        dest_id=db_id,
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
        max_paths=1,
    )
    assert len(paths) <= 1


# ---------------------------------------------------------------------------
# Protocol registration
# ---------------------------------------------------------------------------


async def test_all_query_tools_registered():
    from api.mcp.server import app

    tools = {t.name for t in await app.list_tools()}
    assert {
        "search_code",
        "get_callers",
        "get_callees",
        "get_dependencies",
        "find_path",
    }.issubset(tools)
