import unittest
from pathlib import Path
from falkordb import FalkorDB
from api import Graph
from api.entities import File


class TestGraphOps(unittest.TestCase):
    def setUp(self):
        self.db = FalkorDB()
        self.g = self.db.select_graph('test')
        self.graph = Graph(name='test')

    def test_add_function(self):
        func_id = self.graph.add_entity(
            'Function', 'func', '', '/path/to/function', 1, 10,
            {'ret_type': 'int', 'src': '', 'args': [['x', 'int'], ['y', 'float']]}
        )
        result = self.graph.get_function(func_id)
        self.assertIsNotNone(result)
        self.assertEqual(result.properties['name'], 'func')
        self.assertEqual(result.properties['ret_type'], 'int')
        self.assertEqual(result.properties['args'], [['x', 'int'], ['y', 'float']])

    def test_add_file(self):
        file = File(Path('/path/to/file.txt'), None)
        self.graph.add_file(file)
        result = self.graph.get_file('/path/to/file.txt', 'file.txt', '.txt')
        self.assertIsNotNone(result)
        self.assertEqual(result.properties['name'], 'file.txt')
        self.assertEqual(result.properties['ext'], '.txt')

    def test_file_add_function(self):
        file = File(Path('/path/to/file.txt'), None)
        self.graph.add_file(file)

        func_id = self.graph.add_entity(
            'Function', 'func', '', '/path/to/function', 1, 10,
            {'ret_type': 'int', 'src': '', 'args': []}
        )

        self.graph.connect_entities("CONTAINS", file.id, func_id)

        query = """MATCH (file:File)-[:CONTAINS]->(func:Function)
                   WHERE ID(func) = $func_id AND ID(file) = $file_id
                   RETURN true"""

        params = {'file_id': file.id, 'func_id': func_id}
        res = self.g.query(query, params).result_set
        self.assertTrue(res[0][0])

    def test_function_calls_function(self):
        caller_id = self.graph.add_entity(
            'Function', 'func_A', '', '/path/to/function', 1, 10,
            {'ret_type': 'int', 'src': '', 'args': []}
        )
        callee_id = self.graph.add_entity(
            'Function', 'func_B', '', '/path/to/function', 11, 21,
            {'ret_type': 'int', 'src': '', 'args': []}
        )

        self.graph.function_calls_function(caller_id, callee_id, 10)

        query = """MATCH (caller:Function)-[:CALLS]->(callee:Function)
               WHERE ID(caller) = $caller_id AND ID(callee) = $callee_id
               RETURN true"""

        params = {'caller_id': caller_id, 'callee_id': callee_id}
        res = self.g.query(query, params).result_set
        self.assertTrue(res[0][0])

    def test_add_files_batch(self):
        files = [File(Path(f'/batch/file{i}.py'), None) for i in range(5)]
        self.graph.add_files_batch(files)

        for i, f in enumerate(files):
            self.assertIsNotNone(f.id)
            result = self.graph.get_file(f'/batch/file{i}.py', f'file{i}.py', '.py')
            self.assertIsNotNone(result)
            self.assertEqual(result.properties['name'], f'file{i}.py')

    def test_add_files_batch_empty(self):
        self.graph.add_files_batch([])

    def test_add_entities_batch(self):
        from api.entities.entity import Entity
        from unittest.mock import MagicMock

        entities_data = []
        for i in range(3):
            mock_entity = MagicMock()
            mock_entity.id = None
            entities_data.append((
                mock_entity, 'Function', f'func_{i}', f'doc {i}',
                '/batch/path', i * 10, i * 10 + 5, {}
            ))

        self.graph.add_entities_batch(entities_data)

        for item in entities_data:
            self.assertIsNotNone(item[0].id)

    def test_connect_entities_batch(self):
        file = File(Path('/batch/connect_test.py'), None)
        self.graph.add_file(file)

        func_a_id = self.graph.add_entity(
            'Function', 'batch_a', '', '/batch/connect_test.py', 1, 5, {}
        )
        func_b_id = self.graph.add_entity(
            'Function', 'batch_b', '', '/batch/connect_test.py', 6, 10, {}
        )
        func_c_id = self.graph.add_entity(
            'Function', 'batch_c', '', '/batch/connect_test.py', 11, 15, {}
        )

        self.graph.connect_entities_batch([
            ("DEFINES", file.id, func_a_id, {}),
            ("DEFINES", file.id, func_b_id, {}),
            ("DEFINES", file.id, func_c_id, {}),
            ("CALLS", func_a_id, func_b_id, {"line": 3, "text": "batch_b()"}),
        ])

        # Verify DEFINES relationships
        q = """MATCH (f:File)-[:DEFINES]->(fn:Function)
               WHERE ID(f) = $file_id
               RETURN count(fn)"""
        res = self.g.query(q, {'file_id': file.id}).result_set
        self.assertEqual(res[0][0], 3)

        # Verify CALLS relationship with properties
        q = """MATCH (a:Function)-[c:CALLS]->(b:Function)
               WHERE ID(a) = $a_id AND ID(b) = $b_id
               RETURN c.line, c.text"""
        res = self.g.query(q, {'a_id': func_a_id, 'b_id': func_b_id}).result_set
        self.assertEqual(res[0][0], 3)
        self.assertEqual(res[0][1], "batch_b()")

    def test_connect_entities_batch_empty(self):
        self.graph.connect_entities_batch([])

if __name__ == '__main__':
    unittest.main()
