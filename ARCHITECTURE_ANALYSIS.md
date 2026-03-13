# CodeGraph FastAPI Backend - Architecture Analysis

## Executive Summary

CodeGraph currently exposes a **FastAPI** backend from `api.index:app` and serves the built React UI from the same process when `app/dist` exists.

The framework-specific HTTP code is concentrated in `api/index.py`. Most of the backend domain modules (`graph.py`, `project.py`, `analyzers/`, `git_utils/`, `info.py`, `llm.py`) are reusable Python components that do not depend on FastAPI.

## 1. Backend Layout

```
api/
├── __init__.py                     # Public package exports
├── index.py                        # FastAPI app, auth dependencies, routes, SPA serving
├── graph.py                        # FalkorDB graph access (sync + async helpers)
├── llm.py                          # GraphRAG + LiteLLM chat integration
├── info.py                         # Repository metadata stored in Redis/FalkorDB
├── project.py                      # Clone/local repo analysis orchestration
├── auto_complete.py                # Prefix search helper
├── prompts.py                      # Chat/Cypher prompt templates
│
├── analyzers/
│   ├── analyzer.py                 # Abstract analyzer base class
│   ├── source_analyzer.py          # File scanning + analyzer dispatch
│   ├── python/analyzer.py          # Python analyzer
│   ├── java/analyzer.py            # Java analyzer
│   ├── csharp/analyzer.py          # C# analyzer
│   └── c/analyzer.py               # Present in tree, but not registered
│
├── entities/                       # Entity/File wrappers and encoders
├── git_utils/                      # Git history graph and repo utilities
└── code_coverage/                  # Coverage helpers
```

## 2. HTTP Layer (`api/index.py`)

### 2.1 Application and routing

- The backend app is `FastAPI()`.
- All API routes are mounted under `/api/...`.
- A catch-all route serves static files from `app/dist` and falls back to `index.html` for the React SPA.

### 2.2 Authentication dependencies

`api/index.py` defines two FastAPI dependencies:

- `public_or_auth`: used by read-only endpoints. If `CODE_GRAPH_PUBLIC=1`, the request is allowed without auth; otherwise it checks the `Authorization` header against `SECRET_TOKEN`.
- `token_required`: used by mutating endpoints and always checks the `Authorization` header against `SECRET_TOKEN`.

The current `_verify_token()` helper also treats a missing `SECRET_TOKEN` as allowing requests with no `Authorization` header.

### 2.3 Request models

The API uses Pydantic request models for POST bodies, including:

- `RepoRequest`
- `NeighborsRequest`
- `AutoCompleteRequest`
- `FindPathsRequest`
- `ChatRequest`
- `AnalyzeFolderRequest`
- `AnalyzeRepoRequest`
- `SwitchCommitRequest`

### 2.4 Endpoint inventory

**Read endpoints** (`public_or_auth`):

- `GET /api/graph_entities`
- `POST /api/get_neighbors`
- `POST /api/auto_complete`
- `GET /api/list_repos`
- `POST /api/repo_info`
- `POST /api/find_paths`
- `POST /api/chat`
- `POST /api/list_commits`

**Mutating endpoints** (`token_required`):

- `POST /api/analyze_folder`
- `POST /api/analyze_repo`
- `POST /api/switch_commit`

### 2.5 Async behavior

The FastAPI handlers are `async def`, but several heavy operations are still blocking and are moved off the event loop with `asyncio.get_running_loop().run_in_executor(...)`:

- local folder analysis
- repository clone + analysis
- LLM chat work
- commit switching

## 3. Domain Modules

### 3.1 `graph.py`

`Graph` is the core FalkorDB interface used for code-graph mutations and queries. It also exposes helpers such as:

- `get_sub_graph()`
- `get_neighbors()`
- `add_entity()`
- `connect_entities()`
- `find_paths()`
- `stats()`
- backlog helpers used during git-history processing

Async route handlers use `AsyncGraphQuery` and `async_get_repos()` for non-blocking access patterns.

### 3.2 `project.py`

