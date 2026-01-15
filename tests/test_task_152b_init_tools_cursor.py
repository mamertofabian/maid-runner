"""Behavioral tests for Task-152b: Create init_tools/cursor.py module.

Tests verify that:
1. setup_cursor() function exists and sets up Cursor IDE rules
2. create_cursor_rules() creates .cursor/rules/ directory and maid-runner.mdc file
3. The .mdc file has proper YAML frontmatter and MAID content
"""

from maid_runner.cli.init_tools.cursor import create_cursor_rules, setup_cursor


class TestSetupCursor:
    """Test setup_cursor() function."""

    def test_setup_cursor_creates_rules(self, tmp_path):
        """Verify setup_cursor creates Cursor rules."""
        setup_cursor(str(tmp_path), force=True, dry_run=False)

        assert (tmp_path / ".cursor" / "rules").exists()
        assert (tmp_path / ".cursor" / "rules" / "maid-runner.mdc").exists()


class TestCreateCursorRules:
    """Test create_cursor_rules() function."""

    def test_creates_rules_directory(self, tmp_path):
        """Verify Cursor setup creates .cursor/rules/ directory."""
        create_cursor_rules(str(tmp_path), force=True, dry_run=False)

        rules_dir = tmp_path / ".cursor" / "rules"
        assert rules_dir.exists()
        assert rules_dir.is_dir()

    def test_creates_maid_runner_mdc_file(self, tmp_path):
        """Verify Cursor setup creates maid-runner.mdc file."""
        create_cursor_rules(str(tmp_path), force=True, dry_run=False)

        rule_file = tmp_path / ".cursor" / "rules" / "maid-runner.mdc"
        assert rule_file.exists()

    def test_mdc_has_yaml_frontmatter(self, tmp_path):
        """Verify Cursor .mdc file has proper YAML frontmatter."""
        create_cursor_rules(str(tmp_path), force=True, dry_run=False)

        rule_file = tmp_path / ".cursor" / "rules" / "maid-runner.mdc"
        content = rule_file.read_text()

        assert "---" in content
        assert "description:" in content
        assert "globs:" in content
        assert "alwaysApply:" in content

    def test_mdc_contains_maid_content(self, tmp_path):
        """Verify Cursor .mdc file contains MAID methodology content."""
        create_cursor_rules(str(tmp_path), force=True, dry_run=False)

        rule_file = tmp_path / ".cursor" / "rules" / "maid-runner.mdc"
        content = rule_file.read_text()

        assert "MAID Methodology" in content
        assert "Manifest-driven AI Development" in content

    def test_dry_run_shows_create_action(self, tmp_path, capsys):
        """Verify dry_run shows [CREATE] action for new file."""
        create_cursor_rules(str(tmp_path), force=False, dry_run=True)

        captured = capsys.readouterr()
        assert "[CREATE]" in captured.out
        assert "maid-runner.mdc" in captured.out

        # File should NOT be created in dry run
        rule_file = tmp_path / ".cursor" / "rules" / "maid-runner.mdc"
        assert not rule_file.exists()

    def test_dry_run_shows_update_action_for_existing_file(self, tmp_path, capsys):
        """Verify dry_run shows [UPDATE] action for existing file."""
        # First create the file
        create_cursor_rules(str(tmp_path), force=True, dry_run=False)

        # Now run dry_run - should show UPDATE
        create_cursor_rules(str(tmp_path), force=False, dry_run=True)

        captured = capsys.readouterr()
        assert "[UPDATE]" in captured.out
        assert "maid-runner.mdc" in captured.out

    def test_existing_file_without_force_warns_user(self, tmp_path, capsys):
        """Verify existing file without force shows warning."""
        # First create the file
        create_cursor_rules(str(tmp_path), force=True, dry_run=False)

        # Now try without force - should warn
        create_cursor_rules(str(tmp_path), force=False, dry_run=False)

        captured = capsys.readouterr()
        assert "already exists" in captured.out
        assert "--force" in captured.out
