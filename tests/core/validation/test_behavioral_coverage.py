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


def test_local_same_name_helper_without_identity_does_not_cover_artifact(project):
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
        "def update():\n"
        "    return 'local'\n\n"
        "def test_widget_local_update():\n"
        "    assert update() == 'local'\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
    untested = coverage_errors(result)

    assert result.success is False
    assert len(untested) == 1
    assert "update" in untested[0].message


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
