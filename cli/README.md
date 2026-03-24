# falkordb-cgraph

Lightweight CLI for querying [FalkorDB](https://falkordb.com) code-graph knowledge graphs.

## Installation

```bash
pipx install falkordb-cgraph
```

This installs only `falkordb` and `typer` — no heavy server-side dependencies.

## Usage

```bash
cgraph --help

# Ensure FalkorDB is running (starts a Docker container if needed)
cgraph ensure-db

# List all indexed repositories
cgraph list

# Search for entities by prefix
cgraph search <prefix> [--repo <name>]

# Get neighboring entities
cgraph neighbors <id>... [--repo <name>] [--rel <type>] [--label <label>]

# Find call-chain paths between two nodes
cgraph paths <src-id> <dest-id> [--repo <name>]

# Show repository statistics and metadata
cgraph info [--repo <name>]
```

`--repo` defaults to the current directory name.

## Indexing

The `index` and `index-repo` commands require the full server package:

```bash
pip install falkordb-code-graph
```

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `FALKORDB_HOST` | `localhost` | FalkorDB host |
| `FALKORDB_PORT` | `6379` | FalkorDB port |
| `FALKORDB_USERNAME` | — | FalkorDB username (optional) |
| `FALKORDB_PASSWORD` | — | FalkorDB password (optional) |
