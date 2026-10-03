"""CI dependency installations must not share mutable uv-cache inodes."""

import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest
import yaml

from maid_runner.core._knockout_snapshot import SharedEnvironmentProjectSnapshotBackend


_ROOT = Path(__file__).resolve().parents[2]
_JOBS = (
    ("publish.yml", "test"),
    ("maid-validation.yml", "maid-validation"),
    ("maid-test.yml", "maid-test"),
)


def _write_probe_wheel(tmp_path):
    wheel = tmp_path / "maid_ci_probe-0.0.0-py3-none-any.whl"
    metadata = "maid_ci_probe-0.0.0.dist-info"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("maid_ci_probe/__init__.py", "VALUE = 1\n")
        archive.writestr(
            f"{metadata}/METADATA",
            "Metadata-Version: 2.1\nName: maid-ci-probe\nVersion: 0.0.0\n",
        )
        archive.writestr(
            f"{metadata}/WHEEL",
            "Wheel-Version: 1.0\nGenerator: maid-ci-test\n"
            "Root-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr(f"{metadata}/RECORD", "")
    return wheel


def _run(command, environment):
    result = subprocess.run(
        command, env=environment, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("workflow_name,job_name", _JOBS)
def test_ci_installation_remains_unchanged_during_external_cache_linking(
    tmp_path, workflow_name, job_name
):
    workflow = yaml.safe_load((_ROOT / ".github/workflows" / workflow_name).read_text())
    mode = workflow["jobs"][job_name].get("env", {}).get("UV_LINK_MODE")
    assert mode == "copy"
    environment = dict(
        os.environ, UV_CACHE_DIR=str(tmp_path / "cache"), UV_LINK_MODE=mode
    )
    wheel = _write_probe_wheel(tmp_path)
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "src/target.py").write_text("VALUE = 1\n")
    source_env = project / ".venv"
    consumer_env = tmp_path / "consumer/.venv"
    for virtual_env in (source_env, consumer_env):
        _run(["uv", "venv", str(virtual_env), "--python", sys.executable], environment)
    _run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(source_env / "bin/python"),
            "--offline",
            str(wheel),
        ],
        environment,
    )
    dependency = next(
        source_env.glob("lib/python*/site-packages/maid_ci_probe/__init__.py")
    )
    assert dependency.stat().st_nlink == 1

    with SharedEnvironmentProjectSnapshotBackend().create(
        project, ("src/target.py",), "ci-cache-link-isolation"
    ):
        _run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(consumer_env / "bin/python"),
                "--offline",
                str(wheel),
            ],
            dict(environment, UV_LINK_MODE="hardlink"),
        )
        consumer_dependency = next(
            consumer_env.glob("lib/python*/site-packages/maid_ci_probe/__init__.py")
        )
        assert consumer_dependency.stat().st_nlink > 1
        assert consumer_dependency.stat().st_ino != dependency.stat().st_ino

    assert dependency.stat().st_nlink == 1
    assert dependency.read_text() == "VALUE = 1\n"
