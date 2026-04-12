# Code Graph MCP Server — Design Summary

## What We're Building

An MCP server inside the `code-graph` repo that gives AI coding agents two capabilities:
1. **Structural tools** (deterministic, no LLM): get_callers, get_callees, get_dependencies, impact_analysis, find_path, search_code, index_repo
2. **Ask tool** (GraphRAG SDK, needs LLM): natural language questions about the codebase → NL-to-Cypher → grounded answers

Phase 1 also bundles three foundational improvements to `api/` that the MCP server needs and that benefit all consumers of code-graph (CLI, web UI, future integrations):

3. **Multi-branch graph identity**: per `(repo, branch)` graph naming so concurrent agents on different branches can't corrupt each other's view. (Today, two users on different branches overwrite each other's graphs — this is a real bug.)
4. **Incremental indexing**: file-hash-based skip-unchanged so agents can call `index_repo` cheaply on every interaction. Default-on once a graph exists.
5. **Tree-sitter language expansion**: a shared `TreeSitterAnalyzer` base class plus 5 new languages (Go, Rust, TypeScript, Ruby, C++) and re-enabling C. Brings supported languages from 5 to 11.

## Key Decisions Made

- **Mono-repo**: Build inside `code-graph/api/mcp/`, not a separate project. One pip package, one repo.
- **Module path is `api/mcp/`, NOT top-level `mcp/`**: A top-level `mcp/` directory would shadow the installed `mcp` PyPI SDK and break `from mcp.server.fastmcp import FastMCP`. Entry point: `cgraph-mcp = "api.mcp.server:main"`.
- **Python MCP server**: Use the official `mcp` Python SDK (`from mcp.server.fastmcp import FastMCP`), NOT standalone `fastmcp` or Node.js. Avoids language bridge.
- **Reuse everything**: Most code already exists. The MCP tools are thin wrappers around `api/graph.py`, `api/project.py`, `api/cli.py`, and `api/llm.py`.
- **GraphRAG SDK powers the ask tool**: `kg.ask()` does NL-to-Cypher. Code-graph's `api/llm.py` already integrates this — repackage for MCP.
- **Reuse the existing hand-coded ontology** from `api/llm.py:_define_ontology()` (lines 26–233) rather than auto-extracting via `Ontology.from_kg_graph()`. The hand-coded version has richer entity attributes and descriptions tuned for code. Refactor: rename `_define_ontology` → `define_ontology` so the MCP module can import it.
- **11 languages in Phase 1**: Python/JS/Kotlin via tree-sitter (refactored onto a shared base class in T15), Go/Rust/TypeScript/Ruby/C/C++ added in T16, Java/C# stay on multilspy.
- **Incremental indexing in Phase 1**: file-hash-based skip-unchanged, default-on once a `(project, branch)` graph exists (T18). Full re-index via `--full` (CLI) or `incremental=False` (MCP).
- **No Graphiti/memory or raw FalkorDB MCP in v1**: Out of scope. Available as separate servers. Architecture supports merging later.
- **Auto-init for zero config**: ensure-db auto-starts FalkorDB Docker, auto-index on first tool call, auto-GraphRAG init.
- **Expose Cypher in ask responses**: Transparency for the agent + learning patterns.
- **Stdio transport only in Phase 1**: HTTP/SSE deferred to Phase 1.5. Stdio is sufficient for Claude Code, Cursor, and Claude Desktop.
- **`impact_analysis` defaults**: direction `IN` (upstream callers — "what breaks if I change this"), depth `3`, max depth clamp `10`. Parameters allow override.
- **Multi-branch graph identity**: graph name is `code:{project}:{branch}`. Sourcegraph-zoekt-style isolation. The IDE/LSP "single current index, re-index on switch" model only works because IDEs are single-tenant; code-graph is multi-tenant (a server, not a desktop tool, with concurrent agents on different branches), so per-branch isolation is required for correctness. Existing single-graph deployments migrate to `code:{project}:_default`. Within a branch, the existing transition-based `switch_commit` flow continues to work unchanged.
- **`index_repo` auto-detects branch**: from `git rev-parse --abbrev-ref HEAD` in the target path. Optional override parameter. Non-git paths use `_default`.
- **Incremental indexing default-on**: once a `(project, branch)` graph exists, `index_repo` and `cgraph index` auto-detect and run incremental. Opt out with `--full` (CLI) or `incremental=False` (MCP). First-time runs are full. Tracks per-file SHA256 hashes in Redis under `{repo}:{branch}_files`. Built on the existing `delete_files()` primitive in `api/graph.py` (today only used in the git-history flow).
- **Tree-sitter base class**: refactor existing PythonAnalyzer / JavaScriptAnalyzer / KotlinAnalyzer onto a shared `TreeSitterAnalyzer` base in Phase 1. Five new languages added on the new base in the same phase. C is re-enabled. Java and C# stay on multilspy (LSP) until a future phase.

## Directory Structure

```text
code-graph/
├── api/                          # Existing Python backend (FastAPI, analyzers, graph, llm, cli)
│   └── mcp/                      # NEW — MCP server module (under api/ to avoid shadowing the installed `mcp` SDK)
│       ├── __init__.py
│       ├── server.py             # FastMCP entry point, tool registration, stdio transport
│       ├── auto_init.py          # ensure-db + auto-index hooks
│       ├── graphrag_init.py      # KnowledgeGraph construction + per-project caching (reuses api/llm.py:define_ontology)
│       ├── code_prompts.py       # Re-exports + hooks for GraphRAG prompts (sourced from api/prompts.py)
│       ├── templates/            # Agent guidance file templates (cursorrules, claude_mcp_section)
│       └── tools/
│           ├── __init__.py
│           ├── structural.py     # index_repo, get_callers, get_callees, get_dependencies,
│           │                     # impact_analysis, find_path, search_code
│           └── ask.py            # GraphRAG-powered ask tool
├── app/                          # Existing React frontend
├── skills/                       # Existing Claude Code skill
├── tests/
│   └── mcp/
│       ├── __init__.py
│       ├── conftest.py           # Session-scoped FalkorDB + indexed-fixture fixtures
│       ├── fixtures/
│       │   ├── sample_project/   # Py/Java/C# fixture with known call graph
│       │   └── expected.yaml     # Assertion contract: counts, callers, callees, paths, search hits
│       ├── test_scaffold.py      # Scaffold smoke test (T1)
│       ├── test_index_repo.py    # T4 — unit + integration + protocol
│       ├── test_neighbors.py     # T5 — unit + integration + protocol + CLI parity
│       ├── test_impact_analysis.py # T6
│       ├── test_find_path.py     # T7
│       ├── test_search_code.py   # T8
│       ├── test_graphrag_init.py # T9
│       ├── test_code_prompts.py  # T10 (snapshot)
│       ├── test_ask.py           # T11 — mocked LLM, real Cypher against fixture
│       ├── test_auto_init.py     # T12
│       └── test_init_agent.py    # T13
└── pyproject.toml                # Adds `cgraph-mcp = "api.mcp.server:main"` and `mcp>=1.0,<2.0`
```

**Note on test layout:** Each tool ticket ships its own integration + MCP-protocol round-trip tests in the same PR — there is no separate "integration tests" or "protocol tests" milestone. The previous `integration/` and `e2e/` subdirectories are removed in favor of per-tool test files. Real-LLM E2E is deferred to Phase 1.5.

## CLI-to-MCP Tool Mapping

| cgraph Command | MCP Tool | Shared Code | Delta |
|---|---|---|---|
| `cgraph index` / `index-repo` | `index_repo` | api/project.py, analyzers/ | + GraphRAG init after indexing |
| `cgraph neighbors --rel CALLS --dir in` | `get_callers` | api/graph.py Cypher | Thin wrapper |
| `cgraph neighbors --rel CALLS --dir out` | `get_callees` | api/graph.py Cypher | Thin wrapper |
| `cgraph neighbors` (multi-rel) | `get_dependencies` | api/graph.py Cypher | New multi-rel query |
| (new) | `impact_analysis` | api/graph.py Cypher | New variable-depth traversal |
| `cgraph paths` | `find_path` | api/graph.py Cypher | Thin wrapper |
| `cgraph search` | `search_code` | api/auto_complete.py | Thin wrapper |
| (web UI chat) | `ask` | api/llm.py + GraphRAG SDK | Repackage as MCP tool |

## GraphRAG SDK Integration Pattern

The MCP `ask` tool is a thin wrapper around the GraphRAG SDK flow already implemented in `api/llm.py`. End-to-end:

1. **Pre-step (once per project, in `api/mcp/graphrag_init.py`):** construct a `KnowledgeGraph` and cache it. Reuses the existing hand-coded ontology from `api/llm.py:define_ontology()` (renamed from `_define_ontology` in T9).

2. **Per-call (in the `ask` tool):** retrieve cached `KnowledgeGraph`, call `kg.ask(question)`, return `{answer, cypher_query, context_nodes}`. Internally this is **two LLM round-trips bracketing one Cypher query against FalkorDB**:
   - LLM #1: question + ontology → Cypher
   - FalkorDB: execute Cypher → rows
   - LLM #2: question + rows → natural-language answer

   The graph itself never goes to the LLM — only schema and query results — which is why this works on huge codebases.

```python
# api/mcp/graphrag_init.py — construct once, cache per project
from graphrag_sdk import KnowledgeGraph
from graphrag_sdk.models.litellm import LiteModel
from graphrag_sdk.model_config import KnowledgeGraphModelConfig

from api.llm import define_ontology  # renamed from _define_ontology in T9
from api.mcp.code_prompts import (
    CYPHER_GEN_SYSTEM, CYPHER_GEN_PROMPT,
    GRAPH_QA_SYSTEM, GRAPH_QA_PROMPT,
)

_kg_cache: dict[str, KnowledgeGraph] = {}

def get_or_create_kg(project_name: str) -> KnowledgeGraph:
    if project_name in _kg_cache:
        return _kg_cache[project_name]

    model = LiteModel(model_name=os.getenv("MODEL_NAME", "gemini/gemini-flash-lite-latest"))
    kg = KnowledgeGraph(
        name=f"code:{project_name}",
        model_config=KnowledgeGraphModelConfig.with_model(model),
        ontology=define_ontology(),                    # REUSE — do NOT call Ontology.from_kg_graph
        cypher_system_instruction=CYPHER_GEN_SYSTEM,
        qa_system_instruction=GRAPH_QA_SYSTEM,
        cypher_gen_prompt=CYPHER_GEN_PROMPT,
        qa_prompt=GRAPH_QA_PROMPT,
    )
    _kg_cache[project_name] = kg
    return kg

# api/mcp/tools/ask.py — the tool itself
async def ask(question: str) -> dict:
    kg = get_or_create_kg(current_project_name())
    response = await asyncio.get_event_loop().run_in_executor(None, kg.ask, question)
    return {
        "answer": response.answer,
        "cypher_query": response.cypher_query,   # exposed for transparency
        "context_nodes": response.context_nodes,
    }
```

## Multi-Branch Graph Identity

**Problem.** Today, `Graph(project_name)` (api/project.py:225, api/index.py:246) names every graph after the repo directory. There is no branch component. Two users (or agents) indexing the same repo on different branches **silently overwrite each other** — the second indexer wipes the first. The Redis metadata under `{repo}_info` (api/info.py:33-46) is also a single global hash per repo, so the commit pointer is shared. This is a real bug that the MCP server will hit immediately because agents working on PR branches need their branch's view, not stale state from someone else's main.

**Comparison with prior art.**

| System | Storage | Branch behavior | Why it works for them |
|---|---|---|---|
| JetBrains IDEs | Single on-disk index | Filesystem-state-based; re-index on `git checkout` | Single-tenant; one developer, one workspace |
| VS Code + LSPs | In-memory per workspace + content-hash cache | LSP receives `didChangeWatchedFiles`, reanalyzes touched files | Single-tenant; each workspace is isolated by process |
| GitHub Blackbird | Server-side, commit-sharded, deduped | All commits indexed simultaneously | Massive scale; full historical search |
| Sourcegraph zoekt | Per `(repo, branch)` shard | Default branch always indexed; others by config | Server, multi-tenant, interactive use |
| Sourcegraph SCIP | Per-commit graph data uploaded by CI | Commit-keyed | Reproducible cross-commit code intel |

Code-graph is architecturally a server (FalkorDB-backed, accessed by multiple clients), so the IDE single-index model is wrong for it. The closest analog is **Sourcegraph zoekt: per `(repo, branch)` graphs**.

**Solution (T17).** Graph naming becomes `code:{project_name}:{branch}`. The full set of changes:

| File | Change |
|---|---|
| `api/graph.py` | `Graph` and `AsyncGraphQuery` constructors take a `branch` parameter; default `_default`; graph name composed as `code:{project}:{branch}` |
| `api/project.py` | `Project.from_git_repository()` and `Project.from_local_directory()` accept and propagate `branch`; auto-detect via `git rev-parse --abbrev-ref HEAD` when `None` |
| `api/info.py` | Redis metadata keys become `{repo}:{branch}_info`; `set_repo_commit`, `get_repo_commit`, etc. take a branch param |
| `api/git_utils/` | Git-transitions graph becomes `{repo}:{branch}_git`; `switch_commit` stays scoped to a single branch graph |
| `api/cli.py` | `cgraph index --branch <name>`; `cgraph list` enumerates `(project, branch)` pairs; `cgraph info`, `cgraph search` accept `--branch` |
| `api/index.py` | `/api/list_repos`, `/api/graph_entities`, `/api/repo_info`, `/api/get_neighbors`, `/api/find_paths`, `/api/auto_complete` accept optional `branch` query param; responses include the branch |
| MCP `index_repo` | Accepts optional `branch`; auto-detects from target path's checkout; returns `branch` in response |

**Migration.** A one-shot helper renames `code:{project}` → `code:{project}:_default` and copies `{repo}_info` → `{repo}:_default_info` on first read. Documented as `cgraph migrate` for explicit invocation.

**Out of scope for Phase 1.** Cross-branch query tools, branch comparison, branch garbage collection. Each branch is an isolated graph; users prune via `cgraph delete --branch`.

## Incremental Indexing

**Today.** `SourceAnalyzer.first_pass()` (`api/analyzers/source_analyzer.py:82-121`) re-parses **every supported file** on every index call. There is no per-file hash tracking. The codebase already has the primitives for incremental work — `Graph.delete_files()` (referenced in `api/git_utils/git_utils.py:153, 217`) and the file-classification logic in `classify_changes` — but they're coupled to the git-history-build flow and not used for ad-hoc reindexing.

**Solution (T18).** Add file-hash-based incremental indexing on top of T17's per-branch storage. Flow:

1. **Hash store**: Redis hash `{repo}:{branch}_files` mapping `file_path → SHA256(content)`. Persisted at the end of every full or incremental index.
2. **Diff phase**: `Project.analyze_sources(incremental=True)` walks the file tree, computes current hashes, diffs against the stored map:
   - **Unchanged** → skip the analyzer entirely
   - **Modified** → call `delete_files([path])` to remove old graph entities, then re-run the analyzer (first pass) on the file
   - **Deleted** → call `delete_files([path])` only
   - **New** → analyze normally
3. **Second-pass (LSP) decision**: if any file changed, run the LSP-based second pass over the entire branch graph. Per-file second-pass is a Phase 2 optimization (correctness over speed in v1).
4. **Persist** the new hash map.

**Defaults.**
- First run on a fresh `(project, branch)` → automatically falls back to full
- Hash store missing or corrupted → falls back to full with a warning logged
- File renames → treated as delete + add (rename detection deferred to Phase 2)
- CLI `cgraph index .` defaults to incremental when a graph exists; `--full` forces full
- MCP `index_repo` defaults to incremental; response includes `mode: "full"|"incremental"` and `files_changed: list[str]`

**Why this is the right primitive for agents.** Agents call `index_repo` reflexively at the start of every interaction to ensure freshness. With full re-index, this is too slow to be reflexive. With incremental + content-hash skipping (the same trick LSP servers use), the steady-state cost is "diff a few file hashes" — acceptable for every-call use.

## Competitive Context

5 competitors exist: codebase-memory-mcp (66 langs, SQLite), GitNexus (23.8K stars, KuzuDB), Codegraph (11 langs, 30+ tools, SQLite), CodeGraphContext (Neo4j), Code Pathfinder (Python only).

**All share 3 gaps FalkorDB fills:**
1. No NL query layer (none have an "ask" tool — GraphRAG SDK is the differentiator)
2. Local-only embedded storage (all SQLite — FalkorDB is client-server, supports shared/team/cloud)
3. No ecosystem path to memory/intelligence (FalkorDB has Graphiti, GraphRAG SDK, mcpserver)

**Don't compete on:** tool count or language count.
**Compete on:** ask tool (understanding), shared graphs (scale), cloud path (enterprise).

## CI Testing Strategy

**Each tool ticket ships its own four kinds of tests in the same PR.** No bulk-testing milestones at the end.

| Layer | Runs On | FalkorDB | LLM | What It Tests |
|---|---|---|---|---|
| Unit tests | Every PR | Mocked | No | Parameter parsing, Cypher generation, output formatting, error handling |
| Integration (structural) | Every PR | Docker service | No | Tool against indexed fixture, asserted via `expected.yaml` contract |
| Integration (ask, mocked) | Every PR | Docker service | Mocked | GraphRAG init, prompt construction, real Cypher execution against fixture, answer formatting |
| MCP protocol round-trip | Every PR | Docker service | No | `session.list_tools()` schema check + `session.call_tool(...)` round-trip via the `mcp` SDK's stdio client |
| CLI parity (where applicable) | Every PR | Docker service | No | MCP tool output matches the equivalent `cgraph` CLI command output |
| E2E (ask, real LLM) | **Phase 1.5** (nightly, deferred) | Docker service | Real (secret) | Prompt quality, answer grounding, regression detection |

GitHub Actions FalkorDB service (added in T2):
```yaml
services:
  falkordb:
    image: falkordb/falkordb:latest
    ports:
      - 6379:6379
    options: >-
      --health-cmd "redis-cli ping"
      --health-interval 10s
      --health-timeout 5s
      --health-retries 5
```

## GitHub Issues Breakdown (Phase 1: 18 vertical issues)

Each tool ticket ships impl + unit + integration + protocol round-trip in a single PR. There are no separate "testing" milestones — testing is folded into every ticket.

### Foundation
1. **T1 — Scaffold `api/mcp/` module + `cgraph-mcp` entry point.** FastMCP server, stdio runner, `mcp>=1.0,<2.0` dep, copy design doc into repo, scaffold smoke test.
2. **T2 — CI workflow with FalkorDB service.** `.github/workflows/mcp-tests.yml`, FalkorDB service container, runs on path filter, scaffold smoke test green.
3. **T3 — Test fixture project + assertion contract.** `tests/mcp/fixtures/sample_project/` with known call graph in Py/Java/C#, plus `expected.yaml` and session-scoped `conftest.py`.

### Core `api/` improvements (prerequisite to MCP tools)
17. **T17 — Per-branch graph identity.** `code:{project}:{branch}` naming everywhere; branch param on `Graph`, `Project`, `info`, CLI, REST endpoints; one-shot migration helper to `_default`. **On the critical path before T4.**
18. **T18 — Incremental indexing.** File-hash-based skip-unchanged in `SourceAnalyzer`, default-on once a graph exists. Builds on T17. CLI `--full` flag; MCP `incremental` parameter.

### Structural Tools (each ticket: impl + unit + integration + protocol round-trip + CLI parity)
4. **T4 — `index_repo` tool.** Wraps `Project.from_git_repository` + `analyze_sources` post-T17. Auto-detects branch; supports incremental via T18.
5. **T5 — `get_callers` / `get_callees` / `get_dependencies` tools.** Three tools sharing one helper over `AsyncGraphQuery.get_neighbors`.
6. **T6 — `impact_analysis` tool.** New variable-depth Cypher in `api/graph.py`. Defaults: direction `IN`, depth `3`, max clamp `10`.
7. **T7 — `find_path` tool.** Wraps `AsyncGraphQuery.find_paths`.
8. **T8 — `search_code` tool.** Wraps `AsyncGraphQuery.prefix_search`.

### Ask Tool + GraphRAG
9. **T9 — GraphRAG init module (`api/mcp/graphrag_init.py`).** Reuses `api/llm.py:define_ontology` (renamed from `_define_ontology`). Caches `KnowledgeGraph` per `(project, branch)`.
10. **T10 — Code-specific prompt overrides (`api/mcp/code_prompts.py`).** Re-exports + snapshot-pinned prompts from `api/prompts.py`.
11. **T11 — `ask` MCP tool.** Returns `{answer, cypher_query, context_nodes}`. Mocked-LLM integration test executes real Cypher against the T3 fixture.

### Operational
12. **T12 — Auto-init: ensure FalkorDB + auto-index CWD.** Bootstraps Docker if FalkorDB unreachable; lazy auto-index gated on `CODE_GRAPH_AUTO_INDEX=true`.
13. **T13 — Agent guidance bundle.** AGENTS.md section, `.cursorrules` template, `cgraph init-agent` CLI command.
14. **T14 — Packaging.** Dockerfile MCP mode, docker-compose for FalkorDB + MCP server, README quickstart with `claude mcp add-json` snippet.

### Tree-sitter expansion (parallel swimlane)
15. **T15 — Tree-sitter analyzer base class refactor.** Extract `TreeSitterAnalyzer` base from existing Python/JS/Kotlin analyzers. Strictly non-functional.
16. **T16 — Add 5 new tree-sitter languages + re-enable C.** Go, Rust, TypeScript, Ruby, C++; per-language fixtures and tests. Brings supported languages from 5 to 11.

### Deferred to Phase 1.5
- HTTP/SSE transport (was Phase 1 issue #3 in earlier draft)
- Real-LLM nightly E2E with API-key secrets (was a row in the CI table)

### Dependency graph
```text
T1 ──┬─> T2 ──> T3 ──> T17 ──> T4 ──┬─> T5
     │                                ├─> T6
     │                                ├─> T7
     │                                └─> T8
     ├─> T9 ──> T10 ──> T11 (also needs T3, T17)
     ├─> T12 (also needs T4)
     ├─> T13
     ├─> T14 (also needs T12)
     ├─> T15 ──> T16
     └─> T18 (also needs T17, lands in parallel with T4+)
```
After T17 lands, multiple streams parallelize: structural tools (T4 → T5/T6/T7/T8), ask (T9 → T10 → T11), tree-sitter expansion (T15 → T16), and incremental indexing (T18). T17 is the only addition to the critical path; everything else is parallel work.

## Configuration

| Variable | Description | Default |
|---|---|---|
| FALKORDB_HOST | FalkorDB hostname | localhost |
| FALKORDB_PORT | FalkorDB port | 6379 |
| MODEL_NAME | LLM for ask tool (LiteLLM format) | openai/gpt-4o-mini |
| LLM_API_KEY | API key for ask tool (optional) | — |
| CODE_GRAPH_AUTO_INDEX | Auto-index on first tool call | false |
| CODE_GRAPH_IGNORE | Dirs to ignore | node_modules,.git,__pycache__ |
| MCP_TRANSPORT | stdio or http | stdio |
| MCP_PORT | HTTP transport port | 3000 |

Quick start (Claude Code):
```bash
claude mcp add-json "code-graph" '{"command":"cgraph-mcp","env":{"FALKORDB_HOST":"localhost","LLM_API_KEY":"sk-..."}}'
```

## Roadmap

- **Phase 1:** MCP server with 8 tools. **11 languages** (Python/JS/Kotlin/Go/Rust/TypeScript/Ruby/C/C++ via tree-sitter; Java/C# via multilspy). Stdio transport. Auto-init. Agent guidance. **Per-branch graph identity. Default-on incremental indexing.** **18 vertical issues** (T1–T18).
- **Phase 1.5:** HTTP/SSE transport. Real-LLM nightly E2E with secret-managed API key. Prompt iteration on `ask` tool.
- **Phase 2:** Cross-branch query tools ("what changed between branches"). Per-file second-pass LSP optimization in incremental indexing. Rename detection in incremental flow. tree-sitter language coverage beyond the 11 (toward the 60+ baseline). Benchmarks.
- **Phase 3:** Dedicated TS/Go analyzers (replacing tree-sitter for those two with deeper LSP integration). Copilot extension. FalkorDB Cloud integration. Branch garbage collection / TTL.
- **Future:** Merge with Graphiti (memory) and mcpserver (raw graph) into unified `@falkordb/code-intelligence`.

## Design Doc

The full design document (v4) is in `code-graph-mcp-v4.docx` and covers: competitive landscape, architecture, tool catalog, data model, parsing strategy, GraphRAG integration, agent integration patterns, current state assessment, execution roadmap, success metrics, risks, and configuration reference.
