"""Behavioral tests for Task-152c: Create init_tools/windsurf.py module.

Tests verify that:
1. setup_windsurf() function exists and sets up Windsurf IDE rules
2. create_windsurf_rules() creates .windsurf/rules/ directory and maid-runner.md file
3. The .md file contains MAID methodology content
"""

from maid_runner.cli.init_tools.windsurf import create_windsurf_rules, setup_windsurf


class TestSetupWindsurf:
    """Test setup_windsurf() function."""

    def test_setup_windsurf_creates_rules(self, tmp_path):
        """Verify setup_windsurf creates Windsurf rules."""
        setup_windsurf(str(tmp_path), force=True, dry_run=False)

        assert (tmp_path / ".windsurf" / "rules").exists()
        assert (tmp_path / ".windsurf" / "rules" / "maid-runner.md").exists()


class TestCreateWindsurfRules:
    """Test create_windsurf_rules() function."""

    def test_creates_rules_directory(self, tmp_path):
        """Verify Windsurf setup creates .windsurf/rules/ directory."""
        create_windsurf_rules(str(tmp_path), force=True, dry_run=False)

        rules_dir = tmp_path / ".windsurf" / "rules"
        assert rules_dir.exists()
        assert rules_dir.is_dir()

    def test_creates_maid_runner_md_file(self, tmp_path):
        """Verify Windsurf setup creates maid-runner.md file."""
        create_windsurf_rules(str(tmp_path), force=True, dry_run=False)

        rule_file = tmp_path / ".windsurf" / "rules" / "maid-runner.md"
        assert rule_file.exists()

    def test_md_contains_maid_content(self, tmp_path):
        """Verify Windsurf .md file contains MAID methodology content."""
        create_windsurf_rules(str(tmp_path), force=True, dry_run=False)

        rule_file = tmp_path / ".windsurf" / "rules" / "maid-runner.md"
        content = rule_file.read_text()

        assert "MAID Methodology" in content
        assert "Manifest-driven AI Development" in content

    def test_dry_run_shows_create_action(self, tmp_path, capsys):
        """Verify dry_run shows [CREATE] action for new file."""
        create_windsurf_rules(str(tmp_path), force=False, dry_run=True)

        captured = capsys.readouterr()
        assert "[CREATE]" in captured.out
        assert "maid-runner.md" in captured.out

        # File should NOT be created in dry run
        rule_file = tmp_path / ".windsurf" / "rules" / "maid-runner.md"
        assert not rule_file.exists()

    def test_dry_run_shows_update_action_for_existing_file(self, tmp_path, capsys):
        """Verify dry_run shows [UPDATE] action for existing file."""
        # First create the file
        create_windsurf_rules(str(tmp_path), force=True, dry_run=False)

        # Now run dry_run - should show UPDATE
        create_windsurf_rules(str(tmp_path), force=False, dry_run=True)

        captured = capsys.readouterr()
        assert "[UPDATE]" in captured.out
        assert "maid-runner.md" in captured.out

    def test_existing_file_without_force_warns_user(self, tmp_path, capsys):
        """Verify existing file without force shows warning."""
        # First create the file
        create_windsurf_rules(str(tmp_path), force=True, dry_run=False)

        # Now try without force - should warn
        create_windsurf_rules(str(tmp_path), force=False, dry_run=False)

        captured = capsys.readouterr()
        assert "already exists" in captured.out
        assert "--force" in captured.out
