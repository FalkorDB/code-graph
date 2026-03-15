import redis
import pytest
import api.index
from api import Project
from starlette.testclient import TestClient

@pytest.fixture()
def client():
    redis.Redis().flushall()
    return TestClient(api.index.app)

def test_repo_info(client):
    # Start with an empty DB
    response = client.post("/api/repo_info", json={ "repo": "GraphRAG-SDK" })
    status   = response.json()["status"]

    # Expecting an empty response
    assert status == "Missing repository \"GraphRAG-SDK\""

    # Process Git repository
    proj = Project.from_git_repository("https://github.com/FalkorDB/GraphRAG-SDK")
    proj.analyze_sources()
    proj.process_git_history()

    # Reissue list_commits request
    response = client.post("/api/repo_info", json={ "repo": "GraphRAG-SDK" })
    data     = response.json()
    status   = data["status"]
    info     = data["info"]

    # Expecting an empty response
    assert status == "success"
    assert 'edge_count' in info
    assert 'node_count' in info
    assert info['repo_url'] == 'https://github.com/FalkorDB/GraphRAG-SDK'


def test_repo_info_public_access(monkeypatch):
    """Public access is granted when CODE_GRAPH_PUBLIC=1."""
    monkeypatch.setenv("CODE_GRAPH_PUBLIC", "1")
    client = TestClient(api.index.app, raise_server_exceptions=False)
    response = client.post("/api/repo_info", json={"repo": "nonexistent"})
    # Auth passed (not 401); endpoint may error without a database backend
    assert response.status_code != 401


def test_repo_info_token_required(monkeypatch):
    """When SECRET_TOKEN is set and CODE_GRAPH_PUBLIC != 1, auth is enforced."""
    monkeypatch.setattr(api.index, "SECRET_TOKEN", "test-secret")
    monkeypatch.delenv("CODE_GRAPH_PUBLIC", raising=False)

    # Without auth header → 401
    client = TestClient(api.index.app)
    response = client.post("/api/repo_info", json={"repo": "nonexistent"})
    assert response.status_code == 401

    # With valid auth header → not 401
    client = TestClient(api.index.app, raise_server_exceptions=False)
    response = client.post("/api/repo_info", json={"repo": "nonexistent"},
                           headers={"Authorization": "Bearer test-secret"})
    assert response.status_code != 401

