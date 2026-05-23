from __future__ import annotations

import ast
from pathlib import Path

import pytest

from maid_runner.core._artifact_collection_cache import (
    clear_artifact_collection_cache,
    collect_cached_behavioral_artifacts,
    collect_cached_implementation_artifacts,
    get_cached_test_function_bodies,
)
from maid_runner.core._implementation_validation import ImplementationFileValidator
from maid_runner.core._test_function_contracts import (
    validate_test_function_behavior,
    validate_test_function_names,
)
from maid_runner.core import ts_module_paths
from maid_runner.core.types import (
    ArtifactKind,
    ArtifactSpec,
    FileMode,
    FileSpec,
    Manifest,
    TestFunctionDetails,
    ValidationMode,
)
from maid_runner.core.validate import ValidationEngine, validate_all
from maid_runner.validators.base import BaseValidator, CollectionResult, FoundArtifact
from maid_runner.validators.python import get_cached_python_ast
from maid_runner.validators.registry import ValidatorRegistry


class CountingValidator(BaseValidator):
    implementation_calls = 0
    behavioral_calls = 0
    body_calls = 0

    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".ts", ".svelte")

    @classmethod
    def reset_counts(cls) -> None:
        cls.implementation_calls = 0
        cls.behavioral_calls = 0
        cls.body_calls = 0

    def collect_implementation_artifacts(
        self,
        source: str,
        file_path: str | Path,
    ) -> CollectionResult:
        type(self).implementation_calls += 1
        return CollectionResult(
            artifacts=[FoundArtifact(kind=ArtifactKind.FUNCTION, name=_name(source))],
            language="typescript",
            file_path=str(file_path),
        )

    def collect_behavioral_artifacts(
        self,
        source: str,
        file_path: str | Path,
    ) -> CollectionResult:
        type(self).behavioral_calls += 1
        return CollectionResult(
            artifacts=[FoundArtifact(kind=ArtifactKind.FUNCTION, name=_name(source))],
            language="typescript",
            file_path=str(file_path),
        )

    def get_test_function_bodies(
        self,
        source: str,
        file_path: str | Path,
    ) -> dict[str, str]:
        type(self).body_calls += 1
        return {"test_shared": source}


class TestFunctionCountingValidator(BaseValidator):
    behavioral_calls = 0
    body_calls = 0

    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".ts",)

    @classmethod
    def reset_counts(cls) -> None:
        cls.behavioral_calls = 0
        cls.body_calls = 0

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult([], "typescript", str(file_path))

    def collect_behavioral_artifacts(self, source, file_path):
        type(self).behavioral_calls += 1
        return CollectionResult(
            [FoundArtifact(kind=ArtifactKind.TEST_FUNCTION, name="test_shared")],
            "typescript",
            str(file_path),
        )

    def get_test_function_bodies(self, source, file_path):
        type(self).body_calls += 1
        return {"test_shared": "assert shared is not None"}


def _name(source: str) -> str:
    first = source.strip().split(maxsplit=1)[0]
    return first if first else "shared"


def _registry() -> ValidatorRegistry:
    registry = ValidatorRegistry()
    registry.register(CountingValidator)
    return registry


def _test_function_registry() -> ValidatorRegistry:
    registry = ValidatorRegistry()
    registry.register(TestFunctionCountingValidator)
    return registry


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _write_overlapping_project(project_root: Path) -> None:
    _write(project_root / "src" / "shared.ts", "shared")
    _write(project_root / "tests" / "shared.test.ts", "shared")
    manifests = project_root / "manifests"
    manifests.mkdir()
    for slug in ("first", "second"):
        _write(
            manifests / f"{slug}.manifest.yaml",
            """schema: "2"
goal: "Validate shared TypeScript source"
type: fix
files:
  edit:
    - path: src/shared.ts
      artifacts:
        - kind: function
          name: shared
  read:
    - tests/shared.test.ts
validate:
  - pytest tests/shared.test.ts
""",
        )


