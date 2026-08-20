"""Behavioral contract for hosted-runner pytest worker wiring."""

from pathlib import Path

import yaml

from maid_runner.core.config import load_config


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_github_workflows_bound_pytest_workers_without_lowering_local_default() -> None:
    config = load_config(PROJECT_ROOT).test_execution

    assert config.pytest_workers == 8
    assert 4 in config.accepted_pytest_worker_counts

    expected_workflows = {
        "maid-test.yml": (
            "maid-test",
            "Run MAID test contract",
            "_maid_test_pytest_worker_wiring",
            "uv run maid test",
        ),
        "maid-validation.yml": (
            "maid-validation",
            "Run MAID validation gate",
            "_maid_validation_pytest_worker_wiring",
            "uv run maid verify",
        ),
    }
    for workflow_name, (
        job_name,
        step_name,
        artifact_name,
        command_prefix,
    ) in expected_workflows.items():
        workflow_path = PROJECT_ROOT / ".github" / "workflows" / workflow_name
        workflow = yaml.load(workflow_path.read_text(), Loader=yaml.BaseLoader)
        inputs = workflow["on"]["workflow_call"]["inputs"]
        worker_input = inputs["pytest-workers"]
        assert worker_input["type"] == "number"
        assert worker_input["required"] == "false"
        assert "default" not in worker_input

        steps = workflow["jobs"][job_name]["steps"]
        maid_step = next(step for step in steps if step.get("name") == step_name)
        assert maid_step["env"]["PYTEST_WORKERS"] == (
            "${{ inputs['pytest-workers'] || "
            "(github.repository == 'mamertofabian/maid-runner' && 4) || '' }}"
        )
        run_script = maid_step["run"]
        assert "PYTEST_WORKER_ARGS=()" in run_script
        assert 'if [[ -n "$PYTEST_WORKERS" ]]; then' in run_script
        assert 'PYTEST_WORKER_ARGS=(--pytest-workers "$PYTEST_WORKERS")' in run_script
        command_lines = [
            line.strip()
            for line in run_script.splitlines()
            if line.strip().startswith(command_prefix)
        ]
        assert command_lines
        assert all('"${PYTEST_WORKER_ARGS[@]}"' in line for line in command_lines)
        assert artifact_name in workflow_path.read_text()

    guide = (PROJECT_ROOT / "docs" / "github-actions.md").read_text()
    assert "_github_actions_pytest_worker_guidance" in guide
    assert "`pytest-workers`" in guide
    assert "four pytest workers" in guide
    assert "eight-worker local default" in guide
    assert "retain their own repository worker policy" in guide
    assert "override" in guide
