"""Unit tests for the tree-sitter Python resolver (T18 / #689)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest
import tree_sitter_python as tspython
from tree_sitter import Language, Parser

from api.analyzers.python.ts_resolver import (
    TreeSitterPythonResolver,
    _node_to_dotted_parts,
    _path_to_module,
)
from api.entities.entity import Entity
from api.entities.file import File


_PY = Language(tspython.language())
_PARSER = Parser(_PY)


def _file_from(path: Path, source: str) -> File:
    tree = _PARSER.parse(source.encode("utf-8"))
    return File(path, tree)


def _find_call_node(tree_root, text: str):
    """Find the first call node whose surface text matches ``text``."""
    stack = [tree_root]
    while stack:
        node = stack.pop()
        if node.type == "call" and node.text.decode("utf-8").startswith(text):
            return node
        stack.extend(node.children)
    raise AssertionError(f"call '{text}' not found")


def _find_name_node(tree_root, text: str):
    stack = [tree_root]
    while stack:
        node = stack.pop()
        if node.type == "identifier" and node.text.decode("utf-8") == text:
            return node
        stack.extend(node.children)
    raise AssertionError(f"identifier '{text}' not found")


def _call_target(call_node):
    """Mirror ``PythonAnalyzer._extract_call_target``.

    Production passes the resolver the call's *method-name* identifier (the
    ``attribute`` child) for ``recv.method()``, not the full dotted node. Tests
    that exercise method-call resolution should feed the same shape.
    """
    func = call_node.child_by_field_name("function")
    if func is not None and func.type == "attribute":
        return func.child_by_field_name("attribute")
    return func


# ---------------------------------------------------------------------------
# _node_to_dotted_parts
# ---------------------------------------------------------------------------


def test_dotted_parts_identifier():
    tree = _PARSER.parse(b"foo")
    name = tree.root_node.descendant_for_point_range((0, 0), (0, 3))
    assert _node_to_dotted_parts(name) == ["foo"]


def test_dotted_parts_attribute_chain():
    tree = _PARSER.parse(b"a.b.c")
    # The whole expression as an attribute node
    expr = tree.root_node.named_children[0].named_children[0]
    assert _node_to_dotted_parts(expr) == ["a", "b", "c"]


def test_dotted_parts_subscript_unwrapping():
    # Optional[Node] in a type annotation context. tree-sitter-python wraps
    # this as a ``type`` node containing a ``generic_type``.
    tree = _PARSER.parse(b"x: Optional[Node] = None\n")
    type_node = None
    stack = [tree.root_node]
    while stack:
        n = stack.pop()
        if n.type == "type":
            type_node = n
            break
        stack.extend(n.children)
    assert type_node is not None
    assert _node_to_dotted_parts(type_node) == ["Optional"]


# ---------------------------------------------------------------------------
# _path_to_module
# ---------------------------------------------------------------------------


def test_path_to_module_basic(tmp_path: Path):
    root = tmp_path
    f = root / "pkg" / "sub" / "mod.py"
    assert _path_to_module(f, root) == "pkg.sub.mod"


def test_path_to_module_package_init(tmp_path: Path):
    root = tmp_path
    f = root / "pkg" / "sub" / "__init__.py"
    assert _path_to_module(f, root) == "pkg.sub"


def test_path_to_module_outside_root(tmp_path: Path):
    root = tmp_path
    f = Path("/elsewhere/foo.py")
    assert _path_to_module(f, root) == "/elsewhere/foo.py"


# ---------------------------------------------------------------------------
# Resolver end-to-end
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path, layout: dict[str, str]) -> dict[Path, File]:
    files: dict[Path, File] = {}
    for rel, src in layout.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src)
        files[p.resolve()] = _file_from(p.resolve(), src)
    return files


def test_resolver_local_module_function(tmp_path: Path):
    files = _make_project(
        tmp_path,
        {
            "mod.py": (
                "def helper():\n    pass\n\n"
                "def caller():\n    helper()\n"
            ),
        },
    )
    r = TreeSitterPythonResolver(_PY)
    mod_path = (tmp_path / "mod.py").resolve()
    helper_call = _find_call_node(files[mod_path].tree.root_node, "helper(")
    # Caller passes the call's identifier (after _extract_call_target).
    func_ident = helper_call.child_by_field_name("function")
    out = r.resolve(files, mod_path, tmp_path.resolve(), func_ident)
    assert len(out) == 1
    file, def_node, resolution = out[0]
    assert file.path == mod_path
    assert def_node.type == "function_definition"
    name = def_node.child_by_field_name("name").text.decode("utf-8")
    assert name == "helper"
    assert resolution == "static_exact"


def test_resolver_from_import_resolution(tmp_path: Path):
    files = _make_project(
        tmp_path,
        {
            "lib.py": "def shared():\n    return 1\n",
            "app.py": "from lib import shared\n\ndef use():\n    shared()\n",
        },
    )
    r = TreeSitterPythonResolver(_PY)
    app_path = (tmp_path / "app.py").resolve()
    lib_path = (tmp_path / "lib.py").resolve()
    call = _find_call_node(files[app_path].tree.root_node, "shared(")
    out = r.resolve(files, app_path, tmp_path.resolve(), call.child_by_field_name("function"))
    assert len(out) == 1
    assert out[0][0].path == lib_path
    assert out[0][1].child_by_field_name("name").text.decode("utf-8") == "shared"


def test_resolver_aliased_import(tmp_path: Path):
    files = _make_project(
        tmp_path,
        {
            "lib.py": "def shared():\n    return 1\n",
            "app.py": "from lib import shared as s\n\ndef use():\n    s()\n",
        },
    )
    r = TreeSitterPythonResolver(_PY)
    app_path = (tmp_path / "app.py").resolve()
    call = _find_call_node(files[app_path].tree.root_node, "s(")
    out = r.resolve(files, app_path, tmp_path.resolve(), call.child_by_field_name("function"))
    assert len(out) == 1
    assert out[0][0].path == (tmp_path / "lib.py").resolve()


def test_resolver_import_dotted_then_attribute(tmp_path: Path):
    files = _make_project(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/lib.py": "def shared():\n    return 1\n",
            "app.py": "import pkg.lib\n\ndef use():\n    pkg.lib.shared()\n",
        },
    )
    r = TreeSitterPythonResolver(_PY)
    app_path = (tmp_path / "app.py").resolve()
    call = _find_call_node(files[app_path].tree.root_node, "pkg.lib.shared(")
    # The call's function is the attribute chain pkg.lib.shared
    func = call.child_by_field_name("function")
    out = r.resolve(files, app_path, tmp_path.resolve(), func)
    assert len(out) == 1
    assert out[0][0].path == (tmp_path / "pkg" / "lib.py").resolve()


def test_resolver_class_method_via_class_name(tmp_path: Path):
    files = _make_project(
        tmp_path,
        {
            "mod.py": (
                "class Foo:\n"
                "    def bar(self):\n"
                "        return 1\n\n"
                "def caller():\n"
                "    Foo.bar(None)\n"
            ),
        },
    )
    r = TreeSitterPythonResolver(_PY)
    mod = (tmp_path / "mod.py").resolve()
    call = _find_call_node(files[mod].tree.root_node, "Foo.bar")
    func = call.child_by_field_name("function")
    out = r.resolve(files, mod, tmp_path.resolve(), func)
    assert len(out) == 1
    assert out[0][1].child_by_field_name("name").text.decode("utf-8") == "bar"


def test_resolver_unknown_name_returns_empty(tmp_path: Path):
    files = _make_project(tmp_path, {"mod.py": "x = totally_unknown_name\n"})
    r = TreeSitterPythonResolver(_PY)
    mod = (tmp_path / "mod.py").resolve()
    name = _find_name_node(files[mod].tree.root_node, "totally_unknown_name")
    assert r.resolve(files, mod, tmp_path.resolve(), name) == []


def test_resolver_many_defs_name_def_alignment(tmp_path: Path):
    """Regression for the scrambled module symbol table.

    With several top-level definitions in one module, pairing the ``@name``
    and ``@def`` captures by zipping two independently-grouped lists mis-
    aligned names with definitions (e.g. an imported ``arange`` call resolved
    to the ``array`` def node). Each imported call must resolve to the def
    whose name actually matches the call name.
    """
    lib_src = "".join(f"def fn_{i}():\n    return {i}\n\n" for i in range(10))
    import_line = "from lib import " + ", ".join(f"fn_{i}" for i in range(10))
    call_lines = "\n".join(f"    fn_{i}()" for i in range(10))
    app_src = f"{import_line}\n\ndef use():\n{call_lines}\n"
    files = _make_project(tmp_path, {"lib.py": lib_src, "app.py": app_src})
    r = TreeSitterPythonResolver(_PY)
    app_path = (tmp_path / "app.py").resolve()
    lib_path = (tmp_path / "lib.py").resolve()
    root = files[app_path].tree.root_node
    for i in range(10):
        call = _find_call_node(root, f"fn_{i}(")
        out = r.resolve(
            files, app_path, tmp_path.resolve(), call.child_by_field_name("function")
        )
        assert len(out) == 1, f"fn_{i} did not resolve uniquely"
        file, def_node, _ = out[0]
        assert file.path == lib_path
        resolved_name = def_node.child_by_field_name("name").text.decode("utf-8")
        assert resolved_name == f"fn_{i}", (
            f"call fn_{i} resolved to wrong def {resolved_name}"
        )


def test_resolver_many_classes_name_def_alignment(tmp_path: Path):
    """Same alignment regression for top-level classes."""
    lib_src = "".join(f"class Cls{i}:\n    pass\n\n" for i in range(8))
    import_line = "from lib import " + ", ".join(f"Cls{i}" for i in range(8))
    body = "\n".join(f"    Cls{i}()" for i in range(8))
    app_src = f"{import_line}\n\ndef use():\n{body}\n"
    files = _make_project(tmp_path, {"lib.py": lib_src, "app.py": app_src})
    r = TreeSitterPythonResolver(_PY)
    app_path = (tmp_path / "app.py").resolve()
    root = files[app_path].tree.root_node
    for i in range(8):
        call = _find_call_node(root, f"Cls{i}(")
        out = r.resolve(
            files, app_path, tmp_path.resolve(), call.child_by_field_name("function")
        )
        assert len(out) == 1
        resolved_name = out[0][1].child_by_field_name("name").text.decode("utf-8")
        assert resolved_name == f"Cls{i}"


# ---------------------------------------------------------------------------
# Cross-project bare-name fallback — precision (blocker #1 + Copilot #4)
# ---------------------------------------------------------------------------


def test_resolver_unique_cross_module_bare_name_resolves(tmp_path: Path):
    """A bare call to a *uniquely*-named module-level function still resolves
    across modules even without an explicit import."""
    files = _make_project(
        tmp_path,
        {
            "lib.py": "def helper():\n    return 1\n",
            "caller.py": "def f():\n    helper()\n",
        },
    )
    r = TreeSitterPythonResolver(_PY)
    caller = (tmp_path / "caller.py").resolve()
    call = _find_call_node(files[caller].tree.root_node, "helper(")
    out = r.resolve(files, caller, tmp_path.resolve(), call.child_by_field_name("function"))
    assert len(out) == 1
    assert out[0][0].path == (tmp_path / "lib.py").resolve()


def test_resolver_ambiguous_bare_name_returns_empty(tmp_path: Path):
    """Two module-level functions share a name: a bare call is ambiguous and
    must resolve to nothing rather than fanning out to both (false CALLS)."""
    files = _make_project(
        tmp_path,
        {
            "a.py": "def helper():\n    return 1\n",
            "b.py": "def helper():\n    return 2\n",
            "caller.py": "def f():\n    helper()\n",
        },
    )
    r = TreeSitterPythonResolver(_PY)
    caller = (tmp_path / "caller.py").resolve()
    call = _find_call_node(files[caller].tree.root_node, "helper(")
    out = r.resolve(files, caller, tmp_path.resolve(), call.child_by_field_name("function"))
    assert out == []


def test_resolver_func_and_class_same_name_ambiguous(tmp_path: Path):
    """A func and a class sharing a name are also ambiguous under bare lookup."""
    files = _make_project(
        tmp_path,
        {
            "a.py": "def Widget():\n    return 1\n",
            "b.py": "class Widget:\n    pass\n",
            "caller.py": "def f():\n    Widget()\n",
        },
    )
    r = TreeSitterPythonResolver(_PY)
    caller = (tmp_path / "caller.py").resolve()
    call = _find_call_node(files[caller].tree.root_node, "Widget(")
    out = r.resolve(files, caller, tmp_path.resolve(), call.child_by_field_name("function"))
    assert out == []


def test_resolver_bare_name_excludes_methods(tmp_path: Path):
    """A receiver-less ``run()`` must not bind to a class method ``A.run`` —
    methods need a receiver, so the bare-name fallback excludes them."""
    files = _make_project(
        tmp_path,
        {
            "a.py": "class A:\n    def run(self):\n        return 1\n",
            "caller.py": "def f():\n    run()\n",
        },
    )
    r = TreeSitterPythonResolver(_PY)
    caller = (tmp_path / "caller.py").resolve()
    call = _find_call_node(files[caller].tree.root_node, "run(")
    out = r.resolve(files, caller, tmp_path.resolve(), call.child_by_field_name("function"))
    assert out == []


# ---------------------------------------------------------------------------
# Relative imports inside package __init__.py (Copilot #3)
# ---------------------------------------------------------------------------


def test_resolver_relative_import_in_package_init(tmp_path: Path):
    """Inside ``pkg/sub/__init__.py`` the single dot refers to package
    ``pkg.sub`` itself, so ``from . import mod`` binds ``pkg.sub.mod`` (not
    ``pkg.mod``)."""
    files = _make_project(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/sub/__init__.py": "from . import mod\n\ndef use():\n    mod.thing()\n",
            "pkg/sub/mod.py": "def thing():\n    return 1\n",
        },
    )
    r = TreeSitterPythonResolver(_PY)
    init_path = (tmp_path / "pkg" / "sub" / "__init__.py").resolve()
    call = _find_call_node(files[init_path].tree.root_node, "mod.thing(")
    out = r.resolve(files, init_path, tmp_path.resolve(), call.child_by_field_name("function"))
    assert len(out) == 1
    assert out[0][0].path == (tmp_path / "pkg" / "sub" / "mod.py").resolve()


# ---------------------------------------------------------------------------
# Concurrency — _ensure_built must be race-free under the index thread pool
# ---------------------------------------------------------------------------


def test_resolver_concurrent_build_is_safe(tmp_path: Path):
    """Many threads resolving against the same files dict must all observe a
    fully-built table (no half-built reads from a concurrent rebuild)."""
    import threading

    files = _make_project(
        tmp_path,
        {
            "lib.py": "def shared():\n    return 1\n",
            "app.py": "from lib import shared\n\ndef use():\n    shared()\n",
        },
    )
    r = TreeSitterPythonResolver(_PY)
    app_path = (tmp_path / "app.py").resolve()
    root = tmp_path.resolve()
    call = _find_call_node(files[app_path].tree.root_node, "shared(")
    func = call.child_by_field_name("function")

    results: list[int] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        try:
            barrier.wait()
            for _ in range(20):
                out = r.resolve(files, app_path, root, func)
                results.append(len(out))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    assert results and all(n == 1 for n in results)


# ---------------------------------------------------------------------------
# PythonAnalyzer integration via env var
# ---------------------------------------------------------------------------


def test_python_analyzer_disables_lsp_under_tree_sitter_env():
    with mock.patch.dict(os.environ, {"CODE_GRAPH_PY_RESOLVER": "tree_sitter"}):
        from api.analyzers.python.analyzer import PythonAnalyzer

        a = PythonAnalyzer()
        assert a._ts_resolver is not None
        assert a.needs_lsp() is False


def test_python_analyzer_default_still_uses_jedi():
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("CODE_GRAPH_PY_RESOLVER", None)
        from api.analyzers.python.analyzer import PythonAnalyzer

        a = PythonAnalyzer()
        assert a._ts_resolver is None
        assert a.needs_lsp() is True


# ---------------------------------------------------------------------------
# Static method-call resolution: self/cls exact + guarded name fallback
# ---------------------------------------------------------------------------


def test_resolver_name_fallback_single_method(tmp_path: Path):
    """``g._query()`` with a single project method ``_query`` emits a CALLS edge
    tagged ``static_name`` even though ``g``'s type is unknown."""
    files = _make_project(
        tmp_path,
        {
            "graph.py": "class Graph:\n    def _query(self, q):\n        return q\n",
            "structural.py": "def _build_corpus(g):\n    g._query('x')\n",
        },
    )
    r = TreeSitterPythonResolver(_PY)
    sp = (tmp_path / "structural.py").resolve()
    call = _find_call_node(files[sp].tree.root_node, "g._query(")
    out = r.resolve(files, sp, tmp_path.resolve(), _call_target(call))
    assert len(out) == 1
    file, def_node, resolution = out[0]
    assert file.path == (tmp_path / "graph.py").resolve()
    assert def_node.child_by_field_name("name").text.decode("utf-8") == "_query"
    assert resolution == "static_name"


