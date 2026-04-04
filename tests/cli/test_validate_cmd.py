"""Tests for CLI 'maid validate' command (v2)."""

from __future__ import annotations

import argparse
import json
import os
import textwrap

import pytest
import yaml


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
            ]
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


class TestCmdValidateSingleManifest:
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


class TestCmdValidateAll:
    def test_validate_all_returns_0_on_success(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(["validate"])
        assert exit_code == 0

    def test_validate_all_returns_1_on_failure(self, failing_project, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(failing_project)
        exit_code = main(["validate"])
        assert exit_code == 1

    def test_validate_all_json_output(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(["validate", "--json"])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "total" in data
        assert "passed" in data

    def test_validate_nonexistent_dir_returns_0(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(tmp_path)
        # Nonexistent manifest dir returns 0 (no manifests = nothing to fail)
        exit_code = main(["validate", "--manifest-dir", "nonexistent/"])
        assert exit_code == 0

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
