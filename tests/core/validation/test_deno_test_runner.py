"""Behavioral contract for explicit Deno test commands."""

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


def _write_deno_test_project(
    root: Path,
    *,
    subcommand: str = "test",
    options: tuple[str, ...] = ("--no-check", "--allow-env"),
) -> Path:
    test_file = root / "supabase" / "functions" / "mcp" / "authenticate.test.ts"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "const it = Deno.test;\n" "it('rejects a missing bearer token', () => {});\n",
        encoding="utf-8",
    )

    manifest_dir = root / "manifests"
    manifest_dir.mkdir()
    manifest_path = manifest_dir / "deno-test.manifest.yaml"
    manifest_path.write_text(
        'schema: "2"\n'
        'goal: "Exercise an explicit Deno behavioral test"\n'
        "type: fix\n"
        'created: "2026-09-10T00:00:00Z"\n'
        "files:\n"
        "  create:\n"
        "    - path: supabase/functions/mcp/authenticate.test.ts\n"
        "      artifacts:\n"
        "        - kind: test_function\n"
        "          name: rejects a missing bearer token\n"
        "validate:\n"
        f"  - [deno, {subcommand}, {', '.join(options)}, "
        "supabase/functions/mcp/authenticate.test.ts]\n",
        encoding="utf-8",
    )
    return manifest_path


def test_command_integrity_accepts_explicit_deno_test_file(tmp_path: Path) -> None:
    manifest_path = _write_deno_test_project(tmp_path)

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert errors == []


def test_run_manifest_tests_executes_explicit_deno_test_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _write_deno_test_project(tmp_path)
    executable = tmp_path / "bin" / "deno"
    executable.parent.mkdir()
    executable.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > deno-args.txt\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{executable.parent}{os.pathsep}{os.environ['PATH']}")

    result = run_manifest_tests(manifest_path, project_root=tmp_path)

    assert (result.total, result.passed, result.failed) == (1, 1, 0)
    assert (tmp_path / "deno-args.txt").read_text(encoding="utf-8").splitlines() == [
        "test",
        "--no-check",
        "--allow-env",
        "supabase/functions/mcp/authenticate.test.ts",
    ]


def test_command_integrity_rejects_non_test_deno_subcommand(tmp_path: Path) -> None:
    manifest_path = _write_deno_test_project(tmp_path, subcommand="fmt")

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_command_integrity_rejects_non_executing_deno_test_mode(
    tmp_path: Path,
) -> None:
    manifest_path = _write_deno_test_project(tmp_path, options=("--help",))

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_command_integrity_rejects_filtered_deno_test_run(tmp_path: Path) -> None:
    manifest_path = _write_deno_test_project(
        tmp_path,
        options=("--filter", "missing bearer token"),
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_command_integrity_rejects_deno_no_run_mode(tmp_path: Path) -> None:
    manifest_path = _write_deno_test_project(tmp_path, options=("--no-run",))

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_command_integrity_ignores_deno_script_argument_test_paths(
    tmp_path: Path,
) -> None:
    manifest_path = _write_deno_test_project(
        tmp_path,
        options=(
            "unrelated.test.ts",
            "--",
            "supabase/functions/mcp/authenticate.test.ts",
        ),
    )
    (tmp_path / "unrelated.test.ts").write_text(
        "Deno.test('unrelated', () => {});\n",
        encoding="utf-8",
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_command_integrity_rejects_deno_option_value_test_path(
    tmp_path: Path,
) -> None:
    manifest_path = _write_deno_test_project(
        tmp_path,
        options=(
            "--junit-path",
            "supabase/functions/mcp/authenticate.test.ts",
            "unrelated.test.ts",
            "--",
        ),
    )
    (tmp_path / "unrelated.test.ts").write_text(
        "Deno.test('unrelated', () => {});\n",
        encoding="utf-8",
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]
