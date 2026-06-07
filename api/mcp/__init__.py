"""MCP server module for code-graph.

Exposes the code-graph indexer and graph queries as MCP tools so AI coding
agents (Claude Code, Cursor, Copilot, Roo/Cline) can drive the indexer over
the standard Model Context Protocol stdio transport.

Entry point: ``cgraph-mcp`` (defined in ``pyproject.toml``).
"""
