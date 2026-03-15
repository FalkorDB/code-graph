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

def test_graph_entities(client):
    # Start with an empty DB
    response = client.post("/api/get_neighbors", json={"repo": "GraphRAG-SDK", "node_ids": [0]}).json()
    status   = response["status"] 

    # Expecting an error
    assert status == "Missing project GraphRAG-SDK"

    # Process Git repository
    proj = Project.from_git_repository("https://github.com/FalkorDB/GraphRAG-SDK")
    proj.analyze_sources()

    # Re-issue with none existing node id
    response  = client.post("/api/get_neighbors", json={"repo": "GraphRAG-SDK", "node_ids": [99999999]}).json()
    status    = response["status"]
    neighbors = response["neighbors"]

    assert status == "success"
    assert neighbors["nodes"] == []
    assert neighbors["edges"] == []

    # Re-issue with valid node id
    response  = client.post("/api/get_neighbors", json={"repo": "GraphRAG-SDK", "node_ids": [0]}).json()
    status    = response["status"] 
    neighbors = response["neighbors"]
    nodes     = neighbors["nodes"]
    edges     = neighbors["edges"]

    assert status == "success"
    assert len(nodes) > 0 and len(nodes) < 1000
    assert len(edges) > 0 and len(edges) < 1000
