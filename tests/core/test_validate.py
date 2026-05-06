"""Tests for maid_runner.core.validate - ValidationEngine.

Golden test cases from 15-golden-tests.md sections 6 and 7.
"""

import pytest

from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine, validate, _check_test_assertions


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


def _add_test_file(project_dir, test_rel_path, source_module, artifact_names):
    """Write a minimal test file that references the given artifacts.

    Returns the test_rel_path for inclusion in manifest YAML.
    """
    public_names = [n for n in artifact_names if not n.startswith("_")]
    if not public_names:
        public_names = artifact_names
    imports = ", ".join(public_names)
    tests = "\n".join(
        f"def test_{n}():\n    assert {n} is not None\n" for n in public_names
    )
    content = f"from {source_module} import {imports}\n\n{tests}\n"
    _write_source(project_dir, test_rel_path, content)
    return test_rel_path


class TestImplementationValidation:
    def test_consolidated_validation_methods_are_referenced(self):
        """Smoke references for ValidationEngine public validation methods."""
        assert callable(ValidationEngine.validate_behavioral)
        assert callable(ValidationEngine.validate_acceptance)
        assert callable(ValidationEngine.validate_implementation)

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
  read:
    - tests/test_greet.py
validate:
  - pytest tests/test_greet.py -v
""",
        )
        _write_source(
            project,
            "src/greet.py",
            'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n',
        )
        _add_test_file(project, "tests/test_greet.py", "src.greet", ["greet"])

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

    def test_wrong_artifact_kind_with_same_name_fails(self, project):
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(project, "src/config.py", "Config = object()\n")
        _add_test_file(project, "tests/test_config.py", "src.config", ["Config"])

        result = validate(
            manifest_path,
            mode=ValidationMode.IMPLEMENTATION,
            project_root=project,
        )

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
  read:
    - tests/test_greet.py
validate:
  - pytest tests/test_greet.py -v
""",
        )
        _write_source(
            project,
            "src/greet.py",
            'def greet(name):\n    return _format(name)\n\ndef _format(name):\n    return f"Hello, {name}!"\n',
        )
        _add_test_file(project, "tests/test_greet.py", "src.greet", ["greet"])

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
  read:
    - tests/test_greet.py
validate:
  - pytest tests/test_greet.py -v
""",
        )
        _write_source(
            project,
            "src/greet.py",
            'def greet(name):\n    return f"Hello, {name}!"\n\ndef farewell(name):\n    return f"Goodbye, {name}!"\n',
        )
        _add_test_file(project, "tests/test_greet.py", "src.greet", ["farewell"])

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


class TestMissingAnnotationWarning:
    def test_missing_return_type_is_warning_not_error(self, project):
        """Golden test 5.2: manifest says returns: str, code has no annotation -> WARNING E304."""
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(project, "src/func.py", 'def foo():\n    return "hello"\n')

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        # Should NOT have E302 TYPE_MISMATCH error
        assert not any(e.code == ErrorCode.TYPE_MISMATCH for e in result.errors)
        # Should have E304 MISSING_RETURN_TYPE warning
        assert any(w.code == ErrorCode.MISSING_RETURN_TYPE for w in result.warnings)

    def test_missing_arg_type_is_warning_not_error(self, project):
        """Manifest says arg type: str, code has no annotation -> WARNING E304."""
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(project, "src/func.py", "def foo(x):\n    return x\n")

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert not any(e.code == ErrorCode.TYPE_MISMATCH for e in result.errors)
        assert any(w.code == ErrorCode.MISSING_RETURN_TYPE for w in result.warnings)


class TestFileTracking:
    def test_gitignored_file_not_reported_as_undeclared(self, project):
        """File tracking ignores source files excluded by gitignore."""
        import subprocess

        subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
        (project / ".gitignore").write_text("generated.py\n")
        _write_source(project, "generated.py", "def generated(): pass\n")

        from maid_runner.core.chain import ManifestChain

        engine = ValidationEngine(project_root=project)
        chain = ManifestChain(project / "manifests", project_root=project)
        report = engine.run_file_tracking(chain)

        assert all(e.path != "generated.py" for e in report.entries)

    def test_read_only_file_classified_as_registered(self, project):
        """Golden test 9.1: File only in files.read should be REGISTERED, not UNDECLARED."""
        _write_manifest(
            project / "manifests",
            "use-dep.manifest.yaml",
            """schema: "2"
goal: "Use dependency"
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: run
  read:
    - src/dep.py
validate:
  - pytest tests/ -v
""",
        )
        _write_source(project, "src/app.py", "def run(): pass\n")
        _write_source(project, "src/dep.py", "def helper(): pass\n")

        from maid_runner.core.chain import ManifestChain
        from maid_runner.core.result import FileTrackingStatus

        engine = ValidationEngine(project_root=project)
        chain = ManifestChain(project / "manifests", project_root=project)
        report = engine.run_file_tracking(chain)

        dep_entries = [e for e in report.entries if e.path == "src/dep.py"]
        assert len(dep_entries) == 1
        entry = dep_entries[0]
        assert entry.status == FileTrackingStatus.REGISTERED
        assert entry.status != FileTrackingStatus.UNDECLARED
        assert any("read" in issue.lower() for issue in entry.issues)


class TestAcceptanceValidation:
    def test_acceptance_files_exist_pass(self, project):
        """Acceptance test file exists -> no E500 errors."""
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(project, "src/auth.py", "class AuthService:\n    pass\n")
        _write_source(
            project,
            "tests/acceptance/test_auth.py",
            "def test_auth():\n    assert True\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert not any(
            e.code == ErrorCode.ACCEPTANCE_TEST_FILE_NOT_FOUND for e in result.errors
        )

    def test_acceptance_files_missing_fail(self, project):
        """Acceptance test file missing -> E500 error."""
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(project, "src/auth.py", "class AuthService:\n    pass\n")
        # Don't create acceptance test file

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert any(
            e.code == ErrorCode.ACCEPTANCE_TEST_FILE_NOT_FOUND for e in result.errors
        )

    def test_no_acceptance_no_errors(self, project):
        """Manifest without acceptance -> no E500 errors."""
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(project, "src/greet.py", "def greet():\n    pass\n")

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert not any(
            e.code == ErrorCode.ACCEPTANCE_TEST_FILE_NOT_FOUND for e in result.errors
        )

    def test_acceptance_validation_in_behavioral_mode(self, project):
        """Acceptance validation also runs in behavioral mode."""
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(
            project,
            "tests/test_auth.py",
            "from src.auth import AuthService\ndef test_auth():\n    AuthService()\n",
        )
        # Don't create acceptance test file

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.BEHAVIORAL)
        assert any(
            e.code == ErrorCode.ACCEPTANCE_TEST_FILE_NOT_FOUND for e in result.errors
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
  read:
    - tests/test_greet.py
validate:
  - pytest tests/test_greet.py -v
""",
        )
        _write_source(
            project,
            "src/greet.py",
            'def greet(name):\n    return f"Hello, {name}!"\n',
        )
        _add_test_file(project, "tests/test_greet.py", "src.greet", ["greet"])

        result = validate(
            manifest_path,
            mode=ValidationMode.IMPLEMENTATION,
            project_root=project,
        )
        assert result.success is True


