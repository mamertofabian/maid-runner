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


def unexpected_artifact_messages(result):
    return [
        error.message
        for error in result.errors
        if error.code == ErrorCode.UNEXPECTED_ARTIFACT
    ]


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


def test_exported_typescript_type_alias_is_allowed_in_strict_create_mode(project):
    manifest_path = write_manifest(
        project,
        "add-auth.manifest.yaml",
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
    write_source(
        project,
        "src/auth.ts",
        "export type AuthConfig = { host: string; port: number };\n\n"
        "export function authenticate(): boolean { return true; }\n",
    )
    write_test(project, "tests/test_auth.py", "src.auth", ["authenticate"])

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert ErrorCode.UNEXPECTED_ARTIFACT not in error_codes(result)


def test_undeclared_typescript_interface_members_are_allowed_in_strict_create_mode(
    project,
):
    manifest_path = write_manifest(
        project,
        "add-auth.manifest.yaml",
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
    write_source(
        project,
        "src/auth.ts",
        "export interface AuthConfig {\n  host: string;\n  port: number;\n}\n\n"
        "export function authenticate(): boolean { return true; }\n",
    )
    write_test(project, "tests/test_auth.py", "src.auth", ["authenticate"])

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert ErrorCode.UNEXPECTED_ARTIFACT not in error_codes(result)


def test_declared_typescript_interface_members_are_strictly_validated(project):
    manifest_path = write_manifest(
        project,
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
    write_source(
        project,
        "src/auth.ts",
        "export interface AuthConfig {\n  host: string;\n  port: number;\n}\n\n"
        "export function authenticate(): boolean { return true; }\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is False
    assert any(
        "AuthConfig.port" in message for message in unexpected_artifact_messages(result)
    )


def test_typescript_strict_mode_allows_private_keyword_methods(project):
    manifest_path = write_manifest(
        project,
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
    write_source(
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
    write_source(
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
    assert unexpected_artifact_messages(result) == []


def test_typescript_strict_mode_allows_public_getter_with_private_setter(project):
    manifest_path = write_manifest(
        project,
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
    write_source(
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
    write_source(
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
    assert unexpected_artifact_messages(result) == []


def test_typescript_strict_mode_allows_module_local_constants(project):
    manifest_path = write_manifest(
        project,
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
    write_source(
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
    write_source(
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
    assert unexpected_artifact_messages(result) == []


def test_typescript_strict_mode_still_flags_exported_undeclared_constants(project):
    manifest_path = write_manifest(
        project,
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
    write_source(
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
    write_source(
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
    messages = unexpected_artifact_messages(result)

    assert result.success is False
    assert any("PUBLIC_POINTS" in message for message in messages)
    assert not any("LOCAL_POINTS" in message for message in messages)


def test_typescript_strict_mode_allows_export_assignment_target(project):
    manifest_path = write_manifest(
        project,
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
    write_source(
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
    write_source(
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
    assert unexpected_artifact_messages(result) == []


def test_typescript_generic_type_parameter_mismatch_reports_type_mismatch(project):
    manifest_path = write_manifest(
        project,
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
    write_source(
        project,
        "src/store.ts",
        "export class Store<T extends Other = Other> {}\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert ErrorCode.TYPE_MISMATCH in error_codes(result)
    assert any("type parameters" in error.message for error in result.errors)


def test_strict_create_flags_undeclared_python_function(project):
    manifest_path = write_manifest(
        project,
        "add-auth.manifest.yaml",
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
    write_source(
        project,
        "src/auth.py",
        "def authenticate():\n    pass\n\n" "def helper():\n    pass\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is False
    assert ErrorCode.UNEXPECTED_ARTIFACT in error_codes(result)


def test_edit_mode_allows_undeclared_python_function(project):
    manifest_path = write_manifest(
        project,
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
    write_source(
        project,
        "src/greet.py",
        'def greet(name):\n    return f"Hello, {name}!"\n\n'
        'def farewell(name):\n    return f"Goodbye, {name}!"\n',
    )
    write_test(project, "tests/test_greet.py", "src.greet", ["farewell"])

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert ErrorCode.UNEXPECTED_ARTIFACT not in error_codes(result)


def test_strict_create_flags_undeclared_python_class(project):
    manifest_path = write_manifest(
        project,
        "add-auth.manifest.yaml",
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
    write_source(
        project,
        "src/auth.py",
        "def authenticate():\n    pass\n\n" "class Helper:\n    pass\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is False
    assert ErrorCode.UNEXPECTED_ARTIFACT in error_codes(result)


def test_private_parent_members_are_allowed_in_strict_create_mode(project):
    manifest_path = write_manifest(
        project,
        "add-auth.manifest.yaml",
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
    write_source(
        project,
        "src/auth.py",
        "class _Internal:\n    def helper(self):\n        pass\n\n"
        "def authenticate():\n    pass\n",
    )
    write_test(project, "tests/test_auth.py", "src.auth", ["authenticate"])

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert ErrorCode.UNEXPECTED_ARTIFACT not in error_codes(result)


def test_test_file_create_mode_allows_undeclared_test_helpers(project):
    manifest_path = write_manifest(
        project,
        "add-auth-tests.manifest.yaml",
        """schema: "2"
goal: "Add auth tests"
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
    write_source(
        project,
        "tests/test_auth.py",
        "def _make_user():\n    return {'name': 'test'}\n\n"
        "def test_authenticate():\n    user = _make_user()\n    assert user\n\n"
        "def test_login():\n    assert True\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert ErrorCode.UNEXPECTED_ARTIFACT not in error_codes(result)


def test_test_file_create_mode_still_requires_declared_test_artifacts(project):
    manifest_path = write_manifest(
        project,
        "add-auth-tests.manifest.yaml",
        """schema: "2"
goal: "Add auth tests"
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
    write_source(
        project, "tests/test_auth.py", "def test_authenticate():\n    assert True\n"
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is False
    assert ErrorCode.ARTIFACT_NOT_DEFINED in error_codes(result)


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
