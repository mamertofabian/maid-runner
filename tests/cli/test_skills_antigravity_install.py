"""Behavioral tests for Antigravity user-level `maid-onboard` skill packaging, install, and uninstall."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib

from maid_runner.cli.commands._main import main
from maid_runner.core.skill_install import (
    install_onboard_skill,
    uninstall_onboard_skill,
)
from scripts.sync_claude_files import sync_user_skills


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _platform_supports_symlinks(tmp_path: Path) -> bool:
    probe = tmp_path / "_symlink_probe"
    try:
        probe.symlink_to(tmp_path)
    except (OSError, NotImplementedError):
        return False
    probe.unlink()
    return True


def _make_payload(root: Path, *, include_antigravity: bool = True) -> Path:
    tools = (
        ("claude", "codex", "antigravity")
        if include_antigravity
        else ("claude", "codex")
    )
    for tool in tools:
        skill_dir = root / tool / "maid-onboard"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: maid-onboard\n---\n{tool} onboard body\n",
            encoding="utf-8",
        )
    return root


def test_sync_user_skills_packages_antigravity_onboard_from_canonical_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    shutil.copytree(
        PROJECT_ROOT / ".claude" / "skills" / "maid-onboard",
        workspace / ".claude" / "skills" / "maid-onboard",
    )
    shutil.copytree(
        PROJECT_ROOT / ".codex" / "skills" / "maid-onboard",
        workspace / ".codex" / "skills" / "maid-onboard",
    )
    monkeypatch.chdir(workspace)

    sync_user_skills()

    synced_agy = (
        workspace
        / "maid_runner"
        / "user_skills"
        / "antigravity"
        / "maid-onboard"
        / "SKILL.md"
    )
    canonical = (
        workspace / ".claude" / "skills" / "maid-onboard" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert synced_agy.is_file()
    assert synced_agy.read_text(encoding="utf-8") == canonical

    committed_agy = (
        PROJECT_ROOT
        / "maid_runner"
        / "user_skills"
        / "antigravity"
        / "maid-onboard"
        / "SKILL.md"
    )
    assert committed_agy.is_file()
    assert committed_agy.read_text(encoding="utf-8") == canonical
    assert (
        "maid init --tool antigravity" in canonical or "--tool antigravity" in canonical
    )
    assert ".agents/skills" in canonical
    assert "~/.gemini/config/skills" in canonical

    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]["maid_runner"]
    assert "user_skills/antigravity/*/SKILL.md" in package_data

    agy_init_manifest = json.loads(
        (PROJECT_ROOT / "maid_runner" / "antigravity" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert "maid-onboard" not in agy_init_manifest["skills"]["distributable"]


def test_install_onboard_skill_delivers_antigravity_under_gemini_config_and_links(
    tmp_path: Path,
) -> None:
    payload = _make_payload(tmp_path / "payload", include_antigravity=True)
    home = tmp_path / "home"

    written = install_onboard_skill(home, payload, False)

    agy_skill = home / ".gemini" / "config" / "skills" / "maid-onboard" / "SKILL.md"
    assert agy_skill.is_file()
    assert agy_skill.read_text(encoding="utf-8") == (
        "---\nname: maid-onboard\n---\nantigravity onboard body\n"
    )
    assert ".gemini/config/skills/maid-onboard/SKILL.md" in written
    assert ".claude/skills/maid-onboard/SKILL.md" in written
    assert ".codex/skills/maid-onboard/SKILL.md" in written

    # Stale files under .gemini/config/skills/maid-onboard are pruned on reinstall.
    stale = agy_skill.parent / "STALE.md"
    stale.write_text("stale\n", encoding="utf-8")
    install_onboard_skill(home, payload, False)
    assert not stale.exists()
    assert agy_skill.is_file()

    # --link symlinks when supported.
    link_home = tmp_path / "link-home"
    install_onboard_skill(link_home, payload, True)
    linked_skill = (
        link_home / ".gemini" / "config" / "skills" / "maid-onboard" / "SKILL.md"
    )
    assert linked_skill.exists()
    if _platform_supports_symlinks(tmp_path):
        assert os.path.islink(linked_skill)

    # Synthetic 2-tool payloads remain compatible without creating .gemini/.
    two_tool_payload = _make_payload(tmp_path / "two-tool", include_antigravity=False)
    two_tool_home = tmp_path / "two-tool-home"
    two_tool_written = install_onboard_skill(two_tool_home, two_tool_payload, False)
    assert ".claude/skills/maid-onboard/SKILL.md" in two_tool_written
    assert ".codex/skills/maid-onboard/SKILL.md" in two_tool_written
    assert not (two_tool_home / ".gemini").exists()


def test_uninstall_onboard_skill_removes_antigravity_and_respects_modifications_and_symlinks(
    tmp_path: Path,
) -> None:
    payload = _make_payload(tmp_path / "payload", include_antigravity=True)
    home = tmp_path / "home"
    install_onboard_skill(home, payload, False)

    custom = home / ".gemini" / "config" / "skills" / "custom-skill" / "SKILL.md"
    custom.parent.mkdir(parents=True)
    custom.write_text("keep custom\n", encoding="utf-8")

    preview = uninstall_onboard_skill(home, payload, True)
    assert (home / ".gemini" / "config" / "skills" / "maid-onboard").is_dir()
    report = uninstall_onboard_skill(home, payload, False)

    assert preview == report
    assert sorted(report.removed) == [
        ".claude/skills/maid-onboard",
        ".codex/skills/maid-onboard",
        ".gemini/config/skills/maid-onboard",
    ]
    assert report.preserved == []
    assert report.missing == []
    assert not (home / ".gemini" / "config" / "skills" / "maid-onboard").exists()
    assert custom.read_text(encoding="utf-8") == "keep custom\n"

    # Modified Antigravity onboard copy is preserved while untouched siblings are removed.
    mod_home = tmp_path / "mod-home"
    install_onboard_skill(mod_home, payload, False)
    modified = mod_home / ".gemini" / "config" / "skills" / "maid-onboard" / "SKILL.md"
    modified.write_text("user customized\n", encoding="utf-8")
    mod_report = uninstall_onboard_skill(mod_home, payload, False)
    assert ".gemini/config/skills/maid-onboard" in mod_report.preserved
    assert ".claude/skills/maid-onboard" in mod_report.removed
    assert modified.read_text(encoding="utf-8") == "user customized\n"

    # Installed Antigravity skill with a 2-tool payload lacking antigravity is preserved, not deleted.
    partial_home = tmp_path / "partial-home"
    install_onboard_skill(partial_home, payload, False)
    two_tool_payload = _make_payload(
        tmp_path / "two-tool-uninstall", include_antigravity=False
    )
    partial_report = uninstall_onboard_skill(partial_home, two_tool_payload, False)
    assert ".gemini/config/skills/maid-onboard" in partial_report.preserved
    assert (
        partial_home / ".gemini" / "config" / "skills" / "maid-onboard" / "SKILL.md"
    ).is_file()

    # Symlinked ancestor boundaries (.gemini, .gemini/config, .gemini/config/skills) are never crossed.
    if _platform_supports_symlinks(tmp_path):
        for boundary_name, relative_parent, tail in (
            ("gemini", Path(".gemini"), Path("config/skills/maid-onboard/SKILL.md")),
            ("config", Path(".gemini/config"), Path("skills/maid-onboard/SKILL.md")),
            ("skills", Path(".gemini/config/skills"), Path("maid-onboard/SKILL.md")),
        ):
            b_home = tmp_path / f"boundary-{boundary_name}"
            install_onboard_skill(b_home, payload, False)
            linked = b_home / relative_parent
            outside = tmp_path / f"outside-{boundary_name}"
            linked.rename(outside)
            linked.symlink_to(outside, target_is_directory=True)

            b_report = uninstall_onboard_skill(b_home, payload, False)
            assert ".gemini/config/skills/maid-onboard" in b_report.preserved
            assert (outside / tail).is_file()


def test_skills_cli_install_and_uninstall_cover_antigravity_and_docs(
    tmp_path: Path,
) -> None:
    home = tmp_path / "cli-home"

    assert main(["skills", "install", "--target-root", str(home)]) == 0
    agy_skill = home / ".gemini" / "config" / "skills" / "maid-onboard" / "SKILL.md"
    assert agy_skill.is_file()
    assert "--tool antigravity" in agy_skill.read_text(encoding="utf-8")

    assert main(["skills", "uninstall", "--target-root", str(home), "--dry-run"]) == 0
    assert agy_skill.is_file()

    assert main(["skills", "uninstall", "--target-root", str(home)]) == 0
    assert not agy_skill.exists()
    assert main(["skills", "uninstall", "--target-root", str(home)]) == 0

    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "~/.gemini/config" in readme
