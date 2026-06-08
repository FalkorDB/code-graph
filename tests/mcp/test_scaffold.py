"""Scaffold smoke tests for the cgraph-mcp server (T1).

These tests prove the bare module is wired correctly:

1. The FastMCP ``app`` instance is importable.
2. The ``cgraph-mcp`` console script spawns a working stdio MCP server.
3. A client can complete the MCP handshake and ``list_tools`` returns 0
   tools (no tools are registered yet — they land in T4-T8, T11).

When tool tickets land they should ADD tests, not modify these — these
guard the scaffold itself.
"""

from __future__ import annotations

import shutil

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

STDIO_TIMEOUT = 10  # seconds — prevents CI from hanging if the server fails to start


@pytest.fixture
def anyio_backend() -> str:
    """Pin the anyio backend to asyncio so transitive trio installs don't double-run tests."""
    return "asyncio"


def test_app_is_importable() -> None:
    """The FastMCP instance can be imported and is named ``code-graph``."""
    from api.mcp.server import app

    assert app is not None
    assert app.name == "code-graph"


def test_main_entry_point_exists() -> None:
    """``main()`` is exposed for the console script."""
    from api.mcp import server

    assert callable(server.main)


@pytest.mark.anyio
async def test_stdio_server_lists_registered_tools() -> None:
    """Spawn ``cgraph-mcp`` over stdio and verify the protocol handshake.

    Once tool tickets land (T4+), ``list_tools`` returns at least the
    tools they register. This test only guards the *handshake* — per-tool
    behavioural assertions live in the per-tool test modules.
    """
    cgraph_mcp = shutil.which("cgraph-mcp")
    assert cgraph_mcp is not None, (
        "cgraph-mcp not on PATH; run `uv pip install -e .` first"
    )

    params = StdioServerParameters(command=cgraph_mcp, args=[])
    with anyio.fail_after(STDIO_TIMEOUT):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                # ``index_repo`` lands in T4; this assertion intentionally
                # only checks for presence so it stays stable as more tools
                # are registered in T5-T8 / T11.
                names = {t.name for t in result.tools}
                assert "index_repo" in names
