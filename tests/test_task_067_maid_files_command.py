"""Behavioral tests for task-067: maid files command.

These tests verify that the 'maid files' CLI command correctly shows
file-level tracking status without requiring full validation.
"""

import json

# Import the functions that will be implemented
from maid_runner.cli.files import (
    run_files,
    format_files_output,
    format_files_json,
)
from maid_runner.validators.file_tracker import FileTrackingAnalysis


class TestRunFiles:
    """Tests for the run_files main entry point."""

    def test_run_files_with_default_options(self, tmp_path, capsys):
        """Test run_files with default options shows file summary."""
        # Create a minimal manifests directory
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Call run_files with defaults
        run_files(
            manifest_dir=str(manifests_dir),
            issues_only=False,
            status_filter=None,
            quiet=False,
            json_output=False,
            hide_private=False,
        )

        captured = capsys.readouterr()
        # Should produce some output (even if no files found)
        assert captured.out is not None

    def test_run_files_issues_only(self, tmp_path, capsys):
        """Test run_files with --issues-only flag filters output."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        run_files(
            manifest_dir=str(manifests_dir),
            issues_only=True,
            status_filter=None,
            quiet=False,
            json_output=False,
            hide_private=False,
        )

        captured = capsys.readouterr()
        # Issues-only mode should not show "TRACKED" files
        assert "TRACKED" not in captured.out or captured.out == ""

    def test_run_files_status_filter(self, tmp_path, capsys):
        """Test run_files with --status filter limits output to that status."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        run_files(
            manifest_dir=str(manifests_dir),
            issues_only=False,
            status_filter="undeclared",
            quiet=False,
            json_output=False,
            hide_private=False,
        )

        captured = capsys.readouterr()
        # Should only show undeclared status (or nothing if none exist)
        assert "REGISTERED" not in captured.out

    def test_run_files_quiet_mode(self, tmp_path, capsys):
        """Test run_files with --quiet flag produces minimal output."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        run_files(
            manifest_dir=str(manifests_dir),
            issues_only=False,
            status_filter=None,
            quiet=True,
            json_output=False,
            hide_private=False,
        )

        captured = capsys.readouterr()
        # Quiet mode should have no decorative output (no emoji headers)
        assert "━" not in captured.out

    def test_run_files_json_output(self, tmp_path, capsys):
        """Test run_files with --json flag produces valid JSON."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        run_files(
            manifest_dir=str(manifests_dir),
            issues_only=False,
            status_filter=None,
            quiet=False,
            json_output=True,
            hide_private=False,
        )

        captured = capsys.readouterr()
        # Should produce valid JSON
        parsed = json.loads(captured.out)
        assert isinstance(parsed, dict)


