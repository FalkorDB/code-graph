from pathlib import Path

import e2e.seed_test_data as seed_test_data


def test_load_project_uses_existing_cached_clone(monkeypatch, tmp_path):
    repo_path = tmp_path / "GraphRAG-SDK"
    (repo_path / ".git").mkdir(parents=True)

    calls = []

    class FakeProject:
        @staticmethod
        def from_local_repository(path):
            calls.append(path)
            return path

    monkeypatch.setattr(seed_test_data, "REPOSITORIES_DIR", tmp_path)
    monkeypatch.setattr(seed_test_data, "Project", FakeProject)

    project = seed_test_data.load_project("https://github.com/FalkorDB/GraphRAG-SDK")

    assert project == repo_path
    assert calls == [repo_path]


def test_load_project_clones_into_cache(monkeypatch, tmp_path):
    repo_path = tmp_path / "flask"
    clone_calls = []
    project_calls = []

    class FakeProject:
        @staticmethod
        def from_local_repository(path):
            project_calls.append(path)
            return path

    def fake_clone(url: str, path: Path) -> Path:
        clone_calls.append((url, path))
        (path / ".git").mkdir(parents=True)
        return path

    monkeypatch.setattr(seed_test_data, "REPOSITORIES_DIR", tmp_path)
    monkeypatch.setattr(seed_test_data, "Project", FakeProject)
    monkeypatch.setattr(seed_test_data, "fresh_clone_repository", fake_clone)

    project = seed_test_data.load_project("https://github.com/pallets/flask")

    assert project == repo_path
    assert clone_calls == [("https://github.com/pallets/flask", repo_path)]
    assert project_calls == [repo_path]
