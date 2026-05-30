"""JavaScript analyzer using tree-sitter for code entity extraction."""

from pathlib import Path
from typing import Optional

from multilspy import SyncLanguageServer
from ...entities.entity import Entity
from ...entities.file import File
from ..analyzer import AbstractAnalyzer

import tree_sitter_javascript as tsjs
from tree_sitter import Language, Node

import logging
logger = logging.getLogger('code_graph')


class JavaScriptAnalyzer(AbstractAnalyzer):
    """Analyzer for JavaScript source files using tree-sitter.

    Extracts functions, classes, and methods from JavaScript code.
    Resolves class inheritance (extends) and function/method call references.
    """

    def __init__(self) -> None:
        """Initialize the JavaScript analyzer with the tree-sitter JS grammar."""
        super().__init__(Language(tsjs.language()))

    def add_dependencies(self, path: Path, files: list[Path]) -> None:
        """Detect and register JavaScript project dependencies.

        Currently a no-op; npm dependency resolution is not yet implemented.
        """
        pass

    def get_entity_label(self, node: Node) -> str:
        """Return the graph label for a given AST node type.

        Args:
            node: A tree-sitter AST node representing a JavaScript entity.

        Returns:
            One of 'Function', 'Class', or 'Method'.

        Raises:
            ValueError: If the node type is not a recognised entity.
        """
        if node.type == 'function_declaration':
            return "Function"
        elif node.type == 'class_declaration':
            return "Class"
        elif node.type == 'method_definition':
            return "Method"
        raise ValueError(f"Unknown entity type: {node.type}")

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

    def get_entity_types(self) -> list[str]:
        """Return the tree-sitter node types recognised as JavaScript entities."""
        return ['function_declaration', 'class_declaration', 'method_definition']

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

    def resolve_path(self, file_path: str, path: Path) -> str:
        """Resolve an import path relative to the project root."""
        return file_path

    def resolve_type(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, node: Node) -> list[Entity]:
        """Resolve a type reference to its class declaration entity."""
        res = []
        for file, resolved_node in self.resolve(files, lsp, file_path, path, node):
            type_dec = self.find_parent(resolved_node, ['class_declaration'])
            if type_dec in file.entities:
                res.append(file.entities[type_dec])
        return res

    def resolve_method(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, node: Node) -> list[Entity]:
        """Resolve a call expression to the target function or method entity."""
        res = []
        if node.type == 'call_expression':
            func_node = node.child_by_field_name('function')
            if func_node and func_node.type == 'member_expression':
                func_node = func_node.child_by_field_name('property')
            if func_node:
                node = func_node
        for file, resolved_node in self.resolve(files, lsp, file_path, path, node):
            method_dec = self.find_parent(resolved_node, ['function_declaration', 'method_definition', 'class_declaration'])
            if method_dec and method_dec.type == 'class_declaration':
                continue
            if method_dec in file.entities:
                res.append(file.entities[method_dec])
        return res

    def add_file_imports(self, file: File) -> None:
        """JavaScript import tracking not yet implemented."""
        pass

    def resolve_import(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, import_node: Node) -> list[Entity]:
        """JavaScript import resolution not yet implemented."""
        return []

    def resolve_symbol(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, key: str, symbol: Node) -> list[Entity]:
        """Dispatch symbol resolution based on the symbol category.

        Routes ``base_class`` symbols to type resolution and ``call`` symbols
        to method resolution.
        """
        if key == "base_class":
            return self.resolve_type(files, lsp, file_path, path, symbol)
        elif key == "call":
            return self.resolve_method(files, lsp, file_path, path, symbol)
        else:
            raise ValueError(f"Unknown key {key}")
