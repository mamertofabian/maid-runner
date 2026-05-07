"""Tests for CLI 'maid init' command (v2)."""

from __future__ import annotations

import os
from pathlib import Path


MAID_SECTION_START = "<!-- BEGIN MAID RUNNER -->"
MAID_SECTION_END = "<!-- END MAID RUNNER -->"


class TestCmdInit:
    def test_init_creates_manifests_dir_and_config(self, tmp_path):
        from maid_runner.cli.commands._main import main

        os.chdir(tmp_path)
        exit_code = main(["init"])
        assert exit_code == 0
        assert (tmp_path / "manifests").is_dir()
        assert (tmp_path / ".maidrc.yaml").is_file()

    def test_init_dry_run_does_not_create(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(tmp_path)
        exit_code = main(["init", "--dry-run"])
        assert exit_code == 0
        assert not (tmp_path / "manifests").exists()
        assert not (tmp_path / ".maidrc.yaml").exists()
        captured = capsys.readouterr()
        assert "Would create" in captured.out

    def test_init_already_initialized_returns_2(self, tmp_path):
        from maid_runner.cli.commands._main import main

        os.chdir(tmp_path)
        # Initialize first
        main(["init"])
        # Try again without --force
        exit_code = main(["init"])
        assert exit_code == 2

    def test_init_force_reinitializes(self, tmp_path):
        from maid_runner.cli.commands._main import main

        os.chdir(tmp_path)
        main(["init"])
        exit_code = main(["init", "--force"])
        assert exit_code == 0

    def test_init_config_contains_schema_version(self, tmp_path):
        from maid_runner.cli.commands._main import main

        os.chdir(tmp_path)
        main(["init"])
        content = (tmp_path / ".maidrc.yaml").read_text()
        assert "schema_version: 2" in content

    def test_init_claude_creates_repo_level_maid_assets(self, tmp_path, monkeypatch):
        from maid_runner.cli.commands.init import cmd_init
        from maid_runner.cli.commands._main import main

        monkeypatch.chdir(tmp_path)
        assert callable(cmd_init)
        exit_code = main(["init", "--tool", "claude"])

        assert exit_code == 0
        assert (tmp_path / "manifests").is_dir()
        assert (tmp_path / ".maidrc.yaml").is_file()
        assert (tmp_path / ".claude" / "manifest.json").is_file()
        assert (tmp_path / ".claude" / "skills" / "maid-planner" / "SKILL.md").is_file()
        assert (
            tmp_path / ".claude" / "skills" / "maid-plan-review" / "SKILL.md"
        ).is_file()
        assert (
            tmp_path / ".claude" / "skills" / "maid-implementation-review" / "SKILL.md"
        ).is_file()
        assert (
            tmp_path / ".claude" / "skills" / "maid-incident-logger" / "SKILL.md"
        ).is_file()
        installed_agents = sorted(
            path.name for path in (tmp_path / ".claude" / "agents").glob("*.md")
        )
        assert installed_agents == ["maid-implementation-reviewer.md"]
        assert not (tmp_path / ".claude" / "commands").exists()
        assert not (tmp_path / ".claude" / "commands" / "pypi-release.md").exists()

        claude_md = (tmp_path / "CLAUDE.md").read_text()
        assert MAID_SECTION_START in claude_md
        assert MAID_SECTION_END in claude_md
        assert "maid-planner" in claude_md
        assert "maid-implementation-review" in claude_md
        assert "Available MAID slash commands" not in claude_md

    def test_init_claude_dry_run_reports_assets_without_creating_them(
        self, tmp_path, capsys, monkeypatch
    ):
        from maid_runner.cli.commands._main import main

        monkeypatch.chdir(tmp_path)
        exit_code = main(["init", "--tool", "claude", "--dry-run"])

        assert exit_code == 0
        assert not (tmp_path / "manifests").exists()
        assert not (tmp_path / ".maidrc.yaml").exists()
        assert not (tmp_path / ".claude").exists()
        assert not (tmp_path / "CLAUDE.md").exists()
        captured = capsys.readouterr()
        assert "Would create: .claude/skills/maid-planner/SKILL.md" in captured.out
        assert (
            "Would create: .claude/agents/maid-implementation-reviewer.md"
            in captured.out
        )
        assert "Would create: .claude/commands/" not in captured.out
        assert "Would update: CLAUDE.md" in captured.out

    def test_init_claude_force_replaces_only_marked_claude_md_section(
        self, tmp_path, monkeypatch
    ):
        from maid_runner.cli.commands._main import main

        monkeypatch.chdir(tmp_path)
        Path("CLAUDE.md").write_text(
            "Project heading\n\n"
            f"{MAID_SECTION_START}\n"
            "stale MAID instructions\n"
            f"{MAID_SECTION_END}\n\n"
            "Project footer\n"
        )
        main(["init", "--tool", "claude"])
        Path(".claude/manifest.json").write_text(
            """
{
  "agents": {"distributable": ["maid-developer.md"]},
  "commands": {"distributable": ["plan.md"]},
  "skills": {"distributable": ["old-skill"]}
}
""".strip()
        )
        Path(".claude/commands").mkdir(parents=True)
        Path(".claude/commands/plan.md").write_text("stale command\n")
        Path(".claude/commands/custom.md").write_text("custom command\n")
        Path(".claude/agents/maid-developer.md").write_text("stale agent\n")
        Path(".claude/agents/custom-agent.md").write_text("custom agent\n")
        Path(".claude/skills/old-skill").mkdir(parents=True)
        Path(".claude/skills/old-skill/SKILL.md").write_text("stale skill\n")
        Path(".claude/skills/custom-skill").mkdir(parents=True)
        Path(".claude/skills/custom-skill/SKILL.md").write_text("custom skill\n")

        exit_code = main(["init", "--tool", "claude", "--force"])

        assert exit_code == 0
        claude_md = Path("CLAUDE.md").read_text()
        assert "Project heading" in claude_md
        assert "Project footer" in claude_md
        assert "stale MAID instructions" not in claude_md
        assert claude_md.count(MAID_SECTION_START) == 1
        assert claude_md.count(MAID_SECTION_END) == 1
        assert "maid-plan-review" in claude_md
        installed_agents = sorted(
            path.name for path in Path(".claude/agents").glob("*.md")
        )
        installed_skills = sorted(
            path.name for path in Path(".claude/skills").iterdir()
        )
        assert not Path(".claude/commands/plan.md").exists()
        assert Path(".claude/commands/custom.md").is_file()
        assert "custom-agent.md" in installed_agents
        assert "maid-developer.md" not in installed_agents
        assert "maid-implementation-reviewer.md" in installed_agents
        assert "custom-skill" in installed_skills
        assert "old-skill" not in installed_skills

    def test_init_non_claude_tool_does_not_create_claude_assets(
        self, tmp_path, monkeypatch
    ):
        from maid_runner.cli.commands._main import main

        monkeypatch.chdir(tmp_path)
        exit_code = main(["init", "--tool", "generic"])

        assert exit_code == 0
        assert (tmp_path / "manifests").is_dir()
        assert (tmp_path / ".maidrc.yaml").is_file()
        assert not (tmp_path / ".claude").exists()
        assert not (tmp_path / "CLAUDE.md").exists()
