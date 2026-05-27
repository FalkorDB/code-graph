"""T3 — assertion contract sanity check.

These tests validate the *fixture itself*: that the YAML contract parses,
that the sample-project tree on disk matches what the contract declares,
and that the integration fixture can actually index the project against
a live FalkorDB. Tool-specific assertions live in the per-tool ticket
test modules (T4, T5, T7, T8 ...).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.mcp.conftest import EXPECTED_PATH, SAMPLE_PROJECT


# ---------------------------------------------------------------------------
# Pure-Python contract checks (always run)
# ---------------------------------------------------------------------------


def test_expected_yaml_exists():
    assert EXPECTED_PATH.is_file(), "fixtures/expected.yaml must exist"


def test_expected_contract_shape(expected_contract):
    """Required top-level keys are present and well-typed."""

    assert expected_contract["project_name"] == "sample_project"

    counts = expected_contract["counts_min"]
    for label in ("File", "Class", "Function"):
        assert label in counts and isinstance(counts[label], int) and counts[label] >= 0

    calls = expected_contract["calls"]
    for sym in ("service", "entrypoint", "db"):
        assert sym in calls, f"calls.{sym} missing from expected.yaml"

    paths = expected_contract["paths"]
    assert isinstance(paths, list) and len(paths) >= 1
    for p in paths:
        for k in ("source", "dest", "min_paths"):
            assert k in p, f"path entry missing key: {k}"

    prefixes = expected_contract["search_prefixes"]
    assert "ent" in prefixes


def test_sample_project_python_files_present():
    """The Python tree the contract references must exist on disk."""
    py = SAMPLE_PROJECT / "python"
    for name in ("entrypoint.py", "service.py", "repo.py", "db.py", "__init__.py"):
        assert (py / name).is_file(), f"missing fixture file: python/{name}"


# ---------------------------------------------------------------------------
# Integration check — requires FalkorDB; self-skips when unreachable
# ---------------------------------------------------------------------------


def test_indexed_fixture_loads_minimum_counts(indexed_fixture, expected_contract):
    """The fixture indexes cleanly and meets the minimum count contract.

    Subsequent per-tool tickets (T4+) use ``indexed_fixture`` directly;
    this test exists so the fixture itself is regression-tested in
    isolation.
    """

    from api.graph import Graph

    g = Graph(indexed_fixture.project, branch=indexed_fixture.branch)
    counts_min = expected_contract["counts_min"]

    for label, minimum in counts_min.items():
        rows = g.g.query(f"MATCH (n:{label}) RETURN count(n) AS c").result_set
        actual = rows[0][0] if rows else 0
        assert actual >= minimum, (
            f"label {label}: expected >={minimum}, got {actual}"
        )
