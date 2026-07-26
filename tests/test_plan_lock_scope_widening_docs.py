from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLAUDE_REVIEW_SKILL = ROOT / ".claude/skills/maid-implementation-review/SKILL.md"
CODEX_SOURCE_REVIEW_SKILL = ROOT / ".codex/skills/maid-implementation-review/SKILL.md"
CODEX_REVIEW_SKILL = (
    ROOT / "maid_runner/codex/skills/maid-implementation-review/SKILL.md"
)
PACKAGED_CLAUDE_REVIEW_SKILL = (
    ROOT / "maid_runner/claude/skills/maid-implementation-review/SKILL.md"
)
DOCS_SPEC = ROOT / "docs/maid_specs.md"
PACKAGED_DOCS_SPEC = ROOT / "maid_runner/docs/maid_specs.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_review_skill_payloads_classify_e708_as_non_blocking() -> None:
    for content in (
        _read(CLAUDE_REVIEW_SKILL),
        _read(CODEX_SOURCE_REVIEW_SKILL),
        _read(CODEX_REVIEW_SKILL),
    ):
        assert "E708 PLAN_LOCK_SCOPE_WIDENED" in content
        assert "non-blocking" in content.lower() or "advisory" in content.lower()


def test_review_skill_payloads_state_the_e708_reconcile_action() -> None:
    for content in (
        _read(CLAUDE_REVIEW_SKILL),
        _read(CODEX_SOURCE_REVIEW_SKILL),
        _read(CODEX_REVIEW_SKILL),
    ):
        assert "E708 PLAN_LOCK_SCOPE_WIDENED" in content
        assert "reconcile the manifests" in content
        assert "explicit baseline" in content


def test_specs_document_e708_in_the_plan_lock_stage() -> None:
    specs = _read(DOCS_SPEC)

    assert "E708 PLAN_LOCK_SCOPE_WIDENED" in specs
    assert "warning" in specs.lower()
    assert "enforcement widened beyond the task window" in specs


def test_specs_state_e708_does_not_change_which_manifests_are_enforced() -> None:
    specs = _read(DOCS_SPEC)

    assert "deliberate fail-closed behavior" in specs
    assert (
        "reports this widening without changing which manifests are enforced" in specs
    )


def test_packaged_guidance_matches_source_guidance_for_e708() -> None:
    source_review = _read(CLAUDE_REVIEW_SKILL)
    source_codex_review = _read(CODEX_SOURCE_REVIEW_SKILL)
    packaged_claude_review = _read(PACKAGED_CLAUDE_REVIEW_SKILL)
    packaged_codex_review = _read(CODEX_REVIEW_SKILL)
    source_specs = _read(DOCS_SPEC)
    packaged_specs = _read(PACKAGED_DOCS_SPEC)

    expected_review_guidance = (
        "E708 PLAN_LOCK_SCOPE_WIDENED is a non-blocking advisory disclosure."
    )
    expected_specs_guidance = (
        "E708 PLAN_LOCK_SCOPE_WIDENED is a warning reporting that enforcement "
        "widened beyond the task window."
    )

    for content in (
        source_review,
        source_codex_review,
        packaged_claude_review,
        packaged_codex_review,
    ):
        assert expected_review_guidance in content
        assert "reconcile the manifests" in content
        assert "explicit baseline" in content

    assert expected_specs_guidance in source_specs
    assert expected_specs_guidance in packaged_specs
