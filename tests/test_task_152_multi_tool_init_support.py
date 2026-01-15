"""Behavioral tests for Task-152: Multi-tool MAID init support and howto command.

Tests verify that:
1. run_init() accepts a tools list parameter
2. Tool registry dispatches to correct tool setup functions
3. Claude Code setup works (moved to init_tools/claude.py)
4. Cursor IDE rules are created correctly
5. Windsurf IDE rules are created correctly
6. Generic MAID.md file is created correctly
7. Multiple tools can be set up simultaneously
8. Howto command displays interactive guide
9. CLI argument parsing handles tool flags correctly
"""

import pytest

from maid_runner.cli.init import run_init
from maid_runner.cli.init_tools import setup_tool


class TestRunInitWithTools:
    """Test run_init() with tools parameter."""

    def test_run_init_accepts_tools_list(self, tmp_path):
        """Verify run_init accepts tools list parameter."""
        # Should not raise
        run_init(str(tmp_path), tools=["claude"], force=True, dry_run=False)

    def test_run_init_with_claude_tool(self, tmp_path):
        """Verify run_init sets up Claude Code when tools includes 'claude'."""
        run_init(str(tmp_path), tools=["claude"], force=True, dry_run=False)

        # Verify Claude Code files were created
        assert (tmp_path / ".claude" / "agents").exists()
        assert (tmp_path / ".claude" / "commands").exists()

    def test_run_init_with_cursor_tool(self, tmp_path):
        """Verify run_init sets up Cursor IDE when tools includes 'cursor'."""
        run_init(str(tmp_path), tools=["cursor"], force=True, dry_run=False)

        # Verify Cursor rules were created
        cursor_rules = tmp_path / ".cursor" / "rules"
        assert cursor_rules.exists()
        rule_file = cursor_rules / "maid-runner.mdc"
        assert rule_file.exists()

    def test_run_init_with_windsurf_tool(self, tmp_path):
        """Verify run_init sets up Windsurf IDE when tools includes 'windsurf'."""
        run_init(str(tmp_path), tools=["windsurf"], force=True, dry_run=False)

        # Verify Windsurf rules were created
        windsurf_rules = tmp_path / ".windsurf" / "rules"
        assert windsurf_rules.exists()
        rule_file = windsurf_rules / "maid-runner.md"
        assert rule_file.exists()

    def test_run_init_with_generic_tool(self, tmp_path):
        """Verify run_init creates MAID.md when tools includes 'generic'."""
        run_init(str(tmp_path), tools=["generic"], force=True, dry_run=False)

        # Verify generic MAID.md was created
        maid_md = tmp_path / "MAID.md"
        assert maid_md.exists()
        content = maid_md.read_text()
        assert "MAID Methodology" in content

    def test_run_init_with_multiple_tools(self, tmp_path):
        """Verify run_init can set up multiple tools simultaneously."""
        run_init(
            str(tmp_path),
            tools=["claude", "cursor", "generic"],
            force=True,
            dry_run=False,
        )

        # Verify all tools were set up
        assert (tmp_path / ".claude" / "agents").exists()
        assert (tmp_path / ".cursor" / "rules").exists()
        assert (tmp_path / "MAID.md").exists()

    def test_run_init_defaults_to_claude_when_empty_tools(self, tmp_path):
        """Verify run_init defaults to Claude when tools list is empty."""
        run_init(str(tmp_path), tools=[], force=True, dry_run=False)

        # Should still create Claude files (backward compatibility)
        assert (tmp_path / ".claude" / "agents").exists()

    def test_run_init_with_all_tools(self, tmp_path):
        """Verify run_init sets up all tools when tools=['claude', 'cursor', 'windsurf', 'generic']."""
        run_init(
            str(tmp_path),
            tools=["claude", "cursor", "windsurf", "generic"],
            force=True,
            dry_run=False,
        )

        # Verify all tools were set up
        assert (tmp_path / ".claude" / "agents").exists()
        assert (tmp_path / ".cursor" / "rules").exists()
        assert (tmp_path / ".windsurf" / "rules").exists()
        assert (tmp_path / "MAID.md").exists()


class TestToolRegistry:
    """Test tool registry and dispatcher."""

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
        """Verify setup_tool raises error for unknown tool."""
        with pytest.raises(ValueError, match="Unknown tool"):
            setup_tool(str(tmp_path), "unknown", force=True, dry_run=False)


