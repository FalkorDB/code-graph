"""Unit tests for the per-branch graph identity refactor (T17, issue #651).

Exercises only the name-composition / parsing helpers and the in-memory
behaviour of the ``Graph`` / ``AsyncGraphQuery`` constructors plus the
``run_migration`` orchestration. Anything that would require a live
FalkorDB / Redis instance is mocked.
"""

from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from api.graph import (
    DEFAULT_BRANCH,
    Graph,
    AsyncGraphQuery,
    compose_graph_name,
    parse_graph_name,
    async_get_repos,
)
from api.info import _repo_info_key, _legacy_repo_info_key, _normalize_branch
from api.git_utils.git_utils import GitRepoName, LegacyGitRepoName


# ---------------------------------------------------------------------------
# compose_graph_name / parse_graph_name
# ---------------------------------------------------------------------------

def test_compose_graph_name_default_branch():
    assert compose_graph_name("falkordb") == f"code:falkordb:{DEFAULT_BRANCH}"


def test_compose_graph_name_explicit_branch():
    assert compose_graph_name("falkordb", "main") == "code:falkordb:main"


def test_compose_graph_name_empty_branch_falls_back_to_default():
    assert compose_graph_name("foo", "") == f"code:foo:{DEFAULT_BRANCH}"


def test_compose_graph_name_branch_with_slashes():
    # Real-world branches like `dvir/feature` must survive composition.
    assert compose_graph_name("foo", "dvir/feature") == "code:foo:dvir/feature"


def test_parse_graph_name_round_trip():
    name = compose_graph_name("falkordb", "main")
    assert parse_graph_name(name) == ("falkordb", "main")


def test_parse_graph_name_legacy_returns_none():
    assert parse_graph_name("legacy_bare_name") is None


def test_parse_graph_name_handles_branch_with_colons():
    # Branch names cannot contain ':' in git, so we don't try to support it.
    # But branch may contain other unusual characters: the regex is
    # ``code:{project}:(.+)`` so anything after the second colon is the branch.
    assert parse_graph_name("code:repo:feature/x") == ("repo", "feature/x")


# ---------------------------------------------------------------------------
# Graph constructor branch-awareness
# ---------------------------------------------------------------------------

def _patched_falkordb():
    """Return a MagicMock that replaces ``FalkorDB`` in ``api.graph``."""
    mock_db = MagicMock()
    mock_db.select_graph = MagicMock(return_value=MagicMock())
    return patch("api.graph.FalkorDB", return_value=mock_db)


def test_graph_default_branch_composes_name():
    with _patched_falkordb():
        g = Graph("foo")
    assert g.project == "foo"
    assert g.branch == DEFAULT_BRANCH
    assert g.name == f"code:foo:{DEFAULT_BRANCH}"


def test_graph_explicit_branch_composes_name():
    with _patched_falkordb():
        g = Graph("foo", branch="main")
    assert g.project == "foo"
    assert g.branch == "main"
    assert g.name == "code:foo:main"


def test_graph_accepts_already_composed_name():
    with _patched_falkordb():
        g = Graph("code:bar:dev")
    assert g.project == "bar"
    assert g.branch == "dev"
    assert g.name == "code:bar:dev"


def test_graph_two_branches_produce_distinct_names():
    with _patched_falkordb():
        a = Graph("foo", branch="main")
        b = Graph("foo", branch="feat")
    assert a.name != b.name
    assert a.project == b.project == "foo"


def test_graph_from_raw_name_bypasses_composition():
    with _patched_falkordb():
        g = Graph.from_raw_name("code:foo:main_tmp")
    # raw name preserved exactly, even though it isn't a well-formed
    # ``code:project:branch`` graph.
    assert g.name == "code:foo:main_tmp"


# ---------------------------------------------------------------------------
# AsyncGraphQuery constructor branch-awareness
# ---------------------------------------------------------------------------

def test_async_graph_query_default_branch():
    with patch("api.graph._async_db") as mock_db:
        mock_db.return_value = MagicMock()
        g = AsyncGraphQuery("foo")
    assert g.project == "foo"
    assert g.branch == DEFAULT_BRANCH
    assert g.name == f"code:foo:{DEFAULT_BRANCH}"


def test_async_graph_query_branch_param():
    with patch("api.graph._async_db") as mock_db:
        mock_db.return_value = MagicMock()
        g = AsyncGraphQuery("foo", branch="develop")
    assert g.name == "code:foo:develop"


