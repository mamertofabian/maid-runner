"""Behavioral tests for Task-152e: Create init_tools/__init__.py module.

Tests verify that:
1. setup_tool() function exists and dispatches to correct tool setup functions
2. Tool registry contains all supported tools (claude, cursor, windsurf, generic)
3. setup_tool() raises ValueError for unknown tools
"""

import pytest

from maid_runner.cli.init_tools import setup_tool


class TestSetupTool:
    """Test setup_tool() dispatcher function."""

    def test_setup_tool_with_claude(self, tmp_path):
        """Verify setup_tool dispatches to Claude setup."""
        setup_tool(str(tmp_path), "claude", force=True, dry_run=False)

        assert (tmp_path / ".claude" / "agents").exists()

    def test_setup_tool_with_cursor(self, tmp_path):
        """Verify setup_tool dispatches to Cursor setup."""
        setup_tool(str(tmp_path), "cursor", force=True, dry_run=False)

        assert (tmp_path / ".cursor" / "rules").exists()

    def test_setup_tool_with_windsurf(self, tmp_path):
        """Verify setup_tool dispatches to Windsurf setup."""
        setup_tool(str(tmp_path), "windsurf", force=True, dry_run=False)

        assert (tmp_path / ".windsurf" / "rules").exists()

    def test_setup_tool_with_generic(self, tmp_path):
        """Verify setup_tool dispatches to generic setup."""
        setup_tool(str(tmp_path), "generic", force=True, dry_run=False)

        assert (tmp_path / "MAID.md").exists()

    def test_setup_tool_raises_for_unknown_tool(self, tmp_path):
        """Verify setup_tool raises ValueError for unknown tool."""
        with pytest.raises(ValueError, match="Unknown tool"):
            setup_tool(str(tmp_path), "unknown", force=True, dry_run=False)
