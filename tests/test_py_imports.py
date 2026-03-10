import os
import unittest
from pathlib import Path

from api import SourceAnalyzer, File, Graph


class Test_PY_Imports(unittest.TestCase):
    def test_import_tracking(self):
        """Test that Python imports are tracked correctly."""
        # Get test file path
        current_dir = os.path.dirname(os.path.abspath(__file__))
        test_path = os.path.join(current_dir, 'source_files', 'py_imports')
        
        # Create graph and analyze
        g = Graph("py_imports_test")
        analyzer = SourceAnalyzer()
        
        try:
            analyzer.analyze_local_folder(test_path, g)
            
            # Verify files were created
            module_a = g.get_file('', 'module_a.py', '.py')
            self.assertIsNotNone(module_a, "module_a.py should be in the graph")
            
            module_b = g.get_file('', 'module_b.py', '.py')
            self.assertIsNotNone(module_b, "module_b.py should be in the graph")
            
            # Verify classes were created
            class_a = g.get_class_by_name('ClassA')
            self.assertIsNotNone(class_a, "ClassA should be in the graph")
            
            class_b = g.get_class_by_name('ClassB')
            self.assertIsNotNone(class_b, "ClassB should be in the graph")
            
            # Verify function was created
            func_a = g.get_function_by_name('function_a')
            self.assertIsNotNone(func_a, "function_a should be in the graph")
            
            # Test: module_b should have IMPORTS relationship to ClassA
            # Query to check if module_b imports ClassA
            query = """
                MATCH (f:File {name: 'module_b.py'})-[:IMPORTS]->(c:Class {name: 'ClassA'})
                RETURN c
            """
            result = g._query(query, {})
            self.assertGreater(len(result.result_set), 0, 
                             "module_b.py should import ClassA")
            
            # Test: module_b should have IMPORTS relationship to function_a
            query = """
                MATCH (f:File {name: 'module_b.py'})-[:IMPORTS]->(fn:Function {name: 'function_a'})
                RETURN fn
            """
            result = g._query(query, {})
            self.assertGreater(len(result.result_set), 0, 
                             "module_b.py should import function_a")
            
            print("✓ Import tracking test passed")
            
        finally:
            # Cleanup: delete the test graph
            g.delete()


if __name__ == '__main__':
    unittest.main()
