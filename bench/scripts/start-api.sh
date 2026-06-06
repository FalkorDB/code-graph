#!/usr/bin/env bash
# Launch the code-graph API server with the fast tree-sitter Python
# resolver enabled (PR #691 + #692). This is what the bench harness
# expects to talk to at 127.0.0.1:5000.
#
# Usage:
#   bench/scripts/start-api.sh                  # default port 5000
#   bench/scripts/start-api.sh --port 5001
#
# Prereqs:
#   - FalkorDB running. For native falkordb on 6380 set
#     FALKORDB_HOST=127.0.0.1 FALKORDB_PORT=6380 before invoking.
#   - uv on PATH.
#   - cwd must be a code-graph worktree containing api/ with PR #691
#     and PR #692 applied (i.e. the dvirdukhan/query-cache branch tip
#     or staging once those are merged).

set -euo pipefail

PORT=5000
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port) PORT="$2"; shift 2 ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

# Tree-sitter static resolver — turns Python indexing from minutes to
# seconds. Default is still jedi, so callers must opt in explicitly.
export CODE_GRAPH_PY_RESOLVER="${CODE_GRAPH_PY_RESOLVER:-tree_sitter}"

# Allow the bench harness to analyze any folder; the bench worktrees
# live under bench/cache/worktrees.
export ALLOWED_ANALYSIS_DIR="${ALLOWED_ANALYSIS_DIR:-/}"

# Public mode: bench harness does not bother with bearer tokens.
export CODE_GRAPH_PUBLIC="${CODE_GRAPH_PUBLIC:-1}"

echo "[start-api] CODE_GRAPH_PY_RESOLVER=$CODE_GRAPH_PY_RESOLVER"
echo "[start-api] CODE_GRAPH_PUBLIC=$CODE_GRAPH_PUBLIC"
echo "[start-api] FALKORDB_HOST=${FALKORDB_HOST:-127.0.0.1} FALKORDB_PORT=${FALKORDB_PORT:-6379}"
echo "[start-api] Listening on 127.0.0.1:$PORT"

exec uv run uvicorn api.index:app --host 127.0.0.1 --port "$PORT"
