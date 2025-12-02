"""Behavioral tests for Task-069: Claude Files Manifest for Selective Distribution.

These tests verify the behavior of load_claude_manifest() and get_distributable_files()
functions that enable selective distribution of Claude files during maid init.
"""

import tempfile
from pathlib import Path


class TestLoadClaudeManifest:
    """Tests for load_claude_manifest() function."""

    def test_returns_a_dict(self):
        """load_claude_manifest returns a dictionary."""
        from maid_runner.cli.init import load_claude_manifest

        result = load_claude_manifest()

        assert isinstance(result, dict)

    def test_returned_dict_has_agents_key(self):
        """Returned dict contains an 'agents' key."""
        from maid_runner.cli.init import load_claude_manifest

        result = load_claude_manifest()

        assert "agents" in result

    def test_returned_dict_has_commands_key(self):
        """Returned dict contains a 'commands' key."""
        from maid_runner.cli.init import load_claude_manifest

        result = load_claude_manifest()

        assert "commands" in result

    def test_agents_section_has_distributable_list(self):
        """Agents section contains a 'distributable' list."""
        from maid_runner.cli.init import load_claude_manifest

        result = load_claude_manifest()

        assert "distributable" in result["agents"]
        assert isinstance(result["agents"]["distributable"], list)

    def test_commands_section_has_distributable_list(self):
        """Commands section contains a 'distributable' list."""
        from maid_runner.cli.init import load_claude_manifest

        result = load_claude_manifest()

        assert "distributable" in result["commands"]
        assert isinstance(result["commands"]["distributable"], list)

    def test_agents_section_has_descriptions_dict(self):
        """Agents section contains a 'descriptions' dictionary."""
        from maid_runner.cli.init import load_claude_manifest

        result = load_claude_manifest()

        assert "descriptions" in result["agents"]
        assert isinstance(result["agents"]["descriptions"], dict)

    def test_commands_section_has_descriptions_dict(self):
        """Commands section contains a 'descriptions' dictionary."""
        from maid_runner.cli.init import load_claude_manifest

        result = load_claude_manifest()

        assert "descriptions" in result["commands"]
        assert isinstance(result["commands"]["descriptions"], dict)


class TestGetDistributableFiles:
    """Tests for get_distributable_files() function."""

    def test_returns_list_for_agents(self):
        """Returns a list when given 'agents' as file_type."""
        from maid_runner.cli.init import load_claude_manifest, get_distributable_files

        manifest = load_claude_manifest()
        result = get_distributable_files(manifest, "agents")

        assert isinstance(result, list)

    def test_returns_list_for_commands(self):
        """Returns a list when given 'commands' as file_type."""
        from maid_runner.cli.init import load_claude_manifest, get_distributable_files

        manifest = load_claude_manifest()
        result = get_distributable_files(manifest, "commands")

        assert isinstance(result, list)

    def test_returns_only_files_in_distributable_section(self):
        """Returns only files listed in the 'distributable' section."""
        from maid_runner.cli.init import load_claude_manifest, get_distributable_files

        manifest = load_claude_manifest()
        result = get_distributable_files(manifest, "agents")

        # Result should match the distributable list exactly
        assert result == manifest["agents"]["distributable"]

    def test_returns_empty_list_for_unknown_file_type(self):
        """Returns empty list for unknown file_type."""
        from maid_runner.cli.init import load_claude_manifest, get_distributable_files

        manifest = load_claude_manifest()
        result = get_distributable_files(manifest, "unknown_type")

        assert result == []

    def test_each_item_is_a_string(self):
        """Each item in returned list is a string (filename)."""
        from maid_runner.cli.init import load_claude_manifest, get_distributable_files

        manifest = load_claude_manifest()

        # Test both agents and commands
        agents_result = get_distributable_files(manifest, "agents")
        commands_result = get_distributable_files(manifest, "commands")

        for item in agents_result:
            assert isinstance(item, str), f"Expected string, got {type(item)}"

        for item in commands_result:
            assert isinstance(item, str), f"Expected string, got {type(item)}"


