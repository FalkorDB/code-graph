"""Estimate context/token savings from CodeGraph MCP-style lookups.

This benchmark is intentionally deterministic: it does not call an LLM and
does not require provider API keys. It compares the approximate context size an
agent would send when answering 100 code-navigation questions in two modes:

* graph: compact structured context from CodeGraph MCP tools
* plain: raw source-file context from the likely file an agent would inspect

Run after indexing the repo/folder, for example:

    CODE_GRAPH_DB_BACKEND=lite FALKORDB_LITE_PATH=/tmp/code-graph-lite.rdb \
      uv run --extra light cgraph index api --repo code-graph-api --branch local-test

    CODE_GRAPH_DB_BACKEND=lite FALKORDB_LITE_PATH=/tmp/code-graph-lite.rdb \
      uv run --extra light python benchmarks/mcp_context_benchmark.py \
        --project code-graph-api --branch local-test --root api
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logging.disable(logging.CRITICAL)

from api.mcp.tools.structural import find_symbol, get_file_neighbors, get_neighbors  # noqa: E402


@dataclass(frozen=True)
class Target:
    subject: str
    symbol: str
    file: str


@dataclass(frozen=True)
class Question:
    text: str
    target: Target


TARGETS = [
    Target("Graph class ownership and methods", "Graph", "api/graph.py"),
    Target("AsyncGraphQuery neighbor reads", "AsyncGraphQuery", "api/graph.py"),
    Target("regular-vs-Lite backend selection", "create_falkordb", "api/db.py"),
    Target("GraphRAG host/port configuration", "graphrag_connection_kwargs", "api/db.py"),
    Target("MCP repository indexing", "index_repo", "api/mcp/tools/structural.py"),
    Target("symbol resolution before traversal", "find_symbol", "api/mcp/tools/structural.py"),
    Target("single-hop graph traversal", "get_neighbors", "api/mcp/tools/structural.py"),
    Target("project source analysis orchestration", "Project", "api/project.py"),
    Target("local folder analyzer pipeline", "SourceAnalyzer", "api/analyzers/source_analyzer.py"),
    Target("C# analyzer restore behavior", "CSharpAnalyzer", "api/analyzers/csharp/analyzer.py"),
]

QUESTION_TEMPLATES = [
    "What does {subject} do?",
    "Which symbols are directly related to {subject}?",
    "What would likely be impacted if {subject} changed?",
    "Which callers or incoming relationships does {subject} have?",
    "Which dependencies or outgoing relationships does {subject} have?",
    "Where is {subject} defined and what is its local context?",
    "What methods or child symbols does {subject} define?",
    "How should an agent navigate from {subject} to related code?",
    "What source file should be inspected for {subject}?",
    "Summarize {subject} using only relevant structural context.",
]

QUESTIONS = [
    Question(template.format(subject=target.subject), target)
    for target in TARGETS
    for template in QUESTION_TEMPLATES
]


def estimate_tokens(text: str) -> int:
    """Cheap token approximation for relative comparisons."""
    return max(1, len(text) // 4)


def compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)


def read_plain_context(root: Path, file_hint: str) -> str:
    path = root.parent / file_hint if file_hint.startswith(f"{root.name}/") else root / file_hint
    if not path.exists():
        path = root.parent / file_hint
    return path.read_text(errors="replace")


async def graph_context(question: Question, project: str, branch: str | None) -> dict[str, Any]:
    symbols = await find_symbol(
        name=question.target.symbol,
        project=project,
        branch=branch,
        file=question.target.file,
        limit=3,
    )
    payload: dict[str, Any] = {"symbols": symbols}
    if not symbols:
        return payload

    symbol_id = symbols[0]["symbol_id"]
    payload["defines_out"] = await get_neighbors(
        symbol_id=symbol_id,
        project=project,
        branch=branch,
        relation="DEFINES",
        direction="OUT",
        limit=30,
    )
    payload["calls_in"] = await get_neighbors(
        symbol_id=symbol_id,
        project=project,
        branch=branch,
        relation="CALLS",
        direction="IN",
        limit=15,
    )
    payload["calls_out"] = await get_neighbors(
        symbol_id=symbol_id,
        project=project,
        branch=branch,
        relation="CALLS",
        direction="OUT",
        limit=15,
    )
    payload["file_neighbors"] = await get_file_neighbors(
        file=question.target.file,
        project=project,
        branch=branch,
        limit=20,
    )
    return payload


async def run(project: str, branch: str | None, root: Path) -> None:
    rows = []
    graph_total = 0
    plain_total = 0
    graph_contexts: dict[Target, str] = {}

    for question in QUESTIONS:
        if question.target not in graph_contexts:
            graph_contexts[question.target] = compact_json(
                await graph_context(question, project, branch)
            )
        graph_text = graph_contexts[question.target]
        plain_text = read_plain_context(root, question.target.file)
        graph_tokens = estimate_tokens(graph_text)
        plain_tokens = estimate_tokens(plain_text)
        graph_total += graph_tokens
        plain_total += plain_tokens
        rows.append(
            {
                "question": question.text,
                "symbol": question.target.symbol,
                "file": question.target.file,
                "graph_tokens": graph_tokens,
                "plain_tokens": plain_tokens,
                "delta_tokens": plain_tokens - graph_tokens,
                "reduction_pct": round((1 - graph_tokens / plain_tokens) * 100, 1)
                if plain_tokens
                else 0,
            }
        )

    summary = {
        "project": project,
        "branch": branch,
        "questions": len(QUESTIONS),
        "graph_tokens": graph_total,
        "plain_tokens": plain_total,
        "delta_tokens": plain_total - graph_total,
        "reduction_pct": round((1 - graph_total / plain_total) * 100, 1)
        if plain_total
        else 0,
    }
    print(json.dumps({"summary": summary, "rows": rows}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Indexed CodeGraph project name")
    parser.add_argument("--branch", default=None, help="Indexed branch name")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("api"),
        help="Source root used for the plain-context baseline",
    )
    args = parser.parse_args()
    asyncio.run(run(args.project, args.branch, args.root.resolve()))


if __name__ == "__main__":
    main()