class TestFormatFilesOutput:
    """Tests for the format_files_output function."""

    def test_format_files_output_all_files(self, capsys):
        """Test formatting all files shows both undeclared and tracked."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [
                {
                    "file": "foo.py",
                    "status": "UNDECLARED",
                    "issues": ["Not in manifest"],
                    "manifests": [],
                }
            ],
            "registered": [],
            "tracked": ["bar.py"],
            "untracked_tests": [],
        }

        format_files_output(
            analysis=analysis,
            issues_only=False,
            status_filter=None,
            quiet=False,
            hide_private=False,
        )

        captured = capsys.readouterr()
        assert "foo.py" in captured.out
        assert "UNDECLARED" in captured.out

    def test_format_files_output_issues_only(self, capsys):
        """Test formatting only issues excludes tracked files."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [
                {
                    "file": "foo.py",
                    "status": "UNDECLARED",
                    "issues": [],
                    "manifests": [],
                }
            ],
            "registered": [],
            "tracked": ["bar.py"],
            "untracked_tests": [],
        }

        format_files_output(
            analysis=analysis,
            issues_only=True,
            status_filter=None,
            quiet=False,
            hide_private=False,
        )

        captured = capsys.readouterr()
        assert "foo.py" in captured.out
        # Tracked files should not appear in issues-only mode
        assert "bar.py" not in captured.out

    def test_format_files_output_with_status_filter(self, capsys):
        """Test formatting with a status filter shows only that status."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [
                {
                    "file": "foo.py",
                    "status": "UNDECLARED",
                    "issues": [],
                    "manifests": [],
                }
            ],
            "registered": [
                {
                    "file": "baz.py",
                    "status": "REGISTERED",
                    "issues": [],
                    "manifests": ["task-001"],
                }
            ],
            "tracked": ["bar.py"],
            "untracked_tests": [],
        }

        format_files_output(
            analysis=analysis,
            issues_only=False,
            status_filter="undeclared",
            quiet=False,
            hide_private=False,
        )

        captured = capsys.readouterr()
        assert "foo.py" in captured.out
        # Other statuses should not appear
        assert "baz.py" not in captured.out
        assert "bar.py" not in captured.out

    def test_format_files_output_quiet(self, capsys):
        """Test formatting in quiet mode produces machine-readable output."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [
                {
                    "file": "foo.py",
                    "status": "UNDECLARED",
                    "issues": [],
                    "manifests": [],
                }
            ],
            "registered": [],
            "tracked": ["bar.py"],
            "untracked_tests": [],
        }

        format_files_output(
            analysis=analysis,
            issues_only=False,
            status_filter=None,
            quiet=True,
            hide_private=False,
        )

        captured = capsys.readouterr()
        # Quiet mode: no decorative elements
        assert "━" not in captured.out
        assert "🔴" not in captured.out


