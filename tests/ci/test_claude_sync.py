"""Tests for Claude integration payload synchronization."""

from __future__ import annotations

import json
from pathlib import Path


def _write_minimal_claude_source(project: Path) -> None:
    claude = project / ".claude"
    (claude / "agents").mkdir(parents=True)
    (claude / "commands").mkdir(parents=True)
    (project / "skills" / "maid-planner").mkdir(parents=True)

    (claude / "manifest.json").write_text(
        json.dumps(
            {
                "agents": {"distributable": ["maid-agent.md"]},
                "commands": {"distributable": ["plan.md"]},
                "skills": {"distributable": ["maid-planner"]},
            }
        )
    )
    (claude / "agents" / "maid-agent.md").write_text("---\nname: maid-agent\n---\n")
    (claude / "agents" / "ignored-agent.md").write_text(
        "---\nname: ignored-agent\n---\n"
    )
    (claude / "commands" / "plan.md").write_text("plan command\n")
    (claude / "commands" / "ignored.md").write_text("ignored command\n")
    (project / "skills" / "maid-planner" / "SKILL.md").write_text(
        "---\nname: maid-planner\n---\n"
    )
    (project / "skills" / "maid-planner" / "agents").mkdir()
    (project / "skills" / "maid-planner" / "agents" / "openai.yaml").write_text(
        "display_name: Codex metadata\n"
    )


def test_sync_claude_files_copies_manifest_declared_skills(
    tmp_path, monkeypatch
) -> None:
    from scripts.sync_claude_files import main, sync_agents, sync_commands, sync_skills

    _write_minimal_claude_source(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert callable(sync_agents)
    assert callable(sync_commands)
    assert callable(sync_skills)
    main()

    dest = tmp_path / "maid_runner" / "claude"
    assert (dest / "manifest.json").is_file()
    assert (dest / "agents" / "maid-agent.md").is_file()
    assert (dest / "commands" / "plan.md").is_file()
    assert (dest / "skills" / "maid-planner" / "SKILL.md").is_file()
    assert not (dest / "skills" / "maid-planner" / "agents" / "openai.yaml").exists()
    assert not (dest / "agents" / "ignored-agent.md").exists()
    assert not (dest / "commands" / "ignored.md").exists()


def test_sync_claude_files_prunes_stale_generated_payloads(
    tmp_path, monkeypatch
) -> None:
    from scripts.sync_claude_files import main, sync_agents, sync_commands, sync_skills

    _write_minimal_claude_source(tmp_path)
    assert callable(sync_agents)
    assert callable(sync_commands)
    assert callable(sync_skills)
    stale_root = tmp_path / "maid_runner" / "claude"
    (stale_root / "skills" / "old-skill").mkdir(parents=True)
    (stale_root / "skills" / "old-skill" / "SKILL.md").write_text("old\n")
    (stale_root / "commands").mkdir(parents=True)
    (stale_root / "commands" / "old.md").write_text("old\n")
    (stale_root / "agents").mkdir(parents=True)
    (stale_root / "agents" / "old.md").write_text("old\n")
    monkeypatch.chdir(tmp_path)

    main()

    assert not (stale_root / "skills" / "old-skill").exists()
    assert not (stale_root / "commands" / "old.md").exists()
    assert not (stale_root / "agents" / "old.md").exists()
