"""Tests for CLI 'maid manifest' command."""

from __future__ import annotations

import argparse
import json

import yaml

from maid_runner.core.manifest import load_manifest, validate_manifest_schema


class TestCmdManifestNoCommand:
    def test_no_manifest_command_attribute_returns_2(self, capsys):
        """When args lacks manifest_command attribute, returns exit code 2."""
        from maid_runner.cli.commands.manifest import cmd_manifest

        args = argparse.Namespace()
        exit_code = cmd_manifest(args)

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "usage" in captured.err.lower()

    def test_none_manifest_command_returns_2(self, capsys):
        """When manifest_command is None, returns exit code 2."""
        from maid_runner.cli.commands.manifest import cmd_manifest

        args = argparse.Namespace(manifest_command=None)
        exit_code = cmd_manifest(args)

        assert exit_code == 2

    def test_unknown_manifest_command_returns_2(self, capsys):
        """Unrecognized subcommand returns exit code 2."""
        from maid_runner.cli.commands.manifest import cmd_manifest

        args = argparse.Namespace(manifest_command="delete")
        exit_code = cmd_manifest(args)

        assert exit_code == 2


class TestCmdManifestCreateDryRun:
    def test_create_dry_run_yaml_output(self, capsys):
        """Dry-run create prints YAML manifest to stdout."""
        from maid_runner.cli.commands.manifest import cmd_manifest

        args = argparse.Namespace(
            manifest_command="create",
            file_path="src/example.py",
            goal="Add example",
            task_type="feature",
            artifacts='[{"kind": "function", "name": "example_func"}]',
            temptations=None,
            dry_run=True,
            json=False,
        )
        exit_code = cmd_manifest(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        data = yaml.safe_load(captured.out)
        assert data["schema"] == "2"
        assert data["goal"] == "Add example"
        assert data["type"] == "feature"
        assert data["files"]["create"][0]["path"] == "src/example.py"
        assert data["files"]["create"][0]["artifacts"][0]["name"] == "example_func"
        assert validate_manifest_schema(data) == []

    def test_create_dry_run_json_output(self, capsys):
        """Dry-run create with --json prints JSON manifest to stdout."""
        from maid_runner.cli.commands.manifest import cmd_manifest

        args = argparse.Namespace(
            manifest_command="create",
            file_path="src/example.py",
            goal="Add example",
            task_type="feature",
            artifacts='[{"kind": "function", "name": "example_func"}]',
            temptations=None,
            dry_run=True,
            json=True,
        )
        exit_code = cmd_manifest(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["schema"] == "2"
        assert data["goal"] == "Add example"
        assert data["type"] == "feature"
        assert data["files"]["create"][0]["path"] == "src/example.py"
        artifacts = data["files"]["create"][0]["artifacts"]
        assert len(artifacts) == 1
        assert artifacts[0]["kind"] == "function"
        assert artifacts[0]["name"] == "example_func"
        assert validate_manifest_schema(data) == []


class TestCmdManifestCreateWithArtifacts:
    def test_create_with_multiple_artifacts(self, capsys):
        """Multiple artifacts are included in the generated manifest."""
        from maid_runner.cli.commands.manifest import cmd_manifest

        artifacts_json = json.dumps(
            [
                {"kind": "class", "name": "MyClass"},
                {"kind": "function", "name": "helper"},
            ]
        )
        args = argparse.Namespace(
            manifest_command="create",
            file_path="src/service.py",
            goal="Add service module",
            task_type="feature",
            artifacts=artifacts_json,
            temptations=None,
            dry_run=True,
            json=True,
        )
        exit_code = cmd_manifest(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        artifacts = data["files"]["create"][0]["artifacts"]
        assert len(artifacts) == 2
        assert artifacts[0]["name"] == "MyClass"
        assert artifacts[1]["name"] == "helper"

    def test_create_with_no_artifacts(self, capsys):
        """Create with no artifacts returns a schema-focused usage error."""
        from maid_runner.cli.commands.manifest import cmd_manifest

        args = argparse.Namespace(
            manifest_command="create",
            file_path="src/empty.py",
            goal="Create empty module",
            task_type="feature",
            artifacts=None,
            temptations=None,
            dry_run=True,
            json=True,
        )
        exit_code = cmd_manifest(args)

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "at least one artifact" in captured.err.lower()


class TestCmdManifestCreateErrors:
    def test_create_invalid_artifacts_json_returns_2(self, capsys):
        """Malformed JSON in --artifacts returns exit code 2."""
        from maid_runner.cli.commands.manifest import cmd_manifest

        args = argparse.Namespace(
            manifest_command="create",
            file_path="src/example.py",
            goal="Add example",
            task_type="feature",
            artifacts="not valid json",
            temptations=None,
            dry_run=True,
            json=False,
        )
        exit_code = cmd_manifest(args)

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "invalid artifacts json" in captured.err.lower()

    def test_create_missing_artifact_key_returns_2(self, capsys):
        """Artifacts JSON missing required 'name' key returns exit code 2."""
        from maid_runner.cli.commands.manifest import cmd_manifest

        args = argparse.Namespace(
            manifest_command="create",
            file_path="src/example.py",
            goal="Add example",
            task_type="feature",
            artifacts='[{"kind": "function"}]',
            temptations=None,
            dry_run=True,
            json=False,
        )
        exit_code = cmd_manifest(args)

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "invalid artifacts json" in captured.err.lower()

    def test_create_non_dry_run_writes_manifest(self, tmp_path, capsys):
        """Non-dry-run create writes a schema-valid manifest file."""
        from maid_runner.cli.commands.manifest import cmd_manifest

        args = argparse.Namespace(
            manifest_command="create",
            file_path="src/example.py",
            goal="Add example",
            task_type="feature",
            artifacts='[{"kind": "function", "name": "example_func"}]',
            output_dir=str(tmp_path / "manifests"),
            temptations=None,
            dry_run=False,
            json=False,
        )
        exit_code = cmd_manifest(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "created" in captured.out.lower()
        manifest_path = tmp_path / "manifests" / "add-example.manifest.yaml"
        manifest = load_manifest(manifest_path)
        assert manifest.goal == "Add example"
        assert manifest.files_create[0].path == "src/example.py"
        assert manifest.files_create[0].artifacts[0].name == "example_func"

    def test_create_with_temptations(self, capsys):
        """Create includes structured temptations when provided."""
        from maid_runner.cli.commands.manifest import cmd_manifest

        args = argparse.Namespace(
            manifest_command="create",
            file_path="src/example.py",
            goal="Add example",
            task_type="feature",
            artifacts='[{"kind": "function", "name": "example_func"}]',
            temptations=[
                "Do not import private helpers from tests.::Test through the public API.",
                "Do not loosen schema validation.::Add the exact schema property.",
            ],
            dry_run=True,
            json=True,
        )

        exit_code = cmd_manifest(args)

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["temptations"] == [
            {
                "risk": "Do not import private helpers from tests.",
                "instead": "Test through the public API.",
            },
            {
                "risk": "Do not loosen schema validation.",
                "instead": "Add the exact schema property.",
            },
        ]
        assert validate_manifest_schema(data) == []

    def test_create_with_invalid_temptation_format_returns_2(self, capsys):
        """Temptations must pair a risk with the procedure to use instead."""
        from maid_runner.cli.commands.manifest import cmd_manifest

        args = argparse.Namespace(
            manifest_command="create",
            file_path="src/example.py",
            goal="Add example",
            task_type="feature",
            artifacts='[{"kind": "function", "name": "example_func"}]',
            temptations=["Do not import private helpers"],
            dry_run=True,
            json=True,
        )

        exit_code = cmd_manifest(args)

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "risk::instead" in captured.err.lower()

    def test_create_with_too_many_temptations_returns_2(self, capsys):
        """CLI rejects manifests that would violate the temptations schema cap."""
        from maid_runner.cli.commands.manifest import cmd_manifest

        args = argparse.Namespace(
            manifest_command="create",
            file_path="src/example.py",
            goal="Add example",
            task_type="feature",
            artifacts='[{"kind": "function", "name": "example_func"}]',
            temptations=[
                f"Do not take shortcut {i}.::Use procedure {i}."
                for i in range(6)
            ],
            dry_run=True,
            json=True,
        )

        exit_code = cmd_manifest(args)

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "at most five" in captured.err.lower()


class TestCmdManifestViaCLI:
    def test_manifest_create_dry_run_via_main(self, capsys):
        """maid manifest create --dry-run routes correctly through CLI."""
        from maid_runner.cli.commands._main import main

        exit_code = main(
            [
                "manifest",
                "create",
                "src/app.py",
                "--goal",
                "Add app module",
                "--artifacts",
                '[{"kind": "function", "name": "run_app"}]',
                "--temptation",
                "Do not import private helpers.::Test through public API.",
                "--dry-run",
                "--json",
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["goal"] == "Add app module"
        assert data["temptations"][0]["instead"] == "Test through public API."
        assert data["files"]["create"][0]["path"] == "src/app.py"

    def test_manifest_no_subcommand_via_main(self, capsys):
        """maid manifest with no subcommand returns exit code 2."""
        from maid_runner.cli.commands._main import main

        exit_code = main(["manifest"])

        assert exit_code == 2
