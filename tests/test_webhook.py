"""Unit tests for the webhook endpoint and incremental update helpers.

These tests use ``monkeypatch`` to mock out external collaborators (FalkorDB,
Redis, git) so they run without a live database or network connection.
"""

import hashlib
import hmac
import importlib
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
# Webhook endpoint – bearer token fallback mode
# ---------------------------------------------------------------------------

@pytest.fixture()
def client_token_auth(monkeypatch):
    """Test client with bearer-token webhook auth and no poll-watcher."""
    monkeypatch.setattr(api.index, "WEBHOOK_SECRET", "")
    monkeypatch.setattr(api.index, "SECRET_TOKEN", "apitoken")
    monkeypatch.setattr(api.index, "POLL_INTERVAL", 0)
    return TestClient(api.index.app, raise_server_exceptions=False)


@pytest.fixture()
def client_misconfigured(monkeypatch):
    """Test client with webhook auth disabled entirely."""
    monkeypatch.setattr(api.index, "WEBHOOK_SECRET", "")
    monkeypatch.setattr(api.index, "SECRET_TOKEN", None)
    monkeypatch.setattr(api.index, "POLL_INTERVAL", 0)
    return TestClient(api.index.app, raise_server_exceptions=False)


def test_webhook_ignored_wrong_branch(client_token_auth, monkeypatch):
    """Pushes to non-tracked branches return 200 with status='ignored'."""
    monkeypatch.setattr(api.index, "TRACKED_BRANCH", "main")
    payload = _make_push_payload(ref="refs/heads/feature/x")
    resp = client_token_auth.post(
        "/api/webhook",
        json=payload,
        headers={"Authorization": "Bearer apitoken"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ignored"


def test_webhook_unknown_repo(client_token_auth, monkeypatch):
    """Webhook for a repo URL that is not indexed returns 404."""
    monkeypatch.setattr(api.index, "TRACKED_BRANCH", "main")

    # No repos indexed → _find_repo_by_url returns None
    async def _fake_get_repos():
        return []

    monkeypatch.setattr(api.index, "async_get_repos", _fake_get_repos)

    payload = _make_push_payload()
    resp = client_token_auth.post(
        "/api/webhook",
        json=payload,
        headers={"Authorization": "Bearer apitoken"},
    )
    assert resp.status_code == 404


def test_webhook_success(client_token_auth, monkeypatch):
    """Valid push to tracked branch triggers incremental_update and returns stats."""
    monkeypatch.setattr(api.index, "TRACKED_BRANCH", "main")

    async def _fake_get_repos():
        return ["myrepo"]

    async def _fake_get_repo_info(repo_name):
        return {"repo_url": "https://github.com/example/myrepo.git"}

    update_calls = []

    def _fake_sync(repo_name, path, to_sha, before_sha=None, repo_url="", ignore=None):
        update_calls.append((repo_name, before_sha, to_sha, repo_url))
        return {
            "files_added": 1,
            "files_modified": 0,
            "files_deleted": 0,
            "commit": to_sha[:7],
        }

    monkeypatch.setattr(api.index, "async_get_repos", _fake_get_repos)
    monkeypatch.setattr(api.index, "async_get_repo_info", _fake_get_repo_info)
    monkeypatch.setattr(api.index, "_sync_repo_graph", _fake_sync)
    # Skip git fetch (no real clone)
    monkeypatch.setattr(api.index, "fetch_remote", lambda path: None)
    monkeypatch.setattr(api.index, "repo_local_path", lambda name: _FakePath(exists=False))

    payload = _make_push_payload()
    resp = client_token_auth.post(
        "/api/webhook",
        json=payload,
        headers={"Authorization": "Bearer apitoken"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["files_added"] == 1
    assert len(update_calls) == 1
    assert update_calls[0] == (
        "myrepo",
        _FULL_SHA_BEFORE,
        _FULL_SHA_AFTER,
        "https://github.com/example/myrepo.git",
    )


def test_webhook_requires_bearer_token_when_secret_missing(client_token_auth, monkeypatch):
    """Bearer token auth protects the webhook when WEBHOOK_SECRET is unset."""
    monkeypatch.setattr(api.index, "TRACKED_BRANCH", "main")
    payload = _make_push_payload()
    resp = client_token_auth.post("/api/webhook", json=payload)
    assert resp.status_code == 401


def test_webhook_rejected_when_no_auth_is_configured(client_misconfigured, monkeypatch):
    """The webhook returns 503 when neither WEBHOOK_SECRET nor SECRET_TOKEN is set."""
    monkeypatch.setattr(api.index, "TRACKED_BRANCH", "main")
    payload = _make_push_payload()
    resp = client_misconfigured.post("/api/webhook", json=payload)
    assert resp.status_code == 503


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
    monkeypatch.setattr(api.index, "_sync_repo_graph", lambda *a, **kw: {
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


def test_gitlab_webhook_token_accepted(client_secured, monkeypatch):
    """GitLab webhooks authenticate via X-Gitlab-Token and git_http_url payloads."""
    monkeypatch.setattr(api.index, "TRACKED_BRANCH", "main")

    async def _fake_get_repos():
        return ["myrepo"]

    async def _fake_get_repo_info(repo_name):
        return {"repo_url": "https://gitlab.com/example/myrepo.git"}

    monkeypatch.setattr(api.index, "async_get_repos", _fake_get_repos)
    monkeypatch.setattr(api.index, "async_get_repo_info", _fake_get_repo_info)
    monkeypatch.setattr(api.index, "_sync_repo_graph", lambda *a, **kw: {
        "files_added": 0, "files_modified": 0, "files_deleted": 0, "commit": "abc1234",
    })
    monkeypatch.setattr(api.index, "fetch_remote", lambda path: None)
    monkeypatch.setattr(api.index, "repo_local_path", lambda name: _FakePath(exists=False))

    payload = {
        "ref": "refs/heads/main",
        "before": _FULL_SHA_BEFORE,
        "after": _FULL_SHA_AFTER,
        "repository": {"git_http_url": "https://gitlab.com/example/myrepo.git"},
    }
    resp = client_secured.post(
        "/api/webhook",
        json=payload,
        headers={"X-Gitlab-Token": "mysecret", "X-Gitlab-Event": "Push Hook"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_gitlab_webhook_missing_token_rejected(client_secured, monkeypatch):
    """GitLab requests without X-Gitlab-Token are rejected."""
    monkeypatch.setattr(api.index, "TRACKED_BRANCH", "main")
    payload = _make_push_payload()
    resp = client_secured.post(
        "/api/webhook",
        json=payload,
        headers={"X-Gitlab-Event": "Push Hook"},
    )
    assert resp.status_code == 401


def test_webhook_invalid_json(client_token_auth, monkeypatch):
    """Non-JSON bodies are rejected with 400."""
    monkeypatch.setattr(api.index, "TRACKED_BRANCH", "main")
    resp = client_token_auth.post(
        "/api/webhook",
        content=b"not-json",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer apitoken",
        },
    )
    assert resp.status_code == 400


def test_sync_repo_graph_uses_stored_bookmark(monkeypatch, tmp_path):
    """Incremental sync uses the stored bookmark instead of payload.before."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    calls = []
    monkeypatch.setattr(api.index, "get_repo_commit", lambda name: "stored123")
    monkeypatch.setattr(api.index, "can_incrementally_update", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        api.index,
        "incremental_update",
        lambda repo_name, from_sha, to_sha, ignore=None: calls.append(
            (repo_name, from_sha, to_sha, ignore)
        ) or {
            "files_added": 0,
            "files_modified": 0,
            "files_deleted": 0,
            "commit": to_sha[:7],
        },
    )

    api.index._sync_repo_graph(
        "myrepo",
        repo_path,
        _FULL_SHA_AFTER,
        before_sha=_FULL_SHA_BEFORE,
    )

    assert calls == [("myrepo", "stored123", _FULL_SHA_AFTER, [])]


def test_sync_repo_graph_full_reindexes_without_bookmark(monkeypatch, tmp_path):
    """Missing bookmarks fall back to a full reindex instead of partial diffing."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    monkeypatch.setattr(api.index, "get_repo_commit", lambda name: None)
    monkeypatch.setattr(
        api.index,
        "_full_reindex_repository",
        lambda *args, **kwargs: {"mode": "full_reindex", "commit": "abc1234"},
    )

    result = api.index._sync_repo_graph("myrepo", repo_path, _FULL_SHA_AFTER)

    assert result["mode"] == "full_reindex"


def test_sync_repo_graph_full_reindexes_on_history_gap(monkeypatch, tmp_path):
    """History gaps or force-pushes fall back to a full reindex."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    monkeypatch.setattr(api.index, "get_repo_commit", lambda name: "stored123")
    monkeypatch.setattr(api.index, "can_incrementally_update", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        api.index,
        "_full_reindex_repository",
        lambda *args, **kwargs: {"mode": "full_reindex", "commit": "abc1234"},
    )

    result = api.index._sync_repo_graph(
        "myrepo",
        repo_path,
        _FULL_SHA_AFTER,
        before_sha=_FULL_SHA_BEFORE,
    )

    assert result["mode"] == "full_reindex"


# ---------------------------------------------------------------------------
# incremental_update – unit tests (no live DB/git)
# ---------------------------------------------------------------------------

def test_incremental_update_idempotent(monkeypatch, tmp_path):
    """Calling incremental_update with the same SHA twice is a no-op."""
    incremental_update_module = importlib.import_module("api.git_utils.incremental_update")
    _iu = incremental_update_module.incremental_update

    # Patch set_repo_commit to detect unexpected writes
    writes = []
    monkeypatch.setattr(
        incremental_update_module,
        "set_repo_commit",
        lambda *a: writes.append(a),
    )

    sha = "abc1234"
    result = _iu("some-repo", sha, sha)

    assert result["files_added"] == 0
    assert result["files_modified"] == 0
    assert result["files_deleted"] == 0
    assert result["commit"] == sha
    assert writes == [], "set_repo_commit must not be called for no-op update"


def test_incremental_update_missing_repo(monkeypatch, tmp_path):
    """incremental_update raises ValueError when local clone does not exist."""
    incremental_update_module = importlib.import_module("api.git_utils.incremental_update")
    _iu = incremental_update_module.incremental_update

    monkeypatch.setattr(
        incremental_update_module,
        "repo_local_path",
        lambda name: tmp_path / "nonexistent",
    )

    with pytest.raises(ValueError, match="Local repository not found"):
        _iu("some-repo", "aaa1111", "bbb2222")
