"""Behavioral tests for task-118: CLI Main Integration for graph subcommand.

These tests verify that the setup_graph_parser function properly configures
the graph subparser with all required subcommands (query, export, analysis)
and their respective arguments.

Tests focus on:
1. The setup_graph_parser function exists and is callable
2. It adds a "graph" subparser to the main parser
3. The graph subparser has nested subcommands: query, export, analysis
4. Each subcommand has correct arguments with proper types and defaults
5. Integration with run_graph_command from maid_runner.cli.graph
"""

import argparse
import subprocess
import sys
from unittest.mock import patch

import pytest

from maid_runner.cli.main import main, setup_graph_parser


# =============================================================================
# Tests for main function (CLI entry point)
# =============================================================================


class TestMainFunction:
    """Tests for the main CLI entry point function."""

    def test_main_exists(self):
        """The main function should exist."""
        assert main is not None

    def test_main_is_callable(self):
        """The main function should be callable."""
        assert callable(main)

    def test_main_with_help_flag(self):
        """The main function should handle --help flag."""
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["maid", "--help"]):
                main()
        # --help exits with 0
        assert exc_info.value.code == 0

    def test_main_with_graph_help(self):
        """The main function should handle graph --help."""
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["maid", "graph", "--help"]):
                main()
        assert exc_info.value.code == 0


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def main_parser():
    """Create a main parser with subparsers for testing."""
    parser = argparse.ArgumentParser(prog="maid")
    subparsers = parser.add_subparsers(dest="command")
    return parser, subparsers


@pytest.fixture
def configured_parser(main_parser):
    """Create a parser with setup_graph_parser already called."""
    parser, subparsers = main_parser
    setup_graph_parser(subparsers)
    return parser


# =============================================================================
# Tests for setup_graph_parser function existence and signature
# =============================================================================


class TestSetupGraphParserFunction:
    """Verify setup_graph_parser function exists and has correct signature."""

    def test_function_exists(self):
        """Verify setup_graph_parser is importable from maid_runner.cli.main."""
        from maid_runner.cli.main import setup_graph_parser

        assert setup_graph_parser is not None

    def test_function_is_callable(self):
        """Verify setup_graph_parser is callable."""
        assert callable(setup_graph_parser)

    def test_accepts_subparsers_argument(self, main_parser):
        """Verify setup_graph_parser accepts subparsers argument."""
        parser, subparsers = main_parser
        # Should not raise
        setup_graph_parser(subparsers)

    def test_returns_none(self, main_parser):
        """Verify setup_graph_parser returns None."""
        parser, subparsers = main_parser
        result = setup_graph_parser(subparsers)
        assert result is None


# =============================================================================
# Tests for graph subparser registration
# =============================================================================


class TestGraphSubparserRegistration:
    """Verify graph subparser is properly registered."""

    def test_graph_command_registered(self, configured_parser):
        """Verify 'graph' is registered as a subcommand."""
        # Parse just "graph" - should not raise
        # Note: This will fail if graph is not registered
        try:
            configured_parser.parse_args(["graph", "--help"])
        except SystemExit as e:
            # --help causes SystemExit(0) which is expected
            assert e.code == 0

    def test_graph_help_shows_subcommands(self, configured_parser, capsys):
        """Verify graph help shows available subcommands."""
        with pytest.raises(SystemExit) as exc_info:
            configured_parser.parse_args(["graph", "--help"])
        assert exc_info.value.code == 0

        captured = capsys.readouterr()
        # Should mention subcommands in help output
        assert "query" in captured.out or "export" in captured.out


# =============================================================================
# Tests for query subcommand
# =============================================================================


