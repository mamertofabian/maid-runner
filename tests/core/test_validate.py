"""Tests for maid_runner.core.validate - ValidationEngine.

Golden test cases from 15-golden-tests.md sections 6 and 7.
"""

import pytest

from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine, validate


@pytest.fixture()
def project(tmp_path):
    """Create a temporary project directory."""
    src = tmp_path / "src"
    src.mkdir()
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    return tmp_path


def _write_manifest(manifests_dir, name, content):
    path = manifests_dir / name
    path.write_text(content)
    return path


def _write_source(project_dir, rel_path, content):
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


class TestImplementationValidation:
    def test_strict_mode_all_present_pass(self, project):
        """Golden test 6.1: All artifacts present -> PASS."""
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(
            project,
            "src/greet.py",
            'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is True
        assert result.errors == []

    def test_strict_mode_missing_artifact_fail(self, project):
        """Golden test 6.2: Missing artifact -> E300."""
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(project, "src/greet.py", "# empty file\n")

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is False
        assert any(e.code == ErrorCode.ARTIFACT_NOT_DEFINED for e in result.errors)

    def test_strict_mode_unexpected_public_fail(self, project):
        """Golden test 6.3: Unexpected public artifact -> E301."""
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(
            project,
            "src/greet.py",
            'def greet(name):\n    return f"Hello, {name}!"\n\ndef farewell(name):\n    return f"Goodbye, {name}!"\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is False
        assert any(e.code == ErrorCode.UNEXPECTED_ARTIFACT for e in result.errors)

    def test_strict_mode_private_allowed(self, project):
        """Golden test 6.4: Private artifacts allowed in strict mode."""
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(
            project,
            "src/greet.py",
            'def greet(name):\n    return _format(name)\n\ndef _format(name):\n    return f"Hello, {name}!"\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is True

    def test_permissive_mode_extra_public_allowed(self, project):
        """Golden test 6.5: Edit mode allows extra public."""
        manifest_path = _write_manifest(
            project / "manifests",
            "edit-greet.manifest.yaml",
            """schema: "2"
goal: "Add farewell"
files:
  edit:
    - path: src/greet.py
      artifacts:
        - kind: function
          name: farewell
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/greet.py",
            'def greet(name):\n    return f"Hello, {name}!"\n\ndef farewell(name):\n    return f"Goodbye, {name}!"\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is True

    def test_absent_file_still_exists_fail(self, project):
        """Golden test 6.6: File should be absent but exists -> E305."""
        manifest_path = _write_manifest(
            project / "manifests",
            "delete-old.manifest.yaml",
            """schema: "2"
goal: "Remove old module"
files:
  delete:
    - path: src/old_module.py
validate:
  - pytest tests/ -v
""",
        )
        _write_source(project, "src/old_module.py", "# still here\n")

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is False
        assert any(e.code == ErrorCode.FILE_SHOULD_BE_ABSENT for e in result.errors)

    def test_absent_file_not_exists_pass(self, project):
        """File should be absent and is absent -> PASS."""
        manifest_path = _write_manifest(
            project / "manifests",
            "delete-old.manifest.yaml",
            """schema: "2"
goal: "Remove old module"
files:
  delete:
    - path: src/old_module.py
validate:
  - pytest tests/ -v
""",
        )
        # Don't create the file

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is True

    def test_type_mismatch_fail(self, project):
        """Golden test 6.7: Type mismatch -> E302."""
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(
            project,
            "src/calc.py",
            "def add(a: str, b: str) -> str:\n    return a + b\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is False
        assert any(e.code == ErrorCode.TYPE_MISMATCH for e in result.errors)

    def test_file_not_found_fail(self, project):
        """Source file doesn't exist -> E306."""
        manifest_path = _write_manifest(
            project / "manifests",
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
        # Don't create src/greet.py

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is False
        assert any(e.code == ErrorCode.FILE_SHOULD_BE_PRESENT for e in result.errors)


class TestBehavioralValidation:
    def test_artifact_used_in_test_pass(self, project):
        """Golden test 7.1: Artifact used in test -> PASS."""
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(
            project,
            "tests/test_greet.py",
            'from src.greet import greet\n\ndef test_greet():\n    assert greet("World") == "Hello, World!"\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.BEHAVIORAL)
        assert result.success is True

    def test_artifact_not_used_fail(self, project):
        """Golden test 7.2: Artifact not used -> E200."""
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(
            project,
            "tests/test_greet.py",
            "def test_something():\n    assert True\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.BEHAVIORAL)
        assert result.success is False
        assert any(
            e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS for e in result.errors
        )


class TestConvenienceFunction:
    def test_validate_function(self, project):
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(
            project,
            "src/greet.py",
            'def greet(name):\n    return f"Hello, {name}!"\n',
        )

        result = validate(
            manifest_path,
            mode=ValidationMode.IMPLEMENTATION,
            project_root=project,
        )
        assert result.success is True
