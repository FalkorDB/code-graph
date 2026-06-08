import os
import shutil
import logging
import validators
import subprocess
from pygit2.repository import Repository
from .info import *
from pathlib import Path
from .graph import Graph, DEFAULT_BRANCH
from typing import Optional, List
from urllib.parse import urlparse
from .analyzers import SourceAnalyzer
from .git_utils import build_commit_graph, GitGraph

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


def detect_branch(path: Path) -> str:
    """Resolve the current branch name for a checkout at ``path``.

    Uses ``git rev-parse --abbrev-ref HEAD``. Returns
    :data:`api.graph.DEFAULT_BRANCH` when the path is not a git checkout
    or when HEAD is detached (the ``rev-parse`` call returns ``HEAD``).
    """

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(path),
            capture_output=True,
            text=True,
            check=True,
        )
        branch = (result.stdout or "").strip()
        if not branch or branch == "HEAD":
            return DEFAULT_BRANCH
        return branch
    except (FileNotFoundError, subprocess.CalledProcessError):
        return DEFAULT_BRANCH

def _clone_source(url: str, name: str) -> Path:
    # path to local repositories
    path = Path.cwd() / "repositories" / name
    print(f"Cloning repository to: {path}")

    # Delete local repository if exists
    if path.exists():
        shutil.rmtree(path)

    # Create directory
    path.mkdir(parents=True, exist_ok=True)

    # Clone repository
    # Prepare the Git clone command
    cmd = ["git", "clone", url, str(path)]

    # Run the git clone command and wait for it to finish
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    
    return path

class Project():
    def __init__(self, name: str, path: Path, url: Optional[str], branch: Optional[str] = None):
        self.url    = url
        self.name   = name
        self.path   = path
        # Auto-detect branch from the working tree when not explicitly given.
        # Treat the empty string the same as ``None`` so the project never
        # reports a branch that disagrees with the graph/info keys it writes
        # (which coerce empty branch to DEFAULT_BRANCH).
        if not branch:
            branch = detect_branch(path) if path is not None and Path(path).exists() else DEFAULT_BRANCH
        self.branch = branch
        self.graph  = Graph(name, branch=self.branch)

        if url is not None:
            save_repo_info(name, url, self.branch)

    @classmethod
    def from_git_repository(cls, url: str, branch: Optional[str] = None):
        # Validate url
        if not validators.url(url):
            raise Exception(f"invalid url: {url}")

        # Extract project name from URL
        parsed_url = urlparse(url)
        name = parsed_url.path.split('/')[-1]
        path = _clone_source(url, name)

        return cls(name, path, url, branch=branch)

    @classmethod
    def from_local_repository(cls, path: Path|str, branch: Optional[str] = None):
        path = Path(path) if isinstance(path, str) else path

        # Validate path exists
        if not path.exists():
            raise Exception(f"missing path: {path}")

        # adjust url
        # 'git@github.com:FalkorDB/code_graph.git'
        url  = Repository(path).remotes[0].url
        url = url.replace("git@", "https://").replace(":", "/").replace(".git", "")

        name = path.name

        return cls(name, path, url, branch=branch)

    def analyze_sources(self, ignore: Optional[List[str]] = None) -> Graph:
        if ignore is None:
            ignore = []
        self.analyzer = SourceAnalyzer()
        self.analyzer.analyze_local_folder(self.path, self.graph, ignore)

        try:
            # Save processed commit hash to the DB
            repo = Repository(self.path)
            current_commit = repo.walk(repo.head.target).__next__()
            set_repo_commit(self.name, current_commit.short_id, self.branch)
        except Exception:
            # Probably not .git folder is missing
            pass

        return self.graph

    def process_git_history(self, ignore: Optional[List[str]] = []) -> GitGraph:
        logging.info(f"processing {self.name} git commit history")

        # Save original working directory for later restore
        original_dir = Path.cwd()

        # change working directory to local repository
        logging.info(f"Switching current working directory to: {self.path}")
        os.chdir(self.path)

        git_graph = build_commit_graph(self.path, self.analyzer, self.name, ignore, branch=self.branch)

        # Restore original working directory
        logging.info(f"Restoring current working directory to: {original_dir}")
        os.chdir(original_dir)

        return git_graph
