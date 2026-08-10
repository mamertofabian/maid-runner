"""Behavioral coverage for native-Windows ``maid init`` portability."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from maid_runner.cli.commands._main import main


def test_init_completes_without_descriptor_chmod(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delattr(os, "fchmod", raising=False)

    assert main(["init", "--tool", "generic"]) == 0

    assert (tmp_path / ".maidrc.yaml").is_file()
    assert (tmp_path / ".pre-commit-config.yaml").is_file()
    assert (tmp_path / ".gitignore").is_file()
    assert (tmp_path / "manifests" / "drafts" / "README.md").is_file()
    assert (tmp_path / "docs" / "draft-manifest-workflow.md").is_file()
    assert (tmp_path / "docs" / "manifest-outcome-records.md").is_file()


def test_init_preserves_descriptor_mode_when_fchmod_is_available(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    calls: list[tuple[int, int]] = []
    real_fchmod = getattr(os, "fchmod", None)

    def recording_fchmod(descriptor: int, mode: int) -> None:
        calls.append((descriptor, mode))
        if real_fchmod is not None:
            real_fchmod(descriptor, mode)

    monkeypatch.setattr(os, "fchmod", recording_fchmod, raising=False)

    assert main(["init", "--tool", "generic"]) == 0

    assert len(calls) == 2
    assert all(mode == 0o644 for _, mode in calls)


def test_windows_ci_runs_init_portability_regression() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/maid-test.yml").read_text())

    windows_job = workflow["jobs"]["windows-init-portability"]
    assert windows_job["runs-on"] == "windows-latest"
    assert windows_job["if"] == "github.repository == 'mamertofabian/maid-runner'"
    commands = "\n".join(str(step.get("run", "")) for step in windows_job["steps"])
    assert "uv sync --group dev" in commands
    assert "tests/cli/test_init_windows_portability.py" in commands
