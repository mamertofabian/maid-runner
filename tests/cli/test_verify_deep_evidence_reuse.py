"""Behavioral contract for evidence-backed deep artifact coverage."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import yaml


def _write_project(
    root: Path,
    execution_log: Path,
    *,
    assertion: str = "assert target() is True",
    residual: bool = False,
) -> None:
    (root / "manifests").mkdir()
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "target.py").write_text("def target() -> bool:\n    return True\n")
    (root / "tests" / "test_target.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "from src.target import target\n\n"
        "def test_target():\n"
        "    log = Path(os.environ['MAID_EVIDENCE_EXECUTION_LOG'])\n"
        "    log.write_text(log.read_text() + 'pytest\\n')\n"
        f"    {assertion}\n"
    )
    commands = ["python -m pytest -q tests/test_target.py"]
    reads = ["tests/test_target.py"]
    if residual:
        (root / "tests" / "residual.py").write_text(
            "import os\n"
            "from pathlib import Path\n"
            "log = Path(os.environ['MAID_EVIDENCE_EXECUTION_LOG'])\n"
            "log.write_text(log.read_text() + 'residual\\n')\n"
        )
        commands.append("python tests/residual.py")
        reads.append("tests/residual.py")
    manifest = {
        "schema": "2",
        "goal": "Exercise evidence-backed deep coverage",
        "type": "refactor",
        "created": "2026-08-11T00:00:00Z",
        "files": {
            "edit": [
                {
                    "path": "src/target.py",
                    "artifacts": [
                        {
                            "kind": "function",
                            "name": "target",
                            "args": [],
                            "returns": "bool",
                        }
                    ],
                }
            ],
            "read": reads,
        },
        "validate": commands,
    }
    (root / "manifests" / "coverage.manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False)
    )
    execution_log.write_text("")


def _add_noncoverage_manifest(root: Path) -> None:
    (root / "docs.md").write_text("No executable coverage target.\n")
    (root / "tests" / "test_noncoverage.py").write_text(
        "import os\n"
        "from pathlib import Path\n\n"
        "def test_noncoverage():\n"
        "    log = Path(os.environ['MAID_EVIDENCE_EXECUTION_LOG'])\n"
        "    log.write_text(log.read_text() + 'noncoverage\\n')\n"
    )
    payload = {
        "schema": "2",
        "goal": "Keep noncoverage tests at the tests stage",
        "type": "refactor",
        "created": "2026-08-11T00:00:01Z",
        "files": {
            "edit": [
                {
                    "path": "docs.md",
                    "artifacts": [
                        {
                            "kind": "attribute",
                            "name": "documentation_marker",
                            "of": "documentation",
                            "type": "markdown",
                        }
                    ],
                }
            ],
            "read": ["tests/test_noncoverage.py"],
        },
        "validate": ["python -m pytest -q tests/test_noncoverage.py"],
    }
    (root / "manifests" / "noncoverage.manifest.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False)
    )


def _active_manifests(root: Path):
    from maid_runner.core.chain import get_cached_manifest_chain

    return get_cached_manifest_chain(root / "manifests", root).active_manifests()


def _verify(root: Path, **overrides):
    from maid_runner.cli.commands.verify import _run_verify_cached

    options = {
        "manifest_dir": "manifests/",
        "project_root": root,
        "allow_empty": False,
        "fail_fast": False,
        "check_assertions": False,
        "check_stubs": False,
        "fail_on_warnings": False,
        "artifact_coverage": True,
        "knockout": False,
    }
    options.update(overrides)
    return _run_verify_cached(**options)


def _stage(result, name: str):
    return next(stage for stage in result.stages if stage.name == name)


def _without_durations(value):
    if isinstance(value, dict):
        return {
            key: _without_durations(item)
            for key, item in value.items()
            if key != "duration_ms"
        }
    if isinstance(value, list):
        return [_without_durations(item) for item in value]
    return value


def test_deep_groups_coverage_execution_and_runs_ordinary_tests_fresh(
    tmp_path, monkeypatch
):
    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))

    result = _verify(tmp_path)

    assert _stage(result, "artifact_coverage").success is True
    assert _stage(result, "tests").success is True
    assert log.read_text().splitlines() == ["pytest", "pytest"]


def test_residual_and_nonpytest_commands_first_execute_at_tests_stage(
    tmp_path, monkeypatch
):
    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log, residual=True)
    _add_noncoverage_manifest(tmp_path)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))

    evidence = __import__(
        "maid_runner.cli.commands.verify",
        fromlist=["_collect_artifact_coverage_evidence"],
    )._collect_artifact_coverage_evidence(tmp_path, "manifests/")

    assert evidence is not None
    assert log.read_text().splitlines() == ["pytest"]

    result = _verify(tmp_path)

    assert _stage(result, "tests").success is True
    assert log.read_text().splitlines() == [
        "pytest",
        "pytest",
        "pytest",
        "noncoverage",
        "residual",
    ]


def test_instrumentation_observable_test_cannot_create_false_green_tests_stage(
    tmp_path, monkeypatch
):
    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(
        tmp_path,
        log,
        assertion=("assert target() and __import__('sys').getprofile() is not None"),
    )
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))

    result = _verify(tmp_path)

    assert _stage(result, "artifact_coverage").success is True
    assert _stage(result, "tests").success is False
    assert _stage(result, "tests")._tests.failed == 1


def test_deep_preserves_artifact_coverage_before_tests_stage_output(
    tmp_path, monkeypatch
):
    from maid_runner.cli.commands._format import format_verify_result

    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))

    result = _verify(tmp_path)
    names = [stage.name for stage in result.stages]
    payload_names = [
        stage["name"]
        for stage in json.loads(format_verify_result(result, json_mode=True))["stages"]
    ]

    assert names.index("artifact_coverage") < names.index("tests")
    assert payload_names.index("artifact_coverage") < payload_names.index("tests")


def test_deep_json_matches_legacy_findings_and_fresh_tests_except_durations(
    tmp_path, monkeypatch
):
    from maid_runner.cli.commands._format import _test_result_to_dict
    from maid_runner.cli.commands.validate import (
        _merge_artifact_coverage_reports,
        _run_artifact_coverage_by_manifest,
        _run_artifact_coverage_for_manifest_dir,
    )
    from maid_runner.core.runtime_evidence import collect_runtime_evidence
    from maid_runner.core.test_runner import run_tests

    optimized_root = tmp_path / "optimized"
    legacy_root = tmp_path / "legacy"
    optimized_root.mkdir()
    legacy_root.mkdir()
    optimized_log = tmp_path / "optimized.log"
    legacy_log = tmp_path / "legacy.log"
    _write_project(optimized_root, optimized_log)
    _write_project(legacy_root, legacy_log)

    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(optimized_log))
    evidence = collect_runtime_evidence(
        _active_manifests(optimized_root), optimized_root
    ).evidence
    optimized_coverage = _merge_artifact_coverage_reports(
        _run_artifact_coverage_by_manifest(
            "manifests/", optimized_root, evidence=evidence
        ).values()
    )
    optimized_tests = run_tests(manifest_dir="manifests/", project_root=optimized_root)

    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(legacy_log))
    legacy_coverage = _run_artifact_coverage_for_manifest_dir("manifests/", legacy_root)
    legacy_tests = run_tests(manifest_dir="manifests/", project_root=legacy_root)

    assert _without_durations(optimized_coverage.to_dict()) == _without_durations(
        legacy_coverage.to_dict()
    )
    assert _without_durations(
        _test_result_to_dict(optimized_tests)
    ) == _without_durations(_test_result_to_dict(legacy_tests))


def test_self_mutating_test_failure_remains_visible_at_fresh_tests_stage(
    tmp_path, monkeypatch
):
    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(
        tmp_path,
        log,
        assertion=(
            "assert target() and " "log.read_text().splitlines().count('pytest') == 1"
        ),
    )
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))

    result = _verify(tmp_path)

    assert _stage(result, "artifact_coverage").success is True
    assert _stage(result, "tests").success is False
    assert log.read_text().splitlines() == ["pytest", "pytest"]


def test_artifact_coverage_fail_fast_does_not_emit_later_tests_stage(
    tmp_path, monkeypatch
):
    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log, assertion="assert target() is False")
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))

    result = _verify(tmp_path, fail_fast=True)

    assert _stage(result, "artifact_coverage").success is False
    assert "tests" not in [stage.name for stage in result.stages]


def test_changed_content_or_command_plan_runs_exact_coverage_fallback(
    tmp_path, monkeypatch
):
    from maid_runner.cli.commands.validate import _run_artifact_coverage_by_manifest
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    for mutation in ("content", "command"):
        root = tmp_path / mutation
        root.mkdir()
        log = tmp_path / f"{mutation}.log"
        _write_project(root, log)
        monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))
        evidence = collect_runtime_evidence(_active_manifests(root), root).evidence
        if mutation == "content":
            path = root / "tests" / "test_target.py"
            path.write_text(path.read_text() + "\n# changed after evidence\n")
        else:
            path = root / "manifests" / "coverage.manifest.yaml"
            payload = yaml.safe_load(path.read_text())
            payload["validate"][0] += " --tb=short"
            path.write_text(yaml.safe_dump(payload, sort_keys=False))

        reports = _run_artifact_coverage_by_manifest(
            "manifests/", root, evidence=evidence
        )

        assert all(report.success for report in reports.values())
        assert log.read_text().splitlines() == ["pytest", "pytest"]


def test_verify_worker_override_reaches_evidence_and_fresh_tests_path(
    tmp_path, monkeypatch
):
    import maid_runner.core.runtime_evidence as evidence_module
    import maid_runner.core.test_runner as test_runner

    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))
    observed = []
    real_collect = evidence_module.collect_runtime_evidence
    real_run_tests = test_runner.run_tests

    def recording_collect(*args, **kwargs):
        observed.append(("coverage", kwargs.get("pytest_workers")))
        return real_collect(*args, **kwargs)

    def recording_tests(*args, **kwargs):
        observed.append(("tests", kwargs.get("pytest_workers")))
        return real_run_tests(*args, **kwargs)

    monkeypatch.setattr(evidence_module, "collect_runtime_evidence", recording_collect)
    monkeypatch.setattr(test_runner, "run_tests", recording_tests)

    result = _verify(tmp_path, pytest_workers=1)

    assert _stage(result, "tests").success is True
    assert observed == [("coverage", 1), ("tests", 1)]


def test_changed_resolved_environment_identity_runs_exact_coverage_fallback(
    tmp_path, monkeypatch
):
    import maid_runner.core.runtime_evidence as evidence_module
    from maid_runner.cli.commands.validate import _run_artifact_coverage_by_manifest

    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))
    evidence = evidence_module.collect_runtime_evidence(
        _active_manifests(tmp_path), tmp_path
    ).evidence
    real_identity = evidence_module._environment_identity

    def changed_identity(command, root):
        return replace(real_identity(command, root), pytest_version="changed")

    monkeypatch.setattr(evidence_module, "_environment_identity", changed_identity)
    reports = _run_artifact_coverage_by_manifest(
        "manifests/", tmp_path, evidence=evidence
    )

    assert all(report.success for report in reports.values())
    assert log.read_text().splitlines() == ["pytest", "pytest"]


def test_intervening_generated_or_untracked_side_effect_runs_exact_coverage_fallback(
    tmp_path, monkeypatch
):
    import maid_runner.core.runtime_evidence as evidence_module
    from maid_runner.cli.commands.validate import _run_artifact_coverage_by_manifest
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    assertion = (
        "assert target(); " "__import__('pathlib').Path('src/target.py').unlink()"
    )
    verify_root = tmp_path / "verify"
    verify_root.mkdir()
    log = tmp_path / "verify.log"
    _write_project(verify_root, log, assertion=assertion)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))

    result = _verify(verify_root, fail_fast=True)

    assert _stage(result, "artifact_coverage").success is False
    assert "tests" not in [stage.name for stage in result.stages]
    assert not (verify_root / "src" / "target.py").exists()

    direct_root = tmp_path / "direct"
    direct_root.mkdir()
    direct_log = tmp_path / "direct.log"
    _write_project(direct_root, direct_log, assertion=assertion)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(direct_log))
    evidence = collect_runtime_evidence(
        _active_manifests(direct_root), direct_root
    ).evidence

    reports = _run_artifact_coverage_by_manifest(
        "manifests/", direct_root, evidence=evidence
    )

    assert any(not report.success for report in reports.values())

    failure_root = tmp_path / "failure"
    failure_root.mkdir()
    failure_log = tmp_path / "failure.log"
    _write_project(failure_root, failure_log)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(failure_log))

    def mutating_collection_failure(*args, **kwargs):
        del args, kwargs
        (failure_root / "src" / "target.py").unlink()
        raise RuntimeError("collection failed after project mutation")

    monkeypatch.setattr(
        evidence_module, "collect_runtime_evidence", mutating_collection_failure
    )
    failure_result = _verify(failure_root, fail_fast=True)

    assert _stage(failure_result, "artifact_coverage").success is False
    assert "tests" not in [stage.name for stage in failure_result.stages]


def test_project_conftest_uses_legacy_coverage_without_speculative_evidence(
    tmp_path, monkeypatch
):
    import maid_runner.core.runtime_evidence as evidence_module
    from maid_runner.cli.commands.verify import (
        _artifact_coverage_stage,
        _collect_artifact_coverage_evidence,
    )

    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log)
    (tmp_path / "conftest.py").write_text("# Project-owned pytest behavior.\n")
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))
    calls = []
    real_collect = evidence_module.collect_runtime_evidence

    def recording_collect(*args, **kwargs):
        calls.append((args, kwargs))
        return real_collect(*args, **kwargs)

    monkeypatch.setattr(evidence_module, "collect_runtime_evidence", recording_collect)

    evidence = _collect_artifact_coverage_evidence(tmp_path, "manifests/")
    stage = _artifact_coverage_stage(tmp_path, "manifests/", evidence=evidence)

    assert evidence is not None
    assert len(calls) == 1
    assert stage.success is True
    assert log.read_text().splitlines() == ["pytest"]


def test_knockout_keeps_ordinary_tests_fresh_after_coverage(tmp_path, monkeypatch):
    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))

    result = _verify(tmp_path, knockout=True, knockout_limit=0)

    assert _stage(result, "knockout").success is True
    assert _stage(result, "tests").success is True
    assert log.read_text().splitlines() == ["pytest", "pytest"]
