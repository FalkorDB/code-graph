"""Symlink-safe guard for snippet file reads (PR #701 security review).

``search_code`` / ``get_file_neighbors`` attach a short source snippet read
from the indexed ``File.path``. Those paths ultimately come from repo content,
so a malicious repo could store (or symlink) a path resolving outside the
indexed worktree and turn a snippet read into an arbitrary host-file read.
``_read_snippet`` now resolves the real path and only reads inside an allowed
root (the ``/<project>/`` repo root and/or ``ALLOWED_ANALYSIS_DIR``).

These tests are pure-Python (real temp files + a symlink); no FalkorDB needed.
"""

from __future__ import annotations

from pathlib import Path

from api.mcp.tools.structural import _is_within, _read_snippet, _snippet_path_allowed


def _make_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create ``<root>/proj/pkg/mod.py`` and an escaping symlink. Returns
    ``(real_file, escaping_symlink, secret_outside)``."""
    proj = tmp_path / "root" / "proj"
    (proj / "pkg").mkdir(parents=True)
    real_file = proj / "pkg" / "mod.py"
    real_file.write_text("def alpha():\n    return 1\n\n\nx = 2\n")

    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("TOP SECRET LINE 1\nTOP SECRET LINE 2\n")

    evil = proj / "evil.py"
    evil.symlink_to(secret)
    return real_file, evil, secret


def test_reads_file_inside_repo_root(tmp_path: Path):
    real_file, _evil, _secret = _make_repo(tmp_path)
    snip = _read_snippet(str(real_file), 1, 3, 5, project="proj")
    assert snip is not None
    assert "def alpha" in snip


def test_blocks_symlink_escaping_repo_root(tmp_path: Path):
    _real_file, evil, _secret = _make_repo(tmp_path)
    # The path lives under /proj/ but resolves (via symlink) outside the repo.
    assert _snippet_path_allowed(str(evil), "proj") is False
    assert _read_snippet(str(evil), 1, 2, 5, project="proj") is None


def test_blocks_outside_path_when_allowed_dir_set(tmp_path: Path, monkeypatch):
    _real_file, _evil, secret = _make_repo(tmp_path)
    monkeypatch.setenv("ALLOWED_ANALYSIS_DIR", str(tmp_path / "root"))
    # No /proj/ marker in this path, but ALLOWED_ANALYSIS_DIR excludes it.
    assert _snippet_path_allowed(str(secret), None) is False
    assert _read_snippet(str(secret), 1, 2, 5) is None


def test_allows_when_no_constraint_derivable(tmp_path: Path):
    # No project marker in the path and no ALLOWED_ANALYSIS_DIR -> legacy read.
    f = tmp_path / "loose.py"
    f.write_text("def beta():\n    return 0\n")
    assert _snippet_path_allowed(str(f), None) is True
    assert _read_snippet(str(f), 1, 2, 5) is not None


def test_is_within_rejects_sibling_prefix(tmp_path: Path):
    root = str(tmp_path / "proj")
    # A sibling dir sharing a string prefix must NOT count as contained.
    assert _is_within(str(tmp_path / "proj-evil" / "x.py"), root) is False
    assert _is_within(str(tmp_path / "proj" / "x.py"), root) is True


def test_missing_path_returns_none():
    assert _read_snippet(None, 1, 2, 5, project="proj") is None
    assert _read_snippet("", 1, 2, 5, project="proj") is None
