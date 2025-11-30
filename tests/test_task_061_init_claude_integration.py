"""Behavioral tests for Task-061: Add Claude Code integration to maid init.

Tests verify that the init command:
1. copy_claude_agents() copies agent files to .claude/agents/ with user confirmation
2. copy_claude_commands() copies command files to .claude/commands/ with confirmation
3. User confirmation defaults to Yes (Y/n pattern)
4. Force flag bypasses confirmation prompts
5. Missing source files are handled gracefully
"""

from unittest.mock import patch

from maid_runner.cli.init import copy_claude_agents, copy_claude_commands


class TestCopyClaudeAgents:
    """Test copy_claude_agents() function."""

    def test_copies_agent_files_to_target_directory(self, tmp_path):
        """Verify agent files are copied to .claude/agents/."""
        # Run with force=True to skip prompts
        copy_claude_agents(str(tmp_path), force=True)

        # Verify directory was created
        agents_dir = tmp_path / ".claude" / "agents"
        assert agents_dir.exists()
        assert agents_dir.is_dir()

        # Verify at least some agent files were copied
        agent_files = list(agents_dir.glob("*.md"))
        assert len(agent_files) > 0, "No agent files were copied"

        # Verify content is preserved
        for agent_file in agent_files:
            content = agent_file.read_text()
            assert len(content) > 0, f"{agent_file.name} is empty"

    def test_creates_destination_directory_if_not_exists(self, tmp_path):
        """Verify .claude/agents/ directory is created if it doesn't exist."""
        # Ensure directory doesn't exist
        agents_dir = tmp_path / ".claude" / "agents"
        assert not agents_dir.exists()

        # Run copy
        copy_claude_agents(str(tmp_path), force=True)

        # Verify directory was created
        assert agents_dir.exists()
        assert agents_dir.is_dir()

    @patch("builtins.input", return_value="")
    def test_prompts_user_with_default_yes(self, mock_input, tmp_path):
        """Verify user is prompted with (Y/n) pattern defaulting to Yes."""
        # Run without force flag
        copy_claude_agents(str(tmp_path), force=False)

        # Verify input was called
        assert mock_input.called, "User prompt was not called"

        # Verify files were copied (default Yes)
        agents_dir = tmp_path / ".claude" / "agents"
        assert agents_dir.exists()
        agent_files = list(agents_dir.glob("*.md"))
        assert len(agent_files) > 0

    @patch("builtins.input", return_value="n")
    def test_skips_copy_when_user_declines(self, mock_input, tmp_path):
        """Verify copy is skipped when user answers 'n'."""
        # Run without force flag
        copy_claude_agents(str(tmp_path), force=False)

        # Verify input was called
        assert mock_input.called

        # Verify files were NOT copied
        agents_dir = tmp_path / ".claude" / "agents"
        if agents_dir.exists():
            agent_files = list(agents_dir.glob("*.md"))
            assert len(agent_files) == 0, "Files were copied despite user declining"

    @patch("builtins.input", return_value="no")
    def test_accepts_no_as_decline(self, mock_input, tmp_path):
        """Verify 'no' is accepted as decline."""
        copy_claude_agents(str(tmp_path), force=False)

        agents_dir = tmp_path / ".claude" / "agents"
        if agents_dir.exists():
            agent_files = list(agents_dir.glob("*.md"))
            assert len(agent_files) == 0

    def test_force_flag_skips_prompt(self, tmp_path):
        """Verify force=True bypasses user prompt."""
        # This should not call input()
        copy_claude_agents(str(tmp_path), force=True)

        # Verify files were copied without prompting
        agents_dir = tmp_path / ".claude" / "agents"
        assert agents_dir.exists()
        agent_files = list(agents_dir.glob("*.md"))
        assert len(agent_files) > 0

    def test_handles_missing_source_gracefully(self, tmp_path, capsys, monkeypatch):
        """Verify graceful handling when source files not found."""
        # Mock the package location to point to non-existent location
        from maid_runner.cli import init as init_module

        original_file = init_module.__file__
        # Point to a location where claude/ directory doesn't exist
        monkeypatch.setattr(init_module, "__file__", str(tmp_path / "fake_module.py"))

        # Should not raise, should print warning
        copy_claude_agents(str(tmp_path), force=True)

        # Verify warning was printed
        captured = capsys.readouterr()
        assert "Warning" in captured.out or "warning" in captured.out.lower()

        # Restore
        monkeypatch.setattr(init_module, "__file__", original_file)


