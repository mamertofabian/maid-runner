"""Behavioral tests for Task-149: --dry-run option for 'maid init' command.

Tests verify that the --dry-run option:
1. Shows which files would be created without actually creating them
2. Shows which files would be updated without actually updating them
3. Shows which directories would be created without actually creating them
4. Works correctly with both new and existing files
5. Works correctly with --force flag
"""

from unittest.mock import patch

from maid_runner.cli.init import (
    copy_claude_agents,
    copy_claude_commands,
    copy_maid_specs,
    copy_unit_testing_rules,
    create_directories,
    handle_claude_md,
    run_init,
)


class TestCreateDirectoriesDryRun:
    """Test directory creation in dry-run mode."""

    def test_shows_directories_to_create_in_dry_run(self, tmp_path, capsys):
        """Verify dry-run shows directories that would be created."""
        create_directories(str(tmp_path), dry_run=True)
        captured = capsys.readouterr()
        output = captured.out

        assert "[CREATE]" in output
        assert "manifests" in output
        assert "tests" in output
        assert ".maid/docs" in output

    def test_does_not_create_directories_in_dry_run(self, tmp_path):
        """Verify dry-run does not actually create directories."""
        create_directories(str(tmp_path), dry_run=True)

        assert not (tmp_path / "manifests").exists()
        assert not (tmp_path / "tests").exists()
        assert not (tmp_path / ".maid").exists()

    def test_shows_existing_directories_in_dry_run(self, tmp_path, capsys):
        """Verify dry-run shows directories even if they already exist."""
        (tmp_path / "manifests").mkdir()
        (tmp_path / "tests").mkdir()

        create_directories(str(tmp_path), dry_run=True)
        captured = capsys.readouterr()
        output = captured.out

        assert "[CREATE]" in output
        assert "manifests" in output
        assert "tests" in output


class TestCopyMaidSpecsDryRun:
    """Test MAID specs copying in dry-run mode."""

    def test_shows_file_to_copy_in_dry_run(self, tmp_path, capsys):
        """Verify dry-run shows file that would be copied."""
        (tmp_path / ".maid" / "docs").mkdir(parents=True)
        copy_maid_specs(str(tmp_path), dry_run=True)
        captured = capsys.readouterr()
        output = captured.out

        assert "[CREATE]" in output or "[UPDATE]" in output
        assert "maid_specs.md" in output

    def test_does_not_copy_file_in_dry_run(self, tmp_path):
        """Verify dry-run does not actually copy file."""
        (tmp_path / ".maid" / "docs").mkdir(parents=True)
        copy_maid_specs(str(tmp_path), dry_run=True)

        assert not (tmp_path / ".maid" / "docs" / "maid_specs.md").exists()


class TestCopyUnitTestingRulesDryRun:
    """Test unit testing rules copying in dry-run mode."""

    def test_shows_file_to_copy_in_dry_run(self, tmp_path, capsys):
        """Verify dry-run shows file that would be copied."""
        (tmp_path / ".maid" / "docs").mkdir(parents=True)
        copy_unit_testing_rules(str(tmp_path), dry_run=True)
        captured = capsys.readouterr()
        output = captured.out

        assert "[CREATE]" in output or "[UPDATE]" in output
        assert "unit-testing-rules.md" in output

    def test_does_not_copy_file_in_dry_run(self, tmp_path):
        """Verify dry-run does not actually copy file."""
        (tmp_path / ".maid" / "docs").mkdir(parents=True)
        copy_unit_testing_rules(str(tmp_path), dry_run=True)

        assert not (tmp_path / ".maid" / "docs" / "unit-testing-rules.md").exists()


