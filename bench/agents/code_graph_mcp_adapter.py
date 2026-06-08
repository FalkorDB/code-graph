"""MCP-transport adapter to cgraph-mcp for the benchmark.

Sibling of `code_graph_adapter.py` (HTTP). Where the HTTP adapter talks
to the host FastAPI service over the network, this one spawns the
`cgraph-mcp` stdio MCP server in-process via the official MCP Python
SDK and dispatches tool calls over JSON-RPC.

This gives us a second, real-world benchmark track that exercises the
exact same transport agents (Claude Code, Cursor, …) will use in
production. Tool names match the 7-tool MCP surface
(`index_repo`, `search_code`, `get_callers`, `get_callees`,
`get_dependencies`, `impact_analysis`, `find_path`).

Each call spawns a fresh server, runs the call, and exits. That's
~0.5-1s overhead per call but keeps the model trivially safe to call
from a bash shim (one process per invocation, no shared state).
A future optimisation could persist the server across calls via a
side-channel daemon, but per-call spawn matches how external agents
actually use MCP servers today.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _default_timeout() -> float:
    """Pick the per-call MCP timeout, honoring CGRAPH_MCP_TIMEOUT_SEC.

    Defaults to 900 s (15 min). Bumped from the historical 300 s after
    we observed `index_repo` on full SWE-bench worktrees (sphinx-doc,
    sympy) finish in 5-10 min when spawned via the MCP stdio transport
    rather than the warm in-process HTTP path.
    """
    try:
        return float(os.environ.get("CGRAPH_MCP_TIMEOUT_SEC", "900"))
    except ValueError:
        return 900.0


DEFAULT_TIMEOUT_SEC = _default_timeout()


def _env_for_mcp() -> dict[str, str]:
    """Build the env for the spawned cgraph-mcp process.

    Pass through everything from the caller but make sure the FalkorDB
    coordinates are present — the runner usually sets them to point at
    the host FalkorDB container.

    Also default ``CODE_GRAPH_PY_RESOLVER=tree_sitter``. Without this,
    the spawned server falls back to the legacy jedi/multilspy path,
    which does ``python -m venv && pip install poetry && poetry install``
    per repo before analyzing the transitive dep tree — wedges for hours
    on large SWE-bench repos (sphinx, sympy). The HTTP track gets this
    via ``bench/scripts/start-api.sh``; we mirror it here so the MCP
    track is symmetric regardless of how the caller shell is configured.
    """
    env = dict(os.environ)
    env.setdefault("FALKORDB_HOST", os.environ.get("FALKORDB_HOST", "127.0.0.1"))
    env.setdefault("FALKORDB_PORT", os.environ.get("FALKORDB_PORT", "6379"))
    env.setdefault("CODE_GRAPH_PY_RESOLVER", "tree_sitter")
    return env


def _extract(result: Any) -> Any:
    """Normalize a CallToolResult into a JSON-serialisable Python value.

    FastMCP serializes list returns as **N separate TextContent
    chunks** (one per item) AND echoes the full list in
    ``structuredContent['result']``. Earlier versions of this helper
    returned only the *first* TextContent chunk, which meant every
    list-returning tool (``search_code``, ``get_callers``,
    ``get_callees``, ``get_dependencies``, ``impact_analysis``,
    ``find_path``) silently returned just the first element. On
    sympy-19040 the Opus agent searched "factor", got back one record
    instead of ten, gave up on the graph entirely and burned ~50 turns
    on bash exploration — cg_mcp ended up at +35% vs baseline.

    The new policy: prefer ``structuredContent`` when present (it
    always carries the full payload), unwrapping the spec's
    ``{"result": ...}`` envelope. Fall back to concatenating the text
    chunks (which may be JSON-each or a single JSON document).
    """
    struct = getattr(result, "structuredContent", None)
    if isinstance(struct, dict):
        if set(struct.keys()) == {"result"}:
            return struct["result"]
        return struct

    chunks: list[str] = [c.text for c in (result.content or []) if getattr(c, "text", None)]
    if not chunks:
        return None
    # Try parsing each chunk as JSON and assembling them. If every
    # chunk parses, we likely had a per-item list serialization; if
    # only one chunk parses, that's the whole payload.
    parsed: list[Any] = []
    for c in chunks:
        try:
            parsed.append(json.loads(c))
        except json.JSONDecodeError:
            return "\n".join(chunks)
    if len(parsed) == 1:
        return parsed[0]
    return parsed


async def _call_tool_async(name: str, arguments: dict[str, Any], timeout: float) -> Any:
    params = StdioServerParameters(command="cgraph-mcp", args=[], env=_env_for_mcp())
    # Silence the server's stderr (analyzer + MCP DEBUG logs). When the
    # bash shim is invoked by the agent, the server's stderr is merged
    # into the agent's tool-output buffer, inflating context by ~1.8kB
    # per call. The agent only needs the JSON-RPC result on stdout.
    devnull = open(os.devnull, "w")
    async with stdio_client(params, errlog=devnull) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=timeout)
            result = await asyncio.wait_for(
                session.call_tool(name, arguments), timeout=timeout
            )
            payload = _extract(result)
            if getattr(result, "isError", False):
                return {"error": payload}
            return payload


def call_tool(name: str, arguments: dict[str, Any], *, timeout: float = DEFAULT_TIMEOUT_SEC) -> Any:
    """Sync entry point for the bash shim. One spawn per call."""
    return asyncio.run(_call_tool_async(name, arguments, timeout))


# ── Top-level convenience wrappers ─────────────────────────────────────
# Names map 1:1 onto MCP tool names (and onto bench/tools/code_graph_mcp/
# tools.yaml entries). Kwargs mirror each tool's MCP arg schema.


def index_repo(path_or_url: str, branch: str | None = None, ignore: list[str] | None = None) -> dict[str, Any]:
    args: dict[str, Any] = {"path_or_url": path_or_url}
    if branch is not None:
        args["branch"] = branch
    if ignore is not None:
        args["ignore"] = ignore
    return call_tool("index_repo", args)


def search_code(prefix: str, project: str, branch: str | None = None, limit: int = 10) -> Any:
    args: dict[str, Any] = {"prefix": prefix, "project": project, "limit": limit}
    if branch is not None:
        args["branch"] = branch
    return call_tool("search_code", args)


def _neighbors(tool: str, symbol_id: int, project: str, branch: str | None, limit: int) -> Any:
    args: dict[str, Any] = {"symbol_id": symbol_id, "project": project, "limit": limit}
    if branch is not None:
        args["branch"] = branch
    return call_tool(tool, args)


def get_callers(symbol_id: int, project: str, branch: str | None = None, limit: int = 50) -> Any:
    return _neighbors("get_callers", symbol_id, project, branch, limit)


def get_callees(symbol_id: int, project: str, branch: str | None = None, limit: int = 50) -> Any:
    return _neighbors("get_callees", symbol_id, project, branch, limit)


def get_dependencies(symbol_id: int, project: str, branch: str | None = None, limit: int = 50) -> Any:
    return _neighbors("get_dependencies", symbol_id, project, branch, limit)


def impact_analysis(
    symbol_id: int,
    project: str,
    branch: str | None = None,
    direction: str = "IN",
    depth: int = 3,
) -> Any:
    args: dict[str, Any] = {
        "symbol_id": symbol_id,
        "project": project,
        "direction": direction,
        "depth": depth,
    }
    if branch is not None:
        args["branch"] = branch
    return call_tool("impact_analysis", args)


def find_path(source_id: int, dest_id: int, project: str, branch: str | None = None) -> Any:
    args: dict[str, Any] = {
        "source_id": source_id,
        "dest_id": dest_id,
        "project": project,
    }
    if branch is not None:
        args["branch"] = branch
    return call_tool("find_path", args)
