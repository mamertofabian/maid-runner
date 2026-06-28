"""Behavioral tests for the distributed maid-outcome-enrich skill guidance."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from maid_runner.cli.commands._main import build_parser


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "maid-outcome-enrich"
SOURCE_SKILLS = (
    Path(".claude/skills") / SKILL_NAME / "SKILL.md",
    Path(".codex/skills") / SKILL_NAME / "SKILL.md",
)
GENERATED_SKILLS = (
    Path("maid_runner/claude/skills") / SKILL_NAME / "SKILL.md",
    Path("maid_runner/codex/skills") / SKILL_NAME / "SKILL.md",
)
CODEX_AGENT_METADATA = Path(".codex/skills") / SKILL_NAME / "agents/openai.yaml"
GENERATED_CODEX_AGENT_METADATA = (
    Path("maid_runner/codex/skills") / SKILL_NAME / "agents/openai.yaml"
)


def _read(relative_path: Path, root: Path = PROJECT_ROOT) -> str:
    return (root / relative_path).read_text()


def _skill_texts(root: Path = PROJECT_ROOT) -> list[str]:
    return [_read(path, root=root) for path in SOURCE_SKILLS]


def _assert_all_skills_contain(*phrases: str, root: Path = PROJECT_ROOT) -> None:
    for text in _skill_texts(root=root):
        for phrase in phrases:
            assert phrase in text


def _subparser(
    parser: argparse.ArgumentParser, command: str
) -> argparse.ArgumentParser:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices[command]
    raise AssertionError("parser has no subcommands")


def _command_options(command: str) -> set[str]:
    parser = _subparser(build_parser(), command)
    return {option for action in parser._actions for option in action.option_strings}


def _subcommand_options(command: str, subcommand: str) -> set[str]:
    parser = _subparser(_subparser(build_parser(), command), subcommand)
    return {option for action in parser._actions for option in action.option_strings}


def _sync_distribution(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(PROJECT_ROOT / ".claude", workspace / ".claude")
    shutil.copytree(PROJECT_ROOT / ".codex", workspace / ".codex")
    scripts_dir = workspace / "scripts"
    scripts_dir.mkdir()
    shutil.copy2(PROJECT_ROOT / "scripts/sync_claude_files.py", scripts_dir)

    subprocess.run(
        [sys.executable, "scripts/sync_claude_files.py"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    return workspace


def _option_tokens(text: str) -> set[str]:
    return set(re.findall(r"(?<![A-Za-z0-9_])--[a-z][a-z0-9-]*", text))


def test_outcome_enrich_skill_describes_validate_render_workflow() -> None:
    phrases = (
        "maid enrich prompt",
        "maid enrich validate",
        "maid enrich render",
        ".maid/outcomes-digest.json",
        ".maid/outcomes-digest.md",
        "maid insights --theme-map",
    )
    assert all(phrase in text for text in _skill_texts() for phrase in phrases)
    _assert_all_skills_contain(*phrases)


def test_outcome_enrich_skill_marks_validate_as_hard_stop() -> None:
    phrases = (
        "non-zero `maid enrich validate` result is a hard stop",
        "Do not hand-edit `.maid/outcomes-digest.json` to satisfy validation",
        "regenerate the candidate digest",
    )
    assert all(phrase in text for text in _skill_texts() for phrase in phrases)
    _assert_all_skills_contain(*phrases)


def test_outcome_enrich_skill_states_cloud_privacy_and_local_default() -> None:
    phrases = (
        "Default to local llama-server generation",
        "Cloud generation is explicit opt-in only",
        "CLOUD-PRIVACY",
        "sending the lesson corpus to a cloud provider publishes Outcome lessons externally",
    )
    assert all(phrase in text for text in _skill_texts() for phrase in phrases)
    _assert_all_skills_contain(*phrases)


def test_outcome_enrich_skill_uses_only_registered_options() -> None:
    enrich_options = _command_options("enrich")
    prompt_options = _subcommand_options("enrich", "prompt")
    validate_options = _subcommand_options("enrich", "validate")
    render_options = _subcommand_options("enrich", "render")
    insights_options = _command_options("insights")
    registered_options = (
        enrich_options
        | prompt_options
        | validate_options
        | render_options
        | insights_options
    )

    for text in _skill_texts():
        unknown_options = _option_tokens(text) - registered_options
        assert unknown_options == set()
        assert "--theme-map" in text
        assert "--allow-stale-index" in text
        assert "--digest" in text
        assert "--md-output" in text
        assert "--output" in text


def test_outcome_enrich_skill_synced_to_agent_payloads(tmp_path: Path) -> None:
    synced_workspace = _sync_distribution(tmp_path)

    for source_path, generated_path in zip(SOURCE_SKILLS, GENERATED_SKILLS):
        assert _read(generated_path, root=synced_workspace) == _read(
            source_path, root=synced_workspace
        )

    assert _read(GENERATED_CODEX_AGENT_METADATA, root=synced_workspace) == _read(
        CODEX_AGENT_METADATA, root=synced_workspace
    )


def test_codex_init_installs_outcome_enrich_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maid_runner.cli.commands._main import main
    from maid_runner.cli.commands.init import cmd_init

    monkeypatch.chdir(tmp_path)
    assert callable(cmd_init)

    exit_code = main(["init", "--tool", "codex"])

    assert exit_code == 0
    skills_dir = tmp_path / ".codex" / "skills"
    assert (skills_dir / SKILL_NAME / "SKILL.md").exists()
    assert (skills_dir / SKILL_NAME / "agents/openai.yaml").exists()
    assert not (skills_dir / "maid-runner-self-improvement").exists()


def test_claude_init_installs_outcome_enrich_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maid_runner.cli.commands._main import main
    from maid_runner.cli.commands.init import cmd_init

    monkeypatch.chdir(tmp_path)
    assert callable(cmd_init)

    exit_code = main(["init", "--tool", "claude"])

    assert exit_code == 0
    assert (tmp_path / ".claude" / "skills" / SKILL_NAME / "SKILL.md").exists()
    manifest = json.loads((tmp_path / ".claude" / "manifest.json").read_text())
    assert SKILL_NAME in manifest["skills"]["distributable"]