class TestDistributableFilesIntegration:
    """Integration tests for distributable files content."""

    def test_distributable_agents_contains_maid_workflow_agents(self):
        """Distributable agents list contains expected MAID workflow agents."""
        from maid_runner.cli.init import load_claude_manifest, get_distributable_files

        manifest = load_claude_manifest()
        distributable_agents = get_distributable_files(manifest, "agents")

        # Expected MAID workflow agents (core agents that should be distributed)
        expected_agents = [
            "maid-manifest-architect.md",
            "maid-test-designer.md",
            "maid-developer.md",
            "maid-refactorer.md",
            "maid-auditor.md",
        ]

        for agent in expected_agents:
            assert (
                agent in distributable_agents
            ), f"Expected {agent} in distributable agents"

    def test_distributable_commands_contains_maid_workflow_commands(self):
        """Distributable commands list contains expected MAID workflow commands."""
        from maid_runner.cli.init import load_claude_manifest, get_distributable_files

        manifest = load_claude_manifest()
        distributable_commands = get_distributable_files(manifest, "commands")

        # Expected MAID workflow commands (core commands that should be distributed)
        expected_commands = [
            "plan.md",
            "generate-manifest.md",
            "generate-tests.md",
            "implement.md",
            "refactor.md",
            "audit.md",
        ]

        for command in expected_commands:
            assert (
                command in distributable_commands
            ), f"Expected {command} in distributable commands"

    def test_project_specific_files_not_in_distributable_agents(self):
        """Project-specific agent files are NOT in distributable lists."""
        from maid_runner.cli.init import load_claude_manifest, get_distributable_files

        manifest = load_claude_manifest()
        distributable_agents = get_distributable_files(manifest, "agents")

        # README.md is project-specific documentation
        assert "README.md" not in distributable_agents

    def test_project_specific_files_not_in_distributable_commands(self):
        """Project-specific command files (pypi-release.md) are NOT in distributable lists."""
        from maid_runner.cli.init import load_claude_manifest, get_distributable_files

        manifest = load_claude_manifest()
        distributable_commands = get_distributable_files(manifest, "commands")

        # pypi-release.md is project-specific (PyPI publishing)
        assert "pypi-release.md" not in distributable_commands

    def test_all_distributable_agent_files_exist(self):
        """All files in distributable agents list actually exist in the package directory."""
        from maid_runner.cli.init import load_claude_manifest, get_distributable_files

        manifest = load_claude_manifest()
        distributable_agents = get_distributable_files(manifest, "agents")

        # Get path to agents directory in package
        init_path = Path(__file__).parent.parent / "maid_runner" / "cli" / "init.py"
        maid_runner_package = init_path.parent.parent
        agents_dir = maid_runner_package / "claude" / "agents"

        for agent_file in distributable_agents:
            agent_path = agents_dir / agent_file
            assert (
                agent_path.exists()
            ), f"Agent file {agent_file} does not exist at {agent_path}"

    def test_all_distributable_command_files_exist(self):
        """All files in distributable commands list actually exist in the package directory."""
        from maid_runner.cli.init import load_claude_manifest, get_distributable_files

        manifest = load_claude_manifest()
        distributable_commands = get_distributable_files(manifest, "commands")

        # Get path to commands directory in package
        init_path = Path(__file__).parent.parent / "maid_runner" / "cli" / "init.py"
        maid_runner_package = init_path.parent.parent
        commands_dir = maid_runner_package / "claude" / "commands"

        for command_file in distributable_commands:
            command_path = commands_dir / command_file
            assert (
                command_path.exists()
            ), f"Command file {command_file} does not exist at {command_path}"


class TestManifestDescriptions:
    """Tests for manifest descriptions structure (indirect via load_claude_manifest)."""

    def test_manifest_contains_descriptions_for_all_distributable_agents(self):
        """Manifest contains descriptions for all distributable agents."""
        from maid_runner.cli.init import load_claude_manifest, get_distributable_files

        manifest = load_claude_manifest()
        distributable_agents = get_distributable_files(manifest, "agents")
        descriptions = manifest["agents"]["descriptions"]

        for agent_file in distributable_agents:
            assert (
                agent_file in descriptions
            ), f"Missing description for agent: {agent_file}"

    def test_manifest_contains_descriptions_for_all_distributable_commands(self):
        """Manifest contains descriptions for all distributable commands."""
        from maid_runner.cli.init import load_claude_manifest, get_distributable_files

        manifest = load_claude_manifest()
        distributable_commands = get_distributable_files(manifest, "commands")
        descriptions = manifest["commands"]["descriptions"]

        for command_file in distributable_commands:
            assert (
                command_file in descriptions
            ), f"Missing description for command: {command_file}"

    def test_agent_descriptions_are_non_empty_strings(self):
        """All agent descriptions are non-empty strings."""
        from maid_runner.cli.init import load_claude_manifest, get_distributable_files

        manifest = load_claude_manifest()
        distributable_agents = get_distributable_files(manifest, "agents")
        descriptions = manifest["agents"]["descriptions"]

        for agent_file in distributable_agents:
            description = descriptions[agent_file]
            assert isinstance(
                description, str
            ), f"Description for {agent_file} is not a string"
            assert len(description) > 0, f"Description for {agent_file} is empty"

    def test_command_descriptions_are_non_empty_strings(self):
        """All command descriptions are non-empty strings."""
        from maid_runner.cli.init import load_claude_manifest, get_distributable_files

        manifest = load_claude_manifest()
        distributable_commands = get_distributable_files(manifest, "commands")
        descriptions = manifest["commands"]["descriptions"]

        for command_file in distributable_commands:
            description = descriptions[command_file]
            assert isinstance(
                description, str
            ), f"Description for {command_file} is not a string"
            assert len(description) > 0, f"Description for {command_file} is empty"


