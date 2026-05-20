"""Focused characterization tests for validate_all manifest-chain behavior."""

import pytest

from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine, validate_all


@pytest.fixture()
def project(tmp_path):
    """Create a temporary project directory."""
    (tmp_path / "src").mkdir()
    (tmp_path / "manifests").mkdir()
    (tmp_path / "tests").mkdir()
    return tmp_path


def write_manifest(project_dir, name, content):
    path = project_dir / "manifests" / name
    path.write_text(content)
    return path


def write_source(project_dir, rel_path, content):
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def write_test(project_dir, rel_path, module, artifact_names):
    imports = ", ".join(artifact_names)
    assertions = "\n".join(
        f"    assert {artifact_name} is not None" for artifact_name in artifact_names
    )
    write_source(
        project_dir,
        rel_path,
        f"from {module} import {imports}\n\n"
        f"def test_declared_artifacts_exist():\n{assertions}\n",
    )


def test_validate_all_validates_active_manifests_and_skips_superseded(project):
    write_manifest(
        project,
        "old-greet.manifest.yaml",
        """schema: "2"
goal: "Old greet"
type: feature
created: "2026-01-01"
files:
  create:
    - path: src/old_greet.py
      artifacts:
        - kind: function
          name: old_greet
  read:
    - tests/test_old_greet.py
validate:
  - pytest tests/test_old_greet.py -v
""",
    )
    write_manifest(
        project,
        "new-greet.manifest.yaml",
        """schema: "2"
goal: "New greet"
type: feature
created: "2026-01-02"
supersedes:
  - old-greet
files:
  create:
    - path: src/new_greet.py
      artifacts:
        - kind: function
          name: new_greet
  read:
    - tests/test_new_greet.py
validate:
  - pytest tests/test_new_greet.py -v
""",
    )
    write_source(project, "src/old_greet.py", "def old_greet():\n    return 'old'\n")
    write_source(project, "src/new_greet.py", "def new_greet():\n    return 'new'\n")
    write_test(project, "tests/test_old_greet.py", "src.old_greet", ["old_greet"])
    write_test(project, "tests/test_new_greet.py", "src.new_greet", ["new_greet"])

    engine = ValidationEngine(project_root=project)
    result = engine.validate_all(mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert result.total_manifests == 2
    assert result.passed == 1
    assert result.failed == 0
    assert result.skipped == 1
    assert [manifest_result.manifest_slug for manifest_result in result.results] == [
        "new-greet"
    ]


def test_validate_all_reports_invalid_manifest_as_chain_error(project):
    write_manifest(
        project,
        "good.manifest.yaml",
        """schema: "2"
goal: "Good"
files:
  create:
    - path: src/good.py
      artifacts:
        - kind: function
          name: good
  read:
    - tests/test_good.py
validate:
  - pytest tests/test_good.py -v
""",
    )
    write_manifest(
        project,
        "bad.manifest.yaml",
        """schema: "2"
goal: "Bad"
files:
  create:
    - path: src/bad.py
validate:
  - pytest
""",
    )
    write_source(project, "src/good.py", "def good():\n    return 'good'\n")
    write_test(project, "tests/test_good.py", "src.good", ["good"])

    engine = ValidationEngine(project_root=project)
    result = engine.validate_all(mode=ValidationMode.IMPLEMENTATION)

    assert result.success is False
    assert result.passed == 1
    assert result.failed == 0
    assert len(result.results) == 1
    assert any(
        error.code == ErrorCode.SCHEMA_VALIDATION_ERROR for error in result.chain_errors
    )


def test_validate_all_missing_manifest_directory_fails_by_default(tmp_path):
    engine = ValidationEngine(project_root=tmp_path)

    result = engine.validate_all("missing-manifests")

    assert result.success is False
    assert result.total_manifests == 0
    assert result.failed == 1
    assert any(
        error.code == ErrorCode.EMPTY_MANIFEST_SET for error in result.chain_errors
    )


def test_validate_all_function_allows_empty_manifest_directory_when_requested(tmp_path):
    (tmp_path / "manifests").mkdir()

    result = validate_all("manifests", project_root=tmp_path, allow_empty=True)

    assert result.success is True
    assert result.total_manifests == 0
    assert result.passed == 0
    assert result.failed == 0
    assert result.chain_errors == []


def test_validate_all_applies_chain_strictness_to_active_manifests(project):
    write_manifest(
        project,
        "create-service.manifest.yaml",
        """schema: "2"
goal: "Create service"
type: feature
created: "2026-01-01"
files:
  create:
    - path: src/service.py
      artifacts:
        - kind: function
          name: func_a
  read:
    - tests/test_service.py
validate:
  - pytest tests/test_service.py -v
""",
    )
    write_manifest(
        project,
        "add-func-b.manifest.yaml",
        """schema: "2"
goal: "Add func_b"
type: feature
created: "2026-01-02"
files:
  edit:
    - path: src/service.py
      artifacts:
        - kind: function
          name: func_b
  read:
    - tests/test_service.py
validate:
  - pytest tests/test_service.py -v
""",
    )
    write_source(
        project,
        "src/service.py",
        "def func_a():\n"
        "    return 'a'\n\n"
        "def func_b():\n"
        "    return 'b'\n\n"
        "def func_c():\n"
        "    return 'c'\n",
    )
    write_test(project, "tests/test_service.py", "src.service", ["func_a", "func_b"])

    engine = ValidationEngine(project_root=project)
    result = engine.validate_all(mode=ValidationMode.IMPLEMENTATION)

    assert result.success is False
    assert result.passed == 0
    assert result.failed == 2
    assert any(
        error.code == ErrorCode.UNEXPECTED_ARTIFACT and "func_c" in error.message
        for manifest_result in result.results
        for error in manifest_result.errors
    )
