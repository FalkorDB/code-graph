# code-graph MCP server — agent guidance

This repo is indexed into a FalkorDB **code knowledge graph** exposed
to you over MCP as `code-graph`. Use it instead of grepping when you
need to understand how symbols connect.

## When to call each tool

| Tool | Call this when… | Example |
|---|---|---|
| `index_repo(path)` | **First** thing in a new repo; or after large changes outside your edits. | `index_repo(path=".")` |
| `search_code(prefix, project)` | You know part of a symbol name and need its id. | `search_code(prefix="processPay", project="myrepo")` |
| `get_callers(symbol_id, project)` | "Who calls this?" — refactoring a function, tracking down a regression. | `get_callers(symbol_id=42, project="myrepo")` |
| `get_callees(symbol_id, project)` | "What does this call?" — understanding a function before editing it. | `get_callees(symbol_id=42, project="myrepo")` |
| `get_dependencies(symbol_id, project)` | All edges out of a symbol (CALLS + IMPORTS + DEFINES). | `get_dependencies(symbol_id=42, project="myrepo")` |
| `impact_analysis(symbol_id, project, direction, depth)` | **"What breaks if I change this?"** Transitive upstream callers. | `impact_analysis(symbol_id=42, project="myrepo", direction="IN", depth=3)` |
| `find_path(source_id, dest_id, project)` | Show the call chain between two known symbols. | `find_path(source_id=10, dest_id=42, project="myrepo")` |
| `ask(question, project)` | Open-ended natural-language question. **More expensive — use last.** | `ask(question="why does login fail when MFA is on?", project="myrepo")` |

## Rules of thumb

1. **Start with `search_code`** to turn names into ids. Most tools take a `symbol_id`.
2. **Prefer structural tools over `ask`.** `get_callers` is one cheap Cypher
   hop; `ask` is two LLM round-trips. Use `ask` for fuzzy/conceptual
   questions, not for "who calls X".
3. **`impact_analysis` before refactoring.** Even when you think you know
   the answer — the transitive closure often surprises you.
4. **`branch` is optional** but pass it when working on a feature branch
   so you query the right per-branch index.

## Environment

- `CODE_GRAPH_AUTO_INDEX=true` — auto-index CWD on first tool call (off by
  default; opt-in because indexing big repos takes minutes).
- `FALKORDB_HOST` / `FALKORDB_PORT` — defaults to `localhost:6379`. If
  unreachable on localhost, the server runs `cgraph ensure-db` to
  spin up the official Docker image.
