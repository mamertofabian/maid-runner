"""Tests for CLI 'maid test' command (v2)."""

from __future__ import annotations

import json
import os
import textwrap
from argparse import Namespace

import pytest
import yaml


@pytest.fixture
def project_with_tests(tmp_path):
    """Create a project with a manifest that has a passing test command."""
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    (src_dir / "greet.py").write_text(
        textwrap.dedent(
            """\
        def greet(name: str) -> str:
            return f"Hello, {name}"
        """
        )
    )

    # Use 'true' command as a always-passing validation command
    manifest = {
        "schema": "2",
        "goal": "Add greeting function",
        "type": "feature",
        "files": {
            "create": [
                {
                    "path": "src/greet.py",
                    "artifacts": [
                        {"kind": "function", "name": "greet"},
                    ],
                }
            ]
        },
        "validate": ["true"],
    }
    (manifest_dir / "add-greet.manifest.yaml").write_text(yaml.dump(manifest))

    return tmp_path


@pytest.fixture
def project_with_failing_tests(tmp_path):
    """Create a project with a manifest that has a failing test command."""
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()

    manifest = {
        "schema": "2",
        "goal": "Failing task",
        "type": "feature",
        "files": {
            "create": [
                {
                    "path": "src/fail.py",
                    "artifacts": [
                        {"kind": "function", "name": "fail_func"},
                    ],
                }
            ]
        },
        "validate": ["false"],
    }
    (manifest_dir / "fail-task.manifest.yaml").write_text(yaml.dump(manifest))

    return tmp_path


def _write_noop_behavioral_test_project(
    tmp_path,
    slug: str = "test-noop",
    *,
    validate_command: str = 'python -c "raise SystemExit(0)"',
):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir(exist_ok=True)
    src_dir = tmp_path / "src"
    src_dir.mkdir(exist_ok=True)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(exist_ok=True)

    (src_dir / "gate.py").write_text("def gate() -> str:\n    return 'ok'\n")
    (tests_dir / "test_gate.py").write_text(
        "from src.gate import gate\n\ndef test_gate():\n    assert gate() == 'not ok'\n"
    )

    manifest = {
        "schema": "2",
        "goal": "Reject no-op validate command",
        "type": "fix",
        "files": {
            "edit": [
                {
                    "path": "src/gate.py",
                    "artifacts": [
                        {"kind": "function", "name": "gate"},
                    ],
                }
            ],
            "read": ["tests/test_gate.py"],
        },
        "validate": [validate_command],
    }
    manifest_path = manifest_dir / f"{slug}.manifest.yaml"
    manifest_path.write_text(yaml.dump(manifest))
    return manifest_path


def _write_parent_relative_test_target_project(tmp_path, slug: str):
    project_root = tmp_path / "project"
    project_root.mkdir()
    manifest_path = _write_noop_behavioral_test_project(
        project_root,
        slug,
        validate_command="python -m pytest ../tests/test_gate.py -q",
    )
    sibling_tests = tmp_path / "tests"
    sibling_tests.mkdir()
    (sibling_tests / "test_gate.py").write_text(
        "from src.gate import gate\n\n"
        "def test_gate():\n"
        "    assert gate() == 'ok'\n"
    )
    return project_root, manifest_path


class TestCmdTestAll:
    def test_passing_tests_return_0(self, project_with_tests, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_with_tests)
        exit_code = main(["test"])
        assert exit_code == 0

    def test_failing_tests_return_1(self, project_with_failing_tests, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_with_failing_tests)
        exit_code = main(["test"])
        assert exit_code == 1

    def test_json_output(self, project_with_tests, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_with_tests)
        exit_code = main(["test", "--json"])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["total"] >= 1
        assert data["passed"] >= 1

    def test_verbose_shows_stdout(self, project_with_tests, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_with_tests)
        exit_code = main(["test", "--verbose"])
        assert exit_code == 0

    def test_no_manifests_returns_0(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        # Empty dir with no manifests
        (tmp_path / "manifests").mkdir()
        os.chdir(tmp_path)
        exit_code = main(["test"])
        assert exit_code == 0

    def test_default_batch_flag_uses_auto_mode(self, monkeypatch, capsys):
        from maid_runner.cli.commands.test import cmd_test
        from maid_runner.core.result import BatchTestResult

        captured = {}

        def fake_run_tests(**kwargs):
            captured["batch"] = kwargs["batch"]
            return BatchTestResult(results=[], total=0, passed=0, failed=0)

        monkeypatch.setattr("maid_runner.core.test_runner.run_tests", fake_run_tests)

        exit_code = cmd_test(
            Namespace(
                manifest=None,
                manifest_dir="manifests/",
                fail_fast=False,
                batch=None,
                verbose=False,
                json=False,
            )
        )

        assert exit_code == 0
        assert captured["batch"] is None

    def test_test_rejects_noop_validate_command_for_behavioral_tests(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        _write_noop_behavioral_test_project(tmp_path)

        os.chdir(tmp_path)
        exit_code = main(["test"])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "python -c" in captured.out

    def test_test_rejects_parent_relative_validate_command_target(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        project_root, _ = _write_parent_relative_test_target_project(
            tmp_path,
            "test-parent-relative-target",
        )

        os.chdir(project_root)
        exit_code = main(["test"])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "E113" in captured.out
        assert "../tests/test_gate.py" in captured.out


class TestCmdTestSingleManifest:
    def test_single_manifest_passing(self, project_with_tests, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_with_tests)
        exit_code = main(["test", "--manifest", "manifests/add-greet.manifest.yaml"])
        assert exit_code == 0

    def test_single_manifest_failing(self, project_with_failing_tests, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_with_failing_tests)
        exit_code = main(["test", "--manifest", "manifests/fail-task.manifest.yaml"])
        assert exit_code == 1

    def test_test_manifest_rejects_noop_validate_command_for_behavioral_tests(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_path = _write_noop_behavioral_test_project(tmp_path)

        os.chdir(tmp_path)
        exit_code = main(["test", "--manifest", str(manifest_path)])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in captured.out
        assert "python -c" in captured.out

    def test_test_manifest_rejects_parent_relative_validate_command_target(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        project_root, manifest_path = _write_parent_relative_test_target_project(
            tmp_path,
            "test-manifest-parent-relative-target",
        )

        os.chdir(project_root)
        exit_code = main(["test", "--manifest", str(manifest_path)])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "E113" in captured.out
        assert "../tests/test_gate.py" in captured.out


class TestCmdTestFailFast:
    def test_fail_fast_stops_on_first_failure(self, project_with_failing_tests, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_with_failing_tests)
        exit_code = main(["test", "--fail-fast"])
        assert exit_code == 1
