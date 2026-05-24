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


# Historical active manifests still read this legacy file for these method
# references. Executable assertions live in tests/core/validation/test_validate_api.py.
_VALIDATION_ENGINE_PUBLIC_METHODS = (
    ValidationEngine.validate,
    ValidationEngine.validate_behavioral,
    ValidationEngine.validate_acceptance,
    ValidationEngine.validate_implementation,
)
_LEGACY_MANIFEST_REFERENCE_ANCHORS = (
    ValidationEngine.run_file_tracking,
    ErrorCode.VALIDATOR_NOT_AVAILABLE,
)


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


class TestFileTracking:
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


class TestStubDetection:
    """Tests for check_stubs=True detecting hollow implementations."""


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


class TestStrictModeStructuralArtifacts:
    """Strict mode should not flag undeclared type aliases or interfaces (structural artifacts)."""

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
