"""Reusable MAID jobs protect shared dependency environments at process startup."""

import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from maid_runner.core._knockout_snapshot import SharedEnvironmentProjectSnapshotBackend


_JOBS = (
    ("maid-validation.yml", "maid-validation"),
    ("maid-test.yml", "maid-test"),
)
_ROOT = Path(__file__).resolve().parents[2]


def _job(workflow_name, job_name):
    workflow = yaml.safe_load((_ROOT / ".github/workflows" / workflow_name).read_text())
    return workflow["jobs"][job_name]


def _apply_cache_setup(job, tmp_path, environment):
    step = next(
        (s for s in job["steps"] if s.get("name") == "Configure Python bytecode cache"),
        None,
    )
    if step is None:
        return
    assert job["steps"][0] is step
    environment_file = tmp_path / "github-env"
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", step["run"]],
        env=dict(
            environment, RUNNER_TEMP=str(tmp_path), GITHUB_ENV=str(environment_file)
        ),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    for line in environment_file.read_text().splitlines():
        key, value = line.split("=", 1)
        environment[key] = value


@pytest.mark.parametrize("workflow_name,job_name", _JOBS)
def test_maid_job_cold_import_keeps_dependency_environment_unchanged(
    tmp_path, workflow_name, job_name
):
    environment = dict(os.environ)
    environment.pop("PYTHONDONTWRITEBYTECODE", None)
    environment.pop("PYTHONPYCACHEPREFIX", None)
    _apply_cache_setup(_job(workflow_name, job_name), tmp_path, environment)
    root = tmp_path / "project"
    source = root / "src/target.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n")
    dependency = root / ".venv/lib/site-packages/cold_maid_dependency.py"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("VALUE = 1\n")

    with SharedEnvironmentProjectSnapshotBackend().create(
        root, ("src/target.py",), "maid-workflow-cold-import"
    ):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; "
                f"sys.path.insert(0, {str(dependency.parent)!r}); "
                "import cold_maid_dependency; assert cold_maid_dependency.VALUE == 1",
            ],
            env=environment,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    assert dependency.read_text() == "VALUE = 1\n"
    assert not (dependency.parent / "__pycache__").exists()
    cache_root = Path(environment["PYTHONPYCACHEPREFIX"])
    assert cache_root == tmp_path / "maid-python-cache"
    assert any(cache_root.rglob("cold_maid_dependency*.pyc"))


@pytest.mark.parametrize("workflow_name,job_name", _JOBS)
def test_maid_job_binds_uv_to_reusable_input_selected_interpreter(
    workflow_name, job_name
):
    job = _job(workflow_name, job_name)
    setup = next(step for step in job["steps"] if step.get("name") == "Set up Python")
    selected = setup["with"]["python-version"]

    assert selected == "${{ inputs['python-version'] || '3.12' }}"
    assert job.get("env", {}).get("UV_PYTHON") == selected