class TestStubDetection:
    """Tests for check_stubs=True detecting hollow implementations."""

    def test_stub_function_detected_as_warning(self, project):
        """Stub function detected when check_stubs=True -> E310 WARNING."""
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
        _write_source(project, "src/greet.py", "def greet():\n    pass\n")
        _add_test_file(project, "tests/test_greet.py", "src.greet", ["greet"])

        engine = ValidationEngine(project_root=project)
        result = engine.validate(
            manifest_path,
            mode=ValidationMode.IMPLEMENTATION,
            check_stubs=True,
        )
        # Structural validation passes (function exists)
        assert result.success is True
        # But stub is flagged as warning
        assert any(w.code == ErrorCode.STUB_FUNCTION_DETECTED for w in result.warnings)

    def test_stub_not_detected_without_flag(self, project):
        """Stub function NOT flagged when check_stubs=False (default)."""
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
        _write_source(project, "src/greet.py", "def greet():\n    pass\n")
        _add_test_file(project, "tests/test_greet.py", "src.greet", ["greet"])

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is True
        assert not any(
            w.code == ErrorCode.STUB_FUNCTION_DETECTED for w in result.warnings
        )

    def test_real_function_no_stub_warning(self, project):
        """Real function -> no stub warning even with check_stubs=True."""
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
            "src/greet.py",
            'def greet(name):\n    return f"Hello, {name}!"\n',
        )
        _add_test_file(project, "tests/test_greet.py", "src.greet", ["greet"])

        engine = ValidationEngine(project_root=project)
        result = engine.validate(
            manifest_path,
            mode=ValidationMode.IMPLEMENTATION,
            check_stubs=True,
        )
        assert result.success is True
        assert not any(
            w.code == ErrorCode.STUB_FUNCTION_DETECTED for w in result.warnings
        )


class TestAssertionChecking:
    """Tests for check_assertions=True in behavioral mode."""

    def test_test_with_assertions_passes(self, project):
        """Test function with assert -> no E210."""
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
        result = engine.validate(
            manifest_path,
            mode=ValidationMode.BEHAVIORAL,
            check_assertions=True,
        )
        assert not any(w.code == ErrorCode.MISSING_ASSERTIONS for w in result.warnings)

    def test_test_without_assertions_warned(self, project):
        """Test function with no assert -> E210 WARNING."""
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
            "from src.greet import greet\n\ndef test_greet():\n    greet()\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(
            manifest_path,
            mode=ValidationMode.BEHAVIORAL,
            check_assertions=True,
        )
        assert any(w.code == ErrorCode.MISSING_ASSERTIONS for w in result.warnings)

    def test_assertions_not_checked_without_flag(self, project):
        """No E210 when check_assertions=False (default)."""
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
            "from src.greet import greet\n\ndef test_greet():\n    greet()\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.BEHAVIORAL)
        assert not any(w.code == ErrorCode.MISSING_ASSERTIONS for w in result.warnings)

    def test_pytest_raises_counts_as_assertion(self, project):
        """pytest.raises is recognized as an assertion."""
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
          name: divide
  read:
    - tests/test_calc.py
validate:
  - pytest tests/test_calc.py -v
