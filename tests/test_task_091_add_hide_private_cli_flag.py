"""Behavioral tests for task-091: Add --hide-private CLI flag.

These tests verify that the --hide-private flag is properly wired up
in the main CLI argument parser and passed to the files command.
"""

import subprocess
import sys


class TestHidePrivateCliFlag:
    """Tests for --hide-private CLI flag integration."""

    def test_hide_private_flag_exists(self, tmp_path):
        """The --hide-private flag is recognized by the CLI."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Run command with --hide-private flag
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "files",
                "--manifest-dir",
                str(manifests_dir),
                "--hide-private",
            ],
            capture_output=True,
            text=True,
        )

        # Should not error due to unrecognized argument
        assert result.returncode == 0
        assert "unrecognized arguments" not in result.stderr

    def test_hide_private_flag_actually_hides_files(self, tmp_path):
        """The --hide-private flag actually filters private files from output."""
        # Create test environment
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "_private.py").write_text("# private")
        (src_dir / "public.py").write_text("# public")

        # Run without --hide-private
        result_show = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "files",
                "--manifest-dir",
                str(manifests_dir),
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )

        # Run with --hide-private
        result_hide = subprocess.run(
            [
                sys.executable,
                "-m",
                "maid_runner.cli.main",
                "files",
                "--manifest-dir",
                str(manifests_dir),
                "--hide-private",
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )

        # Private file should appear without flag
        assert "_private.py" in result_show.stdout

        # Private file should NOT appear with flag
        assert "_private.py" not in result_hide.stdout

        # Public file should appear in both
        assert "public.py" in result_show.stdout
        assert "public.py" in result_hide.stdout

    def test_help_mentions_hide_private(self, tmp_path):
        """The --help output mentions the --hide-private flag."""
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

        # Help text should mention --hide-private
        assert "--hide-private" in result.stdout
