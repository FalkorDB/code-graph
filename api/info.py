import os
import redis
import redis.asyncio as aioredis
import logging
from typing import Optional, Dict

from .graph import DEFAULT_BRANCH

# Configure logging
logging.basicConfig(level=logging.INFO)


def _normalize_branch(branch: Optional[str]) -> str:
    if branch is None or branch == "":
        return DEFAULT_BRANCH
    return branch


def _repo_info_key(repo_name: str, branch: Optional[str] = None) -> str:
    """Compose the Redis hash key holding ``(repo, branch)`` metadata.

    The curly-brace hash-tag stays on ``repo_name`` so per-branch metadata
    keys land on the same FalkorDB cluster slot as the equivalent graph
    keys (e.g. ``{repo}:{branch}_git``).
    """
    branch = _normalize_branch(branch)
    return f"{{{repo_name}}}:{branch}_info"


def _legacy_repo_info_key(repo_name: str) -> str:
    """Pre-T17 key shape, retained for the migration helper / fallback reads."""
    return f"{{{repo_name}}}_info"

def get_redis_connection() -> redis.Redis:
    """
    Establishes a connection to Redis using environment variables.

    Returns:
        redis.Redis: A Redis connection object.
    """
    try:
        return redis.Redis(
            host             = os.getenv('FALKORDB_HOST', "localhost"),
            port             = int(os.getenv('FALKORDB_PORT', "6379")),
            username         = os.getenv('FALKORDB_USERNAME'),
            password         = os.getenv('FALKORDB_PASSWORD'),
            decode_responses = True  # To ensure string responses
        )
    except Exception as e:
        logging.error(f"Error connecting to Redis: {e}")
        raise


def set_repo_commit(repo_name: str, commit_hash: str, branch: Optional[str] = None) -> None:
    """Save processed commit hash to the DB for ``(repo_name, branch)``."""

    try:
        r = get_redis_connection()
        key = _repo_info_key(repo_name, branch)  # Safely format the key

        # Save the repository URL
        r.hset(key, 'commit', commit_hash)
        logging.info(f"Repository set current commit to: {commit_hash}")

    except Exception as e:
        logging.error(f"Error saving repo info for '{repo_name}': {e}")
        raise


def get_repo_commit(repo_name: str, branch: Optional[str] = None) -> str:
    """Get the current commit the repo is at for ``(repo_name, branch)``."""

    try:
        r = get_redis_connection()
        key = _repo_info_key(repo_name, branch)

        # Retrieve all information about the repository
        commit_hash = r.hget(key, "commit")
        if not commit_hash:
            # Fall back to the legacy single-key shape, so reads against
            # un-migrated graphs still succeed.
            commit_hash = r.hget(_legacy_repo_info_key(repo_name), "commit")
        if not commit_hash:
            logging.warning(f"Failed to retrieve {repo_name} current commit hash")
            return None

        logging.info(f"Repository current commit hash: {commit_hash}")
        return commit_hash

    except Exception as e:
        logging.error(f"Error retrieving '{repo_name}' current commit hash: {e}")
        raise


def save_repo_info(repo_name: str, repo_url: str, branch: Optional[str] = None) -> None:
    """
    Saves repository information (URL) to Redis under a hash named
    ``{repo_name}:{branch}_info``.

    Args:
        repo_name (str): The name of the repository.
        repo_url (str): The URL of the repository.
        branch (Optional[str]): The branch. Defaults to ``_default``.
    """

    try:
        r = get_redis_connection()
        key = _repo_info_key(repo_name, branch)

        # Save the repository URL
        r.hset(key, 'repo_url', repo_url)
        logging.info(f"Repository info saved for {repo_name}")

    except Exception as e:
        logging.error(f"Error saving repo info for '{repo_name}': {e}")
        raise

def get_repo_info(repo_name: str, branch: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Retrieves repository information from Redis for ``(repo_name, branch)``.

    Falls back to the legacy single-key shape so pre-migration graphs
    remain readable.

    Args:
        repo_name (str): The name of the repository.
        branch (Optional[str]): The branch. Defaults to ``_default``.

    Returns:
        Optional[Dict[str, str]]: A dictionary of repository information,
        or ``None`` if not found.
    """

    try:
        r = get_redis_connection()
        key = _repo_info_key(repo_name, branch)

        # Retrieve all information about the repository
        repo_info = r.hgetall(key)
        if not repo_info:
            repo_info = r.hgetall(_legacy_repo_info_key(repo_name))
        if not repo_info:
            logging.warning(f"No repository info found for {repo_name}")
            return None

        logging.info(f"Repository info retrieved for {repo_name}")
        return repo_info

    except Exception as e:
        logging.error(f"Error retrieving repo info for '{repo_name}': {e}")
        raise


# ---------------------------------------------------------------------------
# Async versions (for async endpoints)
# ---------------------------------------------------------------------------

async def async_get_redis_connection() -> aioredis.Redis:
    return aioredis.Redis(
        host=os.getenv('FALKORDB_HOST', "localhost"),
        port=int(os.getenv('FALKORDB_PORT', "6379")),
        username=os.getenv('FALKORDB_USERNAME'),
        password=os.getenv('FALKORDB_PASSWORD'),
        decode_responses=True,
    )


async def async_get_repo_info(repo_name: str, branch: Optional[str] = None) -> Optional[Dict[str, str]]:
    try:
        r = await async_get_redis_connection()
        try:
            key = _repo_info_key(repo_name, branch)
            repo_info = await r.hgetall(key)
            if not repo_info:
                repo_info = await r.hgetall(_legacy_repo_info_key(repo_name))
            if not repo_info:
                logging.warning(f"No repository info found for {repo_name}")
                return None
            logging.info(f"Repository info retrieved for {repo_name}")
            return repo_info
        finally:
            await r.aclose()
    except Exception as e:
        logging.error(f"Error retrieving repo info for '{repo_name}': {e}")
        raise

