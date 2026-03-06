from contextlib import nullcontext
from pathlib import Path
from typing import Optional

from api.entities.entity import Entity
from api.entities.file import File

from ..graph import Graph
from .analyzer import AbstractAnalyzer
# from .c.analyzer import CAnalyzer
from .java.analyzer import JavaAnalyzer
from .python.analyzer import PythonAnalyzer
from .csharp.analyzer import CSharpAnalyzer

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger

import logging
# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(filename)s - %(asctime)s - %(levelname)s - %(message)s')

# List of available analyzers
analyzers: dict[str, AbstractAnalyzer] = {
    # '.c': CAnalyzer(),
    # '.h': CAnalyzer(),
    '.py': PythonAnalyzer(),
    '.java': JavaAnalyzer(),
    '.cs': CSharpAnalyzer()}

class NullLanguageServer:
    def start_server(self):
        return nullcontext()

class SourceAnalyzer():
    def __init__(self) -> None:
        self.files: dict[Path, File] = {}

    def supported_types(self) -> list[str]:
        """
        """
        return list(analyzers.keys())

    def create_entity_hierarchy(self, entity: Entity, file: File, analyzer: AbstractAnalyzer, graph: Graph):
        types = analyzer.get_entity_types()
        stack = list(entity.node.children)
        while stack:
            node = stack.pop()
            if node.type in types:
                child = Entity(node)
                child.id = graph.add_entity(analyzer.get_entity_label(node), analyzer.get_entity_name(node), analyzer.get_entity_docstring(node), str(file.path), node.start_point.row, node.end_point.row, {})
                if not analyzer.is_dependency(str(file.path)):
                    analyzer.add_symbols(child)
                file.add_entity(child)
                entity.add_child(child)
                graph.connect_entities("DEFINES", entity.id, child.id)
                self.create_entity_hierarchy(child, file, analyzer, graph)
            else:
                stack.extend(node.children)

    def create_hierarchy(self, file: File, analyzer: AbstractAnalyzer, graph: Graph):
        types = analyzer.get_entity_types()
        stack = [file.tree.root_node]
        while stack:
            node = stack.pop()
            if node.type in types:
                entity = Entity(node)
                entity.id = graph.add_entity(analyzer.get_entity_label(node), analyzer.get_entity_name(node), analyzer.get_entity_docstring(node), str(file.path), node.start_point.row, node.end_point.row, {})
                if not analyzer.is_dependency(str(file.path)):
                    analyzer.add_symbols(entity)
                file.add_entity(entity)
                graph.connect_entities("DEFINES", file.id, entity.id)
                self.create_entity_hierarchy(entity, file, analyzer, graph)
            else:
                stack.extend(node.children)

    def first_pass(self, path: Path, files: list[Path], ignore: list[str], graph: Graph) -> None:
        """
        Perform the first pass analysis on source files in the given directory tree.

        Args:
            ignore (list(str)): List of paths to ignore
            executor (concurrent.futures.Executor): The executor to run tasks concurrently.
        """

        supoorted_types = self.supported_types()
        for ext in set([file.suffix for file in files if file.suffix in supoorted_types]):
            analyzers[ext].add_dependencies(path, files)
        
        files_len = len(files)
        for i, file_path in enumerate(files):
            # Skip none supported files
            if file_path.suffix not in analyzers:
                logging.info(f"Skipping none supported file {file_path}")
                continue

            # Skip ignored files
            if any([i in str(file_path) for i in ignore]):
                logging.info(f"Skipping ignored file {file_path}")
                continue

            logging.info(f'Processing file ({i + 1}/{files_len}): {file_path}')

            analyzer = analyzers[file_path.suffix]

            # Parse file
            source_code = file_path.read_bytes()
            tree = analyzer.parser.parse(source_code)

            # Create file entity
            file = File(file_path, tree)
            self.files[file_path] = file

            # Walk thought the AST
            graph.add_file(file)
            self.create_hierarchy(file, analyzer, graph)

    def second_pass(self, graph: Graph, files: list[Path], path: Path) -> None:
        """
        Recursively analyze the contents of a directory.

        Args:
            base (str): The base directory for analysis.
            root (str): The current directory being analyzed.
            executor (concurrent.futures.Executor): The executor to run tasks concurrently.
        """

        logger = MultilspyLogger()
        logger.logger.setLevel(logging.ERROR)
        lsps = {}
        if any(path.rglob('*.java')):
            config = MultilspyConfig.from_dict({"code_language": "java"})
            lsps[".java"] = SyncLanguageServer.create(config, logger, str(path))
        else:
            lsps[".java"] = NullLanguageServer()
        if any(path.rglob('*.py')):
            config = MultilspyConfig.from_dict({"code_language": "python", "environment_path": f"{path}/venv"})
            lsps[".py"] = SyncLanguageServer.create(config, logger, str(path))
        else:
            lsps[".py"] = NullLanguageServer()
        if any(path.rglob('*.cs')):
            config = MultilspyConfig.from_dict({"code_language": "csharp"})
            lsps[".cs"] = SyncLanguageServer.create(config, logger, str(path))
        else:
            lsps[".cs"] = NullLanguageServer()
        with lsps[".java"].start_server(), lsps[".py"].start_server(), lsps[".cs"].start_server():
            files_len = len(self.files)
            for i, file_path in enumerate(files):
                file = self.files[file_path]
                logging.info(f'Processing file ({i + 1}/{files_len}): {file_path}')
                for _, entity in file.entities.items():
                    entity.resolved_symbol(lambda key, symbol: analyzers[file_path.suffix].resolve_symbol(self.files, lsps[file_path.suffix], file_path, path, key, symbol))
                    for key, symbols in entity.symbols.items():
                        for symbol in symbols:
                            if len(symbol.resolved_symbol) == 0:
                                continue
                            resolved_symbol = next(iter(symbol.resolved_symbol))
                            if key == "base_class":
                                graph.connect_entities("EXTENDS", entity.id, resolved_symbol.id)
                            elif key == "implement_interface":
                                graph.connect_entities("IMPLEMENTS", entity.id, resolved_symbol.id)
                            elif key == "extend_interface":
                                graph.connect_entities("EXTENDS", entity.id, resolved_symbol.id)
                            elif key == "call":
                                graph.connect_entities("CALLS", entity.id, resolved_symbol.id, {"line": symbol.symbol.start_point.row, "text": symbol.symbol.text.decode("utf-8")})
                            elif key == "return_type":
                                graph.connect_entities("RETURNS", entity.id, resolved_symbol.id)
                            elif key == "parameters":
                                graph.connect_entities("PARAMETERS", entity.id, resolved_symbol.id)

    def analyze_files(self, files: list[Path], path: Path, graph: Graph) -> None:
        self.first_pass(path, files, [], graph)
        self.second_pass(graph, files, path)

    def analyze_sources(self, path: Path, ignore: list[str], graph: Graph) -> None:
        path = path.resolve()
        files = list(path.rglob("*.java")) + list(path.rglob("*.py")) + list(path.rglob("*.cs"))
        # First pass analysis of the source code
        self.first_pass(path, files, ignore, graph)

        # Second pass analysis of the source code
        self.second_pass(graph, files, path)

    def analyze_local_folder(self, path: str, g: Graph, ignore: Optional[list[str]] = []) -> None:
        """
        Analyze path.

        Args:
            path (str): Path to a local folder containing source files to process
            ignore (List(str)): List of paths to skip
        """

        logging.info(f"Analyzing local folder {path}")

        # Analyze source files
        self.analyze_sources(Path(path), ignore, g)

        logging.info("Done analyzing path")

    def analyze_local_repository(self, path: str, ignore: Optional[list[str]] = None) -> Graph:
        if ignore is None:
            ignore = []
        # ... (rest of the function implementation)
        """
        Analyze a local Git repository.

        Args:
            path (str): Path to a local git repository
            ignore (List(str)): List of paths to skip
        """
        from pygit2.repository import Repository

        self.analyze_local_folder(path, ignore)

        # Save processed commit hash to the DB
        repo = Repository(path)
        head = repo.commit("HEAD")
        self.graph.set_graph_commit(head.short_id)

        return self.graph
    