class TestCursorTool:
    """Test Cursor IDE tool setup."""

    def test_cursor_creates_rules_directory(self, tmp_path):
        """Verify Cursor setup creates .cursor/rules/ directory."""
        setup_tool(str(tmp_path), "cursor", force=True, dry_run=False)

        rules_dir = tmp_path / ".cursor" / "rules"
        assert rules_dir.exists()
        assert rules_dir.is_dir()

    def test_cursor_creates_maid_runner_mdc_file(self, tmp_path):
        """Verify Cursor setup creates maid-runner.mdc file."""
        setup_tool(str(tmp_path), "cursor", force=True, dry_run=False)

        rule_file = tmp_path / ".cursor" / "rules" / "maid-runner.mdc"
        assert rule_file.exists()

    def test_cursor_mdc_has_yaml_frontmatter(self, tmp_path):
        """Verify Cursor .mdc file has proper YAML frontmatter."""
        setup_tool(str(tmp_path), "cursor", force=True, dry_run=False)

        rule_file = tmp_path / ".cursor" / "rules" / "maid-runner.mdc"
        content = rule_file.read_text()

        assert "---" in content
        assert "description:" in content
        assert "globs:" in content
        assert "alwaysApply:" in content

    def test_cursor_mdc_contains_maid_content(self, tmp_path):
        """Verify Cursor .mdc file contains MAID methodology content."""
        setup_tool(str(tmp_path), "cursor", force=True, dry_run=False)

        rule_file = tmp_path / ".cursor" / "rules" / "maid-runner.mdc"
        content = rule_file.read_text()

        assert "MAID Methodology" in content
        assert "Manifest-driven AI Development" in content


class TestWindsurfTool:
    """Test Windsurf IDE tool setup."""

    def test_windsurf_creates_rules_directory(self, tmp_path):
        """Verify Windsurf setup creates .windsurf/rules/ directory."""
        setup_tool(str(tmp_path), "windsurf", force=True, dry_run=False)

        rules_dir = tmp_path / ".windsurf" / "rules"
        assert rules_dir.exists()
        assert rules_dir.is_dir()

    def test_windsurf_creates_maid_runner_md_file(self, tmp_path):
        """Verify Windsurf setup creates maid-runner.md file."""
        setup_tool(str(tmp_path), "windsurf", force=True, dry_run=False)

        rule_file = tmp_path / ".windsurf" / "rules" / "maid-runner.md"
        assert rule_file.exists()

    def test_windsurf_md_contains_maid_content(self, tmp_path):
        """Verify Windsurf .md file contains MAID methodology content."""
        setup_tool(str(tmp_path), "windsurf", force=True, dry_run=False)

        rule_file = tmp_path / ".windsurf" / "rules" / "maid-runner.md"
        content = rule_file.read_text()

        assert "MAID Methodology" in content
        assert "Manifest-driven AI Development" in content


class TestGenericTool:
    """Test generic tool setup."""

    def test_generic_creates_maid_md_file(self, tmp_path):
        """Verify generic setup creates MAID.md file in project root."""
        setup_tool(str(tmp_path), "generic", force=True, dry_run=False)

        maid_md = tmp_path / "MAID.md"
        assert maid_md.exists()

    def test_generic_maid_md_contains_maid_content(self, tmp_path):
        """Verify generic MAID.md contains MAID methodology content."""
        setup_tool(str(tmp_path), "generic", force=True, dry_run=False)

        maid_md = tmp_path / "MAID.md"
        content = maid_md.read_text()

        assert "MAID Methodology" in content
        assert "Manifest-driven AI Development" in content

    def test_generic_maid_md_is_language_aware(self, tmp_path):
        """Verify generic MAID.md adapts to project language."""
        # Create Python project marker
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        setup_tool(str(tmp_path), "generic", force=True, dry_run=False)

        maid_md = tmp_path / "MAID.md"
        content = maid_md.read_text()

        # Should contain Python-specific content
        assert "pytest" in content or "Python" in content


class TestHowtoCommand:
    """Test howto command."""

    def test_howto_command_exists(self):
        """Verify howto command module exists and is importable."""
        from maid_runner.cli import howto

        assert hasattr(howto, "run_howto")

    def test_howto_command_displays_content(self, capsys):
        """Verify howto command displays guide content."""
        from maid_runner.cli.howto import run_howto

        # Run with a section to avoid interactive prompts
        run_howto(section="intro")

        captured = capsys.readouterr()
        output = captured.out

        assert "MAID" in output or "Manifest-driven" in output

    def test_howto_command_accepts_section_parameter(self):
        """Verify howto command accepts section parameter."""
        from maid_runner.cli.howto import run_howto

        # Should not raise
        run_howto(section="principles")
