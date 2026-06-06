"""Tests for the MCP-transport bench adapter (`cg-mcp`).

Heavy end-to-end test (talks to real cgraph-mcp + FalkorDB) is gated
behind the same `_falkordb_reachable` check as the existing MCP tests.
Light tests run unconditionally and validate the argparse surface and
`_extract` shape handling.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from bench.agents import code_graph_mcp_adapter as cgm
from bench.cli import cg_mcp


REPO_ROOT = Path(__file__).resolve().parents[2]


def _mcp_server_available() -> bool:
    """The benchmark MCP adapter requires the in-repo `cgraph-mcp` server.

    On branches that pre-date the MCP stack (e.g. this branch's base,
    `fix-find-symbol-nested-name`), `api.mcp.server` is absent. The
    end-to-end test must skip there; it will run on staging once the
    MCP stack lands.
    """
    try:
        import api.mcp.server  # noqa: F401
        return True
    except ImportError:
        return False


def _falkordb_reachable() -> bool:
    host = os.environ.get("FALKORDB_HOST", "127.0.0.1")
    port = int(os.environ.get("FALKORDB_PORT", "6390"))
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


# ── light unit tests ──────────────────────────────────────────────────


class _FakeChunk:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResult:
    def __init__(self, content, structured=None, is_error=False):
        self.content = content
        self.structuredContent = structured
        self.isError = is_error


def test_extract_prefers_text_chunk_json():
    r = _FakeResult([_FakeChunk('{"id": 7, "name": "foo"}')])
    assert cgm._extract(r) == {"id": 7, "name": "foo"}


def test_extract_falls_back_to_structured_result_wrapper():
    r = _FakeResult(content=[], structured={"result": [1, 2, 3]})
    assert cgm._extract(r) == [1, 2, 3]


def test_extract_returns_raw_text_when_not_json():
    r = _FakeResult([_FakeChunk("not json at all")])
    assert cgm._extract(r) == "not json at all"


def test_cli_rejects_unknown_subcommand(capsys):
    with pytest.raises(SystemExit):
        cg_mcp.main(["totally_bogus"])


def test_cli_index_repo_parses_ignore_list(monkeypatch):
    captured: dict = {}

    def fake_index_repo(path_or_url, branch=None, ignore=None):
        captured.update(path_or_url=path_or_url, branch=branch, ignore=ignore)
        return {"ok": True, **captured}

    monkeypatch.setattr(cgm, "index_repo", fake_index_repo)
    rc = cg_mcp.main(
        [
            "index_repo",
            "--path-or-url",
            "/tmp/x",
            "--branch",
            "main",
            "--ignore",
            ".venv",
            "node_modules",
        ]
    )
    assert rc == 0
    assert captured["path_or_url"] == "/tmp/x"
    assert captured["branch"] == "main"
    assert captured["ignore"] == [".venv", "node_modules"]


# ── heavy end-to-end test ─────────────────────────────────────────────


@pytest.mark.skipif(
    not _mcp_server_available(),
    reason="api.mcp.server not present — requires MCP stack to be merged",
)
@pytest.mark.skipif(not _falkordb_reachable(), reason="FalkorDB unreachable")
def test_cg_mcp_search_code_end_to_end(tmp_path):
    """Spawn the actual cg-mcp shim against a freshly-indexed fixture."""
    fixture = REPO_ROOT / "tests" / "mcp" / "fixtures" / "sample_project"
    if not fixture.exists():
        pytest.skip("MCP sample fixture not present")

    env = os.environ.copy()
    env["FALKORDB_HOST"] = os.environ.get("FALKORDB_HOST", "127.0.0.1")
    env["FALKORDB_PORT"] = os.environ.get("FALKORDB_PORT", "6390")
    env["BENCH_PYTHON"] = sys.executable
    # Ensure cgraph-mcp is on PATH for the spawned subprocess.
    venv_bin = str(Path(sys.executable).parent)
    env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"

    # Index the fixture under a deterministic project/branch.
    project = "sample_project"
    branch = f"benchmcp-{os.getpid()}"
    idx = subprocess.run(
        [
            str(REPO_ROOT / "bench" / "cli" / "cg-mcp"),
            "index_repo",
            "--path-or-url",
            str(fixture),
            "--branch",
            branch,
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert idx.returncode == 0, idx.stderr
    idx_payload = json.loads(idx.stdout)
    assert "graph_name" in idx_payload
    assert idx_payload["num_nodes"] > 0

    # Then search for any known symbol from the fixture.
    sr = subprocess.run(
        [
            str(REPO_ROOT / "bench" / "cli" / "cg-mcp"),
            "search_code",
            "--project",
            project,
            "--branch",
            branch,
            "--prefix",
            "a",  # broad prefix to match something in the fixture
            "--limit",
            "3",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert sr.returncode == 0, sr.stderr
    out = json.loads(sr.stdout)
    assert out is not None
