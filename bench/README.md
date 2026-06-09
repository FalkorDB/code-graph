# Benchmark workstream

Quantify code-graph's value to a coding agent vs:

- `baseline` — no navigation tools (file read/write/grep/bash only).
- `lsp` — multilspy-driven pyright tools.
- `code_graph_mcp` — graph operations over the cgraph-mcp stdio transport
  (the same MCP surface Claude Code / Cursor use in production).

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
  agents/       # (planned) thin adapters around SWE-agent
  runners/      # (planned) swe_bench.py
  metrics/      # (planned) token + accuracy from SWE-agent trajectories
  report/       # (planned) JSONL -> markdown table aggregator
  configs/      # YAML run configs (model, temperature, split, budget)
  cache/        # FalkorDB graph cache keyed by <repo>@<commit>  (gitignored)
  tools/
    baseline/   # SWE-agent default tools (no navigation)
    lsp/        # baseline + pyright tools via multilspy + shim
    code_graph_mcp/ # baseline + graph tools over the cgraph-mcp stdio
                #   transport (search_code, find_symbol, get_neighbors,
                #   get_file_neighbors, find_path, impact_analysis)
```

## Headline metric

- **Outcome accuracy** — SWE-bench-Verified-sample patch-pass rate
  (pass@1, temperature 0, retry stochastic failures 2×).
- **Token cost** — LLM in+out tokens per task; report median, p90,
  and Δ vs baseline. **Indexing cost reported separately**; never
  combined with per-task token cost.

## Run targets (planned Makefile)

```text
make bench-smoke      # stage 1: 3 hand-picked tasks x 3 configs
make bench-calibrate  # stage 2: 10 random tasks x 3 configs
make bench-headline   # stage 3: 37 remaining tasks x 3 configs (pass@1+retry)
make bench-report     # aggregate JSONL into bench/report/results.md
```

## Out of scope (decided during the grill)

- RepoBench — shape mismatch with code-graph's node-granularity outputs.
- opencode qualitative track — marketing, not validity.
- Intrinsic retrieval diagnostic — focus on the outcome question.
- Raw-LSP comparison run — shim is documented and consistent.