def test_resolver_self_method_exact_enclosing_class(tmp_path: Path):
    """``self._query()`` resolves to the *enclosing* class's method (exact),
    never to a same-named method on a different class."""
    src = (
        "class A:\n"
        "    def _query(self, q):\n"
        "        return q\n"
        "    def run(self):\n"
        "        self._query('x')\n\n"
        "class B:\n"
        "    def _query(self, q):\n"
        "        return q * 2\n"
    )
    files = _make_project(tmp_path, {"mod.py": src})
    r = TreeSitterPythonResolver(_PY)
    mod = (tmp_path / "mod.py").resolve()
    call = _find_call_node(files[mod].tree.root_node, "self._query(")
    out = r.resolve(files, mod, tmp_path.resolve(), _call_target(call))
    assert len(out) == 1
    _, def_node, resolution = out[0]
    assert resolution == "static_exact"
    cls = def_node.parent
    while cls is not None and cls.type != "class_definition":
        cls = cls.parent
    assert cls is not None
    assert cls.child_by_field_name("name").text.decode("utf-8") == "A"


def test_resolver_import_prefix_blocks_name_fallback(tmp_path: Path):
    """``logging.getLogger()`` with ``logging`` imported must NOT bind to a
    project method named ``getLogger`` -- the import-prefix guard rejects it."""
    files = _make_project(
        tmp_path,
        {
            "util.py": "class Log:\n    def getLogger(self):\n        return 1\n",
            "app.py": "import logging\n\ndef f():\n    logging.getLogger()\n",
        },
    )
    r = TreeSitterPythonResolver(_PY)
    app = (tmp_path / "app.py").resolve()
    call = _find_call_node(files[app].tree.root_node, "logging.getLogger(")
    out = r.resolve(files, app, tmp_path.resolve(), _call_target(call))
    assert out == []


