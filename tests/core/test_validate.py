"""Tests for maid_runner.core.validate - ValidationEngine.

Golden test cases from 15-golden-tests.md sections 6 and 7.
"""

import pytest

from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import (
    ValidationEngine,
    validate,
    validate_all,
)
from maid_runner.validators._typescript_behavioral import (
    collect_behavioral_artifacts as collect_ts_behavioral_artifacts,
)
from maid_runner.validators._typescript_parse import parse_typescript_source
from maid_runner.validators.typescript import TypeScriptValidator


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


def _commit_all(project_dir):
    import subprocess

    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "add", "."], cwd=project_dir, check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            "commit",
            "-m",
            "baseline",
        ],
        cwd=project_dir,
        check=True,
        capture_output=True,
    )


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
        assert callable(ValidationEngine.validate)
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

    def test_typescript_strict_mode_allows_private_keyword_methods(self, project):
        manifest_path = _write_manifest(
            project / "manifests",
            "add-worker.manifest.yaml",
            """schema: "2"
goal: "Add worker"
files:
  create:
    - path: src/worker.ts
      artifacts:
        - kind: class
          name: Worker
        - kind: method
          name: run
          of: Worker
          args: []
          returns: string
  read:
    - tests/worker.test.ts
validate:
  - vitest run tests/worker.test.ts
""",
        )
        _write_source(
            project,
            "src/worker.ts",
            """export class Worker {
  run(): string {
    return this.format();
  }

  private format(): string {
    return 'ok';
  }

  protected audit(): void {}
}
""",
        )
        _write_source(
            project,
            "tests/worker.test.ts",
            """import { Worker } from '../src/worker';

test('worker runs', () => {
  expect(new Worker().run()).toBe('ok');
});
""",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        assert result.success is True
        assert not any(e.code == ErrorCode.UNEXPECTED_ARTIFACT for e in result.errors)

    def test_typescript_strict_mode_allows_public_getter_with_private_setter(
        self, project
    ):
        manifest_path = _write_manifest(
            project / "manifests",
            "add-meter.manifest.yaml",
            """schema: "2"
goal: "Add meter"
files:
  create:
    - path: src/meter.ts
      artifacts:
        - kind: class
          name: Meter
        - kind: method
          name: size
          of: Meter
          args: []
          returns: number
  read:
    - tests/meter.test.ts
validate:
  - vitest run tests/meter.test.ts
""",
        )
        _write_source(
            project,
            "src/meter.ts",
            """export class Meter {
  private value = 0;

  public get size(): number {
    return this.value;
  }

  private set size(value: number) {
    this.value = value;
  }
}
""",
        )
        _write_source(
            project,
            "tests/meter.test.ts",
            """import { Meter } from '../src/meter';

test('meter exposes size', () => {
  expect(new Meter().size).toBe(0);
});
""",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        assert result.success is True
        assert not any(e.code == ErrorCode.UNEXPECTED_ARTIFACT for e in result.errors)

    def test_typescript_strict_mode_allows_module_local_constants(self, project):
        manifest_path = _write_manifest(
            project / "manifests",
            "add-listing-component.manifest.yaml",
            """schema: "2"
goal: "Add listing component"
files:
  create:
    - path: src/listing.component.ts
      artifacts:
        - kind: class
          name: ListingComponent
        - kind: method
          name: render
          of: ListingComponent
          args: []
          returns: string
  read:
    - tests/listing.component.test.ts
validate:
  - vitest run tests/listing.component.test.ts
""",
        )
        _write_source(
            project,
            "src/listing.component.ts",
            """import { Component } from '@angular/core';

const LCS_DEFAULT_POINTS: Record<string, number> = {};
function localHelper(): number {
  return 1;
}

export class ListingComponent {
  render(): string {
    return String(localHelper() + Object.keys(LCS_DEFAULT_POINTS).length);
  }
}
""",
        )
        _write_source(
            project,
            "tests/listing.component.test.ts",
            """import { ListingComponent } from '../src/listing.component';

test('listing component renders', () => {
  expect(new ListingComponent().render()).toBe('1');
});
""",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        assert result.success is True
        assert not any(e.code == ErrorCode.UNEXPECTED_ARTIFACT for e in result.errors)

    def test_typescript_strict_mode_still_flags_exported_undeclared_constants(
        self, project
    ):
        manifest_path = _write_manifest(
            project / "manifests",
            "add-listing-component.manifest.yaml",
            """schema: "2"
goal: "Add listing component"
files:
  create:
    - path: src/listing.component.ts
      artifacts:
        - kind: class
          name: ListingComponent
        - kind: method
          name: render
          of: ListingComponent
          args: []
          returns: string
  read:
    - tests/listing.component.test.ts
validate:
  - vitest run tests/listing.component.test.ts
""",
        )
        _write_source(
            project,
            "src/listing.component.ts",
            """import { Component } from '@angular/core';

const LOCAL_POINTS: Record<string, number> = {};
export const PUBLIC_POINTS: Record<string, number> = {};

export class ListingComponent {
  render(): string {
    return String(Object.keys(LOCAL_POINTS).length);
  }
}
""",
        )
        _write_source(
            project,
            "tests/listing.component.test.ts",
            """import { ListingComponent } from '../src/listing.component';

test('listing component renders', () => {
  expect(new ListingComponent().render()).toBe('0');
});
""",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        assert result.success is False
        unexpected_messages = [
            e.message for e in result.errors if e.code == ErrorCode.UNEXPECTED_ARTIFACT
        ]
        assert any("PUBLIC_POINTS" in message for message in unexpected_messages)
        assert not any("LOCAL_POINTS" in message for message in unexpected_messages)

    def test_typescript_strict_mode_allows_export_assignment_target(self, project):
        manifest_path = _write_manifest(
            project / "manifests",
            "add-create-config.manifest.yaml",
            """schema: "2"
goal: "Add CommonJS config factory"
files:
  create:
    - path: src/create-config.cts
      artifacts:
        - kind: function
          name: createConfig
          args: []
          returns: Config
  read:
    - tests/create-config.test.ts
validate:
  - vitest run tests/create-config.test.ts
""",
        )
        _write_source(
            project,
            "src/create-config.cts",
            """function createConfig(): Config {
  return { ready: true };
}

function localHelper(): Config {
  return createConfig();
}

export = createConfig;
""",
        )
        _write_source(
            project,
            "tests/create-config.test.ts",
            """import createConfig = require('../src/create-config');

test('config can be created', () => {
  expect(createConfig()).toEqual({ ready: true });
});
""",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        assert result.success is True
        assert not any(e.code == ErrorCode.UNEXPECTED_ARTIFACT for e in result.errors)

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

    def test_validate_command_directory_discovers_nested_test_files(self, project):
        """A validate command may point at a test directory, not one file."""
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
        _write_source(project, "src/greet.py", "def greet():\n    return 'hello'\n")
        _write_source(
            project,
            "tests/unit/test_greet.py",
            "from src.greet import greet\n\n"
            "def test_greet():\n"
            "    assert greet() == 'hello'\n",
        )

        engine = ValidationEngine(project_root=project)
        assert callable(ValidationEngine.validate_all)
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


class TestManifestPathContainment:
    def test_validate_rejects_file_spec_path_that_escapes_project_root(self, project):
        outside = project.parent / "outside.py"
        outside.write_text("def escaped():\n    return None\n")
        manifest_path = _write_manifest(
            project / "manifests",
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

        assert not result.success
        assert [error.code for error in result.errors] == [
            ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
        ]
        assert result.errors[0].location is not None
        assert result.errors[0].location.file == "../outside.py"

    def test_behavioral_validate_rejects_escaped_test_path_from_files_read(
        self, project
    ):
        outside_tests = project.parent / "outside"
        outside_tests.mkdir(exist_ok=True)
        (outside_tests / "test_contract.py").write_text(
            "from src.app import run\n\n"
            "def test_run():\n"
            "    assert run is not None\n"
        )
        manifest_path = _write_manifest(
            project / "manifests",
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

        assert not result.success
        assert [error.code for error in result.errors] == [
            ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
        ]
        assert result.errors[0].location is not None
        assert result.errors[0].location.file == "../outside/test_contract.py"

    def test_validate_rejects_delete_path_that_escapes_project_root(self, project):
        outside = project.parent / "old.py"
        outside.write_text("# should not be checked through MAID\n")
        manifest_path = _write_manifest(
            project / "manifests",
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

        assert not result.success
        assert [error.code for error in result.errors] == [
            ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
        ]
        assert result.errors[0].location is not None
        assert result.errors[0].location.file == "../old.py"
        assert all(
            error.code != ErrorCode.FILE_SHOULD_BE_ABSENT for error in result.errors
        )

    def test_behavioral_validate_rejects_escaped_test_path_from_validate_command(
        self, project
    ):
        outside_tests = project.parent / "outside"
        outside_tests.mkdir(exist_ok=True)
        (outside_tests / "test_contract.py").write_text(
            "from src.app import run\n\n"
            "def test_run():\n"
            "    assert run is not None\n"
        )
        manifest_path = _write_manifest(
            project / "manifests",
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

        assert not result.success
        assert [error.code for error in result.errors] == [
            ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
        ]
        assert result.errors[0].location is not None
        assert result.errors[0].location.file == "../outside/test_contract.py"

    def test_behavioral_validate_rejects_escaped_equal_option_path_from_validate_command(
        self, project
    ):
        outside_tests = project.parent / "outside-suite"
        outside_tests.mkdir(exist_ok=True)
        (outside_tests / "test_contract.py").write_text(
            "from src.app import run\n\n"
            "def test_run():\n"
            "    assert run is not None\n"
        )
        manifest_path = _write_manifest(
            project / "manifests",
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

        assert not result.success
        assert [error.code for error in result.errors] == [
            ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
        ]
        assert result.errors[0].location is not None
        assert result.errors[0].location.file == "../outside-suite"

    def test_validate_rejects_escaped_acceptance_test_path(self, project):
        outside_tests = project.parent / "outside"
        outside_tests.mkdir(exist_ok=True)
        (outside_tests / "test_acceptance.py").write_text(
            "def test_acceptance():\n    assert True\n"
        )
        _write_source(project, "src/app.py", "def run():\n    return None\n")
        manifest_path = _write_manifest(
            project / "manifests",
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

        assert not result.success
        assert [error.code for error in result.errors] == [
            ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
        ]
        assert result.errors[0].location is not None
        assert result.errors[0].location.file == "../outside/test_acceptance.py"
        assert all(
            error.code != ErrorCode.ACCEPTANCE_TEST_FILE_NOT_FOUND
            for error in result.errors
        )

    def test_validate_rejects_removed_artifact_path_that_escapes_project_root(
        self, project
    ):
        outside = project.parent / "outside.py"
        outside.write_text("def removed():\n    return None\n")
        _write_source(project, "src/app.py", "def run():\n    return None\n")
        manifest_path = _write_manifest(
            project / "manifests",
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

        assert not result.success
        assert [error.code for error in result.errors] == [
            ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
        ]
        assert result.errors[0].location is not None
        assert result.errors[0].location.file == "../outside.py"
        assert all(
            error.code != ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT
            for error in result.errors
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
    def test_validate_all_file_tracking_gate_fails_on_undeclared_source(self, project):
        """validate_all can fail on undeclared production source files."""
        _write_manifest(
            project / "manifests",
            "add-app.manifest.yaml",
            """schema: "2"
goal: "Add app"
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: run
  read:
    - tests/test_app.py
validate:
  - pytest tests/test_app.py -v
""",
        )
        _write_source(project, "src/app.py", "def run():\n    return 'ok'\n")
        _write_source(project, "src/extra.py", "def extra():\n    return 'drift'\n")
        _add_test_file(project, "tests/test_app.py", "src.app", ["run"])

        engine = ValidationEngine(project_root=project)
        result = engine.validate_all(project / "manifests", check_file_tracking=True)

        assert result.success is False
        reports = [r.file_tracking for r in result.results if r.file_tracking]
        assert reports
        assert any(
            entry.path == "src/extra.py"
            for report in reports
            for entry in report.undeclared
        )

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

    def test_worktree_scope_gate_reports_changed_production_file_outside_manifest_scope(
        self, project
    ):
        """Changed production files must be writable in the active manifest chain."""
        import subprocess

        from maid_runner.core.worktree import changed_files, validate_worktree_scope

        _write_manifest(
            project / "manifests",
            "add-app.manifest.yaml",
            """schema: "2"
goal: "Add app"
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: run
validate:
  - pytest tests/test_app.py -v
""",
        )
        _write_source(project, "src/app.py", "def run():\n    return 'ok'\n")
        _write_source(project, "src/drift.py", "def drift():\n    return 'drift'\n")
        subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)

        chain = ManifestChain(project / "manifests", project_root=project)
        errors = validate_worktree_scope(project, chain)

        assert "src/drift.py" in changed_files(project)
        assert any(
            error.code == ErrorCode.CHANGED_FILE_OUTSIDE_MANIFEST_SCOPE
            and error.location
            and error.location.file == "src/drift.py"
            for error in errors
        )

    def test_worktree_scope_gate_allows_changed_file_in_files_edit(self, project):
        """Changed production files listed in files.edit are inside writable scope."""
        import subprocess

        from maid_runner.core.worktree import validate_worktree_scope

        _write_manifest(
            project / "manifests",
            "edit-app.manifest.yaml",
            """schema: "2"
goal: "Edit app"
files:
  edit:
    - path: src/app.py
      artifacts:
        - kind: function
          name: run
validate:
  - pytest tests/test_app.py -v
""",
        )
        _write_source(project, "src/app.py", "def run():\n    return 'changed'\n")
        subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)

        chain = ManifestChain(project / "manifests", project_root=project)

        assert validate_worktree_scope(project, chain) == []

    def test_worktree_scope_gate_treats_files_read_as_not_writable(self, project):
        """files.read gives context, not permission to change production code."""
        import subprocess

        from maid_runner.core.worktree import validate_worktree_scope

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
  - pytest tests/test_app.py -v
""",
        )
        _write_source(project, "src/app.py", "def run():\n    return 'ok'\n")
        _write_source(project, "src/dep.py", "def helper():\n    return 'changed'\n")
        subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)

        chain = ManifestChain(project / "manifests", project_root=project)
        errors = validate_worktree_scope(project, chain)

        assert any(
            error.code == ErrorCode.CHANGED_FILE_OUTSIDE_MANIFEST_SCOPE
            and error.location
            and error.location.file == "src/dep.py"
            for error in errors
        )

    def test_worktree_scope_gate_reports_rename_source_outside_writable_scope(
        self, project
    ):
        """A git rename must check the deleted source path, not only the destination."""
        import subprocess

        from maid_runner.core.worktree import changed_files, validate_worktree_scope

        _write_manifest(
            project / "manifests",
            "add-new.manifest.yaml",
            """schema: "2"
goal: "Add renamed module"
files:
  create:
    - path: src/new.py
      artifacts:
        - kind: function
          name: old
validate:
  - pytest tests/test_new.py -v
""",
        )
        _write_source(project, "src/old.py", "def old():\n    return 'old'\n")
        _commit_all(project)
        subprocess.run(
            ["git", "mv", "src/old.py", "src/new.py"],
            cwd=project,
            check=True,
            capture_output=True,
        )

        chain = ManifestChain(project / "manifests", project_root=project)
        paths = changed_files(project)
        errors = validate_worktree_scope(project, chain)

        assert "src/new.py" in paths
        assert "src/old.py" in paths
        assert any(
            error.code == ErrorCode.CHANGED_FILE_OUTSIDE_MANIFEST_SCOPE
            and error.location
            and error.location.file == "src/old.py"
            for error in errors
        )
        assert not any(
            error.location and error.location.file == "src/new.py" for error in errors
        )

    def test_worktree_scope_gate_includes_test_files_only_when_requested(self, project):
        """Changed test files are ignored by default and checked on request."""
        import subprocess

        from maid_runner.core.worktree import validate_worktree_scope

        _write_manifest(
            project / "manifests",
            "add-app.manifest.yaml",
            """schema: "2"
goal: "Add app"
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: run
  read:
    - tests/test_app.py
validate:
  - pytest tests/test_app.py -v
""",
        )
        _write_source(project, "src/app.py", "def run():\n    return 'ok'\n")
        _write_source(project, "tests/test_app.py", "from src.app import run\n")
        subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)

        chain = ManifestChain(project / "manifests", project_root=project)

        assert validate_worktree_scope(project, chain) == []
        errors = validate_worktree_scope(project, chain, include_tests=True)
        assert any(
            error.code == ErrorCode.CHANGED_FILE_OUTSIDE_MANIFEST_SCOPE
            and error.location
            and error.location.file == "tests/test_app.py"
            for error in errors
        )

    def test_changed_files_returns_paths_relative_to_nested_project_root(
        self, tmp_path
    ):
        """Nested project roots should not receive repo-root-relative paths."""
        from maid_runner.core.worktree import changed_files

        repo = tmp_path / "repo"
        project_root = repo / "project"
        (project_root / "src").mkdir(parents=True)
        (repo / "outside").mkdir(parents=True)
        (project_root / "src" / "app.py").write_text(
            "def run():\n    return 'before'\n"
        )
        (repo / "outside" / "other.py").write_text(
            "def other():\n    return 'before'\n"
        )
        _commit_all(repo)

        (project_root / "src" / "app.py").write_text("def run():\n    return 'after'\n")
        (repo / "outside" / "other.py").write_text("def other():\n    return 'after'\n")

        assert changed_files(project_root) == ("src/app.py",)


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

    def test_abstract_method_not_detected_as_stub_warning(self, project):
        """Abstract method placeholders define contracts and are not stubs."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-base.manifest.yaml",
            """schema: "2"
goal: "Add base class"
files:
  create:
    - path: src/base.py
      artifacts:
        - kind: class
          name: Base
        - kind: method
          name: run
          of: Base
  read:
    - tests/test_base.py
validate:
  - pytest tests/test_base.py -v
""",
        )
        _write_source(
            project,
            "src/base.py",
            "from abc import ABC, abstractmethod\n\n"
            "class Base(ABC):\n"
            "    @abstractmethod\n"
            "    def run(self):\n"
            "        pass\n",
        )
        _write_source(
            project,
            "tests/test_base.py",
            "from src.base import Base\n\n"
            "def test_base_declares_run_contract():\n"
            "    assert Base.run.__name__ == 'run'\n",
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

    def test_custom_abstractmethod_attribute_detected_as_stub_warning(self, project):
        """Only abc.abstractmethod suppresses stub warnings."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-base.manifest.yaml",
            """schema: "2"
goal: "Add base class"
files:
  create:
    - path: src/base.py
      artifacts:
        - kind: class
          name: Base
        - kind: method
          name: run
          of: Base
  read:
    - tests/test_base.py
validate:
  - pytest tests/test_base.py -v
""",
        )
        _write_source(
            project,
            "src/base.py",
            "class _Fake:\n"
            "    def abstractmethod(self, fn):\n"
            "        return fn\n\n"
            "_fake = _Fake()\n\n"
            "class Base:\n"
            "    @_fake.abstractmethod\n"
            "    def run(self):\n"
            "        pass\n",
        )
        _write_source(
            project,
            "tests/test_base.py",
            "from src.base import Base\n\n"
            "def test_base_declares_run_contract():\n"
            "    assert Base.run.__name__ == 'run'\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(
            manifest_path,
            mode=ValidationMode.IMPLEMENTATION,
            check_stubs=True,
        )

        assert result.success is True
        assert any(w.code == ErrorCode.STUB_FUNCTION_DETECTED for w in result.warnings)

    def test_typescript_generic_type_parameters_are_validated(self, project):
        """Manifest-declared generic parameters must match implementation artifacts."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-store.manifest.yaml",
            """schema: "2"
goal: "Add generic store"
files:
  create:
    - path: src/store.ts
      artifacts:
        - kind: class
          name: Store
          type_parameters:
            - T extends Item = Item
validate:
  - pytest tests/test_store.py -v
""",
        )
        _write_source(
            project,
            "src/store.ts",
            "export class Store<T extends Other = Other> {}\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        assert any(e.code == ErrorCode.TYPE_MISMATCH for e in result.errors)
        assert any("type parameters" in e.message for e in result.errors)


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


class TestStrictWarningPolicy:
    def test_validate_fail_on_warnings_marks_result_unsuccessful(self, project):
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
            fail_on_warnings=True,
        )

        assert result.success is False
        assert result.errors == []
        assert any(w.code == ErrorCode.STUB_FUNCTION_DETECTED for w in result.warnings)

    def test_validate_all_threads_strict_warning_policy_to_each_manifest(self, project):
        _write_manifest(
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
        batch = engine.validate_all(
            project / "manifests",
            mode=ValidationMode.IMPLEMENTATION,
            check_stubs=True,
            fail_on_warnings=True,
        )

        assert batch.success is False
        assert batch.passed == 0
        assert batch.failed == 1
        assert any(
            w.code == ErrorCode.STUB_FUNCTION_DETECTED
            for result in batch.results
            for w in result.warnings
        )

    def test_validate_all_function_threads_strict_warning_policy_to_each_manifest(
        self, project
    ):
        _write_manifest(
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
            w.code == ErrorCode.STUB_FUNCTION_DETECTED
            for result in batch.results
            for w in result.warnings
        )


class TestImportVerification:
    """Tests for required imports field on FileSpec."""

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

    def test_ts_required_import_accepts_tsconfig_alias_when_compiler_resolution_is_needed(
        self, project
    ):
        """Tsconfig path alias resolves to project-local module for E320 check."""
        import json

        (project / "tsconfig.json").write_text(
            json.dumps(
                {
                    "compilerOptions": {
                        "baseUrl": ".",
                        "paths": {"@app/*": ["./src/*"]},
                    }
                }
            )
        )
        # Target must exist so tsconfig path resolution can confirm it
        models_dir = project / "src" / "models"
        models_dir.mkdir(parents=True, exist_ok=True)
        (models_dir / "Budget.ts").write_text("export class Budget {}\n")

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
            'import { Budget } from "@app/models/Budget";\n\nexport function BudgetPage() { return new Budget(); }\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_ts_required_import_accepts_workspace_package_export_when_compiler_resolution_is_needed(
        self, project, monkeypatch
    ):
        """Workspace package import resolved by compiler bridge passes E320 check."""
        import sys
        from maid_runner.core.ts_module_paths import resolve_ts_import as _real_resolve

        _validate_module = sys.modules["maid_runner.core.validate"]

        def fake_resolve_ts_import(specifier, importer_module, root):
            if specifier == "@workspace/budget":
                return "src/packages/budget"
            return _real_resolve(specifier, importer_module, root)

        monkeypatch.setattr(
            _validate_module, "resolve_ts_import", fake_resolve_ts_import
        )

        manifest_path = _write_manifest(
            project / "manifests",
            "add-app.manifest.yaml",
            """schema: "2"
goal: "Add workspace consumer"
files:
  create:
    - path: src/App.ts
      artifacts:
        - kind: function
          name: App
      imports:
        - src/packages/budget
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/App.ts",
            'import { Budget } from "@workspace/budget";\n\nexport function App() { return new Budget(); }\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_ts_required_import_does_not_resolve_unrelated_bare_imports(
        self, project, monkeypatch
    ):
        """Compiler bridge is not invoked when required imports are already present."""
        import sys

        assert callable(ValidationEngine.validate)
        assert callable(validate)
        _validate_module = sys.modules["maid_runner.core.validate"]
        compiler_calls: list[str] = []

        def track_resolve_ts_import(specifier, importer_module, root):
            compiler_calls.append(specifier)
            return specifier

        monkeypatch.setattr(
            _validate_module, "resolve_ts_import", track_resolve_ts_import
        )

        manifest_path = _write_manifest(
            project / "manifests",
            "add-app.manifest.yaml",
            """schema: "2"
goal: "Add app"
files:
  create:
    - path: src/App.ts
      artifacts:
        - kind: function
          name: App
      imports:
        - pkg0
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/App.ts",
            "\n".join(
                [f'import {{ value{i} }} from "pkg{i}";' for i in range(5)]
                + ["export function App() { return value0; }"]
            ),
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0
        assert compiler_calls == []

    def test_ts_required_import_resolves_only_relevant_unresolved_bare_imports(
        self, project, monkeypatch
    ):
        """Compiler bridge skips unrelated bare imports while resolving a required alias."""
        import sys

        _validate_module = sys.modules["maid_runner.core.validate"]
        compiler_calls: list[str] = []

        def fake_resolve_ts_import(specifier, importer_module, root):
            compiler_calls.append(specifier)
            if specifier == "@design/system":
                return "src/models/Budget"
            return specifier

        monkeypatch.setattr(
            _validate_module, "resolve_ts_import", fake_resolve_ts_import
        )

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
            'import { left } from "unrelated-left";\n'
            'import { Budget } from "@design/system";\n'
            'import { right } from "unrelated-right";\n\n'
            "export function BudgetPage() { return new Budget(); }\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0
        assert compiler_calls == ["@design/system"]

    def test_ts_required_import_accepts_package_barrel_reexport_target(self, project):
        """Package-style import can satisfy a required import behind a barrel."""
        import json

        (project / "tsconfig.json").write_text(
            json.dumps(
                {
                    "compilerOptions": {
                        "baseUrl": ".",
                        "paths": {"@design/system": ["packages/ui/src"]},
                    }
                }
            )
        )
        ui_src = project / "packages" / "ui" / "src"
        ui_src.mkdir(parents=True)
        (ui_src / "index.ts").write_text(
            'export { Button } from "./Button";\n', encoding="utf-8"
        )
        (ui_src / "Button.ts").write_text(
            "export function Button() { return null; }\n", encoding="utf-8"
        )

        manifest_path = _write_manifest(
            project / "manifests",
            "add-app.manifest.yaml",
            """schema: "2"
goal: "Add app"
files:
  create:
    - path: src/App.ts
      artifacts:
        - kind: function
          name: App
      imports:
        - packages/ui/src/Button
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/App.ts",
            'import { Button } from "@design/system";\n\nexport function App() { return Button(); }\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0

    def test_ts_required_import_rejects_unimported_package_barrel_reexport_target(
        self, project
    ):
        """A barrel target only counts when its binding is imported from that barrel."""
        import json

        (project / "tsconfig.json").write_text(
            json.dumps(
                {
                    "compilerOptions": {
                        "baseUrl": ".",
                        "paths": {"@design/system": ["packages/ui/src"]},
                    }
                }
            )
        )
        ui_src = project / "packages" / "ui" / "src"
        ui_src.mkdir(parents=True)
        (ui_src / "index.ts").write_text(
            'export { Button } from "./Button";\n' 'export { Theme } from "./Theme";\n',
            encoding="utf-8",
        )
        (ui_src / "Button.ts").write_text(
            "export function Button() { return null; }\n", encoding="utf-8"
        )
        (ui_src / "Theme.ts").write_text(
            "export function Theme() { return null; }\n", encoding="utf-8"
        )

        manifest_path = _write_manifest(
            project / "manifests",
            "add-app.manifest.yaml",
            """schema: "2"
goal: "Add app"
files:
  create:
    - path: src/App.ts
      artifacts:
        - kind: function
          name: App
      imports:
        - packages/ui/src/Button
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/App.ts",
            'import { Button } from "unrelated-kit";\n'
            'import { Theme } from "@design/system";\n\n'
            "export function App() { return Theme() || Button(); }\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 1

    def test_ts_required_import_rejects_aliased_different_barrel_binding(self, project):
        """A local alias does not count as importing a different barrel export."""
        import json

        (project / "tsconfig.json").write_text(
            json.dumps(
                {
                    "compilerOptions": {
                        "baseUrl": ".",
                        "paths": {"@design/system": ["packages/ui/src"]},
                    }
                }
            )
        )
        ui_src = project / "packages" / "ui" / "src"
        ui_src.mkdir(parents=True)
        (ui_src / "index.ts").write_text(
            'export { Button } from "./Button";\n' 'export { Theme } from "./Theme";\n',
            encoding="utf-8",
        )
        (ui_src / "Button.ts").write_text(
            "export function Button() { return null; }\n", encoding="utf-8"
        )
        (ui_src / "Theme.ts").write_text(
            "export function Theme() { return null; }\n", encoding="utf-8"
        )

        manifest_path = _write_manifest(
            project / "manifests",
            "add-app.manifest.yaml",
            """schema: "2"
goal: "Add app"
files:
  create:
    - path: src/App.ts
      artifacts:
        - kind: function
          name: App
      imports:
        - packages/ui/src/Button
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/App.ts",
            'import { Theme as Button } from "@design/system";\n\n'
            "export function App() { return Button(); }\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 1

    def test_ts_required_import_does_not_invoke_compiler_for_relative_imports(
        self, project, monkeypatch
    ):
        """Relative TS import is resolved through fast path without invoking compiler bridge."""
        from maid_runner.core import ts_compiler_resolver

        def fail_if_compiler_called(*args, **kwargs):
            raise AssertionError("compiler bridge must not run for relative imports")

        monkeypatch.setattr(
            ts_compiler_resolver, "_run_compiler_request", fail_if_compiler_called
        )

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

    def test_ts_required_import_keeps_third_party_package_boundary_with_compiler_available(
        self, project, monkeypatch
    ):
        """Third-party package import is not resolved through compiler; passes as-is."""
        from maid_runner.core import ts_compiler_resolver

        compiler_calls: list = []

        def track_compiler_calls(*args, **kwargs):
            compiler_calls.append(args)
            return None

        monkeypatch.setattr(
            ts_compiler_resolver, "_run_compiler_request", track_compiler_calls
        )

        # Install react to node_modules so it registers as an external package
        react_dir = project / "node_modules" / "react"
        react_dir.mkdir(parents=True)
        (react_dir / "package.json").write_text(
            '{"name": "react", "main": "index.js"}\n'
        )

        manifest_path = _write_manifest(
            project / "manifests",
            "add-component.manifest.yaml",
            """schema: "2"
goal: "Add React component"
files:
  create:
    - path: src/App.tsx
      artifacts:
        - kind: function
          name: App
      imports:
        - react
validate:
  - pytest tests/ -v
""",
        )
        _write_source(
            project,
            "src/App.tsx",
            'import React from "react";\n\nexport function App() { return React.createElement("div"); }\n',
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        import_errors = [
            e for e in result.errors if e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        ]
        assert len(import_errors) == 0
        assert (
            len(compiler_calls) == 0
        ), "compiler must not be invoked for external packages"


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

    def test_validate_all_fails_when_manifest_dir_is_missing_by_default(self, tmp_path):
        engine = ValidationEngine(tmp_path)

        result = engine.validate_all("missing-manifests")

        assert result.success is False
        assert result.total_manifests == 0
        assert result.failed == 1
        assert any(e.code == ErrorCode.EMPTY_MANIFEST_SET for e in result.chain_errors)
        assert "missing-manifests" in result.chain_errors[0].message

    def test_validate_all_fails_when_manifest_dir_contains_no_active_manifests(
        self, tmp_path
    ):
        manifest_dir = tmp_path / "manifests"
        (manifest_dir / "drafts").mkdir(parents=True)
        _write_manifest(
            manifest_dir / "drafts",
            "future.manifest.yaml",
            """# draft-kind: implementation
schema: "2"
goal: "Future draft"
files:
  create:
    - path: src/future.py
      artifacts:
        - kind: function
          name: future
validate:
  - pytest
""",
        )
        engine = ValidationEngine(tmp_path)

        result = engine.validate_all("manifests")

        assert result.success is False
        assert result.total_manifests == 0
        assert result.failed == 1
        assert any(e.code == ErrorCode.EMPTY_MANIFEST_SET for e in result.chain_errors)
        assert "No active manifests discovered" in result.chain_errors[0].message

    def test_validate_all_allows_empty_manifest_set_only_when_explicit(self, tmp_path):
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        engine = ValidationEngine(tmp_path)

        result = engine.validate_all("manifests", allow_empty=True)

        assert result.success is True
        assert result.total_manifests == 0
        assert result.passed == 0
        assert result.failed == 0
        assert result.chain_errors == []

    def test_validate_all_function_allows_empty_manifest_set_only_when_explicit(
        self, tmp_path
    ):
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        result = validate_all("manifests", project_root=tmp_path, allow_empty=True)

        assert result.success is True
        assert result.total_manifests == 0
        assert result.passed == 0
        assert result.failed == 0
        assert result.chain_errors == []

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
            "export interface AuthConfig {\n  host: string;\n  port: number;\n}\n\n"
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
            "export interface AuthConfig {\n  host: string;\n  port: number;\n}\n\n"
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


class TestImplementationTestCoverage:
    """Test that implementation mode enforces test coverage.

    Manifests with public artifacts MUST have test files.
    Artifacts not referenced in tests produce warnings.
    """

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

    def test_implementation_fails_when_public_artifact_not_referenced_in_tests(
        self, project
    ):
        """Public artifact not referenced in any test -> E200 error."""
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
        assert result.success is False
        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert len(untested) == 1
        assert "update" in untested[0].message
        assert untested[0].severity.value == "error"

    def test_python_import_only_reference_does_not_satisfy_coverage(self, project):
        """Import declarations alone are not behavioral coverage."""
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
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import update\n\n"
            "def test_widget_placeholder():\n"
            "    assert True\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_src_layout_import_covers_manifest_artifact_without_src_prefix(
        self, project
    ):
        """A src-layout import can cover a manifest path that includes src/."""
        manifest_path = _write_manifest(
            project / "manifests",
            "score-payloads.manifest.yaml",
            """schema: "2"
goal: "Expose score payload serializers"
type: fix
files:
  edit:
    - path: src/ai_analysis/services/score_payloads.py
      artifacts:
        - kind: function
          name: build_rufus_score_payload
  read:
    - tests/test_score_payloads.py
validate:
  - pytest tests/test_score_payloads.py -v
""",
        )
        _write_source(
            project,
            "src/ai_analysis/services/score_payloads.py",
            "def build_rufus_score_payload(value):\n    return value\n",
        )
        _write_source(
            project,
            "tests/test_score_payloads.py",
            "from ai_analysis.services.score_payloads import "
            "build_rufus_score_payload\n\n"
            "def test_build_rufus_score_payload_includes_split_scores():\n"
            "    assert build_rufus_score_payload({'copy_score': 8})"
            " == {'copy_score': 8}\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is True
        assert untested == []

    def test_python_importlib_dynamic_module_attribute_covers_numeric_migration_class(
        self, project
    ):
        """A literal importlib module load can cover numeric migration modules."""
        manifest_path = _write_manifest(
            project / "manifests",
            "split-scores.manifest.yaml",
            """schema: "2"
goal: "Add split scores migration"
type: fix
files:
  edit:
    - path: src/ai_analysis/migrations/0023_split_scores_and_cosmo_evidence.py
      artifacts:
        - kind: class
          name: Migration
        - kind: attribute
          name: dependencies
          of: Migration
          type: list
        - kind: attribute
          name: operations
          of: Migration
          type: list
  read:
    - tests/test_split_scores_migration.py
validate:
  - pytest tests/test_split_scores_migration.py -v
""",
        )
        _write_source(
            project,
            "src/ai_analysis/migrations/0023_split_scores_and_cosmo_evidence.py",
            "class Migration:\n"
            "    dependencies = [('ai_analysis', '0022_previous')]\n"
            "    operations = ['split_scores']\n",
        )
        _write_source(
            project,
            "tests/test_split_scores_migration.py",
            "import importlib\n\n"
            "def test_split_scores_migration_declares_dependencies():\n"
            "    module = importlib.import_module(\n"
            "        'ai_analysis.migrations.0023_split_scores_and_cosmo_evidence'\n"
            "    )\n"
            "    Migration = module.Migration\n"
            "    assert Migration.dependencies\n"
            "    assert Migration.operations\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is True
        assert untested == []

    @pytest.mark.parametrize(
        ("test_source", "scenario"),
        [
            (
                "def update():\n"
                "    return 'local'\n\n"
                "def test_widget_local_update():\n"
                "    assert update() == 'local'\n",
                "local helper before test",
            ),
            (
                "def test_widget_bare_update_call():\n"
                "    update()\n"
                "    assert True\n",
                "bare same-name call with no import",
            ),
            (
                "from src.other import noop\n\n"
                "def test_widget_bare_update_call_with_unrelated_import():\n"
                "    assert noop() == 'noop'\n"
                "    update()\n",
                "bare same-name call with unrelated import",
            ),
            (
                "def test_widget_late_local_update():\n"
                "    assert update() == 'local'\n\n"
                "def update():\n"
                "    return 'local'\n",
                "local helper after test",
            ),
            (
                "update = lambda: 'local'\n\n"
                "def test_widget_assigned_update():\n"
                "    assert update() == 'local'\n",
                "local callable assignment",
            ),
            (
                "class Local:\n"
                "    def update(self):\n"
                "        return 'local'\n\n"
                "def test_widget_local_method_update():\n"
                "    assert Local().update() == 'local'\n",
                "local method call",
            ),
        ],
    )
    def test_python_local_function_without_identity_import_does_not_cover_artifact(
        self, project, test_source, scenario
    ):
        """A local same-name helper without an import is not production coverage."""
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
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(project, "src/other.py", "def noop():\n    return 'noop'\n")
        _write_source(project, "tests/test_widget.py", test_source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_shadowed_import_reference_does_not_satisfy_coverage(self, project):
        """A local test helper with the same name as an import is not coverage."""
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
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import update\n\n"
            "def test_widget_shadow():\n"
            "    def update():\n"
            "        return 'local'\n"
            "    assert update() == 'local'\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_shadowed_import_before_later_import_does_not_cover_artifact(
        self, project
    ):
        """Shadow detection is not dependent on source order of imports."""
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
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "def test_widget_shadow():\n"
            "    def update():\n"
            "        return 'local'\n"
            "    assert update() == 'local'\n\n"
            "from src.widget import update\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_module_rebinding_after_import_does_not_cover_artifact(
        self, project
    ):
        """A module-level local rebinding after import is not production coverage."""
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
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import update\n\n"
            "def update():\n"
            "    return 'local'\n\n"
            "def test_widget_shadow():\n"
            "    assert update() == 'local'\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_alias_placeholder_import_does_not_cover_local_artifact(
        self, project
    ):
        """Importing the artifact under an alias does not cover a local namesake."""
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
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import update as real_update\n\n"
            "def update():\n"
            "    return 'local'\n\n"
            "def test_widget_shadow():\n"
            "    assert update() == 'local'\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_module_placeholder_import_does_not_cover_local_artifact(
        self, project
    ):
        """Importing the artifact module under an alias is not local coverage."""
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
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "import src.widget as widget_module\n\n"
            "def update():\n"
            "    return 'local'\n\n"
            "def test_widget_shadow():\n"
            "    assert update() == 'local'\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_function_local_import_still_covers_after_module_shadow(
        self, project
    ):
        """A real function-local import keeps identity despite module rebinding."""
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
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import update\n\n"
            "def update():\n"
            "    return 'local'\n\n"
            "def test_widget_imports_real_update():\n"
            "    from src.widget import update\n"
            "    assert update() == 'updated'\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is True
        assert untested == []

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "from src.widget import update\n\n"
                "def test_widget_lambda_shadow():\n"
                "    assert (lambda update: update())(lambda: 'local') == 'local'\n",
                "lambda parameter",
            ),
            (
                "from src.widget import update\n\n"
                "def test_widget_comprehension_shadow():\n"
                "    values = [update() for update in [lambda: 'local']]\n"
                "    assert values == ['local']\n",
                "comprehension target",
            ),
        ],
    )
    def test_python_expression_scope_shadowed_import_does_not_cover_artifact(
        self, project, source, scenario
    ):
        """Lambda and comprehension-local names are not production coverage."""
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
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(project, "tests/test_widget.py", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "update" in untested[0].message

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "from src.widget import update\n\n"
                "def test_widget_walrus_shadow():\n"
                "    assert (update := (lambda: 'local'))() == 'local'\n",
                "walrus binding",
            ),
            (
                "from src.widget import update\n\n"
                "def test_widget_match_shadow():\n"
                "    match (lambda: 'local'):\n"
                "        case update:\n"
                "            assert update() == 'local'\n",
                "match capture",
            ),
        ],
    )
    def test_python_binding_expression_shadowed_import_does_not_cover_artifact(
        self, project, source, scenario
    ):
        """Walrus and match bindings are not production coverage."""
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
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(project, "tests/test_widget.py", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_annotation_only_reference_does_not_cover_artifact(self, project):
        """Python type annotations are not behavioral runtime coverage."""
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
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import update\n\n"
            "def test_widget_annotation_only(value: update = None) -> update:\n"
            "    assert value is None\n"
            "    return None\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_keyword_argument_does_not_cover_same_module_artifact(self, project):
        """A keyword name passed to one function does not cover another artifact."""
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
            "def render(**kwargs):\n    return kwargs\n\n"
            "def update():\n    return 'updated'\n",
        )
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import render\n\n"
            "def test_widget_render_flag():\n"
            "    assert render(update=True) == {'update': True}\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "from src.widget import update\n\n"
                "def test_widget_starred_assignment_shadow():\n"
                "    *update, = [lambda: 'local']\n"
                "    assert update[0]() == 'local'\n",
                "starred assignment",
            ),
            (
                "from src.widget import update\n\n"
                "def test_widget_starred_for_shadow():\n"
                "    for *update, in [[lambda: 'local']]:\n"
                "        assert update[0]() == 'local'\n",
                "starred for target",
            ),
        ],
    )
    def test_python_starred_shadowed_import_does_not_cover_artifact(
        self, project, source, scenario
    ):
        """Starred Python target bindings are not production coverage."""
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
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(project, "tests/test_widget.py", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_late_function_local_import_does_not_cover_artifact(self, project):
        """A later local import shadows earlier same-name calls in a function."""
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
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(project, "src/other.py", "def update():\n    return 'other'\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import update\n\n"
            "def test_widget_late_local_import_shadow():\n"
            "    update()\n"
            "    from src.other import update\n"
            "    assert update() == 'other'\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "from src.widget import update\n\n"
                "class TestWidget:\n"
                "    update = staticmethod(lambda: 'local')\n\n"
                "    def test_local_class_attribute(self):\n"
                "        assert self.update() == 'local'\n",
                "class attribute assignment",
            ),
            (
                "from src.widget import update\n\n"
                "del update\n\n"
                "def test_delete_placeholder():\n"
                "    assert True\n",
                "delete target",
            ),
        ],
    )
    def test_python_store_and_delete_references_do_not_cover_artifact(
        self, project, source, scenario
    ):
        """Store and delete targets are not behavioral access coverage."""
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
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(project, "tests/test_widget.py", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_shadowed_constructor_keyword_does_not_cover_attribute(
        self, project
    ):
        """A keyword on a shadowed local callable does not cover an attribute."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-settings.manifest.yaml",
            """schema: "2"
goal: "Add settings"
files:
  edit:
    - path: src/settings.py
      artifacts:
        - kind: class
          name: Settings
        - kind: attribute
          name: timeout
          of: Settings
  read:
    - tests/test_settings.py
validate:
  - pytest tests/test_settings.py -v
""",
        )
        _write_source(
            project,
            "src/settings.py",
            "class Settings:\n"
            "    def __init__(self, timeout):\n"
            "        self.timeout = timeout\n",
        )
        _write_source(
            project,
            "tests/test_settings.py",
            "from src.settings import Settings as RealSettings\n\n"
            "def test_settings_shadowed_keyword():\n"
            "    assert RealSettings is not None\n"
            "    def Settings(**kwargs):\n"
            "        return kwargs\n"
            "    assert Settings(timeout=5) == {'timeout': 5}\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "timeout" in untested[0].message

    @pytest.mark.parametrize(
        ("test_source", "scenario"),
        [
            (
                "from src.settings import Settings as RealSettings\n\n"
                "class Local:\n"
                "    timeout = 5\n\n"
                "def test_settings_local_timeout():\n"
                "    assert RealSettings is not None\n"
                "    assert Local().timeout == 5\n",
                "local constructor member access",
            ),
            (
                "from src.settings import Settings as RealSettings\n\n"
                "class Local:\n"
                "    timeout = 5\n\n"
                "def test_settings_local_instance_timeout():\n"
                "    assert RealSettings is not None\n"
                "    local = Local()\n"
                "    assert local.timeout == 5\n",
                "assigned local object member access",
            ),
        ],
    )
    def test_python_local_attribute_without_owner_identity_does_not_cover_declared_attribute(
        self, project, test_source, scenario
    ):
        """A local object's member does not cover a production owned attribute."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-settings.manifest.yaml",
            """schema: "2"
goal: "Add settings"
files:
  edit:
    - path: src/settings.py
      artifacts:
        - kind: class
          name: Settings
        - kind: attribute
          name: timeout
          of: Settings
  read:
    - tests/test_settings.py
validate:
  - pytest tests/test_settings.py -v
""",
        )
        _write_source(
            project,
            "src/settings.py",
            "class Settings:\n"
            "    def __init__(self, timeout):\n"
            "        self.timeout = timeout\n",
        )
        _write_source(project, "tests/test_settings.py", test_source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "timeout" in untested[0].message

    def test_python_constructor_keyword_covers_owned_attribute(self, project):
        """A keyword on an imported constructor covers that class's attribute."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-settings.manifest.yaml",
            """schema: "2"
goal: "Add settings"
files:
  edit:
    - path: src/settings.py
      artifacts:
        - kind: class
          name: Settings
        - kind: attribute
          name: timeout
          of: Settings
  read:
    - tests/test_settings.py
validate:
  - pytest tests/test_settings.py -v
""",
        )
        _write_source(
            project,
            "src/settings.py",
            "class Settings:\n"
            "    def __init__(self, timeout):\n"
            "        self.timeout = timeout\n",
        )
        _write_source(
            project,
            "tests/test_settings.py",
            "from src.settings import Settings\n\n"
            "def test_settings_timeout_keyword():\n"
            "    settings = Settings(timeout=5)\n"
            "    assert settings.timeout == 5\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is True
        assert untested == []

    def test_python_imported_class_member_access_covers_owned_attribute(self, project):
        """Member access on an imported constructor instance covers its attribute."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-settings.manifest.yaml",
            """schema: "2"
goal: "Add settings"
files:
  edit:
    - path: src/settings.py
      artifacts:
        - kind: class
          name: Settings
        - kind: attribute
          name: timeout
          of: Settings
  read:
    - tests/test_settings.py
validate:
  - pytest tests/test_settings.py -v
""",
        )
        _write_source(
            project,
            "src/settings.py",
            "class Settings:\n"
            "    def __init__(self, timeout):\n"
            "        self.timeout = timeout\n",
        )
        _write_source(
            project,
            "tests/test_settings.py",
            "from src.settings import Settings\n\n"
            "def test_settings_timeout_member_access():\n"
            "    settings = Settings(5)\n"
            "    assert settings.timeout == 5\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is True
        assert untested == []

    def test_python_unrelated_imported_callable_keyword_does_not_cover_attribute(
        self, project
    ):
        """A keyword on an unrelated imported callable does not cover an attribute."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-settings.manifest.yaml",
            """schema: "2"
goal: "Add settings"
files:
  edit:
    - path: src/settings.py
      artifacts:
        - kind: class
          name: Settings
        - kind: attribute
          name: timeout
          of: Settings
  read:
    - tests/test_settings.py
validate:
  - pytest tests/test_settings.py -v
""",
        )
        _write_source(
            project,
            "src/settings.py",
            "class Settings:\n"
            "    def __init__(self, timeout):\n"
            "        self.timeout = timeout\n\n"
            "def render(**kwargs):\n"
            "    return kwargs\n",
        )
        _write_source(
            project,
            "tests/test_settings.py",
            "from src.settings import Settings, render\n\n"
            "def test_settings_unrelated_keyword():\n"
            "    assert Settings is not None\n"
            "    assert render(timeout=5) == {'timeout': 5}\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "timeout" in untested[0].message

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "from src.widget import update\n"
                "import pytest\n\n"
                "@pytest.mark.parametrize('value', [update()])\n"
                "def test_widget_decorator(value):\n"
                "    assert value == 'updated'\n",
                "decorator",
            ),
            (
                "from src.widget import update\n\n"
                "def test_widget_default(value=update()):\n"
                "    assert value == 'updated'\n",
                "default value",
            ),
        ],
    )
    def test_python_runtime_definition_references_cover_artifact(
        self, project, source, scenario
    ):
        """Runtime decorators and default values are behavioral coverage."""
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
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(project, "tests/test_widget.py", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is True, scenario
        assert untested == []

    def test_typescript_import_only_reference_does_not_satisfy_coverage(self, project):
        """TypeScript import declarations alone are not behavioral coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(
            project,
            "tests/widget.test.ts",
            "import { update } from '../src/widget';\n\n"
            "it('placeholder', () => {\n"
            "  expect(true).toBe(true);\n"
            "});\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_typescript_shadowed_import_reference_does_not_satisfy_coverage(
        self, project
    ):
        """A local TypeScript binding with the same name as an import is not coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(
            project,
            "tests/widget.test.ts",
            "import { update } from '../src/widget';\n\n"
            "it('shadows update', () => {\n"
            "  const update = () => 'local';\n"
            "  expect(update()).toBe('local');\n"
            "});\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    @pytest.mark.parametrize(
        ("test_source", "expected_reference_context", "scenario"),
        [
            (
                "function update() {\n"
                "  return 'local';\n"
                "}\n\n"
                "it('uses local update', () => {\n"
                "  expect(update()).toBe('local');\n"
                "});\n",
                "local",
                "local function declaration",
            ),
            (
                "import { noop } from '../src/other';\n\n"
                "it('uses unrelated import before bare update', () => {\n"
                "  expect(noop()).toBe('noop');\n"
                "  update();\n"
                "});\n",
                "access",
                "bare same-name call with unrelated import",
            ),
            (
                "class Local {\n"
                "  update() {\n"
                "    return 'local';\n"
                "  }\n"
                "}\n\n"
                "it('uses local update method', () => {\n"
                "  expect(new Local().update()).toBe('local');\n"
                "});\n",
                "local",
                "local method call",
            ),
        ],
    )
    def test_typescript_local_function_without_identity_import_does_not_cover_artifact(
        self, project, test_source, expected_reference_context, scenario
    ):
        """A local same-name TypeScript helper is not production coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(
            project,
            "src/other.ts",
            "export function noop() {\n  return 'noop';\n}\n",
        )
        _write_source(project, "tests/widget.test.ts", test_source)
        validator = TypeScriptValidator()
        session = parse_typescript_source(
            (project / "tests/widget.test.ts").read_text(),
            project / "tests/widget.test.ts",
            validator._ts_parser,
            validator._tsx_parser,
        )
        collected_references = collect_ts_behavioral_artifacts(
            session.tree.root_node,
            session.source_bytes,
            project / "tests/widget.test.ts",
        )
        assert any(
            ref.name == "update" and ref.reference_context == expected_reference_context
            for ref in collected_references
        ), scenario

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "update" in untested[0].message

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "import { update } from '../src/widget';\n\n"
                "it('shadows update in a for loop', () => {\n"
                "  for (const update of [() => 'local']) {\n"
                "    expect(update()).toBe('local');\n"
                "  }\n"
                "});\n",
                "for loop binding",
            ),
            (
                "import { update } from '../src/widget';\n\n"
                "it('shadows update in a catch clause', () => {\n"
                "  try {\n"
                "    throw () => 'local';\n"
                "  } catch (update) {\n"
                "    expect(update()).toBe('local');\n"
                "  }\n"
                "});\n",
                "catch clause binding",
            ),
        ],
    )
    def test_typescript_control_flow_shadowed_import_does_not_satisfy_coverage(
        self, project, source, scenario
    ):
        """Control-flow scoped TypeScript bindings are not production coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(project, "tests/widget.test.ts", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "update" in untested[0].message

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "import { update } from '../src/widget';\n\n"
                "it('shadows update as an arrow parameter', update => {\n"
                "  expect(update()).toBe('local');\n"
                "});\n",
                "single arrow parameter",
            ),
            (
                "import { update } from '../src/widget';\n\n"
                "it('shadows update with nested var', () => {\n"
                "  { var update = () => 'local'; }\n"
                "  expect(update()).toBe('local');\n"
                "});\n",
                "nested var binding",
            ),
            (
                "import { update } from '../src/widget';\n\n"
                "it('shadows update with for-var', () => {\n"
                "  for (var update of [() => 'local']) {}\n"
                "  expect(update()).toBe('local');\n"
                "});\n",
                "for-var binding",
            ),
        ],
    )
    def test_typescript_function_scope_shadowed_import_does_not_satisfy_coverage(
        self, project, source, scenario
    ):
        """Function-scoped TypeScript bindings are not production coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(project, "tests/widget.test.ts", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_typescript_switch_case_shadowed_import_does_not_satisfy_coverage(
        self, project
    ):
        """Switch-case lexical bindings are not production coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(
            project,
            "tests/widget.test.ts",
            "import { update } from '../src/widget';\n\n"
            "it('shadows update in a switch case', () => {\n"
            "  switch ('local') {\n"
            "    case 'local':\n"
            "      const update = () => 'local';\n"
            "      expect(update()).toBe('local');\n"
            "      break;\n"
            "  }\n"
            "});\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "import { update } from '../src/widget';\n\n"
                "it('shadows update through destructuring', () => {\n"
                "  const helper = { update: () => 'local' };\n"
                "  const { update } = helper;\n"
                "  expect(update()).toBe('local');\n"
                "});\n",
                "variable destructuring",
            ),
            (
                "import { update } from '../src/widget';\n\n"
                "it('shadows update through a parameter', ({ update }) => {\n"
                "  expect(update()).toBe('local');\n"
                "});\n",
                "parameter destructuring",
            ),
            (
                "import { update } from '../src/widget';\n\n"
                "it('shadows update through a for header', () => {\n"
                "  for (const { update } of [{ update: () => 'local' }]) {\n"
                "    expect(update()).toBe('local');\n"
                "  }\n"
                "});\n",
                "for destructuring",
            ),
            (
                "import { update } from '../src/widget';\n\n"
                "it('shadows update through a catch binding', () => {\n"
                "  try {\n"
                "    throw { update: () => 'local' };\n"
                "  } catch ({ update }) {\n"
                "    expect(update()).toBe('local');\n"
                "  }\n"
                "});\n",
                "catch destructuring",
            ),
        ],
    )
    def test_typescript_destructuring_shadowed_import_does_not_satisfy_coverage(
        self, project, source, scenario
    ):
        """Destructured TypeScript bindings are not production coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(project, "tests/widget.test.ts", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_typescript_type_only_reference_does_not_satisfy_coverage(self, project):
        """Type-only TypeScript references are not runtime coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(
            project,
            "tests/widget.test.ts",
            "import type { update } from '../src/widget';\n\n"
            "type UpdateType = typeof update;\n\n"
            "it('placeholder', () => {\n"
            "  expect(true).toBe(true);\n"
            "});\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "interface User { id: string }\n\n"
                "it('uses a local interface only', () => {\n"
                "  expect(true).toBe(true);\n"
                "});\n",
                "local interface",
            ),
            (
                "function identity<User>(value: User): User {\n"
                "  return value;\n"
                "}\n\n"
                "it('uses a local type parameter only', () => {\n"
                "  expect(identity({ id: 'local' })).toEqual({ id: 'local' });\n"
                "});\n",
                "type parameter",
            ),
        ],
    )
    def test_typescript_local_type_bindings_do_not_cover_imported_interface(
        self, project, source, scenario
    ):
        """Local type declarations and parameters are not production coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-user.manifest.yaml",
            """schema: "2"
goal: "Add user"
files:
  edit:
    - path: src/user.ts
      artifacts:
        - kind: interface
          name: User
  read:
    - tests/user.test.ts
validate:
  - pytest tests/user.test.ts -v
""",
        )
        _write_source(
            project,
            "src/user.ts",
            "export interface User {\n  id: string;\n}\n",
        )
        _write_source(project, "tests/user.test.ts", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "User" in untested[0].message

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "import { update } from '../src/widget';\n\n"
                "type update = () => string;\n\n"
                "it('calls the runtime update', () => {\n"
                "  expect(update()).toBe('updated');\n"
                "});\n",
                "type alias",
            ),
            (
                "import { update } from '../src/widget';\n\n"
                "interface update { value: string }\n\n"
                "it('calls the runtime update', () => {\n"
                "  expect(update()).toBe('updated');\n"
                "});\n",
                "interface",
            ),
        ],
    )
    def test_typescript_type_declarations_do_not_shadow_runtime_import_coverage(
        self, project, source, scenario
    ):
        """Type-only declarations do not shadow same-named runtime imports."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(project, "tests/widget.test.ts", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is True, scenario
        assert untested == []

    def test_typescript_alias_placeholder_import_does_not_cover_local_artifact(
        self, project
    ):
        """Importing a TypeScript artifact under an alias is not local coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(
            project,
            "tests/widget.test.ts",
            "import { update as realUpdate } from '../src/widget';\n\n"
            "it('uses a local update', () => {\n"
            "  const update = () => 'local';\n"
            "  expect(update()).toBe('local');\n"
            "});\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_typescript_namespace_placeholder_import_does_not_cover_local_artifact(
        self, project
    ):
        """Importing the artifact namespace is not local binding coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(
            project,
            "tests/widget.test.ts",
            "import * as widget from '../src/widget';\n\n"
            "it('uses a local update', () => {\n"
            "  const update = () => 'local';\n"
            "  expect(update()).toBe('local');\n"
            "});\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_typescript_test_label_does_not_satisfy_artifact_coverage(self, project):
        """A test label matching an artifact name is not behavioral coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(
            project,
            "tests/widget.test.ts",
            "import { update } from '../src/widget';\n\n"
            "it('update', () => {\n"
            "  expect(true).toBe(true);\n"
            "});\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
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
            e
            for e in result.errors + result.warnings
            if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
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
            e
            for e in result.errors + result.warnings
            if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
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
            e
            for e in result.errors + result.warnings
            if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
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
            e
            for e in result.errors + result.warnings
            if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert not any("currentUserName" in w.message for w in untested)
        assert not any("communityStatus" in w.message for w in untested)

    def test_typescript_computed_keys_count_as_attribute_coverage(self, project):
        """Computed enum-key access should cover declared TS attribute artifacts."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-step-completion.manifest.yaml",
            """schema: "2"
goal: "Add step completion"
files:
  edit:
    - path: src/audit.ts
      artifacts:
        - kind: enum
          name: ManualAuditStep
        - kind: interface
          name: StepCompletion
        - kind: attribute
          name: "[ManualAuditStep.AUDIT_DETAILS]"
          of: StepCompletion
          type: boolean
        - kind: attribute
          name: "[ManualAuditStep.CONTENT_CREATION]"
          of: StepCompletion
          type: boolean
        - kind: function
          name: buildStepCompletion
          args: []
          returns: StepCompletion
  read:
    - tests/audit.test.ts
validate:
  - vitest tests/audit.test.ts
""",
        )
        _write_source(
            project,
            "src/audit.ts",
            """export enum ManualAuditStep {
  AUDIT_DETAILS = "audit-details",
  CONTENT_CREATION = "content-creation",
}

export interface StepCompletion {
  [ManualAuditStep.AUDIT_DETAILS]: boolean;
  [ManualAuditStep.CONTENT_CREATION]: boolean;
}

export function buildStepCompletion(): StepCompletion {
  return {
    [ManualAuditStep.AUDIT_DETAILS]: true,
    [ManualAuditStep.CONTENT_CREATION]: false,
  };
}
""",
        )
        _write_source(
            project,
            "tests/audit.test.ts",
            """import { buildStepCompletion, ManualAuditStep, type StepCompletion } from "../src/audit";

it("uses computed step completion flags", () => {
  const completion: StepCompletion = buildStepCompletion();
  expect(completion[ManualAuditStep.AUDIT_DETAILS]).toBe(true);
  expect(completion[ManualAuditStep.CONTENT_CREATION]).toBe(false);
});
""",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is True
        untested = [
            e
            for e in result.errors + result.warnings
            if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert not any("[ManualAuditStep.AUDIT_DETAILS]" in w.message for w in untested)
        assert not any(
            "[ManualAuditStep.CONTENT_CREATION]" in w.message for w in untested
        )

    def test_typescript_literal_computed_keys_count_as_attribute_coverage(
        self, project
    ):
        """Literal computed-key access should cover declared TS attribute artifacts."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-audit-completion.manifest.yaml",
            """schema: "2"
goal: "Add audit completion"
files:
  edit:
    - path: src/audit.ts
      artifacts:
        - kind: interface
          name: AuditCompletion
        - kind: attribute
          name: "[\\"audit-details\\"]"
          of: AuditCompletion
          type: boolean
        - kind: function
          name: buildAuditCompletion
          args: []
          returns: AuditCompletion
  read:
    - tests/audit.test.ts
validate:
  - vitest tests/audit.test.ts
""",
        )
        _write_source(
            project,
            "src/audit.ts",
            """export interface AuditCompletion {
  ["audit-details"]: boolean;
}

export function buildAuditCompletion(): AuditCompletion {
  return { ["audit-details"]: true };
}
""",
        )
        _write_source(
            project,
            "tests/audit.test.ts",
            """import { buildAuditCompletion, type AuditCompletion } from "../src/audit";

it("uses literal computed completion flags", () => {
  const completion: AuditCompletion = buildAuditCompletion();
  expect(completion["audit-details"]).toBe(true);
});
""",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is True
        untested = [
            e
            for e in result.errors + result.warnings
            if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert not any('["audit-details"]' in w.message for w in untested)

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
        assert result.success is True
        untested = [
            e
            for e in result.errors + result.warnings
            if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
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

    def test_snapshot_manifest_still_exempt_from_behavioral_coverage_error(
        self, project
    ):
        """Snapshot manifests do not emit E200 for unreferenced public artifacts."""
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
  read:
    - tests/test_utils.py
validate:
  - pytest tests/test_utils.py -v
""",
        )
        _write_source(project, "src/utils.py", "def helper():\n    pass\n")
        _write_source(
            project, "tests/test_utils.py", "def test_smoke():\n    assert True\n"
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        behavioral_result = engine.validate(
            manifest_path, mode=ValidationMode.BEHAVIORAL
        )

        assert result.success is True
        assert not any(
            e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
            for e in result.errors + result.warnings
        )
        assert behavioral_result.success is True
        assert not any(
            e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
            for e in behavioral_result.errors + behavioral_result.warnings
        )

    def test_test_file_artifacts_do_not_require_meta_test_coverage(self, project):
        """test_function artifacts do not need another test file."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-test-coverage.manifest.yaml",
            """schema: "2"
goal: "Add tests"
type: fix
files:
  edit:
    - path: tests/test_widget.py
      artifacts:
        - kind: test_function
          name: test_widget
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(
            project,
            "tests/test_widget.py",
            "def test_widget():\n    assert True\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        assert result.success is True
        assert not any(
            e.code
            in {
                ErrorCode.NO_TEST_FILES,
                ErrorCode.ARTIFACT_NOT_USED_IN_TESTS,
            }
            for e in result.errors + result.warnings
        )

        workflow_manifest_path = _write_manifest(
            project / "manifests",
            "workflow-test-behavior.manifest.yaml",
            """schema: "2"
goal: "Describe workflow behavior"
type: fix
files:
  edit:
    - path: .github/workflows/publish.yml
      artifacts:
        - kind: test_function
          name: publish_workflow_test_job_installs_npm_dependencies
validate:
  - make check
""",
        )
        _write_source(project, ".github/workflows/publish.yml", "name: publish\n")

        workflow_result = engine.validate(
            workflow_manifest_path, mode=ValidationMode.IMPLEMENTATION
        )

        assert workflow_result.success is True
        assert not any(
            e.code
            in {
                ErrorCode.NO_TEST_FILES,
                ErrorCode.ARTIFACT_NOT_USED_IN_TESTS,
            }
            for e in workflow_result.errors + workflow_result.warnings
        )


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
