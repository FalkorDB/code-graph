"""Corpus-cache tests for the search_code hot path (PR #701).

``search_code``'s ranker caches the query-independent corpus (three full-graph
reads + tokenization) per ``(graph, project)`` and applies only a cheap
per-query overlay on each call. These tests pin the cache contract:

* a warm call reuses the corpus (no rebuild) and returns identical results;
* the ``(node_count, edge_count, commit)`` signature probe rebuilds when the
  graph mutates;
* ``reset_corpus_cache`` (the ``index_repo`` hook) forces a rebuild;
* concurrent first-time calls rebuild exactly once (per-key lock).

They build tiny synthetic graphs with raw Cypher rather than the shared
session ``indexed_fixture`` so a mutation test can never corrupt other tests.
Each needs a reachable FalkorDB.
"""

from __future__ import annotations

import os
import uuid

import pytest


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _falkordb_reachable() -> bool:
    try:
        from falkordb import FalkorDB

        host = os.getenv("FALKORDB_HOST", "localhost")
        port = int(os.getenv("FALKORDB_PORT", 6379))
        return bool(FalkorDB(host=host, port=port, socket_timeout=1).connection.ping())
    except Exception:
        return False


@pytest.fixture(autouse=True)
def _clean_cache():
    """Reset module-global cache state around every test."""
    import api.mcp.tools.structural as S

    S.reset_corpus_cache()
    S._CORPUS_LOCKS.clear()
    yield
    S.reset_corpus_cache()
    S._CORPUS_LOCKS.clear()


@pytest.fixture
def synth_graph():
    """A tiny two-file graph seeded via raw Cypher, dropped on teardown.

    Paths embed ``/<project>/`` so ``_relativize`` yields stable repo-relative
    keys (project == ``proj``). Yields ``(graph_name, project, branch)``.
    """
    if not _falkordb_reachable():
        pytest.skip("FalkorDB not reachable on $FALKORDB_HOST:$FALKORDB_PORT")

    from falkordb import FalkorDB

    project = "proj"
    branch = f"cachetest-{uuid.uuid4().hex[:8]}"
    name = f"code:{project}:{branch}"

    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", 6379))
    db = FalkorDB(host=host, port=port)
    g = db.select_graph(name)
    g.query(
        "CREATE "
        "(a:File {path:'/root/proj/alpha.py'}), "
        "(b:File {path:'/root/proj/beta.py'}), "
        "(fa:Function {name:'parse_tokens', path:'/root/proj/alpha.py', "
        "src_start:1, src_end:9, doc:'parse the tokens of a query'}), "
        "(fb:Function {name:'resolve_symbol', path:'/root/proj/beta.py', "
        "src_start:1, src_end:9, doc:'resolve a symbol to its node'}), "
        "(fb)-[:CALLS]->(fa)"
    )
    try:
        yield name, project, branch
    finally:
        try:
            g.delete()
        except Exception:
            pass


def _spy_build(monkeypatch):
    """Wrap _build_corpus with a call counter; returns the counter dict."""
    import api.mcp.tools.structural as S

    calls = {"n": 0}
    orig = S._build_corpus

    async def counting(g, project):
        calls["n"] += 1
        return await orig(g, project)

    monkeypatch.setattr(S, "_build_corpus", counting)
    return calls


async def test_warm_call_reuses_corpus(synth_graph, monkeypatch):
    import api.mcp.tools.structural as S
    from api.graph import AsyncGraphQuery

    name, project, branch = synth_graph
    calls = _spy_build(monkeypatch)

    g = AsyncGraphQuery(name)
    try:
        first = await S._hybrid_rank(g, "parse tokens", project)
        second = await S._hybrid_rank(g, "parse tokens", project)
    finally:
        await g.close()

    assert calls["n"] == 1, "second call should hit the cache, not rebuild"
    assert first == second
    assert any("alpha.py" in r["file"] for r in first), first


