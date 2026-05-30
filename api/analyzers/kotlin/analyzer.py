from pathlib import Path
from ...entities.entity import Entity
from ...entities.file import File
from typing import Optional
from ..analyzer import AbstractAnalyzer

from multilspy import SyncLanguageServer

import tree_sitter_kotlin as tskotlin
from tree_sitter import Language, Node

import logging
logger = logging.getLogger('code_graph')

class KotlinAnalyzer(AbstractAnalyzer):
    def __init__(self) -> None:
        super().__init__(Language(tskotlin.language()))

    def add_dependencies(self, path: Path, files: list[Path]):
        # For now, we skip dependency resolution for Kotlin
        # In the future, this could parse build.gradle or pom.xml for Kotlin projects
        pass

    def get_entity_label(self, node: Node) -> str:
        if node.type == 'class_declaration':
            # Check if it's an interface by looking for interface keyword
            for child in node.children:
                if child.type == 'interface':
                    return "Interface"
            return "Class"
        elif node.type == 'object_declaration':
            return "Object"
        elif node.type == 'function_declaration':
            # Check if this is a method (inside a class) or a top-level function
            parent = node.parent
            if parent and parent.type == 'class_body':
                return "Method"
            return "Function"
        raise ValueError(f"Unknown entity type: {node.type}")

    def get_entity_name(self, node: Node) -> str:
        if node.type in ['class_declaration', 'object_declaration', 'function_declaration']:
            for child in node.children:
                if child.type == 'identifier':
                    return child.text.decode('utf-8')
        raise ValueError(f"Cannot extract name from entity type: {node.type}")
    
    def get_entity_docstring(self, node: Node) -> Optional[str]:
        if node.type in ['class_declaration', 'object_declaration', 'function_declaration']:
            # Check for KDoc comment (/** ... */) before the node
            if node.prev_sibling and node.prev_sibling.type == "multiline_comment":
                comment_text = node.prev_sibling.text.decode('utf-8')
                # Only return if it's a KDoc comment (starts with /**)
                if comment_text.startswith('/**'):
                    return comment_text
            return None
        raise ValueError(f"Unknown entity type: {node.type}")        

    def get_entity_types(self) -> list[str]:
        return ['class_declaration', 'object_declaration', 'function_declaration']
    
    def _get_delegation_types(self, entity: Entity) -> list[tuple]:
        """Extract type identifiers from delegation specifiers in order.
        
        Returns list of (node, is_constructor_invocation) tuples.
        constructor_invocation indicates a superclass; plain user_type indicates an interface.
        """
        types = []
        for child in entity.node.children:
            if child.type == 'delegation_specifiers':
                for spec in child.children:
                    if spec.type == 'delegation_specifier':
                        for sub in spec.children:
                            if sub.type == 'constructor_invocation':
                                for s in sub.children:
                                    if s.type == 'user_type':
                                        for id_node in s.children:
                                            if id_node.type == 'identifier':
                                                types.append((id_node, True))
                            elif sub.type == 'user_type':
                                for id_node in sub.children:
                                    if id_node.type == 'identifier':
                                        types.append((id_node, False))
        return types

    def add_symbols(self, entity: Entity) -> None:
        if entity.node.type == 'class_declaration':
            types = self._get_delegation_types(entity)
            for node, is_class in types:
                if is_class:
                    entity.add_symbol("base_class", node)
                else:
                    entity.add_symbol("implement_interface", node)
                    
        elif entity.node.type == 'object_declaration':
            types = self._get_delegation_types(entity)
            for node, _ in types:
                entity.add_symbol("implement_interface", node)
                    
        elif entity.node.type == 'function_declaration':
            # Find function calls
            captures = self._captures("(call_expression) @reference.call", entity.node)
            if 'reference.call' in captures:
                for caller in captures['reference.call']:
                    entity.add_symbol("call", caller)
            
            # Find parameters with types
            captures = self._captures("(parameter (user_type (identifier) @parameter))", entity.node)
            if 'parameter' in captures:
                for parameter in captures['parameter']:
                    entity.add_symbol("parameters", parameter)
            
            # Find return type
            captures = self._captures("(function_declaration (user_type (identifier) @return_type))", entity.node)
            if 'return_type' in captures:
                for return_type in captures['return_type']:
                    entity.add_symbol("return_type", return_type)

    def is_dependency(self, file_path: str) -> bool:
        # Check if file is in a dependency directory (e.g., build, .gradle cache)
        return "build/" in file_path or ".gradle/" in file_path or "/cache/" in file_path

    def resolve_path(self, file_path: str, path: Path) -> str:
        # For Kotlin, just return the file path as-is for now
        return file_path

    def resolve_type(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, node: Node) -> list[Entity]:
        res = []
        for file, resolved_node in self.resolve(files, lsp, file_path, path, node):
            type_dec = self.find_parent(resolved_node, ['class_declaration', 'object_declaration'])
            if type_dec in file.entities:
                res.append(file.entities[type_dec])
        return res

    def resolve_method(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, node: Node) -> list[Entity]:
        res = []
        # For call expressions, we need to extract the function name
        if node.type == 'call_expression':
            # Find the identifier being called
            for child in node.children:
                if child.type in ['identifier', 'navigation_expression']:
                    for file, resolved_node in self.resolve(files, lsp, file_path, path, child):
                        method_dec = self.find_parent(resolved_node, ['function_declaration', 'class_declaration', 'object_declaration'])
                        if method_dec and method_dec.type in ['class_declaration', 'object_declaration']:
                            continue
                        if method_dec in file.entities:
                            res.append(file.entities[method_dec])
                    break
        return res
    
    def add_file_imports(self, file: File) -> None:
        """Kotlin import tracking not yet implemented."""
        pass

    def resolve_import(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, import_node: Node) -> list[Entity]:
        """Kotlin import resolution not yet implemented."""
        return []

    def resolve_symbol(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, key: str, symbol: Node) -> list[Entity]:
        if key in ["implement_interface", "base_class", "parameters", "return_type"]:
            return self.resolve_type(files, lsp, file_path, path, symbol)
        elif key in ["call"]:
            return self.resolve_method(files, lsp, file_path, path, symbol)
        else:
            raise ValueError(f"Unknown key {key}")
