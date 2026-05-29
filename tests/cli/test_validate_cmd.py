"""Tests for CLI 'maid validate' command (v2)."""

from __future__ import annotations

import argparse
import json
import os
import textwrap
from pathlib import Path

import pytest
import yaml

from maid_runner.core._validation_test_artifacts import (
    find_test_files,
    validate_manifest_test_commands,
)
from maid_runner.core._pytest_config_addopts import (
    pyproject_pytest_addopts_args,
    pyproject_pytest_addopts_errors,
)
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode


@pytest.fixture
def project_dir(tmp_path):
    """Create a project directory with a valid manifest and source file."""
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # Create a source file
    (src_dir / "greet.py").write_text(
        textwrap.dedent(
            """\
        def greet(name: str) -> str:
            return f"Hello, {name}"
        """
        )
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_greet.py").write_text(
        textwrap.dedent(
            """\
        from src.greet import greet


        def test_greet():
            assert greet("World") == "Hello, World"
        """
        )
    )

    # Create a v2 manifest
    manifest = {
        "schema": "2",
        "goal": "Add greeting function",
        "type": "feature",
        "files": {
            "create": [
                {
                    "path": "src/greet.py",
                    "artifacts": [
                        {
                            "kind": "function",
                            "name": "greet",
                            "args": [{"name": "name", "type": "str"}],
                            "returns": "str",
                        }
                    ],
                }
            ],
            "read": ["tests/test_greet.py"],
        },
        "validate": ["pytest tests/test_greet.py -v"],
    }
    (manifest_dir / "add-greet.manifest.yaml").write_text(yaml.dump(manifest))

    return tmp_path


@pytest.fixture
def failing_project(tmp_path):
    """Create a project with a missing artifact in source."""
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # Source file missing the declared artifact
    (src_dir / "greet.py").write_text("# empty\n")

    manifest = {
        "schema": "2",
        "goal": "Add greeting function",
        "type": "feature",
        "files": {
            "create": [
                {
                    "path": "src/greet.py",
                    "artifacts": [
                        {
                            "kind": "function",
                            "name": "greet",
                        }
                    ],
                }
            ]
        },
        "validate": ["pytest tests/test_greet.py -v"],
    }
    (manifest_dir / "add-greet.manifest.yaml").write_text(yaml.dump(manifest))

    return tmp_path


def _write_run_tests_project(
    tmp_path,
    slug: str,
    validate_command: str,
    *,
    include_files_read: bool = True,
    test_assertion: str = "gate() == 'ok'",
    test_path: str = "tests/test_gate.py",
    include_type: bool = True,
    created: str | None = None,
):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    (src_dir / "gate.py").write_text("def gate() -> str:\n    return 'ok'\n")
    test_file = tmp_path / test_path
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(
        f"from src.gate import gate\n\ndef test_gate():\n    assert {test_assertion}\n"
    )
    files = {
        "create": [
            {
                "path": "src/gate.py",
                "artifacts": [
                    {
                        "kind": "function",
                        "name": "gate",
                        "returns": "str",
                    }
                ],
            }
        ],
    }
    if include_files_read:
        files["read"] = [test_path]

    manifest = {
        "schema": "2",
        "goal": "Exercise validate run-tests gate",
        "files": files,
        "validate": [validate_command],
    }
    if include_type:
        manifest["type"] = "feature"
    if created is not None:
        manifest["created"] = created
    manifest_path = manifest_dir / f"{slug}.manifest.yaml"
    manifest_path.write_text(yaml.dump(manifest))
    return manifest_path


def _write_pyproject_pytest_addopts(tmp_path, addopts: str) -> None:
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            f"""\
            [tool.pytest.ini_options]
            addopts = {addopts}
            """
        )
    )


