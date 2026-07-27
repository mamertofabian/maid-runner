"""Regression tests for shell-wrapped app-root Vitest E230 coverage."""

from maid_runner.core import _test_command_targets as targets


def test_executing_targets_accept_shell_wrapped_app_root_vitest_with_root_paths(
    tmp_path,
):
    backend_test = (
        tmp_path
        / "apps"
        / "backend"
        / "src"
        / "markerManager"
        / "services"
        / "markerManagerClient.test.ts"
    )
    controller_test = (
        tmp_path
        / "apps"
        / "backend"
        / "src"
        / "markerManager"
        / "markerManagerController.test.ts"
    )
    backend_test.parent.mkdir(parents=True)
    backend_test.write_text("test('client', () => {})\n")
    controller_test.write_text("test('controller', () => {})\n")

    command = (
        "bash",
        "-lc",
        "ROOT=$PWD; cd apps/backend && pnpm exec dotenv -c test -- vitest run "
        "$ROOT/apps/backend/src/markerManager/services/markerManagerClient.test.?s "
        "$ROOT/apps/backend/src/markerManager/markerManagerController.test.?s",
    )

    paths = targets.test_paths_from_executing_validate_command(command, tmp_path)
    covered = targets.test_files_covered_by_validate_command(
        command,
        [
            "apps/backend/src/markerManager/services/markerManagerClient.test.ts",
            "apps/backend/src/markerManager/markerManagerController.test.ts",
        ],
        tmp_path,
    )

    assert paths == [
        "apps/backend/src/markerManager/services/markerManagerClient.test.?s",
        "apps/backend/src/markerManager/markerManagerController.test.?s",
    ]
    assert covered == {
        "apps/backend/src/markerManager/services/markerManagerClient.test.ts",
        "apps/backend/src/markerManager/markerManagerController.test.ts",
    }


def test_glob_target_does_not_cover_nested_test_file(tmp_path):
    direct_test = tmp_path / "tests" / "direct.test.ts"
    nested_test = tmp_path / "tests" / "unit" / "nested.test.ts"
    direct_test.parent.mkdir(parents=True)
    nested_test.parent.mkdir(parents=True)
    direct_test.write_text("test('direct', () => {})\n")
    nested_test.write_text("test('nested', () => {})\n")

    covered = targets.test_files_covered_by_validate_command(
        ("vitest", "run", "tests/*.test.ts"),
        ["tests/direct.test.ts", "tests/unit/nested.test.ts"],
        tmp_path,
    )

    assert covered == {"tests/direct.test.ts"}


def test_executing_targets_reject_shell_wrapper_that_only_echoes_test_path(tmp_path):
    test_file = tmp_path / "apps" / "backend" / "src" / "current.test.ts"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("test('current', () => {})\n")

    paths = targets.test_paths_from_executing_validate_command(
        (
            "bash",
            "-lc",
            "ROOT=$PWD; cd apps/backend && echo "
            "$ROOT/apps/backend/src/current.test.ts",
        ),
        tmp_path,
    )

    assert paths == []


def test_executing_targets_reject_shell_or_branch_before_runner(tmp_path):
    test_file = tmp_path / "apps" / "backend" / "src" / "current.test.ts"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("test('current', () => {})\n")

    paths = targets.test_paths_from_executing_validate_command(
        (
            "bash",
            "-lc",
            "ROOT=$PWD; cd apps/backend || pnpm exec dotenv -c test -- "
            "vitest run $ROOT/apps/backend/src/current.test.ts",
        ),
        tmp_path,
    )

    assert paths == []


def test_executing_targets_reject_missing_cd_before_runner(tmp_path):
    test_file = tmp_path / "apps" / "backend" / "src" / "current.test.ts"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("test('current', () => {})\n")

    paths = targets.test_paths_from_executing_validate_command(
        (
            "bash",
            "-lc",
            "ROOT=$PWD; cd missing && pnpm exec dotenv -c test -- "
            "vitest run $ROOT/apps/backend/src/current.test.ts",
        ),
        tmp_path,
    )

    assert paths == []


def test_executing_targets_reject_command_scoped_root_assignment(tmp_path):
    test_file = tmp_path / "tests" / "current.test.ts"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("test('current', () => {})\n")

    paths = targets.test_paths_from_executing_validate_command(
        (
            "bash",
            "-lc",
            "ROOT=$PWD vitest run $ROOT/tests/current.test.ts",
        ),
        tmp_path,
    )

    assert paths == []
