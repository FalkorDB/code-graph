""" Main API module for CodeGraph. """
import os
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from api.analyzers.source_analyzer import SourceAnalyzer
from api.git_utils import git_utils
from api.git_utils.git_graph import GitGraph
from api.graph import Graph, get_repos, graph_exists
from api.info import get_repo_info
from api.llm import ask
from api.project import Project
from .auto_complete import prefix_search

# Load environment variables from .env file
load_dotenv()

# Configure the logger
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authentication helpers
# ---------------------------------------------------------------------------

SECRET_TOKEN = os.getenv('SECRET_TOKEN')

def _verify_token(token: str | None) -> bool:
    """Verify the token provided in the request."""
    if token is not None and token.startswith("Bearer "):
        token = token[len("Bearer "):]
    return token == SECRET_TOKEN or (token is None and SECRET_TOKEN is None)

def public_or_auth(authorization: str | None = Header(None)):
    """Dependency: skip auth when CODE_GRAPH_PUBLIC=1, otherwise require token."""
    if os.environ.get("CODE_GRAPH_PUBLIC", "0") == "1":
        return
    if not _verify_token(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")

def token_required(authorization: str | None = Header(None)):
    """Dependency: always require a valid token."""
    if not _verify_token(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")

# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class RepoRequest(BaseModel):
    repo: str

class NeighborsRequest(BaseModel):
    repo: str
    node_ids: list[int]

class AutoCompleteRequest(BaseModel):
    repo: str
    prefix: str

class FindPathsRequest(BaseModel):
    repo: str
    src: int
    dest: int

class ChatRequest(BaseModel):
    repo: str
    msg: str

class AnalyzeFolderRequest(BaseModel):
    path: str
    ignore: list[str] = []

class AnalyzeRepoRequest(BaseModel):
    repo_url: str
    ignore: list[str] = []

class SwitchCommitRequest(BaseModel):
    repo: str
    commit: str

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

STATIC_DIR = (Path(__file__).resolve().parent.parent / "app" / "dist").resolve()

# Allowed base directory for local folder analysis (defaults to project root)
ALLOWED_ANALYSIS_DIR = Path(
    os.getenv("ALLOWED_ANALYSIS_DIR",
              str(Path(__file__).resolve().parent.parent))
).resolve()

app = FastAPI()

# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get('/api/graph_entities')
def graph_entities(repo: str = Query(None), _=Depends(public_or_auth)):
    """Fetch sub-graph entities from a given repository."""

    if not repo:
        logging.error("Missing 'repo' parameter in request.")
        return JSONResponse({"status": "Missing 'repo' parameter"}, status_code=400)

    if not graph_exists(repo):
        logging.error("Missing project %s", repo)
        return JSONResponse({"status": f"Missing project {repo}"}, status_code=400)

    try:
        g = Graph(repo)
        sub_graph = g.get_sub_graph(500)

        logging.info("Successfully retrieved sub-graph for repo: %s", repo)
        return {"status": "success", "entities": sub_graph}

    except Exception as e:
        logging.exception("Error retrieving sub-graph for repo '%s': %s", repo, e)
        return JSONResponse({"status": "Internal server error"}, status_code=500)


@app.post('/api/get_neighbors')
def get_neighbors(data: NeighborsRequest, _=Depends(public_or_auth)):
    """Get neighbors of a nodes list in the graph."""

    if not graph_exists(data.repo):
        logging.error("Missing project %s", data.repo)
        return JSONResponse({"status": f"Missing project {data.repo}"}, status_code=400)

    g = Graph(data.repo)
    neighbors = g.get_neighbors(data.node_ids)

    logging.info("Successfully retrieved neighbors for node IDs %s in repo '%s'.",
                 data.node_ids, data.repo)
    return {"status": "success", "neighbors": neighbors}


@app.post('/api/auto_complete')
def auto_complete(data: AutoCompleteRequest, _=Depends(public_or_auth)):
    """Process auto-completion requests for a repository based on a prefix."""

    if not graph_exists(data.repo):
        return JSONResponse({"status": f"Missing project {data.repo}"}, status_code=400)

    completions = prefix_search(data.repo, data.prefix)
    return {"status": "success", "completions": completions}


@app.get('/api/list_repos')
def list_repos(_=Depends(public_or_auth)):
    """List all available repositories."""

    repos = get_repos()
    return {"status": "success", "repositories": repos}


@app.post('/api/repo_info')
def repo_info(data: RepoRequest, _=Depends(public_or_auth)):
    """Retrieve information about a specific repository."""

    g = Graph(data.repo)
    stats = g.stats()
    info = get_repo_info(data.repo)

    if stats is None or info is None:
        return JSONResponse({"status": f'Missing repository "{data.repo}"'}, status_code=400)

    stats |= info
    return {"status": "success", "info": stats}


@app.post('/api/find_paths')
def find_paths(data: FindPathsRequest, _=Depends(public_or_auth)):
    """Find all paths between a source and destination node in the graph."""

    if not graph_exists(data.repo):
        logging.error("Missing project %s", data.repo)
        return JSONResponse({"status": f"Missing project {data.repo}"}, status_code=400)

    g = Graph(data.repo)
    paths = g.find_paths(data.src, data.dest)
    return {"status": "success", "paths": paths}


@app.post('/api/chat')
def chat(data: ChatRequest, _=Depends(public_or_auth)):
    """Chat with the CodeGraph language model."""

    try:
        answer = ask(data.repo, data.msg)
    except Exception as e:
        logging.exception("Chat error for repo '%s': %s", data.repo, e)
        return JSONResponse({"status": "error", "response": "Internal server error"},
                            status_code=500)

    return {"status": "success", "response": answer}


@app.post('/api/analyze_folder')
def analyze_folder(data: AnalyzeFolderRequest, _=Depends(token_required)):
    """Analyze local source code. Always requires a valid token."""

    resolved_path = Path(data.path).resolve()

    if not resolved_path.is_relative_to(ALLOWED_ANALYSIS_DIR):
        logging.error("Path '%s' is outside the allowed directory", data.path)
        return JSONResponse(
            {"status": "Invalid path: must be within the allowed analysis directory"},
            status_code=400)

    if not resolved_path.is_dir():
        logging.error("Path '%s' does not exist or is not a directory", data.path)
        return JSONResponse({"status": "Invalid path: must be an existing directory"},
                            status_code=400)

    proj_name = resolved_path.name
    g = Graph(proj_name)

    analyzer = SourceAnalyzer()
    analyzer.analyze_local_folder(str(resolved_path), g, data.ignore)

    return {"status": "success", "project": proj_name}


@app.post('/api/analyze_repo')
def analyze_repo(data: AnalyzeRepoRequest, _=Depends(token_required)):
    """Analyze a GitHub repository. Always requires a valid token."""

    logger.debug('Received repo_url: %s', data.repo_url)

    proj = Project.from_git_repository(data.repo_url)
    proj.analyze_sources(data.ignore)
    proj.process_git_history(data.ignore)

    return {"status": "success"}


@app.post('/api/switch_commit')
def switch_commit(data: SwitchCommitRequest, _=Depends(token_required)):
    """Switch a repository to a specific commit. Always requires a valid token."""

    git_utils.switch_commit(data.repo, data.commit)
    return {"status": "success"}


@app.post('/api/list_commits')
def list_commits(data: RepoRequest, _=Depends(public_or_auth)):
    """List all commits of a specified repository."""

    git_graph = GitGraph(git_utils.GitRepoName(data.repo))
    commits = git_graph.list_commits()
    return {"status": "success", "commits": commits}

# ---------------------------------------------------------------------------
# SPA static file serving (must come after API routes)
# ---------------------------------------------------------------------------

INDEX_HTML = STATIC_DIR / "index.html"

@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    """Serve React SPA — static assets or index.html catch-all."""
    file = (STATIC_DIR / full_path).resolve()
    if not file.is_relative_to(STATIC_DIR):
        return JSONResponse({"error": "Not found"}, status_code=404)
    if full_path and file.is_file():
        return FileResponse(file)
    if INDEX_HTML.is_file():
        return FileResponse(INDEX_HTML)
    return JSONResponse({"error": "Not found"}, status_code=404)