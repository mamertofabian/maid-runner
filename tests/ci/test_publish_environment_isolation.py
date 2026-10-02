"""Publishing lanes keep their interpreter and shared dependencies stable."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from maid_runner.core._knockout_snapshot import SharedEnvironmentProjectSnapshotBackend


def _publish_environment():
    workflow = yaml.safe_load(Path(".github/workflows/publish.yml").read_text())
    return workflow["jobs"]["test"].get("env", {})


def _cold_dependency_project(tmp_path):
    root = tmp_path / "project"
    source = root / "src/target.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n")
    dependency = root / ".venv/lib/site-packages/cold_dependency.py"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("VALUE = 1\n")
    return root, dependency


def test_publish_cold_import_does_not_mutate_shared_snapshot_dependencies(tmp_path):
    root, dependency = _cold_dependency_project(tmp_path)
    environment = dict(os.environ)
    environment.pop("PYTHONDONTWRITEBYTECODE", None)
    environment.pop("PYTHONPYCACHEPREFIX", None)
    configured = _publish_environment()
    if "PYTHONPYCACHEPREFIX" in configured:
        environment["PYTHONPYCACHEPREFIX"] = configured["PYTHONPYCACHEPREFIX"].replace(
            "${{ runner.temp }}", str(tmp_path)
        )

    with SharedEnvironmentProjectSnapshotBackend().create(
        root, ("src/target.py",), "publish-cold-import"
    ):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; "
                f"sys.path.insert(0, {str(dependency.parent)!r}); "
                "import cold_dependency; assert cold_dependency.VALUE == 1",
            ],
            env=environment,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    assert dependency.read_text() == "VALUE = 1\n"
    assert not (dependency.parent / "__pycache__").exists()
    assert configured["PYTHONPYCACHEPREFIX"] == "${{ runner.temp }}/maid-python-cache"
    cache_root = Path(environment["PYTHONPYCACHEPREFIX"])
    assert cache_root.is_relative_to(tmp_path)
    assert any(cache_root.rglob("cold_dependency*.pyc"))


def test_publish_bytecode_policy_keeps_dependency_tampering_fail_closed(tmp_path):
    root, dependency = _cold_dependency_project(tmp_path)

    with pytest.raises(RuntimeError, match="source dependency environment"):
        with SharedEnvironmentProjectSnapshotBackend().create(
            root, ("src/target.py",), "publish-dependency-tamper"
        ):
            dependency.write_text("VALUE = 2\n")


def test_publish_uv_run_uses_matrix_interpreter_despite_project_python_pin(tmp_path):
    configured = _publish_environment()
    assert configured.get("UV_PYTHON") == "${{ matrix.python-version }}"
    environment = dict(os.environ)
    environment["UV_PYTHON"] = sys.executable
    environment.pop("VIRTUAL_ENV", None)
    environment.pop("UV_PROJECT_ENVIRONMENT", None)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "publish-matrix-probe"\nversion = "0.0.0"\n'
        'requires-python = ">=3.10"\n'
    )
    alternate_version = "3.11" if sys.version_info.minor == 12 else "3.12"
    (tmp_path / ".python-version").write_text(alternate_version + "\n")

    result = subprocess.run(
        [
            "uv",
            "run",
            "--offline",
            "python",
            "-c",
            "import json, sys; print(json.dumps(list(sys.version_info[:2])))",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == list(sys.version_info[:2])
