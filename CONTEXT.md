# Benchmark glossary (CONTEXT.md)

Scope: this file is a glossary for the **benchmark workstream** only
(`bench/` and related changes). It is not a project-wide glossary for
code-graph itself. If a project-wide CONTEXT.md is later created at the
repo root, fold these terms into it.

## Terms

### Agent
The autonomous loop that reads a task, calls tools, edits code, and
submits a result. We adopt **SWE-agent** (Princeton) as the harness; we
do not write our own. The agent loop is fixed across all configs.

### Config
One of `baseline`, `lsp`, `code-graph`. A config is **fully defined by
its `tools.yaml`** — same model, same prompt, same iteration cap. The
only variable across configs is the available tool list.

### baseline (config)
SWE-agent's default `tools.yaml`: `read_file`, `write_file`, `edit`,
`bash`, `str_replace`. **Not "zero tools"** — an LLM with literally no
filesystem access is not a useful comparison.

### lsp (config)
`baseline` + multilspy-driven pyright tools: `goto_definition`,
`find_references`, `hover`, `document_symbols`, `workspace_symbols`.

### code-graph (config)
`baseline` + code-graph HTTP tools, **primitive graph operations only**:
`graph_entities`, `get_neighbors`, `find_paths`, `auto_complete`, and
`find_symbol`. The GraphRAG `chat` endpoint is **excluded** because it
is itself a nested LLM agent — including it would double-count tokens
and conflate "the graph helps" with "a sub-agent helps".

### Accuracy
This term **always** needs a qualifier. Two distinct meanings:

- **outcome accuracy** — the SWE-bench-style end-to-end metric: did the
  agent's patch pass the repo's test suite? This is the **headline**
  number.
- **intrinsic retrieval accuracy** — does the tool, asked directly,
  return the right symbol/path? Measured against a hand-crafted
  `bench/intrinsic/` suite (~30 queries × 12 repos), no agent in the
  loop. This is a **diagnostic** number used to explain outcome wins
  and losses.

Never say "accuracy" without one of these qualifiers in this workstream.

### Token cost
LLM input tokens + LLM output tokens summed across one agent session for
one task. Excludes indexing cost (see below). Always report median and
p90 across tasks, and **Δ vs baseline** (the savings number).

### Indexing cost
Wall-clock time and dollar cost to build the FalkorDB graph for a
`<repo>@<commit>` pair. Reported **separately** as a one-time amortized
cost, never folded into per-task token cost.

### Task
One instance from a benchmark dataset. For SWE-bench-Lite, a single
(repo, base-commit, issue, gold-patch) tuple. For RepoBench, a single
retrieval or completion query.

### Run
One execution of (config × task). We do **one run at temperature 0** per
(config, task), then re-run only stochastic failures 2× more to
distinguish flaky failures from real failures.

### Indexed pair
A `<repo>@<commit>` for which a FalkorDB graph has been built. Cache
key. Two tasks against the same commit reuse the graph; same repo
different commits do not (no incremental indexing).

## Conventions

- `bench/` is the top-level directory for everything in this workstream.
- Result files are JSONL, one row per (benchmark, task_id, config,
  run_idx), with token counts pulled from the SWE-agent trajectory JSON.
- The opencode track is **qualitative**. Its outputs are transcripts,
  never folded into the headline tables.
