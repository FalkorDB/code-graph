import redis
import pytest
from pathlib import Path
from index import create_app
from api import Project

@pytest.fixture()
def app():
    app = create_app()
    app.config.update({
        "TESTING": True,
    })

    # other setup can go here
    redis.Redis().flushall()

    yield app

    # clean up / reset resources here

@pytest.fixture()
def client(app):
    return app.test_client()

@pytest.fixture()
def runner(app):
    return app.test_cli_runner()

def test_graph_entities(client):
    # Start with an empty DB
    response = client.get("/get_neighbors?repo=GraphRAG-SDK&node_id=0").json
    status   = response["status"] 

    # Expecting an error
    assert status == "Missing project GraphRAG-SDK"

    # Process Git repository
    proj = Project.from_git_repository("https://github.com/FalkorDB/GraphRAG-SDK")
    proj.analyze_sources()

    # Re-issue with invalid node id
    response = client.get("/get_neighbors?repo=GraphRAG-SDK&node_id=invalid").json
    status   = response["status"]
    assert status == "Invalid node ID. It must be an integer."

    # Re-issue with none existing node id
    response = client.get("/get_neighbors?repo=GraphRAG-SDK&node_id=99999999").json
    status    = response["status"]
    neighbors = response["neighbors"]

    assert status == "success"
    assert neighbors["nodes"] == []
    assert neighbors["edges"] == []

    # Re-issue with valid node id
    response  = client.get("/get_neighbors?repo=GraphRAG-SDK&node_id=0").json
    status    = response["status"] 
    neighbors = response["neighbors"]
    nodes     = neighbors["nodes"]
    edges     = neighbors["edges"]

    assert status == "success"
    assert len(nodes) > 0 and len(nodes) < 1000
    assert len(edges) > 0 and len(edges) < 1000
