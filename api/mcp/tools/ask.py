"""MCP ``ask`` tool — NL → Cypher → QA via GraphRAG (T11).

This is the strategic differentiator vs purely structural code-graph MCP
servers: the agent asks a natural-language question, and we return the
LLM's answer plus the actual Cypher that was executed (for transparency
and learning).

Two LLM round-trips bracket one FalkorDB query:

1. **LLM #1 (cypher gen):** question + ontology → Cypher
2. **FalkorDB:** execute Cypher → rows of nodes
3. **LLM #2 (QA synthesis):** question + rows → natural-language answer

The graph itself never goes to the LLM — only the schema and per-query
results — which is what makes this scale to huge codebases.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from ..graphrag_init import get_or_create_kg
from ..server import app


logger = logging.getLogger(__name__)


def _normalize_response(raw: Any) -> dict[str, Any]:
    """Coerce graphrag-sdk's chat response into the MCP payload shape.

    graphrag-sdk shapes its return as a ``dict`` with at least a
    ``response`` (the natural-language answer) and, depending on the
    SDK version, ``cypher`` / ``context``. We surface ``cypher_query``
    and ``context_nodes`` regardless — the design doc requires the
    Cypher to be visible so agents can debug, learn, and decide whether
    the query was sensible.
    """
    if not isinstance(raw, dict):
        return {"answer": str(raw), "cypher_query": None, "context_nodes": []}

    answer = raw.get("response") or raw.get("answer") or ""
    cypher = raw.get("cypher_query") or raw.get("cypher") or raw.get("query")
    ctx = (
        raw.get("context_nodes")
        or raw.get("context")
        or raw.get("results")
        or []
    )
    return {
        "answer": answer,
        "cypher_query": cypher,
        "context_nodes": ctx,
    }


@app.tool(
    name="ask",
    description=(
        "Ask a natural-language question about the indexed codebase. "
        "Powered by GraphRAG: the question is translated to Cypher, "
        "executed against the FalkorDB code graph, and the rows are "
        "summarised in English. The executed Cypher is returned in "
        "`cypher_query` so the agent can verify the answer and learn the "
        "schema."
    ),
)
async def ask(
    question: str,
    project: str,
    branch: Optional[str] = None,
) -> dict[str, Any]:
    kg = get_or_create_kg(project, branch or "_default")
    loop = asyncio.get_running_loop()

    def _ask_sync() -> Any:
        chat = kg.chat_session()
        return chat.send_message(question)

    try:
        raw = await loop.run_in_executor(None, _ask_sync)
    except Exception as exc:  # surface as a structured failure, not a crash
        logger.exception("ask failed for project=%s branch=%s", project, branch)
        return {
            "answer": "",
            "cypher_query": None,
            "context_nodes": [],
            "error": str(exc),
        }

    return _normalize_response(raw)