class TestHandleClaudeMdDryRun:
    """Test CLAUDE.md handling in dry-run mode."""

    def test_shows_file_to_create_in_dry_run(self, tmp_path, capsys):
        """Verify dry-run shows CLAUDE.md would be created when it doesn't exist."""
        handle_claude_md(str(tmp_path), force=False, dry_run=True)
        captured = capsys.readouterr()
        output = captured.out

        assert "[CREATE]" in output
        assert "CLAUDE.md" in output

    def test_does_not_create_file_in_dry_run(self, tmp_path):
        """Verify dry-run does not actually create CLAUDE.md."""
        handle_claude_md(str(tmp_path), force=False, dry_run=True)

        assert not (tmp_path / "CLAUDE.md").exists()

    def test_shows_file_to_update_in_dry_run(self, tmp_path, capsys):
        """Verify dry-run shows CLAUDE.md would be updated when it exists."""
        (tmp_path / "CLAUDE.md").write_text("# Existing content")
        handle_claude_md(str(tmp_path), force=False, dry_run=True)
        captured = capsys.readouterr()
        output = captured.out

        assert "[UPDATE]" in output
        assert "CLAUDE.md" in output

    def test_does_not_update_file_in_dry_run(self, tmp_path):
        """Verify dry-run does not actually update CLAUDE.md."""
        original_content = "# Existing content"
        (tmp_path / "CLAUDE.md").write_text(original_content)
        handle_claude_md(str(tmp_path), force=False, dry_run=True)

        assert (tmp_path / "CLAUDE.md").read_text() == original_content

    @patch("builtins.input", return_value="a")
    def test_shows_update_with_append_choice_in_dry_run(
        self, mock_input, tmp_path, capsys
    ):
        """Verify dry-run shows update when user would choose append."""
        (tmp_path / "CLAUDE.md").write_text("# Existing")
        handle_claude_md(str(tmp_path), force=False, dry_run=True)
        captured = capsys.readouterr()
        output = captured.out

        assert "[UPDATE]" in output or "[CREATE]" in output
        assert "CLAUDE.md" in output

    def test_shows_update_with_force_flag_in_dry_run(self, tmp_path, capsys):
        """Verify dry-run shows update when --force is used."""
        (tmp_path / "CLAUDE.md").write_text("# Existing")
        handle_claude_md(str(tmp_path), force=True, dry_run=True)
        captured = capsys.readouterr()
        output = captured.out

        assert "[UPDATE]" in output
        assert "CLAUDE.md" in output


class TestCopyClaudeAgentsDryRun:
    """Test Claude agents copying in dry-run mode."""

    def test_shows_files_to_copy_in_dry_run(self, tmp_path, capsys):
        """Verify dry-run shows agent files that would be copied."""
        copy_claude_agents(str(tmp_path), force=False, dry_run=True)
        captured = capsys.readouterr()
        output = captured.out

        # Should show either files to copy or a message about skipping
        assert "[CREATE]" in output or "Skipped" in output or "Warning" in output

    def test_does_not_copy_files_in_dry_run(self, tmp_path):
        """Verify dry-run does not actually copy agent files."""
        copy_claude_agents(str(tmp_path), force=False, dry_run=True)

        agents_dir = tmp_path / ".claude" / "agents"
        if agents_dir.exists():
            assert len(list(agents_dir.iterdir())) == 0


class TestCopyClaudeCommandsDryRun:
    """Test Claude commands copying in dry-run mode."""

    def test_shows_files_to_copy_in_dry_run(self, tmp_path, capsys):
        """Verify dry-run shows command files that would be copied."""
        copy_claude_commands(str(tmp_path), force=False, dry_run=True)
        captured = capsys.readouterr()
        output = captured.out

        # Should show either files to copy or a message about skipping
        assert "[CREATE]" in output or "Skipped" in output or "Warning" in output

    def test_does_not_copy_files_in_dry_run(self, tmp_path):
        """Verify dry-run does not actually copy command files."""
        copy_claude_commands(str(tmp_path), force=False, dry_run=True)

        commands_dir = tmp_path / ".claude" / "commands"
        if commands_dir.exists():
            assert len(list(commands_dir.iterdir())) == 0


class TestRunInitDryRun:
    """Test main run_init function in dry-run mode."""

    @patch("builtins.input", return_value="s")
    def test_shows_all_operations_in_dry_run(self, mock_input, tmp_path, capsys):
        """Verify dry-run shows all files and directories that would be created."""
        run_init(str(tmp_path), force=False, dry_run=True)
        captured = capsys.readouterr()
        output = captured.out

        assert (
            "dry-run" in output.lower() or "[CREATE]" in output or "[UPDATE]" in output
        )
        assert "manifests" in output or "tests" in output

    @patch("builtins.input", return_value="s")
    def test_does_not_create_anything_in_dry_run(self, mock_input, tmp_path):
        """Verify dry-run does not actually create any files or directories."""
        run_init(str(tmp_path), force=False, dry_run=True)

        # Should not create main directories
        assert not (tmp_path / "manifests").exists()
        assert not (tmp_path / "tests").exists()
        assert not (tmp_path / ".maid").exists()
        assert not (tmp_path / "CLAUDE.md").exists()

    def test_works_with_force_flag_in_dry_run(self, tmp_path, capsys):
        """Verify dry-run works correctly with --force flag."""
        (tmp_path / "CLAUDE.md").write_text("# Existing")
        run_init(str(tmp_path), force=True, dry_run=True)
        captured = capsys.readouterr()
        output = captured.out

        assert "[UPDATE]" in output or "[CREATE]" in output

    def test_shows_correct_summary_in_dry_run(self, tmp_path, capsys):
        """Verify dry-run shows appropriate summary message."""
        run_init(str(tmp_path), force=False, dry_run=True)
        captured = capsys.readouterr()
        output = captured.out

        # Should indicate this is a dry-run
        assert (
            "dry-run" in output.lower()
            or "would" in output.lower()
            or "[CREATE]" in output
        )
