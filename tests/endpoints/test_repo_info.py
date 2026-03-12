import redis
import pytest
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
    status   = response.json()["status"] 
    info     = response.json()["info"]

    # Expecting an empty response
    assert status == "success"
    assert 'edge_count' in info
    assert 'node_count' in info
    assert info['repo_url'] == 'https://github.com/FalkorDB/GraphRAG-SDK'

