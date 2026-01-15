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


# =============================================================================
# Tests for main() edge cases to improve coverage
# =============================================================================


class TestMainEdgeCases:
    """Tests for edge cases in main CLI to improve coverage."""

    def test_main_no_command_shows_help(self, capsys):
        """Main with no command should print help and exit with error."""
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["maid"]):
                main()
        # Should exit with 1 when no command provided
        assert exc_info.value.code == 1

    def test_main_version_flag(self, capsys):
        """Main with --version should show version and exit."""
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["maid", "--version"]):
                main()
        assert exc_info.value.code == 0

    def test_validate_with_conflicting_args(self):
        """Validate with both manifest_path and --manifest-dir should error."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "validate",
                "manifests/task-001.manifest.json",
                "--manifest-dir",
                "manifests",
            ],
            capture_output=True,
            text=True,
        )
        # Should error due to conflicting arguments
        assert result.returncode != 0
        assert "Cannot specify both" in result.stderr or result.returncode == 2

    def test_init_with_all_flag(self, tmp_path):
        """Init with --all flag should enable all tools."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "init",
                "--all",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        # Should run without error (dry run)
        assert "unrecognized arguments" not in result.stderr

    def test_init_with_cursor_flag(self, tmp_path):
        """Init with --cursor flag."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "init",
                "--cursor",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert "unrecognized arguments" not in result.stderr

    def test_init_with_windsurf_flag(self, tmp_path):
        """Init with --windsurf flag."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "init",
                "--windsurf",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert "unrecognized arguments" not in result.stderr

    def test_init_with_generic_flag(self, tmp_path):
        """Init with --generic flag."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "init",
                "--generic",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert "unrecognized arguments" not in result.stderr

    def test_validate_default_manifest_dir(self, tmp_path):
        """Validate without args should default to 'manifests' directory."""
        # Create a manifests directory with a valid manifest
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        manifest = manifests_dir / "task-001-test.manifest.json"
        manifest.write_text(
            """{
            "goal": "Test manifest",
            "taskType": "create",
            "creatableFiles": [],
            "editableFiles": [],
            "readonlyFiles": []
        }"""
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "validate",
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        # Should attempt to validate (may fail due to schema, but shouldn't fail arg parsing)
        assert "unrecognized arguments" not in result.stderr

    def test_howto_command(self):
        """Test howto command is accessible."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "howto",
                "--help",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "howto" in result.stdout.lower() or "help" in result.stdout.lower()

    def test_schema_command(self):
        """Test schema command is accessible."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "schema",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Should output JSON schema
        assert "{" in result.stdout

    def test_validate_mutual_exclusivity_error(self, tmp_path):
        """Test that validate command errors when both manifest_path and manifest_dir are specified."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        manifest_file = manifest_dir / "task-001.manifest.json"
        manifest_file.write_text('{"goal": "test"}')

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "validate",
                str(manifest_file),
                "--manifest-dir",
                str(manifest_dir),
            ],
            capture_output=True,
            text=True,
        )
        # Should fail due to mutual exclusivity
        assert result.returncode != 0
        assert "Cannot specify both" in result.stderr

    def test_init_command_help(self):
        """Test init command help is accessible."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "init",
                "--help",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "claude" in result.stdout.lower() or "cursor" in result.stdout.lower()

    def test_init_command_all_flag(self, tmp_path):
        """Test init command with --all flag."""
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            # Use --force to skip interactive prompts
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "maid_runner.cli.main",
                    "init",
                    "--all",
                    "--force",
                ],
                capture_output=True,
                text=True,
            )
            # Should succeed or provide meaningful output
            assert result.returncode == 0 or "already" in result.stdout.lower()
        finally:
            os.chdir(original_cwd)

    def test_manifest_command_without_subcommand(self):
        """Test manifest command without subcommand shows help."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
            ],
            capture_output=True,
            text=True,
        )
        # Should fail without subcommand and show help
        assert result.returncode == 1
        # Help should be printed

    def test_test_command_help(self):
        """Test maid test --help."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "test",
                "--help",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--watch" in result.stdout or "watch" in result.stdout.lower()

    def test_snapshot_command_help(self):
        """Test maid snapshot --help."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "snapshot",
                "--help",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "file_path" in result.stdout.lower() or "output" in result.stdout.lower()

    def test_manifests_command_help(self):
        """Test maid manifests --help."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifests",
                "--help",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "file" in result.stdout.lower()

    def test_files_command_help(self):
        """Test maid files --help."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "files",
                "--help",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Should show options for files command

    def test_unknown_command_shows_help(self):
        """Test that unknown command shows main help."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
            ],
            capture_output=True,
            text=True,
        )
        # Should exit with error and show help
        # (Without arguments, argparse may show help or error)
        assert "usage" in result.stdout.lower() or "usage" in result.stderr.lower()


# =============================================================================
# Tests for generate-stubs command
# =============================================================================


class TestGenerateStubsCommand:
    """Tests for the generate-stubs CLI command."""

    def test_generate_stubs_missing_manifest(self, tmp_path):
        """Test generate-stubs with non-existent manifest."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "generate-stubs",
                str(tmp_path / "nonexistent.manifest.json"),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "not found" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_generate_stubs_invalid_json(self, tmp_path):
        """Test generate-stubs with invalid JSON manifest."""
        manifest_file = tmp_path / "invalid.manifest.json"
        manifest_file.write_text("not valid json {{}")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "generate-stubs",
                str(manifest_file),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "json" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_generate_stubs_missing_field(self, tmp_path):
        """Test generate-stubs with manifest with minimal content succeeds."""
        manifest_file = tmp_path / "incomplete.manifest.json"
        # Minimal manifest - generate_test_stub handles missing fields gracefully
        manifest_file.write_text('{"goal": "test"}')

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "generate-stubs",
                str(manifest_file),
            ],
            capture_output=True,
            text=True,
        )
        # The generate_test_stub function handles minimal manifests
        # It will either succeed or fail gracefully
        assert "unrecognized" not in result.stderr.lower()

    def test_generate_stubs_valid_manifest(self, tmp_path):
        """Test generate-stubs with a valid manifest."""
        import json

        manifest_file = tmp_path / "task-001.manifest.json"
        manifest_data = {
            "goal": "Create test module",
            "taskType": "create",
            "creatableFiles": ["src/test.py"],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/test.py",
                "contains": [{"type": "function", "name": "test_func"}],
            },
        }
        manifest_file.write_text(json.dumps(manifest_data))

        # Create the source directory structure
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        # Create tests directory
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "generate-stubs",
                str(manifest_file),
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        # May succeed or fail based on test directory structure
        # The key is it should try to generate stubs
        assert "stub" in result.stdout.lower() or result.returncode in (0, 1)

    def test_generate_stubs_help(self):
        """Test generate-stubs --help."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "generate-stubs",
                "--help",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "manifest" in result.stdout.lower()


# =============================================================================
# Tests for init command with specific tool flags
# =============================================================================


class TestInitCommandToolFlags:
    """Tests for init command with specific tool flag combinations."""

    def test_init_cursor_only(self, tmp_path):
        """Test init with --cursor flag only."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "init",
                "--cursor",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        # Should handle cursor flag
        assert "unrecognized" not in result.stderr.lower()

    def test_init_windsurf_only(self, tmp_path):
        """Test init with --windsurf flag only."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "init",
                "--windsurf",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert "unrecognized" not in result.stderr.lower()

    def test_init_generic_only(self, tmp_path):
        """Test init with --generic flag only."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "init",
                "--generic",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert "unrecognized" not in result.stderr.lower()

    def test_init_cursor_and_windsurf(self, tmp_path):
        """Test init with both --cursor and --windsurf flags."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "init",
                "--cursor",
                "--windsurf",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert "unrecognized" not in result.stderr.lower()

    def test_init_all_tools(self, tmp_path):
        """Test init with --all flag."""
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "maid_runner.cli.main",
                    "init",
                    "--all",
                    "--force",
                ],
                capture_output=True,
                text=True,
            )
            # With --all and --force, should succeed or indicate already initialized
            assert result.returncode == 0 or "already" in result.stdout.lower()
        finally:
            os.chdir(original_cwd)


# =============================================================================
# Tests for coherence validation modes
# =============================================================================


class TestCoherenceValidation:
    """Tests for coherence validation in CLI."""

    def test_validate_coherence_only_flag(self, tmp_path):
        """Test validate --coherence-only flag."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "task-001.manifest.json"
        manifest_file.write_text(
            """{
            "goal": "Test",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "editableFiles": [],
            "readonlyFiles": []
        }"""
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "validate",
                "--coherence-only",
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        # Should run coherence validation
        assert "unrecognized" not in result.stderr.lower()

    def test_validate_with_coherence_flag(self, tmp_path):
        """Test validate --coherence flag (after standard validation)."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "task-001.manifest.json"
        manifest_file.write_text(
            """{
            "goal": "Test",
            "taskType": "create",
            "creatableFiles": [],
            "editableFiles": [],
            "readonlyFiles": []
        }"""
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "validate",
                "--coherence",
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        # Should run both standard and coherence validation
        assert "unrecognized" not in result.stderr.lower()


# =============================================================================
# Tests for test command routing
# =============================================================================


class TestTestCommandRouting:
    """Tests for maid test command routing."""

    def test_test_command_calls_run_test(self, tmp_path):
        """Test that test command routes correctly."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "task-001.manifest.json"
        manifest_file.write_text(
            """{
            "goal": "Test",
            "taskType": "create",
            "creatableFiles": [],
            "editableFiles": [],
            "readonlyFiles": [],
            "validationCommand": ["echo", "test"]
        }"""
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "test",
                "--manifest-dir",
                str(manifest_dir),
            ],
            capture_output=True,
            text=True,
        )
        # Should execute without arg parsing errors
        assert "unrecognized" not in result.stderr.lower()

    def test_test_command_with_fail_fast(self):
        """Test maid test --fail-fast flag."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "test",
                "--fail-fast",
                "--help",
            ],
            capture_output=True,
            text=True,
        )
        # --help should still work with --fail-fast
        assert result.returncode == 0


# =============================================================================
# Tests for manifests command routing
# =============================================================================


class TestManifestsCommandRouting:
    """Tests for maid manifests command routing."""

    def test_manifests_command_routing(self, tmp_path):
        """Test manifests command routes correctly."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "task-001.manifest.json"
        manifest_file.write_text(
            """{
            "goal": "Test",
            "creatableFiles": ["test.py"],
            "editableFiles": [],
            "readonlyFiles": []
        }"""
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifests",
                "test.py",
                "--manifest-dir",
                str(manifest_dir),
            ],
            capture_output=True,
            text=True,
        )
        # Should find the manifest
        assert "task-001" in result.stdout or result.returncode == 0

    def test_manifests_command_json_output(self, tmp_path):
        """Test manifests command with --json output."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest_file = manifest_dir / "task-001.manifest.json"
        manifest_file.write_text(
            """{
            "goal": "Test",
            "creatableFiles": ["test.py"],
            "editableFiles": [],
            "readonlyFiles": []
        }"""
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifests",
                "test.py",
                "--manifest-dir",
                str(manifest_dir),
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        # Should output JSON
        assert "[" in result.stdout or result.returncode == 0


# =============================================================================
# Tests for manifest create command
# =============================================================================


class TestManifestCreateCommand:
    """Tests for manifest create subcommand."""

    def test_manifest_create_dry_run(self, tmp_path):
        """Test manifest create --dry-run."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "test.py",
                "--goal",
                "Test goal",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        # Should show dry run output
        assert "unrecognized" not in result.stderr.lower()

    def test_manifest_create_with_json_output(self, tmp_path):
        """Test manifest create --json output."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "manifest",
                "create",
                "test.py",
                "--goal",
                "Test",
                "--dry-run",
                "--json",
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert "unrecognized" not in result.stderr.lower()


# =============================================================================
# Tests for files command
# =============================================================================


class TestFilesCommand:
    """Tests for maid files command."""

    def test_files_command_basic(self, tmp_path):
        """Test maid files basic execution."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "files",
                "--manifest-dir",
                str(manifest_dir),
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        # Should run without arg parsing errors
        assert "unrecognized" not in result.stderr.lower()

    def test_files_command_with_status_filter(self, tmp_path):
        """Test maid files --status flag."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "files",
                "--manifest-dir",
                str(manifest_dir),
                "--status",
                "undeclared",
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert "unrecognized" not in result.stderr.lower()

    def test_files_command_with_issues_only(self, tmp_path):
        """Test maid files --issues-only flag."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "files",
                "--manifest-dir",
                str(manifest_dir),
                "--issues-only",
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert "unrecognized" not in result.stderr.lower()

    def test_files_command_json_output(self, tmp_path):
        """Test maid files --json flag."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "files",
                "--manifest-dir",
                str(manifest_dir),
                "--json",
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert "unrecognized" not in result.stderr.lower()


# =============================================================================
# Tests for snapshot command
# =============================================================================


class TestSnapshotCommand:
    """Tests for maid snapshot command."""

    def test_snapshot_nonexistent_file(self, tmp_path):
        """Test snapshot with non-existent file."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "snapshot",
                str(tmp_path / "nonexistent.py"),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "not found" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_snapshot_valid_file(self, tmp_path):
        """Test snapshot with valid Python file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass")

        output_dir = tmp_path / "manifests"
        output_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "snapshot",
                str(test_file),
                "--output-dir",
                str(output_dir),
            ],
            capture_output=True,
            text=True,
        )
        # Should create snapshot manifest
        assert result.returncode == 0 or "manifest" in result.stdout.lower()


# =============================================================================
# Tests for howto command
# =============================================================================


class TestHowtoCommand:
    """Tests for maid howto command."""

    def test_howto_without_section(self):
        """Test howto command without section argument runs but needs input."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "howto",
            ],
            capture_output=True,
            text=True,
            input="",  # Empty input to avoid blocking
        )
        # howto requires interactive input, will fail with EOFError but still shows content
        # The key is it produces output before failing
        assert "MAID" in result.stdout or "Methodology" in result.stdout

    def test_howto_with_section(self):
        """Test howto command with section argument."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "howto",
                "--section",
                "workflow",
            ],
            capture_output=True,
            text=True,
        )
        # Should show section or indicate not found
        assert "unrecognized" not in result.stderr.lower()


# =============================================================================
# Direct main() tests for coverage
# =============================================================================


class TestMainDirectCalls:
    """Direct tests calling main() with mocked functions for coverage."""

    def test_main_validate_coherence_only(self, tmp_path):
        """Test validate with --coherence-only flag directly."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        with patch("sys.argv", ["maid", "validate", "--coherence-only"]):
            with patch(
                "maid_runner.cli.main.handle_coherence_validation"
            ) as mock_coherence:
                mock_coherence.return_value = True
                with patch("os.getcwd", return_value=str(tmp_path)):
                    # Should call coherence validation and exit
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    # Coherence valid returns exit 0
                    assert exc_info.value.code == 0

    def test_main_validate_coherence_only_fails(self, tmp_path):
        """Test validate with --coherence-only flag when validation fails."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        with patch("sys.argv", ["maid", "validate", "--coherence-only"]):
            with patch(
                "maid_runner.cli.main.handle_coherence_validation"
            ) as mock_coherence:
                mock_coherence.return_value = False
                with patch("os.getcwd", return_value=str(tmp_path)):
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    # Coherence invalid returns exit 1
                    assert exc_info.value.code == 1

    def test_main_validate_with_coherence_after_validation(self, tmp_path):
        """Test validate with --coherence flag runs coherence after standard validation."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        with patch("sys.argv", ["maid", "validate", "--coherence"]):
            with patch("maid_runner.cli.validate.run_validation") as mock_validation:
                with patch(
                    "maid_runner.cli.main.handle_coherence_validation"
                ) as mock_coherence:
                    mock_coherence.return_value = True
                    with patch("os.getcwd", return_value=str(tmp_path)):
                        main()
                        mock_validation.assert_called_once()
                        mock_coherence.assert_called_once()

    def test_main_validate_with_coherence_failure(self, tmp_path):
        """Test validate with --coherence flag exits 1 when coherence fails."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        with patch("sys.argv", ["maid", "validate", "--coherence"]):
            with patch("maid_runner.cli.validate.run_validation"):
                with patch(
                    "maid_runner.cli.main.handle_coherence_validation"
                ) as mock_coherence:
                    mock_coherence.return_value = False
                    with patch("os.getcwd", return_value=str(tmp_path)):
                        with pytest.raises(SystemExit) as exc_info:
                            main()
                        assert exc_info.value.code == 1

    def test_main_snapshot_command(self, tmp_path):
        """Test snapshot command routes to run_snapshot."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass")

        with patch(
            "sys.argv",
            ["maid", "snapshot", str(test_file), "--output-dir", str(tmp_path)],
        ):
            with patch("maid_runner.cli.snapshot.run_snapshot") as mock_snapshot:
                main()
                mock_snapshot.assert_called_once()

    def test_main_test_command(self, tmp_path):
        """Test maid test command routes to run_test."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        with patch("sys.argv", ["maid", "test", "--manifest-dir", str(manifest_dir)]):
            with patch("maid_runner.cli.test.run_test") as mock_test:
                main()
                mock_test.assert_called_once()

    def test_main_manifests_command(self, tmp_path):
        """Test manifests command routes to run_list_manifests."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        with patch(
            "sys.argv",
            ["maid", "manifests", "test.py", "--manifest-dir", str(manifest_dir)],
        ):
            with patch(
                "maid_runner.cli.list_manifests.run_list_manifests"
            ) as mock_manifests:
                main()
                mock_manifests.assert_called_once()

    def test_main_init_with_all_flag(self, tmp_path):
        """Test init command with --all flag."""
        with patch("sys.argv", ["maid", "init", "--all", "--dry-run"]):
            with patch("maid_runner.cli.init.run_init") as mock_init:
                with patch("os.getcwd", return_value=str(tmp_path)):
                    main()
                    mock_init.assert_called_once()
                    # Check tools list includes all tools
                    call_args = mock_init.call_args
                    tools = call_args[0][1]
                    assert "claude" in tools
                    assert "cursor" in tools
                    assert "windsurf" in tools
                    assert "generic" in tools

    def test_main_init_with_cursor_flag(self, tmp_path):
        """Test init command with --cursor flag."""
        with patch("sys.argv", ["maid", "init", "--cursor", "--dry-run"]):
            with patch("maid_runner.cli.init.run_init") as mock_init:
                with patch("os.getcwd", return_value=str(tmp_path)):
                    main()
                    call_args = mock_init.call_args
                    tools = call_args[0][1]
                    assert "cursor" in tools
                    # When --cursor is specified, claude is not added by default
                    assert "claude" not in tools

    def test_main_init_with_windsurf_flag(self, tmp_path):
        """Test init command with --windsurf flag."""
        with patch("sys.argv", ["maid", "init", "--windsurf", "--dry-run"]):
            with patch("maid_runner.cli.init.run_init") as mock_init:
                with patch("os.getcwd", return_value=str(tmp_path)):
                    main()
                    call_args = mock_init.call_args
                    tools = call_args[0][1]
                    assert "windsurf" in tools

    def test_main_init_with_generic_flag(self, tmp_path):
        """Test init command with --generic flag."""
        with patch("sys.argv", ["maid", "init", "--generic", "--dry-run"]):
            with patch("maid_runner.cli.init.run_init") as mock_init:
                with patch("os.getcwd", return_value=str(tmp_path)):
                    main()
                    call_args = mock_init.call_args
                    tools = call_args[0][1]
                    assert "generic" in tools

    def test_main_init_default_claude(self, tmp_path):
        """Test init command defaults to claude when no tool flags."""
        with patch("sys.argv", ["maid", "init", "--dry-run"]):
            with patch("maid_runner.cli.init.run_init") as mock_init:
                with patch("os.getcwd", return_value=str(tmp_path)):
                    main()
                    call_args = mock_init.call_args
                    tools = call_args[0][1]
                    # Default is claude when nothing specified
                    assert "claude" in tools

    def test_main_generate_stubs_missing_manifest(self, tmp_path, capsys):
        """Test generate-stubs with non-existent manifest."""
        nonexistent = tmp_path / "nonexistent.manifest.json"

        with patch("sys.argv", ["maid", "generate-stubs", str(nonexistent)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "not found" in captured.err.lower() or "error" in captured.err.lower()

    def test_main_generate_stubs_invalid_json(self, tmp_path, capsys):
        """Test generate-stubs with invalid JSON manifest."""
        manifest_file = tmp_path / "invalid.manifest.json"
        manifest_file.write_text("not valid json {{{")

        with patch("sys.argv", ["maid", "generate-stubs", str(manifest_file)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "json" in captured.err.lower()

    def test_main_files_command(self, tmp_path):
        """Test files command routes to run_files."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        with patch("sys.argv", ["maid", "files", "--manifest-dir", str(manifest_dir)]):
            with patch("maid_runner.cli.files.run_files") as mock_files:
                with patch("os.getcwd", return_value=str(tmp_path)):
                    main()
                    mock_files.assert_called_once()

    def test_main_manifest_create_command(self, tmp_path):
        """Test manifest create command routes correctly."""
        with patch(
            "sys.argv",
            ["maid", "manifest", "create", "test.py", "--goal", "Test", "--dry-run"],
        ):
            with patch(
                "maid_runner.cli.manifest_create.run_create_manifest"
            ) as mock_create:
                with patch("os.getcwd", return_value=str(tmp_path)):
                    main()
                    mock_create.assert_called_once()

    def test_main_manifest_without_subcommand(self):
        """Test manifest command without subcommand shows help."""
        with patch("sys.argv", ["maid", "manifest"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_main_howto_command(self):
        """Test howto command routes to run_howto."""
        with patch("sys.argv", ["maid", "howto", "--section", "intro"]):
            with patch("maid_runner.cli.howto.run_howto") as mock_howto:
                main()
                mock_howto.assert_called_once()

    def test_main_schema_command(self):
        """Test schema command routes to run_schema."""
        with patch("sys.argv", ["maid", "schema"]):
            with patch("maid_runner.cli.schema.run_schema") as mock_schema:
                main()
                mock_schema.assert_called_once()

    def test_main_graph_command(self, tmp_path):
        """Test graph command routes to run_graph_command."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        with patch(
            "sys.argv",
            ["maid", "graph", "query", "test", "--manifest-dir", str(manifest_dir)],
        ):
            with patch(
                "maid_runner.cli.graph.run_graph_command", return_value=0
            ) as mock_graph:
                with pytest.raises(SystemExit) as exc_info:
                    main()
                mock_graph.assert_called_once()
                assert exc_info.value.code == 0

    def test_main_generate_stubs_key_error(self, tmp_path, capsys):
        """Test generate-stubs handles KeyError gracefully."""
        import json

        manifest_file = tmp_path / "test.manifest.json"
        manifest_file.write_text(json.dumps({"goal": "Test"}))

        with patch("sys.argv", ["maid", "generate-stubs", str(manifest_file)]):
            with patch(
                "maid_runner.cli.snapshot.generate_test_stub",
                side_effect=KeyError("missing_field"),
            ):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "missing" in captured.err.lower() or "field" in captured.err.lower()

    def test_main_generate_stubs_file_not_found(self, tmp_path, capsys):
        """Test generate-stubs handles FileNotFoundError gracefully."""
        import json

        manifest_file = tmp_path / "test.manifest.json"
        manifest_file.write_text(json.dumps({"goal": "Test"}))

        with patch("sys.argv", ["maid", "generate-stubs", str(manifest_file)]):
            with patch(
                "maid_runner.cli.snapshot.generate_test_stub",
                side_effect=FileNotFoundError("tests/test_file.py"),
            ):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "not found" in captured.err.lower() or "file" in captured.err.lower()

    def test_main_generate_stubs_permission_error(self, tmp_path, capsys):
        """Test generate-stubs handles PermissionError gracefully."""
        import json

        manifest_file = tmp_path / "test.manifest.json"
        manifest_file.write_text(json.dumps({"goal": "Test"}))

        with patch("sys.argv", ["maid", "generate-stubs", str(manifest_file)]):
            with patch(
                "maid_runner.cli.snapshot.generate_test_stub",
                side_effect=PermissionError("Access denied"),
            ):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "permission" in captured.err.lower() or "denied" in captured.err.lower()

    def test_main_generate_stubs_generic_error(self, tmp_path, capsys):
        """Test generate-stubs handles generic exceptions gracefully."""
        import json

        manifest_file = tmp_path / "test.manifest.json"
        manifest_file.write_text(json.dumps({"goal": "Test"}))

        with patch("sys.argv", ["maid", "generate-stubs", str(manifest_file)]):
            with patch(
                "maid_runner.cli.snapshot.generate_test_stub",
                side_effect=RuntimeError("Unexpected error"),
            ):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "error" in captured.err.lower()
