"""Deno dependency-resolution flags must not hide explicit native test targets."""

from pathlib import Path
import shutil

import pytest
import yaml

from maid_runner import validate
from maid_runner.core._validation_test_artifacts import validate_manifest_test_commands
from maid_runner.core.manifest import load_manifest
from maid_runner.core.plan_lock import create_plan_lock
from maid_runner.core.result import ErrorCode
from maid_runner.core.test_runner import run_manifest_tests
from maid_runner.core.types import ValidationMode


_TEST_PATH = "tests/env.test.ts"

_ACCEPTED_FLAG_SETS = [
    ["--no-lock"],
    ["--no-lock", "--node-modules-dir=none"],
    ["--node-modules-dir"],
    ["--node-modules-dir=auto"],
    ["--node-modules-dir=manual"],
    ["--node-modules-dir=true"],
    ["--node-modules-dir=false"],
    ["--frozen"],
    ["--frozen=true"],
    ["--frozen=false"],
    ["--cached-only"],
    ["--no-remote"],
    ["--no-npm"],
    ["--no-check", "--allow-env", "--no-lock", "--node-modules-dir=none"],
]

_REJECTED_FLAG_SETS = [
    ["--no-lock", "--no-lock"],
    ["--node-modules-dir=none", "--node-modules-dir=auto"],
    ["--frozen", "--frozen=false"],
    ["--cached-only", "--cached-only"],
    ["--no-remote", "--no-remote"],
    ["--no-npm", "--no-npm"],
    ["--node-modules-dir=bogus"],
    ["--node-modules-dir=TRUE"],
    ["--node-modules-dir="],
    ["--frozen=maybe"],
    ["--no-lock=true"],
    ["--cached-only=true"],
    ["--no-remote=false"],
    ["--no-npm=1"],
    ["--no-lock", "--filter", "missing"],
    ["--node-modules-dir=none", "--no-run"],
    ["--no-lock", "--unknown-option"],
]


def _project(
    root: Path, flags: list[str], *, target_first: bool = False, passes: bool = True
) -> Path:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src/env.ts").write_text(
        "export function normalizeEnv(value: string): string {\n"
        "  return value.trim().toLowerCase();\n"
        "}\n"
    )
    expected = "live" if passes else "test"
    (root / _TEST_PATH).write_text(
        'import { normalizeEnv } from "../src/env.ts";\n'
        "const { test } = Deno;\n"
        'test("normalizes the configured environment", () => {\n'
        f'  if (normalizeEnv(" Live ") !== "{expected}") throw new Error("wrong");\n'
        "});\n"
    )
    (root / "tests/unrelated.test.ts").write_text('Deno.test("unrelated", () => {});\n')
    command = ["deno", "test", *flags, _TEST_PATH]
    if target_first:
        command = ["deno", "test", _TEST_PATH, *flags]
    manifest = root / "manifests/deno-env.manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Exercise a native Deno test selected with dependency flags",
                "type": "fix",
                "created": "2026-10-23T00:00:00Z",
                "files": {
                    "create": [
                        {
                            "path": "src/env.ts",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "normalizeEnv",
                                    "args": [{"name": "value", "type": "string"}],
                                    "returns": "string",
                                }
                            ],
                        }
                    ]
                },
                "validate": [command],
            },
            sort_keys=False,
        )
    )
    return manifest


def _behavioral_error_codes(manifest: Path, root: Path) -> list[ErrorCode]:
    result = validate(
        manifest,
        mode=ValidationMode.BEHAVIORAL,
        use_chain=False,
        manifest_dir=root / "manifests",
        project_root=root,
    )
    return [error.code for error in result.errors]


def _write_declared_test_manifest(root: Path, flags: list[str]) -> Path:
    manifest = _project(root, flags)
    data = yaml.safe_load(manifest.read_text())
    data["files"]["create"].append(
        {
            "path": _TEST_PATH,
            "artifacts": [
                {
                    "kind": "test_function",
                    "name": "normalizes the configured environment",
                }
            ],
        }
    )
    manifest.write_text(yaml.safe_dump(data, sort_keys=False))
    return manifest


@pytest.mark.parametrize("flags", _ACCEPTED_FLAG_SETS)
@pytest.mark.parametrize("target_first", [False, True])
def test_dependency_flags_keep_native_test_as_behavioral_evidence(
    tmp_path: Path, flags: list[str], target_first: bool
) -> None:
    manifest = _project(tmp_path, flags, target_first=target_first)

    codes = _behavioral_error_codes(manifest, tmp_path)

    assert codes == []


@pytest.mark.parametrize("flags", _ACCEPTED_FLAG_SETS)
def test_dependency_flags_keep_native_test_in_plan_lock_hashes(
    tmp_path: Path, flags: list[str]
) -> None:
    manifest = _project(tmp_path, flags)

    lock = create_plan_lock(manifest, tmp_path)

    assert set(lock.test_hashes) == {_TEST_PATH}


@pytest.mark.parametrize("flags", _ACCEPTED_FLAG_SETS)
def test_dependency_flags_satisfy_command_integrity_for_declared_test(
    tmp_path: Path, flags: list[str]
) -> None:
    manifest = _write_declared_test_manifest(tmp_path, flags)

    errors = validate_manifest_test_commands(load_manifest(manifest), tmp_path)

    assert errors == []


@pytest.mark.parametrize("flags", _REJECTED_FLAG_SETS)
def test_invalid_or_selecting_dependency_flags_do_not_claim_execution(
    tmp_path: Path, flags: list[str]
) -> None:
    manifest = _write_declared_test_manifest(tmp_path, flags)

    errors = validate_manifest_test_commands(load_manifest(manifest), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


@pytest.mark.parametrize("flags", _REJECTED_FLAG_SETS)
def test_invalid_or_selecting_dependency_flags_provide_no_usage_evidence(
    tmp_path: Path, flags: list[str]
) -> None:
    manifest = _project(tmp_path, flags)

    codes = _behavioral_error_codes(manifest, tmp_path)

    assert ErrorCode.ARTIFACT_NOT_USED_IN_TESTS in codes


@pytest.mark.parametrize(
    "flags", [["--no-lock"], ["--no-lock", "--node-modules-dir=none"]]
)
@pytest.mark.parametrize("passes", [True, False])
def test_native_deno_run_with_dependency_flags_reports_real_result(
    tmp_path: Path, flags: list[str], passes: bool
) -> None:
    if shutil.which("deno") is None:
        pytest.skip("Deno is needed only for native execution coverage")
    manifest = _project(tmp_path, flags, passes=passes)

    result = run_manifest_tests(manifest, project_root=tmp_path)

    assert (result.total, result.passed, result.failed) == (
        1,
        int(passes),
        int(not passes),
    )