def test_resolver_external_module_method_no_edge(tmp_path: Path):
    """``requests.get()`` (external import) must not bind to project ``get``
    methods even when the candidate count is under threshold."""
    files = _make_project(
        tmp_path,
        {
            "models.py": "class Session:\n    def get(self):\n        return 1\n",
            "app.py": "import requests\n\ndef f():\n    requests.get()\n",
        },
    )
    r = TreeSitterPythonResolver(_PY)
    app = (tmp_path / "app.py").resolve()
    call = _find_call_node(files[app].tree.root_node, "requests.get(")
    out = r.resolve(files, app, tmp_path.resolve(), _call_target(call))
    assert out == []


def test_resolver_name_fallback_threshold_skips(tmp_path: Path):
    """More same-named method defs than the threshold => no edge (avoids the
    common-method-name explosion)."""
    lib = "".join(
        f"class C{i}:\n    def get(self):\n        return {i}\n\n" for i in range(6)
    )
    files = _make_project(
        tmp_path,
        {"lib.py": lib, "app.py": "def f(g):\n    g.get()\n"},
    )
    r = TreeSitterPythonResolver(_PY)
    app = (tmp_path / "app.py").resolve()
    call = _find_call_node(files[app].tree.root_node, "g.get(")
    out = r.resolve(files, app, tmp_path.resolve(), _call_target(call))
    assert out == []