""",
        )
        _write_source(
            project,
            "tests/test_calc.py",
            "import pytest\nfrom src.calc import divide\n\ndef test_divide_zero():\n    with pytest.raises(ZeroDivisionError):\n        divide(1, 0)\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(
            manifest_path,
            mode=ValidationMode.BEHAVIORAL,
            check_assertions=True,
        )
        assert not any(w.code == ErrorCode.MISSING_ASSERTIONS for w in result.warnings)


class TestImportVerification:
    """Tests for required imports field on FileSpec."""

    def test_required_import_present_passes(self, project):
        """File has required import -> no E320."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-page.manifest.yaml",
            """schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/budget.py
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - src.api.budgets
  read:
    - tests/test_budget.py
validate:
  - pytest tests/test_budget.py -v
""",
        )
        _write_source(
            project,
            "src/pages/budget.py",
            "from src.api.budgets import list_budgets\n\ndef BudgetPage():\n    data = list_budgets()\n    return data\n",
        )
        _add_test_file(
            project, "tests/test_budget.py", "src.pages.budget", ["BudgetPage"]
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is True
        assert not any(
            e.code == ErrorCode.MISSING_REQUIRED_IMPORT
            for e in result.errors + result.warnings
        )

    def test_required_import_missing_fails(self, project):
        """File missing required import -> E320."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-page.manifest.yaml",
            """schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/budget.py
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - src.api.budgets
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/pages/budget.py",
            "def BudgetPage():\n    return 'placeholder'\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        # Import check is always active when imports are declared
        assert any(e.code == ErrorCode.MISSING_REQUIRED_IMPORT for e in result.errors)

    def test_no_imports_field_no_check(self, project):
        """Manifest without imports field -> no import checking."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-page.manifest.yaml",
            """schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/budget.py
      artifacts:
        - kind: function
          name: BudgetPage
  read:
    - tests/test_budget.py
validate:
  - pytest tests/test_budget.py -v
""",
        )
        _write_source(
            project,
            "src/pages/budget.py",
            "def BudgetPage():\n    return 'placeholder'\n",
        )
        _add_test_file(
            project, "tests/test_budget.py", "src.pages.budget", ["BudgetPage"]
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is True
        assert not any(
            e.code == ErrorCode.MISSING_REQUIRED_IMPORT
            for e in result.errors + result.warnings
        )

    def test_import_symbol_name_passes(self, project):
        """Import by symbol name (e.g., 'list_budgets') matches."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-page.manifest.yaml",
            """schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/budget.py
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - list_budgets
  read:
    - tests/test_budget.py
validate:
  - pytest tests/test_budget.py -v
""",
        )
        _write_source(
            project,
            "src/pages/budget.py",
            "from src.api.budgets import list_budgets\n\ndef BudgetPage():\n    return list_budgets()\n",
        )
        _add_test_file(
            project, "tests/test_budget.py", "src.pages.budget", ["BudgetPage"]
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is True

    def test_ts_relative_import_resolves_to_manifest_path(self, project):
        """TS relative import ../../src/models/Budget resolves to match manifest declaration."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-budget-page.manifest.yaml",
            """schema: "2"
goal: "Add budget page"
files:
  create:
    - path: src/pages/BudgetPage.ts
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - src/models/Budget
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/pages/BudgetPage.ts",
            'import { Budget } from "../models/Budget";\n\nexport function BudgetPage() { return new Budget(); }\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_ts_deep_relative_import_resolves(self, project):
        """Deep relative import ../../src/models/Budget from tests/ resolves correctly."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-test.manifest.yaml",
            """schema: "2"
goal: "Add test"
files:
  create:
    - path: tests/pages/test_budget.ts
      artifacts:
        - kind: function
          name: testBudget
      imports:
        - src/models/Budget
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "tests/pages/test_budget.ts",
            'import { Budget } from "../../src/models/Budget";\n\nexport function testBudget() { return new Budget(); }\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_ts_dot_slash_import_resolves(self, project):
        """TS ./sibling import resolves to match manifest path."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-page.manifest.yaml",
            """schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/BudgetPage.ts
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - src/pages/utils
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/pages/BudgetPage.ts",
            'import { helper } from "./utils";\n\nexport function BudgetPage() { return helper(); }\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_ts_absolute_import_still_works(self, project):
        """Non-relative TS imports (package names) still match exactly."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-page.manifest.yaml",
            """schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/BudgetPage.ts
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - react
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/pages/BudgetPage.ts",
            'import React from "react";\n\nexport function BudgetPage() { return React.createElement("div"); }\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_ts_relative_import_with_extension_stripped(self, project):
        """Import with .ts extension resolves to match manifest path without extension."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-page.manifest.yaml",
            """schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/BudgetPage.ts
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - src/models/Budget
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/pages/BudgetPage.ts",
            'import { Budget } from "../models/Budget.ts";\n\nexport function BudgetPage() { return new Budget(); }\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_js_require_import_detected(self, project):
        """CommonJS require() calls are captured for import checking."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-util.manifest.yaml",
            """schema: "2"
goal: "Add util"
files:
  create:
    - path: src/utils/helper.js
      artifacts:
        - kind: function
          name: helper
      imports:
        - lodash
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/utils/helper.js",
            'const _ = require("lodash");\n\nfunction helper() { return _.get({}, "a"); }\nmodule.exports = { helper };\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_js_require_relative_resolves(self, project):
        """CommonJS require() with relative path resolves correctly."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-svc.manifest.yaml",
            """schema: "2"
goal: "Add service"
files:
  create:
    - path: src/services/api.js
      artifacts:
        - kind: function
          name: callApi
      imports:
        - src/models/Budget
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/services/api.js",
            'const Budget = require("../models/Budget");\n\nfunction callApi() { return new Budget(); }\nmodule.exports = { callApi };\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_ts_export_from_detected(self, project):
        """Re-export: export { X } from './module' captures module path and symbols."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-index.manifest.yaml",
            """schema: "2"
goal: "Add barrel export"
files:
  create:
    - path: src/index.ts
      artifacts:
        - kind: function
          name: barrel
      imports:
        - src/utils
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/index.ts",
            'export { helper } from "./utils";\n\nexport function barrel() {}\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_ts_import_star_detected(self, project):
        """import * as X from './module' captures both namespace name and module path."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-page.manifest.yaml",
            """schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/BudgetPage.ts
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - Models
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/pages/BudgetPage.ts",
            'import * as Models from "../models";\n\nexport function BudgetPage() { return Models; }\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_ts_import_type_detected(self, project):
        """Type-only imports count as required imports."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-types.manifest.yaml",
            """schema: "2"
goal: "Add type consumer"
files:
  create:
    - path: src/pages/BudgetPage.ts
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - src/models/Budget
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/pages/BudgetPage.ts",
            'import type { Budget } from "../models/Budget";\n\nexport function BudgetPage(model: Budget) { return model; }\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_ts_dynamic_import_detected(self, project):
        """Dynamic import() calls count as required imports."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-loader.manifest.yaml",
            """schema: "2"
goal: "Add dynamic loader"
files:
  create:
    - path: src/loaders/loadBudget.ts
      artifacts:
        - kind: function
          name: loadBudget
      imports:
        - src/models/Budget
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/loaders/loadBudget.ts",
            'export async function loadBudget() { return import("../models/Budget"); }\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_ts_require_resolve_detected(self, project):
        """require.resolve() calls count as required imports."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-resolver.manifest.yaml",
            """schema: "2"
goal: "Add resolver"
files:
  create:
    - path: src/loaders/resolveBudget.js
      artifacts:
        - kind: function
          name: resolveBudget
      imports:
        - src/models/Budget
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/loaders/resolveBudget.js",
            'function resolveBudget() { return require.resolve("../models/Budget"); }\nmodule.exports = { resolveBudget };\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_ts_multiline_named_import_detected(self, project):
        """Multiline named imports count as required imports."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-page.manifest.yaml",
            """schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/BudgetPage.ts
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - Budget
        - src/models/Budget
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/pages/BudgetPage.ts",
            'import {\n  Budget,\n} from "../models/Budget";\n\nexport function BudgetPage() { return new Budget(); }\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_ts_commented_out_import_does_not_satisfy_required_import(self, project):
        """Commented-out import text does not satisfy required imports."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-page.manifest.yaml",
            """schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/BudgetPage.ts
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - src/models/Budget
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/pages/BudgetPage.ts",
            '// import { Budget } from "../models/Budget";\n\nexport function BudgetPage() { return null; }\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 1

    def test_ts_import_alias_binding_detected(self, project):
        """Named import aliases count by their local binding name."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-page.manifest.yaml",
            """schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/BudgetPage.ts
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - BudgetModel
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/pages/BudgetPage.ts",
            'import { Budget as BudgetModel } from "../models/Budget";\n\nexport function BudgetPage() { return new BudgetModel(); }\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_ts_root_file_escape_not_resolved(self, project):
        """Import from root-level file that escapes project with .. is not falsely matched."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-app.manifest.yaml",
            """schema: "2"
goal: "Add app"
files:
  create:
    - path: app.ts
      artifacts:
        - kind: function
          name: app
      imports:
        - outside/module
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "app.ts",
            'import { X } from "../outside/module";\n\nexport function app() { return X; }\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        # ../outside/module from root resolves to ../outside/module which escapes
        # project root — filtered out. So "outside/module" won't match.
        assert len(import_errors) == 1

    def test_python_path_style_import_matches_dotted(self, project):
        """Path-style required_import 'src/models/user.py' matches dotted 'src.models.user'."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-user.manifest.yaml",
            """schema: "2"
goal: "Add user model"
files:
  create:
    - path: src/routes/users.py
      artifacts:
        - kind: function
          name: get_users
      imports:
        - src/models/user.py
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/routes/users.py",
            "from src.models.user import User\n\ndef get_users():\n    return User.all()\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_python_path_style_without_extension_matches(self, project):
        """Path-style required_import 'src/models/user' (no .py) matches dotted import."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-user2.manifest.yaml",
            """schema: "2"
goal: "Add user routes"
files:
  create:
    - path: src/routes/users.py
      artifacts:
        - kind: function
          name: list_users
      imports:
        - src/models/user
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/routes/users.py",
            "from src.models.user import User\n\ndef list_users():\n    return []\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_python_dotted_import_still_works(self, project):
        """Dotted required_import 'src.models.user' still matches directly (regression check)."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-user3.manifest.yaml",
            """schema: "2"
goal: "Add user views"
files:
  create:
    - path: src/views/users.py
      artifacts:
        - kind: function
          name: show_users
      imports:
        - src.models.user
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/views/users.py",
            "from src.models.user import User\n\ndef show_users():\n    return User.all()\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0


class TestValidateAllChainReuse:
    """Tests that validate_all passes pre-built chain to validate, not creating new ones."""

    def test_validate_all_creates_single_chain(self, project):
        """With multiple manifests, validate_all should create exactly one ManifestChain."""
        from unittest.mock import patch

        for i in range(5):
            _write_manifest(
                project / "manifests",
                f"m{i}.manifest.yaml",
                f"""schema: "2"
goal: "M{i}"
files:
  create:
    - path: src/m{i}.py
      artifacts:
        - kind: function
          name: func_{i}
  read:
    - tests/test_m{i}.py
validate:
  - pytest tests/test_m{i}.py
""",
            )
            _write_source(project, f"src/m{i}.py", f"def func_{i}():\n    return {i}\n")
            _add_test_file(project, f"tests/test_m{i}.py", f"src.m{i}", [f"func_{i}"])

        engine = ValidationEngine(project)
        with patch(
            "maid_runner.core.validate.ManifestChain", wraps=ManifestChain
        ) as mock_chain_cls:
            result = engine.validate_all()
        assert result.passed == 5
        assert result.failed == 0
        # validate_all creates one chain; individual validate() calls reuse it
        assert mock_chain_cls.call_count == 1

    def test_validate_accepts_chain_parameter(self, project):
        """validate() should accept an optional chain parameter to avoid re-creating it."""
        from maid_runner.core.chain import ManifestChain

        _write_manifest(
            project / "manifests",
            "a.manifest.yaml",
            """schema: "2"
goal: "A"
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: func_a
  read:
    - tests/test_a.py
validate:
  - pytest tests/test_a.py
""",
        )
        _write_source(project, "src/a.py", "def func_a():\n    return 1\n")
        _add_test_file(project, "tests/test_a.py", "src.a", ["func_a"])

        chain = ManifestChain(project / "manifests", project)
        engine = ValidationEngine(project)
        manifest = chain.active_manifests()[0]
        result = engine.validate(manifest, use_chain=True, chain=chain)
        assert result.success is True

    def test_validate_ignores_chain_when_use_chain_false(self, project):
        """Passing chain with use_chain=False should not use the chain."""
        _write_manifest(
            project / "manifests",
            "a.manifest.yaml",
            """schema: "2"
goal: "A"
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: func_a
  read:
    - tests/test_a.py
validate:
  - pytest tests/test_a.py
""",
        )
        _write_source(project, "src/a.py", "def func_a():\n    return 1\n")
        _add_test_file(project, "tests/test_a.py", "src.a", ["func_a"])

        chain = ManifestChain(project / "manifests", project)
        engine = ValidationEngine(project)
        manifest = chain.active_manifests()[0]
        # use_chain=False should ignore the passed chain
        result = engine.validate(manifest, use_chain=False, chain=chain)
        assert result.success is True
        # No file tracking report when chain is not used
        assert result.file_tracking is None

    def test_validate_all_reports_invalid_manifests_as_chain_errors(self, project):
        _write_manifest(
            project / "manifests",
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
  - pytest tests/test_good.py
""",
        )
        _write_source(project, "src/good.py", "def good():\n    return 1\n")
        _add_test_file(project, "tests/test_good.py", "src.good", ["good"])
        _write_manifest(
            project / "manifests",
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

        engine = ValidationEngine(project)
        result = engine.validate_all()

        assert result.success is False
        assert len(result.results) == 1
        assert any(
            e.code == ErrorCode.SCHEMA_VALIDATION_ERROR for e in result.chain_errors
        )

    def test_validate_all_performance_with_many_manifests(self, project):
        """validate_all with 20 manifests should complete quickly (under 5s)."""
        import time

        for i in range(20):
            _write_manifest(
                project / "manifests",
                f"perf{i}.manifest.yaml",
                f"""schema: "2"
goal: "Perf{i}"
files:
  create:
    - path: src/perf{i}.py
      artifacts:
        - kind: function
          name: perf_func_{i}
  read:
    - tests/test_perf{i}.py
validate:
  - pytest tests/test_perf{i}.py
""",
            )
            _write_source(
                project, f"src/perf{i}.py", f"def perf_func_{i}():\n    return {i}\n"
            )
            _add_test_file(
                project, f"tests/test_perf{i}.py", f"src.perf{i}", [f"perf_func_{i}"]
            )

        engine = ValidationEngine(project)
        start = time.monotonic()
        result = engine.validate_all()
        elapsed = time.monotonic() - start
        assert result.passed == 20
        assert elapsed < 5.0, f"validate_all took {elapsed:.1f}s, expected < 5s"


class TestConvenienceFunctionWithDepthFlags:
    """Test that top-level validate() threads check_stubs and check_assertions."""

    def test_validate_with_check_stubs(self, project):
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
        _write_source(project, "src/greet.py", "def greet():\n    pass\n")
        _add_test_file(project, "tests/test_greet.py", "src.greet", ["greet"])

        result = validate(
            manifest_path,
            mode=ValidationMode.IMPLEMENTATION,
            project_root=project,
            check_stubs=True,
        )
        assert result.success is True  # stubs are warnings, not errors
        assert any(w.code == ErrorCode.STUB_FUNCTION_DETECTED for w in result.warnings)


class TestStrictModeStructuralArtifacts:
    """Strict mode should not flag undeclared type aliases or interfaces (structural artifacts)."""

    def test_strict_mode_allows_undeclared_type_alias(self, project):
        """Undeclared type alias in files.create should not trigger E301."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-service.manifest.yaml",
            """schema: "2"
goal: "Add auth service"
files:
  create:
    - path: src/auth.ts
      artifacts:
        - kind: function
          name: authenticate
  read:
    - tests/test_auth.py
validate:
  - pytest tests/test_auth.py -v
""",
        )
        _write_source(
            project,
            "src/auth.ts",
            "type AuthConfig = { host: string; port: number };\n\n"
            "export function authenticate(): boolean { return true; }\n",
        )
        _add_test_file(project, "tests/test_auth.py", "src.auth", ["authenticate"])

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is True

    def test_strict_mode_allows_undeclared_interface(self, project):
        """Undeclared interface in files.create should not trigger E301."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-service.manifest.yaml",
            """schema: "2"
goal: "Add auth service"
files:
  create:
    - path: src/auth.ts
      artifacts:
        - kind: function
          name: authenticate
  read:
    - tests/test_auth.py
validate:
  - pytest tests/test_auth.py -v
""",
        )
        _write_source(
            project,
            "src/auth.ts",
            "interface AuthProvider {\n  validate(): boolean;\n}\n\n"
            "export function authenticate(): boolean { return true; }\n",
        )
        _add_test_file(project, "tests/test_auth.py", "src.auth", ["authenticate"])

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is True

    def test_strict_mode_allows_members_of_undeclared_interface(self, project):
        """Members of undeclared interfaces should not trigger E301."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-service.manifest.yaml",
            """schema: "2"
goal: "Add auth service"
files:
  create:
    - path: src/auth.ts
      artifacts:
        - kind: function
          name: authenticate
  read:
    - tests/test_auth.py
validate:
  - pytest tests/test_auth.py -v
""",
        )
        _write_source(
            project,
            "src/auth.ts",
            "interface AuthConfig {\n  host: string;\n  port: number;\n}\n\n"
            "export function authenticate(): boolean { return true; }\n",
        )
        _add_test_file(project, "tests/test_auth.py", "src.auth", ["authenticate"])

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is True

    def test_strict_mode_still_flags_undeclared_function(self, project):
        """Undeclared functions should still trigger E301 in strict mode."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-service.manifest.yaml",
            """schema: "2"
