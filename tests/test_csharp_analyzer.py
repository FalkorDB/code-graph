import os
import unittest

from api import SourceAnalyzer, Graph


class Test_CSharp_Analyzer(unittest.TestCase):
    def setUp(self):
        self.g = Graph("csharp")

    def tearDown(self):
        self.g.delete()

    def test_analyzer(self):
        analyzer = SourceAnalyzer()

        # Get the current file path
        current_file_path = os.path.abspath(__file__)

        # Get the directory of the current file
        current_dir = os.path.dirname(current_file_path)

        # Append 'source_files/csharp' to the current directory
        path = os.path.join(current_dir, 'source_files')
        path = os.path.join(path, 'csharp')
        path = str(path)

        analyzer.analyze_local_folder(path, self.g)

        # Verify ILogger interface was detected
        q = "MATCH (n:Interface {name: 'ILogger'}) RETURN n LIMIT 1"
        res = self.g._query(q).result_set
        self.assertEqual(len(res), 1)

        # Verify ConsoleLogger class was detected
        q = "MATCH (n:Class {name: 'ConsoleLogger'}) RETURN n LIMIT 1"
        res = self.g._query(q).result_set
        self.assertEqual(len(res), 1)

        # Verify Task class was detected
        q = "MATCH (n:Class {name: 'Task'}) RETURN n LIMIT 1"
        res = self.g._query(q).result_set
        self.assertEqual(len(res), 1)

        # Verify methods were detected
        for method_name in ['Log', 'Execute', 'Abort']:
            q = "MATCH (n {name: $name}) RETURN n LIMIT 1"
            res = self.g._query(q, {'name': method_name}).result_set
            self.assertGreaterEqual(len(res), 1, f"Method {method_name} not found")

        # Verify Constructor was detected
        q = "MATCH (n:Constructor {name: 'Task'}) RETURN n LIMIT 1"
        res = self.g._query(q).result_set
        self.assertEqual(len(res), 1)

        # Verify DEFINES relationships exist (File -> Class/Interface)
        q = "MATCH (f:File)-[:DEFINES]->(n) RETURN count(n)"
        res = self.g._query(q).result_set
        self.assertGreater(res[0][0], 0)

        # Verify class defines methods
        q = "MATCH (c:Class {name: 'Task'})-[:DEFINES]->(m) RETURN count(m)"
        res = self.g._query(q).result_set
        self.assertGreater(res[0][0], 0)

        # Verify ConsoleLogger implements ILogger
        q = "MATCH (c:Class {name: 'ConsoleLogger'})-[:IMPLEMENTS]->(i:Interface {name: 'ILogger'}) RETURN c, i LIMIT 1"
        res = self.g._query(q).result_set
        self.assertEqual(len(res), 1)
