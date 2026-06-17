"""ValidationEngine coverage for validator plugin diagnostics."""

from __future__ import annotations

import importlib.metadata

from maid_runner.core.result import ErrorCode, Severity
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine
from maid_runner.validators.base import BaseValidator, CollectionResult

ENTRY_POINT_GROUP = "maid_runner.validators"


class _ConflictingPythonValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".py",)

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult(
            artifacts=[], language="python-plugin", file_path=str(file_path)
        )

    def collect_behavioral_artifacts(self, source, file_path):
        return CollectionResult(
            artifacts=[], language="python-plugin", file_path=str(file_path)
        )


class _FakeDistribution:
    name = "maid-validator-python"
    version = "1.0.0"
    metadata = {"Name": name}


class _FakeEntryPoint:
    name = "python"
    group = ENTRY_POINT_GROUP
    value = "maid_validator_python:PythonValidator"
    dist = _FakeDistribution()

    def load(self):
        return _ConflictingPythonValidator


class _FakeEntryPoints(tuple):
    def select(self, *, group: str | None = None):
        if group is None:
            return self
        return type(self)(ep for ep in self if ep.group == group)


def _patch_conflicting_plugin(monkeypatch) -> None:
    entry_points = _FakeEntryPoints([_FakeEntryPoint()])

    def entry_points_lookup(*, group: str | None = None):
        if group is None:
            return entry_points
        return entry_points.select(group=group)

    monkeypatch.setattr(importlib.metadata, "entry_points", entry_points_lookup)


def _write_manifest(project, name, source_name):
    manifest_path = project / "manifests" / name
    manifest_path.write_text(
        f"""schema: "2"
goal: "Validate plugin diagnostics"
type: feature
created: "2026-06-18T00:00:00Z"
files:
  create:
    - path: src/{source_name}.py
      artifacts:
        - kind: function
          name: greet
  read:
    - tests/test_{source_name}.py
validate:
  - pytest tests/test_{source_name}.py -v
"""
    )
    return manifest_path


def _write_source_and_test(project, source_name):
    source_path = project / "src" / f"{source_name}.py"
    test_path = project / "tests" / f"test_{source_name}.py"
    source_path.write_text("def greet():\n    return 'hello'\n")
    test_path.write_text(
        f"from src.{source_name} import greet\n\n"
        "def test_greet_exists():\n"
        "    assert greet() == 'hello'\n"
    )


def _project(tmp_path):
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    return tmp_path


def _plugin_warning_codes(result):
    return [
        warning.code
        for warning in result.warnings
        if warning.code
        in {
            ErrorCode.VALIDATOR_PLUGIN_LOAD_FAILURE,
            ErrorCode.VALIDATOR_PLUGIN_CONFLICT,
        }
    ]


def test_validate_surfaces_plugin_diagnostics_for_behavioral_validation(
    tmp_path,
    monkeypatch,
):
    assert ValidationEngine.validate
    _patch_conflicting_plugin(monkeypatch)
    project = _project(tmp_path)
    manifest_path = _write_manifest(project, "greet.manifest.yaml", "greet")
    _write_source_and_test(project, "greet")

    result = ValidationEngine(project_root=project).validate(
        manifest_path,
        mode=ValidationMode.BEHAVIORAL,
    )

    assert result.success is True
    assert _plugin_warning_codes(result) == [ErrorCode.VALIDATOR_PLUGIN_CONFLICT]
    assert result.warnings[-1].severity == Severity.WARNING


def test_validate_surfaces_plugin_diagnostics_for_implementation_validation(
    tmp_path,
    monkeypatch,
):
    _patch_conflicting_plugin(monkeypatch)
    project = _project(tmp_path)
    manifest_path = _write_manifest(project, "greet.manifest.yaml", "greet")
    _write_source_and_test(project, "greet")

    result = ValidationEngine(project_root=project).validate(
        manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
    )

    assert result.success is True
    assert _plugin_warning_codes(result) == [ErrorCode.VALIDATOR_PLUGIN_CONFLICT]


def test_validate_schema_mode_does_not_surface_plugin_diagnostics(
    tmp_path,
    monkeypatch,
):
    _patch_conflicting_plugin(monkeypatch)
    project = _project(tmp_path)
    manifest_path = _write_manifest(project, "greet.manifest.yaml", "greet")

    result = ValidationEngine(project_root=project).validate(
        manifest_path,
        mode=ValidationMode.SCHEMA,
    )

    assert result.success is True
    assert _plugin_warning_codes(result) == []


def test_validate_fail_on_warnings_applies_to_plugin_diagnostics(
    tmp_path,
    monkeypatch,
):
    _patch_conflicting_plugin(monkeypatch)
    project = _project(tmp_path)
    manifest_path = _write_manifest(project, "greet.manifest.yaml", "greet")
    _write_source_and_test(project, "greet")

    result = ValidationEngine(project_root=project).validate(
        manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
        fail_on_warnings=True,
    )

    assert result.success is False
    assert _plugin_warning_codes(result) == [ErrorCode.VALIDATOR_PLUGIN_CONFLICT]


def test_validate_all_surfaces_plugin_diagnostics_once_for_batch(
    tmp_path,
    monkeypatch,
):
    assert ValidationEngine.validate_all
    _patch_conflicting_plugin(monkeypatch)
    project = _project(tmp_path)
    _write_manifest(project, "first.manifest.yaml", "first")
    _write_manifest(project, "second.manifest.yaml", "second")
    _write_source_and_test(project, "first")
    _write_source_and_test(project, "second")

    result = ValidationEngine(project_root=project).validate_all(
        "manifests",
        mode=ValidationMode.IMPLEMENTATION,
    )

    assert result.success is True
    assert [
        error.code
        for error in result.chain_errors
        if error.code == ErrorCode.VALIDATOR_PLUGIN_CONFLICT
    ] == [ErrorCode.VALIDATOR_PLUGIN_CONFLICT]
    assert all(_plugin_warning_codes(manifest) == [] for manifest in result.results)


def test_validate_all_fail_on_warnings_applies_to_batch_plugin_diagnostics(
    tmp_path,
    monkeypatch,
):
    _patch_conflicting_plugin(monkeypatch)
    project = _project(tmp_path)
    _write_manifest(project, "greet.manifest.yaml", "greet")
    _write_source_and_test(project, "greet")

    result = ValidationEngine(project_root=project).validate_all(
        "manifests",
        mode=ValidationMode.IMPLEMENTATION,
        fail_on_warnings=True,
    )

    assert result.success is False
    assert result.failed == 1
    assert [error.severity for error in result.chain_errors] == [Severity.WARNING]
