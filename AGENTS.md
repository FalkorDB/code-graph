# CodeGraph - Agent Instructions

Knowledge graph visualization tool for codebases. Python FastAPI backend + React/TypeScript frontend + FalkorDB graph database.

## Architecture

- **Backend** (`api/`): FastAPI, async-first. All routes in `api/index.py`. Graph ops in `api/graph.py`. LLM chat via GraphRAG in `api/llm.py`.
- **Frontend** (`app/`): React 18 + TypeScript + Vite. Tailwind CSS + Radix UI. 3D force-graph visualization (D3/Force-Graph).
- **Database**: FalkorDB (graph DB on Redis). Metadata in Redis key-value store.
- **Analyzers** (`api/analyzers/`): tree-sitter (Python), multilspy (Java, C#). Base class in `analyzer.py`, orchestrator in `source_analyzer.py`.

### Data flow

1. User submits repo URL or folder path -> backend clones/reads and analyzes via language-specific analyzers
2. Entities stored in FalkorDB (nodes: File, Class, Function; edges: DEFINES, CALLS, etc.)
3. Metadata (URL, commit) stored in Redis
4. Frontend fetches graph, renders interactive visualization
5. User can chat (GraphRAG), explore neighbors, find paths

## Directory structure

```text
api/                  # Python backend
  cli.py              # cgraph CLI tool (typer) — full version used during dev
  index.py            # FastAPI app, routes, auth, SPA serving
  graph.py            # FalkorDB graph operations (sync + async)
  llm.py              # GraphRAG + LiteLLM chat
  project.py          # Repo cloning and analysis pipeline
  info.py             # Redis metadata operations
  prompts.py          # LLM prompt templates
  auto_complete.py    # Prefix search
  analyzers/          # Language-specific code analyzers
  entities/           # Graph entity models
  git_utils/          # Git history graph construction
cli/                  # Lightweight CLI package (falkordb-cgraph)
  pyproject.toml      # Minimal deps: falkordb + typer only
  cgraph/
    main.py           # Standalone CLI commands (list, search, neighbors, paths, info, ensure-db)
app/                  # React frontend (Vite)
  src/components/     # React components (ForceGraph, chat, code-graph, etc.)
  src/lib/            # Utilities
skills/code-graph/    # Claude Code skill for code graph indexing/querying
tests/                # Pytest backend tests
  endpoints/          # API endpoint integration tests
e2e/                  # Playwright E2E tests
  seed_test_data.py   # Test data seeder
```

## Commands

```bash
make install         # Install all deps (uv sync + npm install)
make install-cli     # Install cgraph CLI entry point
make build-dev       # Build frontend (dev mode)
make build-prod      # Build frontend (production)
make run-dev         # Build dev frontend + run API with reload
make run-prod        # Build prod frontend + run API
make test            # Run pytest suite
make lint            # Ruff + TypeScript type-check
make lint-py         # Ruff only
make lint-fe         # TypeScript type-check only
make e2e             # Run Playwright tests
make clean           # Remove build artifacts
make docker-falkordb # Start FalkorDB container for testing
make docker-stop     # Stop test containers
```

### Manual commands

```bash
# Backend
uv run uvicorn api.index:app --host 127.0.0.1 --port 5000 --reload
uv run python -m pytest tests/ --verbose
uv run ruff check .

# Frontend
npm --prefix ./app run dev          # Vite dev server (port 3000, proxies /api to 5000)
npm --prefix ./app run build        # Production build
npm --prefix ./app run lint         # Type-check

# E2E
npx playwright test
```

## Conventions

### Python (backend)
- snake_case for functions/variables, PascalCase for classes
- Async-first: route handlers and most graph operations are async, though api/graph.py includes some synchronous helpers
- Auth: `public_or_auth` for read endpoints, `token_required` for mutating endpoints
- Graph labels: PascalCase (File, Class, Function). Relations: SCREAMING_SNAKE_CASE (DEFINES, CALLS)
- Linter: Ruff

### TypeScript (frontend)
- camelCase for functions/variables, PascalCase for components
- Tailwind CSS for styling
- Radix UI for headless components
- Linter: tsc (type-check only)

### General
- Python >=3.12,<3.14. Node 20+.
- Package managers: `uv` (Python), `npm` (frontend)
- Environment variables: SCREAMING_SNAKE_CASE. See `.env.template` for reference.

## Environment variables

Key variables (see `.env.template` for full list):

| Variable | Default | Purpose |
|----------|---------|---------|
| `FALKORDB_HOST` | `localhost` | Graph DB host |
| `FALKORDB_PORT` | `6379` | Graph DB port |
| `SECRET_TOKEN` | empty | API auth token |
| `CODE_GRAPH_PUBLIC` | `0` | Skip auth on read endpoints when `1` |
| `MODEL_NAME` | `gemini/gemini-flash-lite-latest` | LiteLLM model for chat |
| `ALLOWED_ANALYSIS_DIR` | repo root | Root path for analyze_folder |

## Testing

- **Backend**: `make test` runs pytest against `tests/`. Endpoint tests in `tests/endpoints/`.
- **E2E**: `make e2e` runs Playwright (Chromium + Firefox). Test data seeded via `e2e/seed_test_data.py`.
- **CI**: GitHub Actions — `build.yml` (lint + build), `playwright.yml` (E2E, 2 shards), `release-image.yml` (Docker image).

## API endpoints

### Read (public_or_auth)
- `GET /api/list_repos` — List indexed repos
- `GET /api/graph_entities?repo=<name>` — Fetch graph entities
- `POST /api/get_neighbors` — Neighboring nodes
- `POST /api/auto_complete` — Prefix search
- `POST /api/repo_info` — Repo stats/metadata
- `POST /api/find_paths` — Paths between nodes
- `POST /api/chat` — GraphRAG chat
- `POST /api/list_commits` — Git commit history

### Mutating (token_required)
- `POST /api/analyze_folder` — Analyze local folder
- `POST /api/analyze_repo` — Clone and analyze repo
- `POST /api/switch_commit` — Switch to specific commit

## CLI (`cgraph`)

Two packages provide the `cgraph` command:

**Lightweight CLI** (`falkordb-cgraph` — the recommended install for end users):

Install: `pipx install falkordb-cgraph`

For development: `make install-cli` (installs from `cli/`)

Provides query commands only (`list`, `search`, `neighbors`, `paths`, `info`, `ensure-db`). The `index` and `index-repo` commands print a helpful message directing users to install `falkordb-code-graph`.

**Full server package** (`falkordb-code-graph` — for development/Docker):

Install: `pip install falkordb-code-graph` or `uv sync`

Also provides `cgraph` via `api/cli.py` and includes all indexing commands.

```bash
cgraph ensure-db                          # Start FalkorDB if not running
cgraph index . --ignore node_modules      # Index local folder (full package only)
cgraph index-repo <url>                   # Clone + index a repo (full package only)
cgraph list                               # List indexed repos
cgraph search <prefix> [--repo <name>]    # Full-text prefix search
cgraph neighbors <id>... [--repo <name>] [--rel <type>] [--label <label>]  # Connected entities
cgraph paths <src-id> <dest-id> [--repo <name>]  # Call-chain paths
cgraph info [--repo <name>]              # Repo stats + metadata
```

`--repo` defaults to the current directory name. Claude Code skill in `skills/code-graph/`.
