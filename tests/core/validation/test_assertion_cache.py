from __future__ import annotations

import ast
from pathlib import Path

import pytest

from maid_runner.core._artifact_collection_cache import clear_artifact_collection_cache
from maid_runner.core._test_assertions import (
    TestAssertionTable,
    clear_test_assertion_cache,
    get_cached_test_assertions,
    validate_test_assertions,
)
from maid_runner.core._validation_test_artifacts import (
    clear_test_discovery_cache,
    find_test_files,
)
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine


@pytest.fixture(autouse=True)
def clear_caches():
    clear_artifact_collection_cache()
    yield
    clear_artifact_collection_cache()


def _write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _write_manifest(project_root: Path, slug: str, validate_command: str) -> Path:
    return _write(
        project_root / "manifests" / f"{slug}.manifest.yaml",
        f"""schema: "2"
goal: "Validate shared behavior"
type: fix
files:
  edit:
    - path: src/shared.py
      artifacts:
        - kind: function
          name: shared
validate:
  - {validate_command}
""",
    )


def _batch_signature(batch) -> dict:
    data = batch.to_dict()
    data.pop("duration_ms", None)
    for result in data["results"]:
        result.pop("duration_ms", None)
    return data


def _count_ast_parses(monkeypatch, test_path: Path) -> list[str]:
    parsed: list[str] = []
    real_parse = ast.parse

    def counting_parse(source, filename="<unknown>", *args, **kwargs):
        normalized = str(filename).replace("\\", "/")
        if Path(filename) == test_path or normalized == f"tests/{test_path.name}":
            parsed.append(filename)
        return real_parse(source, filename, *args, **kwargs)

    monkeypatch.setattr(ast, "parse", counting_parse)
    return parsed


def _count_iterdir(monkeypatch, target_path: Path) -> list[Path]:
    walks: list[Path] = []
    real_iterdir = Path.iterdir

    def counting_iterdir(self):
        if self == target_path or self.is_relative_to(target_path):
            walks.append(self)
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", counting_iterdir)
    return walks


def test_validate_test_assertions_reuses_unchanged_python_test_file(
    monkeypatch,
    tmp_path,
):
    test_file = _write(
        tmp_path / "tests" / "test_shared.py",
        "def test_shared():\n    value = 1\n",
    )
    parsed = _count_ast_parses(monkeypatch, test_file)

    first = validate_test_assertions(tmp_path, ["tests/test_shared.py"])
    second = validate_test_assertions(tmp_path, ["tests/test_shared.py"])

    assert len(parsed) == 1
    assert [error.code for error in first] == [ErrorCode.MISSING_ASSERTIONS]
    assert [error.to_dict() for error in second] == [error.to_dict() for error in first]


def test_validate_test_assertions_invalidates_when_file_signature_changes(
    monkeypatch,
    tmp_path,
):
    test_file = _write(
        tmp_path / "tests" / "test_shared.py",
        "def test_shared():\n    value = 1\n",
    )
    parsed = _count_ast_parses(monkeypatch, test_file)

    first = get_cached_test_assertions("tests/test_shared.py", tmp_path)
    test_file.write_text("def test_shared():\n    assert True\n")
    second = get_cached_test_assertions("tests/test_shared.py", tmp_path)

    assert isinstance(first, TestAssertionTable)
    assert len(parsed) == 2
    assert [error.code for error in first.errors] == [ErrorCode.MISSING_ASSERTIONS]
    assert second.errors == ()


def test_find_test_files_reuses_broad_directory_expansion(monkeypatch, tmp_path):
    _write(tmp_path / "src" / "shared.py", "def shared():\n    return 1\n")
    _write(tmp_path / "tests" / "test_shared.py")
    _write(tmp_path / "tests" / "unit" / "test_nested.py")
    manifest_path = _write_manifest(tmp_path, "first", "pytest tests/ -v")
    walks = _count_iterdir(monkeypatch, tmp_path / "tests")
    manifest = load_manifest(manifest_path)

    first = find_test_files(manifest, tmp_path)
    second = find_test_files(manifest, tmp_path)

    assert walks == [tmp_path / "tests", tmp_path / "tests" / "unit"]
    assert second == first == ["tests/test_shared.py", "tests/unit/test_nested.py"]


