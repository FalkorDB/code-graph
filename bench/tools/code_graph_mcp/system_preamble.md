# code-graph (MCP) preamble

A pre-indexed code-graph for this repo is available via the
`cg-mcp` CLI (talks to `cgraph-mcp` over stdio).
**Use `cg-mcp` to locate symbols before reading files or grepping.**
`$PROJECT_NAME` and `$BRANCH` are exported.

## Workflow

1. `cg-mcp search_code --project "$PROJECT_NAME" --prefix <name>` →
   list of `{id, name, file, line}`. Pick the best `id`.
2. `cg-mcp get_callers --project "$PROJECT_NAME" --symbol-id <id>` —
   who calls X. (Default `--limit 50`.)
3. `cg-mcp impact_analysis --project "$PROJECT_NAME" --symbol-id <id> --depth 3` —
   transitive blast radius before any non-trivial edit.
4. Read the file with `sed -n` / `cat`, then edit.

## Sub-commands

- `cg-mcp search_code      --project P --prefix STR [--limit N]`
- `cg-mcp get_callers      --project P --symbol-id ID [--limit N]`
- `cg-mcp get_callees      --project P --symbol-id ID [--limit N]`
- `cg-mcp get_dependencies --project P --symbol-id ID [--limit N]`
- `cg-mcp impact_analysis  --project P --symbol-id ID [--direction IN|OUT] [--depth N]`
- `cg-mcp find_path        --project P --source-id ID --dest-id ID`

Standard Unix tools remain available. If `cg-mcp` returns empty, say so
before falling back to grep.
