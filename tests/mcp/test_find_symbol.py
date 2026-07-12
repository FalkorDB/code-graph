"""T9 — find_symbol MCP tool tests.

Covers name resolution (simple + dotted qualname reduction), the ``file``
disambiguation flag + ordering, response-shape stability, deterministic order,
and ``limit`` / empty-name validation.
"""

from __future__ import annotations

import uuid

import pytest


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Validation — no FalkorDB required (these raise before touching the graph)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "   ", "Foo.", "Bar.   "])
async def test_find_symbol_rejects_empty_name(bad):
    from api.mcp.tools.structural import find_symbol

    with pytest.raises(ValueError, match="non-empty symbol name"):
        await find_symbol(name=bad, project="any")


@pytest.mark.parametrize("bad", ["not-a-number", 1.5, None, True])
async def test_find_symbol_rejects_garbage_limit(bad):
    from api.mcp.tools.structural import find_symbol

    with pytest.raises(ValueError, match="limit"):
        await find_symbol(name="entrypoint", project="any", limit=bad)


# ---------------------------------------------------------------------------
# Integration — sample_project fixture
# ---------------------------------------------------------------------------


async def test_find_symbol_resolves_simple_name(indexed_fixture):
    from api.mcp.tools.structural import find_symbol

    rows = await find_symbol(
        name="entrypoint",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    assert rows, "entrypoint must resolve"
    r = rows[0]
    assert isinstance(r["symbol_id"], int)
    assert r["name"] == "entrypoint"
    assert r["label"] == "Function"
    assert r["file"].endswith("entrypoint.py")
    assert isinstance(r["line"], int)
    # file_match is part of the documented shape and present even without a
    # ``file`` filter (False when none requested).
    assert r["file_match"] is False


async def test_find_symbol_reduces_dotted_qualname(indexed_fixture):
    """``Class.method`` must resolve identically to the bare ``method``."""
    from api.mcp.tools.structural import find_symbol

    dotted = await find_symbol(
        name="BaseRepo.repo",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    simple = await find_symbol(
        name="repo",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    assert {r["symbol_id"] for r in dotted} == {r["symbol_id"] for r in simple}
    assert all(r["name"] == "repo" for r in dotted)
    # Fixture defines repo() on BaseRepo, UserRepo and OrderRepo.
    assert len(simple) == 3


async def test_find_symbol_file_match_shape_stable(indexed_fixture):
    """Every row carries a boolean ``file_match`` regardless of the args."""
    from api.mcp.tools.structural import find_symbol

    rows = await find_symbol(
        name="repo",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    assert rows
    for r in rows:
        assert isinstance(r["file_match"], bool)
        assert set(r) >= {"symbol_id", "name", "label", "file", "line", "file_match"}


async def test_find_symbol_file_filter_flags_matches(indexed_fixture):
    """A matching ``file`` flags every in-file candidate; a non-matching one
    still returns the global matches but flags none."""
    from api.mcp.tools.structural import find_symbol

    in_file = await find_symbol(
        name="repo",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
        file="repo.py",
    )
    assert in_file and all(r["file_match"] for r in in_file)

    no_file = await find_symbol(
        name="repo",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
        file="does_not_exist.py",
    )
    # Search is not silently widened away — global matches still surface…
    assert {r["symbol_id"] for r in no_file} == {r["symbol_id"] for r in in_file}
    # …but the agent can see none were in the requested file.
    assert all(r["file_match"] is False for r in no_file)


async def test_find_symbol_deterministic_order(indexed_fixture):
    """Repeated calls return rows in the same order (no FalkorDB row-order
    dependence)."""
    from api.mcp.tools.structural import find_symbol

    a = await find_symbol(
        name="repo",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    b = await find_symbol(
        name="repo",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    assert [r["symbol_id"] for r in a] == [r["symbol_id"] for r in b]


async def test_find_symbol_honors_limit(indexed_fixture):
    from api.mcp.tools.structural import find_symbol

    rows = await find_symbol(
        name="repo",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
        limit="1",  # stringified ints are accepted and coerced
    )
    assert len(rows) == 1


async def test_find_symbol_negative_limit_clamped_not_tail_slice(indexed_fixture):
    """A negative ``limit`` must clamp to 1, NOT flip ``rows[:limit]`` into a
    surprising tail slice."""
    from api.mcp.tools.structural import find_symbol

    full = await find_symbol(
        name="repo",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
    )
    clamped = await find_symbol(
        name="repo",
        project=indexed_fixture.project,
        branch=indexed_fixture.branch,
        limit=-2,
    )
    assert len(clamped) == 1
    assert clamped[0]["symbol_id"] == full[0]["symbol_id"]


async def test_find_symbol_registered():
    from api.mcp.server import app

    names = {t.name for t in await app.list_tools()}
    assert "find_symbol" in names


# ---------------------------------------------------------------------------
# Ordering across files — purpose-built graph (two same-named symbols)
# ---------------------------------------------------------------------------


@pytest.fixture
async def two_file_graph():
    """Two ``foo`` Functions in different files so ``file`` disambiguation can
    actually reorder the result. Unique branch keeps it isolated; not torn down
    (matches the ``indexed_fixture`` / ``cycle_graph`` pattern)."""
    from api.graph import Graph

    project = "find_symbol_order_test"
    branch = f"order-{uuid.uuid4().hex[:8]}"
    g = Graph(project, branch=branch)
    g.g.query(
        """
        CREATE
          (:Function:Searchable {name: 'foo', path: '/tmp/aaa.py', src_start: 1}),
          (:Function:Searchable {name: 'foo', path: '/tmp/bbb.py', src_start: 1})
        """
    )
    yield project, branch


async def test_find_symbol_orders_in_file_first(two_file_graph):
    from api.mcp.tools.structural import find_symbol

    project, branch = two_file_graph

    rows = await find_symbol(name="foo", project=project, branch=branch, file="bbb.py")
    assert len(rows) == 2
    # The requested file sorts first and is the only flagged match.
    assert rows[0]["file"].endswith("bbb.py")
    assert rows[0]["file_match"] is True
    assert rows[1]["file_match"] is False
