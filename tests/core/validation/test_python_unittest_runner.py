"""Behavioral contract for explicit Python unittest file commands."""

from __future__ import annotations

from pathlib import Path

import pytest

from maid_runner.core._validation_test_artifacts import (
    validate_manifest_test_commands,
)
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.test_runner import run_manifest_tests


def _write_unittest_project(
    root: Path,
    validate_command: str,
    *,
    test_path: str = "tests/test_registration_runbook.py",
) -> Path:
    test_file = root / test_path
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "from pathlib import Path\n"
        "import unittest\n\n"
        "class TestRunbookContract(unittest.TestCase):\n"
        "    def test_runbook(self):\n"
        "        Path('unittest-ran.txt').write_text('ran', encoding='utf-8')\n",
        encoding="utf-8",
    )

    manifest_dir = root / "manifests"
    manifest_dir.mkdir()
    manifest_path = manifest_dir / "unittest-file.manifest.yaml"
    manifest_path.write_text(
        'schema: "2"\n'
        'goal: "Exercise an explicit Python unittest file"\n'
        "type: fix\n"
        'created: "2026-09-10T00:00:00Z"\n'
        "files:\n"
        "  create:\n"
        f"    - path: {test_path}\n"
        "      artifacts:\n"
        "        - kind: test_function\n"
        "          name: test_runbook\n"
        "validate:\n"
        f"  - {validate_command}\n",
        encoding="utf-8",
    )
    return manifest_path


