"""Behavioral tests for Task-031: 'maid init' CLI command.

Tests verify that the init command:
1. Creates necessary directory structure (manifests/, tests/, .maid/docs/)
2. Creates an example manifest file
3. Copies maid_specs.md to .maid/docs/
4. Generates proper MAID documentation content
5. Handles CLAUDE.md creation/update with user confirmation
"""

import json
from unittest.mock import patch

from maid_runner.cli.init import (
    copy_maid_specs,
    create_directories,
    create_example_manifest,
    generate_claude_md_content,
    handle_claude_md,
    run_init,
)


class TestCreateDirectories:
    """Test directory creation functionality."""

    def test_creates_manifests_directory(self, tmp_path):
        """Verify manifests/ directory is created."""
        create_directories(str(tmp_path))
        assert (tmp_path / "manifests").exists()
        assert (tmp_path / "manifests").is_dir()

    def test_creates_tests_directory(self, tmp_path):
        """Verify tests/ directory is created."""
        create_directories(str(tmp_path))
        assert (tmp_path / "tests").exists()
        assert (tmp_path / "tests").is_dir()

    def test_creates_maid_docs_directory(self, tmp_path):
        """Verify .maid/docs/ directory is created."""
        create_directories(str(tmp_path))
        assert (tmp_path / ".maid" / "docs").exists()
        assert (tmp_path / ".maid" / "docs").is_dir()

    def test_does_not_fail_if_directories_exist(self, tmp_path):
        """Verify idempotency - no error if directories already exist."""
        (tmp_path / "manifests").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / ".maid" / "docs").mkdir(parents=True)
        create_directories(str(tmp_path))  # Should not raise
        assert (tmp_path / "manifests").exists()
        assert (tmp_path / "tests").exists()
        assert (tmp_path / ".maid" / "docs").exists()


