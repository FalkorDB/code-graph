"""MCP-side GraphRAG prompt overrides (T10).

Today this module is a thin re-export of ``api.prompts``. The point is the
**seam**: when the MCP ``ask`` tool needs prompt framing tuned for
"the user is an AI agent inspecting a codebase" instead of
"a human chatting about their repo", divergence happens *here* without
touching the existing FastAPI ``/api/chat`` prompts.

Until that day, every prompt below is identical to its ``api.prompts``
counterpart — verified by ``tests/mcp/test_code_prompts.py``.
"""

from __future__ import annotations

from api.prompts import (
    CYPHER_GEN_PROMPT,
    CYPHER_GEN_SYSTEM,
    GRAPH_QA_PROMPT,
    GRAPH_QA_SYSTEM,
)


__all__ = [
    "CYPHER_GEN_SYSTEM",
    "CYPHER_GEN_PROMPT",
    "GRAPH_QA_SYSTEM",
    "GRAPH_QA_PROMPT",
]


# TODO(MCP): start diverging here when agent-vs-human framing matters.
# Keep `api/prompts.py` as the canonical reference for the FastAPI
# chat endpoint and override the MCP-facing variants in this module.
