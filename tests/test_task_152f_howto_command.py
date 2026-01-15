"""Behavioral tests for Task-152f: Create howto.py module.

Tests verify that:
1. run_howto() function exists and displays guide content
2. run_howto() accepts section parameter to jump to specific sections
3. All sections are accessible (intro, principles, workflow, quickstart, patterns, commands, troubleshooting)
"""

from unittest.mock import patch

from maid_runner.cli.howto import run_howto


class TestRunHowto:
    """Test run_howto() function."""

    def test_howto_command_exists(self):
        """Verify howto command module exists and is importable."""
        from maid_runner.cli import howto

        assert hasattr(howto, "run_howto")

    def test_howto_command_displays_content(self, capsys):
        """Verify howto command displays guide content."""
        run_howto(section="intro")

        captured = capsys.readouterr()
        output = captured.out

        assert "MAID" in output or "Manifest-driven" in output

    def test_howto_command_accepts_section_parameter(self):
        """Verify howto command accepts section parameter."""
        # Should not raise
        run_howto(section="principles")
        run_howto(section="workflow")
        run_howto(section="quickstart")
        run_howto(section="patterns")
        run_howto(section="commands")
        run_howto(section="troubleshooting")

    @patch("builtins.input", return_value="")
    def test_howto_command_with_none_section(self, mock_input, capsys):
        """Verify howto command works without section parameter."""
        # Mock input to avoid interactive prompts during testing
        run_howto(section=None)

        # Verify it displayed content
        captured = capsys.readouterr()
        output = captured.out
        assert "MAID Methodology" in output