class TestCopyClaudeCommands:
    """Test copy_claude_commands() function."""

    def test_copies_command_files_to_target_directory(self, tmp_path):
        """Verify command files are copied to .claude/commands/."""
        # Run with force=True to skip prompts
        copy_claude_commands(str(tmp_path), force=True)

        # Verify directory was created
        commands_dir = tmp_path / ".claude" / "commands"
        assert commands_dir.exists()
        assert commands_dir.is_dir()

        # Verify command files were copied
        command_files = list(commands_dir.glob("*.md"))
        assert len(command_files) > 0, "No command files were copied"

        # Verify content is preserved
        for command_file in command_files:
            content = command_file.read_text()
            assert len(content) > 0, f"{command_file.name} is empty"

    def test_creates_destination_directory_if_not_exists(self, tmp_path):
        """Verify .claude/commands/ directory is created if it doesn't exist."""
        # Ensure directory doesn't exist
        commands_dir = tmp_path / ".claude" / "commands"
        assert not commands_dir.exists()

        # Run copy
        copy_claude_commands(str(tmp_path), force=True)

        # Verify directory was created
        assert commands_dir.exists()
        assert commands_dir.is_dir()

    @patch("builtins.input", return_value="")
    def test_prompts_user_with_default_yes(self, mock_input, tmp_path):
        """Verify user is prompted with (Y/n) pattern defaulting to Yes."""
        # Run without force flag
        copy_claude_commands(str(tmp_path), force=False)

        # Verify input was called
        assert mock_input.called, "User prompt was not called"

        # Verify files were copied (default Yes)
        commands_dir = tmp_path / ".claude" / "commands"
        assert commands_dir.exists()
        command_files = list(commands_dir.glob("*.md"))
        assert len(command_files) > 0

    @patch("builtins.input", return_value="n")
    def test_skips_copy_when_user_declines(self, mock_input, tmp_path):
        """Verify copy is skipped when user answers 'n'."""
        # Run without force flag
        copy_claude_commands(str(tmp_path), force=False)

        # Verify input was called
        assert mock_input.called

        # Verify files were NOT copied
        commands_dir = tmp_path / ".claude" / "commands"
        if commands_dir.exists():
            command_files = list(commands_dir.glob("*.md"))
            assert len(command_files) == 0, "Files were copied despite user declining"

    @patch("builtins.input", return_value="no")
    def test_accepts_no_as_decline(self, mock_input, tmp_path):
        """Verify 'no' is accepted as decline."""
        copy_claude_commands(str(tmp_path), force=False)

        commands_dir = tmp_path / ".claude" / "commands"
        if commands_dir.exists():
            command_files = list(commands_dir.glob("*.md"))
            assert len(command_files) == 0

    def test_force_flag_skips_prompt(self, tmp_path):
        """Verify force=True bypasses user prompt."""
        # This should not call input()
        copy_claude_commands(str(tmp_path), force=True)

        # Verify files were copied without prompting
        commands_dir = tmp_path / ".claude" / "commands"
        assert commands_dir.exists()
        command_files = list(commands_dir.glob("*.md"))
        assert len(command_files) > 0

    def test_handles_missing_source_gracefully(self, tmp_path, capsys, monkeypatch):
        """Verify graceful handling when source files not found."""
        # Mock the package location to point to non-existent location
        from maid_runner.cli import init as init_module

        original_file = init_module.__file__
        # Point to a location where claude/ directory doesn't exist
        monkeypatch.setattr(init_module, "__file__", str(tmp_path / "fake_module.py"))

        # Should not raise, should print warning
        copy_claude_commands(str(tmp_path), force=True)

        # Verify warning was printed
        captured = capsys.readouterr()
        assert "Warning" in captured.out or "warning" in captured.out.lower()

        # Restore
        monkeypatch.setattr(init_module, "__file__", original_file)


class TestIntegration:
    """Integration tests for Claude Code file copying."""

    def test_both_functions_copy_complete_structure(self, tmp_path):
        """Verify both copy functions work together to create complete structure."""
        # Copy both agents and commands
        copy_claude_agents(str(tmp_path), force=True)
        copy_claude_commands(str(tmp_path), force=True)

        # Verify complete structure
        claude_dir = tmp_path / ".claude"
        assert claude_dir.exists()

        agents_dir = claude_dir / "agents"
        commands_dir = claude_dir / "commands"

        assert agents_dir.exists()
        assert commands_dir.exists()

        # Verify files in both
        agent_files = list(agents_dir.glob("*.md"))
        command_files = list(commands_dir.glob("*.md"))

        assert len(agent_files) > 0, "No agent files copied"
        assert len(command_files) > 0, "No command files copied"

    @patch("builtins.input", return_value="y")
    def test_explicit_yes_works(self, mock_input, tmp_path):
        """Verify explicit 'y' answer works."""
        copy_claude_agents(str(tmp_path), force=False)

        agents_dir = tmp_path / ".claude" / "agents"
        assert agents_dir.exists()
        agent_files = list(agents_dir.glob("*.md"))
        assert len(agent_files) > 0

    @patch("builtins.input", return_value="yes")
    def test_explicit_yes_full_word_works(self, mock_input, tmp_path):
        """Verify explicit 'yes' answer works."""
        copy_claude_agents(str(tmp_path), force=False)

        agents_dir = tmp_path / ".claude" / "agents"
        assert agents_dir.exists()
        agent_files = list(agents_dir.glob("*.md"))
        assert len(agent_files) > 0
