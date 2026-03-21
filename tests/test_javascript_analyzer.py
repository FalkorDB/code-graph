"""Tests for the JavaScript analyzer - extraction only (no DB required)."""

import unittest
from pathlib import Path

from api.analyzers.javascript.analyzer import JavaScriptAnalyzer
from api.entities.entity import Entity
from api.entities.file import File


def _entity_name(analyzer, entity):
    """Get the name of an entity using the analyzer."""
    return analyzer.get_entity_name(entity.node)


class TestJavaScriptAnalyzer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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
                # Also recurse into entity children (e.g., class body methods)
                stack.extend(node.children)
            else:
                stack.extend(node.children)

    def _entity_names(self):
        return [_entity_name(self.analyzer, e) for e in self.file.entities.values()]

    def test_discovers_js_files(self):
        """SourceAnalyzer should enumerate .js files."""
        source_dir = Path(__file__).parent / "source_files" / "javascript"
        js_files = list(source_dir.rglob("*.js"))
        self.assertTrue(len(js_files) > 0, "Should find .js files")

    def test_entity_types(self):
        """Analyzer should recognise JS entity types."""
        self.assertEqual(
            self.analyzer.get_entity_types(),
            ['function_declaration', 'class_declaration', 'method_definition'],
        )

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

    def test_base_class_symbol(self):
        """Circle should have Shape as a base_class symbol."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) == "Circle":
                base_names = [
                    s.symbol.text.decode("utf-8")
                    for s in entity.symbols.get("base_class", [])
                ]
                self.assertIn("Shape", base_names)

    def test_is_dependency(self):
        """node_modules paths should be flagged as dependencies."""
        self.assertTrue(self.analyzer.is_dependency("foo/node_modules/bar/index.js"))
        self.assertFalse(self.analyzer.is_dependency("src/utils.js"))


if __name__ == "__main__":
    unittest.main()