goal: "Add auth service"
files:
  create:
    - path: src/auth.py
      artifacts:
        - kind: function
          name: authenticate
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/auth.py",
            "def authenticate():\n    pass\n\ndef helper():\n    pass\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is False
        assert any(e.code == ErrorCode.UNEXPECTED_ARTIFACT for e in result.errors)

    def test_strict_mode_still_flags_undeclared_class(self, project):
        """Undeclared classes should still trigger E301 in strict mode."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-service.manifest.yaml",
            """schema: "2"
goal: "Add auth service"
files:
  create:
    - path: src/auth.py
      artifacts:
        - kind: function
          name: authenticate
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/auth.py",
            "def authenticate():\n    pass\n\nclass Helper:\n    pass\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is False
        assert any(e.code == ErrorCode.UNEXPECTED_ARTIFACT for e in result.errors)

    def test_strict_mode_validates_declared_interface_members(self, project):
        """If an interface IS declared, its members should still be validated."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-service.manifest.yaml",
            """schema: "2"
goal: "Add auth service"
files:
  create:
    - path: src/auth.ts
      artifacts:
        - kind: interface
          name: AuthConfig
        - kind: attribute
          name: host
          of: AuthConfig
        - kind: function
          name: authenticate
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/auth.ts",
            "interface AuthConfig {\n  host: string;\n  port: number;\n}\n\n"
            "export function authenticate(): boolean { return true; }\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        # port is undeclared but AuthConfig IS declared, so port triggers E301
        assert result.success is False
        e301_messages = [
            e.message for e in result.errors if e.code == ErrorCode.UNEXPECTED_ARTIFACT
        ]
        assert any("AuthConfig.port" in m for m in e301_messages)

    def test_strict_mode_private_type_members_allowed(self, project):
        """Members of _-prefixed types should not trigger E301 (parent privacy)."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-service.manifest.yaml",
            """schema: "2"
