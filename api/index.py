""" Main API module for CodeGraph. """
import hashlib
import hmac
import os
import asyncio
import contextlib
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from api.analyzers.source_analyzer import SourceAnalyzer
from api.git_utils import git_utils
from api.git_utils.git_graph import AsyncGitGraph
from api.git_utils.incremental_update import (
    can_incrementally_update,
    fetch_remote,
    get_remote_head,
    incremental_update,
    repo_local_path,
    repo_update_lock,
)
from api.graph import Graph, AsyncGraphQuery, async_get_repos, delete_graph_if_exists
from api.info import async_get_repo_info, get_repo_commit
from api.llm import ask
from api.project import Project


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

# ---------------------------------------------------------------------------
# Webhook / poll-watcher configuration
# ---------------------------------------------------------------------------

# HMAC-SHA256 secret shared with GitHub/GitLab.  Leave unset to skip
# signature validation (not recommended for production).
WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")

# Branch whose pushes trigger incremental graph updates.
TRACKED_BRANCH: str = os.getenv("TRACKED_BRANCH", "main")

# Seconds between automatic poll checks (0 = disabled).
POLL_INTERVAL: int = int(os.getenv("POLL_INTERVAL", "60"))

# ---------------------------------------------------------------------------
# Webhook helpers
# ---------------------------------------------------------------------------

def _urls_match(stored_url: str, incoming_url: str) -> bool:
    """Return True when two repository URLs refer to the same repo.

    Normalises both URLs by stripping a trailing ``.git`` suffix and
    converting to lower-case so that, for example,
    ``https://github.com/Org/Repo`` and
    ``https://github.com/org/repo.git`` are treated as identical.
    """
    def _normalise(u: str) -> str:
        return u.rstrip("/").removesuffix(".git").lower()

    return _normalise(stored_url) == _normalise(incoming_url)


async def _find_repo_by_url(url: str) -> str | None:
    """Return the graph name for a repository that matches *url*, or ``None``."""
    repos = await async_get_repos()
    for repo_name in repos:
        info = await async_get_repo_info(repo_name)
        if info and _urls_match(info.get("repo_url", ""), url):
            return repo_name
    return None


def _webhook_auth_mode() -> str:
    if WEBHOOK_SECRET:
        return "shared-secret"
    if SECRET_TOKEN:
        return "token"
    return "disabled"


def _log_webhook_auth_mode() -> None:
    mode = _webhook_auth_mode()
    if mode == "shared-secret":
        logger.info(
            "Webhook auth mode: shared secret (GitHub HMAC or GitLab X-Gitlab-Token)"
        )
    elif mode == "token":
        logger.info("Webhook auth mode: Authorization bearer token fallback")
    else:
        logger.warning(
            "Webhook auth is not configured; /api/webhook will reject requests until "
            "WEBHOOK_SECRET or SECRET_TOKEN is set"
        )


def _authenticate_webhook_request(request: Request, body: bytes) -> None:
    """Authenticate a webhook request using the configured webhook auth mode."""
    if WEBHOOK_SECRET:
        github_signature = request.headers.get("X-Hub-Signature-256")
        gitlab_token = request.headers.get("X-Gitlab-Token")
        gitlab_event = request.headers.get("X-Gitlab-Event")
        gitlab_signature = request.headers.get("X-Gitlab-Signature")

        if github_signature:
            mac = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256)
            expected_signature = "sha256=" + mac.hexdigest()
            if not hmac.compare_digest(github_signature, expected_signature):
                raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")
            return

        if gitlab_token or gitlab_event or gitlab_signature:
            if not gitlab_token:
                raise HTTPException(
                    status_code=401,
                    detail="GitLab webhooks must include X-Gitlab-Token",
                )
            if not hmac.compare_digest(gitlab_token, WEBHOOK_SECRET):
                raise HTTPException(status_code=401, detail="Invalid GitLab webhook token")
            return

        raise HTTPException(
            status_code=401,
            detail="Missing supported webhook authentication header",
        )

    if not SECRET_TOKEN:
        logger.error(
            "Webhook auth misconfigured: set WEBHOOK_SECRET or SECRET_TOKEN before "
            "accepting webhook updates"
        )
        raise HTTPException(
            status_code=503,
            detail="Webhook authentication is not configured",
        )

    token_required(request.headers.get("Authorization"))


