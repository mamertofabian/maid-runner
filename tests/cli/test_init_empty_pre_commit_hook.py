"""Regression coverage for init's empty-repository pre-commit bootstrap."""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest
import yaml

from maid_runner.cli.commands._main import main


CONFIG_NAME = ".pre-commit-config.yaml"
GENERATED_PROFILE_ENTRY = "maid verify --profile pre-commit --since HEAD"
STALE_LITERAL_ENTRY = (
    "maid verify --summary --advisory --require-plan-lock "
    "--require-red-evidence --fail-fast --no-changed-scope "
    "--file-tracking-scope task --plan-lock-scope task --since HEAD"
)


def _maid_entry(project_root: Path) -> str:
    config = yaml.safe_load((project_root / CONFIG_NAME).read_text())
    return next(
        hook["entry"]
        for repo in config["repos"]
        for hook in repo.get("hooks", [])
        if hook.get("id") == "maid-verify"
    )


def _effective_args(entry: str):
    from maid_runner.cli.commands._main import build_parser
    from maid_runner.core.verify_profiles import apply_verify_profile

    argv = shlex.split(entry)
    args = build_parser().parse_args(argv[1:])
    apply_verify_profile(args)
    return argv, args


def test_generated_hook_passes_before_first_active_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "generic"]) == 0
    capsys.readouterr()

    argv, args = _effective_args(_maid_entry(tmp_path))

    assert args.allow_empty is True
    assert main(argv[1:]) == 0
    assert "VERIFY: PASS" in capsys.readouterr().out


def test_force_refresh_adds_allow_empty_without_removing_strict_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "generic"]) == 0

    config_path = tmp_path / CONFIG_NAME
    stale = config_path.read_text().replace(
        GENERATED_PROFILE_ENTRY, STALE_LITERAL_ENTRY
    )
    assert stale != config_path.read_text()
    config_path.write_text(stale)

    assert main(["init", "--tool", "generic", "--force"]) == 0
    refreshed = _maid_entry(tmp_path)
    _, args = _effective_args(refreshed)

    assert refreshed == GENERATED_PROFILE_ENTRY
    assert args.allow_empty is True
    assert args.require_plan_lock is True
    assert args.require_red_evidence is True
    assert args.file_tracking_scope == "task"
    assert args.plan_lock_scope == "task"
    assert args.since == "HEAD"
