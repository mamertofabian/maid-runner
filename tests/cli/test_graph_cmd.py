"""Tests for CLI 'maid graph' command."""

from __future__ import annotations

import argparse


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


class TestCmdGraphNotImplemented:
    def test_query_command_returns_not_implemented(self, capsys):
        """Graph module exists but commands are not yet implemented."""
        from maid_runner.cli.commands.graph import cmd_graph

        args = argparse.Namespace(graph_command="query")
        exit_code = cmd_graph(args)

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "not yet implemented" in captured.err.lower()

    def test_export_command_returns_not_implemented(self, capsys):
        """Export subcommand also returns not-implemented."""
        from maid_runner.cli.commands.graph import cmd_graph

        args = argparse.Namespace(graph_command="export")
        exit_code = cmd_graph(args)

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "not yet implemented" in captured.err.lower()

    def test_analyze_command_returns_not_implemented(self, capsys):
        """Analyze subcommand also returns not-implemented."""
        from maid_runner.cli.commands.graph import cmd_graph

        args = argparse.Namespace(graph_command="analyze")
        exit_code = cmd_graph(args)

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "not yet implemented" in captured.err.lower()


class TestCmdGraphViaCLI:
    def test_graph_no_subcommand_via_main(self, capsys):
        """maid graph with no subcommand returns exit code 2."""
        from maid_runner.cli.commands._main import main

        exit_code = main(["graph"])

        assert exit_code == 2
