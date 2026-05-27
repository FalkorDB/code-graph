"""T12 — auto_init tests (mocked subprocess / graph)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# ensure_falkordb
# ---------------------------------------------------------------------------


def test_ensure_falkordb_no_action_when_reachable(monkeypatch):
    from api.mcp import auto_init

    monkeypatch.setenv("FALKORDB_HOST", "localhost")
    monkeypatch.setenv("FALKORDB_PORT", "6379")

    with patch.object(auto_init, "_falkordb_reachable", return_value=True), \
         patch("api.mcp.auto_init.subprocess.run") as mock_run:
        status = auto_init.ensure_falkordb()

    assert status["status"] == "ok"
    assert status["action"] == "none"
    mock_run.assert_not_called()


def test_ensure_falkordb_runs_cgraph_when_unreachable(monkeypatch):
    from api.mcp import auto_init

    monkeypatch.setenv("FALKORDB_HOST", "localhost")
    monkeypatch.setenv("FALKORDB_PORT", "6379")

    fake_result = MagicMock(returncode=0, stdout="ok", stderr="")
    with patch.object(auto_init, "_falkordb_reachable", return_value=False), \
         patch("api.mcp.auto_init.subprocess.run", return_value=fake_result) as mock_run:
        status = auto_init.ensure_falkordb()

    assert status["status"] == "ok"
    assert status["action"] == "started"
    mock_run.assert_called_once()
    args = mock_run.call_args.args[0]
    assert args == ["cgraph", "ensure-db"]


def test_ensure_falkordb_skips_docker_for_remote_host(monkeypatch):
    """Auto-start is localhost-only by design."""
    from api.mcp import auto_init

    monkeypatch.setenv("FALKORDB_HOST", "graph.example.com")
    monkeypatch.setenv("FALKORDB_PORT", "6379")

    with patch.object(auto_init, "_falkordb_reachable", return_value=False), \
         patch("api.mcp.auto_init.subprocess.run") as mock_run:
        status = auto_init.ensure_falkordb()

    assert status["status"] == "error"
    assert "localhost" in status["message"]
    mock_run.assert_not_called()


def test_ensure_falkordb_handles_missing_cli(monkeypatch):
    from api.mcp import auto_init

    monkeypatch.setenv("FALKORDB_HOST", "localhost")
    monkeypatch.setenv("FALKORDB_PORT", "6379")

    with patch.object(auto_init, "_falkordb_reachable", return_value=False), \
         patch("api.mcp.auto_init.subprocess.run", side_effect=FileNotFoundError):
        status = auto_init.ensure_falkordb()

    assert status["status"] == "error"
    assert "PATH" in status["message"]


# ---------------------------------------------------------------------------
# maybe_auto_index
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_cache():
    from api.mcp.auto_init import reset_auto_index_cache

    reset_auto_index_cache()
    yield
    reset_auto_index_cache()


def test_maybe_auto_index_skipped_when_env_unset(monkeypatch, tmp_path):
    from api.mcp import auto_init

    monkeypatch.delenv("CODE_GRAPH_AUTO_INDEX", raising=False)

    with patch.object(auto_init, "SourceAnalyzer", None, create=True):
        status = auto_init.maybe_auto_index(cwd=tmp_path)

    assert status["status"] == "skipped"
    assert "CODE_GRAPH_AUTO_INDEX" in status["reason"]


def test_maybe_auto_index_indexes_when_opt_in(monkeypatch, tmp_path):
    from api.mcp import auto_init

    monkeypatch.setenv("CODE_GRAPH_AUTO_INDEX", "true")

    fake_analyzer_instance = MagicMock()
    fake_graph_instance = MagicMock()
    with patch("api.analyzers.source_analyzer.SourceAnalyzer", return_value=fake_analyzer_instance), \
         patch("api.graph.Graph", return_value=fake_graph_instance), \
         patch.object(auto_init, "_detect_branch", return_value="main"):
        status = auto_init.maybe_auto_index(cwd=tmp_path, project="myproj")

    assert status["status"] == "indexed"
    assert status["project"] == "myproj"
    assert status["branch"] == "main"
    fake_analyzer_instance.analyze_local_folder.assert_called_once()


def test_maybe_auto_index_idempotent(monkeypatch, tmp_path):
    """Second call for the same (project, branch) is a no-op."""
    from api.mcp import auto_init

    monkeypatch.setenv("CODE_GRAPH_AUTO_INDEX", "1")

    fake_analyzer = MagicMock()
    with patch("api.analyzers.source_analyzer.SourceAnalyzer", return_value=fake_analyzer), \
         patch("api.graph.Graph", return_value=MagicMock()), \
         patch.object(auto_init, "_detect_branch", return_value="main"):
        first = auto_init.maybe_auto_index(cwd=tmp_path, project="myproj")
        second = auto_init.maybe_auto_index(cwd=tmp_path, project="myproj")

    assert first["status"] == "indexed"
    assert second["status"] == "skipped"
    assert "already" in second["reason"]
    # Critical: the analyzer was invoked exactly once.
    assert fake_analyzer.analyze_local_folder.call_count == 1


def test_maybe_auto_index_per_branch(monkeypatch, tmp_path):
    """Different branches under the same project each get one auto-index."""
    from api.mcp import auto_init

    monkeypatch.setenv("CODE_GRAPH_AUTO_INDEX", "yes")

    fake_analyzer = MagicMock()
    with patch("api.analyzers.source_analyzer.SourceAnalyzer", return_value=fake_analyzer), \
         patch("api.graph.Graph", return_value=MagicMock()):
        a = auto_init.maybe_auto_index(cwd=tmp_path, project="p", branch="main")
        b = auto_init.maybe_auto_index(cwd=tmp_path, project="p", branch="feature-x")
        c = auto_init.maybe_auto_index(cwd=tmp_path, project="p", branch="main")

    assert a["status"] == "indexed"
    assert b["status"] == "indexed"
    assert c["status"] == "skipped"
    assert fake_analyzer.analyze_local_folder.call_count == 2


def test_truthy_helper():
    from api.mcp.auto_init import _truthy

    for v in ("1", "true", "TRUE", "yes", "YES", "on"):
        assert _truthy(v)
    for v in ("", "0", "false", "no", "off", None):
        assert not _truthy(v)
