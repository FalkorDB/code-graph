# Benchmark glossary (CONTEXT.md)

Scope: glossary for the **benchmark workstream** (`bench/` and related
changes). Not a project-wide glossary for code-graph.

## Terms

### Agent
The autonomous loop that reads a task, calls tools, edits code, and
submits a result. We adopt **mini-swe-agent** (SWE-agent project's
recommended minimal harness) as the agent. The original SWE-agent
is **not** used: upstream now points users at mini- instead, and its
bash-only tool surface is a much smaller, more transparent
integration. The agent loop is fixed across all configs.

### Config
One of `baseline`, `lsp`, `code-graph`. A config is **fully defined by
its `system_preamble.md` plus the `PATH` it exposes to the agent's
bash**. Same model, same scaffolding template, same step/cost limits
across all three. (mini-swe-agent has no per-config `tools.yaml`
because bash is the only tool; the per-config `tools.yaml` files in
the repo are kept as design documentation.)

### baseline (config)
mini-swe-agent's stock bash environment — `cat`, `grep`, `find`,
`sed`, `git`, the agent's own implicit submit protocol. **Not
"zero tools"** — an LLM with no filesystem access is not a useful
comparison.

### lsp (config)
`baseline` + an `lsp` command on PATH that wraps multilspy/jedi
(`goto-definition`, `find-references`, `hover`, `document-symbols`),
each shaped by the LSP response shim (see below). The plan originally
specified pyright + `workspace_symbols`; we run **jedi-language-server**
(what the pinned multilspy fork ships) and drop `workspace_symbols`
(the fork doesn't implement `request_workspace_symbol`). The shim
normalizes responses so jedi-vs-pyright does not affect the validity
comparison; agent falls back to bash+grep for workspace-wide symbol
search.

### code-graph (config)
`baseline` + a `cg` command on PATH that talks to the code-graph
HTTP service: `graph-entities`, `get-neighbors`, `find-paths`,
`auto-complete`, `find-symbol`, plus `note-edit`. The GraphRAG `chat`
endpoint is **excluded** to avoid nested-agent token double-counting.

### Accuracy
The SWE-bench end-to-end metric: did the agent's patch pass the repo's
test suite? Only accuracy number reported. We considered an intrinsic
retrieval diagnostic and dropped it.

### Token cost
LLM input + LLM output tokens summed across one agent session for one
task. Always reported as median, p90, and **Δ vs baseline**.

### Indexing cost
Wall-clock seconds and any LLM tokens spent to build the FalkorDB graph
for a `<repo>@<commit>` pair. Reported **separately** and **never
combined** with per-task token cost. The writeup states the amortization
break-even task count, no fake math.

### Task
One instance from SWE-bench Verified — `(repo, base-commit, issue,
gold-patch, tests)`.

### Run
One execution of (config × task). We report **pass@1 at temperature 0**.
Failed runs are re-tried 2× more to filter stochastic failures; the
re-tries never change a pass into a fail.

### Indexed pair
A `<repo>@<commit>` for which a FalkorDB graph has been built. Cache
key. No incremental indexing across commits.

### Tool service architecture
mini-swe-agent runs each step as `subprocess.run` in a configured cwd
(the prepared repo working tree). **Tools live on the host** (local
process model): multilspy/jedi runs in-process via the `lsp` CLI
wrapper; code-graph is reached via an HTTP client (`cg` CLI wrapper)
to the FastAPI + FalkorDB service. The runner sets `PATH` so the
agent sees `bench/cli/` only for configs that include those tools
(baseline gets the unmodified host `PATH`). code-graph's graph is
built once per `<repo>@<commit>` and would otherwise go stale on agent
edits, so the code-graph bundle includes a `cg note-edit PATH` tool
that triggers a **single-file incremental re-index** of the touched
file. This keeps fairness with the live-by-default LSP.

### LSP response shim
Raw LSP responses are too verbose for a fair token-cost comparison
(`find_references` can return hundreds of locations; `hover` can return
multi-paragraph markdown). The `lsp` config wraps every pyright tool in
a thin adapter (`bench/tools/lsp/adapter.py`) that:

- Caps result lists at **50** entries. Further results behind a `page`
  arg on the same tool.
- Strips `hover` markdown to the **first signature line + first
  docstring sentence**. Full hover available via an opt-in
  `hover_full`.
- Returns locations as `{path, line, col}`, not the raw LSP `Range`.

The shim is identical across all LSP runs. We do **not** run a
raw-LSP comparison.

### Preambles
Each config gets a single-paragraph **symmetric preamble** introducing
its toolkit. The preambles are committed to
`bench/tools/<config>/system_preamble.md` and reviewed as artifacts.
Before headline runs we sanity-check phrasing sensitivity by re-running
one config with 2-3 alternative phrasings; if pass rate moves by >5%,
the preambles are dominating signal and we revisit.

### Rollout
Three-stage:

1. **Smoke** — 3 hand-picked tasks × 3 configs × 1 run = 9 sessions.
   Verify harness, token accounting, indexing path, tool plumbing.
2. **Calibration** — 10 random Verified tasks × 3 configs × 1 run = 30
   sessions. Verify preamble phrasing sensitivity, shim behavior.
3. **Headline** — remaining 40 of the 50-task sample × 3 configs ×
   pass@1 with retry-2x-on-fail.

### Dataset
**50-task random sample from SWE-bench Verified** (500-task split).
Random seed committed to `bench/configs/default.yaml`. If the headline
Δ between configs is <10 percentage points, we expand to 150 tasks
before publishing — the 50-task sample's confidence interval is roughly
±7 pp.

## Conventions

- `bench/` is the top-level directory for the workstream.
- Results are JSONL, one row per `(task_id, config, run_idx)`, with
  token counts pulled from the mini-swe-agent trajectory JSON
  (`agent.serialize()` — `messages[*].extra.response.usage`).
- The opencode track and RepoBench track are **not** part of this
  workstream (dropped during the grill).
