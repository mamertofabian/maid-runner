"""Tests for maid_runner.core.validate - ValidationEngine.

Golden test cases from 15-golden-tests.md sections 6 and 7.
"""

import pytest

from maid_runner.core.chain import ManifestChain
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
validate:
  - pytest tests/ -v
""",
        )
        _write_source(project, "src/greet.py", "def greet():\n    pass\n")

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
validate:
  - pytest tests/ -v
""",
        )
        _write_source(project, "src/greet.py", "def greet():\n    pass\n")

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
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/greet.py",
            'def greet(name):\n    return f"Hello, {name}!"\n',
        )

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
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/pages/budget.py",
            "from src.api.budgets import list_budgets\n\ndef BudgetPage():\n    data = list_budgets()\n    return data\n",
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
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/pages/budget.py",
            "from src.api.budgets import list_budgets\n\ndef BudgetPage():\n    return list_budgets()\n",
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
validate:
  - pytest
""",
            )
            _write_source(project, f"src/m{i}.py", f"def func_{i}():\n    return {i}\n")

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
validate:
  - pytest
""",
        )
        _write_source(project, "src/a.py", "def func_a():\n    return 1\n")

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
validate:
  - pytest
""",
        )
        _write_source(project, "src/a.py", "def func_a():\n    return 1\n")

        chain = ManifestChain(project / "manifests", project)
        engine = ValidationEngine(project)
        manifest = chain.active_manifests()[0]
        # use_chain=False should ignore the passed chain
        result = engine.validate(manifest, use_chain=False, chain=chain)
        assert result.success is True
        # No file tracking report when chain is not used
        assert result.file_tracking is None

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
validate:
  - pytest
""",
            )
            _write_source(
                project, f"src/perf{i}.py", f"def perf_func_{i}():\n    return {i}\n"
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
validate:
  - pytest tests/ -v
""",
        )
        _write_source(project, "src/greet.py", "def greet():\n    pass\n")

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
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/auth.ts",
            "type AuthConfig = { host: string; port: number };\n\n"
            "export function authenticate(): boolean { return true; }\n",
        )

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
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/auth.ts",
            "interface AuthProvider {\n  validate(): boolean;\n}\n\n"
            "export function authenticate(): boolean { return true; }\n",
        )

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
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/auth.py",
            "class _Internal:\n    def helper(self):\n        pass\n\n"
            "def authenticate():\n    pass\n",
        )

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
