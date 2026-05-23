"""Tests for validation test discovery and artifact collection helpers."""

from pathlib import Path

import pytest

from maid_runner.core._artifact_collection_cache import clear_artifact_collection_cache
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode, Severity
from maid_runner.core.types import ArtifactKind
from maid_runner.core._validation_test_artifacts import (
    TestArtifactsTable,
    clear_test_artifact_cache,
    collect_test_artifacts,
    collection_errors_to_validation_errors,
    find_test_files,
    get_cached_test_artifacts,
    get_validator_for_test,
)
from maid_runner.validators.base import BaseValidator, CollectionResult, FoundArtifact
from maid_runner.validators.registry import ValidatorRegistry


class CountingValidator(BaseValidator):
    calls = 0

    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".ts",)

    @classmethod
    def reset(cls) -> None:
        cls.calls = 0

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult([], "typescript", str(file_path))

    def collect_behavioral_artifacts(self, source, file_path):
        type(self).calls += 1
        name = source.strip().split(maxsplit=1)[0]
        return CollectionResult(
            [FoundArtifact(kind=ArtifactKind.FUNCTION, name=name)],
            "typescript",
            str(file_path),
        )


@pytest.fixture(autouse=True)
def clear_caches():
    clear_artifact_collection_cache()
    CountingValidator.reset()
    yield
    clear_artifact_collection_cache()
    CountingValidator.reset()


def _write(path, content=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _count_reads(monkeypatch, target_path: Path) -> list[Path]:
    reads: list[Path] = []
    real_read_text = Path.read_text

    def counting_read_text(self, *args, **kwargs):
        if self == target_path:
            reads.append(self)
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)
    return reads


def _counting_registry() -> ValidatorRegistry:
    registry = ValidatorRegistry()
    registry.register(CountingValidator)
    return registry


def test_find_test_files_includes_files_read_and_validate_commands(tmp_path):
    manifest_path = _write(
        tmp_path / "manifests" / "test-discovery.manifest.yaml",
        """schema: "2"
goal: "Discover tests"
files:
  edit:
    - path: src/example.py
      artifacts:
        - kind: function
          name: example
  read:
    - tests/test_from_read.py
    - tests/unit
validate:
  - pytest tests/test_from_validate.py tests/feature -v
""",
    )
    _write(tmp_path / "tests" / "test_from_read.py")
    _write(tmp_path / "tests" / "unit" / "test_nested.py")
    _write(tmp_path / "tests" / "unit" / "helper.py")
    _write(tmp_path / "tests" / "test_from_validate.py")
    _write(tmp_path / "tests" / "feature" / "test_feature.py")

    manifest = load_manifest(manifest_path)

    assert find_test_files(manifest, tmp_path) == [
        "tests/test_from_read.py",
        "tests/unit/test_nested.py",
        "tests/test_from_validate.py",
        "tests/feature/test_feature.py",
    ]


def test_find_test_files_respects_cd_without_scanning_working_directory(tmp_path):
    manifest_path = _write(
        tmp_path / "manifests" / "frontend.manifest.yaml",
        """schema: "2"
goal: "Discover scoped frontend tests"
files:
  edit:
    - path: apps/frontend/src/example.ts
      artifacts:
        - kind: function
          name: example
validate:
  - cd apps/frontend && pnpm vitest run src/current.test.ts
""",
    )
    _write(tmp_path / "apps" / "frontend" / "src" / "current.test.ts")
    _write(tmp_path / "apps" / "frontend" / "src" / "unrelated.test.ts")

    manifest = load_manifest(manifest_path)

    assert find_test_files(manifest, tmp_path) == [
        "apps/frontend/src/current.test.ts",
    ]