goal: "Add auth service"
files:
  create:
    - path: src/auth.py
      artifacts:
        - kind: function
          name: authenticate
  read:
    - tests/test_auth.py
validate:
  - pytest tests/test_auth.py -v
""",
        )
        _write_source(
            project,
            "src/auth.py",
            "class _Internal:\n    def helper(self):\n        pass\n\n"
            "def authenticate():\n    pass\n",
        )
        _add_test_file(project, "tests/test_auth.py", "src.auth", ["authenticate"])

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is True


class TestStrictModeTestFiles:
    """Test files should always use permissive mode, even when in files.create."""

    def test_test_file_in_create_allows_undeclared_helpers(self, project):
        """Test helper functions in files.create test files should not trigger E301."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-auth.manifest.yaml",
            """schema: "2"
goal: "Add auth"
files:
  create:
    - path: tests/test_auth.py
      artifacts:
        - kind: function
          name: test_authenticate
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "tests/test_auth.py",
            "def _make_user():\n    return {'name': 'test'}\n\n"
            "def test_authenticate():\n    user = _make_user()\n    assert user\n\n"
            "def test_login():\n    assert True\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        # test_login is undeclared but test files use permissive mode
        assert result.success is True

    def test_test_file_in_create_still_validates_declared_artifacts(self, project):
        """Declared artifacts in test files should still be validated."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-auth.manifest.yaml",
            """schema: "2"
goal: "Add auth"
files:
  create:
    - path: tests/test_auth.py
      artifacts:
        - kind: function
          name: test_authenticate
        - kind: function
          name: test_logout
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "tests/test_auth.py",
            "def test_authenticate():\n    assert True\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        # test_logout is declared but missing -> E300
        assert result.success is False
        assert any(e.code == ErrorCode.ARTIFACT_NOT_DEFINED for e in result.errors)


class TestSchemaErrorHandling:
    """Schema errors during manifest loading should return E004."""

    def test_schema_error_returns_e004(self, project):
        """Manifest with schema error returns SCHEMA_VALIDATION_ERROR."""
        bad_manifest = _write_manifest(
            project / "manifests",
            "bad.manifest.yaml",
            "schema: '2'\ntype: feature\nfiles:\n  create: []\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(str(bad_manifest), use_chain=False)
        assert not result.success
        error_codes = {e.code for e in result.errors}
        assert ErrorCode.SCHEMA_VALIDATION_ERROR in error_codes

    def test_manifest_load_error_returns_e001(self, project):
        """Non-existent manifest path returns FILE_NOT_FOUND."""
        engine = ValidationEngine(project_root=project)
        result = engine.validate(
            str(project / "manifests" / "nonexistent.manifest.yaml"),
            use_chain=False,
        )
        assert not result.success
        error_codes = {e.code for e in result.errors}
        assert ErrorCode.FILE_NOT_FOUND in error_codes


class TestParseErrorHandling:
    def test_python_source_syntax_error_returns_parse_error(self, project):
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(project, "src/broken.py", "def broken(:\n    pass\n")

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        assert not result.success
        assert any(e.code == ErrorCode.SOURCE_PARSE_ERROR for e in result.errors)

    def test_test_file_syntax_error_returns_parse_error(self, project):
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(project, "src/example.py", "def example():\n    return 1\n")
        _write_source(
            project, "tests/test_example.py", "def test_example(:\n    pass\n"
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        warn_codes = {w.code for w in result.warnings}
        error_codes = {e.code for e in result.errors}
        assert ErrorCode.SOURCE_PARSE_ERROR in error_codes | warn_codes


class TestFileAbsentValidation:
    """FileSpec with is_absent=True should fail when the file exists."""

    def test_is_absent_file_still_present_fails(self, project):
        """File marked absent in a create spec with status='absent' triggers E305."""
        manifest_path = _write_manifest(
            project / "manifests",
            "remove-mod.manifest.yaml",
            """schema: "2"
goal: "Remove module"
type: refactor
files:
  delete:
    - path: src/old.py
validate:
  - pytest tests/ -v
""",
        )
        _write_source(project, "src/old.py", "# should be deleted\n")

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert not result.success
        assert any(e.code == ErrorCode.FILE_SHOULD_BE_ABSENT for e in result.errors)

    def test_is_absent_file_actually_absent_passes(self, project):
        """File marked absent that does not exist passes validation."""
        manifest_path = _write_manifest(
            project / "manifests",
            "remove-mod.manifest.yaml",
            """schema: "2"
goal: "Remove module"
type: refactor
files:
  delete:
    - path: src/old.py
validate:
  - pytest tests/ -v
