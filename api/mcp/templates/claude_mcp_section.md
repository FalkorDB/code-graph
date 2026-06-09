# code-graph MCP server — agent guidance

This repo is indexed into a FalkorDB **code knowledge graph** exposed
to you over MCP as `code-graph`. Use it instead of grepping when you
need to understand how symbols connect.

## When to call each tool

| Tool | Call this when… | Example |
|---|---|---|
| `index_repo(path_or_url, branch?)` | **First** thing in a new repo; or after large changes outside your edits. Project name is **derived from the folder or repo URL** — read it back from the response. | `index_repo(path_or_url=".")` |
| `search_code(query, project)` | You know part of a symbol name and need its id (hybrid prefix + ranked match). | `search_code(query="processPay", project="myrepo")` |
| `find_symbol(name, project, file?)` | You know the exact symbol name (optionally in a given file) and want its id directly. | `find_symbol(name="processPayment", project="myrepo")` |
| `get_neighbors(symbol_id, project, relation?, direction?)` | "Who calls this?" (`direction="IN"`), "What does this call?" (`direction="OUT"`), or other edges via `relation` (CALLS/IMPORTS/DEFINES). Replaces the old get_callers/get_callees/get_dependencies. | `get_neighbors(symbol_id=42, project="myrepo", direction="IN")` |
| `get_file_neighbors(file, project)` | Symbols a file defines / depends on — "what's in this file and what does it touch?" | `get_file_neighbors(file="api/graph.py", project="myrepo")` |
| `impact_analysis(symbol_id, project, direction, depth)` | **"What breaks if I change this?"** Transitive upstream callers. | `impact_analysis(symbol_id=42, project="myrepo", direction="IN", depth=3)` |
| `find_path(source_id, dest_id, project)` | Show the call chain between two known symbols. | `find_path(source_id=10, dest_id=42, project="myrepo")` |

## Rules of thumb

1. **Start with `search_code` or `find_symbol`** to turn names into ids. Most tools take a `symbol_id`.
2. **Use `get_neighbors` with `direction`** for who-calls / what-calls: `IN` = callers, `OUT` = callees. Pass `relation` for IMPORTS/DEFINES edges.
3. **`impact_analysis` before refactoring.** Even when you think you know
   the answer — the transitive closure often surprises you.
4. **`branch` is optional** but pass it when working on a feature branch
   so you query the right per-branch index.
5. **Response shape.** Tools that return collections (`search_code`,
   `find_symbol`, `get_neighbors`, `get_file_neighbors`, `find_path`,
   `impact_analysis`) put the array in `structuredContent.result` per
   the MCP spec. The text content is the same JSON for convenience.
   `index_repo` returns a single object.

## Environment

- `CODE_GRAPH_AUTO_INDEX=true` — auto-index CWD on first tool call (off by
  default; opt-in because indexing big repos takes minutes).
- `FALKORDB_HOST` / `FALKORDB_PORT` — defaults to `localhost:6379`. If
  unreachable on localhost, the server runs `cgraph ensure-db` to
  spin up the official Docker image.
