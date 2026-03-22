"""Tests for the JavaScript analyzer - extraction only (no DB required)."""

import unittest
from pathlib import Path

from api.analyzers.javascript.analyzer import JavaScriptAnalyzer
from api.analyzers.source_analyzer import SourceAnalyzer, analyzers
from api.entities.entity import Entity
from api.entities.file import File


def _entity_name(analyzer, entity):
    """Get the name of an entity using the analyzer."""
    return analyzer.get_entity_name(entity.node)


class TestJavaScriptAnalyzer(unittest.TestCase):
    """Unit tests for JavaScriptAnalyzer entity extraction and classification."""

    @classmethod
    def setUpClass(cls):
        """Parse sample.js and populate entities for all tests."""
        cls.analyzer = JavaScriptAnalyzer()
        source_dir = Path(__file__).parent / "source_files" / "javascript"
        cls.sample_path = source_dir / "sample.js"
        source = cls.sample_path.read_bytes()
        tree = cls.analyzer.parser.parse(source)
        cls.file = File(cls.sample_path, tree)

        # Walk AST and extract entities (mirrors create_hierarchy without Graph)
        types = cls.analyzer.get_entity_types()
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if node.type in types:
                entity = Entity(node)
                cls.analyzer.add_symbols(entity)
                cls.file.add_entity(entity)
                stack.extend(node.children)
            else:
                stack.extend(node.children)

    def _entity_names(self):
        """Return all entity names discovered in the sample file."""
        return [_entity_name(self.analyzer, e) for e in self.file.entities.values()]

    # -- Registration ----------------------------------------------------------

    def test_js_extension_registered(self):
        """The .js extension should be registered in the analyzers map."""
        self.assertIn(".js", analyzers)
        self.assertIsInstance(analyzers[".js"], JavaScriptAnalyzer)

    def test_discovers_js_files(self):
        """SourceAnalyzer should enumerate .js files."""
        source_dir = Path(__file__).parent / "source_files" / "javascript"
        js_files = list(source_dir.rglob("*.js"))
        self.assertTrue(len(js_files) > 0, "Should find .js files")

    # -- Entity types ----------------------------------------------------------

    def test_entity_types(self):
        """Analyzer should recognise JS entity types."""
        self.assertEqual(
            self.analyzer.get_entity_types(),
            ['function_declaration', 'class_declaration', 'method_definition'],
        )

    # -- Entity extraction -----------------------------------------------------

    def test_class_extraction(self):
        """Classes should be extracted from sample.js."""
        names = self._entity_names()
        self.assertIn("Shape", names)
        self.assertIn("Circle", names)

    def test_function_extraction(self):
        """Top-level functions should be extracted."""
        names = self._entity_names()
        self.assertIn("calculateTotal", names)

    def test_method_extraction(self):
        """Class methods should be extracted."""
        names = self._entity_names()
        self.assertIn("area", names)
        self.assertIn("constructor", names)

    # -- Labels ----------------------------------------------------------------

    def test_class_labels(self):
        """Classes should get the 'Class' label."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) in ("Shape", "Circle"):
                self.assertEqual(self.analyzer.get_entity_label(entity.node), "Class")

    def test_function_label(self):
        """Functions should get the 'Function' label."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) == "calculateTotal":
                self.assertEqual(self.analyzer.get_entity_label(entity.node), "Function")

    def test_method_label(self):
        """Methods should get the 'Method' label."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) == "area":
                self.assertEqual(self.analyzer.get_entity_label(entity.node), "Method")
                break

    def test_unknown_entity_label_raises(self):
        """get_entity_label should raise ValueError for unknown node types."""
        source = b"let x = 1;"
        tree = self.analyzer.parser.parse(source)
        node = tree.root_node
        with self.assertRaises(ValueError):
            self.analyzer.get_entity_label(node)

    def test_unknown_entity_name_raises(self):
        """get_entity_name should raise ValueError for unknown node types."""
        source = b"let x = 1;"
        tree = self.analyzer.parser.parse(source)
        node = tree.root_node
        with self.assertRaises(ValueError):
            self.analyzer.get_entity_name(node)

    # -- Docstrings ------------------------------------------------------------

    def test_class_docstring(self):
        """Shape class should have a leading comment as docstring."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) == "Shape":
                doc = self.analyzer.get_entity_docstring(entity.node)
                self.assertIsNotNone(doc)
                self.assertIn("Base class for shapes", doc)
                break

    def test_no_docstring(self):
        """Entities without a leading comment should return None."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) == "Circle":
                doc = self.analyzer.get_entity_docstring(entity.node)
                self.assertIsNone(doc)
                break

    def test_unknown_entity_docstring_raises(self):
        """get_entity_docstring should raise ValueError for unknown node types."""
        source = b"let x = 1;"
        tree = self.analyzer.parser.parse(source)
        node = tree.root_node
        with self.assertRaises(ValueError):
            self.analyzer.get_entity_docstring(node)

    # -- Symbols ---------------------------------------------------------------

    def test_base_class_symbol(self):
        """Circle should have Shape as a base_class symbol."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) == "Circle":
                base_names = [
                    s.symbol.text.decode("utf-8")
                    for s in entity.symbols.get("base_class", [])
                ]
                self.assertIn("Shape", base_names)

    def test_no_parameters_symbol(self):
        """JS functions should NOT capture untyped parameters as symbols.

        Unlike typed languages (Java, Python), plain JS parameter names are
        not meaningful type references and should not be extracted.
        """
        for entity in self.file.entities.values():
            self.assertNotIn(
                "parameters", entity.symbols,
                f"Entity '{_entity_name(self.analyzer, entity)}' should not have "
                f"parameter symbols — JS params are untyped",
            )

    def test_call_symbols_extracted(self):
        """Functions with call expressions should have 'call' symbols."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) == "calculateTotal":
                self.assertIn("call", entity.symbols)
                break

    def test_class_without_extends_has_no_base_class(self):
        """Shape (no extends) should have no base_class symbols."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) == "Shape":
                self.assertEqual(len(entity.symbols.get("base_class", [])), 0)

    # -- resolve_symbol dispatch -----------------------------------------------

    def test_resolve_symbol_unknown_key_raises(self):
        """resolve_symbol should raise ValueError for unknown symbol keys."""
        with self.assertRaises(ValueError):
            self.analyzer.resolve_symbol({}, None, Path("f.js"), Path("."), "unknown_key", None)

    # -- Dependency detection --------------------------------------------------

    def test_is_dependency(self):
        """node_modules paths should be flagged as dependencies."""
        self.assertTrue(self.analyzer.is_dependency("foo/node_modules/bar/index.js"))
        self.assertFalse(self.analyzer.is_dependency("src/utils.js"))

    def test_is_dependency_path_segment_matching(self):
        """is_dependency should use path-segment matching, not substring.

        A directory named 'node_modules_utils' should NOT be treated as a
        dependency — only actual 'node_modules' path segments count.
        """
        self.assertFalse(
            self.analyzer.is_dependency("src/node_modules_utils/helper.js")
        )
        self.assertTrue(
            self.analyzer.is_dependency("lib/node_modules/lodash/index.js")
        )

    # -- SourceAnalyzer integration --------------------------------------------

    def test_source_analyzer_supported_types_includes_js(self):
        """SourceAnalyzer.supported_types() should include '.js'."""
        sa = SourceAnalyzer()
        self.assertIn(".js", sa.supported_types())

    def test_source_analyzer_create_hierarchy(self):
        """SourceAnalyzer.create_hierarchy() should process JS files correctly.

        Uses a lightweight mock Graph to verify the production code path
        without requiring a database connection.
        """
        class MockGraph:
            def __init__(self):
                self._next_id = 1
                self.entities = {}
                self.edges = []

            def add_file(self, file):
                file.id = self._next_id
                self._next_id += 1

            def add_entity(self, label, name, doc, path, src_start, src_end, props):
                eid = self._next_id
                self._next_id += 1
                self.entities[eid] = {"label": label, "name": name, "doc": doc}
                return eid

            def connect_entities(self, rel, src, dest, props=None):
                self.edges.append((rel, src, dest))

        sa = SourceAnalyzer()
        source = self.sample_path.read_bytes()
        tree = self.analyzer.parser.parse(source)
        file = File(self.sample_path, tree)
        graph = MockGraph()
        graph.add_file(file)
        sa.create_hierarchy(file, self.analyzer, graph)

        entity_names = [e["name"] for e in graph.entities.values()]
        self.assertIn("Shape", entity_names)
        self.assertIn("Circle", entity_names)
        self.assertIn("calculateTotal", entity_names)
        self.assertIn("area", entity_names)
        self.assertIn("constructor", entity_names)

        # Verify DEFINES edges were created (file → entities)
        defines_edges = [e for e in graph.edges if e[0] == "DEFINES"]
        self.assertTrue(len(defines_edges) > 0, "Should create DEFINES edges")


if __name__ == "__main__":
    unittest.main()