def test_resolver_name_fallback_at_threshold_returns_all(tmp_path: Path):
    """Exactly threshold-many candidates are all returned, tagged static_name
    and deterministically ordered by (file_path, start_byte)."""
    lib = "".join(
        f"class C{i}:\n    def fetch(self):\n        return {i}\n\n" for i in range(5)
    )
    files = _make_project(
        tmp_path,
        {"lib.py": lib, "app.py": "def f(g):\n    g.fetch()\n"},
    )
    r = TreeSitterPythonResolver(_PY)
    app = (tmp_path / "app.py").resolve()
    call = _find_call_node(files[app].tree.root_node, "g.fetch(")
    out = r.resolve(files, app, tmp_path.resolve(), _call_target(call))
    assert len(out) == 5
    assert all(resolution == "static_name" for _, _, resolution in out)
    starts = [def_node.start_byte for _, def_node, _ in out]
    assert starts == sorted(starts)


def test_resolver_super_call_no_name_fallback(tmp_path: Path):
    """``super().foo()`` must not trigger the global name fallback."""
    files = _make_project(
        tmp_path,
        {
            "base.py": "class Base:\n    def foo(self):\n        return 1\n",
            "child.py": (
                "class Child:\n"
                "    def foo(self):\n"
                "        super().foo()\n"
            ),
        },
    )
    r = TreeSitterPythonResolver(_PY)
    child = (tmp_path / "child.py").resolve()
    call = _find_call_node(files[child].tree.root_node, "super().foo(")
    out = r.resolve(files, child, tmp_path.resolve(), _call_target(call))
    assert out == []


