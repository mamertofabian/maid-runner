"""Schema-only validation mode tests."""

from __future__ import annotations

import pytest
import yaml

from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine, validate_all


def _valid_manifest(**overrides):
    manifest = {
        "schema": "2",
        "goal": "Validate schema only",
        "type": "feature",
        "files": {
            "create": [
                {
                    "path": "src/missing.py",
                    "artifacts": [{"kind": "function", "name": "missing"}],
                }
            ],
            "read": ["tests/test_missing.py"],
        },
        "validate": ["python missing_test_runner.py"],
    }
    manifest.update(overrides)
    return manifest


def test_validation_mode_accepts_schema():
    assert ValidationMode("schema") is ValidationMode.SCHEMA


def test_validation_engine_schema_mode_accepts_valid_manifest_without_source_or_tests(
    tmp_path,
):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    manifest_path = manifest_dir / "schema-only.manifest.yaml"
    manifest_path.write_text(yaml.dump(_valid_manifest()))

    result = ValidationEngine(project_root=tmp_path).validate(
        manifest_path, mode=ValidationMode.SCHEMA
    )

    assert result.success is True
    assert result.mode is ValidationMode.SCHEMA
    assert result.errors == []


def test_validation_engine_schema_mode_reports_schema_errors(tmp_path):
    manifest_path = tmp_path / "invalid.manifest.yaml"
    manifest_path.write_text(yaml.dump({"schema": "2", "type": "feature"}))

    result = ValidationEngine(project_root=tmp_path).validate(
        manifest_path, mode=ValidationMode.SCHEMA
    )

    assert result.success is False
    assert [error.code for error in result.errors] == [
        ErrorCode.SCHEMA_VALIDATION_ERROR
    ]


def test_validation_engine_schema_mode_all_reports_invalid_manifest_load_errors(
    tmp_path,
):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    (manifest_dir / "valid.manifest.yaml").write_text(yaml.dump(_valid_manifest()))
    (manifest_dir / "invalid.manifest.yaml").write_text(
        yaml.dump({"schema": "2", "type": "feature"})
    )

    result = ValidationEngine(project_root=tmp_path).validate_all(
        manifest_dir, mode=ValidationMode.SCHEMA
    )

    assert result.success is False
    assert result.passed == 1
    assert result.failed == 0
    assert [error.code for error in result.chain_errors] == [
        ErrorCode.SCHEMA_VALIDATION_ERROR
    ]


def test_validate_all_function_schema_mode_accepts_valid_manifest_without_source_or_tests(
    tmp_path,
):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    manifest_path = manifest_dir / "schema-only.manifest.yaml"
    manifest_path.write_text(yaml.dump(_valid_manifest()))

    result = validate_all(
        "manifests", project_root=tmp_path, mode=ValidationMode.SCHEMA
    )

    assert result.success is True
    assert result.passed == 1
    assert result.failed == 0
    assert result.chain_errors == []


def test_validation_engine_schema_mode_all_ignores_chain_diagnostics_for_schema_valid_manifests(
    tmp_path,
):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    first = _valid_manifest(goal="First", sequence_number=1)
    second = _valid_manifest(goal="Second", sequence_number=1)
    (manifest_dir / "first.manifest.yaml").write_text(yaml.dump(first))
    (manifest_dir / "second.manifest.yaml").write_text(yaml.dump(second))

    result = ValidationEngine(project_root=tmp_path).validate_all(
        manifest_dir, mode=ValidationMode.SCHEMA
    )

    assert result.success is True
    assert result.passed == 2
    assert result.failed == 0
    assert result.chain_errors == []


def test_validation_engine_schema_mode_all_reports_inactive_active_lifecycle_status(
    tmp_path,
):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    manifest = _valid_manifest(metadata={"status": "planning"})
    (manifest_dir / "schema-only.manifest.yaml").write_text(yaml.dump(manifest))

    result = ValidationEngine(project_root=tmp_path).validate_all(
        manifest_dir, mode=ValidationMode.SCHEMA
    )

    assert result.success is False
    assert result.passed == 1
    assert result.failed == 0
    assert [error.code for error in result.chain_errors] == [
        ErrorCode.ACTIVE_MANIFEST_INACTIVE_STATUS
    ]


@pytest.fixture
def schema_cli_project(tmp_path, monkeypatch):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    manifest_path = manifest_dir / "schema-only.manifest.yaml"
    manifest_path.write_text(yaml.dump(_valid_manifest()))
    monkeypatch.chdir(tmp_path)
    return tmp_path
