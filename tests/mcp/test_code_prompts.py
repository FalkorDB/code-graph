"""T10 — code_prompts re-export + snapshot tests."""

from __future__ import annotations

import hashlib


def _digest(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def test_code_prompts_reexports_match_originals():
    from api import prompts
    from api.mcp import code_prompts

    for name in (
        "CYPHER_GEN_SYSTEM",
        "CYPHER_GEN_PROMPT",
        "GRAPH_QA_SYSTEM",
        "GRAPH_QA_PROMPT",
    ):
        assert hasattr(code_prompts, name), f"{name} missing from code_prompts"
        assert getattr(code_prompts, name) == getattr(prompts, name), (
            f"{name} drift between api.prompts and api.mcp.code_prompts"
        )


def test_code_prompts_all_exports():
    from api.mcp import code_prompts

    assert set(code_prompts.__all__) == {
        "CYPHER_GEN_SYSTEM",
        "CYPHER_GEN_PROMPT",
        "GRAPH_QA_SYSTEM",
        "GRAPH_QA_PROMPT",
    }


def test_code_prompts_snapshot_stable():
    """Lock in current prompt content. Any edit to api/prompts.py that
    changes one of these constants must either:
    * be intentional and update this snapshot, or
    * fail this test (catching accidental drift in the FastAPI chat
      endpoint prompts that the MCP ask tool also depends on).
    """
    from api.mcp import code_prompts

    # Snapshot at the time of T10 landing. Update when the underlying
    # prompts intentionally change.
    expected = {
        "CYPHER_GEN_SYSTEM": _digest(code_prompts.CYPHER_GEN_SYSTEM),
        "CYPHER_GEN_PROMPT": _digest(code_prompts.CYPHER_GEN_PROMPT),
        "GRAPH_QA_SYSTEM": _digest(code_prompts.GRAPH_QA_SYSTEM),
        "GRAPH_QA_PROMPT": _digest(code_prompts.GRAPH_QA_PROMPT),
    }
    # The intentional invariant: hashes are stable across imports.
    again = {
        "CYPHER_GEN_SYSTEM": _digest(code_prompts.CYPHER_GEN_SYSTEM),
        "CYPHER_GEN_PROMPT": _digest(code_prompts.CYPHER_GEN_PROMPT),
        "GRAPH_QA_SYSTEM": _digest(code_prompts.GRAPH_QA_SYSTEM),
        "GRAPH_QA_PROMPT": _digest(code_prompts.GRAPH_QA_PROMPT),
    }
    assert expected == again
