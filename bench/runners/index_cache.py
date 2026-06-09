"""Indexing-cache registry — track which `<repo>@<commit>` pairs have been
indexed by code-graph, so the benchmark runner doesn't re-index between runs.

This is a tiny JSON-on-disk registry. It does NOT actually run analysis —
that goes through code-graph's existing `/api/analyze_folder` /
`/api/analyze_repo` endpoints. This module just records what's been done.

Each entry records (repo, commit, indexed_at, source_path) so the runner
can ask "is `django@4.2.7` already indexed?" before kicking off another
full analysis. Cache is content-addressed by `<repo>@<commit>`.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class IndexEntry:
    repo: str
    commit: str
    source_path: str
    indexed_at: float   # unix epoch seconds


class IndexCache:
    """JSON-file-backed cache. Single-writer assumed (one runner at a time)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._file = self.root / "index.json"

    @staticmethod
    def key(repo: str, commit: str) -> str:
        return f"{repo}@{commit}"

    def _load(self) -> dict[str, IndexEntry]:
        if not self._file.exists():
            return {}
        with open(self._file) as f:
            raw = json.load(f)
        return {k: IndexEntry(**v) for k, v in raw.items()}

    def _save(self, entries: dict[str, IndexEntry]) -> None:
        data = {k: asdict(v) for k, v in entries.items()}
        tmp = self._file.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        tmp.replace(self._file)

    def has(self, repo: str, commit: str) -> bool:
        return self.key(repo, commit) in self._load()

    def get(self, repo: str, commit: str) -> IndexEntry | None:
        return self._load().get(self.key(repo, commit))

    def record(self, repo: str, commit: str, source_path: str) -> IndexEntry:
        entries = self._load()
        entry = IndexEntry(
            repo=repo,
            commit=commit,
            source_path=str(source_path),
            indexed_at=time.time(),
        )
        entries[self.key(repo, commit)] = entry
        self._save(entries)
        return entry

    def forget(self, repo: str, commit: str) -> bool:
        entries = self._load()
        k = self.key(repo, commit)
        if k not in entries:
            return False
        del entries[k]
        self._save(entries)
        return True

    def all(self) -> list[IndexEntry]:
        return list(self._load().values())