# ---------------------------------------------------------------------------
# Entity resolution-precedence + normalization
# ---------------------------------------------------------------------------


def test_entity_resolution_precedence_static_exact_wins():
    tree = _PARSER.parse(b"x = 1\n")
    node = tree.root_node
    caller = Entity(node)
    callee = Entity(node)
    caller.add_resolved_symbol("call", callee, "static_name")
    caller.add_resolved_symbol("call", callee, "static_exact")
    assert caller.resolved_symbols["call"][callee] == "static_exact"
    # lsp (and a later static_name) must never downgrade static_exact.
    caller.add_resolved_symbol("call", callee, "lsp")
    caller.add_resolved_symbol("call", callee, "static_name")
    assert caller.resolved_symbols["call"][callee] == "static_exact"


def test_entity_resolved_symbol_normalizes_tuples_and_bare():
    tree = _PARSER.parse(b"x = 1\n")
    node = tree.root_node
    e = Entity(node)
    e.add_symbol("call", node)
    callee_a = Entity(node)
    callee_b = Entity(node)

    def f(key, symbol):
        # tuple (static resolver) + bare entity (legacy LSP/jedi)
        return [(callee_a, "static_name"), callee_b]

    e.resolved_symbol(f)
    assert e.resolved_symbols["call"][callee_a] == "static_name"
    assert e.resolved_symbols["call"][callee_b] == "lsp"


