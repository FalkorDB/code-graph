import subprocess
from pathlib import Path

from multilspy import SyncLanguageServer
from ...entities.entity import Entity
from ...entities.file import File
from typing import Optional
from ..analyzer import AbstractAnalyzer

import tree_sitter_c_sharp as tscsharp
from tree_sitter import Language, Node, QueryCursor

import logging
logger = logging.getLogger('code_graph')

class CSharpAnalyzer(AbstractAnalyzer):
    def __init__(self) -> None:
        super().__init__(Language(tscsharp.language()))

    def _captures(self, pattern: str, node: Node) -> dict:
        """Run a tree-sitter query and return captures dict."""
        query = self.language.query(pattern)
        cursor = QueryCursor(query)
        return cursor.captures(node)

    def add_dependencies(self, path: Path, files: list[Path]):
        if Path(f"{path}/temp_deps_cs").is_dir():
            return
        if any(Path(f"{path}").glob("*.csproj")) or any(Path(f"{path}").glob("*.sln")):
            subprocess.run(["dotnet", "restore"], cwd=str(path))

    def get_entity_label(self, node: Node) -> str:
        if node.type == 'class_declaration':
            return "Class"
        elif node.type == 'interface_declaration':
            return "Interface"
        elif node.type == 'enum_declaration':
            return "Enum"
        elif node.type == 'struct_declaration':
            return "Struct"
        elif node.type == 'method_declaration':
            return "Method"
        elif node.type == 'constructor_declaration':
            return "Constructor"
        raise ValueError(f"Unknown entity type: {node.type}")

    def get_entity_name(self, node: Node) -> str:
        if node.type in ['class_declaration', 'interface_declaration', 'enum_declaration',
                         'struct_declaration', 'method_declaration', 'constructor_declaration']:
            name_node = node.child_by_field_name('name')
            if name_node is None:
                return ''
            return name_node.text.decode('utf-8')
        raise ValueError(f"Unknown entity type: {node.type}")

    def get_entity_docstring(self, node: Node) -> Optional[str]:
        if node.type in ['class_declaration', 'interface_declaration', 'enum_declaration',
                         'struct_declaration', 'method_declaration', 'constructor_declaration']:
            # Walk back through contiguous comment siblings to collect
            # multi-line XML doc comments (each /// line is a separate node)
            lines = []
            sibling = node.prev_sibling
            while sibling and sibling.type == "comment":
                lines.insert(0, sibling.text.decode('utf-8'))
                sibling = sibling.prev_sibling
            return '\n'.join(lines) if lines else None
        raise ValueError(f"Unknown entity type: {node.type}")

    def get_entity_types(self) -> list[str]:
        return ['class_declaration', 'interface_declaration', 'enum_declaration',
                'struct_declaration', 'method_declaration', 'constructor_declaration']

    def add_symbols(self, entity: Entity) -> None:
        if entity.node.type in ['class_declaration', 'struct_declaration']:
            base_list_captures = self._captures("(base_list (_) @base_type)", entity.node)
            if 'base_type' in base_list_captures:
                first = True
                for base_type in base_list_captures['base_type']:
                    if first and entity.node.type == 'class_declaration':
                        # NOTE: Without semantic analysis, we cannot distinguish a base
                        # class from an interface in C# base_list. By convention, the
                        # base class is listed first; if a class only implements
                        # interfaces, this will produce a spurious base_class edge that
                        # the LSP resolution in second_pass can correct.
                        entity.add_symbol("base_class", base_type)
                        first = False
                    else:
                        entity.add_symbol("implement_interface", base_type)
        elif entity.node.type == 'interface_declaration':
            base_list_captures = self._captures("(base_list (_) @base_type)", entity.node)
            if 'base_type' in base_list_captures:
                for base_type in base_list_captures['base_type']:
                    entity.add_symbol("extend_interface", base_type)
        elif entity.node.type in ['method_declaration', 'constructor_declaration']:
            captures = self._captures("(invocation_expression) @reference.call", entity.node)
            if 'reference.call' in captures:
                for caller in captures['reference.call']:
                    entity.add_symbol("call", caller)
            captures = self._captures("(parameter_list (parameter type: (_) @parameter))", entity.node)
            if 'parameter' in captures:
                for parameter in captures['parameter']:
                    entity.add_symbol("parameters", parameter)
            if entity.node.type == 'method_declaration':
                return_type = entity.node.child_by_field_name('type')
                if return_type:
                    entity.add_symbol("return_type", return_type)

    def is_dependency(self, file_path: str) -> bool:
        return "temp_deps_cs" in file_path

    def resolve_path(self, file_path: str, path: Path) -> str:
        return file_path

    def resolve_type(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, node: Node) -> list[Entity]:
        res = []
        for file, resolved_node in self.resolve(files, lsp, file_path, path, node):
            type_dec = self.find_parent(resolved_node, ['class_declaration', 'interface_declaration', 'enum_declaration', 'struct_declaration'])
            if type_dec in file.entities:
                res.append(file.entities[type_dec])
        return res

    def resolve_method(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, node: Node) -> list[Entity]:
        res = []
        if node.type == 'invocation_expression':
            func_node = node.child_by_field_name('function')
            if func_node and func_node.type == 'member_access_expression':
                func_node = func_node.child_by_field_name('name')
            if func_node:
                node = func_node
        for file, resolved_node in self.resolve(files, lsp, file_path, path, node):
            method_dec = self.find_parent(resolved_node, ['method_declaration', 'constructor_declaration', 'class_declaration', 'interface_declaration', 'enum_declaration', 'struct_declaration'])
            if method_dec and method_dec.type in ['class_declaration', 'interface_declaration', 'enum_declaration', 'struct_declaration']:
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
