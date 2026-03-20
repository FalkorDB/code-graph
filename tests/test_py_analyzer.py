import os
import unittest
from pathlib import Path

from api import SourceAnalyzer, Graph


class Test_PY_Analyzer(unittest.TestCase):
    def test_analyzer(self):
        path = Path(__file__).parent
        analyzer = SourceAnalyzer()

        # Get the current file path
        current_file_path = os.path.abspath(__file__)

        # Get the directory of the current file
        current_dir = os.path.dirname(current_file_path)

        # Append 'source_files/py' to the current directory
        path = os.path.join(current_dir, 'source_files')
        path = os.path.join(path, 'py')
        path = str(path)

        g = Graph("py")
        analyzer.analyze_local_folder(path, g)

        f = g.get_file('', 'src.py', '.py')
        self.assertIsNotNone(f)
        self.assertEqual(f.properties['name'], 'src.py')
        self.assertEqual(f.properties['ext'], '.py')

        log = g.get_function_by_name('log')
        self.assertIsNotNone(log)
        self.assertEqual(log.properties['name'], 'log')
        self.assertEqual(log.properties['path'], 'src.py')
        self.assertEqual(log.properties['ret_type'], 'None')
        self.assertEqual(log.properties['src_start'], 0)
        self.assertEqual(log.properties['src_end'], 1)
        self.assertEqual(log.properties['args'], [['msg', 'str']])

        abort = g.get_function_by_name('abort')
        self.assertIsNotNone(abort)
        self.assertEqual(abort.properties['name'], 'abort')
        self.assertEqual(abort.properties['path'], 'src.py')
        self.assertEqual(abort.properties['ret_type'], 'Task')
        self.assertEqual(abort.properties['src_start'], 9)
        self.assertEqual(abort.properties['src_end'], 11)
        self.assertEqual(abort.properties['args'], [['self', 'Unknown'], ['delay', 'float']])

        init = g.get_function_by_name('__init__')
        self.assertIsNotNone(init)
        self.assertEqual(init.properties['name'], '__init__')
        self.assertEqual(init.properties['path'], 'src.py')
        self.assertEqual(init.properties['src_start'], 4)
        self.assertEqual(init.properties['src_end'], 7)
        self.assertEqual(init.properties['args'], [['self', 'Unknown'], ['name', 'str'], ['duration', 'int']])

        task = g.get_class_by_name('Task')
        self.assertIsNotNone(task)
        self.assertEqual(task.properties['name'], 'Task')
        self.assertEqual(task.properties['path'], 'src.py')
        self.assertEqual(task.properties['src_start'], 3)
        self.assertEqual(task.properties['src_end'], 11)

        callees = g.function_calls(abort.id)
        self.assertEqual(len(callees), 1)
        self.assertEqual(callees[0], log)

        print_func = g.get_function_by_name('print')
        callers = g.function_called_by(print_func.id)
        callers = [caller.properties['name'] for caller in callers]

        self.assertIn('__init__', callers)
        self.assertIn('log', callers)

