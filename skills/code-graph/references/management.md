# Code Graph — Installation & Management

## Prerequisites

- **Docker**: Required for FalkorDB (the graph database)
- **Python 3.12+**
- **uv** (Python package manager)

## Installation

### Install the skill (Claude Code)

```bash
npx skills add FalkorDB/code-graph
```

### Install the cgraph CLI

From the code-graph repository:

```bash
cd /path/to/code-graph
uv sync --all-extras
uv pip install -e .
```

Or standalone via pipx:

```bash
pipx install code-graph
```

After installation, verify:

```bash
cgraph --help
```

## Database

FalkorDB is automatically managed by the `ensure-db` command:

```bash
cgraph ensure-db
```

This will:
1. Check if FalkorDB is reachable on `FALKORDB_HOST:FALKORDB_PORT`
2. If not, start a Docker container named `falkordb-cgraph`
3. Wait for connectivity and report status

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `FALKORDB_HOST` | `localhost` | FalkorDB/Redis host |
| `FALKORDB_PORT` | `6379` | FalkorDB/Redis port |
| `FALKORDB_USERNAME` | _(none)_ | Auth username |
| `FALKORDB_PASSWORD` | _(none)_ | Auth password |

## Supported Languages

- **Python** (.py) — via tree-sitter
- **Java** (.java) — via multilspy
- **C#** (.cs) — via multilspy

## Troubleshooting

### `cgraph` not found

Ensure the package is installed and the entry point is on your PATH:

```bash
uv pip install -e .   # from the code-graph repo
# or
pipx install code-graph
```

### Connection refused

FalkorDB is not running. Run:

```bash
cgraph ensure-db
```

If Docker is not installed, install it first or start FalkorDB manually.

### Stale index

If code has changed significantly since last index, re-index:

```bash
cgraph index . --ignore node_modules --ignore venv --ignore .git --ignore __pycache__
```

Re-indexing overwrites the existing graph for the same repo name.