def _extract_repo_url(payload: dict) -> str:
    repository = payload.get("repository", {})
    project = payload.get("project", {})
    return (
        repository.get("clone_url")
        or repository.get("git_http_url")
        or project.get("git_http_url")
        or ""
    )


def _full_reindex_repository(
    repo_name: str,
    repo_path: Path,
    repo_url: str = "",
    ignore: list[str] | None = None,
    reason: str = "",
    target_sha: str | None = None,
) -> dict:
    if ignore is None:
        ignore = []

    logger.warning(
        "Falling back to a full reindex for '%s'%s",
        repo_name,
        f": {reason}" if reason else "",
    )

    with repo_update_lock(repo_name):
        delete_graph_if_exists(repo_name)
        delete_graph_if_exists(git_utils.GitRepoName(repo_name))

        if repo_path.exists():
            if target_sha:
                from pygit2.enums import CheckoutStrategy
                from pygit2.repository import Repository
                repo = Repository(str(repo_path))
                target_commit = repo.revparse_single(target_sha)
                repo.checkout_tree(target_commit.tree, strategy=CheckoutStrategy.FORCE)
                repo.set_head_detached(target_commit.id)
                logger.info("Checked out target commit %s before full reindex", target_sha[:8])
            proj = Project.from_local_repository(repo_path)
        elif repo_url:
            proj = Project.from_git_repository(repo_url)
        else:
            raise ValueError(
                f"Cannot reindex '{repo_name}': local clone is missing and no repo URL is available"
            )

        proj.analyze_sources(ignore)
        proj.process_git_history(ignore)

    return {
        "mode": "full_reindex",
        "files_added": 0,
        "files_modified": 0,
        "files_deleted": 0,
        "commit": get_repo_commit(repo_name),
    }


def _sync_repo_graph(
    repo_name: str,
    repo_path: Path,
    target_sha: str,
    *,
    before_sha: str | None = None,
    repo_url: str = "",
    ignore: list[str] | None = None,
) -> dict:
    if ignore is None:
        ignore = []

    if not repo_path.exists():
        return _full_reindex_repository(
            repo_name,
            repo_path,
            repo_url,
            ignore,
            "local clone missing",
        )

    stored_sha = get_repo_commit(repo_name)
    if not stored_sha:
        return _full_reindex_repository(
            repo_name,
            repo_path,
            repo_url,
            ignore,
            "missing stored commit bookmark",
            target_sha=target_sha,
        )

    if not can_incrementally_update(repo_path, stored_sha, target_sha, before_sha):
        return _full_reindex_repository(
            repo_name,
            repo_path,
            repo_url,
            ignore,
            (
                f"stored bookmark {stored_sha} does not align with "
                f"before={before_sha or '<none>'} and target={target_sha}"
            ),
            target_sha=target_sha,
        )

    return incremental_update(repo_name, stored_sha, target_sha, ignore)

# ---------------------------------------------------------------------------
# Background poll-watcher helpers (synchronous, run in thread-pool executor)
# ---------------------------------------------------------------------------

def _poll_repo(repo_name: str) -> None:
    """Fetch remote and apply incremental updates for *repo_name* if behind.

    This function is intentionally synchronous so it can be safely offloaded
    to ``asyncio``'s default ``ThreadPoolExecutor``.
    """
    path = repo_local_path(repo_name)
    if not path.exists():
        logger.debug("Poll: local clone not found for '%s', skipping", repo_name)
        return

    try:
        fetch_remote(path)
    except Exception as exc:
        logger.warning("Poll: git fetch failed for '%s': %s", repo_name, exc)
        return

    remote_head = get_remote_head(path, TRACKED_BRANCH)
    if not remote_head:
        return

    current_sha = get_repo_commit(repo_name)
    if current_sha:
        # Handle comparison between short (7-char) and full (40-char) SHAs: a short
        # stored SHA is a valid prefix of a full remote SHA for the same commit.
        # We only apply prefix matching when the stored SHA is shorter.
        if len(current_sha) < len(remote_head):
            up_to_date = remote_head.startswith(current_sha)
        elif len(current_sha) > len(remote_head):
            up_to_date = current_sha.startswith(remote_head)
        else:
            up_to_date = current_sha == remote_head
        if up_to_date:
            logger.debug("Poll: '%s' is up-to-date at %s", repo_name, current_sha)
            return
    else:
        logger.warning("Poll: '%s' has no stored bookmark; forcing a full reindex", repo_name)

    logger.info(
        "Poll: new commits detected for '%s' (%s -> %s), updating …",
        repo_name, current_sha, remote_head,
    )
    try:
        result = _sync_repo_graph(repo_name, path, remote_head)
        logger.info("Poll: '%s' updated — %s", repo_name, result)
    except Exception as exc:
        logger.exception(
            "Poll: incremental update failed for '%s': %s", repo_name, exc
        )


