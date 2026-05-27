"""T11 — MCP ``ask`` tool tests (mocked LLM)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_kg_cache():
    from api.mcp.graphrag_init import reset_cache

    reset_cache()
    yield
    reset_cache()


async def test_ask_registered():
    from api.mcp.server import app

    names = {t.name for t in await app.list_tools()}
    assert "ask" in names


async def test_ask_returns_normalised_payload():
    """Mock the entire KG; ensure the ask tool shapes its response
    correctly: {answer, cypher_query, context_nodes}.
    """
    from api.mcp.tools.ask import ask

    fake_chat = MagicMock()
    fake_chat.send_message.return_value = {
        "response": "service is called by entrypoint.",
        "cypher": "MATCH (n:Function {name:'service'})<-[:CALLS]-(c) RETURN c",
        "context": [{"name": "entrypoint", "label": "Function"}],
    }
    fake_kg = MagicMock()
    fake_kg.chat_session.return_value = fake_chat

    with patch("api.mcp.tools.ask.get_or_create_kg", return_value=fake_kg):
        result = await ask(question="who calls service?", project="p", branch="b")

    assert result["answer"] == "service is called by entrypoint."
    assert "MATCH" in (result["cypher_query"] or "")
    assert result["context_nodes"] == [{"name": "entrypoint", "label": "Function"}]
    assert "error" not in result

    fake_kg.chat_session.assert_called_once()
    fake_chat.send_message.assert_called_once_with("who calls service?")


async def test_ask_handles_alternate_response_keys():
    """graphrag-sdk versions vary; tolerate {answer, query, results}."""
    from api.mcp.tools.ask import ask

    fake_chat = MagicMock()
    fake_chat.send_message.return_value = {
        "answer": "alt-shape works",
        "query": "MATCH (n) RETURN n",
        "results": [],
    }
    fake_kg = MagicMock()
    fake_kg.chat_session.return_value = fake_chat

    with patch("api.mcp.tools.ask.get_or_create_kg", return_value=fake_kg):
        result = await ask(question="anything", project="p")

    assert result["answer"] == "alt-shape works"
    assert result["cypher_query"] == "MATCH (n) RETURN n"
    assert result["context_nodes"] == []


async def test_ask_handles_string_response():
    from api.mcp.tools.ask import ask

    fake_chat = MagicMock()
    fake_chat.send_message.return_value = "plain string answer"
    fake_kg = MagicMock()
    fake_kg.chat_session.return_value = fake_chat

    with patch("api.mcp.tools.ask.get_or_create_kg", return_value=fake_kg):
        result = await ask(question="anything", project="p")

    assert result["answer"] == "plain string answer"
    assert result["cypher_query"] is None
    assert result["context_nodes"] == []


async def test_ask_surfaces_errors_as_payload_not_raise():
    """Tool crashes must return a structured error so the agent doesn't
    see a transport exception."""
    from api.mcp.tools.ask import ask

    fake_chat = MagicMock()
    fake_chat.send_message.side_effect = RuntimeError("model unavailable")
    fake_kg = MagicMock()
    fake_kg.chat_session.return_value = fake_chat

    with patch("api.mcp.tools.ask.get_or_create_kg", return_value=fake_kg):
        result = await ask(question="anything", project="p")

    assert result["answer"] == ""
    assert result["error"] == "model unavailable"


async def test_ask_response_is_json_serialisable():
    from api.mcp.tools.ask import ask

    fake_chat = MagicMock()
    fake_chat.send_message.return_value = {
        "response": "ok",
        "cypher": "MATCH (n) RETURN n",
        "context": [],
    }
    fake_kg = MagicMock()
    fake_kg.chat_session.return_value = fake_chat

    with patch("api.mcp.tools.ask.get_or_create_kg", return_value=fake_kg):
        result = await ask(question="q", project="p")

    json.dumps(result)  # must not raise