def _manifest_for_file_spec(file_spec: FileSpec) -> Manifest:
    return Manifest(
        slug="shared",
        source_path="manifests/shared.manifest.yaml",
        goal="Validate shared artifact",
        validate_commands=(("pytest", "tests/shared.test.ts"),),
        files_edit=(file_spec,),
    )


def _batch_signature(batch) -> dict:
    data = batch.to_dict()
    data.pop("duration_ms", None)
    for result in data["results"]:
        result.pop("duration_ms", None)
    return data


@pytest.fixture(autouse=True)
def clear_caches():
    clear_artifact_collection_cache()
    CountingValidator.reset_counts()
    TestFunctionCountingValidator.reset_counts()
    yield
    clear_artifact_collection_cache()
    CountingValidator.reset_counts()
    TestFunctionCountingValidator.reset_counts()


def test_cached_implementation_collection_reuses_same_typescript_source():
    validator = CountingValidator()

    first = collect_cached_implementation_artifacts(
        validator,
        "shared",
        "src/shared.ts",
    )
    second = collect_cached_implementation_artifacts(
        validator,
        "shared",
        "src/shared.ts",
    )

    assert CountingValidator.implementation_calls == 1
    assert second is first
    assert [artifact.name for artifact in second.artifacts] == ["shared"]


def test_cached_behavioral_collection_reuses_same_svelte_test_source():
    validator = CountingValidator()

    first = collect_cached_behavioral_artifacts(
        validator,
        "shared",
        "src/Shared.test.svelte",
    )
    second = collect_cached_behavioral_artifacts(
        validator,
        "shared",
        "src/Shared.test.svelte",
    )

    assert CountingValidator.behavioral_calls == 1
    assert second is first
    assert [artifact.name for artifact in second.artifacts] == ["shared"]


def test_cached_collection_invalidates_when_source_changes():
    validator = CountingValidator()

    first = collect_cached_implementation_artifacts(
        validator,
        "shared",
        "src/shared.ts",
    )
    second = collect_cached_implementation_artifacts(
        validator,
        "changed",
        "src/shared.ts",
    )

    assert CountingValidator.implementation_calls == 2
    assert [artifact.name for artifact in first.artifacts] == ["shared"]
    assert [artifact.name for artifact in second.artifacts] == ["changed"]


def test_cached_test_function_bodies_reuse_same_source():
    validator = CountingValidator()

    first = get_cached_test_function_bodies(
        validator,
        "expect(shared).toBeDefined()",
        "tests/shared.test.ts",
    )
    second = get_cached_test_function_bodies(
        validator,
        "expect(shared).toBeDefined()",
        "tests/shared.test.ts",
    )

    assert CountingValidator.body_calls == 1
    assert second is first
    assert second == {"test_shared": "expect(shared).toBeDefined()"}


def test_clear_artifact_collection_cache_drops_all_cached_entries():
    validator = CountingValidator()

    collect_cached_implementation_artifacts(validator, "shared", "src/shared.ts")
    collect_cached_behavioral_artifacts(validator, "shared", "tests/shared.test.ts")
    get_cached_test_function_bodies(validator, "shared", "tests/shared.test.ts")
    clear_artifact_collection_cache()
    collect_cached_implementation_artifacts(validator, "shared", "src/shared.ts")
    collect_cached_behavioral_artifacts(validator, "shared", "tests/shared.test.ts")
    get_cached_test_function_bodies(validator, "shared", "tests/shared.test.ts")

    assert CountingValidator.implementation_calls == 2
    assert CountingValidator.behavioral_calls == 2
    assert CountingValidator.body_calls == 2