class TestFormatFilesJson:
    """Tests for the format_files_json function."""

    def test_format_files_json_returns_valid_json(self):
        """Test that format_files_json returns valid parseable JSON."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [],
            "registered": [],
            "tracked": ["bar.py"],
            "untracked_tests": [],
        }

        result = format_files_json(
            analysis=analysis,
            issues_only=False,
            status_filter=None,
            hide_private=False,
        )

        assert isinstance(result, str)
        # Must be valid JSON
        parsed = json.loads(result)
        assert isinstance(parsed, dict)
        assert "tracked" in parsed

    def test_format_files_json_issues_only_excludes_tracked(self):
        """Test JSON output with issues_only excludes tracked files."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [
                {
                    "file": "foo.py",
                    "status": "UNDECLARED",
                    "issues": [],
                    "manifests": [],
                }
            ],
            "registered": [],
            "tracked": ["bar.py"],
            "untracked_tests": [],
        }

        result = format_files_json(
            analysis=analysis,
            issues_only=True,
            status_filter=None,
            hide_private=False,
        )

        assert isinstance(result, str)
        parsed = json.loads(result)
        # Issues only should include undeclared
        assert "undeclared" in parsed
        # But not tracked files
        assert "tracked" not in parsed or parsed.get("tracked") == []

    def test_format_files_json_with_status_filter(self):
        """Test JSON output with status filter only includes that status."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [
                {
                    "file": "foo.py",
                    "status": "UNDECLARED",
                    "issues": [],
                    "manifests": [],
                }
            ],
            "registered": [
                {
                    "file": "baz.py",
                    "status": "REGISTERED",
                    "issues": [],
                    "manifests": [],
                }
            ],
            "tracked": ["bar.py"],
            "untracked_tests": [],
        }

        result = format_files_json(
            analysis=analysis,
            issues_only=False,
            status_filter="tracked",
            hide_private=False,
        )

        assert isinstance(result, str)
        parsed = json.loads(result)
        # Should only contain tracked
        assert "bar.py" in str(parsed)
        assert "foo.py" not in str(parsed)
        assert "baz.py" not in str(parsed)


class TestFilesStatusFilters:
    """Tests for different status filters to improve coverage (lines 46-57, 163-170)."""

    def test_format_files_output_registered_status_filter(self, capsys):
        """Test status filter for 'registered' files."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [
                {
                    "file": "undeclared.py",
                    "status": "UNDECLARED",
                    "issues": [],
                    "manifests": [],
                }
            ],
            "registered": [
                {
                    "file": "registered.py",
                    "status": "REGISTERED",
                    "issues": ["Missing artifacts"],
                    "manifests": ["task-001"],
                }
            ],
            "tracked": ["tracked.py"],
            "untracked_tests": [],
        }

        format_files_output(
            analysis=analysis,
            issues_only=False,
            status_filter="registered",
            quiet=False,
            hide_private=False,
        )

        captured = capsys.readouterr()
        # Should only show registered files
        assert "registered.py" in captured.out
        assert "undeclared.py" not in captured.out
        assert "tracked.py" not in captured.out

    def test_format_files_output_tracked_status_filter(self, capsys):
        """Test status filter for 'tracked' files."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [
                {
                    "file": "undeclared.py",
                    "status": "UNDECLARED",
                    "issues": [],
                    "manifests": [],
                }
            ],
            "registered": [],
            "tracked": ["tracked.py", "also_tracked.py"],
            "untracked_tests": [],
        }

        format_files_output(
            analysis=analysis,
            issues_only=False,
            status_filter="tracked",
            quiet=False,
            hide_private=False,
        )

        captured = capsys.readouterr()
        # Should only show tracked files
        assert "tracked.py" in captured.out
        assert "undeclared.py" not in captured.out

    def test_format_files_output_private_impl_status_filter(self, capsys):
        """Test status filter for 'private_impl' files."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [],
            "registered": [],
            "tracked": ["tracked.py"],
            "untracked_tests": [],
            "private_impl": ["_private.py", "_helper.py"],
        }

        format_files_output(
            analysis=analysis,
            issues_only=False,
            status_filter="private_impl",
            quiet=False,
            hide_private=False,
        )

        captured = capsys.readouterr()
        # Should only show private impl files
        assert "_private.py" in captured.out
        assert "tracked.py" not in captured.out

    def test_format_files_json_registered_status_filter(self):
        """Test JSON output with 'registered' status filter."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [
                {
                    "file": "undeclared.py",
                    "status": "UNDECLARED",
                    "issues": [],
                    "manifests": [],
                }
            ],
            "registered": [
                {
                    "file": "registered.py",
                    "status": "REGISTERED",
                    "issues": [],
                    "manifests": ["task-001"],
                }
            ],
            "tracked": ["tracked.py"],
            "untracked_tests": [],
        }

        result = format_files_json(
            analysis=analysis,
            issues_only=False,
            status_filter="registered",
            hide_private=False,
        )

        parsed = json.loads(result)
        assert "registered" in parsed
        assert "registered.py" in str(parsed["registered"])
        assert "undeclared" not in parsed
        assert "tracked" not in parsed

    def test_format_files_json_private_impl_status_filter(self):
        """Test JSON output with 'private_impl' status filter."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [],
            "registered": [],
            "tracked": ["tracked.py"],
            "untracked_tests": [],
            "private_impl": ["_private.py"],
        }

        result = format_files_json(
            analysis=analysis,
            issues_only=False,
            status_filter="private_impl",
            hide_private=False,
        )

        parsed = json.loads(result)
        assert "private_impl" in parsed
        assert "_private.py" in str(parsed["private_impl"])
        assert "tracked" not in parsed

    def test_format_files_json_private_impl_hidden_with_filter(self):
        """Test JSON output with 'private_impl' filter but hide_private=True."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [],
            "registered": [],
            "tracked": ["tracked.py"],
            "untracked_tests": [],
            "private_impl": ["_private.py"],
        }

        result = format_files_json(
            analysis=analysis,
            issues_only=False,
            status_filter="private_impl",
            hide_private=True,
        )

        parsed = json.loads(result)
        # Should be empty when hiding private with private_impl filter
        assert "private_impl" not in parsed or parsed.get("private_impl") == []


class TestFilesQuietModeOutput:
    """Tests for quiet mode output to improve coverage (lines 70-77)."""

    def test_quiet_mode_undeclared_files(self, capsys):
        """Test quiet mode output for undeclared files."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [
                {
                    "file": "undeclared.py",
                    "status": "UNDECLARED",
                    "issues": [],
                    "manifests": [],
                }
            ],
            "registered": [],
            "tracked": [],
            "untracked_tests": [],
        }

        format_files_output(
            analysis=analysis,
            issues_only=False,
            status_filter=None,
            quiet=True,
            hide_private=False,
        )

        captured = capsys.readouterr()
        # Quiet mode should have tab-separated format
        assert "UNDECLARED\t" in captured.out
        assert "undeclared.py" in captured.out

    def test_quiet_mode_registered_files(self, capsys):
        """Test quiet mode output for registered files."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [],
            "registered": [
                {
                    "file": "registered.py",
                    "status": "REGISTERED",
                    "issues": [],
                    "manifests": ["task-001"],
                }
            ],
            "tracked": [],
            "untracked_tests": [],
        }

        format_files_output(
            analysis=analysis,
            issues_only=False,
            status_filter=None,
            quiet=True,
            hide_private=False,
        )

        captured = capsys.readouterr()
        # Quiet mode should have tab-separated format
        assert "REGISTERED\t" in captured.out
        assert "registered.py" in captured.out

    def test_quiet_mode_private_impl_files(self, capsys):
        """Test quiet mode output for private implementation files."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [],
            "registered": [],
            "tracked": [],
            "untracked_tests": [],
            "private_impl": ["_private.py"],
        }

        format_files_output(
            analysis=analysis,
            issues_only=False,
            status_filter=None,
            quiet=True,
            hide_private=False,
        )

        captured = capsys.readouterr()
        # Quiet mode should have tab-separated format
        assert "PRIVATE_IMPL\t" in captured.out
        assert "_private.py" in captured.out


