from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
VALIDATION_WORKFLOW = ROOT / ".github/workflows/maid-validation.yml"
TEST_WORKFLOW = ROOT / ".github/workflows/maid-test.yml"
SETUP_DOC = ROOT / "docs/github-actions.md"


def _triggers(path: Path) -> dict:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    if True in workflow:
        workflow["on"] = workflow.pop(True)
    return workflow["on"]


def test_maid_validation_runs_on_pull_requests_without_push_trigger() -> None:
    source = VALIDATION_WORKFLOW.read_text(encoding="utf-8")
    triggers = _triggers(VALIDATION_WORKFLOW)

    assert "_maid_validation_reusable_workflow" in source
    assert "workflow_call" in triggers
    assert "pull_request" in triggers
    assert "push" not in triggers


def test_maid_test_runs_on_pull_requests_without_push_trigger() -> None:
    source = TEST_WORKFLOW.read_text(encoding="utf-8")
    triggers = _triggers(TEST_WORKFLOW)

    assert "_maid_test_reusable_workflow" in source
    assert "workflow_call" in triggers
    assert "pull_request" in triggers
    assert "push" not in triggers


def test_setup_guide_distinguishes_repository_and_downstream_triggers() -> None:
    guide = SETUP_DOC.read_text(encoding="utf-8")

    assert "_github_actions_setup_guide" in guide
    assert "run directly in this repository on `pull_request` only" in guide
    assert (
        "downstream callers can still invoke them from either `pull_request` or `push`"
        in guide
    )
