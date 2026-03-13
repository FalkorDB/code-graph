import unittest
from falkordb import FalkorDB
from typing import List, Optional
from api import *


class TestGraphOps(unittest.TestCase):
    def setUp(self):
        self.db = FalkorDB()
        self.g = self.db.select_graph('test')
        self.graph = Graph(name='test')

    def test_add_function(self):
        # Create function
        func = Function('/path/to/function', 'func', '', 'int', '', 1, 10)
        func.add_argument('x', 'int')
        func.add_argument('y', 'float')

        self.graph.add_function(func)
        self.assertEqual(func, self.graph.get_function(func.id))

    def test_add_file(self):
        file = File('/path/to/file', 'file', 'txt')

        self.graph.add_file(file)
        self.assertEqual(file, self.graph.get_file('/path/to/file', 'file', 'txt'))

    def test_file_add_function(self):
        file = File('/path/to/file', 'file', 'txt')
        func = Function('/path/to/function', 'func', '', 'int', '', 1, 10)

        self.graph.add_file(file)
        self.graph.add_function(func)

        self.graph.connect_entities("CONTAINS", file.id, func.id)

        query = """MATCH (file:File)-[:CONTAINS]->(func:Function)
                   WHERE ID(func) = $func_id AND ID(file) = $file_id
                   RETURN true"""

        params = {'file_id': file.id, 'func_id': func.id}
        res = self.g.query(query, params).result_set
        self.assertTrue(res[0][0])

    def test_function_calls_function(self):
        caller = Function('/path/to/function', 'func_A', '', 'int', '', 1, 10)
        callee = Function('/path/to/function', 'func_B', '', 'int', '', 11, 21)

        self.graph.add_function(caller)
        self.graph.add_function(callee)
        self.graph.function_calls_function(caller.id, callee.id, 10)

        query = """MATCH (caller:Function)-[:CALLS]->(callee:Function)
               WHERE ID(caller) = $caller_id AND ID(callee) = $callee_id
               RETURN true"""

        params = {'caller_id': caller.id, 'callee_id': callee.id}
        res = self.g.query(query, params).result_set
        self.assertTrue(res[0][0])

if __name__ == '__main__':
    unittest.main()
