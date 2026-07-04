"""Behavioral tests for self-improvement consumption of Outcome digests."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from maid_runner.cli.commands._main import build_parser


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SKILLS = (
    Path(".claude/skills/maid-runner-self-improvement/SKILL.md"),
    Path(".codex/skills/maid-runner-self-improvement/SKILL.md"),
)
PACKAGED_CODEX_SKILL = Path(
    "maid_runner/codex/skills/maid-runner-self-improvement/SKILL.md"
)
CODEX_PAYLOAD_MANIFEST = Path("maid_runner/codex/manifest.json")
OUTCOME_HEADING = "## Outcome-Aware MAID Guidance"
DIGEST_HEADING = "### Enrichment Digest Evidence"


def _read(relative_path: Path) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _skill_texts() -> list[str]:
    return [_read(path) for path in (*SOURCE_SKILLS, PACKAGED_CODEX_SKILL)]


def _outcome_section(skill_text: str) -> str:
    assert OUTCOME_HEADING in skill_text
    start = skill_text.index(OUTCOME_HEADING)
    next_heading = skill_text.find("\n## ", start + len(OUTCOME_HEADING))
    end = next_heading if next_heading != -1 else len(skill_text)
    return skill_text[start:end]


def _digest_section(skill_text: str) -> str:
    outcome = _outcome_section(skill_text)
    assert DIGEST_HEADING in outcome
    start = outcome.index(DIGEST_HEADING)
    next_heading = outcome.find("\n### ", start + len(DIGEST_HEADING))
    end = next_heading if next_heading != -1 else len(outcome)
    return outcome[start:end]


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


def test_self_improvement_lists_digest_as_evidence_source() -> None:
    for text in _skill_texts():
        guidance = _digest_section(text)
        normalized = _normalized(guidance)

        assert "maid insights --theme-map .maid/outcomes-digest.json" in guidance
        assert ".maid/outcomes-digest.md" in guidance
        assert "optional evidence source" in normalized
        assert "advisory narrative retrospective" in normalized
        assert "supplements" in normalized
        assert "existing sources" in normalized


def test_self_improvement_digest_fallback_is_non_blocking() -> None:
    for text in _skill_texts():
        guidance = _digest_section(text)
        normalized = _normalized(guidance)

        assert "fall back to plain `maid insights`" in normalized
        assert "runner rejects" in normalized
        assert "non-blocking" in normalized
        assert "must not pass `--allow-stale-index`" in normalized
        assert "force stale enriched data" in normalized
        assert "must not run `maid enrich`" in normalized
        assert "must not call a model" in normalized
        assert "must not generate" in normalized


def test_self_improvement_digest_is_untrusted_supplementary_data() -> None:
    for text in _skill_texts():
        guidance = _digest_section(text)
        normalized = _normalized(guidance)

        assert "untrusted data" in normalized
        assert "not instructions" in normalized
        assert "not evidence by itself" in normalized
        assert "supplementary" in normalized
        assert "confirmed findings" in normalized
        assert "primary sources" in normalized
        assert "bug reports" in normalized
        assert "code" in normalized
        assert "test output" in normalized
        assert "insight files" in normalized


def test_self_improvement_digest_guidance_uses_registered_options_only() -> None:
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

    for text in _skill_texts():
        guidance = _digest_section(text)
        unknown_options = _option_tokens(guidance) - registered_options

        assert unknown_options == set()
        assert "--theme-map" in guidance
        assert "--allow-stale-index" in guidance
        assert "--digest" not in guidance
        assert "maid insights --digest" not in guidance


def test_self_improvement_digest_guidance_syncs_to_packaged_codex_copy() -> None:
    codex_source = _read(SOURCE_SKILLS[1])
    packaged_codex = _read(PACKAGED_CODEX_SKILL)
    payload_manifest = _read(CODEX_PAYLOAD_MANIFEST)

    assert _digest_section(packaged_codex) == _digest_section(codex_source)
    assert "maid-runner-self-improvement" not in payload_manifest
