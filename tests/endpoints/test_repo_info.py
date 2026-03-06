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

def test_repo_info(client):
    # Start with an empty DB
    response = client.post("/repo_info", json={ "repo": "GraphRAG-SDK" })
    status   = response.json["status"] 

    # Expecting an empty response
    assert status == "Missing repository \"GraphRAG-SDK\""

    # Process Git repository
    proj = Project.from_git_repository("https://github.com/FalkorDB/GraphRAG-SDK")
    proj.analyze_sources()
    proj.process_git_history()

    # Reissue list_commits request
    response = client.post("/repo_info", json={ "repo": "GraphRAG-SDK" })
    status   = response.json["status"] 
    info     = response.json["info"]

    # Expecting an empty response
    assert status == "success"
    assert 'edge_count' in info
    assert 'node_count' in info
    assert info['repo_url'] == 'https://github.com/FalkorDB/GraphRAG-SDK'

