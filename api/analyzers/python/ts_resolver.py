"""Tree-sitter-based static symbol resolver for Python.

A drop-in replacement for the jedi/multilspy round-trip used by
``PythonAnalyzer.resolve``. Builds a project-wide symbol table from the
already-parsed tree-sitter trees and answers ``request_definition``-style
queries by static name resolution.

Selected at runtime via ``CODE_GRAPH_PY_RESOLVER=tree_sitter``.

The resolver intentionally returns the same shape ``AbstractAnalyzer.resolve``
returns: a list of ``(File, Node)`` tuples where ``Node`` is the definition's
tree-sitter node in the target file. This keeps the rest of the analyzer
pipeline (``resolve_type`` / ``resolve_method`` walking up to find_parent)
unchanged.

What we resolve (Python-only):

* Module-local names (function / class defined in the same file).
* ``from X import Y`` — resolves ``Y`` to a definition in module ``X``.
* ``from X import Y as Z`` — same, addressed by ``Z``.
* ``import X`` then ``X.Y`` — drills the dotted chain through the import map.
* ``import X as Z`` then ``Z.Y`` — same.
* Cross-project fallback by bare-name lookup (matches the rest of the
  codebase's tolerance for missing types — jedi returns ``None`` here
  ~80% of the time anyway).

What we don't resolve (matches jedi's miss behavior):

* Dynamic dispatch (``getattr``, metaclasses, monkey-patching).
* Type inference beyond direct ``x = Foo()`` assignment.
* Star imports.
* Cross-package imports outside the indexed project tree.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from tree_sitter import Language, Node, QueryCursor

from api.entities.file import File

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Symbol table data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Definition:
    """A name defined somewhere in the project."""

    file_path: Path
    node: Node
    kind: str  # 'class' | 'func' | 'method' | 'var'


@dataclass
class _ModuleIndex:
    """Per-file index of top-level definitions, imports, and class methods."""

    module: str
    file_path: Path
    # Top-level name -> Definition
    top_level: dict[str, _Definition] = field(default_factory=dict)
    # Class name -> { method_name: Definition }
    class_methods: dict[str, dict[str, _Definition]] = field(default_factory=dict)
    # Local name -> dotted target module path
    # ``import os`` -> {'os': 'os'}
    # ``import os.path as op`` -> {'op': 'os.path'}
    # ``from x.y import z`` -> {'z': 'x.y.z'}
    # ``from x.y import z as w`` -> {'w': 'x.y.z'}
    imports: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tree-sitter queries (compiled once per language instance)
# ---------------------------------------------------------------------------


_QUERY_TOP_LEVEL_FUNC = """
(module (function_definition name: (identifier) @name) @def)
(module (decorated_definition
    definition: (function_definition name: (identifier) @name)) @def)
"""

_QUERY_TOP_LEVEL_CLASS = """
(module (class_definition name: (identifier) @name) @def)
(module (decorated_definition
    definition: (class_definition name: (identifier) @name)) @def)
"""

_QUERY_TOP_LEVEL_ASSIGN = """
(module (expression_statement (assignment left: (identifier) @name) @def))
"""

_QUERY_CLASS_METHODS = """
(class_definition
    name: (identifier) @class_name
    body: (block (function_definition name: (identifier) @method_name) @method_def))
(class_definition
    name: (identifier) @class_name
    body: (block (decorated_definition
        definition: (function_definition name: (identifier) @method_name) @method_def)))
