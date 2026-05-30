from pathlib import Path
from typing import Optional

from multilspy import SyncLanguageServer
from ...entities.entity import Entity
from ...entities.file import File
from ..analyzer import AbstractAnalyzer

import tree_sitter_c as tsc
from tree_sitter import Language, Node

import logging
logger = logging.getLogger('code_graph')


class CAnalyzer(AbstractAnalyzer):
    def __init__(self) -> None:
        super().__init__(Language(tsc.language()))

    def add_dependencies(self, path: Path, files: list[Path]):
        pass

    def get_entity_label(self, node: Node) -> str:
        if node.type == 'struct_specifier':
            return "Struct"
        elif node.type == 'function_definition':
            return "Function"
        raise ValueError(f"Unknown entity type: {node.type}")

    def get_entity_name(self, node: Node) -> str:
        if node.type == 'struct_specifier':
            name_node = node.child_by_field_name('name')
            if name_node:
                return name_node.text.decode('utf-8')
            raise ValueError("Struct has no name")
        elif node.type == 'function_definition':
            declarator = node.child_by_field_name('declarator')
            if declarator:
                name_node = declarator.child_by_field_name('declarator')
                if name_node:
                    return name_node.text.decode('utf-8')
            raise ValueError("Function has no name")
        raise ValueError(f"Unknown entity type: {node.type}")

    def get_entity_docstring(self, node: Node) -> Optional[str]:
        if node.type in ['struct_specifier', 'function_definition']:
            if node.prev_sibling and node.prev_sibling.type == 'comment':
                return node.prev_sibling.text.decode('utf-8')
            return None
        raise ValueError(f"Unknown entity type: {node.type}")

    def get_entity_types(self) -> list[str]:
        return ['struct_specifier', 'function_definition']

    def add_symbols(self, entity: Entity) -> None:
        if entity.node.type == 'function_definition':
            # Find function calls
            captures = self._captures("(call_expression function: (identifier) @reference.call)", entity.node)
            if 'reference.call' in captures:
                for caller in captures['reference.call']:
                    entity.add_symbol("call", caller)

            # Find parameters
            captures = self._captures("(parameter_declaration type: (_) @parameter)", entity.node)
            if 'parameter' in captures:
                for parameter in captures['parameter']:
                    entity.add_symbol("parameters", parameter)

            # Return type
            return_type = entity.node.child_by_field_name('type')
            if return_type:
                entity.add_symbol("return_type", return_type)

    def is_dependency(self, file_path: str) -> bool:
        return False

    def resolve_path(self, file_path: str, path: Path) -> str:
        return file_path

    def resolve_type(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, node: Node) -> list[Entity]:
        res = []
        for file, resolved_node in self.resolve(files, lsp, file_path, path, node):
            type_dec = self.find_parent(resolved_node, ['struct_specifier'])
            if type_dec in file.entities:
                res.append(file.entities[type_dec])
        return res

    def resolve_method(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, node: Node) -> list[Entity]:
        res = []
        if node.type == 'call_expression':
            func_node = node.child_by_field_name('function')
            if func_node:
                node = func_node
        for file, resolved_node in self.resolve(files, lsp, file_path, path, node):
            method_dec = self.find_parent(resolved_node, ['function_definition'])
            if method_dec and method_dec in file.entities:
                res.append(file.entities[method_dec])
        return res

    def resolve_symbol(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, key: str, symbol: Node) -> list[Entity]:
        if key in ["parameters", "return_type"]:
            return self.resolve_type(files, lsp, file_path, path, symbol)
        elif key in ["call"]:
            return self.resolve_method(files, lsp, file_path, path, symbol)
        else:
            raise ValueError(f"Unknown key {key}")

    def get_include_paths(self, tree) -> list[str]:
        """Extract #include paths from a parsed C file."""
        includes = []
        captures = self._captures(
            "(preproc_include [(string_literal) (system_lib_string)] @include)",
            tree.root_node
        )
        if 'include' in captures:
            for node in captures['include']:
                path_text = node.text.decode('utf-8').strip('"<>')
                if path_text:
                    includes.append(path_text)
        return includes
