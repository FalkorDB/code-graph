import os
import unittest
from collections import Counter
from pathlib import Path

from api import SourceAnalyzer, Graph


def _edge_snapshot(g: Graph) -> Counter:
    """Return a multiset of all relationships in the graph keyed by
    (rel_type, src_path, src_name, dst_path, dst_name) so two indexing runs
    can be compared independent of node ids or write order."""
    rows = g._query(
        "MATCH (a)-[r]->(b) "
        "RETURN type(r), a.path, a.name, b.path, b.name"
    ).result_set
    return Counter(tuple(row) for row in rows)


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

    def test_index_workers_edges_are_deterministic(self):
        """second_pass must produce identical edges regardless of
        CODE_GRAPH_INDEX_WORKERS, since phase A only parallelises symbol
        resolution while phase B writes edges in a fixed order.

        Regression guard for the parallel-resolution path (#688): runs the
        same fixture serially (workers=1) and in parallel (workers=4) and
        asserts the full relationship multiset matches.
        """
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'source_files', 'py')

        prev = os.environ.get("CODE_GRAPH_INDEX_WORKERS")
        g1 = Graph("py_workers1")
        g4 = Graph("py_workers4")
        try:
            os.environ["CODE_GRAPH_INDEX_WORKERS"] = "1"
            SourceAnalyzer().analyze_local_folder(path, g1)
            serial = _edge_snapshot(g1)

            os.environ["CODE_GRAPH_INDEX_WORKERS"] = "4"
            SourceAnalyzer().analyze_local_folder(path, g4)
            parallel = _edge_snapshot(g4)

            self.assertEqual(
                serial, parallel,
                "edge multiset differs between workers=1 and workers=4",
            )
            # Sanity: the fixture has resolvable CALLS, so guard against a
            # vacuous all-empty comparison when an LSP is available.
            self.assertGreater(
                sum(serial.values()), 0,
                "expected at least one resolved edge in the fixture",
            )
        finally:
            if prev is None:
                os.environ.pop("CODE_GRAPH_INDEX_WORKERS", None)
            else:
                os.environ["CODE_GRAPH_INDEX_WORKERS"] = prev
            g1.delete()
            g4.delete()

