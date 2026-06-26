"""Behavioral coverage for `maid skills install` and the user-level onboard skill.

The maid-onboard skill is packaged in maid-runner but is a user-level skill:
`maid skills install` delivers it into ~/.claude and ~/.codex (target root is
injectable for tests), while `maid init` must never install it per-repo.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _platform_supports_symlinks(tmp_path: Path) -> bool:
    probe = tmp_path / "_symlink_probe"
    try:
        probe.symlink_to(tmp_path)
    except (OSError, NotImplementedError):
        return False
    probe.unlink()
    return True


def _make_payload(root: Path) -> Path:
    """Create a fake packaged user_skills payload under root and return it."""
    claude = root / "claude" / "maid-onboard"
    claude.mkdir(parents=True)
    (claude / "SKILL.md").write_text("---\nname: maid-onboard\n---\nclaude body\n")
    codex_agents = root / "codex" / "maid-onboard" / "agents"
    codex_agents.mkdir(parents=True)
    (root / "codex" / "maid-onboard" / "SKILL.md").write_text(
        "---\nname: maid-onboard\n---\ncodex body\n"
    )
    (codex_agents / "openai.yaml").write_text(
        "interface:\n  display_name: MAID Onboard\n"
    )
    return root


def test_install_onboard_skill_copies_claude_and_codex_payload(tmp_path: Path) -> None:
    from maid_runner.core.skill_install import install_onboard_skill

    payload = _make_payload(tmp_path / "payload")
    home = tmp_path / "home"

    written = install_onboard_skill(home, payload, False)

    claude_skill = home / ".claude" / "skills" / "maid-onboard" / "SKILL.md"
    codex_skill = home / ".codex" / "skills" / "maid-onboard" / "SKILL.md"
    codex_agent = home / ".codex" / "skills" / "maid-onboard" / "agents" / "openai.yaml"
    assert claude_skill.is_file()
    assert codex_skill.is_file()
    assert codex_agent.is_file()
    assert claude_skill.read_text() == "---\nname: maid-onboard\n---\nclaude body\n"
    assert ".claude/skills/maid-onboard/SKILL.md" in written
    assert ".codex/skills/maid-onboard/agents/openai.yaml" in written


def test_install_onboard_skill_link_creates_symlink(tmp_path: Path) -> None:
    from maid_runner.core.skill_install import install_onboard_skill

    payload = _make_payload(tmp_path / "payload")
    home = tmp_path / "home"

    symlinks_supported = _platform_supports_symlinks(tmp_path)

    install_onboard_skill(home, payload, True)

    claude_skill = home / ".claude" / "skills" / "maid-onboard" / "SKILL.md"
    assert claude_skill.exists()
    if symlinks_supported:
        # On symlink-capable platforms --link must produce an actual symlink,
        # not a silent copy.
        assert os.path.islink(claude_skill)
    assert claude_skill.read_text() == "---\nname: maid-onboard\n---\nclaude body\n"


def test_install_onboard_skill_is_idempotent(tmp_path: Path) -> None:
    from maid_runner.core.skill_install import install_onboard_skill

    payload = _make_payload(tmp_path / "payload")
    home = tmp_path / "home"

    install_onboard_skill(home, payload, False)
    written = install_onboard_skill(home, payload, False)

    assert (home / ".claude" / "skills" / "maid-onboard" / "SKILL.md").is_file()
    assert ".claude/skills/maid-onboard/SKILL.md" in written


def test_skills_install_command_installs_to_target_root(tmp_path: Path) -> None:
    from maid_runner.cli.commands.skills import cmd_skills
    from maid_runner.cli.commands._main import main

    assert callable(cmd_skills)
    home = tmp_path / "home"

    exit_code = main(["skills", "install", "--target-root", str(home)])

    assert exit_code == 0
    claude_skill = home / ".claude" / "skills" / "maid-onboard" / "SKILL.md"
    codex_skill = home / ".codex" / "skills" / "maid-onboard" / "SKILL.md"
    assert claude_skill.is_file()
    assert codex_skill.is_file()
    assert (
        home / ".codex" / "skills" / "maid-onboard" / "agents" / "openai.yaml"
    ).is_file()
    for skill_text in (claude_skill.read_text(), codex_skill.read_text()):
        normalized_skill_text = " ".join(skill_text.split())
        assert (
            "maid recall --for-manifest manifests/drafts/<slug>.manifest.yaml --plan-packet"
            in skill_text
        )
        assert "before promoting the selected draft" in skill_text
        assert "Recall is advisory planning context only" in skill_text
        assert "does not expand scope or replace red evidence" in normalized_skill_text
        for boundary in (
            "behavioral validation",
            "plan lock",
            "implementation validation",
            "review",
        ):
            assert boundary in normalized_skill_text


def test_sync_user_skills_packages_onboard_skill(tmp_path: Path, monkeypatch) -> None:
    from scripts.sync_claude_files import sync_user_skills

    for tool in ("claude", "codex"):
        src = tmp_path / f".{tool}" / "skills" / "maid-onboard"
        (src / "agents").mkdir(parents=True)
        (src / "SKILL.md").write_text(f"---\nname: maid-onboard\n---\n{tool}\n")
        (src / "agents" / "openai.yaml").write_text("interface:\n  display_name: x\n")
    monkeypatch.chdir(tmp_path)

    sync_user_skills()

    base = tmp_path / "maid_runner" / "user_skills"
    assert (base / "claude" / "maid-onboard" / "SKILL.md").is_file()
    assert (base / "codex" / "maid-onboard" / "SKILL.md").is_file()
    assert (base / "codex" / "maid-onboard" / "agents" / "openai.yaml").is_file()


def test_install_onboard_skill_link_falls_back_to_copy_when_unsupported(
    tmp_path: Path, monkeypatch
) -> None:
    from maid_runner.core import skill_install

    payload = _make_payload(tmp_path / "payload")
    home = tmp_path / "home"

    def _no_symlinks(*_args, **_kwargs):
        raise OSError("symlinks disabled")

    monkeypatch.setattr(skill_install.Path, "symlink_to", _no_symlinks)

    skill_install.install_onboard_skill(home, payload, True)

    claude_skill = home / ".claude" / "skills" / "maid-onboard" / "SKILL.md"
    assert claude_skill.is_file()
    assert not os.path.islink(claude_skill)
    assert claude_skill.read_text() == "---\nname: maid-onboard\n---\nclaude body\n"


def test_skills_install_command_reports_copy_fallback(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from maid_runner.cli.commands import skills as skills_mod
    from maid_runner.cli.commands._main import main

    def _no_symlinks(*_args, **_kwargs):
        raise OSError("symlinks disabled")

    monkeypatch.setattr(skills_mod.Path, "symlink_to", _no_symlinks)
    home = tmp_path / "home"

    exit_code = main(["skills", "install", "--link", "--target-root", str(home)])

    assert exit_code == 0
    output = capsys.readouterr().out
    # When symlinks are unavailable the command must not claim it linked.
    assert "Linked" not in output
    assert "symlinks unavailable" in output.lower()


def test_install_onboard_skill_requires_both_tool_payloads(tmp_path: Path) -> None:
    import pytest

    from maid_runner.core.skill_install import install_onboard_skill

    payload = tmp_path / "payload"
    claude = payload / "claude" / "maid-onboard"
    claude.mkdir(parents=True)
    (claude / "SKILL.md").write_text("only claude\n")
    home = tmp_path / "home"

    with pytest.raises(FileNotFoundError):
        install_onboard_skill(home, payload, False)


def test_install_onboard_skill_prunes_stale_files(tmp_path: Path) -> None:
    from maid_runner.core.skill_install import install_onboard_skill

    payload = _make_payload(tmp_path / "payload")
    home = tmp_path / "home"

    install_onboard_skill(home, payload, False)
    stale = home / ".claude" / "skills" / "maid-onboard" / "STALE.md"
    stale.write_text("left over from an older payload\n")

    install_onboard_skill(home, payload, False)

    assert not stale.exists()
    assert (home / ".claude" / "skills" / "maid-onboard" / "SKILL.md").is_file()


def test_onboard_skill_absent_from_per_repo_init_distributable() -> None:
    claude = json.loads(
        (PROJECT_ROOT / "maid_runner" / "claude" / "manifest.json").read_text()
    )
    codex = json.loads(
        (PROJECT_ROOT / "maid_runner" / "codex" / "manifest.json").read_text()
    )
    assert "maid-onboard" not in claude["skills"]["distributable"]
    assert "maid-onboard" not in codex["skills"]["distributable"]
