"""JavaScript analyzer using tree-sitter for code entity extraction."""

from pathlib import Path
from typing import Optional

from ...entities.entity import Entity
from ..tree_sitter_base import TreeSitterAnalyzer

import tree_sitter_javascript as tsjs
from tree_sitter import Language, Node

import logging
logger = logging.getLogger('code_graph')


class JavaScriptAnalyzer(TreeSitterAnalyzer):
    """Analyzer for JavaScript source files using tree-sitter.

    Extracts functions, classes, and methods from JavaScript code.
    Resolves class inheritance (extends) and function/method call references.
    """

    entity_node_types = {
        'function_declaration': "Function",
        'class_declaration': "Class",
        'method_definition': "Method",
    }
    type_definition_node_types = ('class_declaration',)
    callable_definition_node_types = (
        'function_declaration',
        'method_definition',
        'class_declaration',
    )
    callable_exclude_node_types = ('class_declaration',)
    type_resolution_keys = ("base_class",)
    method_resolution_keys = ("call",)

    def __init__(self) -> None:
        """Initialize the JavaScript analyzer with the tree-sitter JS grammar."""
        super().__init__(Language(tsjs.language()))

    def add_dependencies(self, path: Path, files: list[Path]) -> None:
        """Detect and register JavaScript project dependencies.

        Currently a no-op; npm dependency resolution is not yet implemented.
        """
        pass

    def get_entity_name(self, node: Node) -> str:
        """Extract the declared name from a JavaScript entity node.

        Args:
            node: A tree-sitter AST node for a function, class, or method.

        Returns:
            The entity name, or an empty string if no name node is found.

        Raises:
            ValueError: If the node type is not a recognised entity.
        """
        if node.type in ['function_declaration', 'class_declaration', 'method_definition']:
            name_node = node.child_by_field_name('name')
            if name_node is None:
                return ''
            return name_node.text.decode('utf-8')
        raise ValueError(f"Unknown entity type: {node.type}")

    def get_entity_docstring(self, node: Node) -> Optional[str]:
        """Extract a leading comment as a docstring for the entity.

        Looks for a comment node immediately preceding the entity in the AST.

        Args:
            node: A tree-sitter AST node for a function, class, or method.

        Returns:
            The comment text, or None if no leading comment exists.

        Raises:
            ValueError: If the node type is not a recognised entity.
        """
        if node.type in ['function_declaration', 'class_declaration', 'method_definition']:
            if node.prev_sibling and node.prev_sibling.type == 'comment':
                return node.prev_sibling.text.decode('utf-8')
            return None
        raise ValueError(f"Unknown entity type: {node.type}")

    def add_symbols(self, entity: Entity) -> None:
        """Extract symbols (references) from a JavaScript entity.

        For classes: extracts base-class identifiers from ``extends`` clauses.
        For functions/methods: extracts call-expression references.

        Note:
            JavaScript parameters are untyped, so they are not captured as
            symbols — unlike typed languages (Java, Python) where parameter
            type annotations are meaningful for resolution.
        """
        if entity.node.type == 'class_declaration':
            for child in entity.node.children:
                if child.type == 'class_heritage':
                    for heritage_child in child.children:
                        if heritage_child.type == 'identifier':
                            entity.add_symbol("base_class", heritage_child)
        elif entity.node.type in ['function_declaration', 'method_definition']:
            captures = self._captures("(call_expression) @reference.call", entity.node)
            if 'reference.call' in captures:
                for caller in captures['reference.call']:
                    entity.add_symbol("call", caller)

    def is_dependency(self, file_path: str) -> bool:
        """Check whether a file path belongs to an external dependency.

        Uses path-segment matching so that directories merely containing
        'node_modules' in their name (e.g. ``node_modules_utils``) are not
        treated as dependencies.
        """
        return "node_modules" in Path(file_path).parts

    def _extract_call_target(self, node: Node) -> Optional[Node]:
        """Extract the callable target from a JavaScript call expression."""
        if node.type == 'call_expression':
            func_node = node.child_by_field_name('function')
            if func_node and func_node.type == 'member_expression':
                func_node = func_node.child_by_field_name('property')
            if func_node:
                node = func_node
        return node