class TestQuerySubcommand:
    """Verify query subcommand is properly configured."""

    def test_query_subcommand_exists(self, configured_parser):
        """Verify 'graph query' is a valid command."""
        with pytest.raises(SystemExit) as exc_info:
            configured_parser.parse_args(["graph", "query", "--help"])
        assert exc_info.value.code == 0

    def test_query_accepts_positional_query_argument(self, configured_parser):
        """Verify query subcommand accepts a positional query argument."""
        args = configured_parser.parse_args(["graph", "query", "What defines X?"])
        assert hasattr(args, "query")
        assert args.query == "What defines X?"

    def test_query_has_manifest_dir_option(self, configured_parser):
        """Verify query subcommand has --manifest-dir option."""
        args = configured_parser.parse_args(
            ["graph", "query", "test query", "--manifest-dir", "custom/path"]
        )
        assert hasattr(args, "manifest_dir")
        assert args.manifest_dir == "custom/path"

    def test_query_manifest_dir_default_value(self, configured_parser):
        """Verify --manifest-dir defaults to 'manifests'."""
        args = configured_parser.parse_args(["graph", "query", "test query"])
        assert args.manifest_dir == "manifests"

    def test_query_requires_query_argument(self, configured_parser):
        """Verify query subcommand requires the query argument."""
        with pytest.raises(SystemExit) as exc_info:
            configured_parser.parse_args(["graph", "query"])
        # Should fail due to missing required argument
        assert exc_info.value.code != 0


# =============================================================================
# Tests for export subcommand
# =============================================================================


class TestExportSubcommand:
    """Verify export subcommand is properly configured."""

    def test_export_subcommand_exists(self, configured_parser):
        """Verify 'graph export' is a valid command."""
        with pytest.raises(SystemExit) as exc_info:
            configured_parser.parse_args(["graph", "export", "--help"])
        assert exc_info.value.code == 0

    def test_export_has_format_option(self, configured_parser):
        """Verify export subcommand has --format option."""
        args = configured_parser.parse_args(
            ["graph", "export", "--format", "json", "--output", "out.json"]
        )
        assert hasattr(args, "format")
        assert args.format == "json"

    def test_export_format_accepts_json(self, configured_parser):
        """Verify --format accepts 'json' choice."""
        args = configured_parser.parse_args(
            ["graph", "export", "--format", "json", "--output", "out.json"]
        )
        assert args.format == "json"

    def test_export_format_accepts_dot(self, configured_parser):
        """Verify --format accepts 'dot' choice."""
        args = configured_parser.parse_args(
            ["graph", "export", "--format", "dot", "--output", "out.dot"]
        )
        assert args.format == "dot"

    def test_export_format_accepts_graphml(self, configured_parser):
        """Verify --format accepts 'graphml' choice."""
        args = configured_parser.parse_args(
            ["graph", "export", "--format", "graphml", "--output", "out.graphml"]
        )
        assert args.format == "graphml"

    def test_export_format_rejects_invalid_choice(self, configured_parser):
        """Verify --format rejects invalid choices."""
        with pytest.raises(SystemExit) as exc_info:
            configured_parser.parse_args(
                ["graph", "export", "--format", "invalid", "--output", "out.txt"]
            )
        assert exc_info.value.code != 0

    def test_export_has_output_option(self, configured_parser):
        """Verify export subcommand has --output option."""
        args = configured_parser.parse_args(
            ["graph", "export", "--format", "json", "--output", "graph.json"]
        )
        assert hasattr(args, "output")
        assert args.output == "graph.json"

    def test_export_output_is_required(self, configured_parser):
        """Verify --output is required for export."""
        with pytest.raises(SystemExit) as exc_info:
            configured_parser.parse_args(["graph", "export", "--format", "json"])
        # Should fail due to missing required --output
        assert exc_info.value.code != 0

    def test_export_has_manifest_dir_option(self, configured_parser):
        """Verify export subcommand has --manifest-dir option."""
        args = configured_parser.parse_args(
            [
                "graph",
                "export",
                "--format",
                "json",
                "--output",
                "out.json",
                "--manifest-dir",
                "custom/path",
            ]
        )
        assert hasattr(args, "manifest_dir")
        assert args.manifest_dir == "custom/path"

    def test_export_manifest_dir_default_value(self, configured_parser):
        """Verify export --manifest-dir defaults to 'manifests'."""
        args = configured_parser.parse_args(
            ["graph", "export", "--format", "json", "--output", "out.json"]
        )
        assert args.manifest_dir == "manifests"


# =============================================================================
# Tests for analysis subcommand
# =============================================================================