def test_validate_all_with_assertion_cache_matches_uncached_result(
    monkeypatch,
    tmp_path,
):
    _write(tmp_path / "src" / "shared.py", "def shared():\n    return 1\n")
    _write(
        tmp_path / "tests" / "test_shared.py",
        "from src.shared import shared\n\n"
        "def test_shared():\n"
        "    assert shared() == 1\n",
    )
    _write_manifest(tmp_path, "first", "pytest tests/ -v")
    _write_manifest(tmp_path, "second", "pytest tests/ -v")

    engine = ValidationEngine(project_root=tmp_path)
    cached = engine.validate_all(
        "manifests",
        mode=ValidationMode.BEHAVIORAL,
        check_assertions=True,
    )

    from maid_runner.core import _test_assertions as test_assertions

    get_cached = test_assertions.get_cached_test_assertions

    def uncached_get_test_assertions(*args, **kwargs):
        test_assertions.clear_test_assertion_cache()
        return get_cached(*args, **kwargs)

    monkeypatch.setattr(
        test_assertions,
        "get_cached_test_assertions",
        uncached_get_test_assertions,
    )
    uncached = engine.validate_all(
        "manifests",
        mode=ValidationMode.BEHAVIORAL,
        check_assertions=True,
    )

    assert cached.success is True
    assert _batch_signature(cached) == _batch_signature(uncached)


def test_validate_test_assertions_preserves_python_syntax_error_tolerance(
    monkeypatch,
    tmp_path,
):
    test_file = _write(
        tmp_path / "tests" / "test_broken.py",
        "def test_broken(:\n    assert True\n",
    )
    parsed = _count_ast_parses(monkeypatch, test_file)

    first = validate_test_assertions(tmp_path, ["tests/test_broken.py"])
    second = validate_test_assertions(tmp_path, ["tests/test_broken.py"])

    assert len(parsed) == 1
    assert first == []
    assert second == []


def test_clear_test_assertion_cache_forces_recheck(monkeypatch, tmp_path):
    test_file = _write(
        tmp_path / "tests" / "test_shared.py",
        "def test_shared():\n    value = 1\n",
    )
    parsed = _count_ast_parses(monkeypatch, test_file)

    get_cached_test_assertions("tests/test_shared.py", tmp_path)
    clear_test_assertion_cache()
    table = get_cached_test_assertions("tests/test_shared.py", tmp_path)

    assert len(parsed) == 2
    assert [error.code for error in table.errors] == [ErrorCode.MISSING_ASSERTIONS]


def test_find_test_files_invalidates_when_directory_signature_changes(tmp_path):
    _write(tmp_path / "src" / "shared.py", "def shared():\n    return 1\n")
    _write(tmp_path / "tests" / "test_first.py")
    manifest = load_manifest(_write_manifest(tmp_path, "first", "pytest tests/ -v"))

    first = find_test_files(manifest, tmp_path)
    _write(tmp_path / "tests" / "test_second.py")
    second = find_test_files(manifest, tmp_path)

    assert first == ["tests/test_first.py"]
    assert second == ["tests/test_first.py", "tests/test_second.py"]


def test_find_test_files_invalidates_when_nested_directory_signature_changes(tmp_path):
    _write(tmp_path / "src" / "shared.py", "def shared():\n    return 1\n")
    _write(tmp_path / "tests" / "unit" / "test_first.py")
    manifest = load_manifest(_write_manifest(tmp_path, "first", "pytest tests/ -v"))

    first = find_test_files(manifest, tmp_path)
    _write(tmp_path / "tests" / "unit" / "test_second.py")
    second = find_test_files(manifest, tmp_path)

    assert first == ["tests/unit/test_first.py"]
    assert second == ["tests/unit/test_first.py", "tests/unit/test_second.py"]


def test_find_test_files_signature_does_not_recurse_symlinked_directory(tmp_path):
    _write(tmp_path / "src" / "shared.py", "def shared():\n    return 1\n")
    _write(tmp_path / "tests" / "test_inside.py")
    outside = tmp_path / "outside"
    _write(outside / "test_external.py")
    try:
        (tmp_path / "tests" / "linked").symlink_to(
            outside,
            target_is_directory=True,
        )
    except OSError as exc:
        pytest.skip(f"symlink creation failed: {exc}")
    manifest = load_manifest(_write_manifest(tmp_path, "first", "pytest tests/ -v"))

    assert find_test_files(manifest, tmp_path) == ["tests/test_inside.py"]


