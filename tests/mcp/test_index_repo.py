"""T4 — ``index_repo`` MCP tool tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_index_repo_local_path(
    require_falkordb, sample_project_path: Path, expected_contract
):
    """Index a local non-git folder and verify the response shape."""
    from api.mcp.tools.structural import index_repo

    result = await index_repo(str(sample_project_path), branch="t4-local-test")

    assert result["project_name"] == "sample_project"
    assert result["branch"] == "t4-local-test"
    assert result["graph_name"].startswith("code:sample_project:")
    assert result["mode"] == "full"
    assert result["num_nodes"] >= sum(expected_contract["counts"].values())
    assert result["num_edges"] > 0
    assert "py" in result["languages_detected"]


async def test_index_repo_rejects_missing_path():
    """Missing local paths surface as a clear ValueError to the agent."""
    from api.mcp.tools.structural import index_repo

    with pytest.raises(ValueError, match="path does not exist"):
        await index_repo("/this/path/definitely/does/not/exist/anywhere")


async def test_index_repo_honors_allowed_analysis_dir(
    sample_project_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Sandboxing: paths outside ALLOWED_ANALYSIS_DIR are rejected."""
    from api.mcp.tools import structural

    monkeypatch.setenv("ALLOWED_ANALYSIS_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="outside ALLOWED_ANALYSIS_DIR"):
        await structural.index_repo(str(sample_project_path), branch="t4-sandbox")


async def test_index_repo_registered_via_app():
    """The tool is reachable via ``app.list_tools()`` (protocol parity)."""
    from api.mcp.server import app

    tools = await app.list_tools()
    names = {t.name for t in tools}
    assert "index_repo" in names

    tool = next(t for t in tools if t.name == "index_repo")
    schema = tool.inputSchema
    # Description / param schema are surfaced to the agent.
    assert "path_or_url" in schema["properties"]
    assert "branch" in schema["properties"]
    assert "incremental" in schema["properties"]


async def test_index_repo_response_serialises_to_json(
    require_falkordb,
    sample_project_path: Path,
):
    """MCP transports JSON — the response dict must be JSON-serialisable."""
    from api.mcp.tools.structural import index_repo

    result = await index_repo(str(sample_project_path), branch="t4-json-test")
    # Must not raise.
    json.dumps(result)


async def test_index_repo_rejects_ssh_url():
    """scp/ssh git specs surface an actionable error (not a confusing
    'invalid url' from the underlying validator)."""
    from api.mcp.tools.structural import index_repo

    with pytest.raises(ValueError, match="only supports http"):
        await index_repo("git@github.com:FalkorDB/code-graph.git")


async def test_index_repo_local_git_without_remote(
    require_falkordb, tmp_path: Path
):
    """A git checkout with no configured remote must still index.

    ``Project.from_local_repository`` reads ``remotes[0].url`` and raises
    ``IndexError`` when the repo has no remote; ``index_repo`` should fall
    back to indexing without url metadata instead of failing.
    """
    import subprocess

    from api.mcp.tools.structural import index_repo

    repo = tmp_path / "localrepo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "mod.py").write_text(
        "def helper():\n    return 1\n\n\ndef main():\n    return helper()\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-qm", "init"],
        cwd=repo, check=True,
    )

    result = await index_repo(str(repo), branch="t4-no-remote")

    assert result["project_name"] == "localrepo"
    assert result["branch"] == "t4-no-remote"
    assert result["graph_name"].startswith("code:localrepo:")
    assert result["num_nodes"] > 0
