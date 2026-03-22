"""Tests for the cgraph CLI.

Requires FalkorDB running on localhost:6379 (same as the rest of the test suite).
"""

import json
import unittest
from pathlib import Path

from typer.testing import CliRunner

from api.cli import app

runner = CliRunner()


def _parse_json(output: str):
    """Extract the first valid JSON line from mixed stdout+stderr output."""
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError(f"No JSON found in output: {output!r}")


class TestCLIList(unittest.TestCase):
    """list command — always works if FalkorDB is reachable."""

    def test_list_returns_json(self):
        result = runner.invoke(app, ["list"])
        self.assertEqual(result.exit_code, 0)
        data = _parse_json(result.output)
        self.assertIn("repos", data)
        self.assertIsInstance(data["repos"], list)


class TestCLIEnsureDB(unittest.TestCase):
    """ensure-db command — FalkorDB is already running in CI/test."""

    def test_ensure_db_ok(self):
        result = runner.invoke(app, ["ensure-db"])
        self.assertEqual(result.exit_code, 0)
        data = _parse_json(result.output)
        self.assertEqual(data["status"], "ok")


class TestCLIIndex(unittest.TestCase):
    """Index a small fixture directory and query it."""

    FIXTURE_DIR = Path(__file__).parent / "source_files" / "py"
    REPO_NAME = "cli_test_py"

    @classmethod
    def setUpClass(cls):
        result = runner.invoke(
            app,
            ["index", str(cls.FIXTURE_DIR), "--repo", cls.REPO_NAME],
        )
        assert result.exit_code == 0, result.output
        cls.index_data = _parse_json(result.output)

    def test_index_status(self):
        self.assertEqual(self.index_data["status"], "ok")
        self.assertEqual(self.index_data["repo"], self.REPO_NAME)

    def test_index_created_nodes(self):
        self.assertGreater(self.index_data["node_count"], 0)

    def test_info(self):
        result = runner.invoke(app, ["info", "--repo", self.REPO_NAME])
        self.assertEqual(result.exit_code, 0)
        data = _parse_json(result.output)
        self.assertIn("node_count", data)
        self.assertIn("edge_count", data)
        self.assertEqual(data["repo"], self.REPO_NAME)

    def test_search(self):
        result = runner.invoke(
            app, ["search", "src", "--repo", self.REPO_NAME]
        )
        self.assertEqual(result.exit_code, 0)
        data = _parse_json(result.output)
        self.assertIn("results", data)
        # The fixture has a file named src.py, so we should find something
        self.assertIsInstance(data["results"], list)

    def test_list_includes_repo(self):
        result = runner.invoke(app, ["list"])
        self.assertEqual(result.exit_code, 0)
        data = _parse_json(result.output)
        self.assertIn(self.REPO_NAME, data["repos"])


class TestCLIHelp(unittest.TestCase):
    """Smoke test: --help should always work without a DB."""

    def test_main_help(self):
        result = runner.invoke(app, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("index", result.output)
        self.assertIn("search", result.output)

    def test_index_help(self):
        result = runner.invoke(app, ["index", "--help"])
        self.assertEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
