from contextlib import contextmanager
import importlib

from api.analyzers.python.analyzer import PythonAnalyzer


class _DummyLSP:
    def __init__(self, locations):
        self._locations = locations

    def request_definition(self, *_args, **_kwargs):
        return self._locations


class _DummyGraphNode:
    def __init__(self, node_id: int):
        self.id = node_id


class _DummyGraphLookup:
    def __init__(self, node_id: int):
        self.node_id = node_id
        self.calls = []

    def get_entity_at_position(self, path, line, labels):
        self.calls.append((path, line, labels))
        return _DummyGraphNode(self.node_id)


def test_python_resolve_symbol_uses_graph_fallback(tmp_path):
    """Cross-file resolution falls back to graph lookups for unchanged files."""
    analyzer = PythonAnalyzer()
    caller = tmp_path / "caller.py"
    target = tmp_path / "target.py"
    caller.write_text("foo()\n")
    target.write_text("def foo():\n    pass\n")

    tree = analyzer.parser.parse(caller.read_bytes())
    call_node = analyzer._captures("(call) @call", tree.root_node)["call"][0]
    graph = _DummyGraphLookup(42)
    lsp = _DummyLSP(
        [
            {
                "absolutePath": str(target),
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 1, "character": 0},
                },
            }
        ]
    )

    resolved = analyzer.resolve_symbol({}, lsp, caller, tmp_path, graph, "call", call_node)

    assert [entity.id for entity in resolved] == [42]
    assert graph.calls == [(str(target), 0, ["Function", "Class"])]


def test_incremental_update_reprocesses_dependents_under_repo_lock(monkeypatch, tmp_path):
    """Incremental updates expand transitive dependents and hold the repo lock."""
    incremental_update_module = importlib.import_module("api.git_utils.incremental_update")
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    operations = []

    class _FakeCommit:
        def __init__(self, sha):
            self.id = sha
            self.short_id = sha[:7]
            self.tree = object()

    class _FakeRepo:
        def revparse_single(self, sha):
            return _FakeCommit(sha)

        def diff(self, _from_commit, _to_commit):
            return object()

        def checkout_tree(self, _tree, strategy=None):
            operations.append(("checkout", strategy))

        def set_head_detached(self, commit_id):
            operations.append(("detach", commit_id))

    class _FakeAnalyzer:
        def supported_types(self):
            return [".py"]

        def analyze_files(self, files, path, graph):
            operations.append(("analyze", [file.name for file in files], path, graph))

    class _FakeGraph:
        def __init__(self, name):
            self.name = name

        def get_direct_dependent_files(self, files):
            names = tuple(file.name for file in files)
            operations.append(("dependents", names))
            if names == ("deleted.py", "modified.py"):
                return [repo_path / "caller.py"]
            if names == ("caller.py",):
                return [repo_path / "transitive.py"]
            return []

        def delete_files(self, files):
            operations.append(("delete", [file.name for file in files]))

    @contextmanager
    def _fake_repo_lock(repo_name):
        operations.append(("lock-enter", repo_name))
        try:
            yield
        finally:
            operations.append(("lock-exit", repo_name))

    monkeypatch.setattr(incremental_update_module, "repo_local_path", lambda _name: repo_path)
    monkeypatch.setattr(incremental_update_module, "Repository", lambda _path: _FakeRepo())
    monkeypatch.setattr(incremental_update_module, "SourceAnalyzer", _FakeAnalyzer)
    monkeypatch.setattr(incremental_update_module, "Graph", _FakeGraph)
    monkeypatch.setattr(
        incremental_update_module,
        "classify_changes",
        lambda _diff, _repo, _supported, _ignore: (
            [repo_path / "added.py"],
            [repo_path / "deleted.py"],
            [repo_path / "modified.py"],
        ),
    )
    monkeypatch.setattr(
        incremental_update_module,
        "set_repo_commit",
        lambda repo_name, commit: operations.append(("bookmark", repo_name, commit)),
    )
    monkeypatch.setattr(incremental_update_module, "repo_update_lock", _fake_repo_lock)

    result = incremental_update_module.incremental_update("repo", "aaaa111", "bbbb222")

    assert result == {
        "files_added": 1,
        "files_modified": 1,
        "files_deleted": 1,
        "commit": "bbbb222",
    }
    assert ("delete", ["deleted.py", "modified.py"]) in operations
    analyze_call = next(op for op in operations if op[0] == "analyze")
    assert analyze_call[1] == ["added.py", "modified.py", "caller.py", "transitive.py"]
    assert analyze_call[2] == repo_path
    assert operations[0] == ("lock-enter", "repo")
    assert operations[-1] == ("lock-exit", "repo")
    assert operations.index(("lock-enter", "repo")) < operations.index(("checkout", incremental_update_module.CheckoutStrategy.FORCE))
    assert operations.index(("bookmark", "repo", "bbbb222")) < operations.index(("lock-exit", "repo"))
