"""Behavioral tests for Outcome lesson_type vocabulary guidance."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from maid_runner.instruction_payload import INSTRUCTION_PAYLOAD_VERSION


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "maid-implementation-review"
SOURCE_SKILLS = (
    Path(".claude/skills") / SKILL_NAME / "SKILL.md",
    Path(".codex/skills") / SKILL_NAME / "SKILL.md",
)
GENERATED_SKILLS = (
    Path("maid_runner/claude/skills") / SKILL_NAME / "SKILL.md",
    Path("maid_runner/codex/skills") / SKILL_NAME / "SKILL.md",
)
SOURCE_DOC = Path("docs/manifest-outcome-records.md")
GENERATED_DOC = Path("maid_runner/docs/manifest-outcome-records.md")
OUTCOME_HEADING = "## Outcome-Aware MAID Guidance"
VOCABULARY_HEADING = "### Lesson Type Vocabulary Convergence"
BASELINE_PAYLOAD_VERSION = "2026.07.04.1"


def _read(relative_path: Path, root: Path = PROJECT_ROOT) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def _source_skill_texts(root: Path = PROJECT_ROOT) -> list[str]:
    return [_read(path, root=root) for path in SOURCE_SKILLS]


def _normalized(text: str) -> str:
    return " ".join(text.split()).lower()


def _outcome_section(skill_text: str) -> str:
    assert OUTCOME_HEADING in skill_text
    start = skill_text.index(OUTCOME_HEADING)
    next_heading = skill_text.find("\n## ", start + len(OUTCOME_HEADING))
    end = next_heading if next_heading != -1 else len(skill_text)
    return skill_text[start:end]


def _vocabulary_section(text: str) -> str:
    assert VOCABULARY_HEADING in text
    start = text.index(VOCABULARY_HEADING)
    next_heading = re.search(r"\n#{2,3} ", text[start + len(VOCABULARY_HEADING) :])
    end = (
        start + len(VOCABULARY_HEADING) + next_heading.start()
        if next_heading
        else len(text)
    )
    return text[start:end]


def _sync_distribution(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(PROJECT_ROOT / ".claude", workspace / ".claude")
    shutil.copytree(PROJECT_ROOT / ".codex", workspace / ".codex")
    shutil.copytree(PROJECT_ROOT / "docs", workspace / "docs")
    drafts_dir = workspace / "manifests" / "drafts"
    drafts_dir.mkdir(parents=True)
    shutil.copy2(PROJECT_ROOT / "manifests/drafts/README.md", drafts_dir)
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


def _assert_skill_payloads_match_sources(root: Path) -> bool:
    for source_path, generated_path in zip(SOURCE_SKILLS, GENERATED_SKILLS):
        source_text = _read(source_path, root=root)
        generated_text = _read(generated_path, root=root)

        _assert_vocabulary_rule_terms(
            _vocabulary_section(_outcome_section(source_text))
        )
        _assert_vocabulary_rule_terms(
            _vocabulary_section(_outcome_section(generated_text))
        )
        assert generated_text == source_text
    return True


def _assert_docs_payload_matches_source(root: Path) -> bool:
    source_doc = _read(SOURCE_DOC, root=root)
    generated_doc = _read(GENERATED_DOC, root=root)
    source_doc_guidance = _vocabulary_section(source_doc)
    generated_doc_guidance = _vocabulary_section(generated_doc)

    _assert_vocabulary_rule_terms(source_doc_guidance)
    _assert_vocabulary_rule_terms(generated_doc_guidance)
    assert generated_doc == source_doc
    return True


def _assert_vocabulary_rule_terms(guidance: str) -> None:
    normalized = _normalized(guidance)

    assert "before writing new outcome lessons" in normalized
    assert "list the existing lesson_type vocabulary" in normalized
    assert "maid insights" in guidance
    assert "by_lesson_type" in guidance
    assert "before coining a new lesson_type" in normalized
    assert "fresh validated theme map" in normalized
    assert "member_lesson_types" in guidance
    assert "canonical families" in normalized
    assert "reuse an existing lesson_type when one fits" in normalized
    assert "coin a new lesson_type only when no existing value fits" in normalized
    assert "advisory" in normalized
    assert "must not block or delay outcome capture" in normalized


def test_capture_guidance_requires_consulting_existing_lesson_types() -> None:
    for text in _source_skill_texts():
        guidance = _vocabulary_section(_outcome_section(text))
        normalized = _normalized(guidance)

        assert "before writing new outcome lessons" in normalized
        assert "list the existing lesson_type vocabulary" in normalized
        assert "maid insights" in guidance
        assert "by_lesson_type" in guidance
        assert "before coining a new lesson_type" in normalized


def test_capture_guidance_prefers_fresh_theme_map_families() -> None:
    for text in _source_skill_texts():
        guidance = _vocabulary_section(_outcome_section(text))
        normalized = _normalized(guidance)

        assert "fresh validated theme map" in normalized
        assert "member_lesson_types" in guidance
        assert "canonical families" in normalized
        assert "prefer" in normalized


def test_capture_guidance_states_reuse_first_rule() -> None:
    for text in _source_skill_texts():
        guidance = _vocabulary_section(_outcome_section(text))
        normalized = _normalized(guidance)

        assert "reuse an existing lesson_type when one fits" in normalized
        assert "coin a new lesson_type only when no existing value fits" in normalized
        assert "singular" in normalized
        assert "kebab-or-plain lowercase" in normalized


def test_capture_vocabulary_check_is_advisory_and_non_blocking() -> None:
    for text in _source_skill_texts():
        guidance = _vocabulary_section(_outcome_section(text))
        normalized = _normalized(guidance)

        assert "advisory" in normalized
        assert "must not block or delay outcome capture" in normalized
        assert "insights or the index is unavailable" in normalized
        assert "best-fit lesson_type" in normalized


def test_vocabulary_guidance_synced_to_payloads_and_docs(tmp_path: Path) -> None:
    assert _assert_skill_payloads_match_sources(PROJECT_ROOT)
    assert _assert_docs_payload_matches_source(PROJECT_ROOT)

    synced_workspace = _sync_distribution(tmp_path)

    assert _assert_skill_payloads_match_sources(synced_workspace)
    assert _assert_docs_payload_matches_source(synced_workspace)


def test_instruction_payload_version_bumped_for_vocabulary_change() -> None:
    assert _version_tuple(INSTRUCTION_PAYLOAD_VERSION) > _version_tuple(
        BASELINE_PAYLOAD_VERSION
    )
