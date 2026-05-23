"""Tests for validation test discovery and artifact collection helpers."""

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ArtifactKind
from maid_runner.core._validation_test_artifacts import (
    collect_test_artifacts,
    collection_errors_to_validation_errors,
    find_test_files,
    get_validator_for_test,
)
from maid_runner.validators.base import BaseValidator, CollectionResult, FoundArtifact
from maid_runner.validators.registry import ValidatorRegistry


def _write(path, content=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


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


def test_collect_test_artifacts_uses_cached_behavioral_collection(tmp_path):
    class CountingValidator(BaseValidator):
        calls = 0

        @classmethod
        def supported_extensions(cls) -> tuple[str, ...]:
            return (".ts",)

        def collect_implementation_artifacts(self, source, file_path):
            return CollectionResult([], "typescript", str(file_path))

        def collect_behavioral_artifacts(self, source, file_path):
            type(self).calls += 1
            return CollectionResult(
                [FoundArtifact(kind=ArtifactKind.FUNCTION, name="example")],
                "typescript",
                str(file_path),
            )

    _write(tmp_path / "tests" / "example.test.ts", "example")
    registry = ValidatorRegistry()
    registry.register(CountingValidator)
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
