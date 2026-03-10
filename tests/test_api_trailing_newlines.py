from pathlib import Path


API_FILES_WITH_REQUIRED_TRAILING_NEWLINE = [
    "api/analyzers/csharp/__init__.py",
    "api/entities/entity.py",
    "api/index.py",
    "api/llm.py",
    "api/prompts.py",
]


def test_reported_api_files_end_with_trailing_newline():
    repo_root = Path(__file__).resolve().parent.parent

    for relative_path in API_FILES_WITH_REQUIRED_TRAILING_NEWLINE:
        file_path = repo_root / relative_path
        assert file_path.read_bytes().endswith(b"\n"), (
            f"{relative_path} must end with a trailing newline"
        )
