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
    def test_files_shows_tracking(self, project_with_files, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_with_files)
        exit_code = main(["files"])
        assert exit_code == 0

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
