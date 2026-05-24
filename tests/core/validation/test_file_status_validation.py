"""Focused characterization tests for file status validation."""

import pytest

from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine


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


def file_should_be_absent_errors(result):
    return [
        error
        for error in result.errors
        if error.code == ErrorCode.FILE_SHOULD_BE_ABSENT
    ]


def validator_not_available_warnings(result):
    return [
        warning
        for warning in result.warnings
        if warning.code == ErrorCode.VALIDATOR_NOT_AVAILABLE
    ]


def validator_not_available_issues(result):
    return [
        issue
        for issue in result.errors + result.warnings
        if issue.code == ErrorCode.VALIDATOR_NOT_AVAILABLE
    ]


def write_delete_manifest(project, name="remove-mod.manifest.yaml", reason=None):
    reason_line = f'      reason: "{reason}"\n' if reason else ""
    return write_manifest(
        project,
        name,
        f"""schema: "2"
goal: "Remove module"
type: refactor
files:
  delete:
    - path: src/old.py
{reason_line}validate:
  - echo ok
""",
    )


def test_delete_file_that_still_exists_reports_file_should_be_absent(project):
    manifest_path = write_delete_manifest(project)
    write_source(project, "src/old.py", "# should be deleted\n")

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is False
    assert len(file_should_be_absent_errors(result)) == 1


def test_delete_file_that_is_missing_reports_no_file_should_be_absent_error(project):
    manifest_path = write_delete_manifest(project)

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert file_should_be_absent_errors(result) == []


def test_delete_file_with_reason_that_still_exists_reports_file_should_be_absent(
    project,
):
    manifest_path = write_delete_manifest(
        project, reason="Migrated to new architecture"
    )
    write_source(project, "src/old.py", "# should be deleted\n")

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is False
    assert len(file_should_be_absent_errors(result)) == 1


def test_delete_file_with_reason_that_is_missing_reports_no_file_should_be_absent_error(
    project,
):
    manifest_path = write_delete_manifest(
        project, reason="Migrated to new architecture"
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert file_should_be_absent_errors(result) == []


def test_unsupported_language_file_reports_validator_not_available_warning(project):
    manifest_path = write_manifest(
        project,
        "add-ruby.manifest.yaml",
        """schema: "2"
goal: "Add ruby module"
files:
  create:
    - path: src/helper.rb
      artifacts:
        - kind: function
          name: helper
  read:
    - tests/test_helper.py
validate:
  - pytest tests/test_helper.py -v
""",
    )
    write_source(project, "src/helper.rb", "def helper\n  'hello'\nend\n")
    write_source(
        project,
        "tests/test_helper.py",
        "from src.helper import helper\n\n"
        "def test_helper():\n"
        "    assert helper is not None\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert len(validator_not_available_warnings(result)) == 1


def test_supported_python_file_reports_no_validator_not_available_warning(project):
    manifest_path = write_manifest(
        project,
        "add-py.manifest.yaml",
        """schema: "2"
goal: "Add python module"
files:
  create:
    - path: src/mod.py
      artifacts:
        - kind: function
          name: helper
validate:
  - pytest tests/ -v
""",
    )
    write_source(project, "src/mod.py", "def helper():\n    pass\n")

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert validator_not_available_warnings(result) == []


def test_unsupported_language_file_reports_validator_not_available_issue_without_test_file(
    project,
):
    manifest_path = write_manifest(
        project,
        "add-config.manifest.yaml",
        """schema: "2"
goal: "Add config"
type: feature
files:
  create:
    - path: src/config.rb
      artifacts:
        - kind: function
          name: load_config
validate:
  - echo ok
""",
    )
    write_source(project, "src/config.rb", "def load_config\n  nil\nend\n")

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert len(validator_not_available_issues(result)) == 1
