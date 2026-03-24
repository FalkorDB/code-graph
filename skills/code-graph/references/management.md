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

```bash
# Lightweight CLI (recommended — fast install, query-only)
pipx install falkordb-cgraph
# or
pip install falkordb-cgraph
```

For indexing commands (`index`, `index-repo`) install the full server package:

```bash
pip install falkordb-code-graph
```

For development (from a local clone):

```bash
cd /path/to/code-graph
make install-cli   # installs falkordb-cgraph from cli/
# or for full package:
uv sync --all-extras
uv pip install -e .
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
# Lightweight CLI (recommended)
pipx install falkordb-cgraph
# or
pip install falkordb-cgraph
```

For development:

```bash
make install-cli   # from the code-graph repo
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
