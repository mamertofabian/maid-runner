"""Regression tests for release workflow prerequisites."""

from __future__ import annotations

from pathlib import Path

import yaml


def _run_steps_for_job(workflow_path: Path, job_name: str) -> list[str]:
    workflow = yaml.safe_load(workflow_path.read_text())
    steps = workflow["jobs"][job_name]["steps"]
    return [step["run"] for step in steps if "run" in step]


def test_publish_workflow_installs_npm_dependencies_before_maid_tests() -> None:
    runs = _run_steps_for_job(Path(".github/workflows/publish.yml"), "test")

    npm_install_index = runs.index("npm ci")
    maid_test_index = runs.index("uv run maid test")
    full_pytest_index = runs.index("uv run python -m pytest tests/ -v")

    assert npm_install_index < maid_test_index
    assert npm_install_index < full_pytest_index
