"""Tests for bench/runners/index_cache."""

from __future__ import annotations

from pathlib import Path

from bench.runners.index_cache import IndexCache


def test_empty_cache_returns_none(tmp_path: Path):
    c = IndexCache(tmp_path)
    assert c.has("django", "abc123") is False
    assert c.get("django", "abc123") is None
    assert c.all() == []


def test_record_and_lookup(tmp_path: Path):
    c = IndexCache(tmp_path)
    e = c.record("django", "abc123", "/work/django")
    assert e.repo == "django"
    assert e.source_path == "/work/django"
    assert c.has("django", "abc123") is True
    got = c.get("django", "abc123")
    assert got is not None
    assert got.commit == "abc123"


def test_persists_across_instances(tmp_path: Path):
    c1 = IndexCache(tmp_path)
    c1.record("flask", "def456", "/work/flask")
    c2 = IndexCache(tmp_path)
    assert c2.has("flask", "def456") is True


def test_forget(tmp_path: Path):
    c = IndexCache(tmp_path)
    c.record("sympy", "111", "/work/sympy")
    assert c.forget("sympy", "111") is True
    assert c.has("sympy", "111") is False
    assert c.forget("sympy", "111") is False  # second forget is a no-op


def test_all_returns_all_entries(tmp_path: Path):
    c = IndexCache(tmp_path)
    c.record("a", "1", "/p/a")
    c.record("b", "2", "/p/b")
    c.record("c", "3", "/p/c")
    assert {e.repo for e in c.all()} == {"a", "b", "c"}


def test_record_overwrites_same_key(tmp_path: Path):
    c = IndexCache(tmp_path)
    c.record("a", "1", "/p/a")
    c.record("a", "1", "/p/a-new")
    e = c.get("a", "1")
    assert e is not None
    assert e.source_path == "/p/a-new"
    assert len(c.all()) == 1
