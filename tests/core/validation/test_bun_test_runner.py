"""Behavioral contract for explicit Bun test commands."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from maid_runner.core._validation_test_artifacts import (
    validate_manifest_test_commands,
)
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.test_runner import run_manifest_tests


def _write_bun_test_project(
    root: Path,
    *,
    subcommand: str = "test",
    options: tuple[str, ...] = (),
) -> Path:
    test_file = root / "tests" / "maid-onboarding.test.ts"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "import { expect, test } from 'bun:test';\n"
        "test('keeps local MAID onboarding active', () => expect(true).toBe(true));\n",
        encoding="utf-8",
    )

    manifest_dir = root / "manifests"
    manifest_dir.mkdir()
    manifest_path = manifest_dir / "bun-test.manifest.yaml"
    command = ", ".join(("bun", subcommand, *options))
    manifest_path.write_text(
        'schema: "2"\n'
        'goal: "Exercise an explicit Bun behavioral test"\n'
        "type: fix\n"
        'created: "2026-09-15T00:00:00Z"\n'
        "files:\n"
        "  create:\n"
        "    - path: tests/maid-onboarding.test.ts\n"
        "      artifacts:\n"
        "        - kind: test_function\n"
        "          name: keeps local MAID onboarding active\n"
        "validate:\n"
        f"  - [{command}]\n",
        encoding="utf-8",
    )
    return manifest_path


def test_command_integrity_accepts_explicit_bun_test_file(tmp_path: Path) -> None:
    manifest_path = _write_bun_test_project(
        tmp_path,
        options=("tests/maid-onboarding.test.ts",),
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert errors == []


def test_run_manifest_tests_executes_explicit_bun_test_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _write_bun_test_project(
        tmp_path,
        options=("tests/maid-onboarding.test.ts",),
    )
    executable = tmp_path / "bin" / "bun"
    executable.parent.mkdir()
    executable.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > bun-args.txt\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{executable.parent}{os.pathsep}{os.environ['PATH']}")

    result = run_manifest_tests(manifest_path, project_root=tmp_path)

    assert (result.total, result.passed, result.failed) == (1, 1, 0)
    assert (tmp_path / "bun-args.txt").read_text(encoding="utf-8").splitlines() == [
        "test",
        "tests/maid-onboarding.test.ts",
    ]


def test_command_integrity_rejects_non_test_bun_subcommand(tmp_path: Path) -> None:
    manifest_path = _write_bun_test_project(
        tmp_path,
        subcommand="run",
        options=("tests/maid-onboarding.test.ts",),
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_command_integrity_rejects_non_executing_bun_test_mode(
    tmp_path: Path,
) -> None:
    manifest_path = _write_bun_test_project(
        tmp_path,
        options=("--help", "tests/maid-onboarding.test.ts"),
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


@pytest.mark.parametrize(
    "selector",
    ("--test-name-pattern=onboarding", "--only", "--changed=HEAD", "--shard=1/2"),
)
def test_command_integrity_rejects_filtered_bun_test_run(
    tmp_path: Path, selector: str
) -> None:
    manifest_path = _write_bun_test_project(
        tmp_path,
        options=(selector, "tests/maid-onboarding.test.ts"),
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


@pytest.mark.parametrize(
    "option",
    ("--reporter-outfile", "--coverage-dir", "--path-ignore-patterns"),
)
def test_command_integrity_rejects_bun_option_value_test_path(
    tmp_path: Path, option: str
) -> None:
    manifest_path = _write_bun_test_project(
        tmp_path,
        options=(
            option,
            "tests/maid-onboarding.test.ts",
            "tests/unrelated.test.ts",
        ),
    )
    unrelated_test = tmp_path / "tests" / "unrelated.test.ts"
    unrelated_test.write_text("test('unrelated', () => {});\n", encoding="utf-8")

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_command_integrity_rejects_unknown_bun_test_option(tmp_path: Path) -> None:
    manifest_path = _write_bun_test_project(
        tmp_path,
        options=("--future-option", "tests/maid-onboarding.test.ts"),
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]
