"""Tests for the Kotlin analyzer - extraction only (no DB required)."""

import unittest
from pathlib import Path

from api.analyzers.kotlin.analyzer import KotlinAnalyzer
from api.entities.entity import Entity
from api.entities.file import File


def _entity_name(analyzer, entity):
    """Get the name of an entity using the analyzer."""
    return analyzer.get_entity_name(entity.node)


class TestKotlinAnalyzer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analyzer = KotlinAnalyzer()
        source_dir = Path(__file__).parent / "source_files" / "kotlin"
        cls.sample_path = source_dir / "sample.kt"
        source = cls.sample_path.read_bytes()
        tree = cls.analyzer.parser.parse(source)
        cls.file = File(cls.sample_path, tree)

        # Walk AST and extract entities
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
        return [_entity_name(self.analyzer, e) for e in self.file.entities.values()]

    def test_entity_types(self):
        """Analyzer should recognise Kotlin entity types."""
        self.assertEqual(
            self.analyzer.get_entity_types(),
            ['class_declaration', 'object_declaration', 'function_declaration'],
        )

    def test_class_extraction(self):
        """Classes should be extracted."""
        names = self._entity_names()
        self.assertIn("Shape", names)
        self.assertIn("Circle", names)

    def test_interface_extraction(self):
        """Interfaces should be extracted."""
        names = self._entity_names()
        self.assertIn("Logger", names)

    def test_object_extraction(self):
        """Object declarations should be extracted."""
        names = self._entity_names()
        self.assertIn("AppConfig", names)

    def test_function_extraction(self):
        """Top-level functions should be extracted."""
        names = self._entity_names()
        self.assertIn("calculateTotal", names)

    def test_class_label(self):
        """Classes should get the 'Class' label."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) in ("Shape", "Circle"):
                self.assertEqual(self.analyzer.get_entity_label(entity.node), "Class")

    def test_interface_label(self):
        """Interfaces should get the 'Interface' label."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) == "Logger":
                self.assertEqual(self.analyzer.get_entity_label(entity.node), "Interface")

    def test_object_label(self):
        """Object declarations should get the 'Object' label."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) == "AppConfig":
                self.assertEqual(self.analyzer.get_entity_label(entity.node), "Object")

    def test_base_class_symbol(self):
        """Circle should have Shape as base_class (first delegation specifier)."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) == "Circle":
                base_names = [
                    s.text.decode("utf-8")
                    for s in entity.symbols.get("base_class", [])
                ]
                self.assertIn("Shape", base_names)

    def test_interface_implementation(self):
        """Circle should implement Logger (second delegation specifier)."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) == "Circle":
                iface_names = [
                    s.text.decode("utf-8")
                    for s in entity.symbols.get("implement_interface", [])
                ]
                self.assertIn("Logger", iface_names)

    def test_is_dependency(self):
        """Build/gradle paths should be flagged as dependencies."""
        self.assertTrue(self.analyzer.is_dependency("project/build/classes/Main.kt"))
        self.assertTrue(self.analyzer.is_dependency("project/.gradle/cache/lib.kt"))
        self.assertFalse(self.analyzer.is_dependency("src/main/kotlin/App.kt"))


if __name__ == "__main__":
    unittest.main()
