"""Behavioral coverage for Codex init honoring the distributable skill list.

`maid init --tool codex` must install only the skills declared distributable in
the packaged Codex manifest, never the repo-internal maid-runner-* or
maid-validate-hardening skills, and the AGENTS.md guidance it writes must
describe the generic MAID workflow rather than maid-runner-specific skills.
"""

from __future__ import annotations

import json


GENERIC_CODEX_SKILLS = [
    "maid-implementation-review",
    "maid-implementer",
    "maid-plan-review",
    "maid-planner",
]

REPO_INTERNAL_CODEX_SKILLS = [
    "maid-runner-cleanup-and-refactor",
    "maid-runner-draft-implement",
    "maid-runner-performance-optimization",
    "maid-runner-self-improvement",
    "maid-validate-hardening",
]


def test_codex_init_installs_only_distributable_skills(tmp_path, monkeypatch) -> None:
    from maid_runner.cli.commands.init import cmd_init
    from maid_runner.cli.commands._main import main

    monkeypatch.chdir(tmp_path)
    assert callable(cmd_init)

    exit_code = main(["init", "--tool", "codex"])

    assert exit_code == 0
    skills_dir = tmp_path / ".codex" / "skills"
    installed = sorted(path.name for path in skills_dir.iterdir())
    assert installed == GENERIC_CODEX_SKILLS
    for internal in REPO_INTERNAL_CODEX_SKILLS:
        assert not (skills_dir / internal).exists()


def test_codex_init_agents_md_describes_generic_workflow(tmp_path, monkeypatch) -> None:
    from maid_runner.cli.commands.init import cmd_init
    from maid_runner.cli.commands._main import main

    monkeypatch.chdir(tmp_path)
    assert callable(cmd_init)

    main(["init", "--tool", "codex"])

    agents_md = (tmp_path / "AGENTS.md").read_text()
    assert "maid-planner" in agents_md
    assert "maid-plan-review" in agents_md
    assert "maid-implementer" in agents_md
    assert "maid-implementation-review" in agents_md
    assert "maid-runner-" not in agents_md
    assert "maid-validate-hardening" not in agents_md


def test_codex_payload_manifest_distributable_excludes_repo_internal_skills(
    tmp_path, monkeypatch
) -> None:
    from scripts.sync_claude_files import sync_codex_payload

    source_skills = tmp_path / ".codex" / "skills"
    for skill in GENERIC_CODEX_SKILLS + REPO_INTERNAL_CODEX_SKILLS:
        agents_dir = source_skills / skill / "agents"
        agents_dir.mkdir(parents=True)
        (source_skills / skill / "SKILL.md").write_text(f"---\nname: {skill}\n---\n")
        (agents_dir / "openai.yaml").write_text(f"name: {skill}\n")
    monkeypatch.chdir(tmp_path)

    sync_codex_payload()

    manifest = json.loads(
        (tmp_path / "maid_runner" / "codex" / "manifest.json").read_text()
    )
    distributable = manifest["skills"]["distributable"]
    assert sorted(distributable) == GENERIC_CODEX_SKILLS
    for internal in REPO_INTERNAL_CODEX_SKILLS:
        assert internal not in distributable
        assert internal not in manifest["skills"].get("descriptions", {})
