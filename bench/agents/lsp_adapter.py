"""LSP adapter for the `lsp` benchmark config.

Wraps multilspy's `SyncLanguageServer` so we can expose a small set of
LSP-backed navigation tools to SWE-agent. Every response goes through the
shim defined in `bench/tools/lsp/shim.yaml` so raw LSP verbosity doesn't
dominate the token-cost comparison.

Notes on the language server choice:
- multilspy 0.0.11 (current pinned version, latest that resolves under our
  Python 3.13 constraints) ships **jedi-language-server** for Python, not
  pyright. The benchmark validity claim doesn't hinge on jedi-vs-pyright:
  the shim normalizes responses to {path, line, col} + 1-line hover, and
  both servers are competent Python LSPs. If we later need pyright, we'd
  bump multilspy to ≥0.0.15.
- multilspy 0.0.11 also has no `request_workspace_symbol`. We therefore
  drop `workspace_symbols` from the LSP tool set; the agent falls back to
  bash+grep, which is what real LSP workflows actually do.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shim configuration — mirrors bench/tools/lsp/shim.yaml
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LSPShim:
    max_results_per_call: int = 50
    hover_signature_lines: int = 1
    hover_docstring_sentences: int = 1


DEFAULT_SHIM = LSPShim()


def _trim_hover(contents: Any, shim: LSPShim) -> str:
    """Reduce an LSP Hover contents blob to 1 signature + 1 docstring sentence."""
    text = _hover_to_str(contents)
    if not text:
        return ""
    # Drop fence-only lines and empty lines, then split into signature vs rest.
    real_lines = [
        ln for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("```")
    ]
    signature_part = real_lines[: shim.hover_signature_lines]
    rest_lines = real_lines[shim.hover_signature_lines :]
    docstring = " ".join(ln.lstrip("> ").strip() for ln in rest_lines)
    sentences = _split_sentences(docstring, shim.hover_docstring_sentences)

    parts: list[str] = []
    parts.extend(signature_part)
    if sentences:
        parts.append(sentences)
    return "\n".join(parts).strip()


def _hover_to_str(contents: Any) -> str:
    if contents is None:
        return ""
    if isinstance(contents, str):
        return contents
    if isinstance(contents, dict):
        return str(contents.get("value", ""))
    if isinstance(contents, list):
        return "\n".join(_hover_to_str(c) for c in contents)
    return str(contents)


def _split_sentences(text: str, n: int) -> str:
    text = text.strip()
    if not text or n <= 0:
        return ""
    # Lightweight sentence split — good enough for docstrings.
    parts: list[str] = []
    buf: list[str] = []
    for ch in text:
        buf.append(ch)
        if ch in ".!?":
            parts.append("".join(buf).strip())
            buf = []
            if len(parts) >= n:
                break
    if not parts and buf:
        parts.append("".join(buf).strip())
    return " ".join(parts[:n])


def _location_to_dict(loc: dict[str, Any]) -> dict[str, Any]:
    """Convert a multilspy Location (TypedDict) to the shimmed shape."""
    rng = loc.get("range") or {}
    start = rng.get("start") or {}
    path = loc.get("relativePath") or loc.get("absolutePath") or ""
    return {
        "path": path,
        "line": int(start.get("line", 0)),
        "col": int(start.get("character", 0)),
    }


def _cap(items: list[Any], shim: LSPShim) -> list[Any]:
    return items[: shim.max_results_per_call]


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class LSPClient:
    """Lazily-started multilspy session for a single repo root.

    Use as a context manager; the underlying language server subprocess
    lives only inside `with server_running()`.
    """

    def __init__(self, repo_root: str | Path, language: str = "python",
                 shim: LSPShim = DEFAULT_SHIM,
                 environment_path: str | None = None) -> None:
        self.repo_root = str(Path(repo_root).resolve())
        self.language = language
        self.shim = shim
        self._env_path = environment_path
        self._server: Any | None = None  # SyncLanguageServer
        self._cm: Any | None = None  # live start_server() context (persistent mode)

    # ----- lifecycle ------------------------------------------------------

    def _build_server(self) -> Any:
        # Local imports keep this module importable without multilspy installed.
        from multilspy import SyncLanguageServer
        from multilspy.multilspy_config import MultilspyConfig
        from multilspy.multilspy_logger import MultilspyLogger

        # NOTE: The multilspy fork we depend on expects MultilspyConfig built
        # via `from_dict` (the constructor doesn't initialize all fields the
        # JediServer reads). For Python we also need an environment_path so
        # jedi knows where to look for installed packages — fall back to the
        # current interpreter's prefix if the caller doesn't provide one.
        import sys as _sys
        config_dict: dict[str, Any] = {"code_language": self.language}
        if self.language == "python":
            config_dict["environment_path"] = self._env_path or _sys.prefix
        else:
            # Pass through if caller explicitly set an env path.
            if self._env_path:
                config_dict["environment_path"] = self._env_path
        config = MultilspyConfig.from_dict(config_dict)
        logger_ = MultilspyLogger()
        return SyncLanguageServer.create(config, logger_, self.repo_root)

    @contextmanager
    def server_running(self) -> Iterator["LSPClient"]:
        self._server = self._build_server()
        with self._server.start_server():
            try:
                yield self
            finally:
                self._server = None

    # ----- persistent lifecycle (for a long-lived MCP server) -------------

    def start(self) -> "LSPClient":
        """Start a persistent language-server subprocess.

        Unlike ``server_running`` (a per-call context manager used by the
        bash CLI), this keeps one jedi process alive so an MCP server can
        serve many tool calls without paying the ~1-3s startup each time.
        The caller is responsible for calling ``stop()`` at shutdown.
        """
        if self._server is not None:
            return self
        server = self._build_server()
        cm = server.start_server()
        cm.__enter__()
        self._server = server
        self._cm = cm
        return self

    def stop(self) -> None:
        cm = getattr(self, "_cm", None)
        if cm is not None:
            try:
                cm.__exit__(None, None, None)
            finally:
                self._cm = None
        self._server = None

    # ----- relative path normalization -----------------------------------

    def _rel(self, file_path: str) -> str:
        p = Path(file_path)
        if p.is_absolute():
            try:
                return str(p.relative_to(self.repo_root))
            except ValueError:
                return str(p)
        return file_path

    # ----- tools (names mirror bench/tools/lsp/tools.yaml) ---------------

    def goto_definition(self, file: str, line: int, col: int) -> list[dict[str, Any]]:
        assert self._server is not None, "LSP server not started"
        raw = self._server.request_definition(self._rel(file), line, col) or []
        return _cap([_location_to_dict(loc) for loc in raw], self.shim)

    def find_references(self, file: str, line: int, col: int) -> list[dict[str, Any]]:
        assert self._server is not None, "LSP server not started"
        raw = self._server.request_references(self._rel(file), line, col) or []
        return _cap([_location_to_dict(loc) for loc in raw], self.shim)

    def hover(self, file: str, line: int, col: int) -> dict[str, Any]:
        assert self._server is not None, "LSP server not started"
        raw = self._server.request_hover(self._rel(file), line, col)
        if not raw:
            return {"text": ""}
        return {"text": _trim_hover(raw.get("contents"), self.shim)}

    def document_symbols(self, file: str) -> list[dict[str, Any]]:
        assert self._server is not None, "LSP server not started"
        raw = self._server.request_document_symbols(self._rel(file))
        # multilspy returns (symbols, tree). We only want the flat list.
        symbols = raw[0] if isinstance(raw, tuple) else (raw or [])
        out: list[dict[str, Any]] = []
        for s in symbols:
            loc = s.get("location") or {}
            d = _location_to_dict(loc) if loc else {"path": self._rel(file), "line": 0, "col": 0}
            d["name"] = s.get("name", "")
            d["kind"] = s.get("kind", "")
            out.append(d)
        return _cap(out, self.shim)


# ---------------------------------------------------------------------------
# Module-level callables — what SWE-agent tool registries expect
# ---------------------------------------------------------------------------

def _client_from_env(shim: LSPShim = DEFAULT_SHIM) -> LSPClient:
    repo_root = os.environ.get("LSP_REPO_ROOT") or os.getcwd()
    language = os.environ.get("LSP_LANGUAGE", "python")
    return LSPClient(repo_root=repo_root, language=language, shim=shim)


def goto_definition(file: str, line: int, col: int) -> list[dict[str, Any]]:
    with _client_from_env().server_running() as c:
        return c.goto_definition(file, line, col)


def find_references(file: str, line: int, col: int) -> list[dict[str, Any]]:
    with _client_from_env().server_running() as c:
        return c.find_references(file, line, col)


def hover(file: str, line: int, col: int) -> dict[str, Any]:
    with _client_from_env().server_running() as c:
        return c.hover(file, line, col)


def document_symbols(file: str) -> list[dict[str, Any]]:
    with _client_from_env().server_running() as c:
        return c.document_symbols(file)
