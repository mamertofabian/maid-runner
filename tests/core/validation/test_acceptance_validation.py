"""Focused characterization tests for acceptance validation."""

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


def acceptance_file_errors(result):
    return [
        error
        for error in result.errors
        if error.code == ErrorCode.ACCEPTANCE_TEST_FILE_NOT_FOUND
    ]


def test_existing_acceptance_test_file_does_not_report_e500(project):
    manifest_path = write_manifest(
        project,
        "with-acceptance.manifest.yaml",
        """schema: "2"
goal: "Add auth"
files:
  create:
    - path: src/auth.py
      artifacts:
        - kind: class
          name: AuthService
acceptance:
  tests:
    - pytest tests/acceptance/test_auth.py -v
validate:
  - pytest tests/test_auth.py -v
""",
    )
    write_source(project, "src/auth.py", "class AuthService:\n    pass\n")
    write_source(
        project,
        "tests/acceptance/test_auth.py",
        "def test_auth_acceptance():\n    assert True\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert acceptance_file_errors(result) == []


def test_missing_acceptance_test_file_reports_e500(project):
    manifest_path = write_manifest(
        project,
        "with-acceptance.manifest.yaml",
        """schema: "2"
goal: "Add auth"
files:
  create:
    - path: src/auth.py
      artifacts:
        - kind: class
          name: AuthService
acceptance:
  tests:
    - pytest tests/acceptance/test_auth.py -v
validate:
  - pytest tests/test_auth.py -v
""",
    )
    write_source(project, "src/auth.py", "class AuthService:\n    pass\n")

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert len(acceptance_file_errors(result)) == 1


def test_manifest_without_acceptance_section_does_not_report_e500(project):
    manifest_path = write_manifest(
        project,
        "no-acceptance.manifest.yaml",
        """schema: "2"
goal: "Add greet"
files:
  create:
    - path: src/greet.py
      artifacts:
        - kind: function
          name: greet
validate:
  - pytest tests/ -v
""",
    )
    write_source(project, "src/greet.py", "def greet():\n    pass\n")

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert acceptance_file_errors(result) == []


def test_behavioral_mode_reports_missing_acceptance_test_file(project):
    manifest_path = write_manifest(
        project,
        "with-acceptance.manifest.yaml",
        """schema: "2"
goal: "Add auth"
files:
  create:
    - path: src/auth.py
      artifacts:
        - kind: class
          name: AuthService
  read:
    - tests/test_auth.py
acceptance:
  tests:
    - pytest tests/acceptance/test_auth.py -v
validate:
  - pytest tests/test_auth.py -v
""",
    )
    write_source(
        project,
        "tests/test_auth.py",
        "from src.auth import AuthService\n\n"
        "def test_auth():\n"
        "    AuthService()\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.BEHAVIORAL)

    assert len(acceptance_file_errors(result)) == 1
