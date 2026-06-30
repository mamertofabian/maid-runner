"""Behavioral tests for planner consumption of enriched Outcome insights."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from maid_runner.cli.commands._main import build_parser
from maid_runner.instruction_payload import INSTRUCTION_PAYLOAD_VERSION


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "maid-planner"
SOURCE_SKILLS = (
    Path(".claude/skills") / SKILL_NAME / "SKILL.md",
    Path(".codex/skills") / SKILL_NAME / "SKILL.md",
)
GENERATED_SKILLS = (
    Path("maid_runner/claude/skills") / SKILL_NAME / "SKILL.md",
    Path("maid_runner/codex/skills") / SKILL_NAME / "SKILL.md",
)
OUTCOME_HEADING = "## Outcome-Aware MAID Guidance"
BASELINE_PAYLOAD_VERSION = "2026.06.27.1"


def _read(relative_path: Path, root: Path = PROJECT_ROOT) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def _planner_texts(root: Path = PROJECT_ROOT) -> list[str]:
    return [_read(path, root=root) for path in SOURCE_SKILLS]


def _outcome_section(skill_text: str) -> str:
    assert OUTCOME_HEADING in skill_text
    start = skill_text.index(OUTCOME_HEADING)
    next_heading = skill_text.find("\n## ", start + len(OUTCOME_HEADING))
    end = next_heading if next_heading != -1 else len(skill_text)
    return skill_text[start:end]


def _active_insights_rule(skill_text: str) -> str:
    section = _outcome_section(skill_text)
    marker = "- Active insights trigger:"
    assert marker in section
    start = section.index(marker)
    next_bullet = section.find("\n- ", start + len(marker))
    return section[start : next_bullet if next_bullet != -1 else len(section)]


def _normalized(text: str) -> str:
    return " ".join(text.split()).lower()


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


def _option_tokens(text: str) -> set[str]:
    return set(re.findall(r"(?<![A-Za-z0-9_])--[a-z][a-z0-9-]*", text))


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


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def test_planner_outcome_phase_prefers_theme_map_when_digest_present() -> None:
    for text in _planner_texts():
        rule = _active_insights_rule(text)
        normalized = _normalized(rule)

        assert "maid insights --theme-map .maid/outcomes-digest.json" in rule
        assert "prefer" in normalized
        assert "fresh advisory enrichment digest" in normalized
        assert "normalized theme" in normalized


def test_planner_outcome_phase_falls_back_without_fresh_digest() -> None:
    for text in _planner_texts():
        rule = _active_insights_rule(text)
        normalized = _normalized(rule)

        assert "fall back to plain `maid insights`" in normalized
        assert "absent, stale, or invalid" in normalized
        assert "non-blocking" in normalized
        assert "must never block, gate, or downgrade planning" in normalized
        assert "do not pass `--allow-stale-index`" in normalized


def test_planner_theme_map_guidance_keeps_digest_advisory_and_read_only() -> None:
    for text in _planner_texts():
        rule = _active_insights_rule(text)
        normalized = _normalized(rule)

        assert "read-only consumer" in normalized
        assert "planner must not generate" in normalized
        assert "must not call a model" in normalized
        assert "must not run `maid enrich`" in normalized
        assert "advisory planning evidence only" in normalized


def test_planner_theme_map_guidance_uses_only_registered_insights_options() -> None:
    registered_options = _command_options("insights") - {"-h", "--help"}
    assert registered_options == {
        "--index",
        "--manifest-dir",
        "--project-root",
        "--allow-stale-index",
        "--theme-map",
        "--limit",
        "--json",
    }

    for text in _planner_texts():
        rule = _active_insights_rule(text)
        unknown_options = _option_tokens(rule) - registered_options

        assert unknown_options == set()
        assert "--theme-map" in rule
        assert "--allow-stale-index" in rule
        assert "--digest" not in rule
        assert "maid insights --digest" not in rule


def test_planner_theme_map_guidance_synced_to_agent_payloads(
    tmp_path: Path,
) -> None:
    synced_workspace = _sync_distribution(tmp_path)

    for source_path, generated_path in zip(SOURCE_SKILLS, GENERATED_SKILLS):
        source_text = _read(source_path, root=synced_workspace)
        generated_text = _read(generated_path, root=synced_workspace)

        assert "maid insights --theme-map .maid/outcomes-digest.json" in source_text
        assert _outcome_section(source_text)
        assert _outcome_section(generated_text)
        assert generated_text == source_text


def test_instruction_payload_version_bumped_for_planner_change() -> None:
    assert _version_tuple(INSTRUCTION_PAYLOAD_VERSION) > _version_tuple(
        BASELINE_PAYLOAD_VERSION
    )
