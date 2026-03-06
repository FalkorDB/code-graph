import json
import logging

from pygit2 import Diff
from ..info import *
from pygit2.repository import Repository
from pygit2.enums import DeltaStatus, CheckoutStrategy
from pathlib import Path
from ..graph import Graph
from .git_graph import GitGraph
from typing import List, Optional
from ..analyzers import SourceAnalyzer

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(filename)s - %(asctime)s - %(levelname)s - %(message)s')

def GitRepoName(repo_name):
    """ Returns the git repository name """
    return "{" + repo_name + "}_git"

def is_ignored(file_path: str, ignore_list: List[str]) -> bool:
    """
    Checks if a file should be ignored based on the ignore list.

    Args:
        file_path (str): The file path to check.
        ignore_list (List[str]): List of patterns to ignore.

    Returns:
        bool: True if the file should be ignored, False otherwise.
    """

    return any(file_path.startswith(ignore) for ignore in ignore_list)

def classify_changes(
    diff: Diff,
    repo: Repository,
    supported_types: list[str],
    ignore_list: List[str]) -> tuple[list[Path], list[Path], list[Path]]:
    """
    Classifies changes into added, deleted, and modified files.

    Args:
        diff: The git diff object representing changes between two commits.
        ignore_list (List[str]): List of file patterns to ignore.

    Returns:
        (List[str], List[str], List[str]): A tuple of lists representing added, deleted, and modified files.
    """

    added, deleted, modified = [], [], []

    for change in diff.deltas:
        if change.status == DeltaStatus.ADDED and not is_ignored(change.new_file.path, ignore_list):
            logging.debug("new file: %s", change.new_file)
            file_path = Path(f"{repo.workdir}/{change.new_file.path}")
            if file_path.suffix in supported_types:
                added.append(file_path)
        if change.status == DeltaStatus.DELETED and not is_ignored(change.old_file.path, ignore_list):
            logging.debug("deleted file: %s", change.old_file.path)
            file_path = Path(f"{repo.workdir}/{change.old_file.path}")
            if file_path.suffix in supported_types:
                deleted.append(file_path)
        if change.status == DeltaStatus.MODIFIED and not is_ignored(change.new_file.path, ignore_list):
            logging.debug("change file: %s", change.new_file.path)
            file_path = Path(f"{repo.workdir}/{change.new_file.path}")
            if file_path.suffix in supported_types:
                modified.append(file_path)

    return added, deleted, modified

# build a graph capturing the git commit history
def build_commit_graph(path: str, analyzer: SourceAnalyzer, repo_name: str, ignore_list: Optional[List[str]] = None) -> GitGraph:
    """
    Builds a graph representation of the git commit history.

    Args:
        path (str): Path to the git repository.
        repo_name (str): Name of the repository.
        ignore_list (List[str], optional): List of file patterns to ignore.

    Returns:
        GitGraph: Graph object representing the commit history.
    """

    if ignore_list is None:
        ignore_list = []

    # Copy the graph into a temporary graph
    logging.info("Cloning source graph %s -> %s_tmp", repo_name, repo_name)
    # Will be deleted at the end of this function
    g = Graph(repo_name).clone(repo_name + "_tmp")
    g.enable_backlog()

    git_graph       = GitGraph(GitRepoName(repo_name))
    supported_types = analyzer.supported_types()

    # Initialize with the current commit
    # Save current git for later restoration
    repo = Repository('.')
    current_commit = repo.walk(repo.head.target).__next__()
    current_commit_hexsha = current_commit.short_id

    # Add commit to the git graph
    git_graph.add_commit(current_commit)

    #--------------------------------------------------------------------------
    # Process git history going backwards
    #--------------------------------------------------------------------------

    logging.info("Computing transition queries moving backwards")

    child_commit = current_commit
    while len(child_commit.parents) > 0:
        parent_commit = child_commit.parents[0]

        # add commit to the git graph
        git_graph.add_commit(parent_commit)

        # connect child parent commits relation
        git_graph.connect_commits(child_commit.short_id, parent_commit.short_id)

        # Represents the changes going backward!
        # e.g. which files need to be deleted when moving back one commit
        #
        # if we were to switch "direction" going forward
        # delete events would become add event
        # e.g. which files need to be added when moving forward from this commit
        #      to the next one

        # Process file changes in this commit
        logging.info(f"""Computing diff between
            child {child_commit.short_id}: {child_commit.message}
            and {parent_commit.short_id}: {parent_commit.message}""")

        diff = repo.diff(child_commit, parent_commit)
        added, deleted, modified = classify_changes(diff, repo, supported_types, ignore_list)

        # Checkout prev commit
        logging.info(f"Checking out commit: {parent_commit.short_id}")
        repo.checkout_tree(parent_commit.tree, strategy=CheckoutStrategy.FORCE)

        #-----------------------------------------------------------------------
        # Apply changes going backwards
        #-----------------------------------------------------------------------

        # apply deletions

        # reating modified files as both deleted and added
        # remove deleted files from the graph
        if len(deleted + modified) > 0:
            logging.info(f"Removing deleted files: {deleted + modified}")
            g.delete_files(deleted + modified)

        if len(added + modified) > 0:
            logging.info(f"Introducing a new filed: {added + modified}")
            analyzer.analyze_files(added + modified, Path(path), g)

        queries, params = g.clear_backlog()

        # Save transition queries to the git graph
        if len(queries) > 0:
            assert(len(queries) == len(params))

            # Covert parameters from dict to JSON formatted string
            params = [json.dumps(p) for p in params]

            # Log transitions
            logging.debug(f"""Save graph transition from
                             commit: {child_commit.short_id}
                             to
                             commit: {parent_commit.short_id}
                             Queries: {queries}
                             Parameters: {params}
                          """)

            git_graph.set_parent_transition(child_commit.short_id,
                                            parent_commit.short_id, queries, params)
        # advance to the next commit
        child_commit = parent_commit

    #--------------------------------------------------------------------------
    # Process git history going forward
    #--------------------------------------------------------------------------

    logging.info("Computing transition queries moving forward")
    parent_commit = child_commit
    while parent_commit.short_id != current_commit_hexsha:
        child_commit = git_graph.get_child_commit(parent_commit.short_id)
        child_commit = repo.walk(child_commit['hash']).__next__()

        # Represents the changes going forward
        # e.g. which files need to be deleted when moving forward one commit

        # Process file changes in this commit
        logging.info(f"""Computing diff between
            child {parent_commit.short_id}: {parent_commit.message}
            and {child_commit.short_id}: {child_commit.message}""")

        diff = repo.diff(parent_commit, child_commit)
        added, deleted, modified = classify_changes(diff, repo, supported_types, ignore_list)

        # Checkout child commit
        logging.info(f"Checking out commit: {child_commit.short_id}")
        repo.checkout_tree(child_commit.tree, strategy=CheckoutStrategy.FORCE)

        #-----------------------------------------------------------------------
        # Apply changes going forward
        #-----------------------------------------------------------------------

        # apply deletions

        # reating modified files as both deleted and added
        # remove deleted files from the graph
        if len(deleted + modified) > 0:
            logging.info(f"Removing deleted files: {deleted + modified}")
            g.delete_files(deleted + modified)

        if len(added + modified) > 0:
            logging.info(f"Introducing a new files: {added + modified}")
            analyzer.analyze_files(added + modified, Path(path), g)

        queries, params = g.clear_backlog()

        # Save transition queries to the git graph
        if len(queries) > 0:
            assert(len(queries) == len(params))

            # Covert parameters from dict to JSON formatted string
            params = [json.dumps(p) for p in params]

            # Log transitions
            logging.debug(f"""Save graph transition from
                             commit: {parent_commit.short_id}
                             to
                             commit: {child_commit.short_id}
                             Queries: {queries}
                             Parameters: {params}
                          """)

            git_graph.set_child_transition(child_commit.short_id,
                                            parent_commit.short_id, queries, params)
        # advance to the child_commit
        parent_commit = child_commit

    logging.debug("Done processing repository commit history")

    #--------------------------------------------------------------------------
    # Clean up
    #--------------------------------------------------------------------------

    # Delete temporaty graph
    g.disable_backlog()

    logging.debug(f"Deleting temporary graph {repo_name + '_tmp'}")
    g.delete()

    return git_graph