"""

# Plain ``import x`` / ``import x.y`` / ``import x as y`` / ``import x.y as z``.
_QUERY_IMPORT = """
(import_statement) @stmt
"""

# ``from x import y`` / ``from x import y as z`` / ``from . import y`` / ``from .x import y``.
_QUERY_IMPORT_FROM = """
(import_from_statement) @stmt
"""


class _Queries:
    """Compiled tree-sitter queries for a given Language."""

    def __init__(self, language: Language) -> None:
        self.top_level_func = language.query(_QUERY_TOP_LEVEL_FUNC)
        self.top_level_class = language.query(_QUERY_TOP_LEVEL_CLASS)
        self.top_level_assign = language.query(_QUERY_TOP_LEVEL_ASSIGN)
        self.class_methods = language.query(_QUERY_CLASS_METHODS)
        self.imports = language.query(_QUERY_IMPORT)
        self.imports_from = language.query(_QUERY_IMPORT_FROM)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _path_to_module(file_path: Path, project_root: Path) -> str:
    """Convert ``project/pkg/sub/mod.py`` to ``pkg.sub.mod``.

    Returns the file path itself (stringified) if it lives outside the
    project root — those files can still hold definitions but their module
    name is informational only.
    """
    try:
        rel = file_path.relative_to(project_root)
    except ValueError:
        return str(file_path)
    parts = list(rel.parts)
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _dotted_name_text(node: Node) -> str:
    """Reconstruct a dotted ``a.b.c`` string from a tree-sitter node."""
    return node.text.decode("utf-8")


def _captures(query, root: Node) -> dict[str, list[Node]]:
    cursor = QueryCursor(query)
    return cursor.captures(root)


# ---------------------------------------------------------------------------
# Public resolver
# ---------------------------------------------------------------------------


class TreeSitterPythonResolver:
    """Project-wide resolver. Build once, query many times.

    The resolver caches the project symbol table keyed on ``id(files)`` —
    when the analyzer passes a fresh ``files`` dict (new index run) we
    rebuild lazily on the next call. This avoids holding a reference to
    the dict across runs.
    """

    def __init__(self, language: Language) -> None:
        self._language = language
        self._queries = _Queries(language)
        self._files_id: Optional[int] = None
        self._files: Optional[dict[Path, File]] = None
        self._project_root: Optional[Path] = None
        # module name -> _ModuleIndex
        self._modules: dict[str, _ModuleIndex] = {}
        # file path -> module name (reverse lookup)
        self._path_to_module: dict[Path, str] = {}
        # name -> [_Definition, ...] (cross-project fallback)
        self._by_name: dict[str, list[_Definition]] = defaultdict(list)

    # -- build ---------------------------------------------------------------

    def _ensure_built(self, files: dict[Path, File], project_root: Path) -> None:
        if self._files_id == id(files) and self._project_root == project_root:
            return
        self._files_id = id(files)
        self._files = files
        self._project_root = project_root
        self._modules.clear()
        self._path_to_module.clear()
        self._by_name.clear()

        for file_path, file in files.items():
            if file_path.suffix != ".py" or file.tree is None:
                continue
            module = _path_to_module(file_path, project_root)
            mi = _ModuleIndex(module=module, file_path=file_path)
            self._modules[module] = mi
            self._path_to_module[file_path] = module
            self._index_file(mi, file.tree.root_node)

    def _index_file(self, mi: _ModuleIndex, root: Node) -> None:
        # Top-level functions
        caps = _captures(self._queries.top_level_func, root)
        names = caps.get("name", [])
        defs = caps.get("def", [])
        for name_node, def_node in zip(names, defs):
            name = name_node.text.decode("utf-8")
            d = _Definition(mi.file_path, _strip_decorator(def_node), "func")
            mi.top_level[name] = d
            self._by_name[name].append(d)

        # Top-level classes
        caps = _captures(self._queries.top_level_class, root)
        names = caps.get("name", [])
        defs = caps.get("def", [])
        for name_node, def_node in zip(names, defs):
            name = name_node.text.decode("utf-8")
            d = _Definition(mi.file_path, _strip_decorator(def_node), "class")
            mi.top_level[name] = d
            self._by_name[name].append(d)

        # Top-level assignments (for class aliases like ``Foo = OtherFoo``)
        caps = _captures(self._queries.top_level_assign, root)
        names = caps.get("name", [])
        defs = caps.get("def", [])
        for name_node, def_node in zip(names, defs):
            name = name_node.text.decode("utf-8")
            if name in mi.top_level:
                continue
            d = _Definition(mi.file_path, def_node, "var")
            mi.top_level[name] = d
            self._by_name[name].append(d)

        # Class methods
        caps = _captures(self._queries.class_methods, root)
        class_names = caps.get("class_name", [])
        method_names = caps.get("method_name", [])
        method_defs = caps.get("method_def", [])
        for cls_node, mname_node, mdef_node in zip(class_names, method_names, method_defs):
            class_name = cls_node.text.decode("utf-8")
            method_name = mname_node.text.decode("utf-8")
            d = _Definition(mi.file_path, _strip_decorator(mdef_node), "method")
            mi.class_methods.setdefault(class_name, {})[method_name] = d
            self._by_name[method_name].append(d)

        # Imports
        self._index_imports(mi, root)

    def _index_imports(self, mi: _ModuleIndex, root: Node) -> None:
        # ``import X`` statements
        for stmt in _captures(self._queries.imports, root).get("stmt", []):
            for child in stmt.named_children:
                if child.type == "dotted_name":
                    name = child.text.decode("utf-8")
                    # ``import pkg.lib`` binds the *top* package name; users
                    # access ``pkg.lib.x`` via the package head. Map the head
                    # to itself so resolution walks pkg → lib → x naturally.
                    head = name.split(".")[0]
                    mi.imports[head] = head
                elif child.type == "aliased_import":
                    dotted = child.child_by_field_name("name")
                    alias = child.child_by_field_name("alias")
                    if dotted and alias:
                        mi.imports[alias.text.decode("utf-8")] = dotted.text.decode("utf-8")

        # ``from X import Y`` statements
        for stmt in _captures(self._queries.imports_from, root).get("stmt", []):
            module_node = stmt.child_by_field_name("module_name")
            if module_node is None:
                continue
            base_module = self._resolve_from_module(module_node, mi.module)
            if base_module is None:
                continue
            # Each import target is a sibling after module_name
            for child in stmt.named_children:
                if child == module_node:
                    continue
                if child.type == "dotted_name":
                    name = child.text.decode("utf-8")
                    short = name.split(".")[-1]
                    mi.imports[short] = f"{base_module}.{name}"
                elif child.type == "aliased_import":
                    dotted = child.child_by_field_name("name")
                    alias = child.child_by_field_name("alias")
                    if dotted and alias:
                        mi.imports[alias.text.decode("utf-8")] = (
                            f"{base_module}.{dotted.text.decode('utf-8')}"
                        )
                # Wildcard: ignored (matches jedi miss)

    def _resolve_from_module(self, module_node: Node, current_module: str) -> Optional[str]:
        """Handle relative imports (``from . import x``) by climbing the package."""
        if module_node.type == "dotted_name":
            return module_node.text.decode("utf-8")
        if module_node.type == "relative_import":
            # Count leading dots; resolve relative to current package.
            text = module_node.text.decode("utf-8")
            dot_count = 0
            for ch in text:
                if ch == ".":
                    dot_count += 1
                else:
                    break
            tail = text[dot_count:]
            base_parts = current_module.split(".")
            # `from . import x` from pkg.a -> base = pkg
            # `from .. import x` from pkg.a -> base = ''
            up = dot_count
            base = base_parts[: max(0, len(base_parts) - up)]
            if tail:
                base.append(tail)
            return ".".join(p for p in base if p) or None
        return None

    # -- query ---------------------------------------------------------------

    def resolve(
        self,
        files: dict[Path, File],
        file_path: Path,
        project_root: Path,
        node: Node,
    ) -> list[tuple[File, Node]]:
        """Resolve ``node`` (an identifier or dotted attribute) to definitions.

        Returns a list of ``(File, def_node)`` tuples matching the shape
        produced by ``AbstractAnalyzer.resolve``.
        """
        self._ensure_built(files, project_root)
        parts = _node_to_dotted_parts(node)
        if not parts:
            return []
        current_module = self._path_to_module.get(file_path)
        candidate_defs = self._lookup(current_module, parts)
        out: list[tuple[File, Node]] = []
        for d in candidate_defs:
            f = files.get(d.file_path)
            if f is None:
                continue
            out.append((f, d.node))
        return out

    def _lookup(self, current_module: Optional[str], parts: list[str]) -> list[_Definition]:
        if not parts:
            return []
        head = parts[0]
        tail = parts[1:]

        # 1. Local module top-level
        if current_module and current_module in self._modules:
            mi = self._modules[current_module]
            if head in mi.top_level:
                return self._walk_tail(mi.top_level[head], tail)
            # 2. Local file's imports
            if head in mi.imports:
                imported = mi.imports[head]
                # Append the dotted tail to the imported prefix and look up
                # the result as a fully-qualified dotted name. This handles
                # both ``from x import y`` (imported='x.y', tail=[])
                # and ``import pkg.lib`` (imported='pkg.lib', tail=['shared']).
                full_dotted = ".".join([imported, *tail]) if tail else imported
                target_def = self._lookup_dotted(full_dotted)
                if target_def is not None:
                    return [target_def]
                # If the imported path itself names a module, allow direct
                # top-level lookup against that module.
                if imported in self._modules and tail:
                    mi2 = self._modules[imported]
                    if tail[0] in mi2.top_level:
                        return self._walk_tail(mi2.top_level[tail[0]], tail[1:])

        # 3. Cross-project bare-name fallback
        if head in self._by_name:
            # If there's a tail, try walking each candidate; otherwise return all hits.
            if not tail:
                return list(self._by_name[head])
            out = []
            for d in self._by_name[head]:
                out.extend(self._walk_tail(d, tail))
            return out

        return []

    def _lookup_dotted(self, dotted: str) -> Optional[_Definition]:
        """Resolve a fully-qualified ``pkg.mod.Name`` to its _Definition."""
        if dotted in self._modules:
            # A bare module — there's no single definition, just a namespace.
            return None
        # Try splitting from the right: longest prefix that's a module, suffix is symbol path.
        parts = dotted.split(".")
        for split in range(len(parts) - 1, 0, -1):
            mod_candidate = ".".join(parts[:split])
            symbol_parts = parts[split:]
            if mod_candidate in self._modules:
                mi = self._modules[mod_candidate]
                if symbol_parts[0] in mi.top_level:
                    return self._walk_tail_single(mi.top_level[symbol_parts[0]], symbol_parts[1:])
        return None

    def _walk_tail(self, start: _Definition, tail: list[str]) -> list[_Definition]:
        """Walk a dotted-attribute tail from a starting definition. Returns list."""
        d = self._walk_tail_single(start, tail)
        return [d] if d is not None else []

    def _walk_tail_single(self, start: _Definition, tail: list[str]) -> Optional[_Definition]:
        cur = start
        for part in tail:
            if cur.kind == "class":
                class_name = self._class_name_for_def(cur)
                if class_name is None:
                    return None
                mi = self._modules.get(self._path_to_module.get(cur.file_path, ""))
                if mi is None:
                    return None
                methods = mi.class_methods.get(class_name, {})
                if part in methods:
                    cur = methods[part]
                    continue
                return None
            # Other kinds: can't drill further statically
            return None
        return cur

    @staticmethod
    def _class_name_for_def(d: _Definition) -> Optional[str]:
        if d.kind != "class":
            return None
        name_node = d.node.child_by_field_name("name")
        if name_node is None:
            # decorated_definition: drill in
            for child in d.node.named_children:
                if child.type == "class_definition":
                    name_node = child.child_by_field_name("name")
                    break
        return name_node.text.decode("utf-8") if name_node else None


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _strip_decorator(def_node: Node) -> Node:
    """If ``def_node`` is a decorated_definition, return its inner definition.

    The rest of the analyzer expects ``class_definition`` / ``function_definition``
    nodes (those are what ``add_symbols`` traverses and what ``find_parent``
    looks for), so we unwrap decorators here.
    """
    if def_node.type == "decorated_definition":
        for child in def_node.named_children:
            if child.type in ("class_definition", "function_definition"):
                return child
    return def_node


def _node_to_dotted_parts(node: Node) -> list[str]:
    """Reduce a tree-sitter Python expression to its dotted name parts.

    Returns ``[]`` if the node isn't a name reference we can statically resolve.
    """
    if node.type == "identifier":
        return [node.text.decode("utf-8")]
    if node.type == "attribute":
        obj = node.child_by_field_name("object")
        attr = node.child_by_field_name("attribute")
        if obj is None or attr is None:
            return []
        head_parts = _node_to_dotted_parts(obj)
        if not head_parts:
            return []
        return head_parts + [attr.text.decode("utf-8")]
    if node.type == "call":
        func = node.child_by_field_name("function")
        return _node_to_dotted_parts(func) if func else []
    if node.type in ("subscript", "generic_type"):
        # ``Optional[Node]`` / ``dict[Path, File]`` — resolve the outer name.
        # tree-sitter-python uses ``generic_type`` for type annotations and
        # ``subscript`` for runtime indexing expressions.
        if node.type == "subscript":
            inner = node.child_by_field_name("value")
        else:
            inner = node.named_children[0] if node.named_children else None
        return _node_to_dotted_parts(inner) if inner else []
    if node.type == "type":
        # ``type`` wraps the actual annotation expression.
        inner = node.named_children[0] if node.named_children else None
        return _node_to_dotted_parts(inner) if inner else []
    return []
