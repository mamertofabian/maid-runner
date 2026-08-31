"""Behavioral contract for Cypress acceptance ``--spec`` option paths."""

from pathlib import Path

import pytest

from maid_runner.core.manifest import load_manifest, validate_manifest_paths
from maid_runner.core.result import ErrorCode
from maid_runner.core.validate import ValidationEngine


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Create the minimum isolated project needed to load an acceptance manifest."""
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "context.py").write_text("class Context:\n    pass\n")
    return tmp_path


def write_acceptance_manifest(project: Path, command: str) -> Path:
    manifest_path = project / "manifests" / "cypress-spec.manifest.yaml"
    manifest_path.write_text(
        f"""schema: "2"
goal: "Exercise Cypress acceptance path parsing"
files:
  create:
    - path: src/context.py
      artifacts:
        - kind: class
          name: Context
acceptance:
  tests:
    - {command}
validate:
  - pytest tests/test_contract.py
"""
    )
    return manifest_path


def acceptance_file_errors(errors):
    return [
        error
        for error in errors
        if error.code == ErrorCode.ACCEPTANCE_TEST_FILE_NOT_FOUND
    ]


def test_existing_cypress_spec_assignment_does_not_report_e500(project: Path):
    spec_path = "cypress/e2e/offline-indicator-layout.cy.ts"
    full_spec_path = project / spec_path
    full_spec_path.parent.mkdir(parents=True)
    full_spec_path.write_text("describe('offline indicator', () => {})\n")
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npx cypress run --spec={spec_path}",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


def test_existing_nx_cypress_spec_assignment_does_not_report_e500(project: Path):
    spec_path = "apps/example-e2e/src/e2e/offline-indicator-layout.cy.ts"
    full_spec_path = project / spec_path
    full_spec_path.parent.mkdir(parents=True)
    full_spec_path.write_text("describe('nx offline indicator', () => {})\n")
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npx nx e2e example-e2e --configuration=ci --spec={spec_path}",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


@pytest.mark.parametrize("target_option", ["--target=e2e", "-t=e2e"])
def test_existing_nx_target_spec_assignment_does_not_report_e500(
    project: Path,
    target_option: str,
):
    spec_path = "apps/example-e2e/src/e2e/target-option.cy.ts"
    full_spec_path = project / spec_path
    full_spec_path.parent.mkdir(parents=True)
    full_spec_path.write_text("describe('nx target option', () => {})\n")
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npx nx run-many {target_option} --spec={spec_path}",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


def test_nx_configured_target_missing_spec_reports_e500(project: Path):
    spec_path = "apps/example-e2e/src/e2e/configured-target.txt"
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npx nx run example:e2e:ci --spec={spec_path}",
        )
    )

    errors = acceptance_file_errors(
        ValidationEngine(project_root=project).validate_acceptance(manifest)
    )

    assert len(errors) == 1
    assert errors[0].location is not None
    assert errors[0].location.file == spec_path


def test_npx_package_injection_preserves_nx_spec_detection(project: Path):
    spec_path = "apps/example-e2e/src/e2e/npx-package.cy.ts"
    full_spec_path = project / spec_path
    full_spec_path.parent.mkdir(parents=True)
    full_spec_path.write_text("describe('npx package', () => {})\n")
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npx -p nx nx e2e example-e2e --spec={spec_path}",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


@pytest.mark.parametrize(
    "package_option",
    ["-p nx", "--package nx"],
)
def test_npx_package_injection_after_standalone_flag_preserves_detection(
    project: Path,
    package_option: str,
):
    spec_path = "apps/example-e2e/src/e2e/npx-yes.cy.ts"
    full_spec_path = project / spec_path
    full_spec_path.parent.mkdir(parents=True)
    full_spec_path.write_text("describe('npx yes', () => {})\n")
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            "npx --yes " f"{package_option} nx run example:e2e:ci --spec={spec_path}",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


def test_npx_value_option_before_package_injection_preserves_detection(project: Path):
    spec_path = "apps/example-e2e/src/e2e/npx-cache.cy.ts"
    full_spec_path = project / spec_path
    full_spec_path.parent.mkdir(parents=True)
    full_spec_path.write_text("describe('npx cache', () => {})\n")
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            "npx --cache .cache -p nx nx run example:e2e:ci " f"--spec={spec_path}",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


@pytest.mark.parametrize(
    "npx_options",
    [
        "--package wrapper-value.cy.ts",
        "--cache cache-value.cy.ts -p cypress",
    ],
)
def test_npx_test_shaped_option_values_are_not_acceptance_targets(
    project: Path,
    npx_options: str,
):
    spec_path = "cypress/e2e/npx-option-value.cy.ts"
    full_spec_path = project / spec_path
    full_spec_path.parent.mkdir(parents=True)
    full_spec_path.write_text("describe('npx option value', () => {})\n")
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npx {npx_options} cypress run --spec={spec_path}",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


def test_npx_outside_option_value_is_not_a_manifest_path(project: Path):
    spec_path = "cypress/e2e/npx-outside-option.cy.ts"
    full_spec_path = project / spec_path
    full_spec_path.parent.mkdir(parents=True)
    full_spec_path.write_text("describe('npx outside option', () => {})\n")
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            "npx --package ../wrapper-value.cy.ts cypress run " f"--spec={spec_path}",
        )
    )

    errors = validate_manifest_paths(manifest, project)

    assert errors == []


@pytest.mark.parametrize("wrapper", ["/usr/bin/env", "uv run"])
def test_nested_npx_package_injection_preserves_detection(
    project: Path,
    wrapper: str,
):
    spec_path = "apps/example-e2e/src/e2e/nested-npx.cy.ts"
    full_spec_path = project / spec_path
    full_spec_path.parent.mkdir(parents=True)
    full_spec_path.write_text("describe('nested npx', () => {})\n")
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"{wrapper} npx -p nx nx run example:e2e:ci --spec={spec_path}",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


def test_missing_cypress_spec_assignment_reports_extracted_path(project: Path):
    spec_path = "cypress/e2e/missing-layout.cy.ts"
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npx cypress run --spec={spec_path}",
        )
    )

    errors = acceptance_file_errors(
        ValidationEngine(project_root=project).validate_acceptance(manifest)
    )

    assert len(errors) == 1
    assert errors[0].location is not None
    assert errors[0].location.file == spec_path
    assert f"'{spec_path}'" in errors[0].message


def test_missing_nonconventional_cypress_spec_reports_extracted_path(project: Path):
    spec_path = "cypress/e2e/custom-case.txt"
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npx cypress run --spec={spec_path}",
        )
    )

    errors = acceptance_file_errors(
        ValidationEngine(project_root=project).validate_acceptance(manifest)
    )

    assert len(errors) == 1
    assert errors[0].location is not None
    assert errors[0].location.file == spec_path


def test_existing_cypress_split_spec_option_remains_supported(project: Path):
    spec_path = "cypress/e2e/split-option.cy.ts"
    full_spec_path = project / spec_path
    full_spec_path.parent.mkdir(parents=True)
    full_spec_path.write_text("describe('split option', () => {})\n")
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npx cypress run --spec {spec_path}",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


def test_existing_cypress_spec_list_does_not_report_e500(project: Path):
    spec_paths = [
        "cypress/e2e/first.cy.ts",
        "cypress/e2e/second.cy.ts",
    ]
    for spec_path in spec_paths:
        full_spec_path = project / spec_path
        full_spec_path.parent.mkdir(parents=True, exist_ok=True)
        full_spec_path.write_text("describe('listed spec', () => {})\n")
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npx cypress run --spec={','.join(spec_paths)}",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


def test_cypress_spec_glob_does_not_report_literal_e500(project: Path):
    spec_path = project / "cypress/e2e/globbed.cy.ts"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text("describe('globbed', () => {})\n")
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            "npx cypress run --spec=cypress/e2e/*.cy.ts",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


def test_existing_cypress_spec_assignment_respects_command_cwd(project: Path):
    spec_path = "cypress/e2e/command-cwd.cy.ts"
    full_spec_path = project / "frontend" / spec_path
    full_spec_path.parent.mkdir(parents=True)
    full_spec_path.write_text("describe('command cwd', () => {})\n")
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"cd frontend && npx cypress run --spec={spec_path}",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


def test_existing_cypress_spec_respects_attached_command_cwd(project: Path):
    spec_path = "cypress/e2e/attached-cwd.cy.ts"
    full_spec_path = project / "frontend" / spec_path
    full_spec_path.parent.mkdir(parents=True)
    full_spec_path.write_text("describe('attached cwd', () => {})\n")
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npm --prefix=frontend exec cypress run --spec={spec_path}",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


def test_cypress_config_flag_is_not_a_command_cwd(project: Path):
    spec_path = "cypress/e2e/cypress-config-flag.cy.ts"
    full_spec_path = project / spec_path
    full_spec_path.parent.mkdir(parents=True)
    full_spec_path.write_text("describe('cypress config flag', () => {})\n")
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npx cypress run -C cypress.config.ts --spec={spec_path}",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


@pytest.mark.parametrize("dir_option", ["--dir=frontend", "--dir frontend"])
def test_existing_pnpm_cypress_spec_respects_command_cwd(
    project: Path,
    dir_option: str,
):
    spec_path = "cypress/e2e/pnpm-cwd.cy.ts"
    full_spec_path = project / "frontend" / spec_path
    full_spec_path.parent.mkdir(parents=True)
    full_spec_path.write_text("describe('pnpm cwd', () => {})\n")
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"pnpm {dir_option} exec cypress run --spec={spec_path}",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


@pytest.mark.parametrize("runner", ["npm", "pnpm"])
def test_package_exec_separator_preserves_cypress_detection(
    project: Path,
    runner: str,
):
    spec_path = "cypress/e2e/exec-separator.cy.ts"
    full_spec_path = project / spec_path
    full_spec_path.parent.mkdir(parents=True)
    full_spec_path.write_text("describe('exec separator', () => {})\n")
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"{runner} exec -- cypress run --spec={spec_path}",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


def test_command_cwd_option_does_not_leak_to_later_segment(project: Path):
    frontend_spec = "cypress/e2e/frontend.cy.ts"
    root_spec = "cypress/e2e/root.cy.ts"
    frontend_path = project / "frontend" / frontend_spec
    frontend_path.parent.mkdir(parents=True)
    frontend_path.write_text("describe('frontend', () => {})\n")
    root_path = project / root_spec
    root_path.parent.mkdir(parents=True)
    root_path.write_text("describe('root', () => {})\n")
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            "npm --prefix=frontend exec cypress run "
            f"--spec={frontend_spec} && npx cypress run --spec={root_spec}",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


@pytest.mark.parametrize(
    "command",
    [
        "npx cypress run --env=fixture-name.cy.ts",
        "npx cypress run --env fixture-name.cy.ts",
        "npx playwright test --project=mobile.cy.ts",
        "npx playwright test --project mobile.cy.ts",
    ],
)
def test_unrelated_option_with_test_suffix_is_not_a_file_target(
    project: Path,
    command: str,
):
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            command,
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


@pytest.mark.parametrize(
    "spec_option",
    ["--spec=config/custom.cy.ts", "--spec config/custom.cy.ts"],
)
def test_non_cypress_spec_option_is_not_a_file_target(
    project: Path,
    spec_option: str,
):
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"python schema_check.py {spec_option}",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


@pytest.mark.parametrize(
    "command",
    [
        "pytest --browser cypress --spec=missing.txt",
        "python tool.py --runner nx --mode e2e --spec=missing.txt",
    ],
)
def test_cypress_like_argument_values_do_not_activate_spec_parsing(
    project: Path,
    command: str,
):
    manifest = load_manifest(write_acceptance_manifest(project, command))

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


@pytest.mark.parametrize(
    "command",
    [
        "npx nx show projects --with-target e2e --spec=missing.txt",
        "npx nx graph --focus app:e2e --spec=missing.txt",
        "npx nx report --file=app:e2e --spec=missing.txt",
    ],
)
def test_nx_non_target_e2e_values_do_not_activate_spec_parsing(
    project: Path,
    command: str,
):
    manifest = load_manifest(write_acceptance_manifest(project, command))

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


def test_npx_package_value_does_not_activate_cypress_spec_parsing(project: Path):
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            "npx -p cypress python tool.py --spec=missing.txt",
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_shell_login_command_string_is_not_a_literal_test_path(
    project: Path,
    shell: str,
):
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f'{shell} -lc "npx cypress run --spec=missing.cy.ts"',
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


def test_env_wrapped_shell_command_string_is_not_a_literal_test_path(project: Path):
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            '/usr/bin/env sh -lc "npx cypress run --spec=missing.cy.ts"',
        )
    )

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


@pytest.mark.parametrize(
    "command",
    [
        'bash -c -- "npx cypress run --spec=missing.cy.ts"',
        'env --ignore-environment bash -lc "npx cypress run --spec=missing.cy.ts"',
    ],
)
def test_shell_command_string_variants_are_not_literal_test_paths(
    project: Path,
    command: str,
):
    manifest = load_manifest(write_acceptance_manifest(project, command))

    errors = ValidationEngine(project_root=project).validate_acceptance(manifest)

    assert acceptance_file_errors(errors) == []


def test_shell_non_command_flag_preserves_positional_test_path(project: Path):
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            "bash --norc missing.cy.ts",
        )
    )

    errors = acceptance_file_errors(
        ValidationEngine(project_root=project).validate_acceptance(manifest)
    )

    assert len(errors) == 1
    assert errors[0].location is not None
    assert errors[0].location.file == "missing.cy.ts"


def test_positional_acceptance_directory_containment_remains_enforced(project: Path):
    outside_tests = project.parent / f"{project.name}-outside-tests"
    outside_tests.mkdir()
    relative_outside_tests = f"../{outside_tests.name}/tests"
    (outside_tests / "tests").mkdir()
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"pytest {relative_outside_tests}",
        )
    )

    errors = validate_manifest_paths(manifest, project)

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
    assert errors[0].location is not None
    assert errors[0].location.file == relative_outside_tests


def test_attached_acceptance_path_option_containment_remains_enforced(project: Path):
    relative_outside_root = "../outside/tests"
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"pytest --rootdir={relative_outside_root} tests/test_inside.py",
        )
    )

    errors = validate_manifest_paths(manifest, project)

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
    assert errors[0].location is not None
    assert errors[0].location.file == relative_outside_root


def test_legacy_command_cwd_does_not_leak_to_later_outside_target(project: Path):
    outside_tests = project.parent / f"{project.name}-later-outside-tests"
    outside_tests.mkdir()
    (outside_tests / "tests").mkdir()
    relative_outside_tests = f"../{outside_tests.name}/tests"
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            "npm --prefix=frontend exec cypress run "
            f"--spec=inside.cy.ts && pytest {relative_outside_tests}",
        )
    )

    errors = validate_manifest_paths(manifest, project)

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
    assert errors[0].location is not None
    assert errors[0].location.file == relative_outside_tests


@pytest.mark.parametrize("target_option", ["--target=e2e", "-t=e2e"])
def test_nx_target_spec_outside_project_is_rejected(
    project: Path,
    target_option: str,
):
    outside_path = project.parent / f"{project.name}-nx-outside.txt"
    outside_path.write_text("outside nx spec\n")
    relative_outside_path = f"../{outside_path.name}"
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npx nx run-many {target_option} --spec={relative_outside_path}",
        )
    )

    errors = validate_manifest_paths(manifest, project)

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
    assert errors[0].location is not None
    assert errors[0].location.file == relative_outside_path


def test_nx_configured_target_spec_outside_project_is_rejected(project: Path):
    outside_path = project.parent / f"{project.name}-configured-outside.txt"
    outside_path.write_text("outside configured target\n")
    relative_outside_path = f"../{outside_path.name}"
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npx nx run example:e2e:ci --spec={relative_outside_path}",
        )
    )

    errors = validate_manifest_paths(manifest, project)

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
    assert errors[0].location is not None
    assert errors[0].location.file == relative_outside_path


@pytest.mark.parametrize("wrapper", ["/usr/bin/env", "uv run"])
def test_nested_npx_package_injection_outside_spec_is_rejected(
    project: Path,
    wrapper: str,
):
    outside_path = project.parent / f"{project.name}-nested-npx-outside.txt"
    outside_path.write_text("outside nested npx\n")
    relative_outside_path = f"../{outside_path.name}"
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"{wrapper} npx -p nx nx run example:e2e:ci "
            f"--spec={relative_outside_path}",
        )
    )

    errors = validate_manifest_paths(manifest, project)

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
    assert errors[0].location is not None
    assert errors[0].location.file == relative_outside_path


def test_cypress_spec_assignment_outside_project_is_rejected(project: Path):
    outside_path = project.parent / f"{project.name}-outside.cy.ts"
    outside_path.write_text("describe('outside', () => {})\n")
    relative_outside_path = f"../{outside_path.name}"
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npx cypress run --spec={relative_outside_path}",
        )
    )

    errors = validate_manifest_paths(manifest, project)

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
    assert errors[0].location is not None
    assert errors[0].location.file == relative_outside_path


def test_nonconventional_cypress_spec_outside_project_is_rejected(project: Path):
    outside_path = project.parent / f"{project.name}-outside.txt"
    outside_path.write_text("outside spec\n")
    relative_outside_path = f"../{outside_path.name}"
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npx cypress run --spec={relative_outside_path}",
        )
    )

    errors = validate_manifest_paths(manifest, project)

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
    assert errors[0].location is not None
    assert errors[0].location.file == relative_outside_path


def test_attached_command_cwd_outside_project_is_rejected(project: Path):
    outside_dir = project.parent / f"{project.name}-outside-project"
    outside_dir.mkdir()
    spec_path = "outside.cy.ts"
    (outside_dir / spec_path).write_text("describe('outside cwd', () => {})\n")
    relative_outside_dir = f"../{outside_dir.name}"
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npm --prefix={relative_outside_dir} exec cypress run --spec={spec_path}",
        )
    )

    errors = validate_manifest_paths(manifest, project)

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
    assert errors[0].location is not None
    assert errors[0].location.file == f"{relative_outside_dir}/{spec_path}"


@pytest.mark.parametrize("dir_option", ["--dir=frontend", "--dir frontend"])
def test_pnpm_command_cwd_outside_spec_is_rejected(
    project: Path,
    dir_option: str,
):
    outside_path = project.parent / f"{project.name}-pnpm-outside.txt"
    outside_path.write_text("outside pnpm spec\n")
    relative_outside_path = f"../../{outside_path.name}"
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"pnpm {dir_option} exec cypress run --spec={relative_outside_path}",
        )
    )

    errors = validate_manifest_paths(manifest, project)

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
    assert errors[0].location is not None
    assert errors[0].location.file == f"frontend/{relative_outside_path}"


@pytest.mark.parametrize("runner", ["npm", "pnpm"])
def test_package_exec_separator_outside_spec_is_rejected(
    project: Path,
    runner: str,
):
    outside_path = project.parent / f"{project.name}-{runner}-outside.txt"
    outside_path.write_text("outside exec separator\n")
    relative_outside_path = f"../{outside_path.name}"
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"{runner} exec -- cypress run --spec={relative_outside_path}",
        )
    )

    errors = validate_manifest_paths(manifest, project)

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
    assert errors[0].location is not None
    assert errors[0].location.file == relative_outside_path


@pytest.mark.parametrize(
    "cwd_option",
    ["--prefix=frontend", "--prefix frontend"],
)
def test_windows_absolute_spec_with_command_cwd_is_rejected(
    project: Path,
    cwd_option: str,
):
    windows_path = "C:\\outside\\custom.txt"
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npm {cwd_option} exec cypress run --spec='{windows_path}'",
        )
    )

    errors = validate_manifest_paths(manifest, project)

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
    assert errors[0].location is not None
    assert errors[0].location.file == windows_path


def test_cypress_spec_list_rejects_nonleading_project_escape(project: Path):
    inside_path = "cypress/e2e/inside.cy.ts"
    full_inside_path = project / inside_path
    full_inside_path.parent.mkdir(parents=True)
    full_inside_path.write_text("describe('inside', () => {})\n")
    outside_path = project.parent / f"{project.name}-listed-outside.cy.ts"
    outside_path.write_text("describe('outside', () => {})\n")
    relative_outside_path = f"../{outside_path.name}"
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            f"npx cypress run --spec={inside_path},{relative_outside_path}",
        )
    )

    errors = validate_manifest_paths(manifest, project)

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
    assert errors[0].location is not None
    assert errors[0].location.file == relative_outside_path


def test_cypress_spec_glob_outside_project_is_rejected(project: Path):
    manifest = load_manifest(
        write_acceptance_manifest(
            project,
            "npx cypress run --spec=../outside/*.cy.ts",
        )
    )

    errors = validate_manifest_paths(manifest, project)

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
    assert errors[0].location is not None
    assert errors[0].location.file == "../outside/*.cy.ts"
