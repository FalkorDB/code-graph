import redis
import pytest
import api.index
from pathlib import Path
from tests.index import create_app
from api import Project
from starlette.testclient import TestClient

@pytest.fixture()
def app():
    app = create_app()

    # other setup can go here
    redis.Redis().flushall()

    yield app

    # clean up / reset resources here

@pytest.fixture()
def client(app):
    return TestClient(app)

def test_list_repos(client):
    # Start with an empty DB
    response     = client.get("/api/list_repos").json()
    status       = response["status"]
    repositories = response["repositories"]

    # Expecting an empty response
    assert status == "success"
    assert repositories == []

    # Process a local repository
    path = Path(__file__).absolute()
    path = path.parent.parent / "git_repo"

    proj = Project.from_local_repository(path)

    proj.analyze_sources()
    proj.process_git_history()

    # Reissue list_repos request
    response     = client.get("/api/list_repos").json()
    status       = response["status"] 
    repositories = response["repositories"]

    # Expecting an empty response
    assert status == "success"
    assert repositories == ['git_repo']


def test_list_repos_with_auth(monkeypatch):
    """Authenticated request succeeds when SECRET_TOKEN is set."""
    monkeypatch.setattr(api.index, "SECRET_TOKEN", "test-secret")
    monkeypatch.delenv("CODE_GRAPH_PUBLIC", raising=False)
    monkeypatch.setattr(api.index, "get_repos", lambda: ["fake-repo"])
    client = TestClient(api.index.app)
    response = client.get("/api/list_repos",
                          headers={"Authorization": "Bearer test-secret"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["repositories"] == ["fake-repo"]


def test_list_repos_unauthorized(monkeypatch):
    """Request without auth gets 401 when SECRET_TOKEN is set."""
    monkeypatch.setattr(api.index, "SECRET_TOKEN", "test-secret")
    monkeypatch.delenv("CODE_GRAPH_PUBLIC", raising=False)
    client = TestClient(api.index.app)
    response = client.get("/api/list_repos")
    assert response.status_code == 401
