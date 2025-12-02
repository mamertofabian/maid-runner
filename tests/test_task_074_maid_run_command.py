"""Behavioral tests for Task-074: Add /maid-run command for complete MAID workflow.

These tests verify that the maid-run.md command file:
1. Exists in the distributable commands directory
2. Is listed in manifest.json as distributable
3. Has a proper description in manifest.json
4. Contains proper command structure (description, subagent invocation)
"""

from pathlib import Path


class TestMaidRunCommandDistribution:
    """Tests for maid-run.md distribution via maid init."""

    def test_maid_run_in_distributable_commands(self):
        """maid-run.md is listed in manifest.json distributable commands."""
        from maid_runner.cli.init import load_claude_manifest, get_distributable_files

        manifest = load_claude_manifest()
        distributable_commands = get_distributable_files(manifest, "commands")

        assert (
            "maid-run.md" in distributable_commands
        ), "maid-run.md should be in distributable commands"

    def test_maid_run_file_exists_in_package(self):
        """maid-run.md file exists in maid_runner/claude/commands/ directory."""
        from maid_runner.cli.init import load_claude_manifest, get_distributable_files

        manifest = load_claude_manifest()
        distributable_commands = get_distributable_files(manifest, "commands")

        # Verify maid-run.md is in the list
        assert "maid-run.md" in distributable_commands

        # Verify the file actually exists
        init_path = Path(__file__).parent.parent / "maid_runner" / "cli" / "init.py"
        maid_runner_package = init_path.parent.parent
        command_path = maid_runner_package / "claude" / "commands" / "maid-run.md"

        assert command_path.exists(), f"maid-run.md does not exist at {command_path}"

    def test_maid_run_has_description_in_manifest(self):
        """maid-run.md has a description entry in manifest.json."""
        from maid_runner.cli.init import load_claude_manifest

        manifest = load_claude_manifest()
        descriptions = manifest["commands"]["descriptions"]

        assert (
            "maid-run.md" in descriptions
        ), "maid-run.md should have a description in manifest.json"

    def test_maid_run_description_is_non_empty(self):
        """maid-run.md description is a non-empty string."""
        from maid_runner.cli.init import load_claude_manifest

        manifest = load_claude_manifest()
        description = manifest["commands"]["descriptions"]["maid-run.md"]

        assert isinstance(description, str), "Description should be a string"
        assert len(description) > 0, "Description should not be empty"


class TestMaidRunCommandContent:
    """Tests for maid-run.md command file content structure."""

    def _get_command_content(self) -> str:
        """Helper to read the maid-run.md file content."""
        init_path = Path(__file__).parent.parent / "maid_runner" / "cli" / "init.py"
        maid_runner_package = init_path.parent.parent
        command_path = maid_runner_package / "claude" / "commands" / "maid-run.md"
        return command_path.read_text()

    def test_has_frontmatter_description(self):
        """Command file has YAML frontmatter with description."""
        content = self._get_command_content()

        assert content.startswith("---"), "Should start with YAML frontmatter"
        assert "description:" in content, "Should have description field"

    def test_has_argument_hint(self):
        """Command file has argument-hint in frontmatter."""
        content = self._get_command_content()

        assert "argument-hint:" in content, "Should have argument-hint field"

    def test_references_subagents(self):
        """Command file references MAID subagents for workflow phases."""
        content = self._get_command_content()

        # Should reference at least the core workflow agents
        assert (
            "maid-manifest-architect" in content
        ), "Should reference maid-manifest-architect"
        assert "maid-test-designer" in content, "Should reference maid-test-designer"
        assert "maid-developer" in content, "Should reference maid-developer"

    def test_references_validation_commands(self):
        """Command file references maid validate and maid test commands."""
        content = self._get_command_content()

        assert "maid validate" in content, "Should reference maid validate"
        assert "maid test" in content, "Should reference maid test"

    def test_covers_all_maid_phases(self):
        """Command file covers all MAID workflow phases."""
        content = self._get_command_content()

        # Should mention key phases
        assert "Phase 1" in content or "manifest" in content.lower()
        assert "Phase 2" in content or "test" in content.lower()
        assert "Phase 3" in content or "implement" in content.lower()

    def test_mentions_full_workflow(self):
        """Command description mentions full/complete workflow."""
        content = self._get_command_content()
        content_lower = content.lower()

        # Should indicate this is a complete workflow command
        assert (
            "full" in content_lower
            or "complete" in content_lower
            or "end-to-end" in content_lower
            or "workflow" in content_lower
        ), "Should mention full/complete workflow"
