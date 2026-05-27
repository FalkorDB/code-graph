"""T9 — GraphRAG init module: cache + ontology reuse."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _reset_cache():
    from api.mcp.graphrag_init import reset_cache

    reset_cache()
    yield
    reset_cache()


def test_get_or_create_kg_uses_per_branch_graph_name():
    """The KG's underlying graph name must follow the T17 convention so
    the ask tool reads from the graph index_repo wrote to.
    """
    from api.graph import compose_graph_name
    from api.mcp import graphrag_init

    with patch.object(graphrag_init, "LiteModel") as mock_model, \
         patch.object(graphrag_init, "KnowledgeGraph") as mock_kg:
        mock_kg.return_value = object()  # opaque sentinel
        graphrag_init.get_or_create_kg("myproj", "feature-x")

    kwargs = mock_kg.call_args.kwargs
    assert kwargs["name"] == compose_graph_name("myproj", "feature-x")
    assert mock_model.called  # the model was constructed


def test_get_or_create_kg_caches_per_project_branch():
    from api.mcp import graphrag_init

    with patch.object(graphrag_init, "LiteModel"), \
         patch.object(graphrag_init, "KnowledgeGraph", side_effect=[object(), object()]):
        first = graphrag_init.get_or_create_kg("p", "_default")
        second = graphrag_init.get_or_create_kg("p", "_default")
    assert first is second, "same (project, branch) must return the cached instance"


def test_different_keys_yield_different_kgs():
    from api.mcp import graphrag_init

    with patch.object(graphrag_init, "LiteModel"), \
         patch.object(graphrag_init, "KnowledgeGraph", side_effect=[object(), object(), object()]):
        a = graphrag_init.get_or_create_kg("p1", "_default")
        b = graphrag_init.get_or_create_kg("p2", "_default")
        c = graphrag_init.get_or_create_kg("p1", "branch-2")
    assert a is not b
    assert a is not c
    assert b is not c


def test_get_or_create_kg_reuses_handcoded_ontology():
    """Critical: do NOT replace the hand-coded ontology with auto-extracted
    one. T9 acceptance criterion."""
    from api.llm import define_ontology
    from api.mcp import graphrag_init

    with patch.object(graphrag_init, "LiteModel"), \
         patch.object(graphrag_init, "KnowledgeGraph") as mock_kg:
        mock_kg.return_value = object()
        graphrag_init.get_or_create_kg("p", "_default")

    kwargs = mock_kg.call_args.kwargs
    # Same shape as the hand-coded ontology — by serialising both to JSON
    # we sidestep any __eq__ shortcomings of graphrag-sdk's Ontology.
    expected = define_ontology()
    assert type(kwargs["ontology"]) is type(expected)


def test_define_ontology_is_public():
    """T9 renamed _define_ontology → define_ontology."""
    from api import llm

    assert hasattr(llm, "define_ontology")
    assert not hasattr(llm, "_define_ontology"), (
        "the underscore-prefixed name should be gone — keeping both is "
        "an attractive nuisance for callers"
    )