def test_find_test_files_includes_explicit_vitest_directory_target(tmp_path):
    manifest_path = _write(
        tmp_path / "manifests" / "frontend-dir.manifest.yaml",
        """schema: "2"
goal: "Discover explicit frontend test directory"
files:
  edit:
    - path: apps/frontend/src/example.ts
      artifacts:
        - kind: function
          name: example
validate:
  - cd apps/frontend && pnpm vitest run src/lib/audio/components/voice
""",
    )
    _write(
        tmp_path
        / "apps"
        / "frontend"
        / "src"
        / "lib"
        / "audio"
        / "components"
        / "voice"
        / "voiceUpload.test.ts"
    )

    manifest = load_manifest(manifest_path)

    assert find_test_files(manifest, tmp_path) == [
        "apps/frontend/src/lib/audio/components/voice/voiceUpload.test.ts",
    ]


def test_collect_test_artifacts_excludes_test_function_declarations(tmp_path):
    test_path = tmp_path / "tests" / "test_widget.py"
    _write(
        test_path,
        "from src.widget import render\n\n"
        "def test_render():\n"
        "    assert render() is None\n",
    )
    registry = ValidatorRegistry.with_builtin_validators()
    errors = []

    artifacts = collect_test_artifacts(
        ["tests/test_widget.py"], tmp_path, registry, errors
    )

    assert errors == []
    assert get_validator_for_test("tests/test_widget.py", registry) is not None
    assert "tests/test_widget.py" in artifacts
    assert {artifact.name for artifact in artifacts["tests/test_widget.py"]} >= {
        "render"
    }
    assert all(
        artifact.kind.value != "test_function"
        for artifact in artifacts["tests/test_widget.py"]
    )


def test_collect_test_artifacts_converts_parse_errors_to_validation_errors(tmp_path):
    _write(tmp_path / "tests" / "test_broken.py", "def test_broken(:\n    pass\n")
    errors = []

    artifacts = collect_test_artifacts(
        ["tests/test_broken.py"],
        tmp_path,
        ValidatorRegistry.with_builtin_validators(),
        errors,
    )

    assert artifacts == {}
    assert [error.code for error in errors] == [ErrorCode.SOURCE_PARSE_ERROR]
    assert errors[0].location.file == "tests/test_broken.py"
    assert errors[0].location.line == 1

    converted = collection_errors_to_validation_errors(
        ["SyntaxError on line 9: invalid syntax"],
        "tests/test_broken.py",
    )
    assert [error.code for error in converted] == [ErrorCode.SOURCE_PARSE_ERROR]
    assert converted[0].location.file == "tests/test_broken.py"
    assert converted[0].location.line == 9


def test_get_cached_test_artifacts_rewrites_parse_error_locations_per_request(
    tmp_path,
):
    _write(tmp_path / "tests" / "test_broken.py", "def test_broken(:\n    pass\n")
    registry = ValidatorRegistry.with_builtin_validators()

    first = get_cached_test_artifacts("./tests/test_broken.py", tmp_path, registry)
    second = get_cached_test_artifacts("tests/test_broken.py", tmp_path, registry)

    assert first is not None
    assert second is not None
    assert [error.code for error in first.errors] == [ErrorCode.SOURCE_PARSE_ERROR]
    assert [error.code for error in second.errors] == [ErrorCode.SOURCE_PARSE_ERROR]
    assert first.errors[0].location.file == "./tests/test_broken.py"
    assert second.errors[0].location.file == "tests/test_broken.py"


def test_collect_test_artifacts_uses_cached_behavioral_collection(tmp_path):
    _write(tmp_path / "tests" / "example.test.ts", "example")
    registry = _counting_registry()
    errors = []

    first = collect_test_artifacts(
        ["tests/example.test.ts"],
        tmp_path,
        registry,
        errors,
    )
    second = collect_test_artifacts(
        ["tests/example.test.ts"],
        tmp_path,
        registry,
        errors,
    )

    assert errors == []
    assert CountingValidator.calls == 1
    assert first == second


