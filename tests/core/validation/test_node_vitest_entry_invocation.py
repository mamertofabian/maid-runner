"""Behavioral contract for the direct Node-to-Vitest package entry point."""

import os
import shlex
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

from maid_runner.core._validation_test_artifacts import validate_manifest_test_commands
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode


_ENTRY = "node_modules/vitest/vitest.mjs"
_TEST = "tests/unit/value.test.ts"


def _project(root: Path, command: list[str]):
    (root / "src").mkdir(exist_ok=True)
    (root / "src/value.ts").write_text(
        "export function value(): number { return 42; }\n"
    )
    test = root / _TEST
    test.parent.mkdir(parents=True, exist_ok=True)
    test.write_text(
        "import { it, expect } from 'vitest';\n"
        "import { value } from '../../src/value';\n"
        "it('value', () => { expect(value()).toBe(42); });\n"
    )
    manifest = root / "inventory.manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Direct Vitest entry",
                "type": "fix",
                "created": "2026-09-30T00:00:00Z",
                "files": {
                    "edit": [
                        {
                            "path": "src/value.ts",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "value",
                                    "args": [],
                                    "returns": "number",
                                }
                            ],
                        }
                    ],
                    "read": [_TEST],
                },
                "validate": [command],
            }
        )
    )
    return load_manifest(manifest)


@pytest.mark.parametrize("entry_form", ["relative", "dot_relative", "absolute"])
@pytest.mark.parametrize("target", [_TEST, "tests/unit"])
def test_direct_node_vitest_entry_covers_declared_test_targets(
    tmp_path: Path, entry_form, target
):
    entry = {
        "relative": _ENTRY,
        "dot_relative": f"./{_ENTRY}",
        "absolute": str(tmp_path / _ENTRY),
    }[entry_form]
    manifest = _project(tmp_path, ["node", entry, "run", target])

    errors = validate_manifest_test_commands(manifest, tmp_path)

    assert errors == []


@pytest.mark.parametrize(
    "entry",
    [
        "vitest.mjs",
        "tools/vitest.mjs",
        "node_modules/not-vitest/vitest.mjs",
        "fake_node_modules/vitest/vitest.mjs",
        "node_modules/vitest/cli.mjs",
        "node_modules/vitest/vitest.mjs.bak",
        "$SDK/node_modules/vitest/vitest.mjs",
        "*/node_modules/vitest/vitest.mjs",
        "../node_modules/vitest/vitest.mjs",
        "--require=/tmp/node_modules/vitest/vitest.mjs",
        "--import=/tmp/node_modules/vitest/vitest.mjs",
        "--eval=/tmp/node_modules/vitest/vitest.mjs",
    ],
)
def test_arbitrary_or_dynamic_node_scripts_do_not_claim_vitest_coverage(
    tmp_path: Path, entry
):
    manifest = _project(tmp_path, ["node", entry, "run", _TEST])

    errors = validate_manifest_test_commands(manifest, tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


@pytest.mark.parametrize(
    "arguments",
    [
        ["list", _TEST],
        ["run", "--help", _TEST],
        ["run", "--version", _TEST],
        ["run", "--list", _TEST],
        ["run", "--dry-run", _TEST],
    ],
)
def test_node_vitest_nonexecuting_modes_still_report_e230(tmp_path: Path, arguments):
    manifest = _project(tmp_path, ["node", _ENTRY, *arguments])

    errors = validate_manifest_test_commands(manifest, tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


@pytest.mark.parametrize(
    "prefix",
    [
        ["node", "--eval", "void 0"],
        ["node", "--require", "shim.cjs"],
        ["node", "--import", "shim.mjs"],
        ["env", "NODE_OPTIONS=--eval=void0", "node"],
        ["uv", "run", "node"],
        ["pnpm", "exec", "node"],
    ],
)
def test_node_vm_flags_and_unproven_wrappers_remain_rejected(tmp_path: Path, prefix):
    manifest = _project(tmp_path, [*prefix, _ENTRY, "run", _TEST])

    errors = validate_manifest_test_commands(manifest, tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


@pytest.mark.parametrize("option", ["--config", "--outputFile"])
def test_node_vitest_option_values_do_not_count_as_executed_test_targets(
    tmp_path: Path, option
):
    manifest = _project(
        tmp_path, ["node", _ENTRY, "run", option, _TEST, "tests/other.test.ts"]
    )

    errors = validate_manifest_test_commands(manifest, tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]
    assert _TEST in errors[0].message


@pytest.mark.parametrize("shell", ["bash", "sh"])
@pytest.mark.parametrize("mode", ["-c", "-lc"])
def test_shell_wrapped_node_vitest_entry_cannot_claim_direct_execution(
    tmp_path: Path, shell, mode
):
    inner = shlex.join(["node", _ENTRY, "run", _TEST])
    manifest = _project(tmp_path, [shell, mode, inner])

    errors = validate_manifest_test_commands(manifest, tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_existing_local_vitest_binary_recognition_remains_intact(tmp_path: Path):
    manifest = _project(tmp_path, ["node_modules/.bin/vitest", "run", _TEST])

    errors = validate_manifest_test_commands(manifest, tmp_path)

    assert errors == []


def test_node_vitest_entry_executes_declared_suite_when_sdk_available(tmp_path: Path):
    configured = os.environ.get("MAID_TEST_VITEST_ENTRY")
    if not configured or not Path(configured).is_file() or shutil.which("node") is None:
        pytest.skip(
            "Set MAID_TEST_VITEST_ENTRY to an installed Vitest package entry for runtime proof"
        )
    entry = Path(configured).absolute()
    command = ["node", str(entry), "run", _TEST, "--maxWorkers=1", "--no-cache"]
    manifest = _project(tmp_path, command)
    assert validate_manifest_test_commands(manifest, tmp_path) == []
    (tmp_path / "package.json").write_text('{"type":"module"}\n')
    local_modules = tmp_path / "node_modules"
    local_modules.mkdir()
    (local_modules / "vitest").symlink_to(
        entry.resolve().parent, target_is_directory=True
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
    (tmp_path / "src/value.ts").write_text(
        "export function value(): number { return 41; }\n"
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
    assert "value" in failed.stdout + failed.stderr
