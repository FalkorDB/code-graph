import os
import unittest
from pathlib import Path

from api import SourceAnalyzer, File, Class, Function, Graph

class Test_PY_Analyzer(unittest.TestCase):
    def test_analyzer(self):
        path = Path(__file__).parent
        analyzer = SourceAnalyzer()

        # Get the current file path
        current_file_path = os.path.abspath(__file__)

        # Get the directory of the current file
        current_dir = os.path.dirname(current_file_path)

        # Append 'source_files/c' to the current directory
        path = os.path.join(current_dir, 'source_files')
        path = os.path.join(path, 'py')
        path = str(path)

        g = Graph("py")
        analyzer.analyze_local_folder(path, g)

        f = g.get_file('', 'src.py', '.py')
        self.assertEqual(File('', 'src.py', '.py'), f)

        log = g.get_function_by_name('log')
        expected_log = Function('src.py', 'log', None, 'None', '', 0, 1)
        expected_log.add_argument('msg', 'str')
        self.assertEqual(expected_log, log)

        abort = g.get_function_by_name('abort')
        expected_abort = Function('src.py', 'abort', None, 'Task', '', 9, 11)
        expected_abort.add_argument('self', 'Unknown')
        expected_abort.add_argument('delay', 'float')
        self.assertEqual(expected_abort, abort)

        init = g.get_function_by_name('__init__')
        expected_init = Function('src.py', '__init__', None, None, '', 4, 7)
        expected_init.add_argument('self', 'Unknown')
        expected_init.add_argument('name', 'str')
        expected_init.add_argument('duration', 'int')
        self.assertEqual(expected_init, init)

        task = g.get_class_by_name('Task')
        expected_task = Class('src.py', 'Task', None, 3, 11)
        self.assertEqual(expected_task, task)

        callees = g.function_calls(abort.id)
        self.assertEqual(len(callees), 1)
        self.assertEqual(callees[0], log)

        print_func = g.get_function_by_name('print')
        callers = g.function_called_by(print_func.id)
        callers = [caller.name for caller in callers]

        self.assertIn('__init__', callers)
        self.assertIn('log', callers)

