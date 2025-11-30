"""Behavioral tests for Task-060: Claude Code sync infrastructure.

Tests verify that the sync script:
1. sync_agents() copies .claude/agents/*.md to maid_runner/claude/agents/
2. sync_commands() copies .claude/commands/*.md to maid_runner/claude/commands/
3. main() orchestrates the full sync process
4. Files are copied correctly and destination directories are created
5. Script handles missing source directories gracefully
"""

import sys
from pathlib import Path

# Add project root to path for importing scripts
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.sync_claude_files import main, sync_agents, sync_commands


class TestSyncAgents:
    """Test sync_agents() function."""

    def test_sync_agents_copies_agent_files(self, tmp_path, monkeypatch):
        """Verify sync_agents() copies all agent markdown files."""
        # Create mock source structure
        source_agents = tmp_path / ".claude" / "agents"
        source_agents.mkdir(parents=True)

        # Create sample agent files
        (source_agents / "test-agent-1.md").write_text("# Agent 1")
        (source_agents / "test-agent-2.md").write_text("# Agent 2")

        # Set up destination
        dest_root = tmp_path / "maid_runner"
        dest_root.mkdir()

        # Mock the project root
        monkeypatch.chdir(tmp_path)

        # Run sync_agents
        sync_agents()

        # Verify files were copied
        dest_agents = dest_root / "claude" / "agents"
        assert dest_agents.exists()
        assert (dest_agents / "test-agent-1.md").exists()
        assert (dest_agents / "test-agent-2.md").exists()
        assert (dest_agents / "test-agent-1.md").read_text() == "# Agent 1"
        assert (dest_agents / "test-agent-2.md").read_text() == "# Agent 2"

    def test_sync_agents_creates_destination_directory(self, tmp_path, monkeypatch):
        """Verify sync_agents() creates destination directory if it doesn't exist."""
        # Create mock source structure
        source_agents = tmp_path / ".claude" / "agents"
        source_agents.mkdir(parents=True)
        (source_agents / "test-agent.md").write_text("# Agent")

        # Set up maid_runner but not claude subdirectory
        dest_root = tmp_path / "maid_runner"
        dest_root.mkdir()

        # Mock the project root
        monkeypatch.chdir(tmp_path)

        # Run sync_agents
        sync_agents()

        # Verify directory was created
        dest_agents = dest_root / "claude" / "agents"
        assert dest_agents.exists()
        assert dest_agents.is_dir()

    def test_sync_agents_removes_old_files(self, tmp_path, monkeypatch):
        """Verify sync_agents() removes old files before copying new ones."""
        # Create mock source structure
        source_agents = tmp_path / ".claude" / "agents"
        source_agents.mkdir(parents=True)
        (source_agents / "new-agent.md").write_text("# New Agent")

        # Create destination with old file
        dest_root = tmp_path / "maid_runner"
        dest_agents = dest_root / "claude" / "agents"
        dest_agents.mkdir(parents=True)
        (dest_agents / "old-agent.md").write_text("# Old Agent")

        # Mock the project root
        monkeypatch.chdir(tmp_path)

        # Run sync_agents
        sync_agents()

        # Verify old file is removed, new file exists
        assert not (dest_agents / "old-agent.md").exists()
        assert (dest_agents / "new-agent.md").exists()

    def test_sync_agents_handles_missing_source_directory(
        self, tmp_path, monkeypatch, capsys
    ):
        """Verify sync_agents() handles missing source directory gracefully."""
        # Set up destination only (no source)
        dest_root = tmp_path / "maid_runner"
        dest_root.mkdir()

        # Mock the project root
        monkeypatch.chdir(tmp_path)

        # Run sync_agents - should not raise
        sync_agents()

        # Verify warning message was printed
        captured = capsys.readouterr()
        assert "Warning" in captured.out or "warning" in captured.out.lower()


