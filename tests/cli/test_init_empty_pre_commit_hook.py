"""Regression coverage for init's empty-repository pre-commit bootstrap."""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest
import yaml

from maid_runner.cli.commands._main import main


CONFIG_NAME = ".pre-commit-config.yaml"
STRICT_HOOK_FLAGS = {
    "--require-plan-lock",
    "--require-red-evidence",
    "--file-tracking-scope",
    "--plan-lock-scope",
    "--since",
}


def _maid_entry(project_root: Path) -> str:
    config = yaml.safe_load((project_root / CONFIG_NAME).read_text())
    return next(
        hook["entry"]
        for repo in config["repos"]
        for hook in repo.get("hooks", [])
        if hook.get("id") == "maid-verify"
    )


def test_generated_hook_passes_before_first_active_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "generic"]) == 0
    capsys.readouterr()

    argv = shlex.split(_maid_entry(tmp_path))

    assert "--allow-empty" in argv
    assert main(argv[1:]) == 0
    assert "VERIFY: PASS" in capsys.readouterr().out


def test_force_refresh_adds_allow_empty_without_removing_strict_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "generic"]) == 0

    config_path = tmp_path / CONFIG_NAME
    stale = config_path.read_text().replace(" --allow-empty", "")
    config_path.write_text(stale)

    assert main(["init", "--tool", "generic", "--force"]) == 0
    refreshed = shlex.split(_maid_entry(tmp_path))

    assert "--allow-empty" in refreshed
    assert STRICT_HOOK_FLAGS.issubset(refreshed)
    assert refreshed[refreshed.index("--file-tracking-scope") + 1] == "task"
    assert refreshed[refreshed.index("--plan-lock-scope") + 1] == "task"
    assert refreshed[refreshed.index("--since") + 1] == "HEAD"