def test_get_cached_test_artifacts_returns_same_table_within_invocation(
    monkeypatch,
    tmp_path,
):
    test_path = _write(tmp_path / "tests" / "example.test.ts", "example")
    reads = _count_reads(monkeypatch, test_path)

    first = get_cached_test_artifacts(
        "tests/example.test.ts",
        tmp_path,
        _counting_registry(),
    )
    second = get_cached_test_artifacts(
        "tests/example.test.ts",
        tmp_path,
        _counting_registry(),
    )

    assert isinstance(first, TestArtifactsTable)
    assert second is first
    assert [artifact.name for artifact in first.artifacts] == ["example"]
    assert len(reads) == 1
    assert CountingValidator.calls == 1


def test_get_cached_test_artifacts_invalidates_on_signature_change(tmp_path):
    test_path = _write(tmp_path / "tests" / "example.test.ts", "example")
    registry = _counting_registry()

    first = get_cached_test_artifacts("tests/example.test.ts", tmp_path, registry)
    test_path.write_text("changed_name")
    second = get_cached_test_artifacts("tests/example.test.ts", tmp_path, registry)

    assert first is not None
    assert second is not None
    assert second is not first
    assert [artifact.name for artifact in first.artifacts] == ["example"]
    assert [artifact.name for artifact in second.artifacts] == ["changed_name"]
    assert CountingValidator.calls == 2


def test_collect_test_artifacts_reuses_cache_across_manifests(monkeypatch, tmp_path):
    test_path = _write(tmp_path / "tests" / "example.test.ts", "example")
    reads = _count_reads(monkeypatch, test_path)
    registry = _counting_registry()
    errors = []

    first = collect_test_artifacts(
        ["tests/example.test.ts"],
        tmp_path,
        registry,
        errors,
    )
    second = collect_test_artifacts(
        ["tests/example.test.ts"],
        tmp_path,
        registry,
        errors,
    )

    assert errors == []
    assert first == second
    assert [artifact.name for artifact in first["tests/example.test.ts"]] == ["example"]
    assert len(reads) == 1
    assert CountingValidator.calls == 1


def test_clear_test_artifact_cache_drops_all_entries(monkeypatch, tmp_path):
    first_path = _write(tmp_path / "tests" / "first.test.ts", "first")
    second_path = _write(tmp_path / "tests" / "second.test.ts", "second")
    first_reads = _count_reads(monkeypatch, first_path)
    second_reads = _count_reads(monkeypatch, second_path)
    registry = _counting_registry()

    get_cached_test_artifacts("tests/first.test.ts", tmp_path, registry)
    get_cached_test_artifacts("tests/second.test.ts", tmp_path, registry)
    clear_test_artifact_cache()
    get_cached_test_artifacts("tests/first.test.ts", tmp_path, registry)
    get_cached_test_artifacts("tests/second.test.ts", tmp_path, registry)

    assert len(first_reads) == 2
    assert len(second_reads) == 2
    assert CountingValidator.calls == 2


def test_clear_artifact_collection_cache_drops_test_artifact_tables(tmp_path):
    _write(tmp_path / "tests" / "example.test.ts", "example")
    registry = _counting_registry()

    get_cached_test_artifacts("tests/example.test.ts", tmp_path, registry)
    clear_artifact_collection_cache()
    get_cached_test_artifacts("tests/example.test.ts", tmp_path, registry)

    assert CountingValidator.calls == 2


def test_collect_test_artifacts_propagates_file_read_errors(monkeypatch, tmp_path):
    test_path = _write(tmp_path / "tests" / "example.test.ts", "example")
    real_read_text = Path.read_text

    def unreadable_test_file(self, *args, **kwargs):
        if self == test_path:
            raise OSError("permission denied")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unreadable_test_file)
    table = get_cached_test_artifacts(
        "tests/example.test.ts",
        tmp_path,
        _counting_registry(),
    )
    errors = []

    artifacts = collect_test_artifacts(
        ["tests/example.test.ts"],
        tmp_path,
        _counting_registry(),
        errors,
    )

    assert table is not None
    assert [error.code for error in table.errors] == [ErrorCode.FILE_READ_ERROR]
    assert artifacts == {}
    assert [error.code for error in errors] == [ErrorCode.FILE_READ_ERROR]
    assert errors[0].severity == Severity.ERROR
    assert errors[0].location.file == "tests/example.test.ts"