`Project` represents either:

- a cloned git repository via `Project.from_git_repository(url)`, or
- a local repository via `Project.from_local_repository(path)`.

Its two main orchestration steps are:

- `analyze_sources(ignore)`
- `process_git_history(ignore)`

### 3.3 `analyzers/source_analyzer.py`

`SourceAnalyzer` walks the repository tree, picks a registered analyzer by file extension, and builds the code graph.

Registered analyzers in the current code:

- `.py` -> `PythonAnalyzer`
- `.java` -> `JavaAnalyzer`
- `.cs` -> `CSharpAnalyzer`

The C analyzer source exists, but `.c` and `.h` registrations are commented out.

### 3.4 `git_utils/`

Git history is modeled as a separate FalkorDB graph per repository (for example `{repo_name}_git`).

Key pieces:

- `GitGraph` / `AsyncGitGraph`
- `build_commit_graph(...)`
- `switch_commit(...)`
- helper functions for diff classification and ignore checks

### 3.5 `info.py`

Repository metadata is stored via Redis-compatible access backed by FalkorDB connection settings. Stored fields include:

- `repo_url`
- `commit`

### 3.6 `llm.py`

Chat requests use GraphRAG-SDK with LiteLLM:

- default `MODEL_NAME` is `gemini/gemini-flash-lite-latest`
- the backend creates a `KnowledgeGraph` bound to the repository graph
- `ask()` offloads the synchronous chat session call to a worker thread

## 4. Runtime and Environment

### 4.1 Local development

Typical backend dev command:

```bash
uv run uvicorn api.index:app --host 127.0.0.1 --port 5000 --reload
```

Typical frontend dev command:

```bash
cd app && npm run dev
```

`app/vite.config.ts` proxies `/api` requests to `http://127.0.0.1:5000` during frontend development.

### 4.2 Production/container startup

The checked-in production entrypoints use Uvicorn, not Flask:

- `make run-prod`
- `start.sh`
- Docker image entrypoint (`/start.sh`)

### 4.3 Important environment variables

- `FALKORDB_HOST`
- `FALKORDB_PORT`
- `FALKORDB_USERNAME`
- `FALKORDB_PASSWORD`
- `SECRET_TOKEN`
- `CODE_GRAPH_PUBLIC`
- `ALLOWED_ANALYSIS_DIR`
- `MODEL_NAME`
- provider-specific LiteLLM credential(s), such as `GEMINI_API_KEY` for the default model

## 5. Storage Model

### 5.1 Code graph

The main repository graph lives in FalkorDB and contains entities such as:

- `File`
- `Class`
- `Function`
- `Interface`

Relationships include:

- `DEFINES`
- `CALLS`
- `EXTENDS`
- `IMPLEMENTS`

### 5.2 Git graph

Commit history is stored in a second graph named `{repo_name}_git`, with commit metadata and parent/child edges.

### 5.3 Repository metadata

Repository URL and current commit are stored in Redis-style hashes keyed as `{repo_name}_info`.

## 6. Request Flows

### 6.1 `POST /api/analyze_repo`

1. FastAPI validates the request body with `AnalyzeRepoRequest`.
2. `token_required` checks the `Authorization` header.
3. `Project.from_git_repository()` clones the repo locally.
4. `analyze_sources()` builds the code graph.
5. `process_git_history()` builds the repository's git graph.
6. The endpoint returns `{"status": "success"}`.

### 6.2 `POST /api/chat`

1. FastAPI validates `repo` and `msg`.
2. `public_or_auth` enforces auth/public rules.
3. `ask()` creates a GraphRAG chat session for the repository graph.
4. LiteLLM generates Cypher and a natural-language response.
5. The endpoint returns `{"status": "success", "response": ...}`.

## 7. Key Takeaways

- The backend is now FastAPI + Uvicorn, not Flask.
- All public API paths are under `/api/...`.
- The React app can be served by the backend from `app/dist`.
- Most backend logic remains framework-agnostic and reusable.
- Supported analyzers are currently Python, Java, and C#.