class TestAnalysisSubcommand:
    """Verify analysis subcommand is properly configured."""

    def test_analysis_subcommand_exists(self, configured_parser):
        """Verify 'graph analysis' is a valid command."""
        with pytest.raises(SystemExit) as exc_info:
            configured_parser.parse_args(["graph", "analysis", "--help"])
        assert exc_info.value.code == 0

    def test_analysis_has_type_option(self, configured_parser):
        """Verify analysis subcommand has --type option."""
        args = configured_parser.parse_args(
            ["graph", "analysis", "--type", "find-cycles"]
        )
        assert hasattr(args, "analysis_type")
        assert args.analysis_type == "find-cycles"

    def test_analysis_type_accepts_find_cycles(self, configured_parser):
        """Verify --type accepts 'find-cycles' choice."""
        args = configured_parser.parse_args(
            ["graph", "analysis", "--type", "find-cycles"]
        )
        assert args.analysis_type == "find-cycles"

    def test_analysis_type_accepts_show_stats(self, configured_parser):
        """Verify --type accepts 'show-stats' choice."""
        args = configured_parser.parse_args(
            ["graph", "analysis", "--type", "show-stats"]
        )
        assert args.analysis_type == "show-stats"

    def test_analysis_type_rejects_invalid_choice(self, configured_parser):
        """Verify --type rejects invalid choices."""
        with pytest.raises(SystemExit) as exc_info:
            configured_parser.parse_args(
                ["graph", "analysis", "--type", "invalid-type"]
            )
        assert exc_info.value.code != 0

    def test_analysis_has_manifest_dir_option(self, configured_parser):
        """Verify analysis subcommand has --manifest-dir option."""
        args = configured_parser.parse_args(
            [
                "graph",
                "analysis",
                "--type",
                "find-cycles",
                "--manifest-dir",
                "custom/path",
            ]
        )
        assert hasattr(args, "manifest_dir")
        assert args.manifest_dir == "custom/path"

    def test_analysis_manifest_dir_default_value(self, configured_parser):
        """Verify analysis --manifest-dir defaults to 'manifests'."""
        args = configured_parser.parse_args(
            ["graph", "analysis", "--type", "find-cycles"]
        )
        assert args.manifest_dir == "manifests"


# =============================================================================
# Integration tests - parsing complete commands
# =============================================================================


class TestCommandParsing:
    """Integration tests for parsing complete commands."""

    def test_parse_graph_query_command(self, configured_parser):
        """Verify 'maid graph query \"test query\"' parses correctly."""
        args = configured_parser.parse_args(["graph", "query", "test query"])

        assert args.command == "graph"
        assert args.subcommand == "query"
        assert args.query == "test query"
        assert args.manifest_dir == "manifests"

    def test_parse_graph_export_json_command(self, configured_parser):
        """Verify 'maid graph export --format json --output graph.json' parses correctly."""
        args = configured_parser.parse_args(
            ["graph", "export", "--format", "json", "--output", "graph.json"]
        )

        assert args.command == "graph"
        assert args.subcommand == "export"
        assert args.format == "json"
        assert args.output == "graph.json"
        assert args.manifest_dir == "manifests"

    def test_parse_graph_analysis_find_cycles_command(self, configured_parser):
        """Verify 'maid graph analysis --type find-cycles' parses correctly."""
        args = configured_parser.parse_args(
            ["graph", "analysis", "--type", "find-cycles"]
        )

        assert args.command == "graph"
        assert args.subcommand == "analysis"
        assert args.analysis_type == "find-cycles"
        assert args.manifest_dir == "manifests"

    def test_parse_query_with_custom_manifest_dir(self, configured_parser):
        """Verify query with custom manifest-dir parses correctly."""
        args = configured_parser.parse_args(
            ["graph", "query", "find cycles", "--manifest-dir", "/custom/manifests"]
        )

        assert args.query == "find cycles"
        assert args.manifest_dir == "/custom/manifests"

    def test_parse_export_with_all_options(self, configured_parser):
        """Verify export with all options parses correctly."""
        args = configured_parser.parse_args(
            [
                "graph",
                "export",
                "--format",
                "graphml",
                "--output",
                "/tmp/graph.graphml",
                "--manifest-dir",
                "/custom/manifests",
            ]
        )

        assert args.format == "graphml"
        assert args.output == "/tmp/graph.graphml"
        assert args.manifest_dir == "/custom/manifests"


