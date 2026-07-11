"""Behavioral tests for the distributed maid-run-review skill guidance."""

from __future__ import annotations

from pathlib import Path

from maid_runner.instruction_payload import INSTRUCTION_PAYLOAD_VERSION


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "maid-run-review"
SOURCE_SKILLS = (
    Path(".claude/skills") / SKILL_NAME / "SKILL.md",
    Path(".codex/skills") / SKILL_NAME / "SKILL.md",
)
RUN_EVALUATION_DOC = Path("docs/run-evaluation.md")
BASELINE_PAYLOAD_VERSION = "2026.07.05.1"


def _read(relative_path: Path | str) -> str:
    return (PROJECT_ROOT / relative_path).read_text()


def _skill_texts() -> list[str]:
    for path in SOURCE_SKILLS:
        assert (PROJECT_ROOT / path).exists(), f"missing source skill: {path}"
    return [_read(path) for path in SOURCE_SKILLS]


def _assert_all_skills_contain(*phrases: str) -> None:
    for text in _skill_texts():
        for phrase in phrases:
            assert phrase in text


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def test_both_source_skills_pin_cloud_privacy_disclosure() -> None:
    for text in _skill_texts():
        assert "CLOUD-PRIVACY" in text
        assert "run evidence leaves the machine" in text
        assert "Use the model access already available to the hosting agent" in text


def test_skill_pins_validate_before_render_and_no_citation_editing() -> None:
    for text in _skill_texts():
        prompt_index = text.index("maid evaluate prompt")
        model_index = text.index("agent-available model")
        validate_index = text.index("maid evaluate validate")
        render_index = text.index("maid evaluate render")

        assert prompt_index < model_index < validate_index < render_index
        assert "fail closed" in text
        assert "Do not hand-edit citations" in text
        assert "regenerate" in text


def test_skill_and_docs_pin_advisory_never_gate_rule() -> None:
    _assert_all_skills_contain(
        "advisory, never a gate",
        "must not be fed back to the implementing agent as instructions during an active run",
    )
    docs_text = _read(RUN_EVALUATION_DOC)
    assert "advisory, never a gate" in docs_text


def test_run_evaluation_docs_cover_provenance_and_commands() -> None:
    docs_text = _read(RUN_EVALUATION_DOC)
    readme_text = _read("README.md")

    for phrase in (
        "--agent-model",
        "MAID_AGENT_MODEL",
        "maid evaluate run",
        "maid evaluate compare",
        "unknown agent",
        "unclassified",
        "no-lock",
        "no composite scores",
    ):
        assert phrase in docs_text

    assert "docs/run-evaluation.md" in readme_text


def test_agent_skills_doc_lists_run_review_for_both_payloads() -> None:
    docs_text = _read("docs/agent-skills.md")

    assert "`maid-run-review`" in docs_text
    assert "Claude" in docs_text
    assert "Codex" in docs_text


def test_instruction_payload_version_bumped_for_run_review_skill() -> None:
    assert _version_tuple(INSTRUCTION_PAYLOAD_VERSION) > _version_tuple(
        BASELINE_PAYLOAD_VERSION
    )
