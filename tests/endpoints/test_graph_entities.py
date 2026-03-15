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
    response = client.get("/api/graph_entities?repo=GraphRAG-SDK").json()
    status   = response["status"] 

    # Expecting an error
    assert status == "Missing project GraphRAG-SDK"

    # Process Git repository
    proj = Project.from_git_repository("https://github.com/FalkorDB/GraphRAG-SDK")
    proj.analyze_sources()

    # Re-issue graph_entities request
    response = client.get("/api/graph_entities?repo=GraphRAG-SDK").json()
    status   = response["status"] 
    entities = response["entities"]
    nodes    = entities["nodes"]
    edges    = entities["edges"]

    assert status == "success"
    assert len(nodes) > 10 and len(nodes) < 1000
    assert len(edges) > 10 and len(edges) < 1000
