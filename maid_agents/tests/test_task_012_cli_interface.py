"""Behavioral tests for Task-012: CLI Interface."""

import sys
import subprocess
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.cli.main import main


def test_main_function_exists():
    """Test main function can be imported."""
    assert callable(main)


def test_main_function_with_help():
    """Test calling main() with --help argument."""
    with patch("sys.argv", ["ccmaid", "--help"]):
        try:
            main()
        except SystemExit as e:
            # --help causes sys.exit(0)
            assert e.code == 0


def test_cli_help_command():
    """Test CLI --help works."""
    result = subprocess.run(
        ["python", "-m", "maid_agents.cli.main", "--help"],
        capture_output=True,
        text=True,
        cwd="maid_agents",
    )
    # Should show help text without error
    assert result.returncode == 0 or "ccmaid" in result.stdout.lower()


def test_cli_version_command():
    """Test CLI --version works."""
    result = subprocess.run(
        ["python", "-m", "maid_agents.cli.main", "--version"],
        capture_output=True,
        text=True,
        cwd="maid_agents",
    )
    # Should show version or exit cleanly
    assert result.returncode == 0 or "version" in result.stdout.lower()
