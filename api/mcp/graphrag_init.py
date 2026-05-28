"""GraphRAG init for the MCP ``ask`` tool (T9, refined by T11).

The MCP ``ask`` tool needs one ``KnowledgeGraph`` instance per
``(project, branch)`` to drive GraphRAG's NL→Cypher→QA round-trip. Building
one is non-trivial — ontology, model, prompts, FalkorDB connection — and
the existing ``api/llm.py`` builder bakes in a single repo name at module
import.

This module exposes:

* :func:`get_or_create_kg` — process-wide cache keyed by
  ``(project, branch)``. Cheap to call; one instance reused across many
  ``ask`` invocations.
* :func:`reset_cache` — used in tests to drop the cache between runs.

The ontology is intentionally reused from ``api.llm.define_ontology`` — it's
200+ lines of hand-tuned descriptions of File/Class/Function entities that
the LLM relies on to generate good Cypher. Replacing it with
``Ontology.from_kg_graph()`` (auto-extraction) is a regression.
"""

from __future__ import annotations

import os
from typing import Tuple

from graphrag_sdk import KnowledgeGraph, KnowledgeGraphModelConfig
from graphrag_sdk.models.litellm import LiteModel

from api.graph import compose_graph_name
from api.llm import define_ontology
from api.mcp.code_prompts import (
    CYPHER_GEN_PROMPT,
    CYPHER_GEN_SYSTEM,
    GRAPH_QA_PROMPT,
    GRAPH_QA_SYSTEM,
)


_CACHE: dict[Tuple[str, str], KnowledgeGraph] = {}


def _make_model() -> LiteModel:
    """Build the LiteModel from ``$MODEL_NAME`` (same default as api/llm.py)."""
    model_name = os.getenv("MODEL_NAME", "gemini/gemini-flash-lite-latest")
    return LiteModel(model_name)


def get_or_create_kg(project_name: str, branch: str = "_default") -> KnowledgeGraph:
    """Return a cached :class:`KnowledgeGraph` for ``(project, branch)``.

    Two calls with the same ``(project, branch)`` are guaranteed to return
    the **same** instance (identity preserved) so callers don't pay the
    construction cost on every ``ask``.

    The underlying graph name uses the T17 convention
    ``code:{project}:{branch}`` so per-branch indexing works end-to-end.
    """
    key = (project_name, branch)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    graph_name = compose_graph_name(project_name, branch)
    model = _make_model()
    kg = KnowledgeGraph(
        name=graph_name,
        ontology=define_ontology(),
        model_config=KnowledgeGraphModelConfig.with_model(model),
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", 6379)),
        username=os.getenv("FALKORDB_USERNAME", None),
        password=os.getenv("FALKORDB_PASSWORD", None),
        cypher_system_instruction=CYPHER_GEN_SYSTEM,
        qa_system_instruction=GRAPH_QA_SYSTEM,
        cypher_gen_prompt=CYPHER_GEN_PROMPT,
        qa_prompt=GRAPH_QA_PROMPT,
    )
    _CACHE[key] = kg
    return kg


def reset_cache() -> None:
    """Drop the per-process KG cache. Tests only."""
    _CACHE.clear()
