"""CLI tests for disclosing plan-lock scope widening in `maid verify`.

When the changed-scope baseline cannot be resolved, verify keeps enforcing plan
locks across every active manifest (067-07's deliberate fail-closed choice) but
previously said nothing about why. These tests pin the disclosure: the widening
is reported, it names the conflicting manifests, and it never relaxes or
tightens which manifests are enforced.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from maid_runner.cli.commands.verify import cmd_verify
from maid_runner.core.diagnostics_registry import get_rule
from maid_runner.core.plan_lock import create_plan_lock, default_plan_lock_path
from maid_runner.core.result import (
    ErrorCode,
    Severity,
    ValidationError,
    VerificationResult,
    VerificationStageResult,
)
from maid_runner.core.verify_summary import build_verify_summary


def _git(tmp_path: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "user.name=maid-test",
            "-c",
            "user.email=maid-test@example.com",
            *args,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _write_module(tmp_path: Path, module: str, function: str) -> None:
    (tmp_path / "src" / f"{module}.py").write_text(
        f"def {function}() -> int:\n    value = 1\n    return value\n"
    )
    (tmp_path / "tests" / f"test_{module}.py").write_text(
        f"from src.{module} import {function}\n\n\n"
        f"def test_{function}_contract():\n    assert {function}() == 1\n"
    )


def _write_manifest(
    tmp_path: Path,
    slug: str,
    module: str,
    function: str,
    created: str,
    task_base: str | None = None,
) -> Path:
    metadata = f"metadata:\n  maid_task_base: {task_base}\n" if task_base else ""
    manifest_path = tmp_path / "manifests" / f"{slug}.manifest.yaml"
    manifest_path.write_text(
        f"""schema: "2"
goal: "Task for {module}"
type: feature
created: "{created}"
{metadata}files:
  create:
    - path: src/{module}.py
      artifacts:
        - kind: function
          name: {function}
          returns: int
  read:
    - tests/test_{module}.py
validate:
  - python -m pytest -q tests/test_{module}.py
