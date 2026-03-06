import os
import redis
import logging
from typing import Optional, Dict

# Configure logging
logging.basicConfig(level=logging.INFO)

def _repo_info_key(repo_name: str) -> str:
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


def set_repo_commit(repo_name: str, commit_hash: str) -> None:
    """Save processed commit hash to the DB"""

    try:
        r = get_redis_connection()
        key = _repo_info_key(repo_name)  # Safely format the key

        # Save the repository URL
        r.hset(key, 'commit', commit_hash)
        logging.info(f"Repository set current commit to: {commit_hash}")

    except Exception as e:
        logging.error(f"Error saving repo info for '{repo_name}': {e}")
        raise


def get_repo_commit(repo_name: str) -> str:
    """Get the current commit the repo is at"""

    try:
        r = get_redis_connection()
        key = _repo_info_key(repo_name)

        # Retrieve all information about the repository
        commit_hash = r.hget(key, "commit")
        if not commit_hash:
            logging.warning(f"Failed to retrieve {repo_name} current commit hash")
            return None

        logging.info(f"Repository current commit hash: {commit_hash}")
        return commit_hash

    except Exception as e:
        logging.error(f"Error retrieving '{repo_name}' current commit hash: {e}")
        raise


def save_repo_info(repo_name: str, repo_url: str) -> None:
    """
    Saves repository information (URL) to Redis under a hash named {repo_name}_info.

    Args:
        repo_name (str): The name of the repository.
        repo_url (str): The URL of the repository.
    """

    try:
        r = get_redis_connection()
        key = _repo_info_key(repo_name)

        # Save the repository URL
        r.hset(key, 'repo_url', repo_url)
        logging.info(f"Repository info saved for {repo_name}")

    except Exception as e:
        logging.error(f"Error saving repo info for '{repo_name}': {e}")
        raise

def get_repo_info(repo_name: str) -> Optional[Dict[str, str]]:
    """
    Retrieves repository information from Redis.

    Args:
        repo_name (str): The name of the repository.

    Returns:
        Optional[Dict[str, str]]: A dictionary of repository information, or None if not found.
    """

    return {'commit': 'eeb5b3a55907a2d23dd6ab8f2985a43b08167810',
            'repo_url': 'https://github.com/redis/redis'}

    try:
        r = get_redis_connection()
        key = _repo_info_key(repo_name)
        
        # Retrieve all information about the repository
        repo_info = r.hgetall(key)
        if not repo_info:
            logging.warning(f"No repository info found for {repo_name}")
            return None
        
        logging.info(f"Repository info retrieved for {repo_name}")
        return repo_info

    except Exception as e:
        logging.error(f"Error retrieving repo info for '{repo_name}': {e}")
        raise

