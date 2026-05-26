"""Text-to-Cypher chat over an existing FalkorDB code graph.

This module previously relied on `graphrag-sdk` 0.8.x's `KnowledgeGraph` class,
which wrapped a pre-populated graph and provided a `chat_session()` Q&A flow
with custom Cypher-generation and answer-synthesis prompts.

graphrag-sdk 1.x is a ground-up rewrite around document ingestion: the
`KnowledgeGraph` class is gone and the new `GraphRAG` facade expects to own
the graph it serves (it ingests text/files and writes nodes with embeddings).
There is no public primitive for "wrap an existing graph and chat over it".

code-graph builds its graphs through dedicated language analyzers, not through
ingestion. We therefore keep the text-to-Cypher pipeline in-house here:
generate Cypher from the question + ontology, execute it against FalkorDB,
then synthesize a natural-language answer. We use `graphrag-sdk`'s `LiteLLM`
provider as a thin LiteLLM wrapper so we still benefit from its retry logic.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from falkordb.asyncio import FalkorDB as AsyncFalkorDB
from graphrag_sdk import ChatMessage, LiteLLM

from .prompts import (
    CYPHER_GEN_PROMPT,
    CYPHER_GEN_SYSTEM,
    GRAPH_QA_PROMPT,
    GRAPH_QA_SYSTEM,
)

logger = logging.getLogger(__name__)


# The ontology is described to the LLM as plain text. Keeping this as a
# static string (rather than the old `Ontology` object tree) avoids depending
# on v0-only classes and makes the prompt easier to reason about.
_ONTOLOGY_TEXT = """
Entities:
- File(name: string [required, unique], path: string, ext: string)
- Class(name: string [required, unique], path: string, src_start: number, src_end: number, doc: string)
- Function(name: string [required, unique], path: string, src_start: number, src_end: number, args: string, src: string)
- Interface(name: string [required, unique], path: string, src_start: number, src_end: number, doc: string)

Relations (source -[TYPE]-> target):
- File -[DEFINES]-> Class
- File -[DEFINES]-> Function
- Class -[DEFINES]-> Class
- Class -[DEFINES]-> Function
- Function -[DEFINES]-> Function
- Class -[CALLS]-> Function
- Function -[CALLS]-> Function
- Class -[EXTENDS]-> Class
- Class -[IMPLEMENTS]-> Interface
""".strip()


_CYPHER_BLOCK_RE = re.compile(r"```(?:cypher)?\s*(.*?)\s*```", re.DOTALL)


def _extract_cypher(text: str) -> str:
    """Pull the Cypher statement out of an LLM response."""
    match = _CYPHER_BLOCK_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _build_llm() -> LiteLLM:
    model_name = os.getenv("MODEL_NAME", "gemini/gemini-flash-lite-latest")
    return LiteLLM(model_name, temperature=0.0)


def _falkordb() -> AsyncFalkorDB:
    return AsyncFalkorDB(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
        username=os.getenv("FALKORDB_USERNAME") or None,
        password=os.getenv("FALKORDB_PASSWORD") or None,
    )


async def _run_cypher(repo_name: str, cypher: str) -> list[list[Any]]:
    if not cypher:
        return []
    db = _falkordb()
    graph = db.select_graph(repo_name)
    try:
        result = await graph.query(cypher)
        return list(result.result_set or [])
    except Exception:
        logger.exception("Cypher execution failed: %s", cypher)
        return []


async def ask(repo_name: str, question: str) -> str:
    """Answer a natural-language question against the code graph for repo_name."""
    llm = _build_llm()

    cypher_resp = await llm.ainvoke_messages(
        [
            ChatMessage(role="system", content=CYPHER_GEN_SYSTEM.format(ontology=_ONTOLOGY_TEXT)),
            ChatMessage(role="user", content=CYPHER_GEN_PROMPT.format(question=question)),
        ]
    )
    cypher = _extract_cypher(cypher_resp.content)
    logger.debug("Generated Cypher: %s", cypher)

    context = await _run_cypher(repo_name, cypher)

    answer_resp = await llm.ainvoke_messages(
        [
            ChatMessage(role="system", content=GRAPH_QA_SYSTEM),
            ChatMessage(
                role="user",
                content=GRAPH_QA_PROMPT.format(
                    cypher=cypher,
                    context=context,
                    question=question,
                ),
            ),
        ]
    )
    return answer_resp.content
