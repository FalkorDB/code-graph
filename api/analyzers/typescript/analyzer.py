import shutil
import subprocess
from pathlib import Path

from multilspy import SyncLanguageServer
from ...entities import *
from typing import Optional
from ..analyzer import AbstractAnalyzer

import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Node

import logging
logger = logging.getLogger('code_graph')

class TypeScriptAnalyzer(AbstractAnalyzer):
    def __init__(self) -> None:
        super().__init__(Language(tstypescript.language_typescript()))

    def add_dependencies(self, path: Path, _files: list[Path]):
        if Path(f"{path}/node_modules").is_dir():
            return
        if Path(f"{path}/package.json").is_file():
            npm_path = shutil.which("npm")
            if npm_path is None:
                logger.warning("npm not found on PATH, skipping dependency install")
                return
            try:
                subprocess.run(
                    [npm_path, "install", "--ignore-scripts"],
                    cwd=str(path),
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError as e:
                logger.warning(f"npm install failed: {e}")

    def get_entity_label(self, node: Node) -> str:
        if node.type == 'class_declaration':
            return "Class"
        elif node.type == 'interface_declaration':
            return "Interface"
        elif node.type == 'function_declaration':
            return "Function"
        elif node.type == 'method_definition':
            return "Method"
        raise ValueError(f"Unknown entity type: {node.type}")

    def get_entity_name(self, node: Node) -> str:
        if node.type in ['class_declaration', 'interface_declaration', 'function_declaration', 'method_definition']:
            name_node = node.child_by_field_name('name')
            if name_node:
                return name_node.text.decode('utf-8')
            return ''
        raise ValueError(f"Unknown entity type: {node.type}")

    def get_entity_docstring(self, node: Node) -> Optional[str]:
        if node.type in ['class_declaration', 'interface_declaration', 'function_declaration', 'method_definition']:
            sibling = node.prev_sibling
            if sibling and sibling.type == 'comment':
                return sibling.text.decode('utf-8')
            return None
        raise ValueError(f"Unknown entity type: {node.type}")

    def get_entity_types(self) -> list[str]:
        return ['class_declaration', 'interface_declaration', 'function_declaration', 'method_definition']

    def add_symbols(self, entity: Entity) -> None:
        if entity.node.type == 'class_declaration':
            heritage = self._captures("(class_heritage (extends_clause value: (_) @base_class))", entity.node)
            if 'base_class' in heritage:
                for base in heritage['base_class']:
                    entity.add_symbol("base_class", base)
            implements = self._captures("(implements_clause (type_identifier) @interface)", entity.node)
            if 'interface' in implements:
                for iface in implements['interface']:
                    entity.add_symbol("implement_interface", iface)
        elif entity.node.type == 'interface_declaration':
            extends = self._captures("(extends_type_clause (_) @type)", entity.node)
            if 'type' in extends:
                for t in extends['type']:
                    entity.add_symbol("extend_interface", t)
        elif entity.node.type in ['function_declaration', 'method_definition']:
            captures = self._captures("(call_expression) @reference.call", entity.node)
            if 'reference.call' in captures:
                for caller in captures['reference.call']:
                    entity.add_symbol("call", caller)
            params = self._captures("(formal_parameters (required_parameter type: (_) @parameter))", entity.node)
            if 'parameter' in params:
                for param in params['parameter']:
                    entity.add_symbol("parameters", param)
            return_type = entity.node.child_by_field_name('return_type')
            if return_type:
                entity.add_symbol("return_type", return_type)

    def is_dependency(self, file_path: str) -> bool:
        return "node_modules" in file_path

    def resolve_path(self, file_path: str, path: Path) -> str:
        return file_path

    def resolve_type(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, node: Node) -> list[Entity]:
        res = []
        for file, resolved_node in self.resolve(files, lsp, file_path, path, node):
            type_dec = self.find_parent(resolved_node, ['class_declaration', 'interface_declaration'])
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
            method_dec = self.find_parent(resolved_node, ['function_declaration', 'method_definition', 'class_declaration', 'interface_declaration'])
            if method_dec and method_dec.type in ['class_declaration', 'interface_declaration']:
                continue
            if method_dec in file.entities:
                res.append(file.entities[method_dec])
        return res

    def resolve_symbol(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, key: str, symbol: Node) -> list[Entity]:
        if key in ["implement_interface", "base_class", "extend_interface", "parameters", "return_type"]:
            return self.resolve_type(files, lsp, file_path, path, symbol)
        elif key in ["call"]:
            return self.resolve_method(files, lsp, file_path, path, symbol)
        else:
            raise ValueError(f"Unknown key {key}")
