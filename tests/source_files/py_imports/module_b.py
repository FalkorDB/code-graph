"""Module B that imports from module A."""

from module_a import ClassA, function_a

class ClassB(ClassA):
    """A class that extends ClassA."""
    
    def method_b(self):
        """A method in ClassB."""
        result = function_a()
        return f"Method B: {result}"
