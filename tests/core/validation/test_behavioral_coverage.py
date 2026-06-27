"""Focused characterization tests for behavioral coverage validation."""

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


def coverage_errors(result):
    return [
        error
        for error in result.errors
        if error.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
    ]


def coverage_issues(result):
    return [
        issue
        for issue in result.errors + result.warnings
        if issue.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
    ]


def test_behavioral_validation_passes_when_artifact_is_used_in_test(project):
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
        "tests/test_greet.py",
        "from src.greet import greet\n\n"
        "def test_greet():\n"
        '    assert greet("World") == "Hello, World!"\n',
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.BEHAVIORAL)

    assert result.success is True
    assert coverage_issues(result) == []


def test_validate_command_directory_discovers_nested_test_files(project):
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
    write_source(project, "src/greet.py", "def greet():\n    return 'hello'\n")
    write_source(
        project,
        "tests/unit/test_greet.py",
        "from src.greet import greet\n\n"
        "def test_greet():\n"
        "    assert greet() == 'hello'\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.BEHAVIORAL)

    assert result.success is True
    assert coverage_issues(result) == []


def test_sys_path_imported_python_script_in_hyphenated_skill_dir_satisfies_e200(
    project,
):
    manifest_path = write_manifest(
        project,
        "extract-exercise-candidates.manifest.yaml",
        """schema: "2"
goal: "Extract exercise candidates"
files:
  edit:
    - path: .codex/skills/pdf-book-lesson-compiler/scripts/extract_exercise_candidates.py
      artifacts:
        - kind: function
          name: extract_candidates
  read:
    - tests/test_extract_exercise_candidates.py
validate:
  - pytest tests/test_extract_exercise_candidates.py -v
""",
    )
    write_source(
        project,
        ".codex/skills/pdf-book-lesson-compiler/scripts/extract_exercise_candidates.py",
        "def extract_candidates(text):\n" "    return []\n",
    )
    write_source(
        project,
        "tests/test_extract_exercise_candidates.py",
        "import sys\n"
        "from pathlib import Path\n\n"
        "SCRIPTS_DIR = Path(__file__).resolve().parents[1] / '.codex' / 'skills' / "
        "'pdf-book-lesson-compiler' / 'scripts'\n"
        "sys.path.insert(0, str(SCRIPTS_DIR))\n\n"
        "from extract_exercise_candidates import extract_candidates\n\n"
        "def test_extract_candidates():\n"
        "    assert extract_candidates('1. Do the thing') == []\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.BEHAVIORAL)

    assert result.success is True
    assert coverage_issues(result) == []


def test_behavioral_validation_fails_when_artifact_is_not_used_in_test(project):
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
        "tests/test_greet.py",
        "def test_something():\n    assert True\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.BEHAVIORAL)

    assert result.success is False
    assert len(coverage_errors(result)) == 1


def test_public_artifact_without_test_file_reports_no_test_files(project):
    manifest_path = write_manifest(
        project,
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
    write_source(project, "src/widget.py", "def render():\n    pass\n")

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is False
    assert any(error.code == ErrorCode.NO_TEST_FILES for error in result.errors)


def test_validate_command_test_file_satisfies_implementation_test_requirement(project):
    manifest_path = write_manifest(
        project,
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
    write_source(project, "src/widget.py", "def render():\n    pass\n")
    write_source(
        project,
        "tests/test_widget.py",
        "from src.widget import render\n\n"
        "def test_render():\n"
        "    render()\n"
        "    assert True\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert not any(error.code == ErrorCode.NO_TEST_FILES for error in result.errors)
    assert coverage_issues(result) == []


def test_private_only_manifest_does_not_require_test_files(project):
    manifest_path = write_manifest(
        project,
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
    write_source(project, "src/helper.py", "def _internal_helper():\n    pass\n")

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert not any(error.code == ErrorCode.NO_TEST_FILES for error in result.errors)
    assert coverage_issues(result) == []


def test_read_only_manifest_schema_error_does_not_also_require_test_files(project):
    manifest_path = write_manifest(
        project,
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
    write_source(project, "src/config.py", "DEBUG = True\n")

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is False
    assert any(
        error.code == ErrorCode.SCHEMA_VALIDATION_ERROR for error in result.errors
    )
    assert not any(error.code == ErrorCode.NO_TEST_FILES for error in result.errors)


def test_snapshot_manifest_without_test_file_does_not_report_no_test_files(project):
    manifest_path = write_manifest(
        project,
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
    write_source(project, "src/utils.py", "def helper():\n    pass\n")

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert not any(error.code == ErrorCode.NO_TEST_FILES for error in result.errors)


def test_unreferenced_public_artifact_reports_e200_error(project):
    manifest_path = write_manifest(
        project,
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
    write_source(
        project,
        "src/widget.py",
        "def render():\n    pass\n\ndef update():\n    pass\n",
    )
    write_source(
        project,
        "tests/test_widget.py",
        "from src.widget import render\n\n"
        "def test_render():\n"
        "    render()\n"
        "    assert True\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
    untested = coverage_errors(result)

    assert result.success is False
    assert len(untested) == 1
    assert "update" in untested[0].message
    assert untested[0].severity.value == "error"


def test_all_declared_public_artifacts_used_in_tests_reports_no_coverage_errors(
    project,
):
    manifest_path = write_manifest(
        project,
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
    write_source(
        project,
        "src/widget.py",
        "def render():\n    pass\n\n" "def update():\n    pass\n",
    )
    write_source(
        project,
        "tests/test_widget.py",
        "from src.widget import render, update\n\n"
        "def test_render():\n"
        "    render()\n"
        "    assert True\n\n"
        "def test_update():\n"
        "    update()\n"
        "    assert True\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert coverage_issues(result) == []


def test_private_artifact_without_test_reference_reports_no_coverage_errors(project):
    manifest_path = write_manifest(
        project,
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
    write_source(
        project,
        "src/widget.py",
        "def render():\n    pass\n\n" "def _helper():\n    pass\n",
    )
    write_source(
        project,
        "tests/test_widget.py",
        "from src.widget import render\n\n"
        "def test_render():\n"
        "    render()\n"
        "    assert True\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert coverage_issues(result) == []


def test_typescript_attribute_member_access_counts_as_coverage(project):
    manifest_path = write_manifest(
        project,
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
    write_source(
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
    write_source(
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

    assert not any("make" in issue.message for issue in coverage_issues(result))


def test_typescript_object_literal_props_count_as_attribute_coverage(project):
    manifest_path = write_manifest(
        project,
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
    write_source(
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
    write_source(
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
    issues = coverage_issues(result)

    assert not any("currentUserName" in issue.message for issue in issues)
    assert not any("communityStatus" in issue.message for issue in issues)


def test_typescript_jsx_props_count_as_attribute_coverage(project):
    manifest_path = write_manifest(
        project,
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
    write_source(
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
    write_source(
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
    issues = coverage_issues(result)

    assert not any("currentUserName" in issue.message for issue in issues)
    assert not any("communityStatus" in issue.message for issue in issues)


def test_typescript_computed_keys_count_as_attribute_coverage(project):
    manifest_path = write_manifest(
        project,
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
    write_source(
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
    write_source(
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
    issues = coverage_issues(result)

    assert result.success is True
    assert not any(
        "[ManualAuditStep.AUDIT_DETAILS]" in issue.message for issue in issues
    )
    assert not any(
        "[ManualAuditStep.CONTENT_CREATION]" in issue.message for issue in issues
    )


def test_typescript_literal_computed_keys_count_as_attribute_coverage(project):
    manifest_path = write_manifest(
        project,
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
    write_source(
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
    write_source(
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
    assert not any(
        '["audit-details"]' in issue.message for issue in coverage_issues(result)
    )


def test_import_only_reference_is_not_behavioral_coverage(project):
    manifest_path = write_manifest(
        project,
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
    write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
    write_source(
        project,
        "tests/test_widget.py",
        "from src.widget import update\n\n"
        "def test_widget_placeholder():\n"
        "    assert True\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
    untested = coverage_errors(result)

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
def test_local_same_name_helper_without_identity_does_not_cover_artifact(
    project, test_source, scenario
):
    manifest_path = write_manifest(
        project,
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
    write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
    write_source(project, "src/other.py", "def noop():\n    return 'noop'\n")
    write_source(project, "tests/test_widget.py", test_source)

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
    untested = coverage_errors(result)

    assert result.success is False, scenario
    assert len(untested) == 1
    assert "update" in untested[0].message


@pytest.mark.parametrize(
    ("test_source", "scenario"),
    [
        (
            "function update() {\n"
            "  return 'local';\n"
            "}\n\n"
            "it('uses local update', () => {\n"
            "  expect(update()).toBe('local');\n"
            "});\n",
            "local function declaration",
        ),
        (
            "import { noop } from '../src/other';\n\n"
            "it('uses unrelated import before bare update', () => {\n"
            "  expect(noop()).toBe('noop');\n"
            "  update();\n"
            "});\n",
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
            "local method call",
        ),
    ],
)
def test_typescript_local_same_name_helper_variants_without_identity_do_not_cover_artifact(
    project, test_source, scenario
):
    manifest_path = write_manifest(
        project,
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
    write_source(
        project, "src/widget.ts", "export function update() {\n  return 'updated';\n}\n"
    )
    write_source(
        project, "src/other.ts", "export function noop() {\n  return 'noop';\n}\n"
    )
    write_source(project, "tests/widget.test.ts", test_source)

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
    untested = coverage_errors(result)

    assert result.success is False, scenario
    assert len(untested) == 1
    assert "update" in untested[0].message


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
def test_python_local_attribute_member_variants_without_owner_identity_do_not_cover_declared_attribute(
    project, test_source, scenario
):
    manifest_path = write_manifest(
        project,
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
    write_source(
        project,
        "src/settings.py",
        "class Settings:\n"
        "    def __init__(self, timeout):\n"
        "        self.timeout = timeout\n",
    )
    write_source(project, "tests/test_settings.py", test_source)

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
    untested = coverage_errors(result)

    assert result.success is False, scenario
    assert len(untested) == 1
    assert "timeout" in untested[0].message


def test_python_imported_class_member_access_satisfies_owned_attribute_coverage(
    project,
):
    manifest_path = write_manifest(
        project,
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
    write_source(
        project,
        "src/settings.py",
        "class Settings:\n"
        "    def __init__(self, timeout):\n"
        "        self.timeout = timeout\n",
    )
    write_source(
        project,
        "tests/test_settings.py",
        "from src.settings import Settings\n\n"
        "def test_settings_timeout_member_access():\n"
        "    settings = Settings(5)\n"
        "    assert settings.timeout == 5\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert coverage_errors(result) == []


def test_imported_production_call_satisfies_behavioral_coverage(project):
    manifest_path = write_manifest(
        project,
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
    write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
    write_source(
        project,
        "tests/test_widget.py",
        "from src.widget import update\n\n"
        "def test_widget_update():\n"
        "    assert update() == 'updated'\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert coverage_issues(result) == []


def test_snapshot_manifest_is_exempt_from_behavioral_coverage(project):
    manifest_path = write_manifest(
        project,
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
    write_source(project, "src/utils.py", "def helper():\n    pass\n")
    write_source(project, "tests/test_utils.py", "def test_smoke():\n    assert True\n")

    engine = ValidationEngine(project_root=project)
    implementation = engine.validate(
        manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
    )
    behavioral = engine.validate(manifest_path, mode=ValidationMode.BEHAVIORAL)

    assert implementation.success is True
    assert behavioral.success is True
    assert coverage_issues(implementation) == []
    assert coverage_issues(behavioral) == []


def assert_single_coverage_error(result, artifact_name):
    untested = coverage_errors(result)

    assert result.success is False
    assert len(untested) == 1
    assert artifact_name in untested[0].message


def validate_python_update_coverage(project, test_source, extra_sources=None):
    manifest_path = write_manifest(
        project,
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
    write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
    for rel_path, content in extra_sources or ():
        write_source(project, rel_path, content)
    write_source(project, "tests/test_widget.py", test_source)

    engine = ValidationEngine(project_root=project)
    return engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)


def validate_typescript_update_coverage(project, test_source):
    manifest_path = write_manifest(
        project,
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
    write_source(
        project,
        "src/widget.ts",
        "export function update() {\n  return 'updated';\n}\n",
    )
    write_source(project, "tests/widget.test.ts", test_source)

    engine = ValidationEngine(project_root=project)
    return engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)


@pytest.mark.parametrize(
    ("test_source", "scenario"),
    [
        (
            "from src.widget import update\n\n"
            "def test_widget_shadow():\n"
            "    def update():\n"
            "        return 'local'\n"
            "    assert update() == 'local'\n",
            "function-local shadow",
        ),
        (
            "def test_widget_shadow():\n"
            "    def update():\n"
            "        return 'local'\n"
            "    assert update() == 'local'\n\n"
            "from src.widget import update\n",
            "shadow before later import",
        ),
        (
            "from src.widget import update\n\n"
            "def update():\n"
            "    return 'local'\n\n"
            "def test_widget_shadow():\n"
            "    assert update() == 'local'\n",
            "module-level rebinding",
        ),
        (
            "from src.widget import update as real_update\n\n"
            "def update():\n"
            "    return 'local'\n\n"
            "def test_widget_shadow():\n"
            "    assert update() == 'local'\n",
            "placeholder alias import",
        ),
        (
            "import src.widget as widget_module\n\n"
            "def update():\n"
            "    return 'local'\n\n"
            "def test_widget_shadow():\n"
            "    assert update() == 'local'\n",
            "module placeholder import",
        ),
    ],
)
def test_python_shadowed_import_variants_do_not_satisfy_coverage(
    project, test_source, scenario
):
    result = validate_python_update_coverage(project, test_source)

    assert_single_coverage_error(result, "update"), scenario


def test_python_function_local_import_still_covers_after_module_shadow(project):
    result = validate_python_update_coverage(
        project,
        "from src.widget import update\n\n"
        "def update():\n"
        "    return 'local'\n\n"
        "def test_widget_imports_real_update():\n"
        "    from src.widget import update\n"
        "    assert update() == 'updated'\n",
    )

    assert result.success is True
    assert coverage_errors(result) == []


@pytest.mark.parametrize(
    ("test_source", "scenario"),
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
def test_python_expression_and_binding_shadows_do_not_cover_artifact(
    project, test_source, scenario
):
    result = validate_python_update_coverage(project, test_source)

    assert_single_coverage_error(result, "update"), scenario


@pytest.mark.parametrize(
    ("test_source", "scenario"),
    [
        (
            "from src.widget import update\n\n"
            "def test_widget_annotation_only(value: update = None) -> update:\n"
            "    assert value is None\n"
            "    return None\n",
            "annotation-only reference",
        ),
        (
            "from src.widget import update\n\n"
            "def test_widget_late_local_import_shadow():\n"
            "    update()\n"
            "    from src.other import update\n"
            "    assert update() == 'other'\n",
            "late function-local import",
        ),
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
def test_python_non_runtime_or_rebound_references_do_not_cover_artifact(
    project, test_source, scenario
):
    result = validate_python_update_coverage(
        project,
        test_source,
        extra_sources=(("src/other.py", "def update():\n    return 'other'\n"),),
    )

    assert_single_coverage_error(result, "update"), scenario


def test_python_keyword_argument_does_not_cover_same_module_artifact(project):
    manifest_path = write_manifest(
        project,
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
    write_source(
        project,
        "src/widget.py",
        "def render(**kwargs):\n    return kwargs\n\n"
        "def update():\n    return 'updated'\n",
    )
    write_source(
        project,
        "tests/test_widget.py",
        "from src.widget import render\n\n"
        "def test_widget_render_flag():\n"
        "    assert render(update=True) == {'update': True}\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert_single_coverage_error(result, "update")


@pytest.mark.parametrize(
    ("test_source", "expected_success", "scenario"),
    [
        (
            "from src.settings import Settings as RealSettings\n\n"
            "def test_settings_shadowed_keyword():\n"
            "    assert RealSettings is not None\n"
            "    def Settings(**kwargs):\n"
            "        return kwargs\n"
            "    assert Settings(timeout=5) == {'timeout': 5}\n",
            False,
            "shadowed constructor keyword",
        ),
        (
            "from src.settings import Settings\n\n"
            "def test_settings_timeout_keyword():\n"
            "    settings = Settings(timeout=5)\n"
            "    assert settings.timeout == 5\n",
            True,
            "imported constructor keyword",
        ),
        (
            "from src.settings import Settings, render\n\n"
            "def test_settings_unrelated_keyword():\n"
            "    assert Settings is not None\n"
            "    assert render(timeout=5) == {'timeout': 5}\n",
            False,
            "unrelated imported callable keyword",
        ),
    ],
)
def test_python_constructor_keyword_coverage_requires_imported_owner_identity(
    project, test_source, expected_success, scenario
):
    manifest_path = write_manifest(
        project,
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
    write_source(
        project,
        "src/settings.py",
        "class Settings:\n"
        "    def __init__(self, timeout):\n"
        "        self.timeout = timeout\n\n"
        "def render(**kwargs):\n"
        "    return kwargs\n",
    )
    write_source(project, "tests/test_settings.py", test_source)

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    if expected_success:
        assert result.success is True, scenario
        assert coverage_errors(result) == []
    else:
        assert_single_coverage_error(result, "timeout"), scenario


@pytest.mark.parametrize(
    ("test_source", "scenario"),
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
    project, test_source, scenario
):
    result = validate_python_update_coverage(project, test_source)

    assert result.success is True, scenario
    assert coverage_errors(result) == []


@pytest.mark.parametrize(
    ("test_source", "scenario"),
    [
        (
            "import { update } from '../src/widget';\n\n"
            "it('placeholder', () => {\n"
            "  expect(true).toBe(true);\n"
            "});\n",
            "import only",
        ),
        (
            "import { update } from '../src/widget';\n\n"
            "it('shadows update', () => {\n"
            "  const update = () => 'local';\n"
            "  expect(update()).toBe('local');\n"
            "});\n",
            "local binding",
        ),
        (
            "import { update as realUpdate } from '../src/widget';\n\n"
            "it('uses a local update', () => {\n"
            "  const update = () => 'local';\n"
            "  expect(update()).toBe('local');\n"
            "});\n",
            "placeholder alias import",
        ),
        (
            "import * as widget from '../src/widget';\n\n"
            "it('uses a local update', () => {\n"
            "  const update = () => 'local';\n"
            "  expect(update()).toBe('local');\n"
            "});\n",
            "namespace placeholder import",
        ),
        (
            "import { update } from '../src/widget';\n\n"
            "it('update', () => {\n"
            "  expect(true).toBe(true);\n"
            "});\n",
            "test label only",
        ),
    ],
)
def test_typescript_import_and_placeholder_references_do_not_satisfy_coverage(
    project, test_source, scenario
):
    result = validate_typescript_update_coverage(project, test_source)

    assert_single_coverage_error(result, "update"), scenario


@pytest.mark.parametrize(
    ("test_source", "scenario"),
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
        (
            "import { update } from '../src/widget';\n\n"
            "it('shadows update in a switch case', () => {\n"
            "  switch ('local') {\n"
            "    case 'local':\n"
            "      const update = () => 'local';\n"
            "      expect(update()).toBe('local');\n"
            "      break;\n"
            "  }\n"
            "});\n",
            "switch-case binding",
        ),
    ],
)
def test_typescript_control_flow_and_function_scope_shadows_do_not_cover_artifact(
    project, test_source, scenario
):
    result = validate_typescript_update_coverage(project, test_source)

    assert_single_coverage_error(result, "update"), scenario


@pytest.mark.parametrize(
    ("test_source", "scenario"),
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
    project, test_source, scenario
):
    result = validate_typescript_update_coverage(project, test_source)

    assert_single_coverage_error(result, "update"), scenario


def test_typescript_type_only_reference_does_not_satisfy_coverage(project):
    result = validate_typescript_update_coverage(
        project,
        "import type { update } from '../src/widget';\n\n"
        "type UpdateType = typeof update;\n\n"
        "it('placeholder', () => {\n"
        "  expect(true).toBe(true);\n"
        "});\n",
    )

    assert_single_coverage_error(result, "update")


@pytest.mark.parametrize(
    ("test_source", "scenario"),
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
    project, test_source, scenario
):
    manifest_path = write_manifest(
        project,
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
    write_source(project, "src/user.ts", "export interface User {\n  id: string;\n}\n")
    write_source(project, "tests/user.test.ts", test_source)

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert_single_coverage_error(result, "User"), scenario


@pytest.mark.parametrize(
    ("test_source", "scenario"),
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
    project, test_source, scenario
):
    result = validate_typescript_update_coverage(project, test_source)

    assert result.success is True, scenario
    assert coverage_errors(result) == []


def test_snapshot_manifest_still_exempt_from_behavioral_coverage_error(project):
    manifest_path = write_manifest(
        project,
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
    write_source(project, "src/utils.py", "def helper():\n    pass\n")
    write_source(project, "tests/test_utils.py", "def test_smoke():\n    assert True\n")

    engine = ValidationEngine(project_root=project)
    implementation = engine.validate(
        manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
    )
    behavioral = engine.validate(manifest_path, mode=ValidationMode.BEHAVIORAL)

    assert implementation.success is True
    assert behavioral.success is True
    assert coverage_issues(implementation) == []
    assert coverage_issues(behavioral) == []


def test_test_file_artifacts_do_not_require_meta_test_coverage(project):
    manifest_path = write_manifest(
        project,
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
    write_source(
        project, "tests/test_widget.py", "def test_widget():\n    assert True\n"
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert not any(
        issue.code
        in {
            ErrorCode.NO_TEST_FILES,
            ErrorCode.ARTIFACT_NOT_USED_IN_TESTS,
        }
        for issue in result.errors + result.warnings
    )

    workflow_manifest_path = write_manifest(
        project,
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
    write_source(project, ".github/workflows/publish.yml", "name: publish\n")

    workflow_result = engine.validate(
        workflow_manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
    )

    assert workflow_result.success is True
    assert not any(
        issue.code
        in {
            ErrorCode.NO_TEST_FILES,
            ErrorCode.ARTIFACT_NOT_USED_IN_TESTS,
        }
        for issue in workflow_result.errors + workflow_result.warnings
    )
