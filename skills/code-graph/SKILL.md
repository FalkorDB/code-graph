---
name: code-graph
description: "This skill should be used when understanding code structure, finding
  dependencies between functions/classes, tracing call graphs, or exploring code
  relationships. Trigger phrases include 'code graph', 'call graph', 'who calls',
  'what calls', 'find dependencies', 'code structure', 'inheritance', 'find paths'."
---

# Code Graph Skill

You own the full `cgraph` lifecycle: database, indexing, and querying. The user should never need to run cgraph commands manually.

## Ownership Rules

- If `cgraph` commands fail with connection errors, run `cgraph ensure-db` first.
- If `cgraph` is not found, see `management.md` for installation instructions.
- Index at session start or after significant code changes: `cgraph index . --ignore node_modules --ignore venv --ignore .git --ignore __pycache__`
- No need to re-index between consecutive queries if no code has changed.
- All command output is JSON on stdout. Status/progress goes to stderr.
- `--repo` defaults to the current directory name if omitted.

## Indexing

```bash
# Index the current project
cgraph index . --ignore node_modules --ignore venv --ignore .git --ignore __pycache__

# Index a specific folder with a custom name
cgraph index /path/to/project --repo my-project --ignore node_modules

# Clone and index a remote repository
cgraph index-repo https://github.com/org/repo --ignore node_modules
```

## Searching

```bash
# Search for entities by prefix
cgraph search get_user
cgraph search parse
cgraph search MyClass
```

Results return JSON with node `id`, `labels` (File, Class, Function, etc.), and `properties` (name, path, src_start, src_end). Use the `id` for follow-up queries.

## Exploring Relationships

```bash
# Get all neighbors of a node
cgraph neighbors 42 --repo my-project

# Filter by relationship type
cgraph neighbors 42 --rel CALLS          # what does it call?
cgraph neighbors 42 --rel DEFINES         # what does it define?

# Filter by destination label
cgraph neighbors 42 --label Function      # only function neighbors

# Multiple nodes at once
cgraph neighbors 42 55 --repo my-project
```

## Finding Paths

```bash
# Trace call-chain paths between two nodes
cgraph paths 42 99 --repo my-project
```

Follows CALLS edges to find how one function reaches another.

## Repository Info

```bash
# List all indexed repos
cgraph list

# Show stats for a repo
cgraph info --repo my-project
```

## Working with Results

- Search results include `path`, `src_start`, `src_end` — use the Read tool to load the actual source code at those locations.
- **Node labels**: File, Class, Function, Interface, Struct
- **Edge types**: DEFINES (hierarchy), CALLS (call graph), EXTENDS (inheritance), IMPLEMENTS (interfaces), RETURNS (return types), PARAMETERS (param types)
- See `querying.md` for detailed JSON structures and common query patterns.
