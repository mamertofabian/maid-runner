"""Focused characterization tests for the top-level validation API."""

import pytest

from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine, validate


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


def add_greet_manifest(project_dir):
    return write_manifest(
        project_dir,
        "add-greet.manifest.yaml",
        """schema: "2"
goal: "Add greet"
files:
  create:
    - path: src/greet.py
      artifacts:
        - kind: function
          name: greet
  read:
    - tests/test_greet.py
validate:
  - pytest tests/test_greet.py -v
""",
    )


def add_greet_test(project_dir):
    write_source(
        project_dir,
        "tests/test_greet.py",
        "from src.greet import greet\n\n"
        "def test_greet_exists():\n"
        "    assert greet is not None\n",
    )


def warning_codes(result):
    return {warning.code for warning in result.warnings}


def test_validation_engine_exposes_public_validation_methods():
    methods = [
        ValidationEngine.validate,
        ValidationEngine.validate_behavioral,
        ValidationEngine.validate_acceptance,
        ValidationEngine.validate_implementation,
    ]

    assert all(callable(method) for method in methods)


def test_validate_function_runs_implementation_validation(project):
    manifest_path = add_greet_manifest(project)
    write_source(
        project,
        "src/greet.py",
        'def greet(name):\n    return f"Hello, {name}!"\n',
    )
    add_greet_test(project)

    result = validate(
        manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
        project_root=project,
    )

    assert result.success is True
    assert result.errors == []


def test_validate_function_threads_check_stubs_flag(project):
    manifest_path = add_greet_manifest(project)
    write_source(project, "src/greet.py", "def greet():\n    pass\n")
    add_greet_test(project)

    result = validate(
        manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
        project_root=project,
        check_stubs=True,
    )

    assert result.success is True
    assert result.errors == []
    assert ErrorCode.STUB_FUNCTION_DETECTED in warning_codes(result)
