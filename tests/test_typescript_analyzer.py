import os
import unittest

from api import SourceAnalyzer, Graph


class TestTypeScriptAnalyzer(unittest.TestCase):
    def test_analyzer(self):
        analyzer = SourceAnalyzer()

        current_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(current_dir, 'source_files', 'typescript')

        g = Graph("typescript")
        analyzer.analyze_local_folder(path, g)

        # Verify entities were created
        stats = g.stats()
        self.assertGreater(stats['node_count'], 0)

        # Verify class was extracted
        console_logger = g.get_class_by_name('ConsoleLogger')
        self.assertIsNotNone(console_logger)
        self.assertEqual(console_logger.properties['name'], 'ConsoleLogger')

        # Verify function was extracted
        greet = g.get_function_by_name('greet')
        self.assertIsNotNone(greet)
        self.assertEqual(greet.properties['name'], 'greet')
