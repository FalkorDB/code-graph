import os
import shutil
import logging
import validators
import subprocess
from pygit2.repository import Repository
from .info import *
from shlex import quote
from pathlib import Path
from .graph import Graph
from typing import Optional, List
from urllib.parse import urlparse
from .analyzers import SourceAnalyzer
from .git_utils import build_commit_graph, GitGraph

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

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
    cmd = ["git", "clone", quote(url), path]

    # Run the git clone command and wait for it to finish
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    
    return path

class Project():
    def __init__(self, name: str, path: Path, url: Optional[str]):
        self.url   = url
        self.name  = name
        self.path  = path
        self.graph = Graph(name)

        if url is not None:
            save_repo_info(name, url)

    @classmethod
    def from_git_repository(cls, url: str):
        # Validate url
        if not validators.url(url):
            raise Exception(f"invalid url: {url}")

        # Extract project name from URL
        parsed_url = urlparse(url)
        name = parsed_url.path.split('/')[-1]
        path = _clone_source(url, name)

        return cls(name, path, url)

    @classmethod
    def from_local_repository(cls, path: Path|str):
        path = Path(path) if isinstance(path, str) else path

        # Validate path exists
        if not path.exists():
            raise Exception(f"missing path: {path}")

        # adjust url
        # 'git@github.com:FalkorDB/code_graph.git'
        url  = Repository(path).remotes[0].url
        url = url.replace("git@", "https://").replace(":", "/").replace(".git", "")

        name = path.name

        return cls(name, path, url)

    def analyze_sources(self, ignore: Optional[List[str]] = None) -> Graph:
        if ignore is None:
            ignore = []
        self.analyzer = SourceAnalyzer()
        self.analyzer.analyze_local_folder(self.path, self.graph, ignore)

        try:
            # Save processed commit hash to the DB
            repo = Repository(self.path)
            current_commit = repo.walk(repo.head.target).__next__()
            set_repo_commit(self.name, current_commit.short_id)
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

        git_graph = build_commit_graph(self.path, self.analyzer, self.name, ignore)

        # Restore original working directory
        logging.info(f"Restoring current working directory to: {original_dir}")
        os.chdir(original_dir)

        return git_graph
