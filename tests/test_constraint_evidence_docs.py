from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
MAID_SPECS = ROOT / "docs/maid_specs.md"
TROUBLESHOOTING = ROOT / "docs/troubleshooting.md"
CLAUDE_REVIEW_SKILL = ROOT / ".claude/skills/maid-implementation-review/SKILL.md"
CODEX_REVIEW_SKILL = ROOT / ".codex/skills/maid-implementation-review/SKILL.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_constraint_evidence_docs_describe_opt_in_gates() -> None:
    readme = _read(README)
    specs = _read(MAID_SPECS)

    for document in (readme, specs):
        assert "`maid verify --artifact-coverage`" in document
        assert "`maid validate --artifact-coverage`" in document
        assert "`maid verify --knockout`" in document
        assert "opt-in" in document
        assert "Python-only" in document
        assert "`maid-runner[quality]`" in document
        assert "E307" in document
        assert "`--knockout-limit`" in document
        assert "`--knockout-allow-dirty`" in document
        assert "not full mutation testing" in document


def test_troubleshooting_covers_e710_through_e712() -> None:
    troubleshooting = _read(TROUBLESHOOTING)

    for code in ("E710", "E711", "E712"):
        assert f"(`{code}`)" in troubleshooting

    assert "ARTIFACT_NOT_EXECUTED_BY_TESTS" in troubleshooting
    assert "ARTIFACT_KNOCKOUT_NOT_DETECTED" in troubleshooting
    assert "KNOCKOUT_HARNESS_FAILURE" in troubleshooting
    assert "behavioral tests never execute the artifact body" in troubleshooting
    assert "tests do not constrain the artifact behavior" in troubleshooting
    assert "git checkout -- <file>" in troubleshooting


def test_review_skill_payloads_quote_constraint_evidence_command() -> None:
    for skill_path in (CLAUDE_REVIEW_SKILL, CODEX_REVIEW_SKILL):
        skill = _read(skill_path)

        assert "`maid verify --artifact-coverage --knockout`" in skill
        assert "high-risk changes" in skill
