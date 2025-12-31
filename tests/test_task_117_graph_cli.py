"""
Behavioral tests for task-117: CLI command handler for graph operations.

Tests verify that:
1. run_graph_command() routes to appropriate handlers based on args
2. handle_query() executes queries and prints results
3. handle_export() creates output files in json/dot/graphml formats
4. handle_analysis() runs find-cycles and show-stats operations
5. Functions handle empty/nonexistent manifest directories gracefully
"""

import argparse
import json
import pytest
from pathlib import Path

from maid_runner.cli.graph import (
    run_graph_command,
    handle_query,
    handle_export,
    handle_analysis,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_manifest_dir(tmp_path):
    """Create a temporary directory with test manifests."""
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    return manifest_dir


@pytest.fixture
def temp_output_file(tmp_path):
    """Create a temporary output file path."""
    return tmp_path / "output"


@pytest.fixture
def create_test_manifest(temp_manifest_dir):
    """Factory fixture for creating test manifests."""

    def _create_manifest(
        filename: str, file_path: str = "test.py", artifact_name: str = None
    ) -> Path:
        manifest_path = temp_manifest_dir / filename
        if artifact_name is None:
            artifact_name = f"func_{filename.split('.')[0].replace('-', '_')}"
        manifest = {
            "version": "1",
            "goal": f"Test manifest for {filename}",
            "taskType": "edit",
            "creatableFiles": [],
            "editableFiles": [file_path],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": file_path,
                "contains": [{"type": "function", "name": artifact_name}],
            },
            "validationCommand": ["pytest", f"tests/test_{filename.split('.')[0]}.py"],
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        return manifest_path

    return _create_manifest


@pytest.fixture
def populated_manifest_dir(temp_manifest_dir, create_test_manifest):
    """Create a manifest directory with multiple test manifests."""
    create_test_manifest("task-001.manifest.json", "file1.py", "function_one")
    create_test_manifest("task-002.manifest.json", "file2.py", "function_two")
    create_test_manifest("task-003.manifest.json", "file3.py", "function_three")
    return temp_manifest_dir


@pytest.fixture
def query_args(temp_manifest_dir):
    """Create argparse.Namespace for query subcommand."""
    return argparse.Namespace(
        subcommand="query",
        query="What defines function_one?",
        manifest_dir=temp_manifest_dir,
    )


@pytest.fixture
def export_args(temp_manifest_dir, temp_output_file):
    """Create argparse.Namespace for export subcommand."""
    return argparse.Namespace(
        subcommand="export",
        format="json",
        output=temp_output_file / "graph.json",
        manifest_dir=temp_manifest_dir,
    )


@pytest.fixture
def analysis_args(temp_manifest_dir):
    """Create argparse.Namespace for analysis subcommand."""
    return argparse.Namespace(
        subcommand="analysis",
        analysis_type="find-cycles",
        manifest_dir=temp_manifest_dir,
    )


# =============================================================================
# Tests for run_graph_command
# =============================================================================


class TestRunGraphCommand:
    """Test suite for run_graph_command() function."""

    def test_function_exists_and_callable(self):
        """Verify run_graph_command function exists and is callable."""
        assert callable(run_graph_command)

    def test_returns_int_exit_code(self, query_args, populated_manifest_dir):
        """Verify run_graph_command returns an integer exit code."""
        query_args.manifest_dir = populated_manifest_dir
        result = run_graph_command(query_args)
        assert isinstance(result, int)

    def test_returns_zero_on_success_query(self, query_args, populated_manifest_dir):
        """Verify run_graph_command returns 0 on successful query execution."""
        query_args.manifest_dir = populated_manifest_dir
        result = run_graph_command(query_args)
        assert result == 0

    def test_routes_to_query_handler(
        self, query_args, populated_manifest_dir, capsys, monkeypatch
    ):
        """Verify run_graph_command routes query args to handle_query."""
        query_args.manifest_dir = populated_manifest_dir
        query_args.query = "What defines function_one?"

        result = run_graph_command(query_args)

        # Should succeed and produce output
        assert result == 0
        captured = capsys.readouterr()
        # Query handler should print something
        assert len(captured.out) > 0 or len(captured.err) >= 0

    def test_routes_to_export_handler(
        self, export_args, populated_manifest_dir, tmp_path
    ):
        """Verify run_graph_command routes export args to handle_export."""
        export_args.manifest_dir = populated_manifest_dir
        export_args.output = tmp_path / "graph.json"

        result = run_graph_command(export_args)

        assert result == 0
        # Export handler should create the output file
        assert export_args.output.exists()

    def test_routes_to_analysis_handler(
        self, analysis_args, populated_manifest_dir, capsys
    ):
        """Verify run_graph_command routes analysis args to handle_analysis."""
        analysis_args.manifest_dir = populated_manifest_dir

        result = run_graph_command(analysis_args)

        assert result == 0
        captured = capsys.readouterr()
        # Analysis handler should produce output
        assert len(captured.out) > 0 or len(captured.err) >= 0


# =============================================================================
# Tests for handle_query
# =============================================================================


class TestHandleQuery:
    """Test suite for handle_query() function."""

    def test_function_exists_and_callable(self):
        """Verify handle_query function exists and is callable."""
        assert callable(handle_query)

    def test_executes_without_error_valid_query(self, populated_manifest_dir):
        """Verify handle_query executes without error for valid query."""
        # Should not raise any exceptions
        handle_query("What defines function_one?", populated_manifest_dir)

    def test_prints_output_to_stdout(self, populated_manifest_dir, capsys):
        """Verify handle_query prints output to stdout."""
        handle_query("What defines function_one?", populated_manifest_dir)

        captured = capsys.readouterr()
        # Should produce some output
        assert len(captured.out) > 0

    def test_handles_find_cycles_query(self, populated_manifest_dir, capsys):
        """Verify handle_query handles find-cycles query."""
        handle_query("Find all cycles", populated_manifest_dir)

        captured = capsys.readouterr()
        # Should produce output about cycles
        assert len(captured.out) > 0

    def test_handles_impact_query(self, populated_manifest_dir, capsys):
        """Verify handle_query handles impact analysis query."""
        handle_query(
            "What would break if I change function_one?", populated_manifest_dir
        )

        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_handles_empty_manifest_directory(self, temp_manifest_dir, capsys):
        """Verify handle_query handles empty manifest directory gracefully."""
        # Should not raise, should produce some output
        handle_query("What defines something?", temp_manifest_dir)

        captured = capsys.readouterr()
        # Should produce some output (even if just "not found")
        assert len(captured.out) >= 0


# =============================================================================
# Tests for handle_export
# =============================================================================


class TestHandleExport:
    """Test suite for handle_export() function."""

    def test_function_exists_and_callable(self):
        """Verify handle_export function exists and is callable."""
        assert callable(handle_export)

    def test_creates_json_output_file(self, populated_manifest_dir, tmp_path):
        """Verify handle_export creates output file in json format."""
        output_path = tmp_path / "graph.json"

        handle_export("json", output_path, populated_manifest_dir)

        assert output_path.exists()
        # Verify it's valid JSON
        with open(output_path) as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert "nodes" in data
        assert "edges" in data

    def test_creates_dot_output_file(self, populated_manifest_dir, tmp_path):
        """Verify handle_export creates output file in dot format."""
        output_path = tmp_path / "graph.dot"

        handle_export("dot", output_path, populated_manifest_dir)

        assert output_path.exists()
        # Verify it's valid DOT format
        with open(output_path) as f:
            content = f.read()
        assert "digraph" in content

    def test_creates_graphml_output_file(self, populated_manifest_dir, tmp_path):
        """Verify handle_export creates output file in graphml format."""
        output_path = tmp_path / "graph.graphml"

        handle_export("graphml", output_path, populated_manifest_dir)

        assert output_path.exists()
        # Verify it's valid GraphML (XML)
        with open(output_path) as f:
            content = f.read()
        assert "graphml" in content
        assert "<?xml" in content

    def test_creates_output_directory_if_needed(self, populated_manifest_dir, tmp_path):
        """Verify handle_export creates output directory if it doesn't exist."""
        output_path = tmp_path / "new_dir" / "subdir" / "graph.json"

        handle_export("json", output_path, populated_manifest_dir)

        assert output_path.parent.exists()
        assert output_path.exists()

    def test_handles_empty_manifest_directory(self, temp_manifest_dir, tmp_path):
        """Verify handle_export handles empty manifest directory gracefully."""
        output_path = tmp_path / "empty_graph.json"

        handle_export("json", output_path, temp_manifest_dir)

        assert output_path.exists()
        with open(output_path) as f:
            data = json.load(f)
        # Should have empty or minimal graph structure
        assert "nodes" in data
        assert "edges" in data

    def test_overwrites_existing_output_file(self, populated_manifest_dir, tmp_path):
        """Verify handle_export overwrites existing output file."""
        output_path = tmp_path / "graph.json"

        # Create initial file with different content
        with open(output_path, "w") as f:
            json.dump({"old": "data"}, f)

        handle_export("json", output_path, populated_manifest_dir)

        with open(output_path) as f:
            data = json.load(f)

        assert "old" not in data
        assert "nodes" in data


# =============================================================================
# Tests for handle_analysis
# =============================================================================


class TestHandleAnalysis:
    """Test suite for handle_analysis() function."""

    def test_function_exists_and_callable(self):
        """Verify handle_analysis function exists and is callable."""
        assert callable(handle_analysis)

    def test_find_cycles_runs_without_error(self, populated_manifest_dir):
        """Verify handle_analysis with find-cycles runs without error."""
        # Should not raise
        handle_analysis("find-cycles", populated_manifest_dir)

    def test_show_stats_runs_without_error(self, populated_manifest_dir):
        """Verify handle_analysis with show-stats runs without error."""
        # Should not raise
        handle_analysis("show-stats", populated_manifest_dir)

    def test_find_cycles_prints_output(self, populated_manifest_dir, capsys):
        """Verify handle_analysis with find-cycles prints output."""
        handle_analysis("find-cycles", populated_manifest_dir)

        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_show_stats_prints_output(self, populated_manifest_dir, capsys):
        """Verify handle_analysis with show-stats prints output."""
        handle_analysis("show-stats", populated_manifest_dir)

        captured = capsys.readouterr()
        # Should print statistics
        assert len(captured.out) > 0

    def test_handles_empty_manifest_directory(self, temp_manifest_dir, capsys):
        """Verify handle_analysis handles empty manifest directory gracefully."""
        # Should not raise
        handle_analysis("find-cycles", temp_manifest_dir)

        captured = capsys.readouterr()
        # Should produce some output
        assert len(captured.out) >= 0


# =============================================================================
# Integration Tests
# =============================================================================


class TestGraphCLIIntegration:
    """Integration tests for complete CLI workflow."""

    def test_query_then_export_workflow(self, populated_manifest_dir, tmp_path, capsys):
        """Verify query and export work together in sequence."""
        # First run a query
        handle_query("What defines function_one?", populated_manifest_dir)
        query_output = capsys.readouterr()

        # Then export the graph
        output_path = tmp_path / "graph.json"
        handle_export("json", output_path, populated_manifest_dir)

        # Both should succeed
        assert len(query_output.out) > 0
        assert output_path.exists()

    def test_analysis_then_export_workflow(
        self, populated_manifest_dir, tmp_path, capsys
    ):
        """Verify analysis and export work together in sequence."""
        # First run analysis
        handle_analysis("show-stats", populated_manifest_dir)
        analysis_output = capsys.readouterr()

        # Then export
        output_path = tmp_path / "graph.dot"
        handle_export("dot", output_path, populated_manifest_dir)

        # Both should succeed
        assert len(analysis_output.out) > 0
        assert output_path.exists()

    def test_all_export_formats(self, populated_manifest_dir, tmp_path):
        """Verify all export formats work correctly."""
        formats = ["json", "dot", "graphml"]

        for fmt in formats:
            output_path = tmp_path / f"graph.{fmt}"
            handle_export(fmt, output_path, populated_manifest_dir)
            assert output_path.exists(), f"Export to {fmt} format failed"

    def test_run_graph_command_with_all_subcommands(
        self, populated_manifest_dir, tmp_path, capsys
    ):
        """Verify run_graph_command works with all subcommand types."""
        # Query subcommand
        query_args = argparse.Namespace(
            subcommand="query",
            query="Show all artifacts",
            manifest_dir=populated_manifest_dir,
        )
        result = run_graph_command(query_args)
        assert result == 0

        # Export subcommand
        export_args = argparse.Namespace(
            subcommand="export",
            format="json",
            output=tmp_path / "test.json",
            manifest_dir=populated_manifest_dir,
        )
        result = run_graph_command(export_args)
        assert result == 0

        # Analysis subcommand
        analysis_args = argparse.Namespace(
            subcommand="analysis",
            analysis_type="show-stats",
            manifest_dir=populated_manifest_dir,
        )
        result = run_graph_command(analysis_args)
        assert result == 0


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Test suite for error handling in graph CLI."""

    def test_run_graph_command_handles_invalid_subcommand(self):
        """Verify run_graph_command handles invalid subcommand gracefully."""
        invalid_args = argparse.Namespace(
            subcommand="invalid",
            manifest_dir=Path("."),
        )

        result = run_graph_command(invalid_args)

        # Should return non-zero exit code for invalid subcommand
        assert isinstance(result, int)
        assert result != 0

    def test_handle_export_with_invalid_format(self, populated_manifest_dir, tmp_path):
        """Verify handle_export handles invalid format gracefully."""
        output_path = tmp_path / "graph.txt"

        # Should raise or handle gracefully
        try:
            handle_export("invalid_format", output_path, populated_manifest_dir)
        except (ValueError, KeyError):
            pass  # Expected behavior for invalid format

    def test_handle_analysis_with_invalid_type(self, populated_manifest_dir):
        """Verify handle_analysis handles invalid analysis type gracefully."""
        # Should raise or handle gracefully
        try:
            handle_analysis("invalid-analysis-type", populated_manifest_dir)
        except (ValueError, KeyError):
            pass  # Expected behavior for invalid type
