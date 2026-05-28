# code-graph preamble

A pre-indexed code-graph for this repo is available via `cg`.
**Use `cg` to locate symbols before reading files or grepping.**
`$REPO_NAME` is exported.

## Workflow

1. `cg find-symbol --repo "$REPO_NAME" --name <symbol>` → `{id, file, line}`.
2. `cg get-neighbors --repo "$REPO_NAME" --ids <id> [--limit 50]` →
   callers / callees / definitions. Default limit 50 keeps output small;
   pass `--limit 0` only if you truly need everything.
3. Read the file with `sed -n` / `cat`, then edit.
4. After every edit run `cg note-edit --repo "$REPO_NAME" --path <relpath>`.

## Sub-commands

- `cg find-symbol     --repo R --name NAME`
- `cg get-neighbors   --repo R --ids N [N ...] [--limit N]`
- `cg find-paths      --repo R --src N --dst N`
- `cg auto-complete   --repo R --prefix STRING`
- `cg note-edit       --repo R --path PATH`        (call after every edit)
- `cg graph-entities  --repo R`                    (large; rarely needed)

Standard Unix tools (`cat`, `grep`, `find`, `sed`) remain available for
cases the graph can't answer. If `cg` returns empty, say so before
falling back.
