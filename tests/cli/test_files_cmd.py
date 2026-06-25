"""Tests for CLI 'maid files' and 'maid manifests' commands (v2)."""

from __future__ import annotations

import json
import os
import textwrap

import pytest
import yaml


@pytest.fixture
def project_with_files(tmp_path):
    """Create a project with manifests and source files."""
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


class TestCmdManifests:
    def test_manifests_for_file_found(self, project_with_files, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_with_files)
        exit_code = main(["manifests", "src/greet.py"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "add-greet" in captured.out

    def test_manifests_for_file_not_found(self, project_with_files, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_with_files)
        exit_code = main(["manifests", "src/nonexistent.py"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "No manifests" in captured.out

    def test_manifests_json_output(self, project_with_files, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_with_files)
        exit_code = main(["manifests", "src/greet.py", "--json"])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) >= 1
        assert data[0]["slug"] == "add-greet"

    def test_manifests_quiet_shows_paths(self, project_with_files, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_with_files)
        exit_code = main(["manifests", "src/greet.py", "--quiet"])
        assert exit_code == 0


class TestCmdFiles:
    def test_files_command_handlers_are_directly_importable(self):
        from maid_runner.cli.commands.files import cmd_files, cmd_manifests

        assert callable(cmd_files)
        assert callable(cmd_manifests)

    def test_files_shows_tracking(self, project_with_files, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_with_files)
        exit_code = main(["files"])
        assert exit_code == 0

    def test_files_fail_on_undeclared_returns_1(self, project_with_files, capsys):
        from maid_runner.cli.commands._main import main

        (project_with_files / "src" / "extra.py").write_text(
            "def extra():\n    return 'drift'\n"
        )

        os.chdir(project_with_files)
        exit_code = main(["files", "--fail-on", "undeclared"])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "src/extra.py" in captured.out

        repeated_exit_code = main(
            ["files", "--fail-on", "registered", "--fail-on", "undeclared"]
        )
        assert repeated_exit_code == 1
        repeated_output = capsys.readouterr().out
        assert "src/extra.py" in repeated_output

        any_exit_code = main(["files", "--fail-on", "any"])
        assert any_exit_code == 1
        any_output = capsys.readouterr().out
        assert "src/extra.py" in any_output

    def test_files_fail_on_registered_returns_1_for_read_only_production_file(
        self, project_with_files, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_path = project_with_files / "manifests" / "add-greet.manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text())
        manifest["files"]["read"] = ["src/dep.py"]
        manifest_path.write_text(yaml.dump(manifest))
        (project_with_files / "src" / "dep.py").write_text(
            "def helper():\n    return 'registered'\n"
        )

        os.chdir(project_with_files)
        exit_code = main(["files", "--fail-on", "registered"])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "src/dep.py" in captured.out

    def test_files_registered_gate_ignores_scope_only_source_file(
        self, project_with_files, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_path = project_with_files / "manifests" / "add-greet.manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text())
        manifest["files"]["scope"] = [
            {
                "path": "src/routes/settings/+page.svelte",
                "reason": "Route-local state is covered through route tests.",
            }
        ]
        manifest_path.write_text(yaml.dump(manifest))
        route = project_with_files / "src" / "routes" / "settings" / "+page.svelte"
        route.parent.mkdir(parents=True, exist_ok=True)
        route.write_text('<script lang="ts">let selected = "tl";</script>\n')

        os.chdir(project_with_files)
        registered_exit_code = main(["files", "--fail-on", "registered"])
        registered_output = capsys.readouterr().out
        any_exit_code = main(["files", "--fail-on", "any"])
        any_output = capsys.readouterr().out

        assert registered_exit_code == 0
        assert any_exit_code == 0
        assert "src/routes/settings/+page.svelte" in registered_output
        assert "src/routes/settings/+page.svelte" in any_output
        assert "Registered" not in registered_output
        assert "Registered" not in any_output

    def test_files_json_output(self, project_with_files, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_with_files)
        exit_code = main(["files", "--json"])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "tracked" in data or "undeclared" in data or "registered" in data

    def test_files_nonexistent_dir_returns_2(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(tmp_path)
        exit_code = main(["files", "--manifest-dir", "nonexistent/"])
        assert exit_code == 2