class TestCopyClaudeFilesSelectiveDistribution:
    """Tests that copy functions only copy distributable files."""

    def test_copy_claude_agents_only_copies_distributable_files(self):
        """copy_claude_agents only copies files listed in manifest distributable."""
        from maid_runner.cli.init import (
            copy_claude_agents,
            load_claude_manifest,
            get_distributable_files,
        )

        manifest = load_claude_manifest()
        expected_files = set(get_distributable_files(manifest, "agents"))

        with tempfile.TemporaryDirectory() as tmpdir:
            copy_claude_agents(tmpdir, force=True)

            dest_agents = Path(tmpdir) / ".claude" / "agents"
            copied_files = {f.name for f in dest_agents.glob("*.md")}

            assert (
                copied_files == expected_files
            ), f"Expected {expected_files}, got {copied_files}"

    def test_copy_claude_commands_only_copies_distributable_files(self):
        """copy_claude_commands only copies files listed in manifest distributable."""
        from maid_runner.cli.init import (
            copy_claude_commands,
            load_claude_manifest,
            get_distributable_files,
        )

        manifest = load_claude_manifest()
        expected_files = set(get_distributable_files(manifest, "commands"))

        with tempfile.TemporaryDirectory() as tmpdir:
            copy_claude_commands(tmpdir, force=True)

            dest_commands = Path(tmpdir) / ".claude" / "commands"
            copied_files = {f.name for f in dest_commands.glob("*.md")}

            assert (
                copied_files == expected_files
            ), f"Expected {expected_files}, got {copied_files}"

    def test_copy_claude_agents_excludes_readme(self):
        """copy_claude_agents does not copy README.md."""
        from maid_runner.cli.init import copy_claude_agents

        with tempfile.TemporaryDirectory() as tmpdir:
            copy_claude_agents(tmpdir, force=True)

            dest_agents = Path(tmpdir) / ".claude" / "agents"
            copied_files = [f.name for f in dest_agents.glob("*")]

            assert "README.md" not in copied_files

    def test_copy_claude_commands_excludes_project_specific(self):
        """copy_claude_commands does not copy project-specific files."""
        from maid_runner.cli.init import copy_claude_commands

        project_specific_files = [
            "pypi-release.md",
            "quality-check-and-commit.md",
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            copy_claude_commands(tmpdir, force=True)

            dest_commands = Path(tmpdir) / ".claude" / "commands"
            copied_files = [f.name for f in dest_commands.glob("*.md")]

            for excluded_file in project_specific_files:
                assert (
                    excluded_file not in copied_files
                ), f"{excluded_file} should not be copied"

    def test_copy_claude_agents_creates_destination_directory(self):
        """copy_claude_agents creates .claude/agents/ directory."""
        from maid_runner.cli.init import copy_claude_agents

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_agents = Path(tmpdir) / ".claude" / "agents"
            assert not dest_agents.exists()

            copy_claude_agents(tmpdir, force=True)

            assert dest_agents.exists()
            assert dest_agents.is_dir()

    def test_copy_claude_commands_creates_destination_directory(self):
        """copy_claude_commands creates .claude/commands/ directory."""
        from maid_runner.cli.init import copy_claude_commands

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_commands = Path(tmpdir) / ".claude" / "commands"
            assert not dest_commands.exists()

            copy_claude_commands(tmpdir, force=True)

            assert dest_commands.exists()
            assert dest_commands.is_dir()