def test_resolver_chained_receiver_no_name_fallback(tmp_path: Path):
    """A chained receiver (``line.strip().split()``) has no head we can trust,
    so the name fallback must not fire even with a project method ``split``."""
    files = _make_project(
        tmp_path,
        {
            "lib.py": "class Tok:\n    def split(self):\n        return 1\n",
            "app.py": "def f(line):\n    line.strip().split()\n",
        },
    )
    r = TreeSitterPythonResolver(_PY)
    app = (tmp_path / "app.py").resolve()
    call = _find_call_node(files[app].tree.root_node, "line.strip().split(")
    out = r.resolve(files, app, tmp_path.resolve(), _call_target(call))
    assert out == []


def test_resolver_dotted_receiver_no_name_fallback(tmp_path: Path):
    """A dotted receiver (``a.b.method()``) is rejected by the simple-identifier
    guard -- only ``identifier.method()`` is eligible for the name fallback."""
    files = _make_project(
        tmp_path,
        {
            "lib.py": "class C:\n    def ping(self):\n        return 1\n",
            "app.py": "def f(a):\n    a.b.ping()\n",
        },
    )
    r = TreeSitterPythonResolver(_PY)
    app = (tmp_path / "app.py").resolve()
    call = _find_call_node(files[app].tree.root_node, "a.b.ping(")
    out = r.resolve(files, app, tmp_path.resolve(), _call_target(call))
    assert out == []


def test_resolver_self_in_staticmethod_not_exact(tmp_path: Path):
    """``self.method()`` inside a ``@staticmethod`` (no ``self`` parameter) must
    not produce a high-confidence ``static_exact`` edge to the enclosing class."""
    src = (
        "class A:\n"
        "    def _query(self, q):\n"
        "        return q\n"
        "    @staticmethod\n"
        "    def f():\n"
        "        self._query('x')\n"
    )
    files = _make_project(tmp_path, {"mod.py": src})
    r = TreeSitterPythonResolver(_PY)
    mod = (tmp_path / "mod.py").resolve()
    call = _find_call_node(files[mod].tree.root_node, "self._query(")
    out = r.resolve(files, mod, tmp_path.resolve(), _call_target(call))
    # No static_exact binding; at most a low-confidence name-based guess.
    assert all(resolution != "static_exact" for _, _, resolution in out)


def test_resolver_self_in_nested_function_shadowing_not_exact(tmp_path: Path):
    """A nested function that redefines the first parameter shadows the method's
    ``self``; the enclosing-function first-parameter guard must reject it."""
    src = (
        "class A:\n"
        "    def _query(self, q):\n"
        "        return q\n"
        "    def outer(self):\n"
        "        def inner(other):\n"
        "            self._query('x')\n"
        "        return inner\n"
    )
    files = _make_project(tmp_path, {"mod.py": src})
    r = TreeSitterPythonResolver(_PY)
    mod = (tmp_path / "mod.py").resolve()
    call = _find_call_node(files[mod].tree.root_node, "self._query(")
    out = r.resolve(files, mod, tmp_path.resolve(), _call_target(call))
    assert all(resolution != "static_exact" for _, _, resolution in out)
