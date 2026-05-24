"""Focused characterization tests for validation error handling."""

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


def test_invalid_manifest_schema_reports_schema_validation_error(project):
    manifest_path = write_manifest(
        project,
        "bad.manifest.yaml",
        "schema: '2'\ntype: feature\nfiles:\n  create: []\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(str(manifest_path), use_chain=False)

    assert result.success is False
    assert ErrorCode.SCHEMA_VALIDATION_ERROR in {error.code for error in result.errors}


def test_missing_manifest_path_reports_file_not_found(project):
    missing_manifest = project / "manifests" / "nonexistent.manifest.yaml"

    engine = ValidationEngine(project_root=project)
    result = engine.validate(str(missing_manifest), use_chain=False)

    assert result.success is False
    assert ErrorCode.FILE_NOT_FOUND in {error.code for error in result.errors}


def test_python_source_syntax_error_reports_source_parse_error(project):
    manifest_path = write_manifest(
        project,
        "broken-src.manifest.yaml",
        """schema: "2"
goal: "Broken source"
files:
  create:
    - path: src/broken.py
      artifacts:
        - kind: function
          name: broken
validate:
  - pytest tests/ -v
""",
    )
    write_source(project, "src/broken.py", "def broken(:\n    pass\n")

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is False
    assert ErrorCode.SOURCE_PARSE_ERROR in {error.code for error in result.errors}


def test_python_test_file_syntax_error_reports_source_parse_error(project):
    manifest_path = write_manifest(
        project,
        "broken-test.manifest.yaml",
        """schema: "2"
goal: "Broken test"
files:
  create:
    - path: src/example.py
      artifacts:
        - kind: function
          name: example
  read:
    - tests/test_example.py
validate:
  - pytest tests/test_example.py -v
""",
    )
    write_source(project, "src/example.py", "def example():\n    return 1\n")
    write_source(project, "tests/test_example.py", "def test_example(:\n    pass\n")

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
    issue_codes = {issue.code for issue in result.errors + result.warnings}

    assert ErrorCode.SOURCE_PARSE_ERROR in issue_codes
