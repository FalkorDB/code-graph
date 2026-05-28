from collections import Counter
from pathlib import Path

from api.analyzers.javascript.analyzer import JavaScriptAnalyzer
from api.analyzers.kotlin.analyzer import KotlinAnalyzer
from api.analyzers.python.analyzer import PythonAnalyzer
from api.analyzers.source_analyzer import SourceAnalyzer, analyzers
from api.entities.file import File


class MockGraph:
    def __init__(self):
        self._next_id = 1
        self.files = []
        self.entities = {}
        self.edges = []

    def add_file(self, file):
        file.id = self._next_id
        self._next_id += 1
        self.files.append(file)

    def add_entity(self, label, name, doc, path, src_start, src_end, props):
        entity_id = self._next_id
        self._next_id += 1
        self.entities[entity_id] = {
            "label": label,
            "name": name,
            "doc": doc,
            "path": path,
            "src_start": src_start,
            "src_end": src_end,
            "props": props,
        }
        return entity_id

    def connect_entities(self, rel, src, dest, props=None):
        self.edges.append((rel, src, dest, props))


def test_tree_sitter_subclasses_expose_expected_entity_node_types():
    assert list(PythonAnalyzer.entity_node_types) == [
        'class_definition',
        'function_definition',
    ]
    assert list(JavaScriptAnalyzer.entity_node_types) == [
        'function_declaration',
        'class_declaration',
        'method_definition',
    ]
    assert list(KotlinAnalyzer.entity_node_types) == [
        'class_declaration',
        'object_declaration',
        'function_declaration',
    ]


def test_tree_sitter_multilanguage_fixture_graph_counts():
    source_analyzer = SourceAnalyzer()
    graph = MockGraph()
    fixture_dir = Path(__file__).parent / "fixtures" / "multilang"

    for file_path in sorted(fixture_dir.iterdir()):
        analyzer = analyzers[file_path.suffix]
        tree = analyzer.parser.parse(file_path.read_bytes())
        file = File(file_path, tree)
        graph.add_file(file)
        source_analyzer.create_hierarchy(file, analyzer, graph)

    assert len(graph.files) == 3
    assert len(graph.entities) == 9
    assert len(graph.files) + len(graph.entities) == 12
    assert len(graph.edges) == 9
    assert Counter(entity["label"] for entity in graph.entities.values()) == Counter(
        {"Class": 3, "Function": 4, "Method": 2}
    )
    assert Counter(edge[0] for edge in graph.edges) == Counter({"DEFINES": 9})