def test_command_integrity_accepts_uv_python_module_unittest_file(
    tmp_path: Path,
) -> None:
    manifest_path = _write_unittest_project(
        tmp_path,
        "uv run python -m unittest tests/test_registration_runbook.py",
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert errors == []


def test_run_manifest_tests_executes_python_module_unittest_file(
    tmp_path: Path,
) -> None:
    manifest_path = _write_unittest_project(
        tmp_path,
        "python -m unittest tests/test_registration_runbook.py",
    )

    result = run_manifest_tests(manifest_path, project_root=tmp_path)

    assert (result.total, result.passed, result.failed) == (1, 1, 0)
    assert (tmp_path / "unittest-ran.txt").read_text(encoding="utf-8") == "ran"


def test_command_integrity_ignores_pytest_addopts_for_unittest_file(
    tmp_path: Path,
) -> None:
    manifest_path = _write_unittest_project(
        tmp_path,
        (
            "env PYTEST_ADDOPTS=--collect-only "
            "python -m unittest tests/test_registration_runbook.py"
        ),
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert errors == []


def test_command_integrity_rejects_unittest_help_mode(tmp_path: Path) -> None:
    manifest_path = _write_unittest_project(
        tmp_path,
        "python -m unittest --help tests/test_registration_runbook.py",
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_command_integrity_rejects_unittest_discovery_mode(tmp_path: Path) -> None:
    manifest_path = _write_unittest_project(
        tmp_path,
        "python -m unittest discover -s tests",
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_command_integrity_rejects_unittest_dotted_selector(tmp_path: Path) -> None:
    manifest_path = _write_unittest_project(
        tmp_path,
        (
            "python -m unittest "
            "tests.test_registration_runbook.TestRunbookContract.test_runbook"
        ),
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_command_integrity_rejects_non_test_python_module(tmp_path: Path) -> None:
    manifest_path = _write_unittest_project(
        tmp_path,
        "python -m compileall tests/test_registration_runbook.py",
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


@pytest.mark.parametrize(
    "target",
    [
        "tests",
        ".",
        "tests/test_*.py",
        "tests/test_registration_runbook.py/",
        "tests/test_registration_runbook.py/.",
    ],
)
def test_command_integrity_rejects_unittest_non_file_target(
    tmp_path: Path,
    target: str,
) -> None:
    manifest_path = _write_unittest_project(
        tmp_path,
        f"python -m unittest {target}",
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_command_integrity_rejects_unittest_module_path_lookalike(
    tmp_path: Path,
) -> None:
    manifest_path = _write_unittest_project(
        tmp_path,
        "python -m tools/unittest tests/test_registration_runbook.py",
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_command_integrity_rejects_unittest_py_suffixed_directory(
    tmp_path: Path,
) -> None:
    manifest_path = _write_unittest_project(
        tmp_path,
        "python -m unittest tests.py",
        test_path="tests.py/test_registration_runbook.py",
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


@pytest.mark.parametrize(
    "target",
    [
        "/tests/test_registration_runbook.py",
        "../tests/test_registration_runbook.py",
    ],
)
def test_command_integrity_rejects_unittest_escaping_file_target(
    tmp_path: Path,
    target: str,
) -> None:
    manifest_path = _write_unittest_project(
        tmp_path,
        f"python -m unittest {target}",
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_command_integrity_rejects_unittest_shell_cwd_escape(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    manifest_path = _write_unittest_project(
        project_root,
        (
            "bash -lc 'cd .. && python -m unittest "
            "tests/test_registration_runbook.py'"
        ),
    )
    external_test = tmp_path / "tests" / "test_registration_runbook.py"
    external_test.parent.mkdir()
    external_test.write_text(
        "import unittest\n\n"
        "class TestExternal(unittest.TestCase):\n"
        "    def test_runbook(self):\n"
        "        pass\n",
        encoding="utf-8",
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), project_root)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_command_integrity_rejects_unittest_wrapper_cwd_parent_target(
    tmp_path: Path,
) -> None:
    (tmp_path / "sub").mkdir()
    manifest_path = _write_unittest_project(
        tmp_path,
        (
            "pnpm --dir sub exec python -m unittest "
            "../tests/test_registration_runbook.py"
        ),
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


@pytest.mark.parametrize(
    ("command", "test_path"),
    [
        (
            "bash -lc 'cd ~ && python -m unittest "
            "tests/test_registration_runbook.py'",
            "~/tests/test_registration_runbook.py",
        ),
        (
            "bash -lc 'cd -- && python -m unittest "
            "tests/test_registration_runbook.py'",
            "--/tests/test_registration_runbook.py",
        ),
        (
            'bash -lc \'cd "" && python -m unittest '
            "tests/test_registration_runbook.py'",
            "tests/test_registration_runbook.py",
        ),
        (
            "bash -lc 'python -m unittest tests/test_{other,decoy}.py'",
            "tests/test_{other,decoy}.py",
        ),
        (
            "bash -lc 'python -m unittest ~/test_registration_runbook.py'",
            "~/test_registration_runbook.py",
        ),
        (
            "bash -lc 'python -m unittest tests/test_`pwd`.py'",
            "tests/test_`pwd`.py",
        ),
    ],
)
def test_command_integrity_rejects_shell_wrapped_unittest(
    tmp_path: Path,
    command: str,
    test_path: str,
) -> None:
    manifest_path = _write_unittest_project(
        tmp_path,
        command,
        test_path=test_path,
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


@pytest.mark.parametrize(
    "command",
    [
        "poetry run python -m unittest tests/test_registration_runbook.py",
        "pdm run python -m unittest tests/test_registration_runbook.py",
        "pnpm exec python -m unittest tests/test_registration_runbook.py",
        "yarn exec python -m unittest tests/test_registration_runbook.py",
        "bunx python -m unittest tests/test_registration_runbook.py",
        "npm exec python -m unittest tests/test_registration_runbook.py",
        "dotenv -- python -m unittest tests/test_registration_runbook.py",
        "docker exec app python -m unittest tests/test_registration_runbook.py",
        "coverage run -m python -m unittest tests/test_registration_runbook.py",
        "/tmp/fake/uv run python -m unittest tests/test_registration_runbook.py",
        "./uv run python -m unittest tests/test_registration_runbook.py",
        (
            "/tmp/fake/env PYTEST_ADDOPTS=--collect-only python -m unittest "
            "tests/test_registration_runbook.py"
        ),
    ],
)
def test_command_integrity_rejects_non_uv_unittest_wrapper(
    tmp_path: Path,
    command: str,
) -> None:
    manifest_path = _write_unittest_project(
        tmp_path,
        command,
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


@pytest.mark.parametrize(
    "command",
    [
        "uv run uv run python -m unittest tests/test_registration_runbook.py",
        "uv run env python -m unittest tests/test_registration_runbook.py",
        (
            "env PYTEST_ADDOPTS=--collect-only uv run python -m unittest "
            "tests/test_registration_runbook.py"
        ),
        (
            "PYTEST_ADDOPTS=--collect-only uv run python -m unittest "
            "tests/test_registration_runbook.py"
        ),
        "env FOO=bar python -m unittest tests/test_registration_runbook.py",
        (
            "PYTEST_ADDOPTS=--collect-only python -m unittest "
            "tests/test_registration_runbook.py"
        ),
    ],
)
def test_command_integrity_rejects_nested_uv_unittest_wrapper(
    tmp_path: Path,
    command: str,
) -> None:
    manifest_path = _write_unittest_project(tmp_path, command)

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


@pytest.mark.parametrize(
    "command",
    [
        "uv run --module python -m unittest tests/test_registration_runbook.py",
        "uv run --module unittest tests/test_registration_runbook.py",
        "uv run -m unittest tests/test_registration_runbook.py",
        "uv run --module=unittest tests/test_registration_runbook.py",
        "uv run -munittest tests/test_registration_runbook.py",
    ],
)
def test_command_integrity_rejects_uv_module_unittest_lookalike(
    tmp_path: Path,
    command: str,
) -> None:
    manifest_path = _write_unittest_project(tmp_path, command)

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


@pytest.mark.parametrize(
    "command",
    [
        "scripts/python -m unittest tests/test_registration_runbook.py",
        "python3.wrapper -m unittest tests/test_registration_runbook.py",
        "python3.１２ -m unittest tests/test_registration_runbook.py",
        "python3.١٢ -m unittest tests/test_registration_runbook.py",
        "uv run scripts/python -m unittest tests/test_registration_runbook.py",
    ],
)
def test_command_integrity_rejects_python_interpreter_lookalike(
    tmp_path: Path,
    command: str,
) -> None:
    manifest_path = _write_unittest_project(tmp_path, command)

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_command_integrity_rejects_unittest_symlink_target(tmp_path: Path) -> None:
    manifest_path = _write_unittest_project(
        tmp_path,
        "python -m unittest tests/test_registration_runbook.py",
    )
    declared_test = tmp_path / "tests" / "test_registration_runbook.py"
    decoy_test = tmp_path / "tests" / "test_decoy.py"
    decoy_test.write_text(declared_test.read_text(encoding="utf-8"), encoding="utf-8")
    declared_test.unlink()
    declared_test.symlink_to(decoy_test.name)

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_command_integrity_rejects_unittest_symlink_ancestor(
    tmp_path: Path,
) -> None:
    manifest_path = _write_unittest_project(
        tmp_path,
        "python -m unittest alias/test_registration_runbook.py",
        test_path="alias/test_registration_runbook.py",
    )
    alias = tmp_path / "alias"
    real_tests = tmp_path / "real-tests"
    alias.rename(real_tests)
    alias.symlink_to(real_tests.name, target_is_directory=True)

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_non_unittest_runner_preserves_symlinked_cwd_identity(tmp_path: Path) -> None:
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    test_file = real_dir / "current.test.ts"
    test_file.write_text("test('current', () => {});\n", encoding="utf-8")
    (tmp_path / "alias").symlink_to(real_dir.name, target_is_directory=True)

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    manifest_path = manifest_dir / "symlink-cwd.manifest.yaml"
    manifest_path.write_text(
        'schema: "2"\n'
        'goal: "Preserve a lexical package cwd"\n'
        "type: fix\n"
        'created: "2026-09-10T00:00:00Z"\n'
        "files:\n"
        "  create:\n"
        "    - path: alias/current.test.ts\n"
        "      artifacts:\n"
        "        - kind: test_function\n"
        "          name: current\n"
        "validate:\n"
        "  - pnpm --dir alias exec vitest current.test.ts\n",
        encoding="utf-8",
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert errors == []
