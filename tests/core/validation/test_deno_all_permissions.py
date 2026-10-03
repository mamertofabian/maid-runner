"""Full-permission flags must not hide executable Deno behavioral targets."""

from pathlib import Path
import shutil

import pytest
import yaml

from maid_runner.core._validation_test_artifacts import validate_manifest_test_commands
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.test_runner import run_manifest_tests


_TEST_PATH = "tests/permission.test.ts"


def _project(root: Path, args: list[str], *, subcommand: str = "test") -> Path:
    (root / "tests").mkdir()
    (root / _TEST_PATH).write_text(
        "Deno.test('permission boundary', async () => {\n"
        "  const value = await Deno.readTextFile('input.txt');\n"
        "  await Deno.writeTextFile('executed.txt', value);\n"
        "  if (value !== 'expected') throw new Error('unexpected input');\n"
        "});\n"
    )
    (root / "tests/unrelated.test.ts").write_text("Deno.test('unrelated', () => {});\n")
    (root / "input.txt").write_text("expected")
    manifest = root / "permissions.manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Exercise a Deno permission-sensitive test",
                "type": "fix",
                "created": "2026-09-28",
                "files": {
                    "create": [
                        {
                            "path": _TEST_PATH,
                            "artifacts": [
                                {"kind": "test_function", "name": "permission boundary"}
                            ],
                        }
                    ]
                },
                "validate": [["deno", subcommand, *args]],
            },
            sort_keys=False,
        )
    )
    return manifest


@pytest.mark.parametrize("flag", ["--allow-all", "-A"])
@pytest.mark.parametrize("position", ["before", "after", "combined"])
def test_permission_flags_preserve_explicit_deno_target_coverage(
    tmp_path: Path, flag: str, position: str
) -> None:
    args = [flag, _TEST_PATH]
    if position == "after":
        args = [_TEST_PATH, flag]
    elif position == "combined":
        args = ["--no-check", flag, _TEST_PATH]
    manifest = _project(tmp_path, args)

    errors = validate_manifest_test_commands(load_manifest(manifest), tmp_path)

    assert errors == []


@pytest.mark.parametrize("flag", ["--allow-all", "-A"])
@pytest.mark.parametrize(
    "options",
    [
        ["--help", _TEST_PATH],
        ["--no-run", _TEST_PATH],
        ["--filter", "missing", _TEST_PATH],
        ["--filter=missing", _TEST_PATH],
        ["--unknown-option", _TEST_PATH],
        ["--junit-path", _TEST_PATH, "tests/unrelated.test.ts"],
        ["tests/unrelated.test.ts", "--", _TEST_PATH],
    ],
)
def test_permission_flags_do_not_bypass_target_or_execution_guards(
    tmp_path: Path, flag: str, options: list[str]
) -> None:
    manifest = _project(tmp_path, [flag, *options])

    errors = validate_manifest_test_commands(load_manifest(manifest), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]
    result = run_manifest_tests(manifest, project_root=tmp_path)
    assert result.total == 0
    assert not (tmp_path / "executed.txt").exists()


@pytest.mark.parametrize("flag", ["--allow-all=true", "-A=true", "-Aq"])
def test_permission_flag_value_or_cluster_is_not_guessed(
    tmp_path: Path, flag: str
) -> None:
    manifest = _project(tmp_path, [flag, _TEST_PATH])

    errors = validate_manifest_test_commands(load_manifest(manifest), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


@pytest.mark.parametrize("subcommand", ["run", "check", "fmt"])
def test_permissions_do_not_turn_other_deno_subcommands_into_test_runners(
    tmp_path: Path, subcommand: str
) -> None:
    manifest = _project(tmp_path, ["--allow-all", _TEST_PATH], subcommand=subcommand)

    errors = validate_manifest_test_commands(load_manifest(manifest), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


@pytest.mark.parametrize("flag", ["--allow-all", "-A"])
@pytest.mark.parametrize("passes", [True, False])
@pytest.mark.parametrize("position", ["before", "after", "combined"])
def test_native_deno_permission_test_executes_and_reports_its_result(
    tmp_path: Path, flag: str, passes: bool, position: str
) -> None:
    if shutil.which("deno") is None:
        pytest.skip("Deno is needed only for native execution coverage")
    args = [flag, _TEST_PATH]
    if position == "after":
        args = [_TEST_PATH, flag]
    elif position == "combined":
        args = ["--no-check", flag, _TEST_PATH]
    manifest = _project(tmp_path, args)
    value = "expected" if passes else "wrong"
    (tmp_path / "input.txt").write_text(value)

    result = run_manifest_tests(manifest, project_root=tmp_path)

    assert (result.total, result.passed, result.failed) == (
        1,
        int(passes),
        int(not passes),
    )
    assert (tmp_path / "executed.txt").read_text() == value


@pytest.mark.parametrize(
    "permissions",
    [
        ["--allow-all", "--allow-env"],
        ["--allow-env", "--allow-all"],
        ["-A", "--allow-env"],
        ["--allow-env", "-A"],
        ["--allow-all", "--allow-env=HOME"],
        ["--allow-env=HOME", "--allow-all"],
        ["-A", "--allow-env=HOME"],
        ["--allow-env=HOME", "-A"],
        ["--allow-all", "--allow-all"],
        ["-A", "-A"],
        ["--allow-all", "-A"],
        ["-A", "--allow-all"],
    ],
)
def test_conflicting_permission_flags_do_not_claim_test_execution(
    tmp_path: Path, permissions: list[str]
) -> None:
    manifest = _project(tmp_path, [*permissions, _TEST_PATH])

    errors = validate_manifest_test_commands(load_manifest(manifest), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]
    result = run_manifest_tests(manifest, project_root=tmp_path)
    assert result.total == 0
    assert not (tmp_path / "executed.txt").exists()
