import unittest
from pathlib import Path

from api.analyzers.c.analyzer import CAnalyzer
from api.entities.entity import Entity
from api.entities.file import File


def _entity_name(analyzer, entity):
    """Get the name of an entity using the analyzer."""
    return analyzer.get_entity_name(entity.node)


class TestCAnalyzer(unittest.TestCase):
    """Test the C analyzer's entity extraction (no DB required)."""

    @classmethod
    def setUpClass(cls):
        cls.analyzer = CAnalyzer()
        source_dir = Path(__file__).parent / "source_files" / "c"
        cls.sample_path = source_dir / "src.c"
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

        # Extract includes
        cls.includes = cls.analyzer.get_include_paths(tree)

    def _entity_names(self):
        return [_entity_name(self.analyzer, e) for e in self.file.entities.values()]

    def test_entity_types(self):
        """Analyzer should recognise C entity types."""
        self.assertEqual(
            self.analyzer.get_entity_types(),
            ['struct_specifier', 'function_definition'],
        )

    def test_function_extraction(self):
        """Functions should be extracted from src.c."""
        names = self._entity_names()
        self.assertIn("add", names)
        self.assertIn("main", names)

    def test_struct_extraction(self):
        """Structs should be extracted from src.c."""
        names = self._entity_names()
        self.assertIn("exp", names)

    def test_function_label(self):
        """Functions should get the 'Function' label."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) == "add":
                self.assertEqual(self.analyzer.get_entity_label(entity.node), "Function")

    def test_struct_label(self):
        """Structs should get the 'Struct' label."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) == "exp":
                self.assertEqual(self.analyzer.get_entity_label(entity.node), "Struct")

    def test_call_symbols(self):
        """Function 'main' should have call symbols (calls to 'add')."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) == "main":
                call_syms = entity.symbols.get("call", [])
                self.assertTrue(len(call_syms) > 0, "main should have call symbols")

    def test_include_extraction(self):
        """Include directives should be extracted."""
        self.assertIn("myheader.h", self.includes)
        self.assertIn("stdio.h", self.includes)

    def test_is_dependency(self):
        """is_dependency should return False for C files."""
        self.assertFalse(self.analyzer.is_dependency("src/main.c"))

    def test_docstring_extraction(self):
        """Docstring (comment above entity) should be extracted."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) == "add":
                doc = self.analyzer.get_entity_docstring(entity.node)
                self.assertIsNotNone(doc)
                self.assertIn("Adds two integers", doc)
                return
        self.fail("Function 'add' not found")

    def test_no_docstring(self):
        """Entities without a preceding comment should return None."""
        for entity in self.file.entities.values():
            if _entity_name(self.analyzer, entity) == "main":
                doc = self.analyzer.get_entity_docstring(entity.node)
                self.assertIsNone(doc)
                return
        self.fail("Function 'main' not found")

    def test_unknown_entity_label_raises(self):
        """get_entity_label should raise for unknown node types."""
        # Use the tree root node which is 'translation_unit', not a known entity
        with self.assertRaises(ValueError):
            self.analyzer.get_entity_label(self.file.tree.root_node)

    def test_unknown_entity_name_raises(self):
        """get_entity_name should raise for unknown node types."""
        with self.assertRaises(ValueError):
            self.analyzer.get_entity_name(self.file.tree.root_node)

    def test_resolve_path(self):
        """resolve_path should return the file path unchanged."""
        self.assertEqual(
            self.analyzer.resolve_path("/foo/bar.c", Path("/root")),
            "/foo/bar.c",
        )


if __name__ == "__main__":
    unittest.main()
