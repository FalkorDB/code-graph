""" Main API module for CodeGraph. """
import os
import asyncio
import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from api.analyzers.source_analyzer import SourceAnalyzer
from api.git_utils import git_utils
from api.git_utils.git_graph import AsyncGitGraph
from api.graph import Graph, AsyncGraphQuery, async_get_repos
from api.info import async_get_repo_info
from api.llm import ask
from api.project import Project, detect_branch


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
    branch: Optional[str] = None

class NeighborsRequest(BaseModel):
    repo: str
    node_ids: list[int]
    branch: Optional[str] = None

class AutoCompleteRequest(BaseModel):
    repo: str
    prefix: str
    branch: Optional[str] = None

class FindPathsRequest(BaseModel):
    repo: str
    src: int
    dest: int
    branch: Optional[str] = None

class ChatRequest(BaseModel):
    repo: str
    msg: str
    branch: Optional[str] = None

class AnalyzeFolderRequest(BaseModel):
    path: str
    ignore: list[str] = []
    branch: Optional[str] = None

class AnalyzeRepoRequest(BaseModel):
    repo_url: str
    ignore: list[str] = []
    branch: Optional[str] = None

class SwitchCommitRequest(BaseModel):
    repo: str
    commit: str
    branch: Optional[str] = None

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
async def graph_entities(repo: str = Query(None), branch: Optional[str] = Query(None), _=Depends(public_or_auth)):
    """Fetch sub-graph entities from a given repository."""

    if not repo:
        logging.error("Missing 'repo' parameter in request.")
        return JSONResponse({"status": "Missing 'repo' parameter"}, status_code=400)

    g = AsyncGraphQuery(repo, branch=branch)
    try:
        if not await g.graph_exists():
            logging.error("Missing project %s (branch=%s)", repo, g.branch)
            return JSONResponse({"status": f"Missing project {repo}"}, status_code=400)

        sub_graph = await g.get_sub_graph(500)

        logging.info("Successfully retrieved sub-graph for repo: %s (branch=%s)", repo, g.branch)
        return {"status": "success", "branch": g.branch, "entities": sub_graph}

    except Exception as e:
        logging.exception("Error retrieving sub-graph for repo '%s': %s", repo, e)
        return JSONResponse({"status": "Internal server error"}, status_code=500)
    finally:
        await g.close()


@app.post('/api/get_neighbors')
async def get_neighbors(data: NeighborsRequest, _=Depends(public_or_auth)):
    """Get neighbors of a nodes list in the graph."""

    g = AsyncGraphQuery(data.repo, branch=data.branch)
    try:
        if not await g.graph_exists():
            logging.error("Missing project %s (branch=%s)", data.repo, g.branch)
            return JSONResponse({"status": f"Missing project {data.repo}"}, status_code=400)

        neighbors = await g.get_neighbors(data.node_ids)
    finally:
        await g.close()

    logging.info("Successfully retrieved neighbors for node IDs %s in repo '%s' (branch=%s).",
                 data.node_ids, data.repo, g.branch)
    return {"status": "success", "branch": g.branch, "neighbors": neighbors}


@app.post('/api/auto_complete')
async def auto_complete(data: AutoCompleteRequest, _=Depends(public_or_auth)):
    """Process auto-completion requests for a repository based on a prefix."""

    g = AsyncGraphQuery(data.repo, branch=data.branch)
    try:
        if not await g.graph_exists():
            return JSONResponse({"status": f"Missing project {data.repo}"}, status_code=400)

        completions = await g.prefix_search(data.prefix)
    finally:
        await g.close()
    return {"status": "success", "branch": g.branch, "completions": completions}


@app.get('/api/list_repos')
async def list_repos(_=Depends(public_or_auth)):
    """List all available repositories (returns (project, branch) pairs)."""

    repos = await async_get_repos()
    return {"status": "success", "repositories": repos}


@app.post('/api/repo_info')
async def repo_info(data: RepoRequest, _=Depends(public_or_auth)):
    """Retrieve information about a specific repository."""

    g = AsyncGraphQuery(data.repo, branch=data.branch)
    try:
        if not await g.graph_exists():
            return JSONResponse({"status": f'Missing repository "{data.repo}"'}, status_code=400)

        stats = await g.stats()
    finally:
        await g.close()
    info = await async_get_repo_info(data.repo, data.branch)

    if info is None:
        return JSONResponse({"status": f'Missing repository "{data.repo}"'}, status_code=400)

    stats |= info
    return {"status": "success", "branch": g.branch, "info": stats}


@app.post('/api/find_paths')
async def find_paths(data: FindPathsRequest, _=Depends(public_or_auth)):
    """Find all paths between a source and destination node in the graph."""

    g = AsyncGraphQuery(data.repo, branch=data.branch)
    try:
        if not await g.graph_exists():
            logging.error("Missing project %s (branch=%s)", data.repo, g.branch)
            return JSONResponse({"status": f"Missing project {data.repo}"}, status_code=400)

        paths = await g.find_paths(data.src, data.dest)
    finally:
        await g.close()
    return {"status": "success", "branch": g.branch, "paths": paths}


@app.post('/api/chat')
async def chat(data: ChatRequest, _=Depends(public_or_auth)):
    """Chat with the CodeGraph language model."""

    try:
        answer = await ask(data.repo, data.msg)
    except Exception as e:
        logging.exception("Chat error for repo '%s': %s", data.repo, e)
        return JSONResponse({"status": "error", "response": "Internal server error"},
                            status_code=500)

    return {"status": "success", "response": answer}


@app.post('/api/analyze_folder')
async def analyze_folder(data: AnalyzeFolderRequest, _=Depends(token_required)):
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
    branch = data.branch if data.branch is not None else detect_branch(resolved_path)

    def _analyze():
        g = Graph(proj_name, branch=branch)
        analyzer = SourceAnalyzer()
        analyzer.analyze_local_folder(str(resolved_path), g, data.ignore)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _analyze)

    return {"status": "success", "project": proj_name, "branch": branch}


@app.post('/api/analyze_repo')
async def analyze_repo(data: AnalyzeRepoRequest, _=Depends(token_required)):
    """Analyze a GitHub repository. Always requires a valid token."""

    logger.debug('Received repo_url: %s branch: %s', data.repo_url, data.branch)

    def _analyze():
        proj = Project.from_git_repository(data.repo_url, branch=data.branch)
        proj.analyze_sources(data.ignore)
        proj.process_git_history(data.ignore)
        return proj.branch

    loop = asyncio.get_running_loop()
    resolved_branch = await loop.run_in_executor(None, _analyze)

    return {"status": "success", "branch": resolved_branch}


@app.post('/api/switch_commit')
async def switch_commit(data: SwitchCommitRequest, _=Depends(token_required)):
    """Switch a repository to a specific commit. Always requires a valid token."""

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, git_utils.switch_commit, data.repo, data.commit, data.branch)
    return {"status": "success"}


@app.post('/api/list_commits')
async def list_commits(data: RepoRequest, _=Depends(public_or_auth)):
    """List all commits of a specified repository."""

    git_graph = AsyncGitGraph(git_utils.GitRepoName(data.repo, data.branch))
    try:
        commits = await git_graph.list_commits()
    finally:
        await git_graph.close()
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
