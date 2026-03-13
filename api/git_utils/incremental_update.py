"""Incremental graph update engine.

Given a before/after commit SHA pair, computes the file-level diff,
applies additions/deletions/modifications to the FalkorDB code graph,
and bookmarks the new commit SHA in Redis so the system can resume
correctly after restarts or failures.
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from pygit2.enums import CheckoutStrategy
from pygit2.repository import Repository

from ..analyzers.source_analyzer import SourceAnalyzer
from ..graph import Graph
from ..info import set_repo_commit
from .git_utils import classify_changes

logger = logging.getLogger(__name__)


def repo_local_path(repo_name: str) -> Path:
    """Return the local filesystem path for a cloned repository.

    Respects the ``REPOSITORIES_DIR`` environment variable; falls back to
    ``<cwd>/repositories/<repo_name>`` which matches the convention used by
    :func:`api.project._clone_source`.
    """
    base = os.getenv("REPOSITORIES_DIR", str(Path.cwd() / "repositories"))
    return Path(base) / repo_name


def fetch_remote(repo_path: Path) -> None:
    """Fetch latest changes from the remote *origin*.

    Args:
        repo_path: Absolute path to the local git clone.

    Raises:
        subprocess.CalledProcessError: If the git fetch command fails.
    """
    logger.info("Fetching remote changes for %s", repo_path)
    subprocess.run(
        ["git", "fetch", "origin"],
        cwd=str(repo_path),
        check=True,
        capture_output=True,
        text=True,
    )


def get_remote_head(repo_path: Path, branch: str) -> Optional[str]:
    """Return the full SHA of the remote tracking branch HEAD.

    Args:
        repo_path: Absolute path to the local git clone.
        branch:    Branch name (e.g. ``"main"``).

    Returns:
        The 40-character commit SHA, or ``None`` if the branch does not exist
        on the remote or the command fails.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", f"origin/{branch}"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except subprocess.CalledProcessError:
        logger.warning("Could not resolve origin/%s in %s", branch, repo_path)
        return None


def incremental_update(
    repo_name: str,
    from_sha: str,
    to_sha: str,
    ignore: Optional[list[str]] = None,
) -> dict:
    """Incrementally update the code graph from ``from_sha`` to ``to_sha``.

    Deleted files are removed from the graph.  Modified files are removed
    and then re-analysed.  Added files are analysed and inserted.  The
    commit bookmark stored in Redis is updated to the short ID of ``to_sha``
    on success, matching the convention used by the rest of the system.

    This function is idempotent: if ``from_sha == to_sha`` it returns
    immediately without touching the graph or the bookmark.

    Args:
        repo_name: Graph name in FalkorDB (and repository directory name).
        from_sha:  Commit SHA the graph is currently at (old state).
                   Accepts both abbreviated and full 40-char SHAs.
        to_sha:    Target commit SHA to advance the graph to (new state).
                   Accepts both abbreviated and full 40-char SHAs.
        ignore:    Optional list of path prefixes to skip during analysis.

    Returns:
        A :class:`dict` with keys:

        * ``files_added``    – number of newly added source files processed.
        * ``files_modified`` – number of modified source files re-processed.
        * ``files_deleted``  – number of deleted source files removed.
        * ``commit``         – the short SHA bookmark now stored in Redis.

    Raises:
        ValueError: If the local repository clone cannot be found, or if
            either SHA cannot be resolved.
    """
    if ignore is None:
        ignore = []

    if from_sha == to_sha:
        logger.info(
            "incremental_update: from_sha == to_sha (%s); nothing to do", from_sha
        )
        return {
            "files_added": 0,
            "files_modified": 0,
            "files_deleted": 0,
            "commit": to_sha,
        }

    repo_path = repo_local_path(repo_name)
    if not repo_path.exists():
        raise ValueError(f"Local repository not found at {repo_path}")

    logger.info(
        "Incremental update for '%s': %s -> %s", repo_name, from_sha, to_sha
    )

    repo = Repository(str(repo_path))

    # Resolve commits – accepts both abbreviated and full SHAs
    try:
        from_commit = repo.revparse_single(from_sha)
    except Exception as exc:
        raise ValueError(f"Cannot resolve from_sha '{from_sha}': {exc}") from exc
    try:
        to_commit = repo.revparse_single(to_sha)
    except Exception as exc:
        raise ValueError(f"Cannot resolve to_sha '{to_sha}': {exc}") from exc

    # Compute the file-level diff between the two commits
    analyzer = SourceAnalyzer()
    supported_types = analyzer.supported_types()
    diff = repo.diff(from_commit, to_commit)
    added, deleted, modified = classify_changes(diff, repo, supported_types, ignore)

    logger.info(
        "Diff for '%s': %d added, %d modified, %d deleted",
        repo_name,
        len(added),
        len(modified),
        len(deleted),
    )

    # Checkout target commit so files on disk reflect to_sha
    repo.checkout_tree(to_commit.tree, strategy=CheckoutStrategy.FORCE)
    repo.set_head_detached(to_commit.id)

    # Apply graph changes
    g = Graph(repo_name)

    files_to_remove = deleted + modified
    if files_to_remove:
        logger.info("Removing %d file(s) from graph", len(files_to_remove))
        g.delete_files(files_to_remove)

    files_to_add = added + modified
    if files_to_add:
        logger.info("Inserting/updating %d file(s) in graph", len(files_to_add))
        analyzer.analyze_files(files_to_add, repo_path, g)

    # Persist the new commit bookmark using the short ID for consistency
    # with the rest of the system (build_commit_graph, analyze_sources …)
    new_commit_short = to_commit.short_id
    set_repo_commit(repo_name, new_commit_short)
    logger.info("Graph for '%s' updated to commit %s", repo_name, new_commit_short)

    return {
        "files_added": len(added),
        "files_modified": len(modified),
        "files_deleted": len(deleted),
        "commit": new_commit_short,
    }
