from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
VALIDATION_WORKFLOW = ROOT / ".github/workflows/maid-validation.yml"
TEST_WORKFLOW = ROOT / ".github/workflows/maid-test.yml"
SETUP_DOC = ROOT / "docs/github-actions.md"


def _workflow(path: Path) -> dict:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    if True in workflow:
        workflow["on"] = workflow.pop(True)
    return workflow


def _run_steps(workflow: dict, job_name: str) -> list[str]:
    steps = workflow["jobs"][job_name]["steps"]
    return [step["run"] for step in steps if "run" in step]


def test_maid_validation_workflow_is_reusable_and_event_driven() -> None:
    workflow = _workflow(VALIDATION_WORKFLOW)
    triggers = workflow["on"]
    job = workflow["jobs"]["maid-validation"]
    runs = "\n".join(_run_steps(workflow, "maid-validation"))

    assert "workflow_call" in triggers
    assert "pull_request" in triggers
    assert "push" in triggers
    assert "base-ref" in triggers["workflow_call"]["inputs"]
    assert "test-jobs" in triggers["workflow_call"]["inputs"]
    assert "install-command" in triggers["workflow_call"]["inputs"]
    assert job["permissions"]["contents"] == "read"
    assert "actions/checkout" in str(job["steps"])
    assert 'echo "$HOME/.local/bin" >> "$GITHUB_PATH"' in runs
    assert ".cargo/bin" not in runs
    assert "uv sync" in runs
    assert ".maid/maid-verify.json" in str(job["steps"])
    assert "actions/upload-artifact" in str(job["steps"])


def test_maid_validation_workflow_uses_verify_with_explicit_pr_base_ref() -> None:
    source = VALIDATION_WORKFLOW.read_text(encoding="utf-8")

    assert "_maid_validation_reusable_workflow" in source
    assert "git fetch --no-tags --depth=1 origin" in source
    assert 'BASE_REF="origin/${{ github.base_ref }}"' in source
    assert "uv run maid verify" in source
    assert '--base-ref "$BASE_REF"' in source
    assert "--json" in source
    assert "--no-changed-scope" in source
    assert "$GITHUB_STEP_SUMMARY" in source
    assert 'exit "$VERIFY_EXIT"' in source


def test_maid_test_workflow_runs_contract_tests_and_coverage() -> None:
    workflow = _workflow(TEST_WORKFLOW)
    triggers = workflow["on"]
    runs = "\n".join(_run_steps(workflow, "maid-test"))
    workflow_text = TEST_WORKFLOW.read_text(encoding="utf-8")

    assert "_maid_test_reusable_workflow" in workflow_text
    assert "workflow_call" in triggers
    assert "coverage-command" in triggers["workflow_call"]["inputs"]
    assert "install-command" in triggers["workflow_call"]["inputs"]
    assert 'echo "$HOME/.local/bin" >> "$GITHUB_PATH"' in runs
    assert ".cargo/bin" not in runs
    assert "uv run maid test --json" in runs
    assert "coverage-command" in workflow_text
    assert ".maid/maid-test.json" in workflow_text
    assert "coverage.xml" in workflow_text
    assert "actions/upload-artifact" in workflow_text
    assert "$GITHUB_STEP_SUMMARY" in workflow_text


def test_github_actions_docs_show_downstream_setup_and_reporting() -> None:
    guide = SETUP_DOC.read_text(encoding="utf-8")

    assert "_github_actions_setup_guide" in guide
    assert (
        "uses: mamertofabian/maid-runner/.github/workflows/maid-validation.yml@main"
        in guide
    )
    assert (
        "uses: mamertofabian/maid-runner/.github/workflows/maid-test.yml@main" in guide
    )
    assert ".github/workflows/maid-validation.yml@v2" not in guide
    assert ".github/workflows/maid-test.yml@v2" not in guide
    assert "exact release tags" in guide
    assert "maid verify --base-ref" in guide
    assert "maid test --json" in guide
    assert "pull_request" in guide
    assert "push" in guide
    assert "workflow_call" in guide
    assert ".maid/maid-verify.json" in guide
    assert ".maid/maid-test.json" in guide
    assert "$GITHUB_STEP_SUMMARY" in guide
    assert "coverage-command" in guide
