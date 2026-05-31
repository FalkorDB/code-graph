"""T3 — assertion contract sanity check.

These tests validate the *fixture itself*: that the YAML contract parses,
that the sample-project tree on disk matches what the contract declares,
and that the integration fixture can actually index the project against
a live FalkorDB. Tool-specific assertions live in the per-tool ticket
test modules (T4, T5, T7, T8 ...).
"""

from __future__ import annotations

from tests.mcp.conftest import EXPECTED_PATH, SAMPLE_PROJECT


# ---------------------------------------------------------------------------
# Pure-Python contract checks (always run)
# ---------------------------------------------------------------------------


def test_expected_yaml_exists():
    assert EXPECTED_PATH.is_file(), "fixtures/expected.yaml must exist"


def test_expected_contract_shape(expected_contract):
    """Required top-level keys are present with the expected exact shape."""

    assert expected_contract["project_name"] == "sample_project"

    counts = expected_contract["counts"]
    # Exact, not >=: the fixture is deterministic Python-only tree-sitter.
    assert counts == {"File": 5, "Class": 3, "Function": 6}

    calls = expected_contract["calls"]
    for sym in ("service", "entrypoint", "db"):
        assert sym in calls, f"calls.{sym} missing from expected.yaml"
        # Each entry must declare both directions as exact lists.
        for direction in ("callers", "callees"):
            assert direction in calls[sym], (
                f"calls.{sym}.{direction} missing"
            )
            assert isinstance(calls[sym][direction], list), (
                f"calls.{sym}.{direction} must be a list"
            )

    paths = expected_contract["paths"]
    assert isinstance(paths, list) and len(paths) == 1
    for p in paths:
        for k in ("source", "dest", "paths_count"):
            assert k in p, f"path entry missing key: {k}"
        assert isinstance(p["paths_count"], int) and p["paths_count"] >= 1

    prefixes = expected_contract["search_prefixes"]
    assert "ent" in prefixes
    for key, spec in prefixes.items():
        assert "must_include" in spec, (
            f"search_prefixes.{key}.must_include missing"
        )
        assert isinstance(spec["must_include"], list) and spec["must_include"]


def test_sample_project_python_files_present():
    """The Python tree the contract references must exist on disk."""
    py = SAMPLE_PROJECT / "python"
    for name in ("entrypoint.py", "service.py", "repo.py", "db.py", "__init__.py"):
        assert (py / name).is_file(), f"missing fixture file: python/{name}"


# ---------------------------------------------------------------------------
# Integration check — requires FalkorDB; self-skips when unreachable
# ---------------------------------------------------------------------------


def test_indexed_fixture_loads_exact_counts(indexed_fixture, expected_contract):
    """The fixture indexes cleanly and matches the exact count contract.

    Subsequent per-tool tickets (T4+) use ``indexed_fixture`` directly;
    this test exists so the fixture itself is regression-tested in
    isolation.
    """

    from api.graph import Graph

    g = Graph(indexed_fixture.project, branch=indexed_fixture.branch)
    counts = expected_contract["counts"]

    for label, expected in counts.items():
        rows = g.g.query(f"MATCH (n:{label}) RETURN count(n) AS c").result_set
        actual = rows[0][0] if rows else 0
        assert actual == expected, (
            f"label {label}: expected exactly {expected}, got {actual}"
        )


def test_indexed_fixture_callers_and_callees(indexed_fixture, expected_contract):
    """T3 acceptance: assert at least one named caller and one named callee
    from the contract resolve against the indexed graph.

    Without this the ``calls`` section of ``expected.yaml`` would never be
    exercised, and contract drift would silently break the T5
    (get_callers / get_callees) downstream test.
    """

    from api.graph import Graph

    g = Graph(indexed_fixture.project, branch=indexed_fixture.branch)
    calls = expected_contract["calls"]

    def names(query: str, **params) -> list[str]:
        rows = g.g.query(query, params).result_set
        return sorted(r[0] for r in rows)

    for sym, spec in calls.items():
        expected_callers = sorted(spec["callers"])
        expected_callees = sorted(spec["callees"])

        actual_callers = names(
            "MATCH (s)-[:CALLS]->(d:Searchable {name:$n}) RETURN s.name",
            n=sym,
        )
        actual_callees = names(
            "MATCH (s:Searchable {name:$n})-[:CALLS]->(d) RETURN d.name",
            n=sym,
        )

        assert actual_callers == expected_callers, (
            f"calls.{sym}.callers: expected {expected_callers}, "
            f"got {actual_callers}"
        )
        assert actual_callees == expected_callees, (
            f"calls.{sym}.callees: expected {expected_callees}, "
            f"got {actual_callees}"
        )


def test_indexed_fixture_paths(indexed_fixture, expected_contract):
    """T3 acceptance: assert at least one named path from the contract
    resolves against the indexed graph (used by T7 — find_path)."""

    from api.graph import Graph

    g = Graph(indexed_fixture.project, branch=indexed_fixture.branch)

    def id_for(name: str) -> int:
        rows = g.g.query(
            "MATCH (n:Searchable {name:$n}) RETURN ID(n) LIMIT 1",
            {"n": name},
        ).result_set
        assert rows, f"symbol {name!r} not found in indexed fixture"
        return rows[0][0]

    for entry in expected_contract["paths"]:
        src = id_for(entry["source"])
        dst = id_for(entry["dest"])
        paths = g.find_paths(src, dst)
        assert len(paths) == entry["paths_count"], (
            f"paths {entry['source']!r} -> {entry['dest']!r}: "
            f"expected exactly {entry['paths_count']}, got {len(paths)}"
        )


def test_indexed_fixture_prefix_search(indexed_fixture, expected_contract):
    """T3 acceptance: assert at least one prefix-search hit from the
    contract resolves against the indexed graph (used by T8 —
    search_code)."""

    from api.auto_complete import prefix_search

    for prefix, spec in expected_contract["search_prefixes"].items():
        results = prefix_search(
            indexed_fixture.project,
            prefix,
            branch=indexed_fixture.branch,
        )
        names = {
            (r.get("properties") or {}).get("name")
            for r in results
        }
        for expected_name in spec["must_include"]:
            assert expected_name in names, (
                f"prefix {prefix!r}: expected {expected_name!r} in "
                f"results, got {sorted(n for n in names if n)}"
            )
