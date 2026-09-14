from inspect import signature
from pathlib import Path
from unittest.mock import Mock

from api.graph import Graph


def test_delete_files_return_contract() -> None:
    graph = Graph.__new__(Graph)
    graph._query = Mock()

    result = graph.delete_files([Path("src/example.py")])

    assert result is None
    assert signature(Graph.delete_files).return_annotation is None
    graph._query.assert_called_once()
