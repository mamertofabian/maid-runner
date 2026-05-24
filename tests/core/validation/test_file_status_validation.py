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


def assert_only_manifest_path_outside_project_error(result, location_file):
    assert result.success is False
    assert [error.code for error in result.errors] == [
        ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
    ]
    assert result.errors[0].location is not None
    assert result.errors[0].location.file == location_file


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

    assert result.success is True
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

    assert result.success is True
    assert file_should_be_absent_errors(result) == []


def test_validate_rejects_file_spec_path_that_escapes_project_root(project):
    outside = project.parent / "outside.py"
    outside.write_text("def escaped():\n    return None\n")
    manifest_path = write_manifest(
        project,
        "escaped-file-spec.manifest.yaml",
        """schema: "2"
goal: "Reject escaped file spec"
type: fix
files:
  edit:
    - path: ../outside.py
      artifacts:
        - kind: function
          name: escaped
validate:
  - pytest tests/test_contract.py -v
""",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert_only_manifest_path_outside_project_error(result, "../outside.py")


def test_behavioral_validate_rejects_escaped_test_path_from_files_read(project):
    outside_tests = project.parent / "outside"
    outside_tests.mkdir(exist_ok=True)
    (outside_tests / "test_contract.py").write_text(
        "from src.app import run\n\n" "def test_run():\n" "    assert run is not None\n"
    )
    manifest_path = write_manifest(
        project,
        "escaped-read.manifest.yaml",
        """schema: "2"
goal: "Reject escaped files.read"
type: fix
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: run
  read:
    - ../outside/test_contract.py
validate:
  - pytest tests/test_contract.py -v
""",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.BEHAVIORAL)

    assert_only_manifest_path_outside_project_error(
        result, "../outside/test_contract.py"
    )


def test_validate_rejects_delete_path_that_escapes_project_root(project):
    outside = project.parent / "old.py"
    outside.write_text("# should not be checked through MAID\n")
    manifest_path = write_manifest(
        project,
        "escaped-delete.manifest.yaml",
        """schema: "2"
goal: "Reject escaped delete"
type: fix
files:
  delete:
    - path: ../old.py
      reason: "outside the project"
validate:
  - pytest tests/test_contract.py -v
""",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert_only_manifest_path_outside_project_error(result, "../old.py")
    assert file_should_be_absent_errors(result) == []


def test_behavioral_validate_rejects_escaped_test_path_from_validate_command(project):
    outside_tests = project.parent / "outside"
    outside_tests.mkdir(exist_ok=True)
    (outside_tests / "test_contract.py").write_text(
        "from src.app import run\n\n" "def test_run():\n" "    assert run is not None\n"
    )
    manifest_path = write_manifest(
        project,
        "escaped-validate-command.manifest.yaml",
        """schema: "2"
goal: "Reject escaped validate command test path"
type: fix
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: run
validate:
  - pytest ../outside/test_contract.py -v
""",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.BEHAVIORAL)

    assert_only_manifest_path_outside_project_error(
        result, "../outside/test_contract.py"
    )


def test_behavioral_validate_rejects_escaped_equal_option_path_from_validate_command(
    project,
):
    outside_tests = project.parent / "outside-suite"
    outside_tests.mkdir(exist_ok=True)
    (outside_tests / "test_contract.py").write_text(
        "from src.app import run\n\n" "def test_run():\n" "    assert run is not None\n"
    )
    manifest_path = write_manifest(
        project,
        "escaped-validate-command-option.manifest.yaml",
        """schema: "2"
goal: "Reject escaped validate command option path"
type: fix
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: run
validate:
  - pytest --rootdir=../outside-suite -v
""",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.BEHAVIORAL)

    assert_only_manifest_path_outside_project_error(result, "../outside-suite")


def test_validate_rejects_escaped_acceptance_test_path(project):
    outside_tests = project.parent / "outside"
    outside_tests.mkdir(exist_ok=True)
    (outside_tests / "test_acceptance.py").write_text(
        "def test_acceptance():\n    assert True\n"
    )
    write_source(project, "src/app.py", "def run():\n    return None\n")
    manifest_path = write_manifest(
        project,
        "escaped-acceptance.manifest.yaml",
        """schema: "2"
goal: "Reject escaped acceptance"
type: fix
files:
  edit:
    - path: src/app.py
      artifacts:
        - kind: function
          name: run
acceptance:
  tests:
    - pytest ../outside/test_acceptance.py -v
validate:
  - pytest tests/test_contract.py -v
""",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert_only_manifest_path_outside_project_error(
        result, "../outside/test_acceptance.py"
    )
    assert ErrorCode.ACCEPTANCE_TEST_FILE_NOT_FOUND not in {
        error.code for error in result.errors
    }


def test_validate_rejects_removed_artifact_path_that_escapes_project_root(project):
    outside = project.parent / "outside.py"
    outside.write_text("def removed():\n    return None\n")
    write_source(project, "src/app.py", "def run():\n    return None\n")
    manifest_path = write_manifest(
        project,
        "escaped-removed-artifact.manifest.yaml",
        """schema: "2"
goal: "Reject escaped removed artifact path"
type: fix
removed_artifacts:
  - kind: function
    name: removed
    file: ../outside.py
    reason: "outside project"
files:
  edit:
    - path: src/app.py
      artifacts:
        - kind: function
          name: run
validate:
  - pytest tests/test_contract.py -v
""",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert_only_manifest_path_outside_project_error(result, "../outside.py")
    assert ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT not in {
        error.code for error in result.errors
    }


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
