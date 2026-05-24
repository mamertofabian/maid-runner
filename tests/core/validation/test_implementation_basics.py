"""Focused characterization tests for implementation validation basics."""

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


def error_codes(result):
    return {error.code for error in result.errors}


def test_matching_python_function_signature_passes_implementation_validation(project):
    manifest_path = write_manifest(
        project,
        "add-greet.manifest.yaml",
        """schema: "2"
goal: "Add greet"
files:
  create:
    - path: src/greet.py
      artifacts:
        - kind: function
          name: greet
          args:
            - name: name
              type: str
          returns: str
  read:
    - tests/test_greet.py
validate:
  - pytest tests/test_greet.py -v
""",
    )
    write_source(
        project,
        "src/greet.py",
        'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n',
    )
    write_test(project, "tests/test_greet.py", "src.greet", ["greet"])

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert result.errors == []


def test_missing_declared_python_function_reports_artifact_not_defined(project):
    manifest_path = write_manifest(
        project,
        "add-greet.manifest.yaml",
        """schema: "2"
goal: "Add greet"
files:
  create:
    - path: src/greet.py
      artifacts:
        - kind: function
          name: greet
          args:
            - name: name
              type: str
          returns: str
validate:
  - pytest tests/ -v
""",
    )
    write_source(project, "src/greet.py", "# empty file\n")

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is False
    assert ErrorCode.ARTIFACT_NOT_DEFINED in error_codes(result)


def test_same_named_wrong_kind_reports_artifact_not_defined(project):
    manifest_path = write_manifest(
        project,
        "add-config.manifest.yaml",
        """schema: "2"
goal: "Add Config class"
files:
  create:
    - path: src/config.py
      artifacts:
        - kind: class
          name: Config
  read:
    - tests/test_config.py
validate:
  - pytest tests/test_config.py -v
""",
    )
    write_source(project, "src/config.py", "Config = object()\n")
    write_test(project, "tests/test_config.py", "src.config", ["Config"])

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is False
    assert ErrorCode.ARTIFACT_NOT_DEFINED in error_codes(result)


def test_private_helper_is_allowed_in_strict_create_mode(project):
    manifest_path = write_manifest(
        project,
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
    write_source(
        project,
        "src/greet.py",
        "def greet(name):\n    return _format(name)\n\n"
        'def _format(name):\n    return f"Hello, {name}!"\n',
    )
    write_test(project, "tests/test_greet.py", "src.greet", ["greet"])

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert result.errors == []


def test_python_signature_type_mismatch_reports_type_mismatch(project):
    manifest_path = write_manifest(
        project,
        "add-calc.manifest.yaml",
        """schema: "2"
goal: "Add calc"
files:
  create:
    - path: src/calc.py
      artifacts:
        - kind: function
          name: add
          args:
            - name: a
              type: int
            - name: b
              type: int
          returns: int
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "src/calc.py",
        "def add(a: str, b: str) -> str:\n    return a + b\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is False
    assert ErrorCode.TYPE_MISMATCH in error_codes(result)


def test_created_file_missing_reports_file_should_be_present(project):
    manifest_path = write_manifest(
        project,
        "add-greet.manifest.yaml",
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

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is False
    assert ErrorCode.FILE_SHOULD_BE_PRESENT in error_codes(result)