""",
        )
        # Don't create src/old.py

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success


class TestUnsupportedLanguage:
    """Files with unsupported extensions should produce VALIDATOR_NOT_AVAILABLE warning."""

    def test_unsupported_extension_warns(self, project):
        """A .rb file triggers VALIDATOR_NOT_AVAILABLE warning."""
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(project, "src/helper.rb", "def helper\n  'hello'\nend\n")
        _add_test_file(project, "tests/test_helper.py", "src.helper", ["helper"])

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        # Unsupported language is a warning, not an error, so validation passes
        assert result.success
        assert any(w.code == ErrorCode.VALIDATOR_NOT_AVAILABLE for w in result.warnings)

    def test_supported_extension_no_warning(self, project):
        """A .py file should NOT trigger VALIDATOR_NOT_AVAILABLE."""
        manifest_path = _write_manifest(
            project / "manifests",
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
        _write_source(project, "src/mod.py", "def helper():\n    pass\n")

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert not any(
            w.code == ErrorCode.VALIDATOR_NOT_AVAILABLE for w in result.warnings
        )


class TestCheckTestAssertionsUnit:
    """Direct unit tests for _check_test_assertions function."""

    def test_python_test_no_assertions(self):
        """Python test function without any assertion triggers MISSING_ASSERTIONS."""
        source = "def test_example():\n    x = 1 + 1\n    print(x)\n"
        errors = _check_test_assertions(source, "test_example.py")
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.MISSING_ASSERTIONS
        assert "test_example" in errors[0].message

    def test_python_test_with_assert(self):
        """Python test function with assert statement should not trigger warning."""
        source = "def test_example():\n    assert 1 + 1 == 2\n"
        errors = _check_test_assertions(source, "test_example.py")
        assert len(errors) == 0

    def test_python_non_test_function_ignored(self):
        """Functions not starting with test_ should be ignored."""
        source = "def helper():\n    x = 1\n"
        errors = _check_test_assertions(source, "test_helpers.py")
        assert len(errors) == 0

    def test_python_multiple_test_functions(self):
        """Multiple test functions: only assertion-less ones are flagged."""
        source = (
            "def test_good():\n    assert True\n\n"
            "def test_bad():\n    x = 1\n\n"
            "def test_also_good():\n    assert 1 == 1\n"
        )
        errors = _check_test_assertions(source, "test_multi.py")
        assert len(errors) == 1
        assert "test_bad" in errors[0].message

    def test_js_test_no_expect(self):
        """JS test without expect() triggers MISSING_ASSERTIONS."""
        source = (
            "test('does something', () => {\n  const x = 1;\n  console.log(x);\n});\n"
        )
        errors = _check_test_assertions(source, "example.test.js")
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.MISSING_ASSERTIONS

    def test_js_test_with_expect(self):
        """JS test with expect() should not trigger warning."""
        source = "test('does something', () => {\n  expect(1 + 1).toBe(2);\n});\n"
        errors = _check_test_assertions(source, "example.test.js")
        assert len(errors) == 0

    def test_ts_it_block_no_expect(self):
        """TS it() block without expect() triggers MISSING_ASSERTIONS."""
        source = (
            "it('should work', () => {\n"
            "  const val = calculate();\n"
            "  console.log(val);\n"
            "});\n"
        )
        errors = _check_test_assertions(source, "example.test.ts")
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.MISSING_ASSERTIONS

    def test_non_test_file_returns_empty(self):
        """Non-test file (e.g. .go) returns no errors."""
        source = "package main\nfunc main() {}\n"
        errors = _check_test_assertions(source, "main.go")
        assert len(errors) == 0

    def test_python_syntax_error_returns_empty(self):
        """Python file with syntax error returns no assertion errors."""
        source = "def test_broken(:\n    assert True\n"
        errors = _check_test_assertions(source, "test_broken.py")
        assert len(errors) == 0


class TestRequiredImportsMissing:
    """Edge cases for required imports checking."""

    def test_multiple_missing_imports(self, project):
        """Multiple missing imports each produce an E320 error."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-svc.manifest.yaml",
            """schema: "2"
goal: "Add service"
files:
  create:
    - path: src/service.py
      artifacts:
        - kind: function
          name: run_service
      imports:
        - some.module
        - another.module
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/service.py",
            "def run_service():\n    return 'ok'\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 2

    def test_partial_imports_missing(self, project):
        """When one import is present and another is missing, only the missing one errors."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-svc.manifest.yaml",
            """schema: "2"
goal: "Add service"
files:
  create:
    - path: src/service.py
      artifacts:
        - kind: function
          name: run_service
      imports:
        - os
        - missing_module
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/service.py",
            "import os\n\ndef run_service():\n    return os.getcwd()\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 1
        assert "missing_module" in import_errors[0].message


# ---------------------------------------------------------------------------
# File deletion validation (is_absent)
# ---------------------------------------------------------------------------


class TestFileDeletionValidation:
    def test_absent_file_that_exists_fails(self, project):
        """File marked as absent but still exists should fail with E307."""
        manifest_path = _write_manifest(
            project / "manifests",
            "delete-old.manifest.yaml",
            """schema: "2"
goal: "Remove old module"
type: refactor
files:
  delete:
    - path: src/old_module.py
      reason: "Migrated to new architecture"
validate:
  - echo ok
