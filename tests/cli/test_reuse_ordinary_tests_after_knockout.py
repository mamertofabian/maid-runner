"""Reuse matching ordinary pytest groups after snapshot knockout.

Contract: manifests/drafts/121-28-reuse-ordinary-tests-after-isolated-knockout.manifest.yaml
"""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.knockout import KnockoutReport, KnockoutResult
from maid_runner.core.result import TestRunResult
from tests.cli.test_verify_deep_evidence_reuse import (
    _add_noncoverage_manifest,
    _stage,
    _verify,
    _write_project,
)


def test_matching_pytest_is_reused_after_snapshot_knockout(
    tmp_path: Path, monkeypatch
) -> None:
    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))
    _install_snapshot_knockout(monkeypatch)
    executed = _install_implementation_probe(monkeypatch)

    result = _verify(tmp_path, knockout=True)

    assert _stage(result, "artifact_coverage").success is True
    assert _stage(result, "knockout").success is True
    assert _stage(result, "tests").success is True
    assert [stage.name for stage in result.stages].count("tests") == 1
    assert [stage.name for stage in result.stages].index("artifact_coverage") < [
        stage.name for stage in result.stages
    ].index("tests")
    assert executed == []
    names = [stage.name for stage in result.stages]
    assert "artifact_coverage" in names and "tests" in names


def test_residual_commands_still_run_after_snapshot_knockout_reuse(
    tmp_path: Path, monkeypatch
) -> None:
    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log, residual=True)
    _add_noncoverage_manifest(tmp_path)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))
    _install_snapshot_knockout(monkeypatch)
    executed = _install_implementation_probe(monkeypatch, run_real=True)

    result = _verify(tmp_path, knockout=True)

    assert _stage(result, "tests").success is True
    commands = [command for command, _slug in executed]
    assert ("python", "-m", "pytest", "-q", "tests/test_target.py") not in commands
    assert ("python", "tests/residual.py") in commands
    assert ("python", "-m", "pytest", "-q", "tests/test_noncoverage.py") in commands


def test_changed_checkout_digest_keeps_ordinary_tests_fresh(
    tmp_path: Path, monkeypatch
) -> None:
    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))
    _install_snapshot_knockout(
        monkeypatch,
        mutate=lambda root: (root / "side-effect.txt").write_text("changed\n"),
    )
    executed = _install_implementation_probe(monkeypatch)

    result = _verify(tmp_path, knockout=True)

    assert _stage(result, "tests").success is True
    commands = [command for command, _slug in executed]
    assert ("python", "-m", "pytest", "-q", "tests/test_target.py") in commands


def _install_snapshot_knockout(monkeypatch, mutate=None) -> None:
    def fake_knockout(selected, project_root, **kwargs):
        if mutate is not None:
            mutate(project_root)
        report = KnockoutReport(
            results=(
                KnockoutResult(
                    artifact_name="target",
                    artifact_kind="function",
                    parent_class=None,
                    file_path="src/target.py",
                    detected=True,
                    duration_ms=1.0,
                ),
            ),
            errors=(),
        )
        return {item.source_path: report for item in selected}

    monkeypatch.setattr("maid_runner.core.knockout.run_knockout_batch", fake_knockout)


def _install_implementation_probe(monkeypatch, *, run_real: bool = False):
    from maid_runner.core import test_runner

    executed: list[tuple[tuple[str, ...], str]] = []
    original = test_runner._run_implementation_commands

    def fake_run(commands, *args, **kwargs):
        executed.extend((tuple(command), slug) for command, slug in commands)
        if run_real:
            return original(commands, *args, **kwargs)
        results = [
            TestRunResult(
                manifest_slug=slug,
                command=tuple(command),
                exit_code=0,
                stdout="",
                stderr="",
                duration_ms=0.0,
            )
            for command, slug in commands
        ]
        return results, len(results), 0, None

    monkeypatch.setattr(test_runner, "_run_implementation_commands", fake_run)
    return executed