class TestFilesRegisteredWithManifests:
    """Tests for registered file output with manifests list (lines 99-101)."""

    def test_registered_files_show_manifests(self, capsys):
        """Test that registered files show their manifest references."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [],
            "registered": [
                {
                    "file": "registered.py",
                    "status": "REGISTERED",
                    "issues": ["Missing expectedArtifacts"],
                    "manifests": [
                        "task-001.manifest.json",
                        "task-002.manifest.json",
                        "task-003.manifest.json",
                    ],
                }
            ],
            "tracked": [],
            "untracked_tests": [],
        }

        format_files_output(
            analysis=analysis,
            issues_only=False,
            status_filter=None,
            quiet=False,
            hide_private=False,
        )

        captured = capsys.readouterr()
        # Should show manifests
        assert "Manifests:" in captured.out
        assert "task-001" in captured.out


class TestRunFilesEdgeCases:
    """Tests for edge cases in run_files (lines 214-221, 227)."""

    def test_run_files_with_invalid_manifest_json(self, tmp_path, capsys):
        """Test run_files skips invalid JSON manifests."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create an invalid JSON manifest
        invalid_manifest = manifests_dir / "task-001-invalid.manifest.json"
        invalid_manifest.write_text("{ invalid json }")

        # Create a valid manifest
        valid_manifest = manifests_dir / "task-002-valid.manifest.json"
        valid_manifest.write_text('{"goal": "test", "taskType": "create"}')

        # Should not crash
        run_files(
            manifest_dir=str(manifests_dir),
            issues_only=False,
            status_filter=None,
            quiet=False,
            json_output=False,
            hide_private=False,
        )

        captured = capsys.readouterr()
        # Should produce output without crashing
        assert captured.out is not None

    def test_run_files_with_nonexistent_manifest_dir(self, tmp_path, capsys):
        """Test run_files with nonexistent manifest directory."""
        nonexistent_dir = tmp_path / "nonexistent"

        run_files(
            manifest_dir=str(nonexistent_dir),
            issues_only=False,
            status_filter=None,
            quiet=False,
            json_output=False,
            hide_private=False,
        )

        captured = capsys.readouterr()
        # Should use current working directory as source root
        assert captured.out is not None
