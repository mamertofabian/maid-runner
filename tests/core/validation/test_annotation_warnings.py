"""Focused characterization tests for implementation annotation warnings."""

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


def error_codes(result):
    return {error.code for error in result.errors}


def warning_codes(result):
    return {warning.code for warning in result.warnings}


def test_missing_return_annotation_reports_warning_without_type_mismatch(project):
    manifest_path = write_manifest(
        project,
        "add-func.manifest.yaml",
        """schema: "2"
goal: "Add func"
files:
  create:
    - path: src/func.py
      artifacts:
        - kind: function
          name: foo
          returns: str
validate:
  - pytest tests/ -v
""",
    )
    write_source(project, "src/func.py", 'def foo():\n    return "hello"\n')

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert ErrorCode.TYPE_MISMATCH not in error_codes(result)
    assert ErrorCode.MISSING_RETURN_TYPE in warning_codes(result)


def test_missing_argument_annotation_reports_warning_without_type_mismatch(project):
    manifest_path = write_manifest(
        project,
        "add-func.manifest.yaml",
        """schema: "2"
goal: "Add func"
files:
  create:
    - path: src/func.py
      artifacts:
        - kind: function
          name: foo
          args:
            - name: x
              type: str
validate:
  - pytest tests/ -v
""",
    )
    write_source(project, "src/func.py", "def foo(x):\n    return x\n")

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert ErrorCode.TYPE_MISMATCH not in error_codes(result)
    assert ErrorCode.MISSING_RETURN_TYPE in warning_codes(result)
