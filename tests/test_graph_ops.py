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

if __name__ == '__main__':
    unittest.main()
