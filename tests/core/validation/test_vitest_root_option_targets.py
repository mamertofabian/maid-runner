"""Behavioral contract for Vitest root options and explicit test coverage."""

from pathlib import Path
import os
import shlex
import shutil
import subprocess

import pytest
import yaml

from maid_runner.core import _test_command_targets as targets
from maid_runner.core._validation_test_artifacts import validate_manifest_test_commands
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode


_INSIDE = "frontend/tests/unit/value.test.ts"
_OUTSIDE = "tests/unit/value.test.ts"
_ENTRY = "node_modules/vitest/vitest.mjs"


def _project(root: Path, command: list[str], required: str):
    for relative in (_INSIDE, _OUTSIDE):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "import { it, expect } from 'vitest'; it('value', () => { expect(1).toBe(1); });\n"
        )
    manifest = root / "task.manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Vitest root option coverage",
                "type": "fix",
                "created": "2026-09-30T00:00:00Z",
                "files": {
                    "scope": [
                        {"path": "src/value.ts", "reason": "Fixture production scope"}
                    ],
                    "read": [required],
                },
                "validate": [command],
            }
        )
    )
    (root / "src").mkdir(exist_ok=True)
    (root / "src/value.ts").write_text("export const value = 1;\n")
    return load_manifest(manifest)


@pytest.mark.parametrize(
    "runner", [["vitest"], ["node_modules/.bin/vitest"], ["node", _ENTRY]]
)
@pytest.mark.parametrize(
    "root_option", [["--root", _OUTSIDE], [f"--root={_OUTSIDE}"], ["-r", _OUTSIDE]]
)
def test_vitest_root_values_never_count_as_executed_test_targets(
    tmp_path: Path, runner, root_option
):
    command = [*runner, "run", *root_option, "--passWithNoTests"]
    manifest = _project(tmp_path, command, _OUTSIDE)

    errors = validate_manifest_test_commands(manifest, tmp_path)
    discovered = targets.test_paths_from_validate_command(tuple(command), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]
    assert _OUTSIDE not in discovered


@pytest.mark.parametrize("runner", [["vitest"], ["node", _ENTRY]])
@pytest.mark.parametrize(
    "root_option", [["--root", "frontend"], ["--root=frontend"], ["-r", "frontend"]]
)
@pytest.mark.parametrize("root_after_target", [False, True])
def test_explicit_vitest_targets_resolve_under_root_independent_of_option_order(
    tmp_path: Path, runner, root_option, root_after_target
):
    arguments = (
        [_OUTSIDE, *root_option] if root_after_target else [*root_option, _OUTSIDE]
    )
    command = [*runner, "run", *arguments]
    manifest = _project(tmp_path, command, _INSIDE)

    errors = validate_manifest_test_commands(manifest, tmp_path)
    paths = targets.test_paths_from_executing_validate_command(tuple(command), tmp_path)
    discovered = targets.test_paths_from_validate_command(tuple(command), tmp_path)

    assert errors == []
    assert paths == [_INSIDE]
    assert discovered == [_INSIDE]


def test_cwd_relative_filter_inside_vitest_root_remains_covered(tmp_path: Path):
    command = ["vitest", "run", "--root", "frontend", _INSIDE]
    _project(tmp_path, command, _INSIDE)

    covered = targets.test_files_covered_by_validate_command(
        tuple(command), [_INSIDE, _OUTSIDE], tmp_path
    )

    assert covered == {_INSIDE}


@pytest.mark.parametrize("target", [_OUTSIDE, "../tests/unit/value.test.ts"])
def test_vitest_root_prevents_coverage_claims_for_tests_outside_it(
    tmp_path: Path, target
):
    command = ["vitest", "run", target, "--root", "frontend"]
    manifest = _project(tmp_path, command, _OUTSIDE)

    errors = validate_manifest_test_commands(manifest, tmp_path)
    covered = targets.test_files_covered_by_validate_command(
        tuple(command), [_INSIDE, _OUTSIDE], tmp_path
    )

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]
    assert _OUTSIDE not in covered


def test_absolute_literal_vitest_root_resolves_repo_relative_targets(tmp_path: Path):
    command = ["vitest", "run", "--root", str(tmp_path / "frontend"), _OUTSIDE]
    manifest = _project(tmp_path, command, _INSIDE)

    errors = validate_manifest_test_commands(manifest, tmp_path)

    assert errors == []