def switch_commit(repo: str, to: str):
    """
    Switches the state of a graph repository from its current commit to the given commit.

    This function handles switching between two git commits for a graph-based repository.
    It identifies the changes (additions, deletions, modifications) in nodes and edges between
    the current commit and the target commit and then applies the necessary transitions.

    Args:
        repo (str): The name of the graph repository to switch commits.
        to (str): The target commit hash to switch the graph to.
    """

    # Validate input arguments
    if not repo or not isinstance(repo, str):
        raise ValueError("Invalid repository name")

    if not to or not isinstance(to, str):
        raise ValueError("Invalid desired commit value")

    logging.info(f"Switching to commit: {to}")

    # Initialize the graph and GitGraph objects
    g = Graph(repo)
    git_graph = GitGraph(GitRepoName(repo))

    # Get the current commit hash of the graph
    current_hash = get_repo_commit(repo)
    logging.info(f"Current graph commit: {current_hash}")

    if current_hash == to:
        logging.debug("Current commit: {current_hash} is the requested commit")
        # No change remain at the current commit
        return

    # Find the path between the current commit and the desired commit
    commits = git_graph.get_commits([current_hash, to])

    # Ensure both current and target commits are present
    if len(commits) != 2:
        logging.error("Missing commits. Unable to proceed.")
        raise ValueError("Commits not found")

    # Identify the current and new commits based on their hashes
    current_commit, new_commit = (commits if commits[0]['hash'] == current_hash else reversed(commits))

    # Determine the direction of the switch (forward or backward in the commit history)
    child_commit = None
    parent_commit = None
    if current_commit['date'] > new_commit['date']:
        child_commit  = current_commit
        parent_commit = new_commit
        logging.info(f"Moving backward from {child_commit['hash']} to {parent_commit['hash']}")
        # Get the transitions (queries and parameters) for moving backward
        queries, params = git_graph.get_parent_transitions(child_commit['hash'], parent_commit['hash'])
    else:
        child_commit  = new_commit
        parent_commit = current_commit
        logging.info(f"Moving forward from {parent_commit['hash']} to {child_commit['hash']}")
        # Get the transitions (queries and parameters) for moving forward
        queries, params = git_graph.get_child_transitions(child_commit['hash'], parent_commit['hash'])

    # Apply each transition query with its respective parameters
    for q, p in zip(queries, params):
        for _q, _p in zip(q, p):
            _p = json.loads(_p)
            logging.debug(f"Executing query: {_q} with params: {_p}")

            # Rerun the query with parameters on the graph
            g.rerun_query(_q, _p)

    # Update the graph's commit to the new target commit
    set_repo_commit(repo, to)
    logging.info(f"Graph commit updated to {to}")
