import os
import subprocess
from pathlib import Path

import tomllib
from typing import Optional

from ...entities.entity import Entity
from ..tree_sitter_base import TreeSitterAnalyzer

import tree_sitter_python as tspython
from tree_sitter import Language, Node

import logging
logger = logging.getLogger('code_graph')

class PythonAnalyzer(TreeSitterAnalyzer):
    entity_node_types = {
        'class_definition': "Class",
        'function_definition': "Function",
    }
    type_definition_node_types = ('class_definition',)
    callable_definition_node_types = ('function_definition', 'class_definition')
    type_resolution_keys = ("base_class", "parameters", "return_type")
    method_resolution_keys = ("call",)

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

    def _extract_type_target(self, node: Node) -> Optional[Node]:
        if node.type == 'attribute':
            return node.child_by_field_name('attribute')
        return node

    def _extract_call_target(self, node: Node) -> Optional[Node]:
        if node.type == 'call':
            node = node.child_by_field_name('function')
            if node and node.type == 'attribute':
                node = node.child_by_field_name('attribute')
        return node