""",
        )
        # Create the file that should be deleted
        _write_source(project, "src/old_module.py", "# should be deleted\n")

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert not result.success
        error_codes = {e.code for e in result.errors}
        assert ErrorCode.FILE_SHOULD_BE_ABSENT in error_codes

    def test_absent_file_that_is_missing_passes(self, project):
        """File marked as absent that doesn't exist passes."""
        manifest_path = _write_manifest(
            project / "manifests",
            "delete-old.manifest.yaml",
            """schema: "2"
goal: "Remove old module"
type: refactor
files:
  delete:
    - path: src/old_module.py
      reason: "Migrated to new architecture"
validate:
  - echo ok
""",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        # Should not have E307 since file correctly doesn't exist
        absent_errors = [
            e for e in result.errors if e.code == ErrorCode.FILE_SHOULD_BE_ABSENT
        ]
        assert len(absent_errors) == 0


# ---------------------------------------------------------------------------
# Unsupported language validation
# ---------------------------------------------------------------------------


class TestUnsupportedLanguageValidation:
    def test_unsupported_file_extension_warns(self, project):
        """File with unsupported extension gets VALIDATOR_NOT_AVAILABLE warning."""
        manifest_path = _write_manifest(
            project / "manifests",
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
        # Create a Ruby file (no validator for Ruby)
        _write_source(project, "src/config.rb", "def load_config\n  nil\nend\n")

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        # Should have a warning about no validator
        all_issues = list(result.errors) + list(result.warnings)
        warn_codes = {e.code for e in all_issues}
        assert ErrorCode.VALIDATOR_NOT_AVAILABLE in warn_codes


# ---------------------------------------------------------------------------
# Test assertion checking
# ---------------------------------------------------------------------------


class TestAssertionCheckingFunction:
    def test_python_test_with_no_assertions(self):
        """Python test function with no assertions is flagged."""
        source = "def test_something():\n    x = 1 + 1\n"
        errors = _check_test_assertions(source, "tests/test_foo.py")
        assert len(errors) >= 1
        assert errors[0].code == ErrorCode.MISSING_ASSERTIONS

    def test_python_test_with_assert(self):
        """Python test function with assert statement is OK."""
        source = "def test_something():\n    assert 1 + 1 == 2\n"
        errors = _check_test_assertions(source, "tests/test_foo.py")
        assert len(errors) == 0

    def test_python_test_with_pytest_raises(self):
        """Python test using pytest.raises is OK."""
        source = (
            "import pytest\n"
            "def test_error():\n"
            "    with pytest.raises(ValueError):\n"
            "        raise ValueError('boom')\n"
        )
        errors = _check_test_assertions(source, "tests/test_foo.py")
        assert len(errors) == 0

    def test_python_non_test_function_ignored(self):
        """Non-test functions (no test_ prefix) are not checked."""
        source = "def helper():\n    x = 1\n"
        errors = _check_test_assertions(source, "tests/test_foo.py")
        assert len(errors) == 0

    def test_python_syntax_error_returns_empty(self):
        """Syntax error in test file returns empty list (no crash)."""
        source = "def test_broken(:\n    pass\n"
        errors = _check_test_assertions(source, "tests/test_foo.py")
        assert errors == []


class TestImplementationTestCoverage:
    """Test that implementation mode enforces test coverage.

    Manifests with public artifacts MUST have test files.
    Artifacts not referenced in tests produce warnings.
    """

    def test_no_test_files_with_public_artifacts_fails(self, project):
        """Manifest with public artifacts but zero test files -> E220 error."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: render
validate:
  - make check
""",
        )
        _write_source(project, "src/widget.py", "def render():\n    pass\n")

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is False
        assert any(e.code == ErrorCode.NO_TEST_FILES for e in result.errors)

    def test_test_file_in_read_section_passes(self, project):
        """Manifest with test file in files.read -> no E220."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: render
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def render():\n    pass\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import render\n\ndef test_render():\n    render()\n    assert True\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert not any(e.code == ErrorCode.NO_TEST_FILES for e in result.errors)

    def test_test_file_in_validate_command_passes(self, project):
        """Manifest with test file path in validate commands -> no E220."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: render
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def render():\n    pass\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import render\n\ndef test_render():\n    render()\n    assert True\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert not any(e.code == ErrorCode.NO_TEST_FILES for e in result.errors)

    def test_only_private_artifacts_no_test_required(self, project):
        """Manifest with only private artifacts -> no E220 (private doesn't need tests)."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-helper.manifest.yaml",
            """schema: "2"
goal: "Add helper"
files:
  create:
    - path: src/helper.py
      artifacts:
        - kind: function
          name: _internal_helper
validate:
  - make check
""",
        )
        _write_source(project, "src/helper.py", "def _internal_helper():\n    pass\n")

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert not any(e.code == ErrorCode.NO_TEST_FILES for e in result.errors)

    def test_no_artifacts_no_test_required(self, project):
        """Manifest with no artifacts (read-only files) -> no E220."""
        manifest_path = _write_manifest(
            project / "manifests",
            "read-only.manifest.yaml",
            """schema: "2"
goal: "Read-only task"
files:
  read:
    - src/config.py
validate:
  - make check
""",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert not any(e.code == ErrorCode.NO_TEST_FILES for e in result.errors)

    def test_artifact_not_in_test_warns(self, project):
        """Public artifact not referenced in any test -> E200 warning."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: render
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(
            project,
            "src/widget.py",
            "def render():\n    pass\n\ndef update():\n    pass\n",
        )
        # Test only references 'render', not 'update'
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import render\n\ndef test_render():\n    render()\n    assert True\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        # Should be warning, not error
        untested = [
            w for w in result.warnings if w.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_all_artifacts_in_tests_no_warnings(self, project):
        """All public artifacts referenced in tests -> no E200 warnings."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: render
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(
            project,
            "src/widget.py",
            "def render():\n    pass\n\ndef update():\n    pass\n",
        )
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import render, update\n\ndef test_render():\n    render()\n    assert True\n\ndef test_update():\n    update()\n    assert True\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        untested = [
            w for w in result.warnings if w.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert untested == []

    def test_typescript_attribute_member_access_counts_as_coverage(self, project):
        """TS property access in tests should cover declared attribute artifacts."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-vehicle-input.manifest.yaml",
            """schema: "2"
goal: "Add vehicle input"
files:
  edit:
    - path: src/vehicle.ts
      artifacts:
        - kind: interface
          name: VehicleInput
        - kind: attribute
          name: make
          of: VehicleInput
          type: string
        - kind: function
          name: buildVehicleInput
          args: []
          returns: VehicleInput
  read:
    - tests/vehicle.test.ts
validate:
  - vitest tests/vehicle.test.ts
""",
        )
        _write_source(
            project,
            "src/vehicle.ts",
            """export interface VehicleInput {
  make: string;
}

export function buildVehicleInput(): VehicleInput {
  return { make: "Toyota" };
}
""",
        )
        _write_source(
            project,
            "tests/vehicle.test.ts",
            """import { buildVehicleInput } from "../src/vehicle";

it("uses make", () => {
  const input = buildVehicleInput();
  expect(input.make).toBe("Toyota");
});
""",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        untested = [
            w for w in result.warnings if w.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert not any("make" in w.message for w in untested)

    def test_typescript_object_literal_props_count_as_attribute_coverage(self, project):
        """TSX prop objects should cover declared attribute artifacts."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-rider-dashboard.manifest.yaml",
            """schema: "2"
goal: "Add rider dashboard"
files:
  edit:
    - path: src/RiderDashboard.tsx
      artifacts:
        - kind: interface
          name: RiderDashboardProps
        - kind: attribute
          name: currentUserName
          of: RiderDashboardProps
          type: string
        - kind: attribute
          name: communityStatus
          of: RiderDashboardProps
          type: string
        - kind: function
          name: RiderDashboard
          args:
            - name: props
              type: RiderDashboardProps
          returns: JSX.Element
  read:
    - tests/RiderDashboard.test.tsx
validate:
  - vitest tests/RiderDashboard.test.tsx
""",
        )
        _write_source(
            project,
            "src/RiderDashboard.tsx",
            """export interface RiderDashboardProps {
  currentUserName: string;
  communityStatus: string;
}

export function RiderDashboard(props: RiderDashboardProps): JSX.Element {
  return <section>{props.currentUserName} {props.communityStatus}</section>;
}
""",
        )
        _write_source(
            project,
            "tests/RiderDashboard.test.tsx",
            """import { RiderDashboard } from "../src/RiderDashboard";

it("renders rider details from props", () => {
  const props = {
    currentUserName: "Ari",
    communityStatus: "active",
  };

  RiderDashboard(props);
});
""",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        untested = [
            w for w in result.warnings if w.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert not any("currentUserName" in w.message for w in untested)
        assert not any("communityStatus" in w.message for w in untested)

    def test_typescript_jsx_props_count_as_attribute_coverage(self, project):
        """Direct JSX props should cover declared attribute artifacts."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-rider-dashboard-jsx.manifest.yaml",
            """schema: "2"
goal: "Add rider dashboard"
files:
  edit:
    - path: src/RiderDashboard.tsx
      artifacts:
        - kind: interface
          name: RiderDashboardProps
        - kind: attribute
          name: currentUserName
          of: RiderDashboardProps
          type: string
        - kind: attribute
          name: communityStatus
          of: RiderDashboardProps
          type: string
        - kind: function
          name: RiderDashboard
          args:
            - name: props
              type: RiderDashboardProps
          returns: JSX.Element
  read:
    - tests/RiderDashboard.test.tsx
validate:
  - vitest tests/RiderDashboard.test.tsx
""",
        )
        _write_source(
            project,
            "src/RiderDashboard.tsx",
            """export interface RiderDashboardProps {
  currentUserName: string;
  communityStatus: string;
}

export function RiderDashboard(props: RiderDashboardProps): JSX.Element {
  return <section>{props.currentUserName} {props.communityStatus}</section>;
}
""",
        )
        _write_source(
            project,
            "tests/RiderDashboard.test.tsx",
            """import { RiderDashboard } from "../src/RiderDashboard";

it("renders rider details from direct JSX props", () => {
  <RiderDashboard currentUserName="Ari" communityStatus="active" />;
});
""",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        untested = [
            w for w in result.warnings if w.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert not any("currentUserName" in w.message for w in untested)
        assert not any("communityStatus" in w.message for w in untested)

    def test_private_artifact_not_in_test_no_warning(self, project):
        """Private artifacts not in tests -> no warning (private is optional)."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: render
        - kind: function
          name: _helper
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(
            project,
            "src/widget.py",
            "def render():\n    pass\n\ndef _helper():\n    pass\n",
        )
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import render\n\ndef test_render():\n    render()\n    assert True\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        untested = [
            w for w in result.warnings if w.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert untested == []

    def test_make_check_validate_no_test_files_fails(self, project):
        """Real-world case: validate has 'make check' only, no test paths -> E220."""
        manifest_path = _write_manifest(
            project / "manifests",
            "enhance-widget.manifest.yaml",
            """schema: "2"
goal: "Enhance widget"
type: feature
files:
  edit:
    - path: src/components/Widget.svelte
      artifacts:
        - kind: attribute
          name: STORAGE_KEY
        - kind: interface
          name: Props
        - kind: function
          name: toggleCollapsed
validate:
  - make check
""",
        )
        # Don't need the source file for this test - E220 fires before artifact checks
        # But we need it to avoid E306 (file not found)
        _write_source(
            project,
            "src/components/Widget.svelte",
            """<script>
const STORAGE_KEY = 'widget';
interface Props { title: string }
function toggleCollapsed() {}
</script>
""",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is False
        assert any(e.code == ErrorCode.NO_TEST_FILES for e in result.errors)

    def test_snapshot_manifest_exempt_from_test_coverage(self, project):
        """Snapshot manifests capture existing state — they don't require new tests."""
        manifest_path = _write_manifest(
            project / "manifests",
            "snapshot-utils.manifest.yaml",
            """schema: "2"
goal: "Snapshot utils"
type: snapshot
files:
  create:
    - path: src/utils.py
      artifacts:
        - kind: function
          name: helper
validate:
  - make check
""",
        )
        _write_source(project, "src/utils.py", "def helper():\n    pass\n")

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert not any(e.code == ErrorCode.NO_TEST_FILES for e in result.errors)


class TestStrictModeChainEnforcement:
    """When chain is active, ALL non-test files should use strict mode.

    The chain merges artifacts across all active manifests, giving the
    complete declared public API. Any undeclared public artifact must
    be flagged as E301 (UNEXPECTED_ARTIFACT), regardless of CREATE/EDIT mode.
    """

    def test_edit_mode_with_chain_rejects_undeclared(self, project):
        """EDIT manifest + chain active: undeclared public artifacts fail."""
        # Manifest 1: creates the file with func_a
        _write_manifest(
            project / "manifests",
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
        # Manifest 2: edits the file, adding func_b
        manifest2_path = _write_manifest(
            project / "manifests",
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
        # Code has func_a, func_b, AND undeclared func_c
        _write_source(
            project,
            "src/service.py",
            "def func_a():\n    pass\n\ndef func_b():\n    pass\n\ndef func_c():\n    pass\n",
        )
        _add_test_file(
            project, "tests/test_service.py", "src.service", ["func_a", "func_b"]
        )

        chain = ManifestChain(project / "manifests", project)
        engine = ValidationEngine(project_root=project)
        result = engine.validate(
            manifest2_path,
            mode=ValidationMode.IMPLEMENTATION,
            use_chain=True,
            chain=chain,
        )
        assert result.success is False
        assert any(e.code == ErrorCode.UNEXPECTED_ARTIFACT for e in result.errors)
        # Verify it's specifically func_c that's flagged
        e301_msgs = [
            e.message for e in result.errors if e.code == ErrorCode.UNEXPECTED_ARTIFACT
        ]
        assert any("func_c" in m for m in e301_msgs)

    def test_create_with_multiple_chain_manifests_stays_strict(self, project):
        """CREATE file referenced by multiple manifests: still strict with chain."""
        # Manifest 1: creates the file with func_a
        manifest1_path = _write_manifest(
            project / "manifests",
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
        # Manifest 2: edits the same file, adding func_b
        _write_manifest(
            project / "manifests",
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
        # Code has func_a, func_b, AND undeclared func_c
        _write_source(
            project,
            "src/service.py",
            "def func_a():\n    pass\n\ndef func_b():\n    pass\n\ndef func_c():\n    pass\n",
        )
        _add_test_file(
            project, "tests/test_service.py", "src.service", ["func_a", "func_b"]
        )

        chain = ManifestChain(project / "manifests", project)
        engine = ValidationEngine(project_root=project)
        # Validate the CREATE manifest — should still be strict even with 2 manifests in chain
        result = engine.validate(
            manifest1_path,
            mode=ValidationMode.IMPLEMENTATION,
            use_chain=True,
            chain=chain,
        )
        assert result.success is False
        assert any(e.code == ErrorCode.UNEXPECTED_ARTIFACT for e in result.errors)

    def test_edit_without_chain_remains_permissive(self, project):
        """Without chain, EDIT mode is permissive (no chain = incomplete picture)."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-farewell.manifest.yaml",
            """schema: "2"
goal: "Add farewell"
type: feature
files:
  edit:
    - path: src/greet.py
      artifacts:
        - kind: function
          name: farewell
  read:
    - tests/test_greet.py
validate:
  - pytest tests/test_greet.py -v
""",
        )
        # Code has both greet (undeclared) and farewell (declared)
        _write_source(
            project,
            "src/greet.py",
            'def greet(name):\n    return f"Hello, {name}!"\n\ndef farewell(name):\n    return f"Goodbye, {name}!"\n',
        )
        _add_test_file(project, "tests/test_greet.py", "src.greet", ["farewell"])

        engine = ValidationEngine(project_root=project)
        # No chain — EDIT is permissive (can't know full API without chain)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is True

    def test_chain_strict_still_allows_private(self, project):
        """Private artifacts (_prefix) are always allowed, even in chain strict mode."""
        _write_manifest(
            project / "manifests",
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
          name: do_work
  read:
    - tests/test_service.py
validate:
  - pytest tests/test_service.py -v
""",
        )
        # Code has do_work (declared) and _helper (private, allowed)
        _write_source(
            project,
            "src/service.py",
            "def do_work():\n    return _helper()\n\ndef _helper():\n    return 42\n",
        )
        _add_test_file(project, "tests/test_service.py", "src.service", ["do_work"])

        chain = ManifestChain(project / "manifests", project)
        engine = ValidationEngine(project_root=project)
        result = engine.validate(
            project / "manifests" / "create-service.manifest.yaml",
            mode=ValidationMode.IMPLEMENTATION,
            use_chain=True,
            chain=chain,
        )
        assert result.success is True

    def test_chain_strict_test_files_remain_permissive(self, project):
        """Test files always use permissive mode even with chain active."""
        manifest_path = _write_manifest(
            project / "manifests",
            "create-with-tests.manifest.yaml",
            """schema: "2"
goal: "Create module with tests"
type: feature
created: "2026-01-01"
files:
  create:
    - path: src/calc.py
      artifacts:
        - kind: function
          name: add
    - path: tests/test_calc.py
      artifacts:
        - kind: function
          name: test_add
validate:
  - pytest tests/test_calc.py -v
""",
        )
        _write_source(project, "src/calc.py", "def add(a, b):\n    return a + b\n")
        # Test file has declared test_add PLUS undeclared test_add_negative
        _write_source(
            project,
            "tests/test_calc.py",
            "from src.calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n\ndef test_add_negative():\n    assert add(-1, -2) == -3\n",
        )

        chain = ManifestChain(project / "manifests", project)
        engine = ValidationEngine(project_root=project)
        result = engine.validate(
            manifest_path,
            mode=ValidationMode.IMPLEMENTATION,
            use_chain=True,
            chain=chain,
        )
        assert result.success is True
