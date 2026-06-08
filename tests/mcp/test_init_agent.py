"""Tests for `cgraph init-agent` (T13).

Verifies the CLI drops the MCP guidance templates into CWD and
respects `--force`.
"""

import pytest
from typer.testing import CliRunner

from api.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _cd(monkeypatch: pytest.MonkeyPatch, path) -> None:
    monkeypatch.chdir(path)


def test_init_agent_writes_both_files(runner, tmp_path, monkeypatch):
    _cd(monkeypatch, tmp_path)

    result = runner.invoke(app, ["init-agent"])

    assert result.exit_code == 0, result.output
    claude = tmp_path / "CLAUDE.md"
    cursor = tmp_path / ".cursorrules"
    assert claude.exists()
    assert cursor.exists()
    # Templates should mention at least one core MCP tool.
    body = claude.read_text() + cursor.read_text()
    assert "search_code" in body
    assert "code-graph" in body.lower()


def test_init_agent_refuses_overwrite_without_force(runner, tmp_path, monkeypatch):
    _cd(monkeypatch, tmp_path)
    (tmp_path / "CLAUDE.md").write_text("preexisting\n")

    result = runner.invoke(app, ["init-agent"])

    assert result.exit_code != 0
    # Existing file untouched.
    assert (tmp_path / "CLAUDE.md").read_text() == "preexisting\n"
    # And we didn't write the other one either.
    assert not (tmp_path / ".cursorrules").exists()


def test_init_agent_force_overwrites(runner, tmp_path, monkeypatch):
    _cd(monkeypatch, tmp_path)
    (tmp_path / "CLAUDE.md").write_text("preexisting\n")
    (tmp_path / ".cursorrules").write_text("old rules\n")

    result = runner.invoke(app, ["init-agent", "--force"])

    assert result.exit_code == 0, result.output
    assert "preexisting" not in (tmp_path / "CLAUDE.md").read_text()
    assert "old rules" not in (tmp_path / ".cursorrules").read_text()
    assert "search_code" in (tmp_path / "CLAUDE.md").read_text()


def test_init_agent_templates_ship_with_package():
    """Smoke check: the bundled template files exist on disk where the
    CLI expects them. Guards against pyproject.toml drift."""
    from api.cli import _TEMPLATES_DIR

    assert (_TEMPLATES_DIR / "claude_mcp_section.md").is_file()
    assert (_TEMPLATES_DIR / "cursorrules.template").is_file()