async def test_different_queries_share_one_corpus(synth_graph, monkeypatch):
    import api.mcp.tools.structural as S
    from api.graph import AsyncGraphQuery

    name, project, branch = synth_graph
    calls = _spy_build(monkeypatch)

    g = AsyncGraphQuery(name)
    try:
        await S._hybrid_rank(g, "parse tokens", project)
        await S._hybrid_rank(g, "resolve symbol", project)
        await S._hybrid_rank(g, "nonsense_zzz", project)
    finally:
        await g.close()

    assert calls["n"] == 1, "corpus is query-independent: build once for many queries"


async def test_signature_change_triggers_rebuild(synth_graph, monkeypatch):
    import api.mcp.tools.structural as S
    from api.graph import AsyncGraphQuery

    name, project, branch = synth_graph
    calls = _spy_build(monkeypatch)

    g = AsyncGraphQuery(name)
    try:
        await S._hybrid_rank(g, "parse tokens", project)
        assert calls["n"] == 1

        # Mutate the graph: a new File changes node count -> signature changes.
        await g._query("CREATE (:File {path:'/root/proj/gamma.py'})")

        results = await S._hybrid_rank(g, "gamma", project)
    finally:
        await g.close()

    assert calls["n"] == 2, "node-count change must invalidate the cached corpus"
    assert any("gamma.py" in r["file"] for r in results), results


async def test_reset_corpus_cache_forces_rebuild(synth_graph, monkeypatch):
    import api.mcp.tools.structural as S
    from api.graph import AsyncGraphQuery

    name, project, branch = synth_graph
    calls = _spy_build(monkeypatch)

    g = AsyncGraphQuery(name)
    try:
        await S._hybrid_rank(g, "parse tokens", project)
        assert calls["n"] == 1

        S.reset_corpus_cache(name)
        await S._hybrid_rank(g, "parse tokens", project)
    finally:
        await g.close()

    assert calls["n"] == 2, "explicit reset (index_repo hook) must force a rebuild"


async def test_reset_all_clears_every_graph(synth_graph, monkeypatch):
    import api.mcp.tools.structural as S
    from api.graph import AsyncGraphQuery

    name, project, branch = synth_graph
    calls = _spy_build(monkeypatch)

    g = AsyncGraphQuery(name)
    try:
        await S._hybrid_rank(g, "parse tokens", project)
        assert calls["n"] == 1
        assert len(S._CORPUS_CACHE) == 1

        S.reset_corpus_cache()  # graph_name=None -> clear everything
        assert len(S._CORPUS_CACHE) == 0

        await S._hybrid_rank(g, "parse tokens", project)
    finally:
        await g.close()

    assert calls["n"] == 2


async def test_concurrent_first_calls_build_once(synth_graph, monkeypatch):
    import asyncio

    import api.mcp.tools.structural as S
    from api.graph import AsyncGraphQuery

    name, project, branch = synth_graph
    calls = _spy_build(monkeypatch)

    async def one():
        g = AsyncGraphQuery(name)
        try:
            return await S._hybrid_rank(g, "parse tokens", project)
        finally:
            await g.close()

    results = await asyncio.gather(*[one() for _ in range(5)])

    assert calls["n"] == 1, "per-key lock must collapse concurrent cold builds to one"
    assert all(r == results[0] for r in results)


async def test_mutation_during_build_is_not_cached(synth_graph, monkeypatch):
    """A graph that changes across the reads must not be stored (torn snapshot)."""
    import api.mcp.tools.structural as S
    from api.graph import AsyncGraphQuery

    name, project, branch = synth_graph

    g_probe = AsyncGraphQuery(name)
    orig = S._build_corpus

    async def mutate_then_build(g, project):
        # Simulate a concurrent writer landing between the pre- and post-build
        # signature probes by mutating the graph inside the build.
        corpus = await orig(g, project)
        await g_probe._query("CREATE (:File {path:'/root/proj/delta.py'})")
        return corpus

    monkeypatch.setattr(S, "_build_corpus", mutate_then_build)

    g = AsyncGraphQuery(name)
    try:
        await S._hybrid_rank(g, "parse tokens", project)
    finally:
        await g.close()
        await g_probe.close()

    assert len(S._CORPUS_CACHE) == 0, "torn (mid-build mutation) corpus must not persist"
