# Benchmark workstream

Quantify code-graph's value to a coding agent vs:

- `baseline` — no navigation tools (file read/write/grep/bash only).
- `lsp` — multilspy-driven pyright tools.
- `code-graph` — primitive graph operations against this repo's HTTP API.

See `CONTEXT.md` at the repo root for the glossary and locked-in
decisions. See the session plan at
`~/.copilot/session-state/<id>/plan.md` for the full design doc and the
deferred pre-requisites.

## Status

**Scaffold only.** Directory layout and contracts exist; runners do not.
Next steps are tracked in the session's todo list.

## Layout

```text
bench/
  agents/       # (planned) thin Python adapters around SWE-agent
  runners/      # (planned) swe_bench.py, repobench.py
  metrics/      # (planned) token + accuracy scoring from SWE-agent trajectories
  report/       # (planned) JSONL -> markdown table aggregator
  configs/      # YAML run configs (model, temperature, split, budget)
  cache/        # FalkorDB graph cache keyed by <repo>@<commit>  (gitignored)
  tools/
    baseline/   # SWE-agent default tools (no navigation)
    lsp/        # baseline + pyright tools via multilspy
    code_graph/ # baseline + primitive graph tools (graph_entities,
                #   get_neighbors, find_paths, auto_complete, find_symbol)
  intrinsic/    # (planned) ~30 hand-crafted nav queries per repo, no agent
  opencode/     # (planned) qualitative track using opencode + code-graph MCP
```

## Headline metrics

- **Outcome accuracy** — SWE-bench-Lite patch-pass rate.
- **Token cost** — LLM in+out tokens per task; report median, p90,
  and Δ vs baseline. Indexing cost reported separately.
- **Intrinsic accuracy** — diagnostic only, from `bench/intrinsic/`.

## Run targets (planned Makefile)

```text
make bench-swe        # SWE-bench-Lite, all 3 configs, frontier model
make bench-repo       # RepoBench R+P, all 3 configs
make bench-intrinsic  # tool-only diagnostic, no agent in the loop
make bench-report     # aggregate JSONL into bench/report/results.md
```

## Why not opencode as the primary harness?

opencode is an interactive terminal agent (excellent dev UX, plugin/MCP
model) but lacks a batch runner and per-call token accounting suitable
for scoring. We use opencode for a **secondary qualitative track**
(`bench/opencode/`) showing real dev-flow use, not headline numbers.
