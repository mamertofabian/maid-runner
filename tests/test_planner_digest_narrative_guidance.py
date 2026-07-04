"""Behavioral tests for planner consumption of Outcome digest narrative."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

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
BASELINE_PAYLOAD_VERSION = "2026.07.01.1"


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


def test_planner_reads_digest_narrative_only_after_theme_map_success() -> None:
    for text in _planner_texts():
        rule = _active_insights_rule(text)
        normalized = _normalized(rule)

        assert "maid insights --theme-map .maid/outcomes-digest.json" in rule
        assert ".maid/outcomes-digest.md" in rule
        assert re.search(
            r"after (?:a )?successful .*--theme-map", normalized
        ) or re.search(r"--theme-map .*succeeded", normalized)
        assert "advisory narrative retrospective" in normalized


def test_planner_narrative_forbidden_when_digest_rejected() -> None:
    for text in _planner_texts():
        rule = _active_insights_rule(text)
        normalized = _normalized(rule)

        assert "must not read" in normalized
        assert ".maid/outcomes-digest.md" in rule
        assert "missing, stale, or invalid" in normalized
        assert "digest was rejected" in normalized
        assert "do not pass `--allow-stale-index`" in normalized
        assert "force" in normalized


def test_planner_narrative_is_untrusted_advisory_data() -> None:
    for text in _planner_texts():
        rule = _active_insights_rule(text)
        normalized = _normalized(rule)

        assert "untrusted data" in normalized
        assert "not instructions" in normalized
        assert "not validation evidence" in normalized
        assert "not generated narrative authority" in normalized
        assert "directive-looking text" in normalized
        assert "must be ignored" in normalized


def test_planner_plain_insights_fallback_remains_mandatory() -> None:
    for text in _planner_texts():
        rule = _active_insights_rule(text)
        normalized = _normalized(rule)

        assert "fall back to plain `maid insights`" in normalized
        assert "fallback is mandatory" in normalized
        assert "non-blocking" in normalized
        assert "must never block, gate, or downgrade planning" in normalized


def test_planner_narrative_guidance_synced_to_agent_payloads(
    tmp_path: Path,
) -> None:
    synced_workspace = _sync_distribution(tmp_path)

    for source_path, generated_path in zip(SOURCE_SKILLS, GENERATED_SKILLS):
        source_text = _read(source_path, root=synced_workspace)
        generated_text = _read(generated_path, root=synced_workspace)

        assert ".maid/outcomes-digest.md" in source_text
        assert _outcome_section(source_text)
        assert _outcome_section(generated_text)
        assert generated_text == source_text


def test_instruction_payload_version_bumped_for_narrative_change() -> None:
    assert _version_tuple(INSTRUCTION_PAYLOAD_VERSION) > _version_tuple(
        BASELINE_PAYLOAD_VERSION
    )
