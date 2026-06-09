"""Database backend selection for CodeGraph.

The default backend is a regular FalkorDB server addressed by host/port.
Set ``CODE_GRAPH_DB_BACKEND=lite`` to use FalkorDBLite's embedded server.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


LITE_BACKENDS = {"lite", "falkordblite"}
DEFAULT_LITE_PATH = "~/.cache/code-graph/falkordblite.rdb"


def is_lite_backend() -> bool:
    """Return whether CodeGraph should use the embedded FalkorDBLite backend."""
    backend = os.getenv("CODE_GRAPH_DB_BACKEND", "falkordb").strip().lower()
    return backend in LITE_BACKENDS


def _lite_db_path() -> str:
    path = Path(os.getenv("FALKORDB_LITE_PATH", DEFAULT_LITE_PATH)).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def _lite_serverconfig() -> dict[str, str]:
    """Return FalkorDBLite server config from env.

    FalkorDBLite defaults to a private Unix socket. Supplying
    ``FALKORDB_LITE_PORT`` additionally exposes a local TCP port, which is
    useful for libraries that only accept host/port connection settings.
    """
    port = os.getenv("FALKORDB_LITE_PORT")
    if not port:
        return {}
    return {
        "bind": os.getenv("FALKORDB_LITE_HOST", "127.0.0.1"),
        "port": port,
    }


def create_falkordb() -> Any:
    """Create a sync FalkorDB client for the configured backend."""
    if is_lite_backend():
        try:
            from redislite.falkordb_client import FalkorDB as LiteFalkorDB
        except ImportError as e:
            raise RuntimeError(
                "CODE_GRAPH_DB_BACKEND=lite requires the optional "
                "`falkordblite` dependency. Install with "
                "`uv sync --extra light` or `pip install 'falkordb-code-graph[light]'`."
            ) from e

        return LiteFalkorDB(_lite_db_path(), serverconfig=_lite_serverconfig())

    from falkordb import FalkorDB

    return FalkorDB(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=os.getenv("FALKORDB_PORT", 6379),
        username=os.getenv("FALKORDB_USERNAME", None),
        password=os.getenv("FALKORDB_PASSWORD", None),
    )


def create_async_falkordb() -> Any:
    """Create an async FalkorDB client for the configured backend."""
    if is_lite_backend():
        try:
            from redislite.async_falkordb_client import AsyncFalkorDB as LiteAsyncFalkorDB
        except ImportError as e:
            raise RuntimeError(
                "CODE_GRAPH_DB_BACKEND=lite requires the optional "
                "`falkordblite` dependency. Install with "
                "`uv sync --extra light` or `pip install 'falkordb-code-graph[light]'`."
            ) from e

        client = LiteAsyncFalkorDB(_lite_db_path(), serverconfig=_lite_serverconfig())
        if not hasattr(client, "aclose"):
            client.aclose = client.close
        return client

    from falkordb.asyncio import FalkorDB as AsyncFalkorDB

    return AsyncFalkorDB(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", 6379)),
        username=os.getenv("FALKORDB_USERNAME", None),
        password=os.getenv("FALKORDB_PASSWORD", None),
    )


def create_redis_connection() -> Any:
    """Create a sync Redis-compatible connection for metadata operations."""
    if is_lite_backend():
        return create_falkordb().connection

    import redis

    return redis.Redis(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
        username=os.getenv("FALKORDB_USERNAME"),
        password=os.getenv("FALKORDB_PASSWORD"),
        decode_responses=True,
    )


def create_async_redis_connection() -> Any:
    """Create an async Redis-compatible connection for metadata operations."""
    if is_lite_backend():
        return create_async_falkordb().connection

    import redis.asyncio as aioredis

    return aioredis.Redis(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
        username=os.getenv("FALKORDB_USERNAME"),
        password=os.getenv("FALKORDB_PASSWORD"),
        decode_responses=True,
    )


def graphrag_connection_kwargs() -> dict[str, Any]:
    """Return host/port kwargs for GraphRAG SDK constructors.

    GraphRAG SDK accepts host/port only. FalkorDBLite's private Unix socket is
    therefore usable for structural tools but not for GraphRAG unless a local
    TCP port is explicitly enabled with ``FALKORDB_LITE_PORT``.
    """
    if is_lite_backend():
        port = os.getenv("FALKORDB_LITE_PORT")
        if not port:
            raise RuntimeError(
                "GraphRAG requires host/port access. When using "
                "CODE_GRAPH_DB_BACKEND=lite, set FALKORDB_LITE_PORT to expose "
                "the embedded FalkorDBLite instance on localhost."
            )
        create_falkordb()
        return {
            "host": os.getenv("FALKORDB_LITE_HOST", "127.0.0.1"),
            "port": int(port),
            "username": None,
            "password": None,
        }

    return {
        "host": os.getenv("FALKORDB_HOST", "localhost"),
        "port": int(os.getenv("FALKORDB_PORT", 6379)),
        "username": os.getenv("FALKORDB_USERNAME", None),
        "password": os.getenv("FALKORDB_PASSWORD", None),
    }
