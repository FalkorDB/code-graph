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
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from tree_sitter import Language, Node, QueryCursor

from api.entities.file import File

logger = logging.getLogger(__name__)


# Maximum number of same-named method definitions the guarded name-based
# fallback will link a receiver-less ``obj.method()`` call to. Common method
# names (``get`` / ``add`` / ``run`` / ``close`` ...) are defined on dozens of
# classes; binding a call to all of them is a false-CALLS factory, so above this
# count we emit no edge at all.
_NAME_FALLBACK_MAX_CANDIDATES = 5


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


def _matches(query, root: Node) -> list[tuple[int, dict[str, list[Node]]]]:
    """Return per-match capture groups.

    Unlike :func:`_captures` (which groups *all* nodes by capture name into
    parallel lists that are **not** guaranteed to be index-aligned across
    different capture names), this yields one dict per match so that, e.g.,
    a ``@name`` capture is always paired with the ``@def`` capture from the
    *same* match. Zipping the two independent lists from ``captures()`` mis-
    aligns names and definitions whenever the per-capture node orderings
    diverge, scrambling the module symbol table.
    """
    cursor = QueryCursor(query)
    return cursor.matches(root)


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
        # Serializes rebuilds so concurrent index workers (CODE_GRAPH_INDEX_WORKERS>1)
        # can't clear/repopulate the shared tables out from under each other.
        self._build_lock = threading.Lock()

    # -- build ---------------------------------------------------------------

    def _ensure_built(self, files: dict[Path, File], project_root: Path) -> None:
        if self._files_id == id(files) and self._project_root == project_root:
            return
        with self._build_lock:
            # Double-check inside the lock: another worker may have finished
            # building while we waited.
            if self._files_id == id(files) and self._project_root == project_root:
                return

            # Build into fresh local tables and publish them atomically. This
            # keeps a concurrent reader (lock-free fast path above) from ever
            # observing a half-cleared / half-populated table under the #688
            # thread pool.
            modules: dict[str, _ModuleIndex] = {}
            path_to_module: dict[Path, str] = {}
            by_name: dict[str, list[_Definition]] = defaultdict(list)

            for file_path, file in files.items():
                if file_path.suffix != ".py" or file.tree is None:
                    continue
                module = _path_to_module(file_path, project_root)
                mi = _ModuleIndex(module=module, file_path=file_path)
                modules[module] = mi
                path_to_module[file_path] = module
                self._index_file(mi, file.tree.root_node, by_name)

            self._files = files
            self._modules = modules
            self._path_to_module = path_to_module
            self._by_name = by_name
            self._project_root = project_root
            # Publish the cache key LAST so the fast-path guard never matches a
            # table that isn't fully built yet.
            self._files_id = id(files)

    def _index_file(
        self,
        mi: _ModuleIndex,
        root: Node,
        by_name: dict[str, list[_Definition]],
    ) -> None:
        # Top-level functions
        for _, caps in _matches(self._queries.top_level_func, root):
            name_nodes = caps.get("name", [])
            def_nodes = caps.get("def", [])
            if not name_nodes or not def_nodes:
                continue
            name = name_nodes[0].text.decode("utf-8")
            d = _Definition(mi.file_path, _strip_decorator(def_nodes[0]), "func")
            mi.top_level[name] = d
            by_name[name].append(d)

        # Top-level classes
        for _, caps in _matches(self._queries.top_level_class, root):
            name_nodes = caps.get("name", [])
            def_nodes = caps.get("def", [])
            if not name_nodes or not def_nodes:
                continue
            name = name_nodes[0].text.decode("utf-8")
            d = _Definition(mi.file_path, _strip_decorator(def_nodes[0]), "class")
            mi.top_level[name] = d
            by_name[name].append(d)

        # Top-level assignments (for class aliases like ``Foo = OtherFoo``)
        for _, caps in _matches(self._queries.top_level_assign, root):
            name_nodes = caps.get("name", [])
            def_nodes = caps.get("def", [])
            if not name_nodes or not def_nodes:
                continue
            name = name_nodes[0].text.decode("utf-8")
            if name in mi.top_level:
                continue
            d = _Definition(mi.file_path, def_nodes[0], "var")
            mi.top_level[name] = d
            by_name[name].append(d)

        # Class methods
        for _, caps in _matches(self._queries.class_methods, root):
            class_nodes = caps.get("class_name", [])
            mname_nodes = caps.get("method_name", [])
            mdef_nodes = caps.get("method_def", [])
            if not class_nodes or not mname_nodes or not mdef_nodes:
                continue
            class_name = class_nodes[0].text.decode("utf-8")
            method_name = mname_nodes[0].text.decode("utf-8")
            d = _Definition(mi.file_path, _strip_decorator(mdef_nodes[0]), "method")
            mi.class_methods.setdefault(class_name, {})[method_name] = d
            by_name[method_name].append(d)

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
            is_package = mi.file_path.name == "__init__.py"
            base_module = self._resolve_from_module(module_node, mi.module, is_package)
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

    def _resolve_from_module(
        self,
        module_node: Node,
        current_module: str,
        is_package: bool = False,
    ) -> Optional[str]:
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
            base_parts = current_module.split(".") if current_module else []
            # For a regular module ``pkg.sub.mod`` the leading dot refers to its
            # containing package ``pkg.sub`` (drop the module's own name). For a
            # package ``__init__.py`` the module name already *is* the package
            # (``_path_to_module`` strips ``__init__``), so the first dot refers
            # to the package itself — climb one level fewer.
            up = dot_count - 1 if is_package else dot_count
            if up > len(base_parts):
                # Climbs above the project root — not resolvable here.
                return None
            base = base_parts[: len(base_parts) - up]
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
    ) -> list[tuple[File, Node, str]]:
        """Resolve ``node`` (an identifier or dotted attribute) to definitions.

        Returns a list of ``(File, def_node, resolution)`` tuples. ``resolution``
        is ``"static_exact"`` for direct lookups (module top-level, imports,
        dotted-attribute walks, unique bare names, and ``self``/``cls`` methods)
        and ``"static_name"`` for the guarded receiver-agnostic method fallback.
        """
        self._ensure_built(files, project_root)
        current_module = self._path_to_module.get(file_path)

        call_expr = _call_function_expr(node)
        if call_expr is not None:
            results = self._resolve_call(current_module, call_expr, node)
        else:
            # Non-call reference (type annotations, base classes, ...). Exact
            # resolution only: no receiver reconstruction and no name-based
            # method fallback, so type edges stay precisely as before.
            parts = _node_to_dotted_parts(node)
            results = (
                [(d, "static_exact") for d in self._lookup(current_module, parts)]
                if parts
                else []
            )

        out: list[tuple[File, Node, str]] = []
        for d, resolution in results:
            f = files.get(d.file_path)
            if f is None:
                continue
            out.append((f, d.node, resolution))
        return out

    def _resolve_call(
        self,
        current_module: Optional[str],
        call_expr: Node,
        site_node: Node,
    ) -> list[tuple[_Definition, str]]:
        """Resolve a call's function expression to ``(_Definition, resolution)``."""
        parts = _node_to_dotted_parts(call_expr)
        if not parts:
            return []
        head = parts[0]
        method_name = parts[-1]

        # 1. ``self.method()`` / ``cls.method()`` -> the *enclosing* class's own
        # method (exact). Inherited methods aren't found locally and fall through
        # to the guarded name fallback below.
        if len(parts) >= 2 and head in ("self", "cls"):
            method_def = self._resolve_self_method(
                current_module, call_expr, site_node, head, method_name
            )
            if method_def is not None:
                return [(method_def, "static_exact")]

        # 2. Exact resolution: module top-level, imports, dotted walk, or a
        # unique cross-module bare name.
        exact = self._lookup(current_module, parts)
        if exact:
            return [(d, "static_exact") for d in exact]

        # 3. Guarded name-based method fallback for ``receiver.method()`` whose
        # receiver type can't be resolved statically (e.g. unannotated params).
        # Restrict to a *simple identifier* receiver: chained calls, subscripts,
        # and dotted receivers (``a.b.c()``, ``x.y().z()``) give no head we can
        # trust, so we never guess a method binding for them.
        if call_expr.type != "attribute":
            return []
        receiver = call_expr.child_by_field_name("object")
        if receiver is None or receiver.type != "identifier" or head == "super":
            return []
        # Only when the receiver head is genuinely unknown -- not an import
        # alias, project top-level symbol, or module prefix. ``self``/``cls``
        # reach here only as inherited-method fallthrough and always qualify.
        if head not in ("self", "cls") and self._head_is_resolvable(current_module, head):
            return []
        return [(d, "static_name") for d in self._name_fallback(method_name)]

    def _resolve_self_method(
        self,
        current_module: Optional[str],
        call_expr: Node,
        site_node: Node,
        receiver: str,
        method_name: str,
    ) -> Optional[_Definition]:
        """Resolve ``self.method``/``cls.method`` against the enclosing class.

        Guards against binding when ``self``/``cls`` isn't actually the method
        receiver in scope -- e.g. a ``@staticmethod`` referencing ``self`` or a
        nested function that redefines the first parameter.
        """
        if call_expr.type != "attribute":
            return None
        recv_node = call_expr.child_by_field_name("object")
        if recv_node is None or recv_node.type != "identifier":
            return None
        if not current_module or current_module not in self._modules:
            return None
        class_node = _enclosing_class_node(site_node)
        if class_node is None:
            return None
        # The function immediately enclosing the call site must take ``receiver``
        # as its first parameter for the binding to be sound.
        func = _enclosing_function_node(site_node, class_node)
        if func is None or _first_parameter_name(func) != receiver:
            return None
        name_node = class_node.child_by_field_name("name")
        if name_node is None:
            return None
        class_name = name_node.text.decode("utf-8")
        mi = self._modules[current_module]
        return mi.class_methods.get(class_name, {}).get(method_name)

    def _head_is_resolvable(self, current_module: Optional[str], head: str) -> bool:
        """Whether the receiver ``head`` names something we can place statically.

        Distinguishes "head not found at all" (an unknown/local receiver such as
        an unannotated parameter, which qualifies for the name fallback) from
        "head is a known symbol whose tail walk merely failed" (does not).
        """
        if current_module and current_module in self._modules:
            mi = self._modules[current_module]
            if head in mi.imports or head in mi.top_level:
                return True
        if head in self._modules:
            return True
        # A project-wide top-level definition (class/func/var) by this name.
        for d in self._by_name.get(head, ()):
            if d.kind != "method":
                return True
        return False

    def _name_fallback(self, method_name: str) -> list[_Definition]:
        """Return method defs named ``method_name`` (guarded by a count cap)."""
        candidates = [d for d in self._by_name.get(method_name, ()) if d.kind == "method"]
        if not candidates:
            return []
        if len(candidates) > _NAME_FALLBACK_MAX_CANDIDATES:
            logger.debug(
                "ts_resolver: skipping name fallback for %r (%d candidates > %d)",
                method_name, len(candidates), _NAME_FALLBACK_MAX_CANDIDATES,
            )
            return []
        # Deterministic ordering so edge writes are stable across runs/workers.
        candidates.sort(key=lambda d: (str(d.file_path), d.node.start_byte))
        return candidates

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

        # 3. Cross-project bare-name fallback. This is a last resort: a bare
        # identifier carries no receiver or import to disambiguate it.
        #   * Methods (kind == 'method') are excluded — a receiver-less ``run()``
        #     can't pick which class's ``run`` is meant, so linking it to every
        #     ``Foo.run`` in the project is a false-CALLS factory.
        #   * Among the remaining module-level defs we resolve only when exactly
        #     one matches; multiple same-named defs are ambiguous and dropped
        #     (jedi misses these too — precision over recall for edge building).
        candidates = [
            d for d in self._by_name.get(head, ()) if d.kind != "method"
        ]
        if len(candidates) != 1:
            return []
        return self._walk_tail(candidates[0], tail) if tail else list(candidates)

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