@pytest.mark.parametrize(
    "root_option",
    [
        ["--root"],
        ["--root="],
        ["--root", "missing"],
        ["--root", "$ROOT"],
        ["--root", "frontend", "--root", "."],
        ["--config", "--root", _OUTSIDE],
        ["--outputFile", "--root", _OUTSIDE],
    ],
)
def test_missing_dynamic_or_ambiguous_vitest_roots_fail_closed(
    tmp_path: Path, root_option
):
    command = ["vitest", "run", _OUTSIDE, *root_option]
    manifest = _project(tmp_path, command, _OUTSIDE)

    errors = validate_manifest_test_commands(manifest, tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_vitest_root_bindings_compose_with_package_cwd_and_shell_context(
    tmp_path: Path,
):
    commands = [
        ["pnpm", "--dir", "frontend", "vitest", "run", "--root", ".", _OUTSIDE],
        ["bash", "-c", shlex.join(["vitest", "run", "--root", "frontend", _OUTSIDE])],
    ]
    _project(tmp_path, commands[0], _INSIDE)

    for command in commands:
        covered = targets.test_files_covered_by_validate_command(
            tuple(command), [_INSIDE, _OUTSIDE], tmp_path
        )
        assert covered == {_INSIDE}


def test_vitest_root_does_not_leak_into_following_discovery_segments(tmp_path: Path):
    _project(tmp_path, ["vitest", "run", _OUTSIDE], _OUTSIDE)
    python_test = tmp_path / "tests/test_other.py"
    python_test.write_text("def test_other():\n    assert 1 == 1\n")
    command = (
        "vitest",
        "run",
        "--root",
        "frontend",
        _OUTSIDE,
        "&&",
        "pytest",
        "tests/test_other.py",
    )

    discovered = targets.test_paths_from_validate_command(command, tmp_path)

    assert discovered == [_INSIDE, "tests/test_other.py"]


def test_root_looking_filter_after_option_delimiter_does_not_change_root(
    tmp_path: Path,
):
    command = ["vitest", "run", "--root", "frontend", "--", _OUTSIDE, "--root", _INSIDE]
    manifest = _project(tmp_path, command, _INSIDE)

    errors = validate_manifest_test_commands(manifest, tmp_path)
    paths = targets.test_paths_from_executing_validate_command(tuple(command), tmp_path)

    assert errors == []
    assert paths == [_INSIDE]


def test_pytest_rootdir_keeps_existing_cwd_relative_target_semantics(tmp_path: Path):
    (tmp_path / "frontend").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_value.py").write_text(
        "def test_value():\n    assert 1 == 1\n"
    )

    paths = targets.test_paths_from_executing_validate_command(
        ("pytest", "--rootdir", "frontend", "tests/test_value.py"), tmp_path
    )

    assert paths == ["tests/test_value.py"]


def test_vitest_root_runtime_proof_when_sdk_available(tmp_path: Path):
    configured = os.environ.get("MAID_TEST_VITEST_ENTRY")
    if not configured or not Path(configured).is_file() or shutil.which("node") is None:
        pytest.skip("Set MAID_TEST_VITEST_ENTRY for optional actual SDK root proof")
    entry = Path(configured).absolute()
    command = [
        "node",
        str(entry),
        "run",
        _OUTSIDE,
        "--root",
        "frontend",
        "--maxWorkers=1",
        "--no-cache",
    ]
    manifest = _project(tmp_path, command, _INSIDE)
    assert validate_manifest_test_commands(manifest, tmp_path) == []
    (tmp_path / "package.json").write_text('{"type":"module"}\n')
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules/vitest").symlink_to(
        entry.resolve().parent, target_is_directory=True
    )
    (tmp_path / _OUTSIDE).write_text(
        "import {it,expect} from 'vitest'; it('outside must not run',()=>{expect(1).toBe(2);});\n"
    )
    environment = dict(os.environ)
    environment.pop("NODE_OPTIONS", None)

    passed = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    (tmp_path / _INSIDE).write_text(
        "import {it,expect} from 'vitest'; it('inside must fail',()=>{expect(1).toBe(2);});\n"
    )
    failed = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert failed.returncode != 0
    assert "inside must fail" in failed.stdout + failed.stderr
