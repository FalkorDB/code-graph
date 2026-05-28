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
    file, def_node = out[0]
    assert file.path == mod_path
    assert def_node.type == "function_definition"
    name = def_node.child_by_field_name("name").text.decode("utf-8")
    assert name == "helper"


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
