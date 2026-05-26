"""Tests for the code-graph HTTP adapter using httpx MockTransport."""

from __future__ import annotations

import json

import httpx
import pytest

from bench.agents.code_graph_adapter import CodeGraphClient


def _mock_handler_factory(responses: dict[str, httpx.Response]):
    """Build a MockTransport handler keyed by 'METHOD path'."""

    def handler(request: httpx.Request) -> httpx.Response:
        key = f"{request.method} {request.url.path}"
        if key not in responses:
            return httpx.Response(404, json={"error": f"no mock for {key}"})
        resp = responses[key]
        # capture the body for assertion via the response.extensions
        resp.extensions["last_request_body"] = (
            json.loads(request.content) if request.content else None
        )
        resp.extensions["last_request_query"] = dict(request.url.params)
        return resp

    return handler


def _client_with(responses: dict[str, httpx.Response]) -> CodeGraphClient:
    transport = httpx.MockTransport(_mock_handler_factory(responses))
    return CodeGraphClient(
        base_url="http://test", token="t0k3n", transport=transport
    )


def test_graph_entities_sends_repo_query_and_returns_json():
    resp = httpx.Response(200, json={"nodes": [{"id": 1}], "edges": []})
    with _client_with({"GET /api/graph_entities": resp}) as c:
        out = c.graph_entities("my-repo")
    assert out == {"nodes": [{"id": 1}], "edges": []}
    assert resp.extensions["last_request_query"] == {"repo": "my-repo"}


def test_get_neighbors_posts_json_body():
    resp = httpx.Response(200, json={"nodes": [], "edges": []})
    with _client_with({"POST /api/get_neighbors": resp}) as c:
        c.get_neighbors("r", [1, 2, 3])
    assert resp.extensions["last_request_body"] == {"repo": "r", "node_ids": [1, 2, 3]}


def test_find_paths_posts_src_dest():
    resp = httpx.Response(200, json={"paths": []})
    with _client_with({"POST /api/find_paths": resp}) as c:
        c.find_paths("r", 7, 42)
    assert resp.extensions["last_request_body"] == {"repo": "r", "src": 7, "dest": 42}


def test_auto_complete_posts_prefix():
    resp = httpx.Response(200, json={"completions": [{"name": "Foo"}, {"name": "FooBar"}]})
    with _client_with({"POST /api/auto_complete": resp}) as c:
        out = c.auto_complete("r", "Foo")
    assert resp.extensions["last_request_body"] == {"repo": "r", "prefix": "Foo"}
    assert "completions" in out


def test_find_symbol_filters_for_exact_match():
    resp = httpx.Response(
        200,
        json={"completions": [
            {"name": "Foo", "id": 1},
            {"name": "FooBar", "id": 2},
            {"name": "Foo", "id": 3},
        ]},
    )
    with _client_with({"POST /api/auto_complete": resp}) as c:
        out = c.find_symbol("r", "Foo")
    assert len(out) == 2
    assert all(item["name"] == "Foo" for item in out)


def test_note_edit_calls_analyze_folder_and_reports_path():
    resp = httpx.Response(200, json={"status": "ok"})
    with _client_with({"POST /api/analyze_folder": resp}) as c:
        out = c.note_edit("r", "/work/repo/x/y.py")
    assert out == {"ok": True, "reindexed": "/work/repo/x/y.py"}
    assert resp.extensions["last_request_body"]["path"] == "/work/repo/x"  # os.path.dirname of /work/repo/x/y.py


def test_note_edit_returns_error_dict_on_http_failure():
    resp = httpx.Response(500, json={"error": "boom"})
    with _client_with({"POST /api/analyze_folder": resp}) as c:
        out = c.note_edit("r", "/work/repo/x.py")
    assert out["ok"] is False
    assert "error" in out


def test_client_sends_bearer_token():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    with CodeGraphClient(base_url="http://test", token="secret", transport=transport) as c:
        c.graph_entities("r")
    assert captured["auth"] == "Bearer secret"


def test_4xx_raises():
    resp = httpx.Response(401, json={"detail": "Unauthorized"})
    with _client_with({"GET /api/graph_entities": resp}) as c:
        with pytest.raises(httpx.HTTPStatusError):
            c.graph_entities("r")
