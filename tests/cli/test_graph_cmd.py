"""Tests for CLI 'maid graph' command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


class TestCmdGraphNoCommand:
    def test_no_graph_command_attribute_returns_2(self, capsys):
        """When args lacks graph_command attribute, returns exit code 2."""
        from maid_runner.cli.commands.graph import cmd_graph

        args = argparse.Namespace()
        exit_code = cmd_graph(args)

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "usage" in captured.err.lower()

    def test_empty_graph_command_returns_2(self, capsys):
        """When graph_command is empty string, returns exit code 2."""
        from maid_runner.cli.commands.graph import cmd_graph

        args = argparse.Namespace(graph_command="")
        exit_code = cmd_graph(args)

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "usage" in captured.err.lower()

    def test_none_graph_command_returns_2(self, capsys):
        """When graph_command is None, returns exit code 2."""
        from maid_runner.cli.commands.graph import cmd_graph

        args = argparse.Namespace(graph_command=None)
        exit_code = cmd_graph(args)

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "usage" in captured.err.lower()


class TestCmdGraphImplemented:
    def test_query_command_returns_json_results(self, capsys, tmp_path: Path):
        """Graph query emits deterministic JSON consumable by external tools."""
        from maid_runner.cli.commands.graph import cmd_graph

        manifest_dir = _write_manifest(tmp_path)
        args = argparse.Namespace(
            graph_command="query",
            manifest_dir=str(manifest_dir),
            question="what defines CliService",
            json=True,
        )
        exit_code = cmd_graph(args)

        assert exit_code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is True
        assert payload["query_type"] == "find_definition"
        assert (
            payload["results"]["node"]["id"]
            == "artifact:src/cli_service.py:class:CliService"
        )
        assert payload["stats"]["nodes"] >= 3

    def test_export_command_writes_dot_file(self, capsys, tmp_path: Path):
        """Graph export writes an existing graph package format."""
        from maid_runner.cli.commands.graph import cmd_graph

        manifest_dir = _write_manifest(tmp_path)
        output_path = tmp_path / "graph.dot"
        args = argparse.Namespace(
            graph_command="export",
            manifest_dir=str(manifest_dir),
            format="dot",
            output=str(output_path),
        )
        exit_code = cmd_graph(args)

        assert exit_code == 0
        assert output_path.read_text(encoding="utf-8").startswith("digraph G")
        assert str(output_path) in capsys.readouterr().out

    def test_analyze_command_returns_json_file_dependencies(
        self, capsys, tmp_path: Path
    ):
        """Graph analyze reports file dependencies and graph stats."""
        from maid_runner.cli.commands.graph import cmd_graph

        manifest_dir = _write_manifest(tmp_path)
        args = argparse.Namespace(
            graph_command="analyze",
            manifest_dir=str(manifest_dir),
            file_path="src/cli_service.py",
            json=True,
        )
        exit_code = cmd_graph(args)

        assert exit_code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["file"] == "src/cli_service.py"
        assert payload["manifests"] == ["manifest:add-cli-service"]
        assert payload["artifacts"] == ["CliService", "handle"]
        assert payload["stats"]["edge_types"]["creates"] == 1


class TestCmdGraphViaCLI:
    def test_graph_no_subcommand_via_main(self, capsys):
        """maid graph with no subcommand returns exit code 2."""
        from maid_runner.cli.commands._main import main

        exit_code = main(["graph"])

        assert exit_code == 2

    def test_graph_query_via_main_accepts_manifest_dir_before_subcommand(
        self, capsys, tmp_path: Path
    ):
        """maid graph query works through the top-level parser."""
        from maid_runner.cli.commands._main import main

        manifest_dir = _write_manifest(tmp_path)

        exit_code = main(
            [
                "graph",
                "--manifest-dir",
                str(manifest_dir),
                "query",
                "what defines CliService",
                "--json",
            ]
        )

        assert exit_code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["results"]["node"]["name"] == "CliService"


def _write_manifest(tmp_path: Path) -> Path:
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    data = {
        "schema": "2",
        "goal": "Add CLI graph service",
        "type": "feature",
        "created": "2026-05-31T00:00:00+00:00",
        "files": {
            "create": [
                {
                    "path": "src/cli_service.py",
                    "artifacts": [
                        {"kind": "class", "name": "CliService"},
                        {
                            "kind": "method",
                            "name": "handle",
                            "of": "CliService",
                            "args": [],
                            "returns": "None",
                        },
                    ],
                }
            ],
        },
        "validate": ["uv run python -m pytest -q tests/cli/test_graph_cmd.py"],
    }
    (manifest_dir / "add-cli-service.manifest.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8",
    )
    return manifest_dir
