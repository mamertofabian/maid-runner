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


def test_javascript_jsdoc_return_annotation_satisfies_declared_return(project):
    manifest_path = write_manifest(
        project,
        "add-config.manifest.yaml",
        """schema: "2"
goal: "Add typed JavaScript config helper"
files:
  create:
    - path: src/config.js
      artifacts:
        - kind: function
          name: getTypedLintProjects
          args: []
          returns: string[]
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "src/config.js",
        """/** Return lint-only TypeScript project paths.
 * @returns {string[]}
 */
export function getTypedLintProjects() {
  return ['./tsconfig.eslint.json'];
}
""",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert ErrorCode.MISSING_RETURN_TYPE not in warning_codes(result)
    assert ErrorCode.TYPE_MISMATCH not in error_codes(result)


@pytest.mark.parametrize(
    "jsdoc",
    [
        "/** @returns {string[]} */\n\nconst unrelated = true;\n",
        "/** @returns {string[]} */\n/* unrelated block comment */\n",
        "/** @returns string[] */\n",
    ],
)
def test_javascript_detached_or_malformed_jsdoc_does_not_satisfy_declared_return(
    project, jsdoc
):
    manifest_path = write_manifest(
        project,
        "add-config.manifest.yaml",
        """schema: "2"
goal: "Add typed JavaScript config helper"
files:
  create:
    - path: src/config.js
      artifacts:
        - kind: function
          name: getTypedLintProjects
          args: []
          returns: string[]
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "src/config.js",
        jsdoc + "export function getTypedLintProjects() {\n"
        "  return ['./tsconfig.eslint.json'];\n"
        "}\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert ErrorCode.MISSING_RETURN_TYPE in warning_codes(result)


def test_typescript_native_return_annotation_takes_precedence_over_jsdoc(project):
    manifest_path = write_manifest(
        project,
        "add-count.manifest.yaml",
        """schema: "2"
goal: "Add typed TypeScript count helper"
files:
  create:
    - path: src/count.ts
      artifacts:
        - kind: function
          name: countProjects
          args: []
          returns: number
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "src/count.ts",
        """/** @returns {string[]} */
export function countProjects(): number {
  return 1;
}
""",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert ErrorCode.MISSING_RETURN_TYPE not in warning_codes(result)
    assert ErrorCode.TYPE_MISMATCH not in error_codes(result)


def test_javascript_jsdoc_return_mismatch_reports_type_mismatch(project):
    manifest_path = write_manifest(
        project,
        "add-count.manifest.yaml",
        """schema: "2"
goal: "Add JavaScript count helper"
files:
  create:
    - path: src/count.js
      artifacts:
        - kind: function
          name: countProjects
          args: []
          returns: number
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "src/count.js",
        """/** @returns {string[]} */
export function countProjects() {
  return [];
}
""",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert ErrorCode.MISSING_RETURN_TYPE not in warning_codes(result)
    assert ErrorCode.TYPE_MISMATCH in error_codes(result)


def test_javascript_arrow_function_jsdoc_satisfies_declared_return(project):
    manifest_path = write_manifest(
        project,
        "add-config.manifest.yaml",
        """schema: "2"
goal: "Add JavaScript config helper"
files:
  create:
    - path: src/config.js
      artifacts:
        - kind: function
          name: getTypedLintProjects
          args: []
          returns: string[]
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "src/config.js",
        """/** @returns {string[]} */
export const getTypedLintProjects = () => ['./tsconfig.eslint.json'];
""",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert ErrorCode.MISSING_RETURN_TYPE not in warning_codes(result)
    assert ErrorCode.TYPE_MISMATCH not in error_codes(result)


def test_typescript_jsdoc_without_native_annotation_remains_missing(project):
    manifest_path = write_manifest(
        project,
        "add-config.manifest.yaml",
        """schema: "2"
goal: "Add TypeScript config helper"
files:
  create:
    - path: src/config.ts
      artifacts:
        - kind: function
          name: getTypedLintProjects
          args: []
          returns: string[]
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "src/config.ts",
        """/** @returns {string[]} */
export function getTypedLintProjects() {
  return ['./tsconfig.eslint.json'];
}
""",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert ErrorCode.MISSING_RETURN_TYPE in warning_codes(result)


def test_javascript_class_method_jsdoc_satisfies_declared_return(project):
    manifest_path = write_manifest(
        project,
        "add-config.manifest.yaml",
        """schema: "2"
goal: "Add JavaScript config service"
files:
  create:
    - path: src/config.js
      artifacts:
        - kind: class
          name: ConfigService
        - kind: method
          name: getTypedLintProjects
          of: ConfigService
          args: []
          returns: string[]
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "src/config.js",
        """export class ConfigService {
  /** @returns {string[]} */
  getTypedLintProjects() {
    return ['./tsconfig.eslint.json'];
  }
}
""",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert ErrorCode.MISSING_RETURN_TYPE not in warning_codes(result)
    assert ErrorCode.TYPE_MISMATCH not in error_codes(result)


def test_javascript_jsdoc_does_not_bleed_between_same_line_declarators(project):
    manifest_path = write_manifest(
        project,
        "add-config.manifest.yaml",
        """schema: "2"
goal: "Add JavaScript config helpers"
files:
  create:
    - path: src/config.js
      artifacts:
        - kind: function
          name: getTypedLintProjects
          args: []
          returns: string[]
        - kind: function
          name: countTypedLintProjects
          args: []
          returns: number
validate:
  - pytest tests/ -v
""",
    )
    write_source(
        project,
        "src/config.js",
        """/** @returns {string[]} */
export const getTypedLintProjects = () => [], countTypedLintProjects = () => 0;
""",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    missing_messages = [
        warning.message
        for warning in result.warnings
        if warning.code == ErrorCode.MISSING_RETURN_TYPE
    ]
    assert all("getTypedLintProjects" not in message for message in missing_messages)
    assert any("countTypedLintProjects" in message for message in missing_messages)
    assert ErrorCode.TYPE_MISMATCH not in error_codes(result)