"""
    )
    return manifest_path


def _seed_repo(tmp_path: Path) -> None:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "README.md").write_text("seed\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "seed")


def _add_locked_task(
    tmp_path: Path,
    slug: str,
    module: str,
    function: str,
    task_base: str | None,
) -> Path:
    _write_module(tmp_path, module, function)
    path = _write_manifest(
        tmp_path, slug, module, function, "2026-07-26T00:00:00Z", task_base
    )
    create_plan_lock(path, tmp_path).save(default_plan_lock_path(tmp_path, slug))
    return path


def _verify_args(**overrides) -> argparse.Namespace:
    values = {
        "manifest_dir": "manifests/",
        "allow_empty": False,
        "fail_fast": False,
        "strict": False,
        "fail_on_warnings": False,
        "advisory": False,
        "worktree_scope": False,
        "changed_scope": False,
        "since": None,
        "base_ref": None,
        "include_tests": False,
        "test_jobs": 1,
        "require_plan_lock": False,
        "require_red_evidence": False,
        "summary": False,
        "json": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _plan_lock_findings(payload: dict) -> list[dict]:
    stages = {stage["name"]: stage for stage in payload["stages"]}
    return stages["plan_lock"].get("details", {}).get("errors", [])


def _finding_codes(payload: dict) -> list[str]:
    return [finding["code"] for finding in _plan_lock_findings(payload)]


def _conflicting_task_repo(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    _add_locked_task(tmp_path, "alpha-task", "alpha", "alpha_demo", "aaaa111")
    _add_locked_task(tmp_path, "beta-task", "beta", "beta_demo", "bbbb222")


def test_conflicting_baselines_emit_scope_widened_warning_naming_manifests(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _conflicting_task_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    cmd_verify(_verify_args(require_plan_lock=True, json=True))

    payload = json.loads(capsys.readouterr().out)
    widening = [
        finding
        for finding in _plan_lock_findings(payload)
        if finding["code"] == ErrorCode.PLAN_LOCK_SCOPE_WIDENED.value
    ]

    assert len(widening) == 1
    message = widening[0]["message"]
    assert "manifests/alpha-task.manifest.yaml" in message
    assert "manifests/beta-task.manifest.yaml" in message
    assert "aaaa111" in message
    assert "bbbb222" in message


def test_scope_widened_warning_does_not_block_the_plan_lock_stage(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _conflicting_task_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    cmd_verify(_verify_args(require_plan_lock=True, json=True))

    payload = json.loads(capsys.readouterr().out)
    stages = {stage["name"]: stage for stage in payload["stages"]}

    assert ErrorCode.PLAN_LOCK_SCOPE_WIDENED.value in _finding_codes(payload)
    assert stages["plan_lock"]["success"] is True


def test_scope_widening_still_enforces_every_active_manifest(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _seed_repo(tmp_path)
    _write_module(tmp_path, "legacy", "legacy_demo")
    _write_manifest(
        tmp_path, "legacy-task", "legacy", "legacy_demo", "2026-06-01T00:00:00Z"
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "legacy history")
    _add_locked_task(tmp_path, "alpha-task", "alpha", "alpha_demo", "aaaa111")
    _add_locked_task(tmp_path, "beta-task", "beta", "beta_demo", "bbbb222")
    monkeypatch.chdir(tmp_path)

    exit_code = cmd_verify(_verify_args(require_plan_lock=True, json=True))

    payload = json.loads(capsys.readouterr().out)
    missing = [
        finding
        for finding in _plan_lock_findings(payload)
        if finding["code"] == ErrorCode.PLAN_LOCK_MISSING.value
    ]

    assert exit_code == 1
    assert ErrorCode.PLAN_LOCK_SCOPE_WIDENED.value in _finding_codes(payload)
    assert any(
        "legacy-task.manifest.yaml" in finding["location"]["file"]
        for finding in missing
    )


def test_scope_widened_warning_is_rendered_in_summary_output(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _conflicting_task_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    cmd_verify(_verify_args(require_plan_lock=True, summary=True))

    out = capsys.readouterr().out

    assert ErrorCode.PLAN_LOCK_SCOPE_WIDENED.value in out
    # The actionable content must survive rendering, not just the code.
    assert "manifests/alpha-task.manifest.yaml" in out
    assert "manifests/beta-task.manifest.yaml" in out
    assert "aaaa111" in out
    assert "bbbb222" in out


def test_missing_baseline_does_not_emit_scope_widened_warning(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _seed_repo(tmp_path)
    _add_locked_task(tmp_path, "alpha-task", "alpha", "alpha_demo", None)
    monkeypatch.chdir(tmp_path)

    cmd_verify(_verify_args(require_plan_lock=True, json=True))

    payload = json.loads(capsys.readouterr().out)

    assert ErrorCode.PLAN_LOCK_SCOPE_WIDENED.value not in _finding_codes(payload)


def test_unresolvable_explicit_baseline_emits_scope_widened_warning(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _seed_repo(tmp_path)
    _add_locked_task(tmp_path, "alpha-task", "alpha", "alpha_demo", None)
    monkeypatch.chdir(tmp_path)

    cmd_verify(_verify_args(require_plan_lock=True, since="no-such-ref", json=True))

    payload = json.loads(capsys.readouterr().out)
    widening = [
        finding
        for finding in _plan_lock_findings(payload)
        if finding["code"] == ErrorCode.PLAN_LOCK_SCOPE_WIDENED.value
    ]

    assert len(widening) == 1
    assert "no-such-ref" in widening[0]["message"]


def test_resolved_baseline_emits_no_scope_widened_warning(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _seed_repo(tmp_path)
    head = _git(tmp_path, "rev-parse", "HEAD")
    _add_locked_task(tmp_path, "alpha-task", "alpha", "alpha_demo", head)
    _add_locked_task(tmp_path, "beta-task", "beta", "beta_demo", head)
    monkeypatch.chdir(tmp_path)

    cmd_verify(_verify_args(require_plan_lock=True, json=True))

    payload = json.loads(capsys.readouterr().out)

    assert ErrorCode.PLAN_LOCK_SCOPE_WIDENED.value not in _finding_codes(payload)


def test_plan_lock_stage_still_blocks_on_a_missing_plan_lock(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _seed_repo(tmp_path)
    head = _git(tmp_path, "rev-parse", "HEAD")
    _write_module(tmp_path, "alpha", "alpha_demo")
    _write_manifest(
        tmp_path, "alpha-task", "alpha", "alpha_demo", "2026-07-26T00:00:00Z", head
    )
    monkeypatch.chdir(tmp_path)

    exit_code = cmd_verify(_verify_args(require_plan_lock=True, json=True))

    payload = json.loads(capsys.readouterr().out)
    stages = {stage["name"]: stage for stage in payload["stages"]}

    assert stages["plan_lock"]["success"] is False
    assert ErrorCode.PLAN_LOCK_MISSING.value in _finding_codes(payload)
    assert exit_code == 1


def test_unreadable_working_tree_emits_scope_widened_warning(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    _add_locked_task(tmp_path, "alpha-task", "alpha", "alpha_demo", None)
    monkeypatch.chdir(tmp_path)

    cmd_verify(_verify_args(require_plan_lock=True, json=True))

    payload = json.loads(capsys.readouterr().out)
    widening = [
        finding
        for finding in _plan_lock_findings(payload)
        if finding["code"] == ErrorCode.PLAN_LOCK_SCOPE_WIDENED.value
    ]

    assert len(widening) == 1
    assert "working tree could not be read" in widening[0]["message"]


def test_contradictory_explicit_baselines_emit_scope_widened_warning(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _seed_repo(tmp_path)
    head = _git(tmp_path, "rev-parse", "HEAD")
    _add_locked_task(tmp_path, "alpha-task", "alpha", "alpha_demo", None)
    monkeypatch.chdir(tmp_path)

    cmd_verify(
        _verify_args(require_plan_lock=True, since=head, base_ref=head, json=True)
    )

    payload = json.loads(capsys.readouterr().out)
    widening = [
        finding
        for finding in _plan_lock_findings(payload)
        if finding["code"] == ErrorCode.PLAN_LOCK_SCOPE_WIDENED.value
    ]

    assert len(widening) == 1
    assert "could not be resolved" in widening[0]["message"]


def test_summary_collects_warning_and_info_findings_from_stage_errors() -> None:
    warning = ValidationError(
        code=ErrorCode.VALIDATOR_NOT_AVAILABLE,
        message="stage-level warning",
        severity=Severity.WARNING,
    )
    info = ValidationError(
        code=ErrorCode.GRANDFATHERED_SUPERSESSION,
        message="stage-level info",
        severity=Severity.INFO,
    )
    result = VerificationResult(
        stages=(
            VerificationStageResult(
                name="plan_lock",
                success=True,
                _errors=(warning, info),
            ),
        )
    )

    summary = build_verify_summary(result)

    assert [group.code for group in summary.warning_groups] == [
        ErrorCode.VALIDATOR_NOT_AVAILABLE.value
    ]
    assert [group.code for group in summary.info_groups] == [
        ErrorCode.GRANDFATHERED_SUPERSESSION.value
    ]
    assert summary.raw_warning_count == 1
    assert summary.raw_info_count == 1


def test_scope_widened_code_is_registered_as_a_warning_diagnostic() -> None:
    rule = get_rule(ErrorCode.PLAN_LOCK_SCOPE_WIDENED.value)

    assert rule.default_severity == Severity.WARNING.value
