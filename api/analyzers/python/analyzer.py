import os
import subprocess
from multilspy import SyncLanguageServer
from pathlib import Path

import tomllib
from ...entities import *
from typing import Optional
from ..analyzer import AbstractAnalyzer

import tree_sitter_python as tspython
from tree_sitter import Language, Node

import logging
logger = logging.getLogger('code_graph')

class PythonAnalyzer(AbstractAnalyzer):
    def __init__(self) -> None:
        super().__init__(Language(tspython.language()))
    
    def add_dependencies(self, path: Path, files: list[Path]):
        if Path(f"{path}/venv").is_dir():
            return
        subprocess.run(["python3", "-m", "venv", "venv"], cwd=str(path))
        if Path(f"{path}/pyproject.toml").is_file():
            subprocess.run(["pip", "install", "poetry"], cwd=str(path), env={"VIRTUAL_ENV": f"{path}/venv", "PATH": f"{path}/venv/bin:{os.environ['PATH']}"})
            subprocess.run(["poetry", "install"], cwd=str(path), env={"VIRTUAL_ENV": f"{path}/venv", "PATH": f"{path}/venv/bin:{os.environ['PATH']}"})
            try:
                with open(f"{path}/pyproject.toml", 'rb') as file:
                    pyproject_data = tomllib.load(file)
                    dependencies = (pyproject_data.get("tool") or {}).get("poetry", {}).get("dependencies", {})
                    for requirement in dependencies:
                        files.extend(Path(f"{path}/venv/lib").rglob(f"**/site-packages/{requirement}/*.py"))
            except Exception as e:
                logger.warning("Failed to parse %s/pyproject.toml: %s", path, e)
        elif Path(f"{path}/requirements.txt").is_file():
            subprocess.run(["pip", "install", "-r", "requirements.txt"], cwd=str(path), env={"VIRTUAL_ENV": f"{path}/venv", "PATH": f"{path}/venv/bin:{os.environ['PATH']}"})
            with open(f"{path}/requirements.txt", 'r') as file:
                requirements = [line.strip().split("==") for line in file if line.strip()]
                for requirement in requirements:
                    files.extend(Path(f"{path}/venv/lib/").rglob(f"**/site-packages/{requirement}/*.py"))

    def get_entity_label(self, node: Node) -> str:
        if node.type == 'class_definition':
            return "Class"
        elif node.type == 'function_definition':
            return "Function"
        raise ValueError(f"Unknown entity type: {node.type}")

    def get_entity_name(self, node: Node) -> str:
        if node.type in ['class_definition', 'function_definition']:
            return node.child_by_field_name('name').text.decode('utf-8')
        raise ValueError(f"Unknown entity type: {node.type}")
    
    def get_entity_docstring(self, node: Node) -> Optional[str]:
        if node.type in ['class_definition', 'function_definition']:
            body = node.child_by_field_name('body')
            if body.child_count > 0 and body.children[0].type == 'expression_statement':
                docstring_node = body.children[0].child(0)
                return docstring_node.text.decode('utf-8')
            return None
        raise ValueError(f"Unknown entity type: {node.type}")        
    
    def get_entity_types(self) -> list[str]:
        return ['class_definition', 'function_definition']
    
    def add_symbols(self, entity: Entity) -> None:
        if entity.node.type == 'class_definition':
            superclasses = entity.node.child_by_field_name("superclasses")
            if superclasses:
                base_classes_captures = self._captures("(argument_list (_) @base_class)", superclasses)
                if 'base_class' in base_classes_captures:
                    for base_class in base_classes_captures['base_class']:
                        entity.add_symbol("base_class", base_class)
        elif entity.node.type == 'function_definition':
            captures = self._captures("(call) @reference.call", entity.node)
            if 'reference.call' in captures:
                for caller in captures['reference.call']:
                    entity.add_symbol("call", caller)
            captures = self._captures("(typed_parameter type: (_) @parameter)", entity.node)
            if 'parameter' in captures:
                for parameter in captures['parameter']:
                    entity.add_symbol("parameters", parameter)
            return_type = entity.node.child_by_field_name('return_type')
            if return_type:
                entity.add_symbol("return_type", return_type)

    def is_dependency(self, file_path: str) -> bool:
        return "venv" in file_path

    def resolve_path(self, file_path: str, path: Path) -> str:
        return file_path

    def resolve_type(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path, node: Node) -> list[Entity]:
        res = []
        if node.type == 'attribute':
            node = node.child_by_field_name('attribute')
        for file, resolved_node in self.resolve(files, lsp, file_path, path, node):
            type_dec = self.find_parent(resolved_node, ['class_definition'])
            if type_dec in file.entities:
                res.append(file.entities[type_dec])
        return res

    def resolve_method(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, node: Node) -> list[Entity]:
        res = []
        if node.type == 'call':
            node = node.child_by_field_name('function')
            if node.type == 'attribute':
                node = node.child_by_field_name('attribute')
        for file, resolved_node in self.resolve(files, lsp, file_path, path, node):
            method_dec = self.find_parent(resolved_node, ['function_definition', 'class_definition'])
            if not method_dec:
                continue
            if method_dec in file.entities:
                res.append(file.entities[method_dec])
        return res
    
    def resolve_symbol(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, key: str, symbol: Node) -> list[Entity]:
        if key in ["base_class", "parameters", "return_type"]:
            return self.resolve_type(files, lsp, file_path, path, symbol)
        elif key in ["call"]:
            return self.resolve_method(files, lsp, file_path, path, symbol)
        else:
            raise ValueError(f"Unknown key {key}")

    def add_file_imports(self, file: File) -> None:
        """
        Extract and add import statements from the file.
        
        Supports:
        - import module
        - import module as alias
        - from module import name
        - from module import name1, name2
        - from module import name as alias
        """
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                # Query for both import types
                import_query = self.language.query("""
                    (import_statement) @import
                    (import_from_statement) @import_from
                """)
            
            captures = import_query.captures(file.tree.root_node)
            
            # Add all import statement nodes to the file
            if 'import' in captures:
                for import_node in captures['import']:
                    file.add_import(import_node)
            
            if 'import_from' in captures:
                for import_node in captures['import_from']:
                    file.add_import(import_node)
        except Exception as e:
            logger.debug(f"Failed to extract imports from {file.path}: {e}")

    def resolve_import(self, files: dict[Path, File], lsp: SyncLanguageServer, file_path: Path, path: Path, import_node: Node) -> list[Entity]:
        """
        Resolve an import statement to the entities it imports.
        """
        res = []
        
        try:
            if import_node.type == 'import_statement':
                # Handle "import module" or "import module as alias"
                # Find all dotted_name and aliased_import nodes
                for child in import_node.children:
                    if child.type == 'dotted_name':
                        # Try to resolve the module/name
                        identifier = child.children[0] if child.child_count > 0 else child
                        resolved = self.resolve_type(files, lsp, file_path, path, identifier)
                        res.extend(resolved)
                    elif child.type == 'aliased_import':
                        # Get the actual name from aliased import (before 'as')
                        if child.child_count > 0:
                            actual_name = child.children[0]
                            if actual_name.type == 'dotted_name' and actual_name.child_count > 0:
                                identifier = actual_name.children[0]
                            else:
                                identifier = actual_name
                            resolved = self.resolve_type(files, lsp, file_path, path, identifier)
                            res.extend(resolved)
            
            elif import_node.type == 'import_from_statement':
                # Handle "from module import name1, name2"
                # Find the 'import' keyword to know where imported names start
                import_keyword_found = False
                for child in import_node.children:
                    if child.type == 'import':
                        import_keyword_found = True
                        continue
                    
                    # After 'import' keyword, dotted_name nodes are the imported names
                    if import_keyword_found and child.type == 'dotted_name':
                        # Try to resolve the imported name
                        identifier = child.children[0] if child.child_count > 0 else child
                        resolved = self.resolve_type(files, lsp, file_path, path, identifier)
                        res.extend(resolved)
                    elif import_keyword_found and child.type == 'aliased_import':
                        # Handle "from module import name as alias"
                        if child.child_count > 0:
                            actual_name = child.children[0]
                            if actual_name.type == 'dotted_name' and actual_name.child_count > 0:
                                identifier = actual_name.children[0]
                            else:
                                identifier = actual_name
                            resolved = self.resolve_type(files, lsp, file_path, path, identifier)
                            res.extend(resolved)
        
        except Exception as e:
            logger.debug(f"Failed to resolve import: {e}")
        
        return res
