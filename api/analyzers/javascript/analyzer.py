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
    def __init__(self) -> None:
        super().__init__(Language(tsjs.language()))

    def add_dependencies(self, path: Path, files: list[Path]):
        pass

    def get_entity_label(self, node: Node) -> str:
        if node.type == 'function_declaration':
            return "Function"
        elif node.type == 'class_declaration':
            return "Class"
        elif node.type == 'method_definition':
            return "Method"
        raise ValueError(f"Unknown entity type: {node.type}")

    def get_entity_name(self, node: Node) -> str:
        if node.type in ['function_declaration', 'class_declaration', 'method_definition']:
            name_node = node.child_by_field_name('name')
            if name_node is None:
                return ''
            return name_node.text.decode('utf-8')
        raise ValueError(f"Unknown entity type: {node.type}")

    def get_entity_docstring(self, node: Node) -> Optional[str]:
        if node.type in ['function_declaration', 'class_declaration', 'method_definition']:
            if node.prev_sibling and node.prev_sibling.type == 'comment':
                return node.prev_sibling.text.decode('utf-8')
            return None
        raise ValueError(f"Unknown entity type: {node.type}")

    def get_entity_types(self) -> list[str]:
        return ['function_declaration', 'class_declaration', 'method_definition']

    def add_symbols(self, entity: Entity) -> None:
        if entity.node.type == 'class_declaration':
            heritage = entity.node.child_by_field_name('body')
            if heritage is None:
                return
            superclass_node = entity.node.child_by_field_name('name')
            # Check for `extends` clause via class_heritage
            for child in entity.node.children:
                if child.type == 'class_heritage':
                    for heritage_child in child.children:
                        if heritage_child.type == 'identifier':
                            entity.add_symbol("base_class", heritage_child)
        elif entity.node.type in ['function_declaration', 'method_definition']:
            query = self.language.query("(call_expression) @reference.call")
            captures = query.captures(entity.node)
            if 'reference.call' in captures:
                for caller in captures['reference.call']:
                    entity.add_symbol("call", caller)
            query = self.language.query("(formal_parameters (identifier) @parameter)")
            captures = query.captures(entity.node)
            if 'parameter' in captures:
                for parameter in captures['parameter']:
                    entity.add_symbol("parameters", parameter)

    def is_dependency(self, file_path: str) -> bool:
        return "node_modules" in file_path

    def resolve_path(self, file_path: str, path: Path) -> str:
        return file_path

    def resolve_type(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, node: Node) -> list[Entity]:
        res = []
        for file, resolved_node in self.resolve(files, lsp, file_path, path, node):
            type_dec = self.find_parent(resolved_node, ['class_declaration'])
            if type_dec in file.entities:
                res.append(file.entities[type_dec])
        return res

    def resolve_method(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, node: Node) -> list[Entity]:
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

    def resolve_symbol(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, key: str, symbol: Node) -> list[Entity]:
        if key in ["base_class", "parameters"]:
            return self.resolve_type(files, lsp, file_path, path, symbol)
        elif key in ["call"]:
            return self.resolve_method(files, lsp, file_path, path, symbol)
        else:
            raise ValueError(f"Unknown key {key}")
