<div align="center">

# CodeGraph - Knowledge Graph Visualization Tool

**Visualize codebases as knowledge graphs to analyze dependencies, detect bottlenecks, and optimize projects.**

Connect and ask questions: [![Discord](https://img.shields.io/badge/Discord-%235865F2.svg?&logo=discord&logoColor=white)](https://discord.gg/b32KEzMzce)

[![Try Free](https://img.shields.io/badge/Try%20Free-FalkorDB%20Cloud-FF8101?labelColor=FDE900&link=https://app.falkordb.cloud)](https://app.falkordb.cloud)
[![Dockerhub](https://img.shields.io/docker/pulls/falkordb/falkordb?label=Docker)](https://hub.docker.com/r/falkordb/falkordb/)

![Alt Text](https://res.cloudinary.com/dhd0k02an/image/upload/v1739719361/FalkorDB_-_Github_-_readme_jr6scy.gif)

**[Live Demo](https://code-graph.falkordb.com/)**

</div>

## Project Structure

```
code-graph/
├── api/                  # Python backend (FastAPI)
│   ├── index.py          # FastAPI app, auth deps, API routes, SPA serving
│   ├── graph.py          # FalkorDB graph operations
│   ├── llm.py            # GraphRAG + LiteLLM chat integration
│   ├── project.py        # Repository cloning and analysis orchestration
│   ├── info.py           # Repository metadata stored in Redis/FalkorDB
│   ├── prompts.py        # LLM system and prompt templates
│   ├── cli.py            # cgraph CLI tool (typer)
│   ├── auto_complete.py  # Prefix search helper
│   ├── analyzers/        # Source analyzers (Python, Java, C#)
│   ├── entities/         # Graph/entity models
│   ├── git_utils/        # Git history graph utilities
│   └── code_coverage/    # Coverage utilities
├── app/                  # React frontend (Vite)
│   ├── src/              # Frontend source code
│   ├── public/           # Static assets
│   ├── package.json      # Frontend dependencies and scripts
│   ├── vite.config.ts    # Vite config and /api proxy for dev mode
│   └── tsconfig*.json    # TypeScript config
├── skills/code-graph/    # Claude Code skill for CLI-driven indexing/querying
├── tests/                # Backend/unit and endpoint tests
├── e2e/                  # End-to-end helpers and Playwright assets
├── Dockerfile            # Unified container image
├── docker-compose.yml    # Local FalkorDB + app stack
├── Makefile              # Common dev/build/test commands
├── start.sh              # Container entrypoint
├── pyproject.toml        # Python package and dependency config
└── .env.template         # Example environment variables
```

## Running Locally

### Prerequisites

- Python `>=3.12,<3.14`
- Node.js 20+
- [`uv`](https://docs.astral.sh/uv/)
- A FalkorDB instance (local or cloud)

### 1. Start FalkorDB

**Option A:** Free cloud instance at [app.falkordb.cloud](https://app.falkordb.cloud/signup)

**Option B:** Run locally with Docker:

```bash
docker run -p 6379:6379 -it --rm falkordb/falkordb
```

### 2. Configure environment variables

Copy the template and adjust it for your setup:

```bash
cp .env.template .env
```

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `FALKORDB_HOST` | FalkorDB hostname | No | `localhost` |
| `FALKORDB_PORT` | FalkorDB port | No | `6379` |
| `FALKORDB_USERNAME` | Optional FalkorDB username | No | empty |
| `FALKORDB_PASSWORD` | Optional FalkorDB password | No | empty |
| `SECRET_TOKEN` | Token checked by protected endpoints | No | empty |
| `CODE_GRAPH_PUBLIC` | Set `1` to skip auth on read-only endpoints | No | `0` |
| `ALLOWED_ANALYSIS_DIR` | Root path allowed for `/api/analyze_folder` | No | repository root |
| `MODEL_NAME` | LiteLLM model used by `/api/chat` | No | `gemini/gemini-flash-lite-latest` |
| `HOST` | Optional Uvicorn bind host for `start.sh`/`make run-*` | No | `0.0.0.0` or `127.0.0.1` depending on command |
| `PORT` | Optional Uvicorn bind port for `start.sh`/`make run-*` | No | `5000` |

The chat endpoint also needs the provider credential expected by your chosen `MODEL_NAME`. The default model is Gemini, so set `GEMINI_API_KEY` unless you switch to a different LiteLLM provider/model.

### Authentication behavior

- Send `Authorization: Bearer <SECRET_TOKEN>` (or the raw token string) when `SECRET_TOKEN` is configured.
- Read endpoints use the `public_or_auth` dependency.
- Mutating endpoints (`/api/analyze_folder`, `/api/analyze_repo`, `/api/switch_commit`) use the `token_required` dependency.
- If `SECRET_TOKEN` is unset, the current implementation accepts requests without an `Authorization` header.
- Setting `CODE_GRAPH_PUBLIC=1` makes the read-only endpoints public even when `SECRET_TOKEN` is configured.

### 3. Install dependencies

```bash
# Install backend dependencies
uv sync --all-extras

# Install frontend dependencies
npm install --prefix ./app

# Optional: install Playwright dependencies from the repo root
npm install
```

If you do not use `uv`, `pip install -e ".[test]"` also installs the backend package and test dependencies.

### 4. Run the app

**Backend API with auto-reload:**

```bash
uv run uvicorn api.index:app --host 127.0.0.1 --port 5000 --reload
```

**Frontend hot-reload with Vite:**

```bash
# Terminal 1: backend API
uv run uvicorn api.index:app --host 127.0.0.1 --port 5000 --reload

# Terminal 2: Vite dev server
cd app && npm run dev
```

The Vite dev server runs on `http://localhost:3000` and proxies `/api/*` requests to `http://127.0.0.1:5000`.

**Single-process built frontend + backend:**

```bash
npm --prefix ./app run build
uv run uvicorn api.index:app --host 0.0.0.0 --port 5000
```

In this mode, the FastAPI app serves the built React SPA from `app/dist` on `http://localhost:5000`.

### Using Make

```bash
make install       # Install backend + frontend dependencies
make install-cli   # Install cgraph CLI entry point
make build-dev     # Build frontend in development mode
make build-prod    # Build frontend for production
make run-dev       # Build dev frontend + run Uvicorn with reload
make run-prod      # Build prod frontend + run Uvicorn
make test          # Run backend pytest suite
make lint          # Run Ruff + frontend type-check
make e2e           # Run Playwright tests from repo root
make clean         # Remove build/test artifacts
```

`make test` currently points at the right backend test entrypoint, but some legacy analyzer/git-history tests still need maintenance before the suite passes on a clean checkout.

## CLI Tool (`cgraph`)

CodeGraph includes a CLI tool for indexing codebases and querying the knowledge graph directly from the terminal. All output is JSON (to stdout), with status messages on stderr.

### Install

```bash
# Install from PyPI (recommended for end users)
pipx install falkordb-code-graph

# Or with pip
pip install falkordb-code-graph
```

For development (from a local clone):

```bash
make install-cli
# or
uv pip install -e .
```

### Usage

```bash
# Ensure FalkorDB is running (auto-starts a Docker container if needed)
cgraph ensure-db

# Index the current project
cgraph index . --ignore node_modules --ignore .git --ignore venv --ignore __pycache__

# Index a remote repository
cgraph index-repo https://github.com/user/repo --ignore node_modules

# List indexed repos
cgraph list

# Search for entities by name prefix
cgraph search parse_config

# Explore relationships (what does node 42 call?)
cgraph neighbors 42 --rel CALLS

# Find call-chain paths between two nodes
cgraph paths 42 99

# Show repo statistics
cgraph info
```

The `--repo` flag defaults to the current directory name. Run `cgraph --help` for full details.

### Claude Code Skill

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skill is included in `skills/code-graph/`. Install it with:

```bash
npx skills add FalkorDB/code-graph
```

Then ask Claude things like *"what functions call analyze_sources?"* or *"find the dependency chain between parse_config and send_request"* — it will handle the indexing and querying automatically.

## Running with Docker

### Using Docker Compose

```bash
docker compose up --build
```

This starts FalkorDB and the CodeGraph app together. The checked-in compose file sets `CODE_GRAPH_PUBLIC=1` for the app service.

### Using Docker directly

```bash
docker build -t code-graph .

docker run -p 5000:5000 \
  -e FALKORDB_HOST=host.docker.internal \
  -e FALKORDB_PORT=6379 \
  -e MODEL_NAME=gemini/gemini-flash-lite-latest \
  -e GEMINI_API_KEY=<YOUR_GEMINI_API_KEY> \
  -e SECRET_TOKEN=<YOUR_SECRET_TOKEN> \
  code-graph
```

## Creating a Code Graph

### Analyze a local folder

`analyze_folder` only accepts paths under `ALLOWED_ANALYSIS_DIR` (defaults to the repository root unless you override it).

```bash
curl -X POST http://127.0.0.1:5000/api/analyze_folder \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_SECRET_TOKEN>" \
  -d '{"path": "<FULL_PATH_TO_FOLDER>", "ignore": [".github", ".git"]}'
```

### Analyze a Git repository

```bash
curl -X POST http://127.0.0.1:5000/api/analyze_repo \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_SECRET_TOKEN>" \
  -d '{"repo_url": "https://github.com/user/repo", "ignore": [".github", ".git"]}'
```

### List indexed repositories

```bash
curl http://127.0.0.1:5000/api/list_repos
```

## Supported Languages

`api/analyzers/source_analyzer.py` currently enables these analyzers:

- Python (`.py`)
- Java (`.java`)
- C# (`.cs`)

A C analyzer exists in the source tree, but it is commented out and is not currently registered.

## API Endpoints

### Read endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/list_repos` | List all indexed repositories |
| GET | `/api/graph_entities?repo=<name>` | Fetch a subgraph for a repository |
| POST | `/api/get_neighbors` | Return neighboring nodes for the provided IDs |
| POST | `/api/auto_complete` | Prefix-search indexed entities |
| POST | `/api/repo_info` | Return repository stats and saved metadata |
| POST | `/api/find_paths` | Find paths between two graph nodes |
| POST | `/api/chat` | Ask questions over the code graph via GraphRAG |
| POST | `/api/list_commits` | List commits from the repository's git graph |

### Mutating endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/analyze_folder` | Analyze a local source folder |
| POST | `/api/analyze_repo` | Clone and analyze a git repository |
| POST | `/api/switch_commit` | Switch the indexed repository to a specific commit |

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

Copyright FalkorDB Ltd. 2025