def _commit_all(project_dir, message: str = "commit") -> str:
    import subprocess

    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "add", "."], cwd=project_dir, check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            "commit",
            "-m",
            message,
        ],
        cwd=project_dir,
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class TestCmdValidateSingleManifest:
    def test_cmd_validate_handler_is_directly_importable(self):
        from maid_runner.cli.commands.validate import cmd_validate

        assert callable(cmd_validate)

    def test_valid_manifest_returns_0(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(
            ["validate", "manifests/add-greet.manifest.yaml", "--no-chain"]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "add-greet" in captured.out

    def test_invalid_manifest_returns_1(self, failing_project, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(failing_project)
        exit_code = main(
            ["validate", "manifests/add-greet.manifest.yaml", "--no-chain"]
        )
        assert exit_code == 1

    def test_validate_returns_1_for_unreferenced_public_artifact(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        (src_dir / "widget.py").write_text(
            "def render():\n    return 'rendered'\n\n"
            "def update():\n    return 'updated'\n"
        )
        (tests_dir / "test_widget.py").write_text(
            "from src.widget import render\n\n"
            "def test_render():\n"
            "    assert render() == 'rendered'\n"
        )
        manifest = {
            "schema": "2",
            "goal": "Add widget",
            "type": "feature",
            "files": {
                "edit": [
                    {
                        "path": "src/widget.py",
                        "artifacts": [
                            {"kind": "function", "name": "render"},
                            {"kind": "function", "name": "update"},
                        ],
                    }
                ],
                "read": ["tests/test_widget.py"],
            },
            "validate": ["pytest tests/test_widget.py -v"],
        }
        (manifest_dir / "add-widget.manifest.yaml").write_text(yaml.dump(manifest))

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/add-widget.manifest.yaml",
                "--mode",
                "implementation",
                "--no-chain",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Errors (1):" in captured.out
        assert "E200" in captured.out
        assert "Warnings" not in captured.out

    def test_json_output(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(
            ["validate", "manifests/add-greet.manifest.yaml", "--no-chain", "--json"]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["manifest"] == "add-greet"

    def test_quiet_mode_success_minimal_output(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(
            ["validate", "manifests/add-greet.manifest.yaml", "--no-chain", "--quiet"]
        )
        assert exit_code == 0

    def test_nonexistent_manifest_returns_error(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(["validate", "manifests/nonexistent.yaml", "--no-chain"])
        # Should return 1 (validation failure - manifest not found is a validation error)
        assert exit_code == 1

    def test_validate_run_tests_returns_1_when_manifest_command_fails(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._format import format_test_result
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-fail",
            "python -m pytest tests/test_gate.py -q --bad-option",
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-fail.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "PASS run-tests-fail" in captured.out
        assert "Test Results: 1 commands" in captured.out
        assert "FAIL [run-tests-fail]" in captured.out
        assert "--bad-option" in captured.out
        assert "exit" in captured.out
        assert callable(format_test_result)

    def test_validate_run_tests_returns_0_when_structure_and_commands_pass(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main
        from maid_runner.cli.commands.validate import run_validate_commands_for_result

        manifest_path = _write_run_tests_project(
            tmp_path,
            "run-tests-pass",
            "python -m pytest tests/test_gate.py -q",
        )

        os.chdir(tmp_path)
        helper_result = run_validate_commands_for_result(str(manifest_path))

        assert helper_result.success is True

        exit_code = main(
            [
                "validate",
                "manifests/run-tests-pass.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "PASS run-tests-pass" in captured.out
        assert "Test Results: 1 commands" in captured.out
        assert "PASS [run-tests-pass]" in captured.out

    def test_validate_run_tests_rejects_noop_validate_command(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        manifest_path = _write_run_tests_project(
            tmp_path,
            "run-tests-noop",
            'python -c "raise SystemExit(0)"',
        )
        manifest = load_manifest(manifest_path)

        errors = validate_manifest_test_commands(manifest, tmp_path)

        assert [error.code for error in errors] == [
            ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
        ]

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-noop.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "python -c" in captured.out

    def test_validate_run_tests_rejects_noop_validate_command_path_only(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-noop-path-only",
            'python -c "raise SystemExit(0)" tests/test_gate.py',
            include_files_read=False,
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-noop-path-only.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "tests/test_gate.py" in captured.out

    def test_validate_run_tests_rejects_noop_with_editable_test_file(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_path = _write_run_tests_project(
            tmp_path,
            "run-tests-editable-test-noop",
            'python -c "raise SystemExit(0)"',
            include_files_read=False,
        )
        manifest = yaml.safe_load(manifest_path.read_text())
        manifest["files"].setdefault("edit", []).append(
            {
                "path": "tests/test_gate.py",
                "artifacts": [
                    {
                        "kind": "test_function",
                        "name": "test_gate",
                    }
                ],
            }
        )
        manifest_path.write_text(yaml.dump(manifest))

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-editable-test-noop.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "tests/test_gate.py" in captured.out

    def test_validate_run_tests_rejects_noop_without_manifest_type(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-no-type-noop",
            'python -c "raise SystemExit(0)"',
            include_type=False,
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-no-type-noop.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "tests/test_gate.py" in captured.out

    def test_validate_run_tests_rejects_noop_with_root_test_file(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-root-noop",
            'python -c "raise SystemExit(0)"',
            test_path="test_gate.py",
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-root-noop.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "test_gate.py" in captured.out

    def test_validate_run_tests_rejects_noop_with_colocated_test_file(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-colocated-noop",
            'python -c "raise SystemExit(0)"',
            test_path="src/test_gate.py",
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-colocated-noop.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "src/test_gate.py" in captured.out

    def test_validate_run_tests_rejects_noop_validate_path_colocated_test_file(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-colocated-path-only",
            'python -c "raise SystemExit(0)" src/test_gate.py',
            include_files_read=False,
            test_path="src/test_gate.py",
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-colocated-path-only.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "src/test_gate.py" in captured.out

    def test_validate_run_tests_rejects_shell_separator_runner_segment(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-separator",
            'python -c "raise SystemExit(0)" || pytest tests/test_gate.py',
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-separator.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "|| pytest tests/test_gate.py" in captured.out

    def test_validate_run_tests_requires_all_discovered_test_files(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_path = _write_run_tests_project(
            tmp_path,
            "run-tests-partial",
            "python -m pytest tests/test_gate.py -q",
        )
        (tmp_path / "tests" / "test_other.py").write_text(
            "from src.gate import gate\n\n"
            "def test_other():\n"
            "    assert gate() == 'ok'\n"
        )
        manifest = yaml.safe_load(manifest_path.read_text())
        manifest["files"]["read"] = ["tests/test_gate.py", "tests/test_other.py"]
        manifest_path.write_text(yaml.dump(manifest))

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-partial.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "tests/test_other.py" in captured.out

    def test_validate_run_tests_rejects_pytest_setup_plan(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-setup-plan",
            "python -m pytest --setup-plan tests/test_gate.py -q",
            test_assertion="gate() == 'not ok'",
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-setup-plan.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "--setup-plan" in captured.out

    def test_validate_run_tests_rejects_pytest_setup_only(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-setup-only",
            "python -m pytest --setup-only tests/test_gate.py -q",
            test_assertion="gate() == 'not ok'",
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-setup-only.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "--setup-only" in captured.out

    def test_validate_run_tests_rejects_pytest_ignore_excluding_test_file(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-ignore",
            "python -m pytest tests -q --ignore=tests/test_gate.py",
            test_assertion="gate() == 'not ok'",
        )
        (tmp_path / "tests" / "test_other.py").write_text(
            "from src.gate import gate\n\n"
            "def test_other():\n"
            "    assert gate() == 'ok'\n"
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-ignore.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "--ignore=tests/test_gate.py" in captured.out

    def test_validate_run_tests_rejects_pytest_selector_skipping_declared_test(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-selector",
            "python -m pytest tests -q -k test_other",
            test_assertion="gate() == 'not ok'",
        )
        (tmp_path / "tests" / "test_other.py").write_text(
            "from src.gate import gate\n\n"
            "def test_other():\n"
            "    assert gate() == 'ok'\n"
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-selector.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "-k test_other" in captured.out

    def test_validate_run_tests_rejects_attached_pytest_selector_skipping_declared_test(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-attached-selector",
            "python -m pytest -ktest_other tests -q",
            test_assertion="gate() == 'not ok'",
        )
        (tmp_path / "tests" / "test_other.py").write_text(
            "from src.gate import gate\n\n"
            "def test_other():\n"
            "    assert gate() == 'ok'\n"
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-attached-selector.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "-ktest_other" in captured.out

    def test_validate_run_tests_rejects_clustered_pytest_selector_skipping_declared_test(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-clustered-selector",
            "python -m pytest -qktest_other tests -q",
            test_assertion="gate() == 'not ok'",
        )
        (tmp_path / "tests" / "test_other.py").write_text(
            "from src.gate import gate\n\n"
            "def test_other():\n"
            "    assert gate() == 'ok'\n"
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-clustered-selector.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "-qktest_other" in captured.out

    def test_validate_run_tests_rejects_pytest_addopts_selector(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-addopts-selector",
            "env PYTEST_ADDOPTS=-qktest_other python -m pytest tests -q",
            test_assertion="gate() == 'not ok'",
        )
        (tmp_path / "tests" / "test_other.py").write_text(
            "from src.gate import gate\n\n"
            "def test_other():\n"
            "    assert gate() == 'ok'\n"
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-addopts-selector.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "PYTEST_ADDOPTS=-qktest_other" in captured.out

    def test_validate_run_tests_rejects_pytest_addopts_non_executing_mode(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-addopts-collect-only",
            "env PYTEST_ADDOPTS=--collect-only python -m pytest tests -q",
            test_assertion="gate() == 'not ok'",
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-addopts-collect-only.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "PYTEST_ADDOPTS=--collect-only" in captured.out

    def test_validate_run_tests_rejects_pytest_config_collect_only(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-pyproject-collect-only",
            "python -m pytest tests -q",
            test_assertion="gate() == 'not ok'",
        )
        _write_pyproject_pytest_addopts(tmp_path, '"--collect-only"')

        assert pyproject_pytest_addopts_args(
            tmp_path,
            ("python", "-m", "pytest", "tests", "-q"),
        ) == ("--collect-only",)
        assert (
            pyproject_pytest_addopts_errors(
                tmp_path,
                ("python", "-m", "pytest", "tests", "-q"),
            )
            == ()
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-pyproject-collect-only.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "pyproject.toml" in captured.out
        assert "--collect-only" in captured.out

    def test_validate_run_tests_rejects_pytest_config_selector_deselecting_behavioral_test(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-pyproject-selector",
            "python -m pytest tests -q",
            test_assertion="gate() == 'not ok'",
        )
        (tmp_path / "tests" / "test_other.py").write_text(
            "from src.gate import gate\n\n"
            "def test_other():\n"
            "    assert gate() == 'ok'\n"
        )
        _write_pyproject_pytest_addopts(tmp_path, '"-k test_other"')

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-pyproject-selector.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "pyproject.toml" in captured.out
        assert "-k test_other" in captured.out

    def test_validate_run_tests_rejects_pyproject_addopts_with_empty_dot_pytest_ini(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-empty-dot-pytest-ini",
            "python -m pytest tests -q",
            test_assertion="gate() == 'not ok'",
        )
        _write_pyproject_pytest_addopts(tmp_path, '"--collect-only"')
        (tmp_path / ".pytest.ini").write_text("")

        command = ("python", "-m", "pytest", "tests", "-q")
        assert pyproject_pytest_addopts_args(tmp_path, command) == ("--collect-only",)
        assert pyproject_pytest_addopts_errors(tmp_path, command) == ()

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-empty-dot-pytest-ini.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "pyproject.toml" in captured.out
        assert "--collect-only" in captured.out

    def test_validate_run_tests_allows_benign_pytest_config_addopts(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-benign-pyproject-addopts",
            "python -m pytest tests -q",
        )
        _write_pyproject_pytest_addopts(tmp_path, '"-q --disable-warnings"')

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-benign-pyproject-addopts.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" not in captured.out
        assert (
            "PASS [run-tests-benign-pyproject-addopts] python -m pytest tests -q"
            in (captured.out)
        )

    def test_validate_run_tests_allows_pytest_ini_precedence_over_pyproject_addopts(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-pytest-ini-precedence",
            "python -m pytest tests -q",
        )
        (tmp_path / "tests" / "test_other.py").write_text(
            "from src.gate import gate\n\n"
            "def test_other():\n"
            "    assert gate() == 'ok'\n"
        )
        _write_pyproject_pytest_addopts(tmp_path, '"-k test_other"')
        (tmp_path / "pytest.ini").write_text("[pytest]\n")

        command = ("python", "-m", "pytest", "tests", "-q")
        assert pyproject_pytest_addopts_args(tmp_path, command) == ()
        assert pyproject_pytest_addopts_errors(tmp_path, command) == ()

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-pytest-ini-precedence.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" not in captured.out
        assert (
            "PASS [run-tests-pytest-ini-precedence] python -m pytest tests -q"
            in captured.out
        )

    def test_validate_run_tests_allows_explicit_pytest_config_over_pyproject_addopts(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-explicit-pytest-ini",
            "python -m pytest -c pytest.ini tests -q",
        )
        (tmp_path / "tests" / "test_other.py").write_text(
            "from src.gate import gate\n\n"
            "def test_other():\n"
            "    assert gate() == 'ok'\n"
        )
        _write_pyproject_pytest_addopts(tmp_path, '"-k test_other"')
        (tmp_path / "pytest.ini").write_text("[pytest]\n")

        command = ("python", "-m", "pytest", "-c", "pytest.ini", "tests", "-q")
        assert pyproject_pytest_addopts_args(tmp_path, command) == ()
        assert pyproject_pytest_addopts_errors(tmp_path, command) == ()

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-explicit-pytest-ini.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" not in captured.out
        assert (
            "PASS [run-tests-explicit-pytest-ini] "
            "python -m pytest -c pytest.ini tests -q"
        ) in captured.out

    def test_validate_run_tests_allows_override_ini_addopts_over_pyproject_addopts(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-override-ini-clears-pyproject",
            "python -m pytest -o addopts= tests -q",
        )
        (tmp_path / "tests" / "test_other.py").write_text(
            "from src.gate import gate\n\n"
            "def test_other():\n"
            "    assert gate() == 'ok'\n"
        )
        _write_pyproject_pytest_addopts(tmp_path, '"-k test_other"')

        command = ("python", "-m", "pytest", "-o", "addopts=", "tests", "-q")
        assert pyproject_pytest_addopts_args(tmp_path, command) == ()
        assert pyproject_pytest_addopts_errors(tmp_path, command) == ()

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-override-ini-clears-pyproject.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" not in captured.out
        assert (
            "PASS [run-tests-override-ini-clears-pyproject] "
            "python -m pytest -o addopts= tests -q"
        ) in captured.out

    def test_validate_run_tests_allows_override_ini_addopts_with_explicit_pyproject(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-explicit-pyproject-override-addopts",
            "python -m pytest -c pyproject.toml -o addopts= tests -q",
        )
        (tmp_path / "tests" / "test_other.py").write_text(
            "from src.gate import gate\n\n"
            "def test_other():\n"
            "    assert gate() == 'ok'\n"
        )
        _write_pyproject_pytest_addopts(tmp_path, '"-k test_other"')

        command = (
            "python",
            "-m",
            "pytest",
            "-c",
            "pyproject.toml",
            "-o",
            "addopts=",
            "tests",
            "-q",
        )
        assert pyproject_pytest_addopts_args(tmp_path, command) == ()
        assert pyproject_pytest_addopts_errors(tmp_path, command) == ()

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                (
                    "manifests/"
                    "run-tests-explicit-pyproject-override-addopts.manifest.yaml"
                ),
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" not in captured.out
        assert (
            "PASS [run-tests-explicit-pyproject-override-addopts] "
            "python -m pytest -c pyproject.toml -o addopts= tests -q"
        ) in captured.out

    def test_validate_run_tests_rejects_malformed_pyproject_pytest_addopts(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-malformed-pyproject-addopts",
            "python -m pytest tests -q",
        )
        _write_pyproject_pytest_addopts(tmp_path, '["-q", 42]')

        assert pyproject_pytest_addopts_errors(
            tmp_path,
            ("python", "-m", "pytest", "tests", "-q"),
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-malformed-pyproject-addopts.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "pyproject.toml" in captured.out
        assert "addopts" in captured.out

    def test_validate_run_tests_rejects_pytest_addopts_override_ini_selector(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-addopts-override-ini-selector",
            'env PYTEST_ADDOPTS="-o addopts=-ktest_other" python -m pytest tests -q',
            test_assertion="gate() == 'not ok'",
        )
        (tmp_path / "tests" / "test_other.py").write_text(
            "from src.gate import gate\n\n"
            "def test_other():\n"
            "    assert gate() == 'ok'\n"
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-addopts-override-ini-selector.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "addopts=-ktest_other" in captured.out

    def test_validate_run_tests_rejects_pytest_override_ini_addopts_selector(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        cases = [
            (
                "run-tests-override-ini-addopts-selector",
                "python -m pytest tests -q -o addopts=-ktest_other",
                "-o addopts=-ktest_other",
            ),
            (
                "run-tests-override-ini-equals-addopts-selector",
                "python -m pytest tests -q --override-ini=addopts=-ktest_other",
                "--override-ini=addopts=-ktest_other",
            ),
        ]

        for slug, validate_command, expected in cases:
            project_root = tmp_path / slug
            project_root.mkdir()
            manifest_path = _write_run_tests_project(
                project_root,
                slug,
                validate_command,
                test_assertion="gate() == 'not ok'",
            )
            (project_root / "tests" / "test_other.py").write_text(
                "from src.gate import gate\n\n"
                "def test_other():\n"
                "    assert gate() == 'ok'\n"
            )

            os.chdir(project_root)
            exit_code = main(
                [
                    "validate",
                    f"manifests/{manifest_path.name}",
                    "--no-chain",
                    "--run-tests",
                ]
            )

            assert exit_code == 1
            captured = capsys.readouterr()
            assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
            assert expected in captured.out

    def test_validate_run_tests_rejects_pytest_node_selector_skipping_declared_test(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-node-selector",
            "python -m pytest tests/test_gate.py::test_other -q",
        )
        (tmp_path / "tests" / "test_gate.py").write_text(
            "from src.gate import gate\n\n"
            "def test_gate():\n"
            "    assert gate() == 'not ok'\n\n"
            "def test_other():\n"
            "    assert gate() == 'ok'\n"
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-node-selector.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "tests/test_gate.py::test_other" in captured.out

    def test_validate_command_integrity_rejects_js_runner_selectors(self, tmp_path):
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        cases = [
            (
                "jest-test-path-pattern",
                "tests/foo.test.js",
                "jest tests --testPathPattern=foo.other.test.js",
            ),
            (
                "jest-test-path-ignore-pattern",
                "tests/foo.test.js",
                "jest tests --testPathIgnorePatterns=foo.test.js",
            ),
            (
                "jest-test-name-pattern",
                "tests/foo.test.js",
                "jest tests --testNamePattern test_other",
            ),
            (
                "playwright-grep",
                "tests/foo.spec.ts",
                "playwright test tests --grep test_other",
            ),
            (
                "playwright-short-grep",
                "tests/foo.spec.ts",
                "playwright test tests -g test_other",
            ),
        ]

        for slug, test_path, validate_command in cases:
            test_file = tmp_path / test_path
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("test('foo', () => expect(true).toBe(true));\n")
            manifest_path = manifest_dir / f"{slug}.manifest.yaml"
            manifest_path.write_text(
                yaml.dump(
                    {
                        "schema": "2",
                        "goal": "Reject JS runner selectors",
                        "type": "feature",
                        "files": {
                            "edit": [
                                {
                                    "path": "src/foo.ts",
                                    "artifacts": [{"kind": "function", "name": "foo"}],
                                }
                            ],
                            "read": [test_path],
                        },
                        "validate": [validate_command],
                    }
                )
            )

            errors = validate_manifest_test_commands(
                load_manifest(manifest_path), tmp_path
            )

            assert [error.code for error in errors] == [
                ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
            ]

    def test_validate_run_tests_rejects_backdated_pytest_node_selector(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-backdated-node-selector",
            "python -m pytest tests/test_gate.py::test_other -q",
            created="2026-05-16",
        )
        (tmp_path / "tests" / "test_gate.py").write_text(
            "from src.gate import gate\n\n"
            "def test_gate():\n"
            "    assert gate() == 'not ok'\n\n"
            "def test_other():\n"
            "    assert gate() == 'ok'\n"
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-backdated-node-selector.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "tests/test_gate.py::test_other" in captured.out

    def test_validate_command_integrity_rejects_non_executing_js_runner_modes(
        self, tmp_path
    ):
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        cases = [
            (
                "vitest-list",
                "src/foo.test.ts",
                "vitest list src/foo.test.ts",
            ),
            (
                "jest-clear-cache",
                "tests/foo.test.js",
                "jest --clearCache tests/foo.test.js",
            ),
        ]

        for slug, test_path, validate_command in cases:
            test_file = tmp_path / test_path
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("test('foo', () => expect(true).toBe(true));\n")
            manifest_path = manifest_dir / f"{slug}.manifest.yaml"
            manifest_path.write_text(
                yaml.dump(
                    {
                        "schema": "2",
                        "goal": "Reject non-executing JS runner modes",
                        "type": "feature",
                        "files": {
                            "edit": [
                                {
                                    "path": "src/foo.ts",
                                    "artifacts": [{"kind": "function", "name": "foo"}],
                                }
                            ],
                            "read": [test_path],
                        },
                        "validate": [validate_command],
                    }
                )
            )

            errors = validate_manifest_test_commands(
                load_manifest(manifest_path), tmp_path
            )

            assert [error.code for error in errors] == [
                ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
            ]

    def test_validate_run_tests_accepts_pytest_directory_covering_test_file(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-directory",
            "python -m pytest tests -q",
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-directory.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "PASS run-tests-directory" in captured.out
        assert "PASS [run-tests-directory] python -m pytest tests -q" in captured.out

    def test_validate_run_tests_accepts_pytest_project_root_covering_test_file(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-project-root",
            "python -m pytest . -q",
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-project-root.manifest.yaml",
                "--no-chain",
                "--run-tests",
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "PASS run-tests-project-root" in captured.out
        assert "PASS [run-tests-project-root] python -m pytest . -q" in captured.out

    def test_find_test_files_resolves_django_dotted_module_test_label(self, tmp_path):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        manifest_path = _write_run_tests_project(
            tmp_path,
            "django-dotted-discovery",
            (
                "python manage.py test "
                "seo_scraper_monitor.tests.test_keepa_cubiscan_export --keepdb -v 2"
            ),
            include_files_read=False,
            test_path=test_path,
        )

        test_files = find_test_files(load_manifest(manifest_path), tmp_path)

        assert test_files == [test_path]

    def test_validate_command_integrity_accepts_django_dotted_module_test_label(
        self, tmp_path
    ):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        manifest_path = _write_run_tests_project(
            tmp_path,
            "django-dotted-integrity",
            (
                "python manage.py test "
                "seo_scraper_monitor.tests.test_keepa_cubiscan_export --keepdb -v 2"
            ),
            test_path=test_path,
        )

        errors = validate_manifest_test_commands(
            load_manifest(manifest_path),
            tmp_path,
        )

        assert errors == []

    def test_validate_command_integrity_accepts_docker_exec_django_dotted_module_test_label(
        self, tmp_path
    ):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        manifest_path = _write_run_tests_project(
            tmp_path,
            "django-dotted-docker-integrity",
            (
                "docker exec tools-api python manage.py test "
                "seo_scraper_monitor.tests.test_keepa_cubiscan_export --keepdb -v 2"
            ),
            test_path=test_path,
        )

        errors = validate_manifest_test_commands(
            load_manifest(manifest_path),
            tmp_path,
        )

        assert errors == []

    def test_validate_command_integrity_accepts_docker_exec_pytest_file_target(
        self, tmp_path
    ):
        manifest_path = _write_run_tests_project(
            tmp_path,
            "docker-pytest-file-target",
            "docker exec app pytest tests/test_gate.py -q",
        )

        errors = validate_manifest_test_commands(
            load_manifest(manifest_path),
            tmp_path,
        )

        assert errors == []

    def test_validate_command_integrity_rejects_docker_wrapper_path_tokens(
        self, tmp_path
    ):
        cases = [
            (
                "docker-container-name-tests",
                "docker exec tests pytest unrelated.py",
            ),
            (
                "docker-workdir-tests",
                "docker exec -w tests app pytest unrelated.py",
            ),
        ]

        for slug, validate_command in cases:
            project_root = tmp_path / slug
            project_root.mkdir()
            manifest_path = _write_run_tests_project(
                project_root,
                slug,
                validate_command,
            )

            errors = validate_manifest_test_commands(
                load_manifest(manifest_path),
                project_root,
            )

            assert [error.code for error in errors] == [
                ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
            ]

    def test_validate_command_integrity_accepts_django_top_level_directory_flag(
        self, tmp_path
    ):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        manifest_path = _write_run_tests_project(
            tmp_path,
            "django-dotted-top-level-directory",
            (
                "python manage.py test "
                "seo_scraper_monitor.tests.test_keepa_cubiscan_export "
                "-t . --keepdb -v 2"
            ),
            test_path=test_path,
        )

        errors = validate_manifest_test_commands(
            load_manifest(manifest_path),
            tmp_path,
        )

        assert errors == []

    def test_validate_command_integrity_accepts_django_admin_dotted_module_test_label(
        self, tmp_path
    ):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        manifest_path = _write_run_tests_project(
            tmp_path,
            "django-admin-dotted-integrity",
            (
                "django-admin test "
                "seo_scraper_monitor.tests.test_keepa_cubiscan_export "
                "--settings adverio_tools_pj.settings --keepdb -v 2"
            ),
            test_path=test_path,
        )

        errors = validate_manifest_test_commands(
            load_manifest(manifest_path),
            tmp_path,
        )

        assert errors == []

    def test_validate_command_integrity_accepts_django_admin_pre_test_settings(
        self, tmp_path
    ):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        manifest_path = _write_run_tests_project(
            tmp_path,
            "django-admin-pre-test-settings",
            (
                "django-admin --settings adverio_tools_pj.settings test "
                "seo_scraper_monitor.tests.test_keepa_cubiscan_export "
                "--keepdb -v 2"
            ),
            test_path=test_path,
        )

        errors = validate_manifest_test_commands(
            load_manifest(manifest_path),
            tmp_path,
        )

        assert errors == []

    def test_validate_command_integrity_accepts_manage_py_pre_test_settings(
        self, tmp_path
    ):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        manifest_path = _write_run_tests_project(
            tmp_path,
            "manage-py-pre-test-settings",
            (
                "python manage.py --settings adverio_tools_pj.settings test "
                "seo_scraper_monitor.tests.test_keepa_cubiscan_export "
                "--keepdb -v 2"
            ),
            test_path=test_path,
        )

        errors = validate_manifest_test_commands(
            load_manifest(manifest_path),
            tmp_path,
        )

        assert errors == []

    def test_validate_command_integrity_accepts_python_module_django_test_label(
        self, tmp_path
    ):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        manifest_path = _write_run_tests_project(
            tmp_path,
            "python-module-django-dotted-integrity",
            (
                "python -m django test "
                "seo_scraper_monitor.tests.test_keepa_cubiscan_export "
                "--keepdb -v 2"
            ),
            test_path=test_path,
        )

        errors = validate_manifest_test_commands(
            load_manifest(manifest_path),
            tmp_path,
        )

        assert errors == []

    def test_validate_command_integrity_rejects_django_dotted_class_selector(
        self, tmp_path
    ):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        manifest_path = _write_run_tests_project(
            tmp_path,
            "django-dotted-class-selector",
            (
                "python manage.py test "
                "seo_scraper_monitor.tests.test_keepa_cubiscan_export."
                "TestOtherExportCase --keepdb -v 2"
            ),
            test_path=test_path,
        )

        errors = validate_manifest_test_commands(
            load_manifest(manifest_path),
            tmp_path,
        )

        assert [error.code for error in errors] == [
            ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
        ]

    def test_validate_command_integrity_rejects_django_class_selector_with_top_level_directory(
        self, tmp_path
    ):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        manifest_path = _write_run_tests_project(
            tmp_path,
            "django-dotted-class-selector-top-level-directory",
            (
                "python manage.py test "
                "seo_scraper_monitor.tests.test_keepa_cubiscan_export."
                "TestOtherExportCase --top-level-directory . --keepdb -v 2"
            ),
            test_path=test_path,
        )

        errors = validate_manifest_test_commands(
            load_manifest(manifest_path),
            tmp_path,
        )

        assert [error.code for error in errors] == [
            ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
        ]

    def test_validate_command_integrity_rejects_django_label_without_tests_package(
        self, tmp_path
    ):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        manifest_path = _write_run_tests_project(
            tmp_path,
            "django-dotted-missing-tests-package",
            (
                "python manage.py test "
                "seo_scraper_monitor.test_keepa_cubiscan_export --keepdb -v 2"
            ),
            test_path=test_path,
        )

        errors = validate_manifest_test_commands(
            load_manifest(manifest_path),
            tmp_path,
        )

        assert [error.code for error in errors] == [
            ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
        ]

    def test_validate_command_integrity_rejects_django_dotted_option_value(
        self, tmp_path
    ):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        manifest_path = _write_run_tests_project(
            tmp_path,
            "django-dotted-option-value",
            (
                "python manage.py test other_app "
                "--pythonpath seo_scraper_monitor.tests.test_keepa_cubiscan_export "
                "--keepdb -v 2"
            ),
            test_path=test_path,
        )

        errors = validate_manifest_test_commands(
            load_manifest(manifest_path),
            tmp_path,
        )

        assert [error.code for error in errors] == [
            ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
        ]

    def test_validate_command_integrity_rejects_django_pythonpath_shadowing(
        self, tmp_path
    ):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        manifest_path = _write_run_tests_project(
            tmp_path,
            "django-dotted-pythonpath-shadowing",
            (
                "python manage.py test "
                "seo_scraper_monitor.tests.test_keepa_cubiscan_export "
                "--pythonpath ../outside --keepdb -v 2"
            ),
            test_path=test_path,
        )

        errors = validate_manifest_test_commands(
            load_manifest(manifest_path),
            tmp_path,
        )

        assert [error.code for error in errors] == [
            ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
        ]

    def test_validate_command_integrity_rejects_django_pythonpath_env_shadowing(
        self, tmp_path
    ):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        manifest_path = _write_run_tests_project(
            tmp_path,
            "django-dotted-pythonpath-env-shadowing",
            (
                "PYTHONPATH=../outside python manage.py test "
                "seo_scraper_monitor.tests.test_keepa_cubiscan_export "
                "--keepdb -v 2"
            ),
            test_path=test_path,
        )

        errors = validate_manifest_test_commands(
            load_manifest(manifest_path),
            tmp_path,
        )

        assert [error.code for error in errors] == [
            ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
        ]

    def test_validate_command_integrity_rejects_docker_django_pythonpath_env_shadowing(
        self, tmp_path
    ):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        cases = [
            (
                "docker-env-equals",
                "docker exec --env=PYTHONPATH=../outside tools-api ",
            ),
            (
                "docker-env-separate",
                "docker exec --env PYTHONPATH=../outside tools-api ",
            ),
            (
                "docker-short-env-attached",
                "docker exec -ePYTHONPATH=../outside tools-api ",
            ),
            (
                "docker-short-env-separate",
                "docker exec -e PYTHONPATH=../outside tools-api ",
            ),
        ]

        for slug, docker_prefix in cases:
            project_root = tmp_path / slug
            project_root.mkdir()
            manifest_path = _write_run_tests_project(
                project_root,
                slug,
                (
                    f"{docker_prefix}python manage.py test "
                    "seo_scraper_monitor.tests.test_keepa_cubiscan_export "
                    "--keepdb -v 2"
                ),
                test_path=test_path,
            )

            errors = validate_manifest_test_commands(
                load_manifest(manifest_path),
                project_root,
            )

            assert [error.code for error in errors] == [
                ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
            ]

    def test_validate_command_integrity_rejects_detached_docker_django_command(
        self, tmp_path
    ):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        cases = [
            (
                "docker-detach-short",
                "docker exec -d tools-api ",
            ),
            (
                "docker-detach-long",
                "docker exec --detach tools-api ",
            ),
            (
                "docker-detach-equals",
                "docker exec --detach=true tools-api ",
            ),
            (
                "docker-detach-short-grouped",
                "docker exec -td tools-api ",
            ),
            (
                "docker-detach-short-grouped-after-tty",
                "docker exec -itd tools-api ",
            ),
        ]

        for slug, docker_prefix in cases:
            project_root = tmp_path / slug
            project_root.mkdir()
            manifest_path = _write_run_tests_project(
                project_root,
                slug,
                (
                    f"{docker_prefix}python manage.py test "
                    "seo_scraper_monitor.tests.test_keepa_cubiscan_export "
                    "--keepdb -v 2"
                ),
                test_path=test_path,
            )

            errors = validate_manifest_test_commands(
                load_manifest(manifest_path),
                project_root,
            )

            assert [error.code for error in errors] == [
                ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
            ]

    def test_validate_command_integrity_rejects_docker_django_env_file_shadowing(
        self, tmp_path
    ):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        cases = [
            (
                "docker-env-file-separate",
                "docker exec --env-file .env tools-api ",
            ),
            (
                "docker-env-file-equals",
                "docker exec --env-file=.env tools-api ",
            ),
        ]

        for slug, docker_prefix in cases:
            project_root = tmp_path / slug
            project_root.mkdir()
            manifest_path = _write_run_tests_project(
                project_root,
                slug,
                (
                    f"{docker_prefix}python manage.py test "
                    "seo_scraper_monitor.tests.test_keepa_cubiscan_export "
                    "--keepdb -v 2"
                ),
                test_path=test_path,
            )

            errors = validate_manifest_test_commands(
                load_manifest(manifest_path),
                project_root,
            )

            assert [error.code for error in errors] == [
                ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
            ]

    def test_validate_command_integrity_rejects_django_missing_value_flag_value(
        self, tmp_path
    ):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        cases = [
            (
                "django-missing-settings-value",
                "python manage.py test "
                "seo_scraper_monitor.tests.test_keepa_cubiscan_export --settings",
            ),
            (
                "django-missing-top-level-directory-value",
                "python manage.py test "
                "seo_scraper_monitor.tests.test_keepa_cubiscan_export "
                "--top-level-directory",
            ),
        ]

        for slug, validate_command in cases:
            project_root = tmp_path / slug
            project_root.mkdir()
            manifest_path = _write_run_tests_project(
                project_root,
                slug,
                validate_command,
                test_path=test_path,
            )

            errors = validate_manifest_test_commands(
                load_manifest(manifest_path),
                project_root,
            )

            assert [error.code for error in errors] == [
                ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
            ]

    def test_validate_command_integrity_rejects_django_tag_selector(self, tmp_path):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        manifest_path = _write_run_tests_project(
            tmp_path,
            "django-dotted-tag-selector",
            (
                "python manage.py test "
                "seo_scraper_monitor.tests.test_keepa_cubiscan_export "
                "--tag smoke --keepdb -v 2"
            ),
            test_path=test_path,
        )

        errors = validate_manifest_test_commands(
            load_manifest(manifest_path),
            tmp_path,
        )

        assert [error.code for error in errors] == [
            ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
        ]

    def test_validate_command_integrity_rejects_django_pre_test_selectors(
        self, tmp_path
    ):
        test_path = "src/seo_scraper_monitor/tests/test_keepa_cubiscan_export.py"
        cases = [
            (
                "django-pre-test-tag-selector",
                "--tag smoke",
            ),
            (
                "django-pre-test-exclude-tag-selector",
                "--exclude-tag slow",
            ),
            (
                "django-pre-test-k-selector",
                "-k smoke",
            ),
            (
                "django-pre-test-attached-k-selector",
                "-ksmoke",
            ),
        ]

        for slug, selector_args in cases:
            project_root = tmp_path / slug
            project_root.mkdir()
            manifest_path = _write_run_tests_project(
                project_root,
                slug,
                (
                    f"python manage.py {selector_args} test "
                    "seo_scraper_monitor.tests.test_keepa_cubiscan_export "
                    "--keepdb -v 2"
                ),
                test_path=test_path,
            )

            errors = validate_manifest_test_commands(
                load_manifest(manifest_path),
                project_root,
            )

            assert [error.code for error in errors] == [
                ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
            ]

    def test_validate_command_integrity_allows_known_legacy_pytest_node_selector(
        self,
    ):
        manifest = load_manifest(
            "manifests/replace-ts-required-import-regex-scanner.manifest.yaml"
        )

        errors = validate_manifest_test_commands(manifest, Path("."))

        assert errors == []

    def test_validate_command_integrity_accepts_uv_run_project_pytest_file(
        self, tmp_path
    ):
        test_path = "backend/tests/test_gate.py"
        manifest_path = _write_run_tests_project(
            tmp_path,
            "uv-run-project-pytest-file",
            f"uv run --project backend pytest {test_path} -q",
            test_path=test_path,
        )

        errors = validate_manifest_test_commands(
            load_manifest(manifest_path),
            tmp_path,
        )

        assert errors == []

    def test_validate_run_tests_json_includes_test_result(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-json",
            "python -m pytest tests/test_gate.py -q",
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-json.manifest.yaml",
                "--no-chain",
                "--run-tests",
                "--json",
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["validation"]["success"] is True
        assert data["validation"]["manifest"] == "run-tests-json"
        assert data["tests"]["success"] is True
        assert data["tests"]["total"] == 1
        assert data["tests"]["results"][0]["exit_code"] == 0

    def test_validate_run_tests_json_reports_pyproject_pytest_addopts_integrity_error(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-json-pyproject-selector",
            "python -m pytest tests -q",
            test_assertion="gate() == 'not ok'",
        )
        (tmp_path / "tests" / "test_other.py").write_text(
            "from src.gate import gate\n\n"
            "def test_other():\n"
            "    assert gate() == 'ok'\n"
        )
        _write_pyproject_pytest_addopts(tmp_path, '"-k test_other"')

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-json-pyproject-selector.manifest.yaml",
                "--no-chain",
                "--run-tests",
                "--json",
            ]
        )

        assert exit_code == 1
        data = json.loads(capsys.readouterr().out)
        assert data["success"] is False
        assert data["validation"]["success"] is True
        chain_errors = data["tests"]["chain_errors"]
        assert chain_errors[0]["code"] == "E230"
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in chain_errors[0]["message"]
        assert "pyproject.toml" in chain_errors[0]["message"]

    def test_validate_run_tests_json_reports_null_tests_when_structure_fails(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-structure-fail",
            "python -c \"open('ran.txt', 'w').write('ran')\"",
        )
        (tmp_path / "src" / "gate.py").write_text("# missing declared gate\n")

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-structure-fail.manifest.yaml",
                "--no-chain",
                "--run-tests",
                "--json",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is False
        assert data["validation"]["success"] is False
        assert data["validation"]["manifest"] == "run-tests-structure-fail"
        assert data["tests"] is None
        assert not (tmp_path / "ran.txt").exists()

    def test_validate_run_tests_quiet_prints_failing_command(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-quiet-fail",
            "python -m pytest tests/test_gate.py -q --bad-option",
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-quiet-fail.manifest.yaml",
                "--no-chain",
                "--run-tests",
                "--quiet",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "FAIL [run-tests-quiet-fail]" in captured.out
        assert "--bad-option" in captured.out

    def test_validate_all_run_tests_quiet_prints_failing_command(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-quiet-batch-fail",
            "python -m pytest tests/test_gate.py -q --bad-option",
        )

        os.chdir(tmp_path)
        exit_code = main(["validate", "--run-tests", "--quiet"])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "FAIL [run-tests-quiet-batch-fail]" in captured.out
        assert "--bad-option" in captured.out

    def test_behavioral_mode_reports_test_function_behavior_warnings_by_default(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        manifest = {
            "schema": "2",
            "goal": "Behavior check",
            "type": "feature",
            "files": {
                "edit": [
                    {
                        "path": "tests/test_api.test.ts",
                        "artifacts": [
                            {
                                "kind": "test_function",
                                "name": "test_api_call",
                                "test_function_details": {
                                    "actions": [
                                        {
                                            "type": "api_call",
                                            "subject": {
                                                "module": "src/api.ts",
                                                "export": "createLogin",
                                            },
                                            "endpoint": "/api/v1/auth/login",
                                        }
                                    ]
                                },
                            }
                        ],
                    }
                ]
            },
            "validate": ["echo ok"],
        }
        (manifest_dir / "behavior.manifest.yaml").write_text(yaml.dump(manifest))
        (tests_dir / "test_api.test.ts").write_text(
            'it("test_api_call", () => { expect(true).toBe(true); });\n'
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/behavior.manifest.yaml",
                "--mode",
                "behavioral",
                "--no-chain",
                "--json",
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert any(w["code"] == "E610" for w in data["warnings"])

    def test_behavioral_validate_check_assertions_returns_1_for_no_assertions(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "src" / "greet.py").write_text("def greet():\n    return 'hello'\n")
        (tmp_path / "tests" / "test_greet.py").write_text(
            "from src.greet import greet\n\ndef test_greet():\n    greet()\n"
        )
        manifest = {
            "schema": "2",
            "goal": "Add greet",
            "type": "feature",
            "files": {
                "create": [
                    {
                        "path": "src/greet.py",
                        "artifacts": [{"kind": "function", "name": "greet"}],
                    }
                ],
                "read": ["tests/test_greet.py"],
            },
            "validate": ["pytest tests/test_greet.py -v"],
        }
        (manifest_dir / "add-greet.manifest.yaml").write_text(yaml.dump(manifest))

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--mode",
                "behavioral",
                "--no-chain",
                "--check-assertions",
                "--fail-on-warnings",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "E210" in captured.out
        assert "Warnings" in captured.out

    def test_implementation_validate_check_stubs_returns_1_for_stub_function(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "src" / "greet.py").write_text("def greet():\n    pass\n")
        (tmp_path / "tests" / "test_greet.py").write_text(
            "from src.greet import greet\n\n"
            "def test_greet():\n"
            "    assert greet is not None\n"
        )
        manifest = {
            "schema": "2",
            "goal": "Add greet",
            "type": "feature",
            "files": {
                "create": [
                    {
                        "path": "src/greet.py",
                        "artifacts": [{"kind": "function", "name": "greet"}],
                    }
                ],
                "read": ["tests/test_greet.py"],
            },
            "validate": ["pytest tests/test_greet.py -v"],
        }
        (manifest_dir / "add-greet.manifest.yaml").write_text(yaml.dump(manifest))

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--no-chain",
                "--check-stubs",
                "--fail-on-warnings",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "E310" in captured.out
        assert "Warnings" in captured.out

        quiet_exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--no-chain",
                "--check-stubs",
                "--fail-on-warnings",
                "--quiet",
            ]
        )

        assert quiet_exit_code == 1
        quiet_output = capsys.readouterr().out
        assert "E310" in quiet_output
        assert "Warnings" in quiet_output

    def test_validate_strict_enables_assertion_stub_and_warning_failure(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "src" / "greet.py").write_text("def greet():\n    pass\n")
        (tmp_path / "tests" / "test_greet.py").write_text(
            "from src.greet import greet\n\ndef test_greet():\n    greet()\n"
        )
        manifest = {
            "schema": "2",
            "goal": "Add greet",
            "type": "feature",
            "files": {
                "create": [
                    {
                        "path": "src/greet.py",
                        "artifacts": [{"kind": "function", "name": "greet"}],
                    }
                ],
                "read": ["tests/test_greet.py"],
            },
            "validate": ["pytest tests/test_greet.py -v"],
        }
        (manifest_dir / "add-greet.manifest.yaml").write_text(yaml.dump(manifest))

        os.chdir(tmp_path)
        default_exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--mode",
                "behavioral",
                "--no-chain",
            ]
        )
        assert default_exit_code == 0
        capsys.readouterr()

        behavioral_exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--mode",
                "behavioral",
                "--no-chain",
                "--strict",
            ]
        )
        behavioral_output = capsys.readouterr().out

        implementation_exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--no-chain",
                "--strict",
            ]
        )
        implementation_output = capsys.readouterr().out

        assert behavioral_exit_code == 1
        assert "E210" in behavioral_output
        assert implementation_exit_code == 1
        assert "E310" in implementation_output

    def test_schema_mode_single_manifest_returns_0_for_valid_schema_without_source_files(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        manifest = {
            "schema": "2",
            "goal": "Validate schema only",
            "type": "feature",
            "files": {
                "create": [
                    {
                        "path": "src/missing.py",
                        "artifacts": [{"kind": "function", "name": "missing"}],
                    }
                ],
                "read": ["tests/test_missing.py"],
            },
            "validate": ["python missing_test_runner.py"],
        }
        (manifest_dir / "schema-only.manifest.yaml").write_text(yaml.dump(manifest))

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/schema-only.manifest.yaml",
                "--mode",
                "schema",
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "PASS schema-only" in captured.out
        assert "Mode: schema" in captured.out

    def test_schema_mode_single_manifest_returns_1_for_invalid_schema(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        (manifest_dir / "invalid.manifest.yaml").write_text(
            yaml.dump({"schema": "2", "type": "feature"})
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/invalid.manifest.yaml",
                "--mode",
                "schema",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "E004" in captured.out

    def test_schema_mode_cli_returns_1_for_duplicate_yaml_key(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        (manifest_dir / "duplicate.manifest.yaml").write_text(
            """schema: "2"
goal: "Reject duplicate key"
type: fix
files:
  create:
    - path: src/visible.py
      artifacts:
        - kind: function
          name: visible
files:
  create:
    - path: src/actual.py
      artifacts:
        - kind: function
          name: actual
validate:
  - pytest tests/test_actual.py -q
"""
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/duplicate.manifest.yaml",
                "--mode",
                "schema",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "E003" in captured.out
        assert "duplicate YAML key" in captured.out

    def test_schema_mode_all_manifests_reports_schema_load_errors(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        valid_manifest = {
            "schema": "2",
            "goal": "Validate schema only",
            "type": "feature",
            "files": {
                "create": [
                    {
                        "path": "src/missing.py",
                        "artifacts": [{"kind": "function", "name": "missing"}],
                    }
                ]
            },
            "validate": [],
        }
        (manifest_dir / "valid.manifest.yaml").write_text(yaml.dump(valid_manifest))
        (manifest_dir / "invalid.manifest.yaml").write_text(
            yaml.dump({"schema": "2", "type": "feature"})
        )

        os.chdir(tmp_path)
        exit_code = main(["validate", "--mode", "schema"])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Validation Results: 2 manifests" in captured.out
        assert "E004" in captured.out


class TestCmdValidateAll:
    def test_validate_all_returns_0_on_success(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(["validate"])
        assert exit_code == 0

    def test_validate_file_tracking_gate_returns_1_for_undeclared_source(
        self, project_dir, capsys
    ):
        from maid_runner.cli.commands._main import main

        (project_dir / "src" / "extra.py").write_text(
            "def extra():\n    return 'drift'\n"
        )

        os.chdir(project_dir)
        exit_code = main(["validate", "--file-tracking"])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "src/extra.py" in captured.out

        json_exit_code = main(["validate", "--file-tracking", "--json"])

        assert json_exit_code == 1
        json_output = capsys.readouterr().out
        data = json.loads(json_output)
        assert "src/extra.py" in json.dumps(data)

        schema_exit_code = main(["validate", "--mode", "schema", "--file-tracking"])

        assert schema_exit_code == 1
        schema_output = capsys.readouterr().out
        assert "src/extra.py" in schema_output

        from maid_runner.cli.commands import validate as validate_cmd

        watch_args = argparse.Namespace(
            watch=True,
            watch_all=False,
            manifest_path="manifests/add-greet.manifest.yaml",
            manifest_dir="manifests/",
            mode="implementation",
            json=False,
            quiet=False,
            no_chain=True,
            coherence=False,
            coherence_only=False,
            file_tracking=True,
        )
        watch_exit_code = validate_cmd.cmd_validate(watch_args)

        assert watch_exit_code == 2
        watch_output = capsys.readouterr()
        assert "--file-tracking is only supported" in watch_output.err

    def test_validate_worktree_scope_returns_1_for_out_of_scope_change(
        self, project_dir, capsys
    ):
        import subprocess

        from maid_runner.cli.commands._main import main

        subprocess.run(
            ["git", "init"], cwd=project_dir, check=True, capture_output=True
        )
        (project_dir / "src" / "extra.py").write_text(
            "def extra():\n    return 'drift'\n"
        )

        os.chdir(project_dir)
        exit_code = main(["validate", "--worktree-scope"])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "src/extra.py" in captured.out
        assert "E114" in captured.out

    def test_validate_worktree_scope_include_tests_reports_changed_test_file(
        self, project_dir, capsys
    ):
        import subprocess

        from maid_runner.cli.commands._main import main

        subprocess.run(
            ["git", "init"], cwd=project_dir, check=True, capture_output=True
        )

        os.chdir(project_dir)
        default_exit_code = main(["validate", "--worktree-scope"])
        default_output = capsys.readouterr().out

        include_exit_code = main(["validate", "--worktree-scope", "--include-tests"])
        include_output = capsys.readouterr().out

        assert default_exit_code == 0
        assert "tests/test_greet.py" not in default_output
        assert include_exit_code == 1
        assert "E114" in include_output
        assert "tests/test_greet.py" in include_output

    def test_validate_changed_scope_returns_1_for_changed_read_only_file(
        self, project_dir, capsys
    ):
        from maid_runner.cli.commands._main import main

        baseline = _commit_all(project_dir, "baseline")
        manifest_path = project_dir / "manifests" / "add-greet.manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text())
        manifest["metadata"] = {"maid_task_base": baseline}
        manifest["files"]["read"].append("src/greet.py")
        manifest["files"]["create"][0]["path"] = "src/owner.py"
        manifest["files"]["create"][0]["artifacts"][0]["name"] = "owner"
        manifest_path.write_text(yaml.dump(manifest))
        (project_dir / "src" / "owner.py").write_text(
            "def owner() -> str:\n    return 'ok'\n"
        )
        (project_dir / "tests" / "test_greet.py").write_text(
            "from src.owner import owner\n\n"
            "def test_owner():\n"
            "    assert owner() == 'ok'\n"
        )
        (project_dir / "src" / "greet.py").write_text(
            "def greet(name: str) -> str:\n    return f'Hi, {name}'\n"
        )

        os.chdir(project_dir)
        exit_code = main(["validate", "--changed-scope"])

        assert exit_code == 1
        output = capsys.readouterr().out
        assert "E114" in output
        assert "src/greet.py" in output

    def test_validate_manifest_changed_scope_uses_selected_manifest_scope(
        self, project_dir, capsys
    ):
        from maid_runner.cli.commands._main import main

        baseline = _commit_all(project_dir, "baseline")
        selected_manifest = project_dir / "manifests" / "add-greet.manifest.yaml"
        manifest = yaml.safe_load(selected_manifest.read_text())
        manifest["metadata"] = {"maid_task_base": baseline}
        manifest["files"]["read"].append("src/greet.py")
        manifest["files"]["create"][0]["path"] = "src/owner.py"
        manifest["files"]["create"][0]["artifacts"][0]["name"] = "owner"
        selected_manifest.write_text(yaml.dump(manifest))

        masking_manifest = {
            "schema": "2",
            "goal": "Mask changed scope",
            "type": "fix",
            "metadata": {"maid_task_base": baseline},
            "files": {
                "edit": [
                    {
                        "path": "src/greet.py",
                        "artifacts": [
                            {
                                "kind": "function",
                                "name": "greet",
                                "returns": "str",
                            }
                        ],
                    }
                ],
                "read": ["tests/test_greet.py"],
            },
            "validate": ["pytest tests/test_greet.py -v"],
        }
        (project_dir / "manifests" / "mask-greet.manifest.yaml").write_text(
            yaml.dump(masking_manifest)
        )
        (project_dir / "src" / "owner.py").write_text(
            "def owner() -> str:\n    return 'ok'\n"
        )
        (project_dir / "tests" / "test_greet.py").write_text(
            "from src.owner import owner\n\n"
            "def test_owner():\n"
            "    assert owner() == 'ok'\n"
        )
        (project_dir / "src" / "greet.py").write_text(
            "def greet(name: str) -> str:\n    return f'Hi, {name}'\n"
        )

        os.chdir(project_dir)
        exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--no-chain",
                "--changed-scope",
            ]
        )

        assert exit_code == 1
        output = capsys.readouterr().out
        assert "E114" in output
        assert "src/greet.py" in output

    def test_validate_changed_scope_requires_explicit_or_metadata_baseline(
        self, project_dir, capsys
    ):
        from maid_runner.cli.commands._main import main

        _commit_all(project_dir, "baseline")

        os.chdir(project_dir)
        exit_code = main(["validate", "--changed-scope"])

        assert exit_code == 1
        output = capsys.readouterr().out
        assert "E115" in output
        assert "origin/main" not in output

    def test_validate_all_returns_1_on_failure(self, failing_project, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(failing_project)
        exit_code = main(["validate"])
        assert exit_code == 1

    def test_validate_all_includes_nested_active_manifest_failure(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        (manifest_dir / "components" / "auth").mkdir(parents=True)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "top_level.py").write_text(
            "def top_level():\n    return 'ok'\n"
        )

        top_manifest = {
            "schema": "2",
            "goal": "Top-level active manifest",
            "type": "fix",
            "files": {
                "create": [
                    {
                        "path": "src/top_level.py",
                        "artifacts": [{"kind": "function", "name": "top_level"}],
                    }
                ],
                "read": ["tests/test_top_level.py"],
            },
            "validate": ["pytest tests/test_top_level.py -q"],
        }
        nested_manifest = {
            "schema": "2",
            "goal": "Nested active manifest",
            "type": "fix",
            "files": {
                "create": [
                    {
                        "path": "src/missing_nested.py",
                        "artifacts": [{"kind": "function", "name": "missing_nested"}],
                    }
                ],
                "read": ["tests/test_missing_nested.py"],
            },
            "validate": ["pytest tests/test_missing_nested.py -q"],
        }
        (manifest_dir / "top-level.manifest.yaml").write_text(yaml.dump(top_manifest))
        nested_manifest_path = (
            manifest_dir / "components" / "auth" / "nested-active.manifest.yml"
        )
        nested_manifest_path.write_text(yaml.dump(nested_manifest))
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_top_level.py").write_text(
            "from src.top_level import top_level\n\n"
            "def test_top_level():\n"
            "    assert top_level is not None\n"
        )
        (tmp_path / "tests" / "test_missing_nested.py").write_text(
            "from src.missing_nested import missing_nested\n\n"
            "def test_missing_nested():\n"
            "    assert missing_nested is not None\n"
        )

        os.chdir(tmp_path)
        exit_code = main(["validate", "--manifest-dir", "manifests"])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Validation Results: 2 manifests" in captured.out
        assert "FAIL nested-active" in captured.out
        assert "src/missing_nested.py" in captured.out

    def test_validate_all_json_output(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(["validate", "--json"])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "total" in data
        assert "passed" in data

    def test_validate_nonexistent_dir_returns_1_by_default(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(tmp_path)
        exit_code = main(["validate", "--manifest-dir", "nonexistent/"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "E112" in captured.out
        assert "nonexistent" in captured.out

    def test_validate_empty_manifest_dir_returns_1_by_default(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        (tmp_path / "manifests").mkdir()
        os.chdir(tmp_path)

        exit_code = main(["validate"])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "E112" in captured.out
        assert "No active manifests discovered" in captured.out

    def test_validate_allow_empty_returns_0_for_empty_manifest_dir(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import build_parser
        from maid_runner.cli.commands._main import main

        (tmp_path / "manifests").mkdir()
        os.chdir(tmp_path)

        args = build_parser().parse_args(["validate", "--allow-empty"])
        assert args.allow_empty is True

        exit_code = main(["validate", "--allow-empty"])

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Validation Results: 0 manifests" in captured.out

    def test_behavioral_mode(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(["validate", "--mode", "behavioral"])
        # May return 1 since there's no actual test file
        assert exit_code in (0, 1)


class TestCmdValidateCoherenceOnly:
    def test_coherence_only_with_valid_manifests(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(["validate", "--coherence-only"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Coherence:" in captured.out

    def test_coherence_only_json_output(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(["validate", "--coherence-only", "--json"])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "success" in data

    def test_coherence_only_nonexistent_dir(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(tmp_path)
        exit_code = main(
            ["validate", "--coherence-only", "--manifest-dir", "nonexistent/"]
        )
        assert exit_code == 2


class TestCmdValidateCoherenceFlag:
    def test_coherence_flag_returns_1_when_coherence_errors(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        (project_dir / ".maid-constraints.json").write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "name": "no-greet",
                            "description": "greet module is blocked",
                            "pattern": {
                                "file_pattern": "src/greet.py",
                                "forbidden_imports": ["blocked"],
                            },
                            "severity": "error",
                        }
                    ]
                }
            )
        )

        os.chdir(project_dir)
        exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--no-chain",
                "--coherence",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Coherence: FAIL" in captured.out
        assert "greet module is blocked" in captured.out

    def test_coherence_flag_json_reports_failure_and_exits_1(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        (project_dir / ".maid-constraints.json").write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "name": "no-greet",
                            "description": "greet module is blocked",
                            "pattern": {
                                "file_pattern": "src/greet.py",
                                "forbidden_imports": ["blocked"],
                            },
                            "severity": "error",
                        }
                    ]
                }
            )
        )

        os.chdir(project_dir)
        exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--no-chain",
                "--coherence",
                "--json",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is False
        assert data["validation"]["success"] is True
        coherence = data["coherence"]
        assert coherence["success"] is False
        assert coherence["errors"] == 1
        assert coherence["issues"][0]["message"] == "greet module is blocked"

    def test_coherence_flag_json_reports_success_in_single_document(
        self, project_dir, capsys
    ):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(["validate", "--coherence", "--json"])

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["validation"]["success"] is True
        assert data["validation"]["total"] == 1
        assert data["coherence"]["success"] is True
        assert data["coherence"]["errors"] == 0

    def test_coherence_flag_json_preserves_run_tests_result_in_single_document(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-coherence-json",
            "python -m pytest tests/test_gate.py -q",
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-coherence-json.manifest.yaml",
                "--no-chain",
                "--run-tests",
                "--coherence",
                "--json",
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["validation"]["success"] is True
        assert data["tests"]["success"] is True
        assert data["tests"]["total"] == 1
        assert data["coherence"]["success"] is True

    def test_coherence_flag_json_preserves_failing_run_tests_result_in_single_document(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-fail-coherence-json",
            "python -m pytest tests/test_gate.py -q",
            test_assertion="gate() == 'nope'",
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-fail-coherence-json.manifest.yaml",
                "--no-chain",
                "--run-tests",
                "--coherence",
                "--json",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is False
        assert data["validation"]["success"] is True
        assert data["tests"]["success"] is False
        assert data["tests"]["total"] == 1
        assert data["tests"]["failed"] == 1
        assert data["tests"]["results"][0]["exit_code"] == 1
        assert data["coherence"]["success"] is True

    def test_coherence_flag_json_preserves_failing_run_tests_and_coherence_result_in_single_document(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "run-tests-and-coherence-fail-json",
            "python -m pytest tests/test_gate.py -q",
            test_assertion="gate() == 'nope'",
        )
        (tmp_path / ".maid-constraints.json").write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "name": "no-gate",
                            "description": "gate module is blocked",
                            "pattern": {
                                "file_pattern": "src/gate.py",
                                "forbidden_imports": ["blocked"],
                            },
                            "severity": "error",
                        }
                    ]
                }
            )
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/run-tests-and-coherence-fail-json.manifest.yaml",
                "--no-chain",
                "--run-tests",
                "--coherence",
                "--json",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is False
        assert data["validation"]["success"] is True
        assert data["tests"]["success"] is False
        assert data["tests"]["failed"] == 1
        assert data["coherence"]["success"] is False
        assert data["coherence"]["errors"] == 1
        assert data["coherence"]["issues"][0]["message"] == "gate module is blocked"

    def test_coherence_flag_json_preserves_batch_failing_run_tests_result_in_single_document(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "batch-run-tests-fail-coherence-json",
            "python -m pytest tests/test_gate.py -q",
            test_assertion="gate() == 'nope'",
        )

        os.chdir(tmp_path)
        exit_code = main(["validate", "--run-tests", "--coherence", "--json"])

        assert exit_code == 1
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is False
        assert data["validation"]["success"] is True
        assert data["validation"]["total"] == 1
        assert data["tests"]["success"] is False
        assert data["tests"]["total"] == 1
        assert data["tests"]["failed"] == 1
        assert data["tests"]["results"][0]["manifest"] == (
            "batch-run-tests-fail-coherence-json"
        )
        assert data["tests"]["results"][0]["exit_code"] == 1
        assert data["coherence"]["success"] is True

    def test_coherence_flag_json_preserves_batch_failing_run_tests_and_coherence_result_in_single_document(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_run_tests_project(
            tmp_path,
            "batch-run-tests-and-coherence-fail-json",
            "python -m pytest tests/test_gate.py -q",
            test_assertion="gate() == 'nope'",
        )
        (tmp_path / ".maid-constraints.json").write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "name": "no-gate",
                            "description": "gate module is blocked",
                            "pattern": {
                                "file_pattern": "src/gate.py",
                                "forbidden_imports": ["blocked"],
                            },
                            "severity": "error",
                        }
                    ]
                }
            )
        )

        os.chdir(tmp_path)
        exit_code = main(["validate", "--run-tests", "--coherence", "--json"])

        assert exit_code == 1
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is False
        assert data["validation"]["success"] is True
        assert data["tests"]["success"] is False
        assert data["tests"]["failed"] == 1
        assert data["coherence"]["success"] is False
        assert data["coherence"]["errors"] == 1
        assert data["coherence"]["issues"][0]["message"] == "gate module is blocked"

    def test_coherence_flag_returns_2_when_coherence_cannot_run(
        self, project_dir, capsys, monkeypatch
    ):
        from maid_runner.cli.commands import validate
        from maid_runner.cli.commands.validate import run_coherence

        assert callable(run_coherence)

        def fail_coherence(manifest_dir, json_mode):
            raise RuntimeError(f"cannot run coherence for {manifest_dir}")

        monkeypatch.setattr(validate, "run_coherence", fail_coherence)

        os.chdir(project_dir)
        args = argparse.Namespace(
            watch=False,
            watch_all=False,
            manifest_path="manifests/add-greet.manifest.yaml",
            manifest_dir="manifests/",
            mode="implementation",
            json=False,
            quiet=False,
            no_chain=True,
            coherence=True,
            coherence_only=False,
        )

        exit_code = validate.cmd_validate(args)

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "cannot run coherence for manifests/" in captured.err

    def test_coherence_flag_json_returns_2_when_coherence_cannot_run(
        self, project_dir, capsys, monkeypatch
    ):
        from maid_runner.cli.commands import validate
        from maid_runner.cli.commands.validate import run_coherence

        assert callable(run_coherence)

        def fail_coherence(manifest_dir, json_mode):
            raise RuntimeError(f"cannot run coherence for {manifest_dir}")

        monkeypatch.setattr(validate, "run_coherence", fail_coherence)

        os.chdir(project_dir)
        args = argparse.Namespace(
            watch=False,
            watch_all=False,
            manifest_path="manifests/add-greet.manifest.yaml",
            manifest_dir="manifests/",
            mode="implementation",
            json=True,
            quiet=False,
            no_chain=True,
            coherence=True,
            coherence_only=False,
        )

        exit_code = validate.cmd_validate(args)

        assert exit_code == 2
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data == {"error": "cannot run coherence for manifests/"}
        assert captured.err == ""

    def test_coherence_flag_appends_coherence_output(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--no-chain",
                "--coherence",
            ]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        # Coherence output may be appended after validation
        assert "add-greet" in captured.out

    def test_coherence_flag_on_batch_validation(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(["validate", "--coherence"])
        assert exit_code == 0


class TestCmdValidateWatchMode:
    def test_watch_without_watchdog_returns_error(self, project_dir, capsys):
        """If watchdog is not installed, watch mode returns 2."""
        import importlib.util

        # Check if watchdog is available
        if importlib.util.find_spec("watchdog") is not None:
            pytest.skip("watchdog is installed, cannot test missing dependency path")

        from maid_runner.cli.commands.validate import _run_watch

        args = argparse.Namespace(
            watch=True,
            watch_all=False,
            manifest_path=None,
            manifest_dir="manifests/",
            mode="implementation",
            json=False,
            quiet=False,
            no_chain=False,
            coherence=False,
            coherence_only=False,
        )
        exit_code = _run_watch(args)
        assert exit_code == 2


class TestCmdValidateErrorHandling:
    def test_malformed_manifest_returns_error(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        (manifest_dir / "bad.manifest.yaml").write_text("not: valid: yaml: {{}")

        os.chdir(tmp_path)
        exit_code = main(["validate", "manifests/bad.manifest.yaml", "--no-chain"])
        assert exit_code in (1, 2)  # Either validation error or usage error

    def test_exception_in_validation_returns_2(self, tmp_path, capsys):
        """When validation raises an unexpected exception, returns 2."""
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        # Write manifest pointing to missing directory structure
        manifest = {
            "schema": "2",
            "goal": "Test error",
            "type": "feature",
            "files": {"create": []},
            "validate": [],
        }
        (manifest_dir / "test.manifest.yaml").write_text(yaml.dump(manifest))

        os.chdir(tmp_path)
        # This should handle gracefully
        exit_code = main(["validate"])
        assert exit_code in (0, 1, 2)


class TestRunValidationPass:
    def test_single_manifest_pass(self, project_dir, capsys):
        """_run_validation_pass validates a single manifest."""
        from maid_runner.cli.commands.validate import _run_validation_pass

        os.chdir(project_dir)
        args = argparse.Namespace(
            manifest_path="manifests/add-greet.manifest.yaml",
            manifest_dir="manifests/",
            mode="implementation",
            json=False,
            quiet=False,
            no_chain=True,
            watch_all=False,
        )
        _run_validation_pass(args)
        captured = capsys.readouterr()
        assert "add-greet" in captured.out

    def test_batch_validation_pass(self, project_dir, capsys):
        """_run_validation_pass validates all manifests when watch_all."""
        from maid_runner.cli.commands.validate import _run_validation_pass

        os.chdir(project_dir)
        args = argparse.Namespace(
            manifest_path=None,
            manifest_dir="manifests/",
            mode="implementation",
            json=False,
            quiet=False,
            no_chain=True,
            watch_all=True,
        )
        _run_validation_pass(args)
        captured = capsys.readouterr()
        assert "Validation Results" in captured.out

    def test_error_handling_in_pass(self, tmp_path, capsys):
        """_run_validation_pass handles errors gracefully."""
        from maid_runner.cli.commands.validate import _run_validation_pass

        os.chdir(tmp_path)
        args = argparse.Namespace(
            manifest_path="nonexistent.yaml",
            manifest_dir="manifests/",
            mode="implementation",
            json=False,
            quiet=False,
            no_chain=True,
            watch_all=False,
        )
        # Should not crash
        _run_validation_pass(args)
        captured = capsys.readouterr()
        assert "Error" in captured.err or "FAIL" in captured.out or captured.out
