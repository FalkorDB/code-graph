import os
import unittest
from pathlib import Path

from api import SourceAnalyzer, Graph


class Test_C_Analyzer(unittest.TestCase):
    def test_analyzer(self):
        path = Path(__file__).parent
        analyzer = SourceAnalyzer()

        # Get the current file path
        current_file_path = os.path.abspath(__file__)

        # Get the directory of the current file
        current_dir = os.path.dirname(current_file_path)

        # Append 'source_files/c' to the current directory
        path = os.path.join(current_dir, 'source_files')
        path = os.path.join(path, 'c')
        path = str(path)

        g = Graph("c")
        analyzer.analyze(path, g)

        f = g.get_file('', 'src.c', '.c')
        self.assertIsNotNone(f)
        self.assertEqual(f.properties['name'], 'src.c')
        self.assertEqual(f.properties['ext'], '.c')

        s = g.get_struct_by_name('exp')
        self.assertIsNotNone(s)
        self.assertEqual(s.properties['name'], 'exp')
        self.assertEqual(s.properties['path'], 'src.c')
        self.assertEqual(s.properties['src_start'], 9)
        self.assertEqual(s.properties['src_end'], 13)
        self.assertEqual(s.properties['fields'], [['i', 'int'], ['f', 'float'], ['data', 'char[]']])

        add = g.get_function_by_name('add')
        self.assertIsNotNone(add)
        self.assertEqual(add.properties['name'], 'add')
        self.assertEqual(add.properties['path'], 'src.c')
        self.assertEqual(add.properties['ret_type'], 'int')
        self.assertEqual(add.properties['src_start'], 0)
        self.assertEqual(add.properties['src_end'], 7)
        self.assertEqual(add.properties['args'], [['a', 'int'], ['b', 'int']])
        self.assertIn('a + b', add.properties['src'])

        main = g.get_function_by_name('main')
        self.assertIsNotNone(main)
        self.assertEqual(main.properties['name'], 'main')
        self.assertEqual(main.properties['path'], 'src.c')
        self.assertEqual(main.properties['ret_type'], 'int')
        self.assertEqual(main.properties['src_start'], 15)
        self.assertEqual(main.properties['src_end'], 18)
        self.assertEqual(main.properties['args'], [['argv', 'const char**'], ['argc', 'int']])
        self.assertIn('x = add', main.properties['src'])

        callees = g.function_calls(main.id)
        self.assertEqual(len(callees), 1)
        self.assertEqual(callees[0], add)

        callers = g.function_called_by(add.id)
        callers = [caller.properties['name'] for caller in callers]

        self.assertEqual(len(callers), 2)
        self.assertIn('add', callers)
        self.assertIn('main', callers)

        # Test for include_directive edge creation
        included_file = g.get_file('', 'myheader.h', '.h')
        self.assertIsNotNone(included_file)

        includes = g.get_neighbors([f.id], rel='INCLUDES')
        self.assertEqual(len(includes), 3)
        included_files = [node['properties']['name'] for node in includes['nodes']]
        self.assertIn('myheader.h', included_files)
