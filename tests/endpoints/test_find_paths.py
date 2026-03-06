import os
import redis
import pytest
from pathlib import Path
from index import create_app
from api import Project
from falkordb import FalkorDB, Path, Node, QueryResult

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

def test_find_paths(client):
    # Start with an empty DB
    response = client.post("/find_paths", json={"repo": "GraphRAG-SDK", "src": 0, "dest": 0}).json
    status   = response["status"] 

    # Expecting an error
    assert status == "Missing project GraphRAG-SDK"

    # Process Git repository
    proj = Project.from_git_repository("https://github.com/FalkorDB/GraphRAG-SDK")
    proj.analyze_sources()

    # Re-issue with invalid src node id
    response = client.post("/find_paths", json={"repo": "GraphRAG-SDK", "src": 'invalid', "dest": 0}).json
    status   = response["status"]
    assert status == "src node id must be int"

    # Re-issue with invalid dest node id
    response = client.post("/find_paths", json={"repo": "GraphRAG-SDK", "src": 0, "dest": 'invalid'}).json
    status   = response["status"]
    assert status == "dest node id must be int"

    # Find src and dest nodes that are at least 3 hops apart
    db = FalkorDB(host=os.getenv('FALKORDB_HOST', 'localhost'),
                  port=os.getenv('FALKORDB_PORT', 6379),
                  username=os.getenv('FALKORDB_USERNAME', None),
                  password=os.getenv('FALKORDB_PASSWORD', None))
    g = db.select_graph("GraphRAG-SDK")
    q = """MATCH (a:Function)-[:CALLS*3..5]->(b:Function)
           RETURN ID(a), ID(b)
           LIMIT 1"""

    result_set = g.query(q).result_set
    src_id     = result_set[0][0]
    dest_id    = result_set[0][1]

    # Re-issue with none existing node id
    response = client.post("/find_paths", json={
        "repo": "GraphRAG-SDK",
        "src": src_id,
        "dest": dest_id}).json

    status = response["status"]
    paths  = response["paths"]

    for p in paths:
        assert p[0]['id']  == src_id
        assert p[-1]['id'] == dest_id
        assert len(p) % 2 == 1
        assert len(p) >= 3

