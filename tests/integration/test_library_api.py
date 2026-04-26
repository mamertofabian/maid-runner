"""Integration tests: MAID Runner v2 library API.

Tests verify the public API surface from maid_runner/__init__.py:
- All public symbols are importable
- Convenience functions (validate, validate_all) work end-to-end
- ManifestChain, ValidationEngine class usage
- load_manifest/save_manifest round-trip
- generate_snapshot
- ValidatorRegistry extension point
- Result types serialization
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# 1. All public symbols importable from top-level
# ---------------------------------------------------------------------------


class TestPublicAPIImports:
    def test_version(self):
        from maid_runner import __version__

        assert isinstance(__version__, str)

    def test_convenience_functions(self):
        from maid_runner import validate, validate_all

        assert callable(validate)
        assert callable(validate_all)

    def test_core_classes(self):
        from maid_runner import (
            ManifestChain,
            ValidationEngine,
            generate_snapshot,
            load_manifest,
            save_manifest,
        )

        assert callable(load_manifest)
        assert callable(save_manifest)
        assert callable(generate_snapshot)
        assert callable(ManifestChain)
        assert callable(ValidationEngine)

    def test_type_imports(self):
        from maid_runner import (
            ArtifactKind,
            ArtifactSpec,
            ArgSpec,
            DeleteSpec,
            FileMode,
            FileSpec,
            Manifest,
            TaskType,
            ValidationMode,
        )

        assert ArtifactKind.FUNCTION.value == "function"
        assert FileMode.CREATE.value == "create"
        assert ValidationMode.BEHAVIORAL.value == "behavioral"
        assert TaskType.FEATURE.value == "feature"
        assert ArtifactSpec is not None
        assert ArgSpec is not None
        assert DeleteSpec is not None
        assert FileSpec is not None
        assert Manifest is not None

    def test_result_imports(self):
        from maid_runner import (
            BatchTestResult,
            BatchValidationResult,
            ErrorCode,
            FileTrackingEntry,
            FileTrackingReport,
            FileTrackingStatus,
            Location,
            Severity,
            TestRunResult,
            ValidationError,
            ValidationResult,
        )

        assert ErrorCode.ARTIFACT_NOT_DEFINED.value == "E300"
        assert Severity.ERROR.value == "error"
        assert FileTrackingStatus.TRACKED.value == "tracked"
        assert BatchTestResult is not None
        assert BatchValidationResult is not None
        assert FileTrackingEntry is not None
        assert FileTrackingReport is not None
        assert Location is not None
        assert TestRunResult is not None
        assert ValidationError is not None
        assert ValidationResult is not None

    def test_validator_imports(self):
        from maid_runner import (
            BaseValidator,
            CollectionResult,
            FoundArtifact,
            UnsupportedLanguageError,
            ValidatorRegistry,
        )

        assert hasattr(ValidatorRegistry, "register")
        assert hasattr(ValidatorRegistry, "get")
        assert hasattr(BaseValidator, "collect_implementation_artifacts")
        assert CollectionResult is not None
        assert FoundArtifact is not None
        assert issubclass(UnsupportedLanguageError, Exception)

    def test_exception_imports(self):
        from maid_runner import ManifestLoadError, ManifestSchemaError

        assert issubclass(ManifestLoadError, Exception)
        assert issubclass(ManifestSchemaError, Exception)

    def test_all_declared_exports_match(self):
        import maid_runner

        declared = set(maid_runner.__all__)
        # Every declared export should be an attribute
        for name in declared:
            assert hasattr(maid_runner, name), f"Missing export: {name}"

    def test_generate_snapshot_is_v2(self):
        from maid_runner import generate_snapshot

        assert generate_snapshot.__module__ == "maid_runner.core.snapshot"

    def test_spec_required_exports_present(self):
        """Every symbol required by 10-public-api.md is importable."""
        import maid_runner

        spec_exports = [
            "__version__",
            "validate",
            "validate_all",
            "ValidationEngine",
            "load_manifest",
            "save_manifest",
            "ManifestChain",
            "generate_snapshot",
            "ArtifactKind",
            "ArtifactSpec",
            "ArgSpec",
            "FileSpec",
            "FileMode",
            "DeleteSpec",
            "Manifest",
            "TaskType",
            "ValidationMode",
            "ValidationResult",
            "BatchValidationResult",
            "ValidationError",
            "ErrorCode",
            "Severity",
            "Location",
            "FileTrackingReport",
            "FileTrackingStatus",
            "FileTrackingEntry",
            "TestRunResult",
            "BatchTestResult",
            "ValidatorRegistry",
            "UnsupportedLanguageError",
            "BaseValidator",
            "FoundArtifact",
            "CollectionResult",
            "ManifestLoadError",
            "ManifestSchemaError",
        ]
        for name in spec_exports:
            assert hasattr(maid_runner, name), f"Spec-required export missing: {name}"
            assert (
                name in maid_runner.__all__
            ), f"Spec-required export not in __all__: {name}"


# ---------------------------------------------------------------------------
# 2. validate() convenience function
# ---------------------------------------------------------------------------


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


def _add_test_file(project_dir, test_rel_path, source_module, artifact_names):
    """Write a minimal test file that references the given artifacts."""
    public_names = [n for n in artifact_names if not n.startswith("_")]
    if not public_names:
        public_names = artifact_names
    imports = ", ".join(public_names)
    tests = "\n".join(
        f"def test_{n}():\n    assert {n} is not None\n" for n in public_names
    )
    content = f"from {source_module} import {imports}\n\n{tests}\n"
    path = project_dir / test_rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return test_rel_path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    return tmp_path


class TestValidateConvenience:
    def test_validate_returns_result(self, project: Path):
        from maid_runner import ValidationResult, validate

        manifest_path = project / "manifests" / "add-foo.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add foo",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/foo.py",
                            "artifacts": [{"kind": "function", "name": "foo"}],
                        }
                    ],
                    "read": ["tests/test_foo.py"],
                },
                "validate": ["pytest tests/test_foo.py -v"],
            },
        )
        (project / "src" / "foo.py").write_text("def foo(): pass\n")
        _add_test_file(project, "tests/test_foo.py", "src.foo", ["foo"])

        result = validate(
            str(manifest_path), use_chain=False, project_root=str(project)
        )

        assert isinstance(result, ValidationResult)
        assert result.success is True
        assert result.manifest_slug == "add-foo"
        assert result.duration_ms is not None
        assert result.duration_ms >= 0

    def test_validate_never_raises_on_validation_failure(self, project: Path):
        from maid_runner import validate

        manifest_path = project / "manifests" / "add-foo.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add foo",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/foo.py",
                            "artifacts": [{"kind": "function", "name": "foo"}],
                        }
                    ]
                },
                "validate": ["pytest tests/ -v"],
            },
        )
        (project / "src" / "foo.py").write_text("# empty\n")

        # Should NOT raise, per error handling contract
        result = validate(
            str(manifest_path), use_chain=False, project_root=str(project)
        )
        assert result.success is False
        assert len(result.errors) > 0


# ---------------------------------------------------------------------------
# 3. validate_all() convenience function
# ---------------------------------------------------------------------------


class TestValidateAllConvenience:
    def test_validate_all_returns_batch_result(self, project: Path):
        from maid_runner import BatchValidationResult, validate_all

        _write_yaml(
            project / "manifests" / "a.manifest.yaml",
            {
                "schema": "2",
                "goal": "Add a",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/a.py",
                            "artifacts": [{"kind": "function", "name": "a"}],
                        }
                    ],
                    "read": ["tests/test_a.py"],
                },
                "validate": ["pytest tests/test_a.py -v"],
            },
        )
        (project / "src" / "a.py").write_text("def a(): pass\n")
        _add_test_file(project, "tests/test_a.py", "src.a", ["a"])

        batch = validate_all("manifests/", project_root=str(project))

        assert isinstance(batch, BatchValidationResult)
        assert batch.success is True
        assert batch.passed >= 1
        assert batch.failed == 0

    def test_validate_all_empty_dir(self, project: Path):
        from maid_runner import validate_all

        batch = validate_all("manifests/", project_root=str(project))

        assert batch.total_manifests == 0
        assert batch.passed == 0


# ---------------------------------------------------------------------------
# 4. ManifestChain class usage
# ---------------------------------------------------------------------------


class TestManifestChainAPI:
    def test_chain_api(self, project: Path):
        from maid_runner import ManifestChain

        _write_yaml(
            project / "manifests" / "base.manifest.yaml",
            {
                "schema": "2",
                "goal": "Base",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/svc.py",
                            "artifacts": [{"kind": "class", "name": "Svc"}],
                        }
                    ]
                },
                "validate": ["pytest tests/ -v"],
                "created": "2025-01-01T00:00:00Z",
            },
        )

        chain = ManifestChain(str(project / "manifests"), str(project))

        active = chain.active_manifests()
        assert len(active) == 1
        assert active[0].slug == "base"
        assert active[0].goal == "Base"

        artifacts = chain.merged_artifacts_for("src/svc.py")
        assert len(artifacts) == 1
        assert artifacts[0].name == "Svc"


# ---------------------------------------------------------------------------
# 5. ValidationEngine class usage
# ---------------------------------------------------------------------------


class TestValidationEngineAPI:
    def test_engine_validate(self, project: Path):
        from maid_runner import ValidationEngine, ValidationMode

        manifest_path = project / "manifests" / "add-bar.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add bar",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/bar.py",
                            "artifacts": [{"kind": "function", "name": "bar"}],
                        }
                    ],
                    "read": ["tests/test_bar.py"],
                },
                "validate": ["pytest tests/test_bar.py -v"],
            },
        )
        (project / "src" / "bar.py").write_text("def bar(): pass\n")
        _add_test_file(project, "tests/test_bar.py", "src.bar", ["bar"])

        engine = ValidationEngine(project_root=project)
        result = engine.validate(str(manifest_path), use_chain=False)

        assert result.success is True
        assert result.mode == ValidationMode.IMPLEMENTATION


# ---------------------------------------------------------------------------
# 6. load_manifest / save_manifest round-trip
# ---------------------------------------------------------------------------


class TestManifestRoundTrip:
    def test_load_save_load_preserves_data(self, project: Path):
        from maid_runner import load_manifest, save_manifest

        src = project / "manifests" / "test.manifest.yaml"
        _write_yaml(
            src,
            {
                "schema": "2",
                "goal": "Test round-trip",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/rt.py",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "rt_func",
                                    "args": [{"name": "x", "type": "int"}],
                                    "returns": "str",
                                }
                            ],
                        }
                    ],
                    "read": ["tests/test_rt.py"],
                },
                "validate": ["pytest tests/ -v"],
                "created": "2025-06-15T10:30:00Z",
            },
        )

        original = load_manifest(src)

        dst = project / "manifests" / "copy.manifest.yaml"
        save_manifest(original, dst)

        reloaded = load_manifest(dst)

        assert reloaded.goal == original.goal
        assert reloaded.task_type == original.task_type
        assert len(reloaded.all_file_specs) == len(original.all_file_specs)

        orig_artifacts = original.all_file_specs[0].artifacts
        copy_artifacts = reloaded.all_file_specs[0].artifacts
        assert len(copy_artifacts) == len(orig_artifacts)
        assert copy_artifacts[0].name == orig_artifacts[0].name
        assert copy_artifacts[0].args == orig_artifacts[0].args
        assert copy_artifacts[0].returns == orig_artifacts[0].returns

    def test_load_nonexistent_raises(self):
        from maid_runner import ManifestLoadError, load_manifest

        with pytest.raises(ManifestLoadError):
            load_manifest("/nonexistent/path.manifest.yaml")

    def test_load_invalid_schema_raises(self, project: Path):
        from maid_runner import ManifestSchemaError, load_manifest

        bad = project / "manifests" / "bad.manifest.yaml"
        _write_yaml(bad, {"schema": "2", "files": {"create": []}})

        with pytest.raises(ManifestSchemaError):
            load_manifest(bad)


# ---------------------------------------------------------------------------
# 7. generate_snapshot
# ---------------------------------------------------------------------------


class TestGenerateSnapshotAPI:
    def test_generate_snapshot_from_source(self, project: Path):
        from maid_runner.core.snapshot import generate_snapshot

        (project / "src" / "calc.py").write_text(
            textwrap.dedent(
                """\
                def add(a: int, b: int) -> int:
                    return a + b

                class Calculator:
                    def multiply(self, a: int, b: int) -> int:
                        return a * b
            """
            )
        )

        manifest = generate_snapshot(
            str(project / "src" / "calc.py"),
            project_root=str(project),
        )

        assert manifest.task_type.value == "snapshot"
        names = {a.name for fs in manifest.all_file_specs for a in fs.artifacts}
        assert "add" in names
        assert "Calculator" in names
        assert "multiply" in names


# ---------------------------------------------------------------------------
# 8. ValidatorRegistry extension
# ---------------------------------------------------------------------------


class TestValidatorRegistryExtension:
    def test_has_validator_for_python(self):
        from maid_runner import ValidatorRegistry

        registry = ValidatorRegistry.with_builtin_validators()
        assert registry.has_validator("foo.py") is True

    def test_no_validator_for_unknown(self):
        from maid_runner import UnsupportedLanguageError, ValidatorRegistry

        registry = ValidatorRegistry.with_builtin_validators()
        with pytest.raises(UnsupportedLanguageError):
            registry.get("foo.unknown_ext")

    def test_register_custom_validator(self):
        from maid_runner import (
            BaseValidator,
            CollectionResult,
            ValidatorRegistry,
        )

        class RubyValidator(BaseValidator):
            @classmethod
            def supported_extensions(cls):
                return (".rb",)

            def collect_implementation_artifacts(self, source, file_path):
                return CollectionResult(
                    artifacts=[], language="ruby", file_path=str(file_path)
                )

            def collect_behavioral_artifacts(self, source, file_path):
                return CollectionResult(
                    artifacts=[], language="ruby", file_path=str(file_path)
                )

        registry = ValidatorRegistry.with_builtin_validators()
        registry.register(RubyValidator)
        assert registry.has_validator("test.rb") is True
        validator = registry.get("test.rb")
        assert isinstance(validator, RubyValidator)

    def test_engine_can_use_isolated_registry(self, project: Path):
        from maid_runner import (
            ArtifactKind,
            BaseValidator,
            CollectionResult,
            FoundArtifact,
            ValidationEngine,
            ValidatorRegistry,
        )

        class RubyValidator(BaseValidator):
            @classmethod
            def supported_extensions(cls):
                return (".rb",)

            def collect_implementation_artifacts(self, source, file_path):
                return CollectionResult(
                    artifacts=[
                        FoundArtifact(
                            kind=ArtifactKind.FUNCTION,
                            name="helper",
                        )
                    ],
                    language="ruby",
                    file_path=str(file_path),
                )

            def collect_behavioral_artifacts(self, source, file_path):
                return CollectionResult(
                    artifacts=[], language="ruby", file_path=str(file_path)
                )

        manifest_path = project / "manifests" / "add-ruby.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add ruby",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/helper.rb",
                            "artifacts": [{"kind": "function", "name": "helper"}],
                        }
                    ],
                    "read": ["tests/test_helper.py"],
                },
                "validate": ["true"],
            },
        )
        (project / "src" / "helper.rb").write_text("def helper\n  :ok\nend\n")
        (project / "tests" / "test_helper.py").write_text(
            "from src.helper import helper\n"
        )

        registry = ValidatorRegistry.with_builtin_validators()
        registry.register(RubyValidator)

        isolated_engine = ValidationEngine(project_root=project, registry=registry)
        isolated = isolated_engine.validate(str(manifest_path), use_chain=False)
        assert isolated.success is True
        assert not isolated.warnings

        default_engine = ValidationEngine(project_root=project)
        default = default_engine.validate(str(manifest_path), use_chain=False)
        assert any(w.code.value == "E307" for w in default.warnings)


# ---------------------------------------------------------------------------
# 9. JSON output contract
# ---------------------------------------------------------------------------


class TestJSONOutputContract:
    def test_validation_result_json_structure(self, project: Path):
        import json

        from maid_runner import validate

        manifest_path = project / "manifests" / "add-q.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add q",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/q.py",
                            "artifacts": [{"kind": "function", "name": "q"}],
                        }
                    ]
                },
                "validate": ["pytest tests/ -v"],
            },
        )
        (project / "src" / "q.py").write_text("def q(): pass\n")

        result = validate(
            str(manifest_path), use_chain=False, project_root=str(project)
        )
        json_str = result.to_json()
        data = json.loads(json_str)

        assert "success" in data
        assert "manifest" in data
        assert "mode" in data
        assert "errors" in data
        assert "warnings" in data

    def test_batch_result_to_dict(self, project: Path):
        from maid_runner import validate_all

        _write_yaml(
            project / "manifests" / "a.manifest.yaml",
            {
                "schema": "2",
                "goal": "A",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/a.py",
                            "artifacts": [{"kind": "function", "name": "a"}],
                        }
                    ]
                },
                "validate": ["pytest tests/ -v"],
            },
        )
        (project / "src" / "a.py").write_text("def a(): pass\n")

        batch = validate_all("manifests/", project_root=str(project))
        data = batch.to_dict()

        assert "success" in data
        assert "total" in data
        assert "passed" in data
        assert "failed" in data
        assert "skipped" in data
        assert "results" in data
        assert isinstance(data["results"], list)
