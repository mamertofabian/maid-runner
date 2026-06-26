"""Behavioral tests for stash-backed plan revise guidance in init payloads."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _assert_stash_revise_guidance(text: str) -> None:
    assert "--preserve-red-evidence" in text
    assert "--stash-implementation" in text
    assert "review-driven behavioral contract changes" in text


def _sync_distribution(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(PROJECT_ROOT / ".claude", workspace / ".claude")
    shutil.copytree(PROJECT_ROOT / ".codex", workspace / ".codex")
    scripts_dir = workspace / "scripts"
    scripts_dir.mkdir()
    shutil.copy2(PROJECT_ROOT / "scripts" / "sync_claude_files.py", scripts_dir)

    subprocess.run(
        [sys.executable, "scripts/sync_claude_files.py"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    return workspace


def test_claude_init_installs_stash_revise_guidance(
    tmp_path: Path, monkeypatch
) -> None:
    from maid_runner.cli.commands._main import main

    monkeypatch.chdir(tmp_path)

    exit_code = main(["init", "--tool", "claude"])

    assert exit_code == 0
    _assert_stash_revise_guidance((tmp_path / "CLAUDE.md").read_text())
    _assert_stash_revise_guidance(
        (tmp_path / ".claude" / "skills" / "maid-implementer" / "SKILL.md").read_text()
    )


def test_codex_init_installs_stash_revise_guidance(tmp_path: Path, monkeypatch) -> None:
    from maid_runner.cli.commands._main import main

    monkeypatch.chdir(tmp_path)

    exit_code = main(["init", "--tool", "codex"])

    assert exit_code == 0
    _assert_stash_revise_guidance((tmp_path / "AGENTS.md").read_text())
    _assert_stash_revise_guidance(
        (tmp_path / ".codex" / "skills" / "maid-implementer" / "SKILL.md").read_text()
    )


def test_source_implementer_guidance_syncs_to_packaged_payloads(
    tmp_path: Path,
) -> None:
    synced_workspace = _sync_distribution(tmp_path)
    paths = [
        PROJECT_ROOT / ".claude" / "skills" / "maid-implementer" / "SKILL.md",
        PROJECT_ROOT / ".codex" / "skills" / "maid-implementer" / "SKILL.md",
        synced_workspace
        / "maid_runner"
        / "claude"
        / "skills"
        / "maid-implementer"
        / "SKILL.md",
        synced_workspace
        / "maid_runner"
        / "codex"
        / "skills"
        / "maid-implementer"
        / "SKILL.md",
    ]

    for path in paths:
        text = path.read_text()
        assert "--preserve-red-evidence" in text
        assert "--stash-implementation" in text
        assert "review-driven behavioral contract changes" in text