async def _poll_all_repos() -> None:
    """Check every indexed repository for new commits on the tracked branch."""
    repos = await async_get_repos()
    loop = asyncio.get_running_loop()
    for repo_name in repos:
        await loop.run_in_executor(None, _poll_repo, repo_name)


async def _poll_loop() -> None:
    """Continuously poll all repositories at the configured interval."""
    logger.info(
        "Poll-watcher started (interval=%ds, branch='%s')",
        POLL_INTERVAL, TRACKED_BRANCH,
    )
    while True:
        try:
            await _poll_all_repos()
        except Exception as exc:
            logger.exception("Poll loop error: %s", exc)
        await asyncio.sleep(POLL_INTERVAL)

# ---------------------------------------------------------------------------
# Application lifespan (starts/stops the background poll task)
# ---------------------------------------------------------------------------

@contextlib.asynccontextmanager
async def _lifespan(application: FastAPI):
    _log_webhook_auth_mode()
    poll_task = None
    if POLL_INTERVAL > 0:
        poll_task = asyncio.create_task(_poll_loop())
    yield
    if poll_task is not None:
        poll_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await poll_task

app = FastAPI(lifespan=_lifespan)

# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get('/api/graph_entities')
async def graph_entities(repo: str = Query(None), _=Depends(public_or_auth)):
    """Fetch sub-graph entities from a given repository."""

    if not repo:
        logging.error("Missing 'repo' parameter in request.")
        return JSONResponse({"status": "Missing 'repo' parameter"}, status_code=400)

    g = AsyncGraphQuery(repo)
    try:
        if not await g.graph_exists():
            logging.error("Missing project %s", repo)
            return JSONResponse({"status": f"Missing project {repo}"}, status_code=400)

        sub_graph = await g.get_sub_graph(500)

        logging.info("Successfully retrieved sub-graph for repo: %s", repo)
        return {"status": "success", "entities": sub_graph}

    except Exception as e:
        logging.exception("Error retrieving sub-graph for repo '%s': %s", repo, e)
        return JSONResponse({"status": "Internal server error"}, status_code=500)
    finally:
        await g.close()


@app.post('/api/get_neighbors')
async def get_neighbors(data: NeighborsRequest, _=Depends(public_or_auth)):
    """Get neighbors of a nodes list in the graph."""

    g = AsyncGraphQuery(data.repo)
    try:
        if not await g.graph_exists():
            logging.error("Missing project %s", data.repo)
            return JSONResponse({"status": f"Missing project {data.repo}"}, status_code=400)

        neighbors = await g.get_neighbors(data.node_ids)
    finally:
        await g.close()

    logging.info("Successfully retrieved neighbors for node IDs %s in repo '%s'.",
                 data.node_ids, data.repo)
    return {"status": "success", "neighbors": neighbors}


@app.post('/api/auto_complete')
async def auto_complete(data: AutoCompleteRequest, _=Depends(public_or_auth)):
    """Process auto-completion requests for a repository based on a prefix."""

    g = AsyncGraphQuery(data.repo)
    try:
        if not await g.graph_exists():
            return JSONResponse({"status": f"Missing project {data.repo}"}, status_code=400)

        completions = await g.prefix_search(data.prefix)
    finally:
        await g.close()
    return {"status": "success", "completions": completions}


@app.get('/api/list_repos')
async def list_repos(_=Depends(public_or_auth)):
    """List all available repositories."""

    repos = await async_get_repos()
    return {"status": "success", "repositories": repos}


@app.post('/api/repo_info')
async def repo_info(data: RepoRequest, _=Depends(public_or_auth)):
    """Retrieve information about a specific repository."""

    g = AsyncGraphQuery(data.repo)
    try:
        if not await g.graph_exists():
            return JSONResponse({"status": f'Missing repository "{data.repo}"'}, status_code=400)

        stats = await g.stats()
    finally:
        await g.close()
    info = await async_get_repo_info(data.repo)

    if info is None:
        return JSONResponse({"status": f'Missing repository "{data.repo}"'}, status_code=400)

    stats |= info
    return {"status": "success", "info": stats}