# ---------------------------------------------------------------------------
# async_get_repos returns (project, branch, graph) dicts
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_async_get_repos_mixes_legacy_and_new():
    mock_db = MagicMock()
    mock_db.list_graphs = AsyncMock(
        return_value=[
            "legacy_proj",                # legacy: no `code:` prefix
            "code:newproj:main",          # new style
            "code:newproj:feat",          # same project, different branch
            "code:newproj:main_git",      # internal suffix, must be filtered
            "code:newproj:main_schema",   # internal suffix, must be filtered
        ]
    )
    mock_db.aclose = AsyncMock()

    with patch("api.graph._async_db", return_value=mock_db):
        repos = await async_get_repos()

    assert repos == [
        {"project": "legacy_proj", "branch": DEFAULT_BRANCH, "graph": "legacy_proj"},
        {"project": "newproj", "branch": "main", "graph": "code:newproj:main"},
        {"project": "newproj", "branch": "feat", "graph": "code:newproj:feat"},
    ]


# ---------------------------------------------------------------------------
# Redis info key composition (api.info)
# ---------------------------------------------------------------------------

def test_repo_info_key_default_branch():
    assert _repo_info_key("falkordb") == "{falkordb}:_default_info"


def test_repo_info_key_explicit_branch():
    assert _repo_info_key("falkordb", "main") == "{falkordb}:main_info"


def test_legacy_repo_info_key_for_fallback():
    assert _legacy_repo_info_key("falkordb") == "{falkordb}_info"


def test_normalize_branch_handles_none_and_empty():
    assert _normalize_branch(None) == DEFAULT_BRANCH
    assert _normalize_branch("") == DEFAULT_BRANCH
    assert _normalize_branch("main") == "main"


# ---------------------------------------------------------------------------
# Git graph naming (api.git_utils.git_utils)
# ---------------------------------------------------------------------------

def test_git_repo_name_default_branch():
    assert GitRepoName("repo") == "{repo}:_default_git"


def test_git_repo_name_explicit_branch():
    assert GitRepoName("repo", "main") == "{repo}:main_git"


def test_legacy_git_repo_name_for_fallback():
    assert LegacyGitRepoName("repo") == "{repo}_git"


# ---------------------------------------------------------------------------
# Migration helper (api.migrations.per_branch)
# ---------------------------------------------------------------------------

def test_migration_dry_run_reports_actions_without_renaming():
    from api.migrations import per_branch

    fake_conn = MagicMock()
    fake_conn.exists = MagicMock(return_value=0)
    fake_graph = MagicMock()

    mock_db = MagicMock()
    mock_db.connection = fake_conn
    mock_db.list_graphs = MagicMock(
        return_value=["legacy_proj", "{legacy_proj}_git", "code:already:main"]
    )
    mock_db.select_graph = MagicMock(return_value=fake_graph)

    with patch.object(per_branch, "_connect", return_value=mock_db):
        result = per_branch.run_migration(dry_run=True)

    # Dry-run must never copy or delete any graph.
    fake_graph.copy.assert_not_called()
    fake_graph.delete.assert_not_called()
    fake_conn.rename.assert_not_called()

    # ``code:already:main`` is already migrated and must not be reported.
    assert result["dry_run"] is True
    assert result["graphs_renamed"] == 1  # legacy_proj
    # the {legacy_proj}_git companion graph was also planned, but only when
    # info-key existed; the mock returns exists=0 so info_renamed stays 0.
    assert result["git_renamed"] == 1


def test_migration_is_idempotent_when_no_legacy_graphs():
    from api.migrations import per_branch

    fake_conn = MagicMock()
    fake_conn.exists = MagicMock(return_value=0)
    fake_graph = MagicMock()

    mock_db = MagicMock()
    mock_db.connection = fake_conn
    # Already-migrated layout: only new-style names present.
    mock_db.list_graphs = MagicMock(
        return_value=["code:proj:_default", "{proj}:_default_git"]
    )
    mock_db.select_graph = MagicMock(return_value=fake_graph)

    with patch.object(per_branch, "_connect", return_value=mock_db):
        result = per_branch.run_migration(dry_run=False)

    fake_graph.copy.assert_not_called()
    fake_graph.delete.assert_not_called()
    fake_conn.rename.assert_not_called()
    assert result["graphs_renamed"] == 0
    assert result["info_renamed"] == 0
    assert result["git_renamed"] == 0
