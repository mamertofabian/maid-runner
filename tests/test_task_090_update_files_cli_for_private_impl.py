"""Behavioral tests for task-090: Update files CLI for private implementation files.

These tests verify that the files CLI command can format and filter
private implementation files using the hide_private parameter.
"""

import json

from maid_runner.cli.files import (
    run_files,
    format_files_output,
    format_files_json,
)
from maid_runner.validators.file_tracker import FileTrackingAnalysis


class TestFormatFilesOutputWithPrivateImpl:
    """Tests for format_files_output with private_impl handling."""

    def test_displays_private_impl_by_default(self, capsys):
        """Private implementation files are shown by default."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [],
            "registered": [],
            "tracked": [],
            "private_impl": ["src/_helpers.py", "src/_utils.py"],
            "untracked_tests": [],
        }

        format_files_output(
            analysis=analysis,
            issues_only=False,
            status_filter=None,
            quiet=False,
            hide_private=False,  # Default: show private files
        )

        captured = capsys.readouterr()
        assert "_helpers.py" in captured.out
        assert "_utils.py" in captured.out

    def test_hides_private_impl_when_requested(self, capsys):
        """Private implementation files are hidden when hide_private=True."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [],
            "registered": [],
            "tracked": [],
            "private_impl": ["src/_helpers.py", "src/_utils.py"],
            "untracked_tests": [],
        }

        format_files_output(
            analysis=analysis,
            issues_only=False,
            status_filter=None,
            quiet=False,
            hide_private=True,  # Hide private files
        )

        captured = capsys.readouterr()
        assert "_helpers.py" not in captured.out
        assert "_utils.py" not in captured.out

    def test_includes_private_impl_in_summary_by_default(self, capsys):
        """Summary includes private_impl count by default."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [],
            "registered": [],
            "tracked": [],
            "private_impl": ["src/_helpers.py"],
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
        # Summary should mention private_impl
        assert (
            "private_impl" in captured.out.lower() or "private" in captured.out.lower()
        )

    def test_quiet_mode_with_private_impl(self, capsys):
        """Quiet mode shows private_impl files in machine-readable format."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [],
            "registered": [],
            "tracked": [],
            "private_impl": ["src/_helpers.py"],
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
        assert "PRIVATE_IMPL\tsrc/_helpers.py" in captured.out


class TestFormatFilesJsonWithPrivateImpl:
    """Tests for format_files_json with private_impl handling."""

    def test_includes_private_impl_by_default(self):
        """JSON output includes private_impl field by default."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [],
            "registered": [],
            "tracked": [],
            "private_impl": ["src/_helpers.py", "src/_utils.py"],
            "untracked_tests": [],
        }

        result = format_files_json(
            analysis=analysis,
            issues_only=False,
            status_filter=None,
            hide_private=False,
        )

        parsed = json.loads(result)
        assert "private_impl" in parsed
        assert "src/_helpers.py" in parsed["private_impl"]
        assert "src/_utils.py" in parsed["private_impl"]

    def test_excludes_private_impl_when_hidden(self):
        """JSON output excludes private_impl when hide_private=True."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [],
            "registered": [],
            "tracked": [],
            "private_impl": ["src/_helpers.py", "src/_utils.py"],
            "untracked_tests": [],
        }

        result = format_files_json(
            analysis=analysis,
            issues_only=False,
            status_filter=None,
            hide_private=True,
        )

        parsed = json.loads(result)
        # private_impl should either be absent or empty
        assert parsed.get("private_impl", []) == []

    def test_issues_only_does_not_affect_private_impl(self):
        """issues_only flag doesn't hide private_impl (it's not an issue)."""
        analysis: FileTrackingAnalysis = {
            "undeclared": [],
            "registered": [],
            "tracked": [],
            "private_impl": ["src/_helpers.py"],
            "untracked_tests": [],
        }

        result = format_files_json(
            analysis=analysis,
            issues_only=True,  # Only show issues
            status_filter=None,
            hide_private=False,
        )

        parsed = json.loads(result)
        # Private impl is not an "issue", but should still be included
        # when hide_private=False (even with issues_only=True)
        assert "private_impl" in parsed


class TestRunFilesWithHidePrivate:
    """Tests for run_files with hide_private parameter."""

    def test_run_files_accepts_hide_private_parameter(self, tmp_path, capsys):
        """run_files accepts hide_private parameter without error."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Should not raise any error
        run_files(
            manifest_dir=str(manifests_dir),
            issues_only=False,
            status_filter=None,
            quiet=False,
            json_output=False,
            hide_private=False,
        )

        # Also test with hide_private=True
        run_files(
            manifest_dir=str(manifests_dir),
            issues_only=False,
            status_filter=None,
            quiet=False,
            json_output=False,
            hide_private=True,
        )

        # No assertion needed - just verify it doesn't crash

    def test_run_files_passes_hide_private_to_formatter(self, tmp_path, capsys):
        """run_files passes hide_private parameter to formatters."""
        # Create a test environment
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "_private.py").write_text("# private")

        # Run with hide_private=False
        run_files(
            manifest_dir=str(manifests_dir),
            issues_only=False,
            status_filter=None,
            quiet=False,
            json_output=False,
            hide_private=False,
        )

        captured_show = capsys.readouterr()

        # Run with hide_private=True
        run_files(
            manifest_dir=str(manifests_dir),
            issues_only=False,
            status_filter=None,
            quiet=False,
            json_output=False,
            hide_private=True,
        )

        captured_hide = capsys.readouterr()

        # When shown, private file should appear
        assert "_private.py" in captured_show.out

        # When hidden, private file should not appear
        assert "_private.py" not in captured_hide.out
