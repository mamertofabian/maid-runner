"""Regression tests for task-scoped `maid verify` test execution."""

from __future__ import annotations

import json
import os
import textwrap

from maid_runner.cli.commands._main import main
from maid_runner.cli.commands.verify import (
    _should_scope_tests_to_task,
    _task_scoped_test_manifest_paths,
    _tests_stage,
)
from maid_runner.core.result import (
    ErrorCode,
    Severity,
    ValidationError,
    VerificationResult,
    VerificationStageResult,
)
from tests.cli.test_verify_cmd import _commit_all, _write_verify_project


def test_verify_task_scoped_tests_stage_runs_only_changed_manifest_commands(
    tmp_path,
    capsys,
):
    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="historical-task",
        test_source=(
            "from src.gate import gate\n\n\n"
            "def test_historical_gate():\n    assert gate() == 'not ok'\n"
        ),
        validate_command="python -m pytest tests/test_gate.py -q",
        created="2026-07-01T00:00:00Z",
    )
    baseline = _commit_all(tmp_path, "baseline")

    (tmp_path / "src" / "task.py").write_text(
        "def task_gate() -> str:\n    value = 'task'\n    return value\n"
    )
    (tmp_path / "tests" / "test_task.py").write_text(
        "from src.task import task_gate\n\n\n"
        "def test_task_gate():\n    assert task_gate() == 'task'\n"
    )
    (tmp_path / "manifests" / "changed-task.manifest.yaml").write_text(
        textwrap.dedent(
            """\
            schema: "2"
            goal: "Verify the changed task"
            type: feature
            created: "2026-07-02T00:00:00Z"
            files:
              create:
                - path: src/task.py
                  artifacts:
                    - kind: function
                      name: task_gate
                      returns: str
              read:
                - tests/test_task.py
              scope:
                - path: tests/test_task.py
                  reason: Task-owned behavioral test for the changed manifest.
            validate:
              - python -m pytest tests/test_task.py -q
            """
        )
    )

    exit_code = main(
        [
            "verify",
            "--json",
            "--keep-going",
            "--file-tracking-scope",
            "task",
            "--plan-lock-scope",
            "task",
            "--since",
            baseline,
            "--include-tests",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    stages = {stage["name"]: stage for stage in payload["stages"]}
    assert stages["tests"]["success"] is True
    assert stages["tests"]["details"]["total"] == 1
    assert stages["tests"]["details"]["results"][0]["manifest"] == "changed-task"


def test_task_scoped_tests_stage_stops_before_commands_on_chain_errors(
    tmp_path,
    monkeypatch,
):
    command_calls: list[tuple[str, ...]] = []

    class BrokenChain:
        def diagnostics(self):
            return [
                ValidationError(
                    code=ErrorCode.SCHEMA_VALIDATION_ERROR,
                    message="broken active manifest chain",
                    severity=Severity.ERROR,
                )
            ]

        def active_manifests(self):
            raise AssertionError("active manifests should not be read")

    def fake_chain(*args, **kwargs):
        return BrokenChain()

    def fake_run_command(command, **kwargs):
        command_calls.append(command)
        raise AssertionError("validation commands should not execute")

    monkeypatch.setattr("maid_runner.core.chain.get_cached_manifest_chain", fake_chain)
    monkeypatch.setattr("maid_runner.core.test_runner.run_command", fake_run_command)

    stage = _tests_stage(
        tmp_path,
        "manifests",
        fail_fast=False,
        manifest_paths=("manifests/changed-task.manifest.yaml",),
    )

    assert stage.success is False
    assert stage._tests is not None
    assert stage._tests.total == 0
    assert [error.code for error in stage._tests.chain_errors] == [
        ErrorCode.SCHEMA_VALIDATION_ERROR
    ]
    assert command_calls == []


def test_handoff_profile_forwards_task_test_scope_to_verify(
    monkeypatch,
    capsys,
):
    captured: dict[str, object] = {}

    def fake_run_verify(**kwargs):
        captured.update(kwargs)
        return VerificationResult(stages=(), duration_ms=0.0)

    monkeypatch.setattr("maid_runner.cli.commands.verify._run_verify", fake_run_verify)

    exit_code = main(["verify", "--profile", "handoff", "--no-changed-scope"])

    assert exit_code == 0
    assert captured["test_scope"] == "task"
    assert captured["file_tracking_scope"] == "repository"
    assert captured["plan_lock_scope"] == "repository"
    assert "--test-scope task" in capsys.readouterr().out


def test_explicit_task_test_scope_runs_only_changed_manifest_commands(
    tmp_path,
    capsys,
):
    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="historical-task",
        test_source=(
            "from src.gate import gate\n\n\n"
            "def test_historical_gate():\n    assert gate() == 'not ok'\n"
        ),
        validate_command="python -m pytest tests/test_gate.py -q",
        created="2026-07-01T00:00:00Z",
    )
    baseline = _commit_all(tmp_path, "baseline")
    _write_changed_task_manifest(tmp_path, command_succeeds=True)

    exit_code = main(
        [
            "verify",
            "--json",
            "--keep-going",
            "--test-scope",
            "task",
            "--since",
            baseline,
            "--include-tests",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    stages = {stage["name"]: stage for stage in payload["stages"]}
    assert stages["schema"]["details"]["total"] == 2
    assert stages["behavioral"]["details"]["total"] == 2
    assert stages["implementation"]["details"]["total"] == 2
    assert stages["tests"]["details"]["total"] == 1
    assert stages["tests"]["details"]["results"][0]["manifest"] == "changed-task"


def test_explicit_repository_test_scope_overrides_handoff_profile(
    tmp_path,
    monkeypatch,
    capsys,
):
    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="historical-task",
        created="2026-07-01T00:00:00Z",
    )
    baseline = _commit_all(tmp_path, "baseline")
    _write_changed_task_manifest(tmp_path, command_succeeds=True)
    from maid_runner.core import test_runner

    observed_commands: list[tuple[str, ...]] = []
    real_run_command = test_runner.run_command

    def observe_run_command(command, **kwargs):
        observed_commands.append(command)
        return real_run_command(command, **kwargs)

    monkeypatch.setattr(
        "maid_runner.cli.commands.verify._plan_lock_stage",
        lambda *args, **kwargs: VerificationStageResult(
            name="plan_lock",
            success=True,
        ),
    )
    monkeypatch.setattr(test_runner, "run_command", observe_run_command)

    exit_code = main(
        [
            "verify",
            "--profile",
            "handoff",
            "--test-scope",
            "repository",
            "--json",
            "--keep-going",
            "--since",
            baseline,
            "--include-tests",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["success"] is True
    assert len(observed_commands) == 1
    assert "tests/test_gate.py" in observed_commands[0]
    assert "tests/test_task.py" in observed_commands[0]


def test_task_test_scope_discloses_full_scope_widening_when_baseline_is_unresolvable(
    tmp_path,
    capsys,
):
    os.chdir(tmp_path)
    _write_verify_project(tmp_path, created="2026-07-01T00:00:00Z")
    _commit_all(tmp_path, "baseline")

    exit_code = main(
        [
            "verify",
            "--json",
            "--keep-going",
            "--no-changed-scope",
            "--test-scope",
            "task",
            "--since",
            "missing-baseline",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    stages = {stage["name"]: stage for stage in payload["stages"]}
    assert stages["tests"]["details"]["total"] == 1
    [widening] = stages["tests"]["details"]["chain_errors"]
    assert widening["code"] == "E708"
    assert widening["severity"] == "warning"
    assert "tests-stage selection widened" in widening["message"]
    assert widening["suggestion"] == "Pass a baseline commit this checkout contains."


def test_task_test_scope_propagates_selected_command_failure(
    tmp_path,
    capsys,
):
    os.chdir(tmp_path)
    _write_verify_project(tmp_path, created="2026-07-01T00:00:00Z")
    baseline = _commit_all(tmp_path, "baseline")
    _write_changed_task_manifest(tmp_path, command_succeeds=False)

    exit_code = main(
        [
            "verify",
            "--json",
            "--keep-going",
            "--test-scope",
            "task",
            "--since",
            baseline,
            "--include-tests",
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    tests_stage = next(stage for stage in payload["stages"] if stage["name"] == "tests")
    assert tests_stage["details"]["total"] == 1
    assert tests_stage["details"]["failed"] == 1
    assert tests_stage["details"]["results"][0]["manifest"] == "changed-task"


def test_task_test_scope_selection_changes_when_baseline_changes(tmp_path):
    os.chdir(tmp_path)
    _write_verify_project(tmp_path, created="2026-07-01T00:00:00Z")
    first_baseline = _commit_all(tmp_path, "first baseline")
    _write_changed_task_manifest(tmp_path, command_succeeds=True)
    second_baseline = _commit_all(tmp_path, "second baseline")

    first_selection = _task_scoped_test_manifest_paths(
        tmp_path, "manifests", first_baseline, None
    )
    second_selection = _task_scoped_test_manifest_paths(
        tmp_path, "manifests", second_baseline, None
    )

    assert first_selection is not None
    assert tuple(path.removeprefix(f"{tmp_path}/") for path in first_selection) == (
        "manifests/changed-task.manifest.yaml",
    )
    assert second_selection == ()


def test_explicit_test_scope_preserves_legacy_task_scope_triggers():
    assert _should_scope_tests_to_task(test_scope="task") is True
    assert _should_scope_tests_to_task(file_tracking_scope="task") is True
    assert _should_scope_tests_to_task(plan_lock_scope="task") is True
    assert _should_scope_tests_to_task() is False


def _write_changed_task_manifest(tmp_path, *, command_succeeds: bool) -> None:
    (tmp_path / "src" / "task.py").write_text(
        "def task_gate() -> str:\n    value = 'task'\n    return value\n"
    )
    expected = "task" if command_succeeds else "wrong"
    (tmp_path / "tests" / "test_task.py").write_text(
        "from src.task import task_gate\n\n\n"
        f"def test_task_gate():\n    assert task_gate() == {expected!r}\n"
    )
    (tmp_path / "manifests" / "changed-task.manifest.yaml").write_text(
        textwrap.dedent(
            """\
            schema: "2"
            goal: "Verify the changed task"
            type: feature
            created: "2026-07-02T00:00:00Z"
            files:
              create:
                - path: src/task.py
                  artifacts:
                    - kind: function
                      name: task_gate
                      returns: str
              read:
                - tests/test_task.py
              scope:
                - path: tests/test_task.py
                  reason: Task-owned behavioral test for the changed manifest.
            validate:
              - python -m pytest tests/test_task.py -q
            """
        )
    )