@app.post('/api/find_paths')
async def find_paths(data: FindPathsRequest, _=Depends(public_or_auth)):
    """Find all paths between a source and destination node in the graph."""

    g = AsyncGraphQuery(data.repo)
    try:
        if not await g.graph_exists():
            logging.error("Missing project %s", data.repo)
            return JSONResponse({"status": f"Missing project {data.repo}"}, status_code=400)

        paths = await g.find_paths(data.src, data.dest)
    finally:
        await g.close()
    return {"status": "success", "paths": paths}


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

    def _analyze():
        g = Graph(proj_name)
        analyzer = SourceAnalyzer()
        analyzer.analyze_local_folder(str(resolved_path), g, data.ignore)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _analyze)

    return {"status": "success", "project": proj_name}


@app.post('/api/analyze_repo')
async def analyze_repo(data: AnalyzeRepoRequest, _=Depends(token_required)):
    """Analyze a GitHub repository. Always requires a valid token."""

    logger.debug('Received repo_url: %s', data.repo_url)

    def _analyze():
        proj = Project.from_git_repository(data.repo_url)
        proj.analyze_sources(data.ignore)
        proj.process_git_history(data.ignore)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _analyze)

    return {"status": "success"}


@app.post('/api/switch_commit')
async def switch_commit(data: SwitchCommitRequest, _=Depends(token_required)):
    """Switch a repository to a specific commit. Always requires a valid token."""

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, git_utils.switch_commit, data.repo, data.commit)
    return {"status": "success"}


@app.post('/api/list_commits')
async def list_commits(data: RepoRequest, _=Depends(public_or_auth)):
    """List all commits of a specified repository."""

    git_graph = AsyncGitGraph(git_utils.GitRepoName(data.repo))
    try:
        commits = await git_graph.list_commits()
    finally:
        await git_graph.close()
    return {"status": "success", "commits": commits}


@app.post('/api/webhook')
async def webhook(request: Request):
    """Receive a GitHub/GitLab push event and trigger an incremental graph update.

    When ``WEBHOOK_SECRET`` is set the endpoint validates GitHub's
    ``X-Hub-Signature-256`` HMAC signature or GitLab's ``X-Gitlab-Token``.
    Without ``WEBHOOK_SECRET`` the endpoint falls back to the standard bearer
    token auth used by the other mutating routes.

    Only pushes to the branch configured via ``TRACKED_BRANCH`` (default
    ``main``) trigger an update; pushes to other branches are acknowledged
    with a ``200 ignored`` response so that GitHub does not retry them.

    The repository is identified by matching the payload's repository URL
    (`repository.clone_url`, `repository.git_http_url`, or `project.git_http_url`)
    against the URLs stored for already-indexed repositories.
    """
    body = await request.body()
    _authenticate_webhook_request(request, body)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    ref = payload.get("ref", "")
    before = payload.get("before", "")
    after = payload.get("after", "")
    repo_url = _extract_repo_url(payload)

    # Only process pushes to the configured tracked branch
    expected_ref = f"refs/heads/{TRACKED_BRANCH}"
    if ref != expected_ref:
        logger.debug("Webhook: ignoring push to '%s' (tracking '%s')", ref, expected_ref)
        return {"status": "ignored", "reason": f"Branch not tracked: {ref}"}

    if not before or not after or not repo_url:
        raise HTTPException(
            status_code=400,
            detail=(
                "Payload missing required fields: ref, before, after, and a repository URL "
                "(repository.clone_url, repository.git_http_url, or project.git_http_url)"
            ),
        )

    # Resolve the repository name from the stored index
    repo_name = await _find_repo_by_url(repo_url)
    if repo_name is None:
        logger.warning("Webhook: received push for unknown repo '%s'", repo_url)
        return JSONResponse(
            {"status": "error", "detail": "Repository not indexed"},
            status_code=404,
        )

    logger.info(
        "Webhook: updating '%s' from %s to %s", repo_name, before[:8], after[:8]
    )

    def _update() -> dict:
        path = repo_local_path(repo_name)
        if path.exists():
            fetch_remote(path)
        return _sync_repo_graph(
            repo_name,
            path,
            after,
            before_sha=before,
            repo_url=repo_url,
        )

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, _update)
    except Exception as exc:
        logger.exception(
            "Webhook: incremental update failed for '%s': %s", repo_name, exc
        )
        return JSONResponse(
            {"status": "error", "detail": "Incremental update failed"},
            status_code=500,
        )

    return {"status": "success", **result}

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