class TestSyncCommands:
    """Test sync_commands() function."""

    def test_sync_commands_copies_command_files(self, tmp_path, monkeypatch):
        """Verify sync_commands() copies all command markdown files."""
        # Create mock source structure
        source_commands = tmp_path / ".claude" / "commands"
        source_commands.mkdir(parents=True)

        # Create sample command files
        (source_commands / "test-cmd-1.md").write_text("# Command 1")
        (source_commands / "test-cmd-2.md").write_text("# Command 2")
        (source_commands / "test-cmd-3.md").write_text("# Command 3")

        # Set up destination
        dest_root = tmp_path / "maid_runner"
        dest_root.mkdir()

        # Mock the project root
        monkeypatch.chdir(tmp_path)

        # Run sync_commands
        sync_commands()

        # Verify files were copied
        dest_commands = dest_root / "claude" / "commands"
        assert dest_commands.exists()
        assert (dest_commands / "test-cmd-1.md").exists()
        assert (dest_commands / "test-cmd-2.md").exists()
        assert (dest_commands / "test-cmd-3.md").exists()
        assert (dest_commands / "test-cmd-1.md").read_text() == "# Command 1"

    def test_sync_commands_creates_destination_directory(self, tmp_path, monkeypatch):
        """Verify sync_commands() creates destination directory if it doesn't exist."""
        # Create mock source structure
        source_commands = tmp_path / ".claude" / "commands"
        source_commands.mkdir(parents=True)
        (source_commands / "test-cmd.md").write_text("# Command")

        # Set up maid_runner but not claude subdirectory
        dest_root = tmp_path / "maid_runner"
        dest_root.mkdir()

        # Mock the project root
        monkeypatch.chdir(tmp_path)

        # Run sync_commands
        sync_commands()

        # Verify directory was created
        dest_commands = dest_root / "claude" / "commands"
        assert dest_commands.exists()
        assert dest_commands.is_dir()

    def test_sync_commands_removes_old_files(self, tmp_path, monkeypatch):
        """Verify sync_commands() removes old files before copying new ones."""
        # Create mock source structure
        source_commands = tmp_path / ".claude" / "commands"
        source_commands.mkdir(parents=True)
        (source_commands / "new-cmd.md").write_text("# New Command")

        # Create destination with old file
        dest_root = tmp_path / "maid_runner"
        dest_commands = dest_root / "claude" / "commands"
        dest_commands.mkdir(parents=True)
        (dest_commands / "old-cmd.md").write_text("# Old Command")

        # Mock the project root
        monkeypatch.chdir(tmp_path)

        # Run sync_commands
        sync_commands()

        # Verify old file is removed, new file exists
        assert not (dest_commands / "old-cmd.md").exists()
        assert (dest_commands / "new-cmd.md").exists()

    def test_sync_commands_handles_missing_source_directory(
        self, tmp_path, monkeypatch, capsys
    ):
        """Verify sync_commands() handles missing source directory gracefully."""
        # Set up destination only (no source)
        dest_root = tmp_path / "maid_runner"
        dest_root.mkdir()

        # Mock the project root
        monkeypatch.chdir(tmp_path)

        # Run sync_commands - should not raise
        sync_commands()

        # Verify warning message was printed
        captured = capsys.readouterr()
        assert "Warning" in captured.out or "warning" in captured.out.lower()


class TestMain:
    """Test main() orchestration function."""

    def test_main_syncs_both_agents_and_commands(self, tmp_path, monkeypatch):
        """Verify main() calls both sync_agents() and sync_commands()."""
        # Create complete mock source structure
        source_root = tmp_path / ".claude"
        source_agents = source_root / "agents"
        source_commands = source_root / "commands"
        source_agents.mkdir(parents=True)
        source_commands.mkdir(parents=True)

        (source_agents / "agent.md").write_text("# Agent")
        (source_commands / "command.md").write_text("# Command")

        # Set up destination
        dest_root = tmp_path / "maid_runner"
        dest_root.mkdir()

        # Mock the project root
        monkeypatch.chdir(tmp_path)

        # Run main
        main()

        # Verify both agent and command files were synced
        assert (dest_root / "claude" / "agents" / "agent.md").exists()
        assert (dest_root / "claude" / "commands" / "command.md").exists()

    def test_main_prints_summary(self, tmp_path, monkeypatch, capsys):
        """Verify main() prints a summary of synced files."""
        # Create mock source structure with multiple files
        source_root = tmp_path / ".claude"
        source_agents = source_root / "agents"
        source_commands = source_root / "commands"
        source_agents.mkdir(parents=True)
        source_commands.mkdir(parents=True)

        # Create 2 agent files and 3 command files
        (source_agents / "agent1.md").write_text("# Agent 1")
        (source_agents / "agent2.md").write_text("# Agent 2")
        (source_commands / "cmd1.md").write_text("# Command 1")
        (source_commands / "cmd2.md").write_text("# Command 2")
        (source_commands / "cmd3.md").write_text("# Command 3")

        # Set up destination
        dest_root = tmp_path / "maid_runner"
        dest_root.mkdir()

        # Mock the project root
        monkeypatch.chdir(tmp_path)

        # Run main
        main()

        # Verify summary was printed
        captured = capsys.readouterr()
        assert "2" in captured.out  # 2 agent files
        assert "3" in captured.out  # 3 command files
        assert "Sync" in captured.out or "sync" in captured.out

    def test_main_can_be_run_multiple_times(self, tmp_path, monkeypatch):
        """Verify main() is idempotent and can be run multiple times."""
        # Create mock source structure
        source_root = tmp_path / ".claude"
        source_agents = source_root / "agents"
        source_agents.mkdir(parents=True)
        (source_agents / "agent.md").write_text("# Agent")

        # Set up destination
        dest_root = tmp_path / "maid_runner"
        dest_root.mkdir()

        # Mock the project root
        monkeypatch.chdir(tmp_path)

        # Run main twice
        main()
        main()

        # Verify files still exist and content is correct
        dest_agent = dest_root / "claude" / "agents" / "agent.md"
        assert dest_agent.exists()
        assert dest_agent.read_text() == "# Agent"
