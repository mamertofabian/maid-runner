from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTCOME_DOC = ROOT / "docs/manifest-outcome-records.md"
WORKFLOW_DOC = ROOT / "docs/draft-manifest-workflow.md"
DRAFTS_README = ROOT / "manifests/drafts/README.md"
AGENT_SKILLS_DOC = ROOT / "docs/agent-skills.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_manifest_outcome_docs_define_post_review_capture_step() -> None:
    guide = _read(OUTCOME_DOC)
    workflow = _read(WORKFLOW_DOC)
    drafts_readme = _read(DRAFTS_README)
    agent_skills = _read(AGENT_SKILLS_DOC)

    assert "after implementation review and before final handoff" in guide
    assert "Capture Outcome after implementation review" in guide
    assert "docs/manifest-outcome-records.md" in workflow
    assert "../../docs/manifest-outcome-records.md" in drafts_readme
    assert "manifest-outcome-records.md" in agent_skills


def test_manifest_outcome_docs_preserve_manifest_contract_boundaries() -> None:
    guide = _read(OUTCOME_DOC)

    assert "does not replace behavioral tests" in guide
    assert "declared artifacts" in guide
    assert "validation commands" in guide
    assert "supersession" in guide
    assert "implementation review" in guide


def test_manifest_outcome_docs_define_status_and_non_ai_boundaries() -> None:
    guide = _read(OUTCOME_DOC)

    for status in (
        "completed",
        "failed",
        "partial",
        "superseded",
        "archived",
        "abandoned",
    ):
        assert f"`{status}`" in guide

    assert "Completed outcomes are the default learning source" in guide
    assert "explicit filters" in guide
    assert "human-authored" in guide
    assert "agent-authored" in guide
    assert "MAID does not infer" in guide
    assert "explicit structured data" in guide