class TestCreateExampleManifest:
    """Test example manifest creation."""

    def test_creates_example_manifest_file(self, tmp_path):
        """Verify example manifest file is created."""
        (tmp_path / "manifests").mkdir()
        create_example_manifest(str(tmp_path))
        example_file = tmp_path / "manifests" / "example.manifest.json"
        assert example_file.exists()

    def test_example_manifest_is_valid_json(self, tmp_path):
        """Verify example manifest contains valid JSON."""
        (tmp_path / "manifests").mkdir()
        create_example_manifest(str(tmp_path))
        example_file = tmp_path / "manifests" / "example.manifest.json"
        with open(example_file) as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_example_manifest_has_required_fields(self, tmp_path):
        """Verify example manifest includes all required MAID fields."""
        (tmp_path / "manifests").mkdir()
        create_example_manifest(str(tmp_path))
        example_file = tmp_path / "manifests" / "example.manifest.json"
        with open(example_file) as f:
            data = json.load(f)

        required_fields = [
            "goal",
            "taskType",
            "creatableFiles",
            "editableFiles",
            "readonlyFiles",
            "expectedArtifacts",
            "validationCommand",
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"


class TestCopyMaidSpecs:
    """Test MAID specification document copying."""

    def test_copies_maid_specs_to_target_directory(self, tmp_path):
        """Verify maid_specs.md is copied to .maid/docs/."""
        (tmp_path / ".maid" / "docs").mkdir(parents=True)
        copy_maid_specs(str(tmp_path))
        maid_specs = tmp_path / ".maid" / "docs" / "maid_specs.md"
        assert maid_specs.exists()

    def test_copied_file_is_not_empty(self, tmp_path):
        """Verify copied maid_specs.md contains content."""
        (tmp_path / ".maid" / "docs").mkdir(parents=True)
        copy_maid_specs(str(tmp_path))
        maid_specs = tmp_path / ".maid" / "docs" / "maid_specs.md"
        content = maid_specs.read_text()
        assert len(content) > 0
        assert "MAID" in content

    def test_handles_missing_source_gracefully(self, tmp_path):
        """Verify graceful handling when source maid_specs.md not found."""
        (tmp_path / ".maid" / "docs").mkdir(parents=True)

        # The function should print a warning but not raise when source is missing
        # This test just verifies it doesn't crash
        copy_maid_specs(str(tmp_path))  # Should not raise


class TestGenerateClaudeMdContent:
    """Test CLAUDE.md content generation."""

    def test_returns_string_content(self):
        """Verify function returns a string."""
        content = generate_claude_md_content("python")
        assert isinstance(content, str)
        assert len(content) > 0

    def test_includes_maid_workflow_phases(self):
        """Verify content includes MAID workflow phases."""
        content = generate_claude_md_content("python")
        assert "Phase 1" in content or "Goal Definition" in content
        assert "Phase 2" in content or "Planning Loop" in content
        assert "Phase 3" in content or "Implementation" in content

    def test_includes_manifest_template(self):
        """Verify content includes manifest template."""
        content = generate_claude_md_content("python")
        assert "goal" in content
        assert "expectedArtifacts" in content
        assert "validationCommand" in content

    def test_includes_validation_commands(self):
        """Verify content includes MAID CLI commands."""
        content = generate_claude_md_content("python")
        assert "maid validate" in content

    def test_mentions_ai_agents(self):
        """Verify content mentions MAID-compatible AI agents."""
        content = generate_claude_md_content("python")
        assert "AI" in content or "agent" in content.lower()

    def test_references_local_maid_specs(self):
        """Verify content references .maid/docs/maid_specs.md."""
        content = generate_claude_md_content("python")
        assert ".maid/docs/maid_specs.md" in content


class TestHandleClaudeMd:
    """Test CLAUDE.md file handling."""

    def test_creates_claude_md_if_not_exists(self, tmp_path):
        """Verify CLAUDE.md is created when it doesn't exist."""
        handle_claude_md(str(tmp_path), force=False)
        claude_md = tmp_path / "CLAUDE.md"
        assert claude_md.exists()

    def test_created_file_contains_maid_content(self, tmp_path):
        """Verify created CLAUDE.md contains MAID documentation."""
        handle_claude_md(str(tmp_path), force=False)
        claude_md = tmp_path / "CLAUDE.md"
        content = claude_md.read_text()
        assert "MAID" in content
        assert len(content) > 100

    @patch("builtins.input", return_value="a")
    def test_appends_to_existing_file_when_user_chooses_append(
        self, mock_input, tmp_path
    ):
        """Verify content is appended when user chooses 'append'."""
        claude_md = tmp_path / "CLAUDE.md"
        existing_content = "# Existing Project Documentation\n\nSome content here."
        claude_md.write_text(existing_content)

        handle_claude_md(str(tmp_path), force=False)

        content = claude_md.read_text()
        assert existing_content in content
        assert "MAID" in content

    @patch("builtins.input", return_value="o")
    def test_overwrites_when_user_chooses_overwrite(self, mock_input, tmp_path):
        """Verify file is overwritten when user chooses 'overwrite'."""
        claude_md = tmp_path / "CLAUDE.md"
        existing_content = "# Existing Project Documentation"
        claude_md.write_text(existing_content)

        handle_claude_md(str(tmp_path), force=False)

        content = claude_md.read_text()
        assert existing_content not in content
        assert "MAID" in content

    @patch("builtins.input", return_value="s")
    def test_skips_when_user_chooses_skip(self, mock_input, tmp_path):
        """Verify file is unchanged when user chooses 'skip'."""
        claude_md = tmp_path / "CLAUDE.md"
        existing_content = "# Existing Project Documentation"
        claude_md.write_text(existing_content)

        handle_claude_md(str(tmp_path), force=False)

        content = claude_md.read_text()
        assert content == existing_content

    def test_force_overwrites_without_prompt(self, tmp_path):
        """Verify force flag overwrites without prompting."""
        claude_md = tmp_path / "CLAUDE.md"
        existing_content = "# Existing Project Documentation"
        claude_md.write_text(existing_content)

        # Should not prompt with force=True
        handle_claude_md(str(tmp_path), force=True)

        content = claude_md.read_text()
        assert existing_content not in content
        assert "MAID" in content


class TestRunInit:
    """Test main run_init function."""

    @patch("builtins.input", return_value="s")
    def test_creates_complete_structure(self, mock_input, tmp_path):
        """Verify run_init creates all necessary files and directories."""
        run_init(str(tmp_path), force=False)

        # Check directories
        assert (tmp_path / "manifests").exists()
        assert (tmp_path / "tests").exists()
        assert (tmp_path / ".maid" / "docs").exists()

        # Check files (example.manifest.json no longer created - use maid snapshot)
        assert (tmp_path / ".maid" / "docs" / "maid_specs.md").exists()
        assert (tmp_path / "CLAUDE.md").exists()

    def test_with_force_flag(self, tmp_path):
        """Verify force flag bypasses prompts."""
        # Pre-create CLAUDE.md
        (tmp_path / "CLAUDE.md").write_text("Old content")

        run_init(str(tmp_path), force=True)

        # Should overwrite without prompting
        content = (tmp_path / "CLAUDE.md").read_text()
        assert "Old content" not in content
        assert "MAID" in content
