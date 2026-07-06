"""Behavioral tests for MAID agent skill scope and install guidance."""

from __future__ import annotations

import re
from pathlib import Path

from maid_runner.instruction_payload import INSTRUCTION_PAYLOAD_VERSION


PROJECT_ROOT = Path(__file__).resolve().parents[1]

IMPLEMENTER_SKILLS = (
    Path(".claude/skills/maid-implementer/SKILL.md"),
    Path(".codex/skills/maid-implementer/SKILL.md"),
    Path("maid_runner/claude/skills/maid-implementer/SKILL.md"),
    Path("maid_runner/codex/skills/maid-implementer/SKILL.md"),
)

PLANNER_SKILLS = (
    Path(".claude/skills/maid-planner/SKILL.md"),
    Path(".codex/skills/maid-planner/SKILL.md"),
    Path("maid_runner/claude/skills/maid-planner/SKILL.md"),
    Path("maid_runner/codex/skills/maid-planner/SKILL.md"),
)

PAYLOAD_PAIRS = (
    (
        Path(".claude/skills/maid-implementer/SKILL.md"),
        Path("maid_runner/claude/skills/maid-implementer/SKILL.md"),
    ),
    (
        Path(".codex/skills/maid-implementer/SKILL.md"),
        Path("maid_runner/codex/skills/maid-implementer/SKILL.md"),
    ),
    (
        Path(".claude/skills/maid-planner/SKILL.md"),
        Path("maid_runner/claude/skills/maid-planner/SKILL.md"),
    ),
    (
        Path(".codex/skills/maid-planner/SKILL.md"),
        Path("maid_runner/codex/skills/maid-planner/SKILL.md"),
    ),
)


def _read(path: Path) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def test_implementer_skills_treat_scope_and_delete_as_writable_not_read() -> None:
    for path in IMPLEMENTER_SKILLS:
        text = _read(path)

        assert "`files.scope` declares writable implementation files" in text
        assert (
            "`files.read` is dependency context, not writable production scope" in text
        )

        never_rule = re.search(
            r"NEVER modify files not listed.*?`files\.delete`",
            text,
            flags=re.DOTALL,
        )
        assert never_rule, path
        assert "`files.read`" not in never_rule.group(0)


def test_planner_prerequisites_use_pypi_install_not_local_dev_flow() -> None:
    for path in PLANNER_SKILLS:
        text = _read(path)

        assert "maid --version" in text
        assert "uv run maid --version" in text
        assert "Install `maid-runner` from PyPI" in text
        assert "uv add --dev maid-runner" in text
        assert "python -m pip install maid-runner" in text
        assert "uv sync --dev" not in text
        assert "../maid-runner" not in text
        assert "pip show maid-runner" not in text


def test_gitignore_covers_generated_advisory_payloads() -> None:
    gitignore = _read(Path(".gitignore"))

    for pattern in (
        ".maid/outcomes-digest.md",
        ".maid/outcomes-enrichment-prompt.json",
        ".maid/run-review-request.json",
        ".maid/run-review.json",
        ".maid/run-reviews/",
    ):
        assert pattern in gitignore


def test_skill_guidance_source_and_package_payloads_match() -> None:
    for source, packaged in PAYLOAD_PAIRS:
        assert _read(source) == _read(packaged)


def test_instruction_payload_version_bumped_for_skill_guidance_fix() -> None:
    assert _version_tuple(INSTRUCTION_PAYLOAD_VERSION) > _version_tuple("2026.07.06.1")
