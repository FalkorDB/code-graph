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

def test_list_commits(client):
    # Start with an empty DB
    response = client.post("/list_commits", json={ "repo": "git_repo" })
    status   = response.json["status"] 
    commits  = response.json["commits"]

    # Expecting an empty response
    assert status == "success"
    assert commits == []

    # Process a local repository
    path = Path(__file__).absolute()
    path = path.parent.parent / "git_repo"

    proj = Project.from_local_repository(path)

    proj.analyze_sources()
    proj.process_git_history()

    # Reissue list_commits request
    response = client.post("/list_commits", json={ "repo": "git_repo" })
    status   = response.json["status"] 
    commits  = response.json["commits"]

    expected = [
        {'author': 'Roi Lipman', 'date': 1729068452, 'hash': 'fac1698da4ee14c215316859e68841ae0b0275b0', 'message': 'Initial commit\n'},
        {'author': 'Roi Lipman', 'date': 1729068481, 'hash': 'c4332d05bc1b92a33012f2ff380b807d3fbb9c2e', 'message': 'modified a.py\n'},
        {'author': 'Roi Lipman', 'date': 1729068506, 'hash': '5ec6b14612547393e257098e214ae7748ed12c50', 'message': 'added both b.py and c.py\n'},
        {'author': 'Roi Lipman', 'date': 1729068530, 'hash': 'df8d021dbae077a39693c1e76e8438006d62603e', 'message': 'removed b.py\n'}
    ]

    # Expecting an empty response
    assert status == "success"
    assert commits == expected

