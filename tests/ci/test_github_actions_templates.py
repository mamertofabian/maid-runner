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


def _step_names(workflow: dict, job_name: str) -> list[str]:
    steps = workflow["jobs"][job_name]["steps"]
    return [step["name"] for step in steps if "name" in step]


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


def test_maid_validation_workflow_prepares_clean_checkout_assets() -> None:
    workflow = _workflow(VALIDATION_WORKFLOW)
    names = _step_names(workflow, "maid-validation")
    runs = "\n".join(_run_steps(workflow, "maid-validation"))

    assert "Install maid-runner npm dependencies when package lock exists" in names
    assert "Sync maid-runner packaged agent payloads when available" in names
    assert names.index("Install dependencies") < names.index(
        "Install maid-runner npm dependencies when package lock exists"
    )
    assert names.index(
        "Sync maid-runner packaged agent payloads when available"
    ) < names.index("Run MAID validation gate")
    assert (
        '[[ "${{ github.repository }}" == "mamertofabian/maid-runner" '
        "&& -f package-lock.json ]]" in runs
    )
    assert (
        '[[ "${{ github.repository }}" == "mamertofabian/maid-runner" '
        "&& -f scripts/sync_claude_files.py ]]" in runs
    )
    assert "npm ci" in runs
    assert "scripts/sync_claude_files.py" in runs


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


def test_maid_validation_workflow_declares_sarif_upload_as_opt_in() -> None:
    workflow = _workflow(VALIDATION_WORKFLOW)
    inputs = workflow["on"]["workflow_call"]["inputs"]
    validation_job = workflow["jobs"]["maid-validation"]

    assert "_sarif_upload_wiring" in VALIDATION_WORKFLOW.read_text(encoding="utf-8")
    assert inputs["upload-sarif"]["type"] == "boolean"
    assert inputs["upload-sarif"]["default"] is False
    assert validation_job["permissions"] == {"contents": "read"}
    assert "security-events" not in validation_job["permissions"]


def test_maid_validation_workflow_uploads_matching_sarif_report_when_enabled() -> None:
    workflow = _workflow(VALIDATION_WORKFLOW)
    validation_job = workflow["jobs"]["maid-validation"]
    upload_job = workflow["jobs"]["upload-sarif"]
    validation_runs = "\n".join(_run_steps(workflow, "maid-validation"))
    validation_steps = validation_job["steps"]
    upload_steps = upload_job["steps"]

    assert 'SARIF_PATH=".maid/maid-verify.sarif"' in validation_runs
    assert '--sarif "$SARIF_PATH"' in validation_runs
    assert upload_job["needs"] == "maid-validation"
    assert "always()" in upload_job["if"]
    assert "inputs.upload-sarif" in upload_job["if"]
    assert upload_job["permissions"]["security-events"] == "write"
    assert validation_steps[-1]["with"]["path"] == ".maid/maid-verify.sarif"
    assert "always()" in validation_steps[-1]["if"]
    assert "inputs.upload-sarif" in validation_steps[-1]["if"]
    assert "github/codeql-action/upload-sarif" in str(upload_steps)
    assert upload_steps[-1]["with"]["sarif_file"] == ".maid/maid-verify.sarif"


def test_maid_test_workflow_prepares_clean_checkout_assets() -> None:
    workflow = _workflow(TEST_WORKFLOW)
    names = _step_names(workflow, "maid-test")
    runs = "\n".join(_run_steps(workflow, "maid-test"))

    assert "Install maid-runner npm dependencies when package lock exists" in names
    assert "Sync maid-runner packaged agent payloads when available" in names
    assert names.index("Install dependencies") < names.index(
        "Install maid-runner npm dependencies when package lock exists"
    )
    assert names.index(
        "Sync maid-runner packaged agent payloads when available"
    ) < names.index("Run MAID test contract")
    assert (
        '[[ "${{ github.repository }}" == "mamertofabian/maid-runner" '
        "&& -f package-lock.json ]]" in runs
    )
    assert (
        '[[ "${{ github.repository }}" == "mamertofabian/maid-runner" '
        "&& -f scripts/sync_claude_files.py ]]" in runs
    )
    assert "npm ci" in runs
    assert "scripts/sync_claude_files.py" in runs


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
    assert "_sarif_upload_guidance" in guide
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
    assert "upload-sarif: true" in guide
    assert "security-events: write" in guide
    assert "actions: read" in guide
    assert "contents: read" in guide
    assert "GitHub Advanced Security" in guide
    assert "private repositories" in guide
    assert "failed validation" in guide
