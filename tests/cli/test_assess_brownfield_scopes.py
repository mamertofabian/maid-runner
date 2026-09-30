"""Regression contract for deep assessment in incremental MAID repositories."""

from __future__ import annotations

import json
from pathlib import Path
import shlex
import subprocess
from types import SimpleNamespace

import pytest

from maid_runner.cli.commands.assess import cmd_assess
from maid_runner.cli.commands._main import build_parser
from maid_runner.core.verify_profiles import apply_verify_profile


def _changed_repo(root: Path, *, sensitive: bool) -> str:
    target = root / ("src/auth/session.py" if sensitive else "src/widget.py")
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 1\n")
    legacy = root / "src/legacy.py"
    legacy.write_text("LEGACY = True\n")
    for argv in (
        ["git", "init", "-q"],
        [
            "git",
            "-c",
            "user.name=maid-test",
            "-c",
            "user.email=maid@example.test",
            "add",
            ".",
        ],
        [
            "git",
            "-c",
            "user.name=maid-test",
            "-c",
            "user.email=maid@example.test",
            "commit",
            "-qm",
            "baseline",
        ],
    ):
        subprocess.run(argv, cwd=root, check=True, capture_output=True)
    baseline = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    target.write_text("VALUE = 2\n")
    return baseline


def _assess(baseline: str, baseline_flag: str, *, json_mode: bool) -> SimpleNamespace:
    return SimpleNamespace(
        since=baseline if baseline_flag == "--since" else None,
        base_ref=baseline if baseline_flag == "--base-ref" else None,
        json=json_mode,
        manifest_dir=None,
    )


@pytest.mark.parametrize("baseline_flag", ["--since", "--base-ref"])
def test_deep_assessment_emits_task_tracking_and_lock_scopes(
    tmp_path: Path, monkeypatch, capsys, baseline_flag: str
) -> None:
    baseline = _changed_repo(tmp_path, sensitive=True)
    monkeypatch.chdir(tmp_path)

    result = cmd_assess(_assess(baseline, baseline_flag, json_mode=True))
    payload = json.loads(capsys.readouterr().out)
    argv = payload["verify_argv"]
    parsed = build_parser().parse_args(argv[1:])
    apply_verify_profile(parsed)

    assert result == 0
    assert payload["profile"] == "deep"
    assert parsed.file_tracking_scope == "task"
    assert parsed.plan_lock_scope == "task"
    assert parsed.test_scope == "task"
    assert parsed.require_plan_lock is True
    assert parsed.require_red_evidence is True
    assert parsed.artifact_coverage is True
    assert parsed.knockout is True
    assert argv[-2:] == [baseline_flag, baseline]
    assert shlex.split(payload["verify_command"]) == argv
    assert "--advisory" not in argv
    assert "--no-changed-scope" not in argv


def test_deep_assessment_text_and_json_emit_identical_task_scopes(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    baseline = _changed_repo(tmp_path, sensitive=True)
    monkeypatch.chdir(tmp_path)
    assert cmd_assess(_assess(baseline, "--since", json_mode=True)) == 0
    payload = json.loads(capsys.readouterr().out)

    assert cmd_assess(_assess(baseline, "--since", json_mode=False)) == 0
    output = capsys.readouterr().out
    command = next(
        line.removeprefix("Run: ")
        for line in output.splitlines()
        if line.startswith("Run: ")
    )

    assert shlex.split(command) == payload["verify_argv"]
    argv = shlex.split(command)
    assert argv[argv.index("--file-tracking-scope") + 1] == "task"
    assert argv[argv.index("--plan-lock-scope") + 1] == "task"


def test_handoff_assessment_and_explicit_deep_audits_keep_existing_defaults(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    baseline = _changed_repo(tmp_path, sensitive=False)
    monkeypatch.chdir(tmp_path)

    assert cmd_assess(_assess(baseline, "--since", json_mode=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    manual = build_parser().parse_args(
        ["verify", "--profile", "deep", "--since", baseline]
    )
    apply_verify_profile(manual)

    assert payload["profile"] == "handoff"
    assert "--file-tracking-scope" not in payload["verify_argv"]
    assert "--plan-lock-scope" not in payload["verify_argv"]
    assert manual.file_tracking_scope == "repository"
    assert manual.plan_lock_scope == "repository"
    assert manual.artifact_coverage is True
    assert manual.knockout is True
