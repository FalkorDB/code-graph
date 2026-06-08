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

    # search_code is file-oriented: a free-text query naming a symbol must
    # surface the file that defines it.
    symbol = expected_contract["search_prefixes"]["ent"]["must_include"][0]
    results = await search_code(
        query=symbol,
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    files = [r["file"] for r in results if r.get("file")]
    assert any(f.endswith(f"{symbol}.py") for f in files), files


async def test_search_code_honors_limit(indexed_fixture):
    from api.mcp.tools.structural import search_code

    results = await search_code(
        query="entrypoint service repo db",  # broad: matches several files
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
        limit=1,
    )
    assert len(results) <= 1


async def test_search_code_empty_for_nonsense(indexed_fixture):
    from api.mcp.tools.structural import search_code

    results = await search_code(
        query="zzz_no_such_symbol_zzz",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    assert results == []


async def test_search_code_result_serialisable(indexed_fixture):
    from api.mcp.tools.structural import search_code

    results = await search_code(
        query="service",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    json.dumps(results)  # must not raise


def test_relativize_strips_worktree_prefix():
    from api.mcp.tools.structural import _relativize

    proj = "django__django-18854__loc"
    abs_path = f"/Users/x/.worktrees/bench/worktrees/code_graph/{proj}/django/db/models/fields/__init__.py"
    assert _relativize(abs_path, proj) == "django/db/models/fields/__init__.py"


def test_relativize_keeps_nested_repeat_of_project_name():
    """A nested dir repeating the project name must survive (first-match strip)."""
    from api.mcp.tools.structural import _relativize

    proj = "myproj"
    abs_path = f"/root/{proj}/src/vendor/{proj}/file.py"
    assert _relativize(abs_path, proj) == f"src/vendor/{proj}/file.py"


def test_relativize_noops_without_marker_or_rel_to():
    from api.mcp.tools.structural import _relativize

    assert _relativize("/abs/path/no/marker.py", "absent") == "/abs/path/no/marker.py"
    assert _relativize("/abs/path.py", None) == "/abs/path.py"
    assert _relativize(None, "proj") is None


async def test_search_code_returns_relative_paths(indexed_fixture):
    from api.mcp.tools.structural import search_code

    results = await search_code(
        query="entrypoint",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    for r in results:
        if r.get("file"):
            assert not r["file"].startswith("/"), f"path not relativized: {r['file']}"
            assert f"/{indexed_fixture.project}/" not in r["file"]


async def test_search_code_ranks_exact_match_within_limit(indexed_fixture, expected_contract):
    """A query naming a symbol must surface that symbol's file as the top hit,
    with the matching symbol as the file's representative."""
    from api.mcp.tools.structural import search_code

    symbol = next(iter(expected_contract["search_prefixes"]["ent"]["must_include"]))
    results = await search_code(
        query=symbol,
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
        limit=1,
    )
    assert results, f"no results for query {symbol!r}"
    assert results[0]["file"].endswith(f"{symbol}.py")
    assert results[0]["name"] == symbol


# ---------------------------------------------------------------------------
# get_callers / get_callees / get_dependencies (T5)
# ---------------------------------------------------------------------------


async def _find_id(indexed_fixture, name: str) -> int:
    """Resolve a symbol name to its int node id directly from the graph.

    ``search_code`` is file-oriented and no longer returns per-symbol ids, so
    the neighbor/path/impact tests resolve the id straight from FalkorDB. The
    names used here (entrypoint/service/db) are unique Functions in the fixture,
    so a uniqueness assertion guards against silently picking the wrong node.
    """
    from api.mcp.tools.structural import _project_arg

    g = _project_arg(indexed_fixture.project, indexed_fixture.branch)
    try:
        res = await g._query(
            "MATCH (n) WHERE (n:Function OR n:Class) AND n.name = $name "
            "RETURN ID(n)",
            {"name": name},
        )
    finally:
        await g.close()
    rows = res.result_set
    assert rows, f"symbol {name!r} not found in graph"
    assert len(rows) == 1, f"ambiguous symbol {name!r}: {len(rows)} matches"
    return rows[0][0]


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
        "get_neighbors",
        "find_path",
    }.issubset(tools)
    # The per-edge tools were consolidated into get_neighbors and must no
    # longer be advertised on the MCP surface.
    assert tools.isdisjoint(
        {"get_callers", "get_callees", "get_dependencies", "get_importers", "get_overrides"}
    )


async def test_get_neighbors_matches_legacy_callers_callees(indexed_fixture):
    from api.mcp.tools.structural import get_callees, get_callers, get_neighbors

    project = indexed_fixture.project
    branch = indexed_fixture.branch
    entry_id = await _find_id(indexed_fixture, "entrypoint")

    legacy_callees = await get_callees(symbol_id=entry_id, project=project, branch=branch)
    unified_callees = await get_neighbors(
        symbol_id=entry_id, project=project, branch=branch, relation="CALLS", direction="OUT"
    )
    assert {n["id"] for n in unified_callees} == {n["id"] for n in legacy_callees}

    service_id = await _find_id(indexed_fixture, "service")
    legacy_callers = await get_callers(symbol_id=service_id, project=project, branch=branch)
    unified_callers = await get_neighbors(
        symbol_id=service_id, project=project, branch=branch, relation="CALLS", direction="IN"
    )
    assert {n["id"] for n in unified_callers} == {n["id"] for n in legacy_callers}


async def test_get_neighbors_matches_legacy_dependencies(indexed_fixture):
    from api.mcp.tools.structural import get_dependencies, get_neighbors

    project = indexed_fixture.project
    branch = indexed_fixture.branch
    entry_id = await _find_id(indexed_fixture, "entrypoint")

    legacy = await get_dependencies(symbol_id=entry_id, project=project, branch=branch)
    unified = await get_neighbors(
        symbol_id=entry_id,
        project=project,
        branch=branch,
        relation=["IMPORTS", "CALLS", "DEFINES"],
        direction="OUT",
    )
    assert {n["id"] for n in unified} == {n["id"] for n in legacy}


# ---------------------------------------------------------------------------
# get_file_neighbors (T8b) — file-level structural coupling
# ---------------------------------------------------------------------------


async def test_get_file_neighbors_reaches_cross_file_dependency(indexed_fixture):
    """File-level expansion must reach a cross-file dependency.

    ``entrypoint()`` calls ``service()`` in another file, so ``service.py``
    must surface as a neighbor — and crucially via expanding ALL symbols in
    the file, not only the lowest-``src_start`` representative one.
    """
    from api.mcp.tools.structural import get_file_neighbors

    res = await get_file_neighbors(
        "python/entrypoint.py",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    assert isinstance(res, dict)
    assert res["file"] == "python/entrypoint.py"
    assert res["truncated"] is False
    assert res["total_neighbors"] == len(res["neighbors"])

    names = [n["file"] for n in res["neighbors"]]
    assert any(n.endswith("service.py") for n in names), names
    assert "python/entrypoint.py" not in names  # self excluded

    for n in res["neighbors"]:
        assert isinstance(n["file_id"], int)  # recursable handle
        assert n["edge_count"] >= 1
        assert n["relations"]  # relation:direction breakdown present


async def test_get_file_neighbors_id_and_path_agree(indexed_fixture):
    """Resolving by File-node id and by repo-relative path yields the same set."""
    from api.mcp.tools.structural import get_file_neighbors

    by_path = await get_file_neighbors(
        "python/service.py",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    assert by_path["file_id"] is not None
    by_id = await get_file_neighbors(
        by_path["file_id"],
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    assert [n["file"] for n in by_id["neighbors"]] == [
        n["file"] for n in by_path["neighbors"]
    ]


async def test_get_file_neighbors_unknown_file_is_empty(indexed_fixture):
    from api.mcp.tools.structural import get_file_neighbors

    res = await get_file_neighbors(
        "python/does_not_exist.py",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    assert res["total_neighbors"] == 0
    assert res["neighbors"] == []
    assert res["truncated"] is False


async def test_search_code_returns_file_id(indexed_fixture):
    """Every search_code hit must carry a File-node ``file_id`` to hop from."""
    from api.mcp.tools.structural import search_code

    rows = await search_code(
        query="service repo db",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    assert rows, "expected at least one hit"
    for r in rows:
        assert isinstance(r["file_id"], int)


async def test_get_file_neighbors_registered():
    from api.mcp.server import app

    tools = await app.list_tools()
    assert "get_file_neighbors" in {t.name for t in tools}
