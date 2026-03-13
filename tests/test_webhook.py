"""Unit tests for the webhook endpoint and incremental update helpers.

These tests use ``monkeypatch`` to mock out external collaborators (FalkorDB,
Redis, git) so they run without a live database or network connection.
"""

import hashlib
import hmac
import json

import pytest
from starlette.testclient import TestClient

import api.index


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A full Git SHA-1 hash is 40 hexadecimal characters.
_FULL_SHA_BEFORE = "aaaa1111" * 5  # 40-char SHA simulating the "before" commit
_FULL_SHA_AFTER  = "bbbb2222" * 5  # 40-char SHA simulating the "after" commit


class _FakePath:
    """Minimal Path-like object for use with monkeypatch."""

    def __init__(self, *, exists: bool):
        self._exists = exists

    def exists(self) -> bool:
        return self._exists


def _make_push_payload(
    ref: str = "refs/heads/main",
    before: str = _FULL_SHA_BEFORE,
    after: str = _FULL_SHA_AFTER,
    clone_url: str = "https://github.com/example/myrepo.git",
) -> dict:
    return {
        "ref": ref,
        "before": before,
        "after": after,
        "repository": {"clone_url": clone_url},
    }


def _sign(body: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


# ---------------------------------------------------------------------------
# _urls_match
# ---------------------------------------------------------------------------

def test_urls_match_identical():
    assert api.index._urls_match(
        "https://github.com/org/repo.git",
        "https://github.com/org/repo.git",
    )


def test_urls_match_git_suffix():
    assert api.index._urls_match(
        "https://github.com/org/repo",
        "https://github.com/org/repo.git",
    )


def test_urls_match_case_insensitive():
    assert api.index._urls_match(
        "https://github.com/Org/Repo.git",
        "https://github.com/org/repo.git",
    )


def test_urls_match_trailing_slash():
    assert api.index._urls_match(
        "https://github.com/org/repo/",
        "https://github.com/org/repo.git",
    )


def test_urls_no_match_different_repo():
    assert not api.index._urls_match(
        "https://github.com/org/repo-a.git",
        "https://github.com/org/repo-b.git",
    )


# ---------------------------------------------------------------------------
# Webhook endpoint – no secret configured (open mode)
# ---------------------------------------------------------------------------

@pytest.fixture()
def client_open(monkeypatch):
    """Test client with no webhook secret and no poll-watcher."""
    monkeypatch.setattr(api.index, "WEBHOOK_SECRET", "")
    monkeypatch.setattr(api.index, "POLL_INTERVAL", 0)
    return TestClient(api.index.app, raise_server_exceptions=False)


def test_webhook_ignored_wrong_branch(client_open, monkeypatch):
    """Pushes to non-tracked branches return 200 with status='ignored'."""
    monkeypatch.setattr(api.index, "TRACKED_BRANCH", "main")
    payload = _make_push_payload(ref="refs/heads/feature/x")
    resp = client_open.post("/api/webhook", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ignored"


def test_webhook_unknown_repo(client_open, monkeypatch):
    """Webhook for a repo URL that is not indexed returns 404."""
    monkeypatch.setattr(api.index, "TRACKED_BRANCH", "main")

    # No repos indexed → _find_repo_by_url returns None
    async def _fake_get_repos():
        return []

    monkeypatch.setattr(api.index, "async_get_repos", _fake_get_repos)

    payload = _make_push_payload()
    resp = client_open.post("/api/webhook", json=payload)
    assert resp.status_code == 404


def test_webhook_success(client_open, monkeypatch):
    """Valid push to tracked branch triggers incremental_update and returns stats."""
    monkeypatch.setattr(api.index, "TRACKED_BRANCH", "main")

    async def _fake_get_repos():
        return ["myrepo"]

    async def _fake_get_repo_info(repo_name):
        return {"repo_url": "https://github.com/example/myrepo.git"}

    update_calls = []

    def _fake_update(repo_name, from_sha, to_sha, ignore=None):
        update_calls.append((repo_name, from_sha, to_sha))
        return {
            "files_added": 1,
            "files_modified": 0,
            "files_deleted": 0,
            "commit": to_sha[:7],
        }

    monkeypatch.setattr(api.index, "async_get_repos", _fake_get_repos)
    monkeypatch.setattr(api.index, "async_get_repo_info", _fake_get_repo_info)
    monkeypatch.setattr(api.index, "incremental_update", _fake_update)
    # Skip git fetch (no real clone)
    monkeypatch.setattr(api.index, "fetch_remote", lambda path: None)
    monkeypatch.setattr(api.index, "repo_local_path", lambda name: _FakePath(exists=False))

    payload = _make_push_payload()
    resp = client_open.post("/api/webhook", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["files_added"] == 1
    assert len(update_calls) == 1
    assert update_calls[0] == ("myrepo", _FULL_SHA_BEFORE, _FULL_SHA_AFTER)


# ---------------------------------------------------------------------------
# Webhook endpoint – HMAC-SHA256 signature validation
# ---------------------------------------------------------------------------

@pytest.fixture()
def client_secured(monkeypatch):
    """Test client with WEBHOOK_SECRET='mysecret' and poll disabled."""
    monkeypatch.setattr(api.index, "WEBHOOK_SECRET", "mysecret")
    monkeypatch.setattr(api.index, "POLL_INTERVAL", 0)
    return TestClient(api.index.app, raise_server_exceptions=False)


def test_webhook_missing_signature_rejected(client_secured, monkeypatch):
    """Requests without X-Hub-Signature-256 header are rejected with 401."""
    monkeypatch.setattr(api.index, "TRACKED_BRANCH", "main")
    payload = _make_push_payload()
    resp = client_secured.post("/api/webhook", json=payload)
    assert resp.status_code == 401


def test_webhook_wrong_signature_rejected(client_secured, monkeypatch):
    """Requests with an incorrect signature are rejected with 401."""
    monkeypatch.setattr(api.index, "TRACKED_BRANCH", "main")
    payload = _make_push_payload()
    body = json.dumps(payload).encode()
    bad_sig = _sign(body, "wrongsecret")
    resp = client_secured.post(
        "/api/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": bad_sig},
    )
    assert resp.status_code == 401


def test_webhook_valid_signature_accepted(client_secured, monkeypatch):
    """Requests with a correct HMAC-SHA256 signature are accepted."""
    monkeypatch.setattr(api.index, "TRACKED_BRANCH", "main")
    monkeypatch.setattr(api.index, "WEBHOOK_SECRET", "mysecret")

    async def _fake_get_repos():
        return ["myrepo"]

    async def _fake_get_repo_info(repo_name):
        return {"repo_url": "https://github.com/example/myrepo.git"}

    monkeypatch.setattr(api.index, "async_get_repos", _fake_get_repos)
    monkeypatch.setattr(api.index, "async_get_repo_info", _fake_get_repo_info)
    monkeypatch.setattr(api.index, "incremental_update", lambda *a, **kw: {
        "files_added": 0, "files_modified": 0, "files_deleted": 0, "commit": "abc1234",
    })
    monkeypatch.setattr(api.index, "fetch_remote", lambda path: None)
    monkeypatch.setattr(api.index, "repo_local_path", lambda name: _FakePath(exists=False))

    payload = _make_push_payload()
    body = json.dumps(payload).encode()
    sig = _sign(body, "mysecret")

    resp = client_secured.post(
        "/api/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_webhook_invalid_json(client_open, monkeypatch):
    """Non-JSON bodies are rejected with 400."""
    monkeypatch.setattr(api.index, "TRACKED_BRANCH", "main")
    resp = client_open.post(
        "/api/webhook",
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# incremental_update – unit tests (no live DB/git)
# ---------------------------------------------------------------------------

def test_incremental_update_idempotent(monkeypatch, tmp_path):
    """Calling incremental_update with the same SHA twice is a no-op."""
    from api.git_utils.incremental_update import incremental_update as _iu

    # Patch set_repo_commit to detect unexpected writes
    writes = []
    monkeypatch.setattr("api.git_utils.incremental_update.set_repo_commit",
                        lambda *a: writes.append(a))

    sha = "abc1234"
    result = _iu("some-repo", sha, sha)

    assert result["files_added"] == 0
    assert result["files_modified"] == 0
    assert result["files_deleted"] == 0
    assert result["commit"] == sha
    assert writes == [], "set_repo_commit must not be called for no-op update"


def test_incremental_update_missing_repo(monkeypatch, tmp_path):
    """incremental_update raises ValueError when local clone does not exist."""
    from api.git_utils.incremental_update import incremental_update as _iu

    monkeypatch.setattr(
        "api.git_utils.incremental_update.repo_local_path",
        lambda name: tmp_path / "nonexistent",
    )

    with pytest.raises(ValueError, match="Local repository not found"):
        _iu("some-repo", "aaa1111", "bbb2222")
