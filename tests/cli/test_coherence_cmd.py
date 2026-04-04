"""Tests for CLI 'maid coherence' command."""

from __future__ import annotations

import argparse
import json

import yaml


class TestCmdCoherenceMissingDir:
    def test_missing_manifest_dir_returns_2(self, tmp_path, capsys):
        """Non-existent manifest directory returns exit code 2."""
        from maid_runner.cli.commands.coherence import cmd_coherence

        args = argparse.Namespace(
            manifest_dir=str(tmp_path / "nonexistent"),
            checks=None,
            exclude=None,
            json=False,
        )
        exit_code = cmd_coherence(args)

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "not found" in captured.err.lower()

    def test_missing_manifest_dir_json_mode(self, tmp_path, capsys):
        """Non-existent manifest directory in JSON mode prints JSON error to stdout."""
        from maid_runner.cli.commands.coherence import cmd_coherence

        args = argparse.Namespace(
            manifest_dir=str(tmp_path / "nonexistent"),
            checks=None,
            exclude=None,
            json=True,
        )
        exit_code = cmd_coherence(args)

        assert exit_code == 2
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "error" in data
        assert "not found" in data["error"].lower()


def _create_manifest_project(tmp_path):
    """Helper: create a minimal project with one valid manifest."""
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    (src_dir / "example.py").write_text("def example_func():\n    pass\n")

    manifest = {
        "schema": "2",
        "goal": "Test goal",
        "type": "feature",
        "files": {
            "create": [
                {
                    "path": "src/example.py",
                    "artifacts": [
                        {"kind": "function", "name": "example_func"},
                    ],
                }
            ]
        },
        "validate": ["echo ok"],
    }
    (manifest_dir / "test-coherence.manifest.yaml").write_text(yaml.dump(manifest))
    return tmp_path


class TestCmdCoherenceSuccess:
    def test_successful_coherence_check_returns_0(self, tmp_path, capsys, monkeypatch):
        """Valid project with a simple manifest passes coherence checks."""
        from maid_runner.cli.commands.coherence import cmd_coherence

        project = _create_manifest_project(tmp_path)
        monkeypatch.chdir(project)

        args = argparse.Namespace(
            manifest_dir=str(project / "manifests"),
            checks=None,
            exclude=None,
            json=False,
        )
        exit_code = cmd_coherence(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "PASS" in captured.out


class TestCmdCoherenceFiltering:
    def test_checks_filter_includes_only_specified(self, tmp_path, capsys, monkeypatch):
        """--checks flag limits which coherence checks run."""
        from maid_runner.cli.commands.coherence import cmd_coherence

        project = _create_manifest_project(tmp_path)
        monkeypatch.chdir(project)

        args = argparse.Namespace(
            manifest_dir=str(project / "manifests"),
            checks="duplicate",
            exclude=None,
            json=True,
        )
        exit_code = cmd_coherence(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["checks_run"] == ["duplicate"]

    def test_exclude_filter_removes_specified(self, tmp_path, capsys, monkeypatch):
        """--exclude flag removes specified checks from the run."""
        from maid_runner.cli.commands.coherence import cmd_coherence

        project = _create_manifest_project(tmp_path)
        monkeypatch.chdir(project)

        args = argparse.Namespace(
            manifest_dir=str(project / "manifests"),
            checks=None,
            exclude="duplicate,signature",
            json=True,
        )
        exit_code = cmd_coherence(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "duplicate" not in data["checks_run"]
        assert "signature" not in data["checks_run"]
        # Other checks should still have run
        assert len(data["checks_run"]) > 0

    def test_checks_and_exclude_combined(self, tmp_path, capsys, monkeypatch):
        """When both --checks and --exclude are set, include is applied first, then exclude."""
        from maid_runner.cli.commands.coherence import cmd_coherence

        project = _create_manifest_project(tmp_path)
        monkeypatch.chdir(project)

        args = argparse.Namespace(
            manifest_dir=str(project / "manifests"),
            checks="duplicate,naming",
            exclude="naming",
            json=True,
        )
        exit_code = cmd_coherence(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["checks_run"] == ["duplicate"]


class TestCmdCoherenceViaCLI:
    def test_coherence_via_main(self, tmp_path, capsys, monkeypatch):
        """maid coherence subcommand routes to cmd_coherence correctly."""
        from maid_runner.cli.commands._main import main

        project = _create_manifest_project(tmp_path)
        monkeypatch.chdir(project)

        exit_code = main(["coherence", "--manifest-dir", str(project / "manifests")])

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Coherence" in captured.out