def test_find_test_files_reuses_cache_when_symlinked_directory_target_changes(
    monkeypatch,
    tmp_path,
):
    _write(tmp_path / "src" / "shared.py", "def shared():\n    return 1\n")
    _write(tmp_path / "tests" / "test_inside.py")
    outside = tmp_path / "outside"
    _write(outside / "test_external.py")
    try:
        (tmp_path / "tests" / "linked").symlink_to(
            outside,
            target_is_directory=True,
        )
    except OSError as exc:
        pytest.skip(f"symlink creation failed: {exc}")
    manifest = load_manifest(_write_manifest(tmp_path, "first", "pytest tests/ -v"))
    walks = _count_iterdir(monkeypatch, tmp_path / "tests")

    first = find_test_files(manifest, tmp_path)
    _write(outside / "test_later.py")
    second = find_test_files(manifest, tmp_path)

    assert walks == [tmp_path / "tests"]
    assert first == second == ["tests/test_inside.py"]


def test_find_test_files_invalidates_when_symlinked_file_target_appears(tmp_path):
    _write(tmp_path / "src" / "shared.py", "def shared():\n    return 1\n")
    target = tmp_path / "target" / "test_external.py"
    link = tmp_path / "tests" / "test_link.py"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation failed: {exc}")
    manifest = load_manifest(_write_manifest(tmp_path, "first", "pytest tests/ -v"))

    first = find_test_files(manifest, tmp_path)
    _write(target)
    second = find_test_files(manifest, tmp_path)

    assert first == []
    assert second == ["tests/test_link.py"]


def test_find_test_files_invalidates_when_symlinked_file_target_disappears(tmp_path):
    _write(tmp_path / "src" / "shared.py", "def shared():\n    return 1\n")
    target = _write(tmp_path / "target" / "test_external.py")
    link = tmp_path / "tests" / "test_link.py"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation failed: {exc}")
    manifest = load_manifest(_write_manifest(tmp_path, "first", "pytest tests/ -v"))

    first = find_test_files(manifest, tmp_path)
    target.unlink()
    second = find_test_files(manifest, tmp_path)

    assert first == ["tests/test_link.py"]
    assert second == []


def test_find_test_files_falls_back_when_directory_signature_cannot_read(
    monkeypatch,
    tmp_path,
):
    _write(tmp_path / "src" / "shared.py", "def shared():\n    return 1\n")
    _write(tmp_path / "tests" / "test_top.py")
    _write(tmp_path / "tests" / "unit" / "test_nested.py")
    manifest = load_manifest(_write_manifest(tmp_path, "first", "pytest tests/ -v"))
    real_iterdir = Path.iterdir

    def unreadable_nested_directory(self):
        if self == tmp_path / "tests" / "unit":
            raise OSError("permission denied")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", unreadable_nested_directory)

    assert find_test_files(manifest, tmp_path) == [
        "tests/test_top.py",
        "tests/unit/test_nested.py",
    ]


def test_clear_test_discovery_cache_forces_directory_walk(monkeypatch, tmp_path):
    _write(tmp_path / "src" / "shared.py", "def shared():\n    return 1\n")
    _write(tmp_path / "tests" / "test_shared.py")
    manifest = load_manifest(_write_manifest(tmp_path, "first", "pytest tests/ -v"))
    walks = _count_iterdir(monkeypatch, tmp_path / "tests")

    find_test_files(manifest, tmp_path)
    clear_test_discovery_cache()
    find_test_files(manifest, tmp_path)

    assert walks == [tmp_path / "tests", tmp_path / "tests"]


def test_clear_artifact_collection_cache_drops_assertion_and_discovery_caches(
    monkeypatch,
    tmp_path,
):
    _write(tmp_path / "src" / "shared.py", "def shared():\n    return 1\n")
    test_file = _write(
        tmp_path / "tests" / "test_shared.py",
        "def test_shared():\n    value = 1\n",
    )
    manifest = load_manifest(_write_manifest(tmp_path, "first", "pytest tests/ -v"))
    parsed = _count_ast_parses(monkeypatch, test_file)
    walks = _count_iterdir(monkeypatch, tmp_path / "tests")

    find_test_files(manifest, tmp_path)
    validate_test_assertions(tmp_path, ["tests/test_shared.py"])
    clear_artifact_collection_cache()
    find_test_files(manifest, tmp_path)
    validate_test_assertions(tmp_path, ["tests/test_shared.py"])

    assert walks == [tmp_path / "tests", tmp_path / "tests"]
    assert len(parsed) == 2