def test_clear_artifact_collection_cache_drops_python_ast_cache(tmp_path, monkeypatch):
    source_path = tmp_path / "shared.py"
    source_path.write_text("def shared() -> int:\n    return 1\n")
    real_parse = ast.parse
    calls = []

    def counting_parse(source, filename="<unknown>", mode="exec", *args, **kwargs):
        calls.append((source, filename, mode))
        return real_parse(
            source,
            filename=filename,
            mode=mode,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(ast, "parse", counting_parse)

    get_cached_python_ast(source_path)
    get_cached_python_ast(source_path)
    clear_artifact_collection_cache()
    get_cached_python_ast(source_path)

    assert len(calls) == 2


def test_validate_file_spec_routes_collection_through_cache(tmp_path):
    _write(tmp_path / "src" / "shared.ts", "shared")
    file_spec = FileSpec(
        path="src/shared.ts",
        mode=FileMode.EDIT,
        artifacts=(ArtifactSpec(kind=ArtifactKind.FUNCTION, name="shared"),),
    )
    manifest = _manifest_for_file_spec(file_spec)
    validator = ImplementationFileValidator(tmp_path, _registry())

    first_errors = validator.validate_file_spec(file_spec, manifest, chain=None)
    second_errors = validator.validate_file_spec(file_spec, manifest, chain=None)

    assert first_errors == []
    assert second_errors == []
    assert CountingValidator.implementation_calls == 1


def test_validate_test_function_contracts_route_collection_through_cache(tmp_path):
    _write(tmp_path / "tests" / "shared.test.ts", "test_shared uses shared")
    file_spec = FileSpec(
        path="tests/shared.test.ts",
        mode=FileMode.EDIT,
        artifacts=(
            ArtifactSpec(
                kind=ArtifactKind.TEST_FUNCTION,
                name="test_shared",
                test_details=TestFunctionDetails(
                    actions=(
                        {
                            "type": "api_call",
                            "subject": {"export": "shared"},
                        },
                    )
                ),
            ),
        ),
    )
    manifest = _manifest_for_file_spec(file_spec)
    registry = _test_function_registry()

    assert validate_test_function_names(manifest, tmp_path, registry) == []
    assert validate_test_function_names(manifest, tmp_path, registry) == []
    assert validate_test_function_behavior(manifest, tmp_path, registry) == []
    assert validate_test_function_behavior(manifest, tmp_path, registry) == []

    assert TestFunctionCountingValidator.behavioral_calls == 1
    assert TestFunctionCountingValidator.body_calls == 1


def test_validate_all_results_match_with_artifact_collection_cache_enabled(
    monkeypatch,
    tmp_path,
):
    _write_overlapping_project(tmp_path)
    cached = validate_all(
        "manifests",
        mode=ValidationMode.IMPLEMENTATION,
        project_root=tmp_path,
        registry=_registry(),
    )

    from maid_runner.core import _artifact_collection_cache

    monkeypatch.setattr(
        _artifact_collection_cache,
        "collect_cached_implementation_artifacts",
        lambda validator, source, file_path: validator.collect_implementation_artifacts(
            source, file_path
        ),
    )
    monkeypatch.setattr(
        _artifact_collection_cache,
        "collect_cached_behavioral_artifacts",
        lambda validator, source, file_path: validator.collect_behavioral_artifacts(
            source, file_path
        ),
    )
    clear_artifact_collection_cache()
    uncached = validate_all(
        "manifests",
        mode=ValidationMode.IMPLEMENTATION,
        project_root=tmp_path,
        registry=_registry(),
    )

    assert cached.success is True
    assert _batch_signature(cached) == _batch_signature(uncached)


def test_validate_all_reuses_overlapping_typescript_file_collections(tmp_path):
    _write_overlapping_project(tmp_path)

    result = validate_all(
        "manifests",
        mode=ValidationMode.IMPLEMENTATION,
        project_root=tmp_path,
        registry=_registry(),
    )

    assert result.success is True
    assert CountingValidator.implementation_calls == 1
    assert CountingValidator.behavioral_calls == 1


def test_validation_engine_validate_clears_ts_resolution_cache_between_runs(
    monkeypatch,
    tmp_path,
):
    _write(tmp_path / "src" / "example.ts", "export function example() {}\n")
    manifest_path = _write(
        tmp_path / "manifests" / "schema-only.manifest.yaml",
        """schema: "2"
goal: "Schema validation clears caches"
type: snapshot
files:
  snapshot:
    - path: src/example.ts
      artifacts:
        - kind: function
          name: example
validate:
  - pytest tests/example.test.ts
""",
    )
    state = {"target": ("src/old-button", "Button")}

    def compiler_resolver(module, name, root):
        return state["target"]

    ts_module_paths.clear_ts_resolution_cache()
    monkeypatch.setattr(
        ts_module_paths,
        "resolve_reexport_with_compiler",
        compiler_resolver,
    )
    assert ts_module_paths.resolve_ts_reexport(
        "src/components", "Button", tmp_path
    ) == (
        "src/old-button",
        "Button",
    )

    state["target"] = ("src/new-button", "Button")
    engine = ValidationEngine(project_root=tmp_path)
    result = engine.validate(manifest_path, mode=ValidationMode.SCHEMA)

    assert result.success is True
    assert ts_module_paths.resolve_ts_reexport(
        "src/components", "Button", tmp_path
    ) == (
        "src/new-button",
        "Button",
    )


def test_validation_engine_validate_all_clears_ts_resolution_cache_between_runs(
    monkeypatch,
    tmp_path,
):
    _write(tmp_path / "src" / "example.ts", "export function example() {}\n")
    _write(
        tmp_path / "manifests" / "schema-only.manifest.yaml",
        """schema: "2"
goal: "Schema validation clears caches"
type: snapshot
files:
  snapshot:
    - path: src/example.ts
      artifacts:
        - kind: function
          name: example
validate:
  - pytest tests/example.test.ts
""",
    )
    state = {"target": ("src/old-button", "Button")}

    def compiler_resolver(module, name, root):
        return state["target"]

    ts_module_paths.clear_ts_resolution_cache()
    monkeypatch.setattr(
        ts_module_paths,
        "resolve_reexport_with_compiler",
        compiler_resolver,
    )
    assert ts_module_paths.resolve_ts_reexport(
        "src/components", "Button", tmp_path
    ) == (
        "src/old-button",
        "Button",
    )

    state["target"] = ("src/new-button", "Button")
    engine = ValidationEngine(project_root=tmp_path)
    result = engine.validate_all("manifests", mode=ValidationMode.SCHEMA)

    assert result.success is True
    assert ts_module_paths.resolve_ts_reexport(
        "src/components", "Button", tmp_path
    ) == (
        "src/new-button",
        "Button",
    )


def test_validate_all_behavioral_results_match_uncached_test_artifact_tables(
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
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    for slug, goal in (
        ("first", "Validate shared behavior"),
        ("second", "Validate the same shared behavior"),
    ):
        _write(
            manifests / f"{slug}.manifest.yaml",
            f"""schema: "2"
goal: "{goal}"
type: fix
files:
  edit:
    - path: src/shared.py
      artifacts:
        - kind: function
          name: shared
  read:
    - tests/test_shared.py
validate:
  - pytest tests/test_shared.py
""",
        )

    cached = validate_all(
        "manifests",
        mode=ValidationMode.BEHAVIORAL,
        project_root=tmp_path,
    )

    from maid_runner.core import _validation_test_artifacts as test_artifacts

    get_cached = test_artifacts.get_cached_test_artifacts

    def uncached_get_test_artifacts(*args, **kwargs):
        test_artifacts.clear_test_artifact_cache()
        return get_cached(*args, **kwargs)

    monkeypatch.setattr(
        test_artifacts,
        "get_cached_test_artifacts",
        uncached_get_test_artifacts,
    )
    uncached = validate_all(
        "manifests",
        mode=ValidationMode.BEHAVIORAL,
        project_root=tmp_path,
    )

    assert cached.success is True
    assert _batch_signature(cached) == _batch_signature(uncached)
