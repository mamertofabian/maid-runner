"""Behavioral tests for Task-152a: Create init_tools/claude.py module.

Tests verify that:
1. setup_claude() function exists and sets up Claude Code integration
2. copy_claude_agents() copies agent files to .claude/agents/
3. copy_claude_commands() copies command files to .claude/commands/
"""

from unittest.mock import patch

from maid_runner.cli.init_tools.claude import (
    copy_claude_agents,
    copy_claude_commands,
    setup_claude,
)


class TestSetupClaude:
    """Test setup_claude() function."""

    def test_setup_claude_calls_copy_functions(self, tmp_path):
        """Verify setup_claude calls both copy functions."""
        setup_claude(str(tmp_path), force=True, dry_run=False)

        # Verify both directories were created
        assert (tmp_path / ".claude" / "agents").exists()
        assert (tmp_path / ".claude" / "commands").exists()


class TestCopyClaudeAgents:
    """Test copy_claude_agents() function."""

    def test_copies_agent_files_to_target_directory(self, tmp_path):
        """Verify agent files are copied to .claude/agents/."""
        copy_claude_agents(str(tmp_path), force=True, dry_run=False)

        agents_dir = tmp_path / ".claude" / "agents"
        assert agents_dir.exists()
        assert agents_dir.is_dir()

        agent_files = list(agents_dir.glob("*.md"))
        assert len(agent_files) > 0, "No agent files were copied"

    def test_creates_destination_directory_if_not_exists(self, tmp_path):
        """Verify .claude/agents/ directory is created if it doesn't exist."""
        agents_dir = tmp_path / ".claude" / "agents"
        assert not agents_dir.exists()

        copy_claude_agents(str(tmp_path), force=True, dry_run=False)

        assert agents_dir.exists()
        assert agents_dir.is_dir()

    @patch("builtins.input", return_value="")
    def test_prompts_user_with_default_yes(self, mock_input, tmp_path):
        """Verify user is prompted with (Y/n) pattern defaulting to Yes."""
        copy_claude_agents(str(tmp_path), force=False, dry_run=False)

        assert mock_input.called
        agents_dir = tmp_path / ".claude" / "agents"
        assert agents_dir.exists()

    @patch("builtins.input", return_value="n")
    def test_skips_copy_when_user_declines(self, mock_input, tmp_path):
        """Verify copy is skipped when user answers 'n'."""
        copy_claude_agents(str(tmp_path), force=False, dry_run=False)

        assert mock_input.called
        agents_dir = tmp_path / ".claude" / "agents"
        if agents_dir.exists():
            agent_files = list(agents_dir.glob("*.md"))
            assert len(agent_files) == 0


class TestCopyClaudeCommands:
    """Test copy_claude_commands() function."""

    def test_copies_command_files_to_target_directory(self, tmp_path):
        """Verify command files are copied to .claude/commands/."""
        copy_claude_commands(str(tmp_path), force=True, dry_run=False)

        commands_dir = tmp_path / ".claude" / "commands"
        assert commands_dir.exists()
        assert commands_dir.is_dir()

        command_files = list(commands_dir.glob("*.md"))
        assert len(command_files) > 0, "No command files were copied"

    def test_creates_destination_directory_if_not_exists(self, tmp_path):
        """Verify .claude/commands/ directory is created if it doesn't exist."""
        commands_dir = tmp_path / ".claude" / "commands"
        assert not commands_dir.exists()

        copy_claude_commands(str(tmp_path), force=True, dry_run=False)

        assert commands_dir.exists()
        assert commands_dir.is_dir()
