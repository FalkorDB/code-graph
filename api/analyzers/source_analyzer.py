from contextlib import nullcontext
from pathlib import Path
from typing import Optional

from api.entities.entity import Entity
from api.entities.file import File

from ..graph import Graph
from .analyzer import AbstractAnalyzer
# from .c.analyzer import CAnalyzer
from .csharp.analyzer import CSharpAnalyzer
from .java.analyzer import JavaAnalyzer
from .javascript.analyzer import JavaScriptAnalyzer
from .kotlin.analyzer import KotlinAnalyzer
from .python.analyzer import PythonAnalyzer

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger

import logging
import sys
# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(filename)s - %(asctime)s - %(levelname)s - %(message)s')

# List of available analyzers
analyzers: dict[str, AbstractAnalyzer] = {
    # '.c': CAnalyzer(),
    # '.h': CAnalyzer(),
    '.py': PythonAnalyzer(),
    '.java': JavaAnalyzer(),
    '.cs': CSharpAnalyzer(),
    '.js': JavaScriptAnalyzer(),
    '.kt': KotlinAnalyzer(),
    '.kts': KotlinAnalyzer()}

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
        Resolve symbol references across the codebase via LSP and write the
        resulting edges (CALLS / EXTENDS / IMPLEMENTS / RETURNS / PARAMETERS)
        into the graph.

        Symbol resolution dominates index wall-time on large repos: every
        file's entities trigger several `lsp.request_definition` calls and
        most of them are I/O-bound waiting on the language server.
        multilspy's SyncLanguageServer schedules each request onto a single
        asyncio loop running in a daemon thread (via
        `asyncio.run_coroutine_threadsafe`), which makes concurrent calls
        from multiple worker threads safe and lets us pipeline them.

        We therefore split second_pass into two phases:

          A. Parallel resolution. A bounded thread pool processes files in
             parallel, calling `entity.resolved_symbol(...)` per entity so
             each `Symbol.resolved_symbol` set gets populated. No graph
             writes happen here.

          B. Serial edge writes. The main thread iterates the same files
             in their original order and emits the EXTENDS / CALLS / ...
             edges. Keeping graph writes on one thread avoids contending on
             FalkorDB MERGE locks and produces a deterministic edge order
             matching the pre-parallel implementation.

        Pool size is controlled by `CODE_GRAPH_INDEX_WORKERS` (default 4),
        so resolution runs in parallel by default. This is an intentional
        behaviour change, but the edge output is identical to the
        single-worker path (verified on a 204-file repo): phase B always
        writes in the original file order regardless of how phase A
        interleaves. Set the var to 1 to run a single resolver thread (useful
        when multilspy/jedi misbehaves under concurrency); note this still
        dispatches through the pool rather than the main thread.

        Files whose resolution raises are logged with their traceback and
        excluded from phase B, so one bad file degrades to a logged skip
        instead of a partial or aborted graph -- and that behaviour no longer
        depends on the worker count.
        """
        import os
        from concurrent.futures import ThreadPoolExecutor, as_completed

        logger = MultilspyLogger()
        logger.logger.setLevel(logging.ERROR)
        lsps = {}
        if any(path.rglob('*.java')):
            config = MultilspyConfig.from_dict({"code_language": "java"})
            lsps[".java"] = SyncLanguageServer.create(config, logger, str(path))
        else:
            lsps[".java"] = NullLanguageServer()
        if any(path.rglob('*.py')):
            py_venv = path / "venv"
            py_dotvenv = path / ".venv"
            if py_venv.is_dir() and (py_venv / "bin" / "python").exists():
                env_path = str(py_venv)
            elif py_dotvenv.is_dir() and (py_dotvenv / "bin" / "python").exists():
                env_path = str(py_dotvenv)
            else:
                # Fall back to the host's Python environment so jedi has a
                # valid interpreter to introspect; otherwise every
                # request_definition() raises InvalidPythonEnvironment and
                # we'd silently produce a graph with zero CALLS edges.
                # sys.prefix is the active environment root and is more
                # reliable than deriving it from sys.executable (which breaks
                # when the interpreter is a wrapper/shim).
                env_path = sys.prefix
                logging.info(
                    "No venv at %s; falling back to host env %s for jedi LSP",
                    path, env_path,
                )
            config = MultilspyConfig.from_dict({
                "code_language": "python",
                "environment_path": env_path,
            })
            lsps[".py"] = SyncLanguageServer.create(config, logger, str(path))
        else:
            lsps[".py"] = NullLanguageServer()
        if any(path.rglob('*.cs')):
            config = MultilspyConfig.from_dict({"code_language": "csharp"})
            lsps[".cs"] = SyncLanguageServer.create(config, logger, str(path))
        else:
            lsps[".cs"] = NullLanguageServer()
        # For now, use NullLanguageServer for Kotlin as kotlin-language-server setup is not yet integrated
        lsps[".kt"] = NullLanguageServer()
        lsps[".kts"] = NullLanguageServer()
        lsps[".js"] = NullLanguageServer()
        with lsps[".java"].start_server(), lsps[".py"].start_server(), lsps[".cs"].start_server(), lsps[".js"].start_server(), lsps[".kt"].start_server(), lsps[".kts"].start_server():
            try:
                n_workers = max(1, int(os.environ.get("CODE_GRAPH_INDEX_WORKERS", "4")))
            except ValueError:
                n_workers = 4

            # Drop files we don't actually have an entry for and skip files
            # whose language has no real LSP (NullLanguageServer provides
            # no symbol info, so resolution would be a no-op). De-duplicate
            # while preserving order so a path that appears twice in `files`
            # isn't resolved concurrently by two workers racing on the same
            # entity.resolved_symbols sets.
            resolvable: list[Path] = []
            seen: set[Path] = set()
            for file_path in files:
                if file_path in seen:
                    continue
                seen.add(file_path)
                if file_path not in self.files:
                    # first_pass skipped this file (e.g. parse error, empty,
                    # untracked, or ignored after entering the candidate list).
                    # Skip in second_pass too instead of crashing the whole
                    # index.
                    logging.warning(
                        "second_pass: %s not in files map (first_pass skipped it); skipping",
                        file_path,
                    )
                    continue
                if isinstance(lsps.get(file_path.suffix), NullLanguageServer):
                    continue
                resolvable.append(file_path)

            total = len(resolvable)
            logging.info(
                "second_pass: resolving symbols in %d files with %d worker(s)",
                total, n_workers,
            )

            def _resolve_file(file_path: Path) -> Path:
                # Populate Symbol.resolved_symbol sets for every entity in
                # this file. Pure LSP work, safe to run from worker threads
                # because SyncLanguageServer multiplexes requests through a
                # single asyncio loop.
                file = self.files[file_path]
                for _, entity in file.entities.items():
                    entity.resolved_symbol(
                        lambda key, symbol, fp=file_path: analyzers[fp.suffix].resolve_symbol(
                            self.files, lsps[fp.suffix], fp, path, key, symbol
                        )
                    )
                return file_path

            # Phase A: resolve symbols. A single code path for every worker
            # count keeps the failure policy identical regardless of
            # CODE_GRAPH_INDEX_WORKERS -- a ThreadPoolExecutor with
            # max_workers=1 simply processes one file at a time.
            failed: set[Path] = set()
            done = 0
            log_every = max(1, total // 50) if total else 1
            with ThreadPoolExecutor(max_workers=n_workers, thread_name_prefix="sa-resolve") as ex:
                futures = {ex.submit(_resolve_file, fp): fp for fp in resolvable}
                for fut in as_completed(futures):
                    fp = futures[fut]
                    try:
                        fut.result()
                    except Exception:
                        # Exclude this file from phase B so we never persist a
                        # partially resolved file; keep going so one bad file
                        # doesn't abort the whole index.
                        failed.add(fp)
                        logging.warning(
                            "second_pass: resolution failed for %s; excluding from edge writes",
                            fp, exc_info=True,
                        )
                    done += 1
                    if done % log_every == 0 or done == total:
                        logging.info("second_pass: resolved %d/%d files", done, total)

            # Phase B: serial edge writes, in the original file order so
            # the graph is bit-identical to the single-threaded path. Files
            # whose resolution failed are skipped (see phase A).
            for file_path in resolvable:
                if file_path in failed:
                    continue
                file = self.files[file_path]
                for _, entity in file.entities.items():
                    for key, resolved_set in entity.resolved_symbols.items():
                        for resolved in resolved_set:
                            if key == "base_class":
                                graph.connect_entities("EXTENDS", entity.id, resolved.id)
                            elif key == "implement_interface":
                                graph.connect_entities("IMPLEMENTS", entity.id, resolved.id)
                            elif key == "extend_interface":
                                graph.connect_entities("EXTENDS", entity.id, resolved.id)
                            elif key == "call":
                                graph.connect_entities("CALLS", entity.id, resolved.id)
                            elif key == "return_type":
                                graph.connect_entities("RETURNS", entity.id, resolved.id)
                            elif key == "parameters":
                                graph.connect_entities("PARAMETERS", entity.id, resolved.id)

    def analyze_files(self, files: list[Path], path: Path, graph: Graph) -> None:
        self.first_pass(path, files, [], graph)
        self.second_pass(graph, files, path)

    def analyze_sources(self, path: Path, ignore: list[str], graph: Graph) -> None:
        path = path.resolve()
        files = list(path.rglob("*.java")) + list(path.rglob("*.py")) + list(path.rglob("*.cs")) + [f for f in path.rglob("*.js") if "node_modules" not in f.parts] + list(path.rglob("*.kt")) + list(path.rglob("*.kts"))
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

    def analyze_local_repository(self, path: str, ignore: Optional[list[str]] = None, branch: Optional[str] = None) -> Graph:
        """
        Analyze a local Git repository.

        Args:
            path (str): Path to a local git repository
            ignore (List(str)): List of paths to skip
            branch (Optional[str]): Branch name. Auto-detected from the
                checkout when ``None``.
        """
        if ignore is None:
            ignore = []

        from pygit2.repository import Repository
        from ..project import detect_branch

        proj_name = Path(path).name
        if branch is None:
            branch = detect_branch(Path(path))
        graph = Graph(proj_name, branch=branch)
        self.analyze_local_folder(path, graph, ignore)

        # Save processed commit hash to the DB
        repo = Repository(path)
        current_commit = repo.walk(repo.head.target).__next__()
        graph.set_graph_commit(current_commit.short_id)

        return graph

