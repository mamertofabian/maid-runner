"""Repository command_jobs uses the leftover process budget.

Contract: manifests/drafts/121-25-tune-maid-test-command-jobs.manifest.yaml
"""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.config import load_config

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_repository_command_jobs_use_remaining_process_budget() -> None:
    execution = load_config(REPO_ROOT).test_execution
    assert execution.command_jobs == 2
    assert execution.pytest_workers == 8
    assert execution.max_processes == 16
    assert execution.command_jobs * execution.pytest_workers <= execution.max_processes
