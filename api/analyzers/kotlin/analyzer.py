from pathlib import Path
from ...entities import *
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
        if node.type in ['class_declaration', 'object_declaration']:
            # Find the type_identifier child
            for child in node.children:
                if child.type == 'type_identifier':
                    return child.text.decode('utf-8')
        elif node.type == 'function_declaration':
            # Find the simple_identifier child
            for child in node.children:
                if child.type == 'simple_identifier':
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
    
    def add_symbols(self, entity: Entity) -> None:
        if entity.node.type == 'class_declaration':
            # Find superclass (extends)
            superclass_query = self.language.query("(delegation_specifier (user_type (type_identifier) @superclass))")
            superclass_captures = superclass_query.captures(entity.node)
            if 'superclass' in superclass_captures:
                for superclass in superclass_captures['superclass']:
                    entity.add_symbol("base_class", superclass)
            
            # Find interfaces (implements)
            # In Kotlin, both inheritance and interface implementation use the same syntax
            # We'll treat all as interfaces for now since Kotlin can only extend one class
            interface_query = self.language.query("(delegation_specifier (user_type (type_identifier) @interface))")
            interface_captures = interface_query.captures(entity.node)
            if 'interface' in interface_captures:
                for interface in interface_captures['interface']:
                    entity.add_symbol("implement_interface", interface)
                    
        elif entity.node.type == 'object_declaration':
            # Objects can also have delegation specifiers
            interface_query = self.language.query("(delegation_specifier (user_type (type_identifier) @interface))")
            interface_captures = interface_query.captures(entity.node)
            if 'interface' in interface_captures:
                for interface in interface_captures['interface']:
                    entity.add_symbol("implement_interface", interface)
                    
        elif entity.node.type == 'function_declaration':
            # Find function calls
            query = self.language.query("(call_expression) @reference.call")
            captures = query.captures(entity.node)
            if 'reference.call' in captures:
                for caller in captures['reference.call']:
                    entity.add_symbol("call", caller)
            
            # Find parameters with types
            param_query = self.language.query("(parameter type: (user_type (type_identifier) @parameter))")
            param_captures = param_query.captures(entity.node)
            if 'parameter' in param_captures:
                for parameter in param_captures['parameter']:
                    entity.add_symbol("parameters", parameter)
            
            # Find return type
            return_type_query = self.language.query("(function_declaration type: (user_type (type_identifier) @return_type))")
            return_type_captures = return_type_query.captures(entity.node)
            if 'return_type' in return_type_captures:
                for return_type in return_type_captures['return_type']:
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
                if child.type in ['simple_identifier', 'navigation_expression']:
                    for file, resolved_node in self.resolve(files, lsp, file_path, path, child):
                        method_dec = self.find_parent(resolved_node, ['function_declaration', 'class_declaration', 'object_declaration'])
                        if method_dec and method_dec.type in ['class_declaration', 'object_declaration']:
                            continue
                        if method_dec in file.entities:
                            res.append(file.entities[method_dec])
                    break
        return res
    
    def resolve_symbol(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, key: str, symbol: Node) -> Entity:
        if key in ["implement_interface", "base_class", "parameters", "return_type"]:
            return self.resolve_type(files, lsp, file_path, path, symbol)
        elif key in ["call"]:
            return self.resolve_method(files, lsp, file_path, path, symbol)
        else:
            raise ValueError(f"Unknown key {key}")
