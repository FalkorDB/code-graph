"""T17 (#651): promote legacy graphs into the per-branch namespace.

Before T17 a repo named ``myrepo`` lived at:

  * Graph key:   ``myrepo``
  * Info hash:   ``{myrepo}_info``
  * Git graph:   ``{myrepo}_git``

After T17, the new format is:

  * Graph key:   ``code:myrepo:_default``
  * Info hash:   ``{myrepo}:_default_info``
  * Git graph:   ``{myrepo}:_default_git``

This module renames every legacy artifact in place. It is safe to run
multiple times — already-migrated graphs are skipped — and exposes a
``--dry-run`` mode via ``cgraph migrate`` for previewing changes.
"""

from __future__ import annotations

import logging
import os
from typing import Iterable

from falkordb import FalkorDB

from ..graph import (
    DEFAULT_BRANCH,
    compose_graph_name,
    parse_graph_name,
)
from ..info import _legacy_repo_info_key, _repo_info_key


logger = logging.getLogger(__name__)


def _connect() -> FalkorDB:
    return FalkorDB(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=os.getenv("FALKORDB_PORT", 6379),
        username=os.getenv("FALKORDB_USERNAME", None),
        password=os.getenv("FALKORDB_PASSWORD", None),
    )


def _legacy_graphs(all_graphs: Iterable[str]) -> list[str]:
    """Return graphs that look like the pre-T17 single-name shape."""

    legacy = []
    for name in all_graphs:
        # Already migrated?
        if parse_graph_name(name) is not None:
            continue
        # System graphs etc. — also skip the ``_tmp`` mid-migration name and
        # the per-repo ``_git`` companion (handled separately, see below).
        if name.endswith("_tmp") or name.endswith("_schema") or name.endswith("_git"):
            continue
        legacy.append(name)
    return legacy


def _rename_graph(db: FalkorDB, src: str, dst: str, *, dry_run: bool) -> bool:
    """Copy ``src`` to ``dst`` and delete ``src``. Returns ``True`` on success.

    Skips with ``False`` (and a warning) when ``dst`` already exists.
    """

    if db.connection.exists(dst):
        # Recovery path: a previous migration may have copied ``src`` to
        # ``dst`` but crashed before deleting ``src``. If both still exist,
        # finish the job rather than skipping forever.
        if db.connection.exists(src):
            if dry_run:
                logger.info(
                    "[dry-run] would delete leftover legacy graph %s (dst %s already exists)",
                    src, dst,
                )
                return True
            db.select_graph(src).delete()
            logger.info(
                "Deleted leftover legacy graph %s (dst %s already exists)",
                src, dst,
            )
            return True
        logger.warning("Target graph %s already exists — skipping rename of %s", dst, src)
        return False
    if dry_run:
        logger.info("[dry-run] would rename graph %s -> %s", src, dst)
        return True
    g = db.select_graph(src)
    g.copy(dst)
    g.delete()
    logger.info("Renamed graph %s -> %s", src, dst)
    return True


def _rename_redis_key(db: FalkorDB, src: str, dst: str, *, dry_run: bool) -> bool:
    """Rename a Redis hash key. Idempotent — skips when ``dst`` already exists.

    Uses the underlying ``redis-py`` connection on the FalkorDB client so
    we don't need a separate Redis connection.
    """

    conn = db.connection
    if not conn.exists(src):
        return False
    if conn.exists(dst):
        logger.warning("Target Redis key %s already exists — skipping rename of %s", dst, src)
        return False
    if dry_run:
        logger.info("[dry-run] would rename Redis key %s -> %s", src, dst)
        return True
    conn.rename(src, dst)
    logger.info("Renamed Redis key %s -> %s", src, dst)
    return True


def run_migration(*, dry_run: bool = False) -> dict:
    """Run the per-branch migration once.

    Returns a small summary dict suitable for the CLI to print as JSON::

        {"status": "ok", "graphs_renamed": int, "info_renamed": int,
         "git_renamed": int, "dry_run": bool, "skipped": list[str]}
    """

    db = _connect()
    all_graphs = list(db.list_graphs())
    legacy = _legacy_graphs(all_graphs)

    graphs_renamed = 0
    info_renamed = 0
    git_renamed = 0
    skipped: list[str] = []

    for project in legacy:
        # Rename the main code graph itself.
        new_graph = compose_graph_name(project, DEFAULT_BRANCH)
        if _rename_graph(db, project, new_graph, dry_run=dry_run):
            graphs_renamed += 1
        else:
            skipped.append(project)
            continue

        # Rename the sibling Redis info key, if any.
        legacy_info = _legacy_repo_info_key(project)
        new_info = _repo_info_key(project, DEFAULT_BRANCH)
        if _rename_redis_key(db, legacy_info, new_info, dry_run=dry_run):
            info_renamed += 1

        # Rename the sibling ``{project}_git`` graph, if any.
        legacy_git = "{" + project + "}_git"
        new_git = "{" + project + "}:" + DEFAULT_BRANCH + "_git"
        if legacy_git in all_graphs:
            if _rename_graph(db, legacy_git, new_git, dry_run=dry_run):
                git_renamed += 1

    return {
        "status": "ok",
        "dry_run": dry_run,
        "graphs_renamed": graphs_renamed,
        "info_renamed": info_renamed,
        "git_renamed": git_renamed,
        "skipped": skipped,
    }
