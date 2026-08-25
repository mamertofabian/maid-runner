"""Behavioral contract for reviewer writable-scope payload guidance."""

from __future__ import annotations

import re
from pathlib import Path

from maid_runner.instruction_payload import INSTRUCTION_PAYLOAD_VERSION


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REVIEWER_PAYLOADS = (
    Path(".claude/agents/maid-implementation-reviewer.md"),
    Path(".claude/skills/maid-implementation-review/SKILL.md"),
    Path(".codex/skills/maid-implementation-review/SKILL.md"),
    Path("maid_runner/claude/agents/maid-implementation-reviewer.md"),
    Path("maid_runner/claude/skills/maid-implementation-review/SKILL.md"),
    Path("maid_runner/codex/skills/maid-implementation-review/SKILL.md"),
)

PAYLOAD_PAIRS = (
    (
        Path(".claude/agents/maid-implementation-reviewer.md"),
        Path("maid_runner/claude/agents/maid-implementation-reviewer.md"),
    ),
    (
        Path(".claude/skills/maid-implementation-review/SKILL.md"),
        Path("maid_runner/claude/skills/maid-implementation-review/SKILL.md"),
    ),
    (
        Path(".codex/skills/maid-implementation-review/SKILL.md"),
        Path("maid_runner/codex/skills/maid-implementation-review/SKILL.md"),
    ),
)


def _read(path: Path) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def test_reviewer_guidance_accepts_all_writable_scope_categories() -> None:
    for path in REVIEWER_PAYLOADS:
        text = _read(path)
        writable_rule = re.search(
            r"writable(?: production)? (?:file )?scope.*?(?:files\.delete|`files\.delete`)",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

        assert writable_rule, path
        for category in ("files.create", "files.edit", "files.scope", "files.delete"):
            assert category in writable_rule.group(0), path
        assert "files.read" not in writable_rule.group(0), path
        assert "files.read" in text, path
        assert "dependency context" in text, path


def test_reviewer_guidance_limits_artifact_checks_to_contracted_files() -> None:
    expected = (
        "Artifact validation applies to declarations in `files.create` and "
        "`files.edit` only"
    )

    for path in REVIEWER_PAYLOADS:
        assert expected in _read(path), path


def test_reviewer_payload_sources_and_packages_match() -> None:
    for source, packaged in PAYLOAD_PAIRS:
        assert _read(source) == _read(packaged)


def test_instruction_payload_version_bumped_for_reviewer_scope_fix() -> None:
    assert _version_tuple(INSTRUCTION_PAYLOAD_VERSION) > _version_tuple("2026.08.20.1")
