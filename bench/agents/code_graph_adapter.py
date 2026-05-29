"""HTTP adapter to code-graph's FastAPI service for the benchmark.

The benchmark agent runs inside SWE-agent's container; this module is the
in-container tool surface for the `code_graph` config. Each public function
maps 1:1 onto an SWE-agent tool name registered in
`bench/tools/code_graph/tools.yaml`.

We talk to the host-side code-graph service over HTTP (see backend.service_url
in tools.yaml). The five primitives below — plus `find_symbol` and
`note_edit` — are the only tools the code-graph config gets. The GraphRAG
`chat` endpoint is intentionally NOT exposed (Q2 grill decision).

This module is pure-HTTP (httpx). It does no model calls and no graph
traversal of its own. Token cost on the code-graph side comes only from
the agent's LLM reading these tool responses.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


DEFAULT_TIMEOUT_SEC = 30.0


class CodeGraphClient:
    """Thin synchronous client. SWE-agent tools are typically sync."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SEC,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("CODEGRAPH_URL")
                         or "http://host.docker.internal:5000").rstrip("/")
        self.token = token or os.getenv("SECRET_TOKEN") or os.getenv("CODEGRAPH_TOKEN")
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CodeGraphClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Primitive tools — names match bench/tools/code_graph/tools.yaml
    # ------------------------------------------------------------------

    def graph_entities(self, repo: str) -> dict[str, Any]:
        """Fetch the sub-graph for a repo (paginated server-side)."""
        r = self._client.get("/api/graph_entities", params={"repo": repo})
        r.raise_for_status()
        return r.json()

    def get_neighbors(self, repo: str, node_ids: list[int]) -> dict[str, Any]:
        r = self._client.post(
            "/api/get_neighbors",
            json={"repo": repo, "node_ids": list(node_ids)},
        )
        r.raise_for_status()
        return r.json()

    def find_paths(self, repo: str, src: int, dest: int) -> dict[str, Any]:
        r = self._client.post(
            "/api/find_paths",
            json={"repo": repo, "src": src, "dest": dest},
        )
        r.raise_for_status()
        return r.json()

    def auto_complete(self, repo: str, prefix: str) -> dict[str, Any]:
        r = self._client.post(
            "/api/auto_complete",
            json={"repo": repo, "prefix": prefix},
        )
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # Helper tools — bench-only, not part of the FastAPI surface
    # ------------------------------------------------------------------

    def find_symbol(self, repo: str, name: str) -> list[dict[str, Any]]:
        """Exact-name lookup. Thin wrapper around auto_complete + filter.

        auto_complete returns prefix matches; the agent often wants exact
        matches. Doing this client-side keeps the FastAPI surface untouched.

        The auto_complete payload nests the symbol name under
        `item["properties"]["name"]` (FalkorDB node properties), so we look
        there first and only fall back to a top-level `name` for older /
        flatter shapes the tests may pass in.
        """
        payload = self.auto_complete(repo, name)
        results = payload.get("completions") or payload.get("results") or payload
        if isinstance(results, dict):
            results = results.get("items", [])
        out: list[dict[str, Any]] = []
        for item in (results or []):
            if not isinstance(item, dict):
                continue
            props = item.get("properties") if isinstance(item.get("properties"), dict) else {}
            if props.get("name") == name or item.get("name") == name:
                out.append(item)
        return out

    def note_edit(self, repo: str, path: str) -> dict[str, Any]:
        """Tell code-graph the agent just edited `path`; trigger an
        incremental re-index of that single file.

        Implemented by hitting analyze_folder with the file's directory.
        Until the backend grows a true single-file endpoint this is the
        cheapest available approximation. Failures are non-fatal — the
        agent should continue and accept a slightly stale graph.
        """
        try:
            r = self._client.post(
                "/api/analyze_folder",
                json={"path": os.path.dirname(path) or path, "ignore": []},
            )
            r.raise_for_status()
            return {"ok": True, "reindexed": path}
        except httpx.HTTPError as exc:
            return {"ok": False, "error": str(exc), "path": path}

    # ------------------------------------------------------------------
    # v2 agent verbs — parity with the MCP transport.
    # ------------------------------------------------------------------
    # Each hits a /api/v2/* endpoint that wraps the same async function
    # the FastMCP server exposes. Output shape is identical between
    # transports, so cg / cg-mcp benchmarks measure transport overhead
    # rather than API-surface differences.

    def search_code(self, project: str, prefix: str, branch: str | None = None,
                    limit: int = 10) -> list[dict[str, Any]]:
        body: dict[str, Any] = {"project": project, "prefix": prefix, "limit": limit}
        if branch:
            body["branch"] = branch
        r = self._client.post("/api/v2/search_code", json=body)
        r.raise_for_status()
        return r.json()

    def get_callers(self, project: str, symbol_id: int, branch: str | None = None,
                    limit: int = 50) -> list[dict[str, Any]]:
        body: dict[str, Any] = {"project": project, "symbol_id": symbol_id, "limit": limit}
        if branch:
            body["branch"] = branch
        r = self._client.post("/api/v2/get_callers", json=body)
        r.raise_for_status()
        return r.json()

    def get_callees(self, project: str, symbol_id: int, branch: str | None = None,
                    limit: int = 50) -> list[dict[str, Any]]:
        body: dict[str, Any] = {"project": project, "symbol_id": symbol_id, "limit": limit}
        if branch:
            body["branch"] = branch
        r = self._client.post("/api/v2/get_callees", json=body)
        r.raise_for_status()
        return r.json()

    def get_dependencies(self, project: str, symbol_id: int, branch: str | None = None,
                         limit: int = 50) -> list[dict[str, Any]]:
        body: dict[str, Any] = {"project": project, "symbol_id": symbol_id, "limit": limit}
        if branch:
            body["branch"] = branch
        r = self._client.post("/api/v2/get_dependencies", json=body)
        r.raise_for_status()
        return r.json()

    def impact_analysis(self, project: str, symbol_id: int,
                        branch: str | None = None,
                        direction: str = "IN",
                        depth: int = 3) -> list[dict[str, Any]]:
        body: dict[str, Any] = {
            "project": project, "symbol_id": symbol_id,
            "direction": direction, "depth": depth,
        }
        if branch:
            body["branch"] = branch
        r = self._client.post("/api/v2/impact_analysis", json=body)
        r.raise_for_status()
        return r.json()

    def find_path_v2(self, project: str, source_id: int, dest_id: int,
                     branch: str | None = None,
                     max_paths: int = 10) -> list[dict[str, Any]]:
        body: dict[str, Any] = {
            "project": project, "source_id": source_id, "dest_id": dest_id,
            "max_paths": max_paths,
        }
        if branch:
            body["branch"] = branch
        r = self._client.post("/api/v2/find_path", json=body)
        r.raise_for_status()
        return r.json()

    def ask_v2(self, project: str, question: str, branch: str | None = None) -> Any:
        body: dict[str, Any] = {"project": project, "question": question}
        if branch:
            body["branch"] = branch
        r = self._client.post("/api/v2/ask", json=body)
        r.raise_for_status()
        return r.json()


# Convenience function aliases — the SWE-agent tool registry expects
# top-level callables. Each spins up a short-lived client; for hot loops
# the agent should keep a CodeGraphClient open instead.

def graph_entities(repo: str, **kw: Any) -> dict[str, Any]:
    with CodeGraphClient(**kw) as c:
        return c.graph_entities(repo)


def get_neighbors(repo: str, node_ids: list[int], **kw: Any) -> dict[str, Any]:
    with CodeGraphClient(**kw) as c:
        return c.get_neighbors(repo, node_ids)


def find_paths(repo: str, src: int, dest: int, **kw: Any) -> dict[str, Any]:
    with CodeGraphClient(**kw) as c:
        return c.find_paths(repo, src, dest)


def auto_complete(repo: str, prefix: str, **kw: Any) -> dict[str, Any]:
    with CodeGraphClient(**kw) as c:
        return c.auto_complete(repo, prefix)


def find_symbol(repo: str, name: str, **kw: Any) -> list[dict[str, Any]]:
    with CodeGraphClient(**kw) as c:
        return c.find_symbol(repo, name)


def note_edit(repo: str, path: str, **kw: Any) -> dict[str, Any]:
    with CodeGraphClient(**kw) as c:
        return c.note_edit(repo, path)
