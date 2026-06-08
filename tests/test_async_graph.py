"""Unit tests for async graph wrappers (AsyncGraphQuery, async_graph_exists, async_get_repos).

These tests mock the underlying falkordb.asyncio client so they run without
a live FalkorDB instance.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.graph import AsyncGraphQuery, async_graph_exists, async_get_repos


# ---------------------------------------------------------------------------
# async_graph_exists
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_async_graph_exists_true():
    mock_db = MagicMock()
    mock_db.list_graphs = AsyncMock(return_value=["my_repo", "other"])
    mock_db.aclose = AsyncMock()

    with patch("api.graph._async_db", return_value=mock_db):
        result = await async_graph_exists("my_repo")

    assert result is True
    mock_db.aclose.assert_awaited_once()


@pytest.mark.anyio
async def test_async_graph_exists_false():
    mock_db = MagicMock()
    mock_db.list_graphs = AsyncMock(return_value=["other"])
    mock_db.aclose = AsyncMock()

    with patch("api.graph._async_db", return_value=mock_db):
        result = await async_graph_exists("missing")

    assert result is False
    mock_db.aclose.assert_awaited_once()


@pytest.mark.anyio
async def test_async_graph_exists_closes_on_error():
    mock_db = MagicMock()
    mock_db.list_graphs = AsyncMock(side_effect=RuntimeError("conn failed"))
    mock_db.aclose = AsyncMock()

    with patch("api.graph._async_db", return_value=mock_db):
        with pytest.raises(RuntimeError, match="conn failed"):
            await async_graph_exists("any")

    mock_db.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# async_get_repos
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_async_get_repos_filters_suffixes():
    mock_db = MagicMock()
    mock_db.list_graphs = AsyncMock(
        return_value=["repo1", "code:repo2:main", "repo1_git", "repo1_schema", "code:repo2:main_git"]
    )
    mock_db.aclose = AsyncMock()

    with patch("api.graph._async_db", return_value=mock_db):
        repos = await async_get_repos()

    assert repos == [
        {"project": "repo1", "branch": "_default", "graph": "repo1"},
        {"project": "repo2", "branch": "main", "graph": "code:repo2:main"},
    ]
    mock_db.aclose.assert_awaited_once()


@pytest.mark.anyio
async def test_async_get_repos_empty():
    mock_db = MagicMock()
    mock_db.list_graphs = AsyncMock(return_value=[])
    mock_db.aclose = AsyncMock()

    with patch("api.graph._async_db", return_value=mock_db):
        repos = await async_get_repos()

    assert repos == []
    mock_db.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# AsyncGraphQuery
# ---------------------------------------------------------------------------

def _make_mock_graph_query():
    """Create a mock AsyncGraphQuery with a mocked db and graph."""
    mock_db = MagicMock()
    mock_db.aclose = AsyncMock()
    mock_graph = MagicMock()
    mock_graph.query = AsyncMock()
    mock_db.select_graph = MagicMock(return_value=mock_graph)
    return mock_db, mock_graph


@pytest.mark.anyio
async def test_async_graph_query_stats():
    mock_db, mock_graph = _make_mock_graph_query()

    node_result = MagicMock()
    node_result.result_set = [[42]]
    edge_result = MagicMock()
    edge_result.result_set = [[7]]
    mock_graph.query = AsyncMock(side_effect=[node_result, edge_result])

    with patch("api.graph._async_db", return_value=mock_db):
        gq = AsyncGraphQuery("test_repo")
        stats = await gq.stats()
        await gq.close()

    assert stats == {"node_count": 42, "edge_count": 7}
    mock_db.aclose.assert_awaited_once()


@pytest.mark.anyio
async def test_async_graph_query_close():
    mock_db, _ = _make_mock_graph_query()

    with patch("api.graph._async_db", return_value=mock_db):
        gq = AsyncGraphQuery("test_repo")
        await gq.close()

    mock_db.aclose.assert_awaited_once()