# =============================================================================
# Integration tests - routing to run_graph_command
# =============================================================================


class TestGraphCommandRouting:
    """Test that graph command routes to run_graph_command from maid_runner.cli.graph."""

    def test_graph_command_calls_run_graph_command(self):
        """Verify graph command routes to run_graph_command."""
        with patch("maid_runner.cli.graph.run_graph_command") as mock_run:
            mock_run.return_value = 0

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "maid_runner.cli.main",
                    "graph",
                    "query",
                    "test query",
                ],
                capture_output=True,
                text=True,
            )

            # The command should execute (may fail due to missing manifests,
            # but shouldn't fail due to argparse issues)
            assert "unrecognized arguments" not in result.stderr
            assert "invalid choice" not in result.stderr

    def test_graph_help_accessible(self):
        """Verify 'maid graph --help' works."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "graph",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "graph" in result.stdout.lower()

    def test_graph_query_help_accessible(self):
        """Verify 'maid graph query --help' works."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "graph",
                "query",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "query" in result.stdout.lower() or "manifest" in result.stdout.lower()

    def test_graph_export_help_accessible(self):
        """Verify 'maid graph export --help' works."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "graph",
                "export",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        # Should mention format and output options
        assert "--format" in result.stdout or "--output" in result.stdout

    def test_graph_analysis_help_accessible(self):
        """Verify 'maid graph analysis --help' works."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "graph",
                "analysis",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        # Should mention type option
        assert "--type" in result.stdout or "analysis" in result.stdout.lower()


# =============================================================================
# Tests for CLI via subprocess (end-to-end)
# =============================================================================


class TestCLIEndToEnd:
    """End-to-end tests using subprocess to run the CLI."""

    def test_graph_in_main_help(self):
        """Verify 'graph' appears in main CLI help."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "--help",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "graph" in result.stdout.lower()

    def test_graph_query_parses_successfully(self):
        """Verify graph query command parses without argparse errors."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "graph",
                "query",
                "What defines function_x?",
            ],
            capture_output=True,
            text=True,
        )

        # Should not fail due to argument parsing
        assert "unrecognized arguments" not in result.stderr
        assert "error: argument" not in result.stderr or "query" not in result.stderr

    def test_graph_export_parses_successfully(self):
        """Verify graph export command parses without argparse errors."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "graph",
                "export",
                "--format",
                "json",
                "--output",
                "/tmp/test_graph.json",
            ],
            capture_output=True,
            text=True,
        )

        # Should not fail due to argument parsing
        assert "unrecognized arguments" not in result.stderr

    def test_graph_analysis_parses_successfully(self):
        """Verify graph analysis command parses without argparse errors."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "graph",
                "analysis",
                "--type",
                "find-cycles",
            ],
            capture_output=True,
            text=True,
        )

        # Should not fail due to argument parsing
        assert "unrecognized arguments" not in result.stderr
        assert "invalid choice" not in result.stderr


# =============================================================================
# Tests for subcommand attribute setting
# =============================================================================


class TestSubcommandAttributeSetting:
    """Verify subcommand attribute is set correctly for routing."""

    def test_query_sets_subcommand_attribute(self, configured_parser):
        """Verify query sets subcommand='query' for routing."""
        args = configured_parser.parse_args(["graph", "query", "test"])
        assert hasattr(args, "subcommand")
        assert args.subcommand == "query"

    def test_export_sets_subcommand_attribute(self, configured_parser):
        """Verify export sets subcommand='export' for routing."""
        args = configured_parser.parse_args(
            ["graph", "export", "--format", "json", "--output", "out.json"]
        )
        assert hasattr(args, "subcommand")
        assert args.subcommand == "export"

    def test_analysis_sets_subcommand_attribute(self, configured_parser):
        """Verify analysis sets subcommand='analysis' for routing."""
        args = configured_parser.parse_args(
            ["graph", "analysis", "--type", "find-cycles"]
        )
        assert hasattr(args, "subcommand")
        assert args.subcommand == "analysis"
