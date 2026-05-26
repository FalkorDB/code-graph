"""Tests for the LSP adapter — shim logic + a real jedi roundtrip.

The shim helpers are pure functions tested directly. The actual LSP
roundtrip test starts jedi-language-server against a tiny in-tree fixture
and asserts goto_definition + hover behave end-to-end. That test is
marked `slow` so CI can skip it when LSP installs are unavailable.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from bench.agents.lsp_adapter import (
    DEFAULT_SHIM,
    LSPClient,
    LSPShim,
    _cap,
    _location_to_dict,
    _trim_hover,
)


# ---------------------------------------------------------------------------
# Shim unit tests (no LSP server needed)
# ---------------------------------------------------------------------------

def test_trim_hover_keeps_one_signature_and_one_sentence():
    raw = textwrap.dedent("""
    def greet(name: str) -> str
    Return a greeting for the given name. This part is extra. Even more text.
    """).strip()
    out = _trim_hover(raw, DEFAULT_SHIM)
    assert "def greet" in out
    assert "Return a greeting for the given name." in out
    assert "extra" not in out


def test_trim_hover_strips_code_fences():
    raw = "```python\ndef foo()\n```\nShort docstring."
    out = _trim_hover(raw, DEFAULT_SHIM)
    assert "```" not in out
    assert "def foo()" in out


def test_trim_hover_handles_dict_and_list_contents():
    assert "x" in _trim_hover({"value": "x"}, DEFAULT_SHIM)
    assert "a" in _trim_hover([{"value": "a"}, "b"], DEFAULT_SHIM)
    assert _trim_hover(None, DEFAULT_SHIM) == ""


def test_location_to_dict_uses_relative_path():
    loc = {
        "relativePath": "src/a.py",
        "absolutePath": "/abs/src/a.py",
        "range": {"start": {"line": 10, "character": 4}, "end": {"line": 10, "character": 8}},
    }
    assert _location_to_dict(loc) == {"path": "src/a.py", "line": 10, "col": 4}


def test_location_to_dict_falls_back_to_absolute_when_no_relative():
    loc = {"absolutePath": "/abs/x.py", "range": {"start": {"line": 0, "character": 0}}}
    assert _location_to_dict(loc)["path"] == "/abs/x.py"


def test_cap_limits_results():
    items = list(range(200))
    assert len(_cap(items, LSPShim(max_results_per_call=10))) == 10


def test_shim_dataclass_defaults_match_yaml():
    # If you change shim.yaml, change DEFAULT_SHIM too.
    assert DEFAULT_SHIM.max_results_per_call == 50
    assert DEFAULT_SHIM.hover_signature_lines == 1
    assert DEFAULT_SHIM.hover_docstring_sentences == 1


# ---------------------------------------------------------------------------
# LSP roundtrip — slow, runs real jedi subprocess
# ---------------------------------------------------------------------------


@pytest.fixture
def python_repo(tmp_path: Path) -> Path:
    (tmp_path / "sample.py").write_text(textwrap.dedent('''\
        def greet(name):
            """Return a greeting for the given name."""
            return f"hello {name}"


        def main():
            who = "world"
            return greet(who)
        ''')
    )
    return tmp_path


@pytest.mark.slow
def test_real_jedi_goto_definition_finds_greet(python_repo: Path):
    """End-to-end against jedi-language-server.

    Skipped on `pytest -m 'not slow'`. Heavy: spawns the LSP subprocess
    and downloads jedi on first run.
    """
    client = LSPClient(repo_root=python_repo, language="python")
    with client.server_running():
        # In sample.py, `greet(who)` is called on line 7 (0-indexed). The
        # call site sits at "return greet(who)" — `greet` starts around col 11.
        defs = client.goto_definition("sample.py", line=7, col=11)
    # We expect at least one definition pointing back to sample.py line 0
    # (where `def greet` lives).
    assert any(d["path"].endswith("sample.py") and d["line"] == 0 for d in defs), defs


@pytest.mark.slow
def test_real_jedi_hover_is_shimmed(python_repo: Path):
    client = LSPClient(repo_root=python_repo, language="python")
    with client.server_running():
        h = client.hover("sample.py", line=7, col=11)
    text = h["text"]
    assert "greet" in text or text == ""  # jedi can sometimes return empty hover
    # No more than ~3 lines of output after shimming (signature + 1 sentence).
    assert text.count("\n") <= 3


@pytest.mark.slow
def test_real_jedi_document_symbols_lists_top_level_funcs(python_repo: Path):
    client = LSPClient(repo_root=python_repo, language="python")
    with client.server_running():
        syms = client.document_symbols("sample.py")
    names = {s["name"] for s in syms}
    assert {"greet", "main"}.issubset(names)
