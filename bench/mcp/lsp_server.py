"""FastMCP server exposing LSP navigation primitives for the ``lsp`` arm.

This is the symmetric counterpart to the code-graph MCP server: both arms
surface a small navigation tool set to the Copilot agent over stdio, so the
4-arm comparison isolates *what each backend can answer*, not the harness.

Backend: multilspy's ``SyncLanguageServer`` (jedi-language-server for Python),
wrapped by :mod:`bench.agents.lsp_adapter`. A single jedi subprocess is kept
alive for the whole session (see ``LSPClient.start``) so per-call startup cost
isn't paid on every tool call — the agent-token comparison stays fair.

Tools (mirroring bench/agents/lsp_adapter):
  - goto_definition(file, line, col)  -> [{path, line, col}]
  - find_references(file, line, col)  -> [{path, line, col}]
  - hover(file, line, col)            -> {text}
  - document_symbols(file)            -> [{name, kind, path, line, col}]

Positions are 0-based (LSP convention): the first line of a file is line 0,
the first column is col 0. This matches raw LSP/multilspy semantics.

Required env (set by the benchmark runner):
  LSP_REPO_ROOT   absolute path to the repo being analyzed (the agent's cwd)
  LSP_LANGUAGE    optional; defaults to "python"
  LSP_ENV_PATH    optional; environment_path passed to jedi for import
                  resolution (defaults to the server interpreter's prefix)
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from bench.agents.lsp_adapter import DEFAULT_SHIM, LSPClient

app: FastMCP = FastMCP("lsp")

# Single persistent client/server for the process lifetime. Started lazily on
# the first tool call so server construction errors surface as a tool error
# (visible in the trajectory) rather than killing stdio startup.
_client: LSPClient | None = None


def _get_client() -> LSPClient:
    global _client
    if _client is None:
        repo_root = os.environ.get("LSP_REPO_ROOT") or os.getcwd()
        language = os.environ.get("LSP_LANGUAGE", "python")
        env_path = os.environ.get("LSP_ENV_PATH") or None
        client = LSPClient(
            repo_root=repo_root,
            language=language,
            shim=DEFAULT_SHIM,
            environment_path=env_path,
        )
        client.start()
        _client = client
    return _client


@app.tool(
    name="goto_definition",
    description=(
        "Resolve the symbol at a 0-based (line, col) in `file` to its "
        "definition site(s); returns [{path, line, col}]. Use after you have "
        "located a symbol's position (e.g. via grep) to jump to where it is "
        "defined. line/col are 0-based: the first line is 0."
    ),
)
async def goto_definition(file: str, line: int, col: int) -> list[dict[str, Any]]:
    return _get_client().goto_definition(file, int(line), int(col))


@app.tool(
    name="find_references",
    description=(
        "Find all references to the symbol at a 0-based (line, col) in `file`; "
        "returns [{path, line, col}] across the repo (capped). Use to discover "
        "which other source files use a symbol. line/col are 0-based."
    ),
)
async def find_references(file: str, line: int, col: int) -> list[dict[str, Any]]:
    return _get_client().find_references(file, int(line), int(col))


@app.tool(
    name="hover",
    description=(
        "Get the signature + 1-sentence docstring for the symbol at a 0-based "
        "(line, col) in `file`; returns {text}. line/col are 0-based."
    ),
)
async def hover(file: str, line: int, col: int) -> dict[str, Any]:
    return _get_client().hover(file, int(line), int(col))


@app.tool(
    name="document_symbols",
    description=(
        "List the symbols (functions, classes, methods) defined in `file` with "
        "their 0-based positions; returns [{name, kind, path, line, col}]. Use "
        "to map a file's structure without reading the whole file."
    ),
)
async def document_symbols(file: str) -> list[dict[str, Any]]:
    return _get_client().document_symbols(file)


def main() -> None:
    """Run the LSP MCP server over stdio."""
    try:
        app.run(transport="stdio")
    finally:
        if _client is not None:
            _client.stop()


if __name__ == "__main__":
    main()
