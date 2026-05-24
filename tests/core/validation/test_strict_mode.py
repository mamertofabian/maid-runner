"""Focused characterization tests for strict validation warning policies."""

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


def warning_codes(result):
    return {warning.code for warning in result.warnings}


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


def test_behavioral_assertion_check_warns_for_test_without_assertions(project):
    manifest_path = add_greet_manifest(project)
    write_source(
        project,
        "tests/test_greet.py",
        "from src.greet import greet\n\n" "def test_greet():\n" "    greet()\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(
        manifest_path,
        mode=ValidationMode.BEHAVIORAL,
        check_assertions=True,
    )

    assert result.success is True
    assert result.errors == []
    assert ErrorCode.MISSING_ASSERTIONS in warning_codes(result)


def test_behavioral_assertion_check_is_quiet_without_flag(project):
    manifest_path = add_greet_manifest(project)
    write_source(
        project,
        "tests/test_greet.py",
        "from src.greet import greet\n\n" "def test_greet():\n" "    greet()\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.BEHAVIORAL)

    assert result.success is True
    assert ErrorCode.MISSING_ASSERTIONS not in warning_codes(result)


def test_implementation_stub_check_warns_for_pass_function(project):
    manifest_path = add_greet_manifest(project)
    write_source(project, "src/greet.py", "def greet():\n    pass\n")
    write_source(
        project,
        "tests/test_greet.py",
        "from src.greet import greet\n\n"
        "def test_greet_exists():\n"
        "    assert greet is not None\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(
        manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
        check_stubs=True,
    )

    assert result.success is True
    assert result.errors == []
    assert ErrorCode.STUB_FUNCTION_DETECTED in warning_codes(result)


def test_implementation_stub_check_is_quiet_without_flag(project):
    manifest_path = add_greet_manifest(project)
    write_source(project, "src/greet.py", "def greet():\n    pass\n")
    write_source(
        project,
        "tests/test_greet.py",
        "from src.greet import greet\n\n"
        "def test_greet_exists():\n"
        "    assert greet is not None\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert result.errors == []
    assert ErrorCode.STUB_FUNCTION_DETECTED not in warning_codes(result)


def test_implementation_stub_check_is_quiet_for_real_function(project):
    manifest_path = add_greet_manifest(project)
    write_source(
        project,
        "src/greet.py",
        'def greet(name):\n    return f"Hello, {name}!"\n',
    )
    write_source(
        project,
        "tests/test_greet.py",
        "from src.greet import greet\n\n"
        "def test_greet_exists():\n"
        "    assert greet is not None\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(
        manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
        check_stubs=True,
    )

    assert result.success is True
    assert result.errors == []
    assert ErrorCode.STUB_FUNCTION_DETECTED not in warning_codes(result)


def test_implementation_fail_on_warnings_marks_warning_only_result_failed(project):
    manifest_path = add_greet_manifest(project)
    write_source(project, "src/greet.py", "def greet():\n    pass\n")
    write_source(
        project,
        "tests/test_greet.py",
        "from src.greet import greet\n\n"
        "def test_greet_exists():\n"
        "    assert greet is not None\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(
        manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
        check_stubs=True,
        fail_on_warnings=True,
    )

    assert result.success is False
    assert result.errors == []
    assert ErrorCode.STUB_FUNCTION_DETECTED in warning_codes(result)


def test_validate_all_applies_strict_warning_policy_to_each_manifest(project):
    add_greet_manifest(project)
    write_source(project, "src/greet.py", "def greet():\n    pass\n")
    write_source(
        project,
        "tests/test_greet.py",
        "from src.greet import greet\n\n"
        "def test_greet_exists():\n"
        "    assert greet is not None\n",
    )

    batch = validate_all(
        "manifests",
        project_root=project,
        mode=ValidationMode.IMPLEMENTATION,
        check_stubs=True,
        fail_on_warnings=True,
    )

    assert batch.success is False
    assert batch.passed == 0
    assert batch.failed == 1
    assert any(
        ErrorCode.STUB_FUNCTION_DETECTED in warning_codes(result)
        for result in batch.results
    )