def _enclosing_class_node(node: Node) -> Optional[Node]:
    """Return the nearest enclosing ``class_definition`` ancestor of ``node``.

    Used to bind ``self``/``cls`` to the class that owns the containing method.
    Walking strictly upward keeps nested classes/functions correct: the call
    site's first ``class_definition`` ancestor is the class whose ``self`` is in
    scope.
    """
    cur = node.parent
    while cur is not None:
        if cur.type == "class_definition":
            return cur
        cur = cur.parent
    return None


def _call_function_expr(node: Node) -> Optional[Node]:
    """If ``node`` sits in a call's *function* position, return that expression.

    Handles both shapes reaching the resolver: the full call-function node
    (``Foo.bar`` / ``helper``) and the bare method-name identifier (``bar``)
    that ``PythonAnalyzer._extract_call_target`` produces for ``recv.method()``
    in production. Returns ``None`` for non-call references (type annotations,
    base classes, plain name reads) so they keep exact-only resolution.
    """
    parent = node.parent
    if parent is None:
        return None
    if parent.type == "call" and parent.child_by_field_name("function") == node:
        return node
    if parent.type == "attribute" and parent.child_by_field_name("attribute") == node:
        grand = parent.parent
        if (
            grand is not None
            and grand.type == "call"
            and grand.child_by_field_name("function") == parent
        ):
            return parent
    return None


def _enclosing_function_node(node: Node, stop_at: Node) -> Optional[Node]:
    """Nearest ``function_definition`` ancestor of ``node`` below ``stop_at``.

    ``stop_at`` is the owning class; the search never crosses it so a method's
    own ``function_definition`` (not the class) is returned.
    """
    cur = node.parent
    while cur is not None and cur != stop_at:
        if cur.type == "function_definition":
            return cur
        cur = cur.parent
    return None


def _first_parameter_name(func_node: Node) -> Optional[str]:
    """Return the textual name of a function's first positional parameter."""
    params = func_node.child_by_field_name("parameters")
    if params is None:
        return None
    for child in params.named_children:
        if child.type == "identifier":
            return child.text.decode("utf-8")
        # ``self: Foo`` / ``self=...`` -- unwrap to the bound identifier.
        if child.type in ("typed_parameter", "default_parameter", "typed_default_parameter"):
            inner = child.child_by_field_name("name")
            if inner is None:
                inner = next(
                    (c for c in child.named_children if c.type == "identifier"), None
                )
            return inner.text.decode("utf-8") if inner is not None else None
        return None
    return None


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
