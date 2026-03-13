import os
import unittest
from pathlib import Path

from api import SourceAnalyzer, File, Struct, Function, Graph

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
        analyzer.analyze_local_folder(path, g)

        f = g.get_file('', 'src.c', '.c')
        self.assertEqual(File('', 'src.c', '.c'), f)

        s = g.get_struct_by_name('exp')
        expected_s = Struct('src.c', 'exp', '', 9, 13)
        expected_s.add_field('i', 'int')
        expected_s.add_field('f', 'float')
        expected_s.add_field('data', 'char[]')
        self.assertEqual(expected_s, s)

        add = g.get_function_by_name('add')

        expected_add = Function('src.c', 'add', '', 'int', '', 0, 7)
        expected_add.add_argument('a', 'int')
        expected_add.add_argument('b', 'int')
        self.assertEqual(expected_add, add)
        self.assertIn('a + b', add.src)

        main = g.get_function_by_name('main')

        expected_main = Function('src.c', 'main', '', 'int', '', 15, 18)
        expected_main.add_argument('argv', 'const char**')
        expected_main.add_argument('argc', 'int')
        self.assertEqual(expected_main, main)
        self.assertIn('x = add', main.src)

        callees = g.function_calls(main.id)
        self.assertEqual(len(callees), 1)
        self.assertEqual(callees[0], add)

        callers = g.function_called_by(add.id)
        callers = [caller.name for caller in callers]

        self.assertEqual(len(callers), 2)
        self.assertIn('add', callers)
        self.assertIn('main', callers)

