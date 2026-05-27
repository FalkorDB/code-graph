"""End-to-end MCP smoke test.

Spawns `cgraph-mcp` over stdio, lists tools, indexes the
code-graph repo itself, and exercises `search_code`,
`get_callers`, and `impact_analysis`. Prints a compact pass/fail line per
tool.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = REPO_ROOT / "api"
PROJECT_NAME = "code-graph-mcp-smoke"
BRANCH = "smoke"


def _pretty(result):
    """Pull the first text payload out of a CallToolResult."""
    for chunk in result.content:
        if hasattr(chunk, "text"):
            try:
                return json.loads(chunk.text)
            except Exception:
                return chunk.text
    # No text chunks — show structured content if MCP put the payload there.
    if hasattr(result, "structuredContent") and result.structuredContent is not None:
        return result.structuredContent
    return None


async def main() -> int:
    env = {
        **os.environ,
        "FALKORDB_HOST": os.environ.get("FALKORDB_HOST", "127.0.0.1"),
        "FALKORDB_PORT": os.environ.get("FALKORDB_PORT", "6390"),
    }

    params = StdioServerParameters(
        command="cgraph-mcp",
        args=[],
        env=env,
    )

    fails = 0

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = sorted(t.name for t in tools.tools)
            print(f"[tools] {len(tool_names)}: {tool_names}")
            expected = {
                "index_repo",
                "search_code",
                "get_callers",
                "get_callees",
                "get_dependencies",
                "impact_analysis",
                "find_path",
                "ask",
            }
            missing = expected - set(tool_names)
            if missing:
                print(f"[FAIL] missing tools: {missing}")
                fails += 1

            print(f"[index_repo] indexing {INDEX_PATH} ...")
            idx = await session.call_tool(
                "index_repo",
                {
                    "path_or_url": str(INDEX_PATH),
                    "branch": BRANCH,
                    "ignore": [".venv", "node_modules", ".git", "app/dist"],
                },
            )
            idx_payload = _pretty(idx)
            print(f"[index_repo] -> {json.dumps(idx_payload)[:200]}")
            if not isinstance(idx_payload, dict) or idx_payload.get("error"):
                print("[FAIL] index_repo did not return ok payload")
                fails += 1
                return 1
            project_name = idx_payload["project_name"]
            branch_name = idx_payload["branch"]
            print(f"[index_repo] graph={idx_payload['graph_name']} project={project_name}")

            print("[search_code] prefix='index_repo'")
            sr = await session.call_tool(
                "search_code",
                {"prefix": "index_repo", "project": project_name, "branch": branch_name},
            )
            sr_payload = _pretty(sr)
            print(f"[search_code] -> {json.dumps(sr_payload)[:300]}")
            if isinstance(sr_payload, list):
                hits = sr_payload
            elif isinstance(sr_payload, dict) and "results" in sr_payload:
                hits = sr_payload["results"]
            elif isinstance(sr_payload, dict) and "id" in sr_payload:
                hits = [sr_payload]
            else:
                hits = []
            if not hits:
                print("[FAIL] search_code returned no hits for index_repo")
                fails += 1
                first_id = None
            else:
                first_id = hits[0].get("id")
                print(f"[search_code] picked id={first_id} name={hits[0].get('name')}")

            if first_id is not None:
                print(f"[get_callers] id={first_id}")
                gc = await session.call_tool(
                    "get_callers",
                    {
                        "symbol_id": first_id,
                        "project": project_name,
                        "branch": branch_name,
                    },
                )
                gc_payload = _pretty(gc)
                # Some MCP servers return list payloads in structuredContent only.
                gc_struct = getattr(gc, "structuredContent", None)
                print(f"[get_callers] -> {json.dumps(gc_payload)[:300]} struct={json.dumps(gc_struct)[:200]}")
                # Acceptable shapes: list of caller dicts, or {"callers": [...]}.
                callers = None
                if isinstance(gc_payload, list):
                    callers = gc_payload
                elif isinstance(gc_payload, dict) and "callers" in gc_payload:
                    callers = gc_payload["callers"]
                elif isinstance(gc_struct, dict) and "result" in gc_struct:
                    callers = gc_struct["result"]
                if callers is None:
                    print("[FAIL] get_callers returned no recognizable payload")
                    fails += 1
                else:
                    print(f"[get_callers] {len(callers)} callers")

                print("[impact_analysis] depth=2")
                ia = await session.call_tool(
                    "impact_analysis",
                    {
                        "symbol_id": first_id,
                        "depth": 2,
                        "project": project_name,
                        "branch": branch_name,
                    },
                )
                ia_payload = _pretty(ia)
                ia_struct = getattr(ia, "structuredContent", None)
                print(f"[impact_analysis] -> {json.dumps(ia_payload)[:300]} struct={json.dumps(ia_struct)[:200]}")
                impacted = None
                if isinstance(ia_payload, dict) and "impacted" in ia_payload:
                    impacted = ia_payload["impacted"]
                elif isinstance(ia_struct, dict) and "impacted" in ia_struct:
                    impacted = ia_struct["impacted"]
                elif isinstance(ia_struct, dict) and "result" in ia_struct:
                    impacted = ia_struct["result"]
                if impacted is None:
                    print("[FAIL] impact_analysis no 'impacted' field")
                    fails += 1
                else:
                    print(f"[impact_analysis] {len(impacted)} impacted")

    if fails:
        print(f"\n=== {fails} FAILED ===")
        return 1
    print("\n=== ALL OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
