"""Unknown runner instrumentation must not become claimed artifact nonexecution."""

import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
from pytest import CaptureFixture, MonkeyPatch
import yaml

from maid_runner.cli.commands.verify import cmd_verify
from maid_runner.core.artifact_coverage import (
    evaluate_artifact_coverage_from_evidence,
    run_artifact_coverage,
    run_artifact_coverage_batch,
)
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode, Severity
from maid_runner.core.runtime_evidence import collect_runtime_evidence

_MODES = ["exact", "batch", "batch-isolated", "evidence-exact", "evidence-derived"]


def _project(root: Path, *, runner: str = "unittest", mixed: bool = False):
    (root / "manifests").mkdir()
    (root / "target.py").write_text(
        "def answer() -> int:\n    result = 6 * 7\n    return result\n\n"
        "def other() -> int:\n    result = 7 * 6\n    return result\n"
    )
    (root / "test_target.py").write_text(
        "import unittest\nfrom target import answer, other\n"
        "class AnswerTests(unittest.TestCase):\n"
        "    def test_answer(self):\n        self.assertEqual(answer(), 42)\n"
        "        self.assertEqual(other(), 42)\n"
    )
    (root / "test_pytest.py").write_text(
        "from target import answer\ndef test_answer():\n    assert answer() == 42\n"
    )
    commands = {
        "unittest": ["python", "-m", "unittest", "test_target", "-q"],
        "django": ["python", "manage.py", "test", "test_target"],
        "docker": [
            "docker",
            "exec",
            "backend",
            "python",
            "manage.py",
            "test",
            "test_target",
        ],
        "registered": ["scripts/backend-tests", "test_target"],
        "pytest-alias": ["uv", "run", "--no-sync", "py.test", "test_target.py", "-q"],
    }
    (root / "manage.py").write_text(
        "raise RuntimeError('must not execute Django on host')\n"
    )
    if runner == "registered":
        (root / "scripts").mkdir()
        script = root / "scripts/backend-tests"
        script.write_text("#!/bin/sh\ntouch HOST_COMMAND_EXECUTED\nexit 99\n")
        script.chmod(0o755)
        (root / ".maidrc.yaml").write_text(
            yaml.safe_dump(
                {
                    "test_runner_wrappers": [
                        {"command": "scripts/backend-tests", "runner": "django"}
                    ]
                }
            )
        )
    validate = [commands[runner]]
    if mixed:
        validate.insert(0, ["python", "-m", "pytest", "test_pytest.py", "-q"])
    data = {
        "schema": "2",
        "goal": "Observe target execution",
        "type": "fix",
        "created": "2026-10-21T00:00:00Z",
        "files": {
            "edit": [
                {
                    "path": "target.py",
                    "artifacts": [
                        {"kind": "function", "name": name, "args": [], "returns": "int"}
                        for name in ("answer", "other")
                    ],
                }
            ],
            "read": ["test_target.py", "test_pytest.py"],
        },
        "validate": validate,
    }
    path = root / "manifests/coverage.manifest.yaml"
    path.write_text(yaml.safe_dump(data))
    return load_manifest(path)


def _report(manifest, root: Path, mode: str):
    if mode == "exact":
        return run_artifact_coverage(manifest, root)
    if mode.startswith("batch"):
        return run_artifact_coverage_batch(
            [manifest], root, jobs=2 if mode == "batch-isolated" else 1, max_processes=2
        )[manifest.source_path]
    evidence = collect_runtime_evidence([manifest], root).evidence
    result = evaluate_artifact_coverage_from_evidence(
        [manifest], root, evidence, evidence_mode=mode.removeprefix("evidence-")
    )
    assert result.complete is False
    return result.reports[manifest.source_path]


def _assert_unavailable(report) -> None:
    assert not report.success
    assert report.provenance != "exact"
    assert all(
        error.code != ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS
        for error in report.errors
    )
    unavailable = [
        error
        for error in report.errors
        if error.code == ErrorCode.VALIDATOR_NOT_AVAILABLE
    ]
    assert unavailable
    assert all(error.severity == Severity.ERROR for error in unavailable)
    assert all("instrumentation" in error.message.lower() for error in unavailable)


@pytest.mark.parametrize("mode", _MODES)
def test_real_unittest_execution_is_not_reported_as_nonexecution(
    tmp_path: Path, mode: str
) -> None:
    manifest = _project(tmp_path)
    actual = subprocess.run(
        manifest.validate_commands[0], cwd=tmp_path, capture_output=True, text=True
    )
    assert actual.returncode == 0, actual.stdout + actual.stderr

    report = _report(manifest, tmp_path, mode)

    _assert_unavailable(report)
    assert not report.findings


@pytest.mark.parametrize("runner", ["django", "docker", "registered"])
@pytest.mark.parametrize("mode", _MODES)
def test_isolated_runners_report_limit_without_host_execution(
    tmp_path: Path, runner: str, mode: str
) -> None:
    manifest = _project(tmp_path, runner=runner)

    report = _report(manifest, tmp_path, mode)

    _assert_unavailable(report)
    assert not report.findings
    assert not (tmp_path / "HOST_COMMAND_EXECUTED").exists()
    assert any(
        manifest.validate_commands[0][0] in error.message for error in report.errors
    )


@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize("observed_all", [False, True])
@pytest.mark.parametrize("runner", ["unittest", "pytest-alias"])
def test_mixed_test_runners_preserve_observations_without_claiming_complete_evidence(
    tmp_path: Path, mode: str, observed_all: bool, runner: str
) -> None:
    manifest = _project(tmp_path, runner=runner, mixed=True)
    if observed_all:
        (tmp_path / "test_pytest.py").write_text(
            "from target import answer, other\ndef test_answers():\n"
            "    assert answer() == other() == 42\n"
        )

    report = _report(manifest, tmp_path, mode)

    _assert_unavailable(report)
    expected = (
        [("answer", True), ("other", True)] if observed_all else [("answer", True)]
    )
    assert [
        (finding.artifact_name, finding.executed) for finding in report.findings
    ] == expected


@pytest.mark.parametrize("mode", _MODES)
def test_unrelated_validation_does_not_make_supported_python_coverage_incomplete(
    tmp_path: Path, mode: str
) -> None:
    manifest = _project(tmp_path)
    path = Path(manifest.source_path)
    data = yaml.safe_load(path.read_text())
    data["files"]["edit"][0]["artifacts"] = data["files"]["edit"][0]["artifacts"][:1]
    data["validate"] = [
        ["python", "-m", "pytest", "test_pytest.py", "-q"],
        ["ruff", "check", "target.py"],
        ["mypy", "target.py"],
        ["maid", "validate", "manifests/coverage.manifest.yaml"],
        ["pnpm", "exec", "vitest", "run", "frontend.test.ts"],
        ["deno", "test", "frontend_test.ts"],
        ["cargo", "test"],
    ]
    path.write_text(yaml.safe_dump(data))
    manifest = load_manifest(path)
    if mode.startswith("evidence-"):
        evidence = collect_runtime_evidence([manifest], tmp_path).evidence
        report = evaluate_artifact_coverage_from_evidence(
            [manifest], tmp_path, evidence, evidence_mode=mode.removeprefix("evidence-")
        ).reports[manifest.source_path]
    else:
        report = _report(manifest, tmp_path, mode)

    assert report.success, report.errors
    assert [
        (finding.artifact_name, finding.executed) for finding in report.findings
    ] == [("answer", True)]


def test_instrumentation_unavailable_is_a_blocking_verify_stage(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = cmd_verify(
        SimpleNamespace(
            manifest_dir="manifests",
            artifact_coverage=True,
            json=True,
            no_cache=True,
            changed_scope=False,
        )
    )

    payload = json.loads(capsys.readouterr().out)
    stage = next(
        stage for stage in payload["stages"] if stage["name"] == "artifact_coverage"
    )
    assert exit_code == 1
    assert stage["success"] is False
    serialized = json.dumps(stage)
    assert "E307" in serialized and '"severity": "error"' in serialized
    assert "E710" not in serialized


@pytest.mark.parametrize("mode", _MODES)
def test_missing_test_instrumentation_does_not_claim_nonexecution(
    tmp_path: Path, mode: str
) -> None:
    manifest = _project(tmp_path)
    path = Path(manifest.source_path)
    data = yaml.safe_load(path.read_text())
    data["validate"] = [["ruff", "check", "target.py"]]
    path.write_text(yaml.safe_dump(data))

    report = _report(load_manifest(path), tmp_path, mode)

    _assert_unavailable(report)
    assert not report.findings


@pytest.mark.parametrize("mode", _MODES)
def test_abstract_only_contracts_need_no_runtime_instrumentation(
    tmp_path: Path, mode: str
) -> None:
    manifest = _project(tmp_path)
    (tmp_path / "target.py").write_text(
        "from abc import ABC, abstractmethod\nclass Reader(ABC):\n"
        "    @abstractmethod\n    def read(self) -> int:\n        ...\n"
    )
    (tmp_path / "test_target.py").write_text(
        "import unittest\nfrom target import Reader\nclass ReaderTests(unittest.TestCase):\n"
        "    def test_contract(self):\n        self.assertTrue(Reader.__abstractmethods__)\n"
    )
    path = Path(manifest.source_path)
    data = yaml.safe_load(path.read_text())
    data["files"]["edit"][0]["artifacts"] = [
        {"kind": "class", "name": "Reader"},
        {
            "kind": "method",
            "name": "read",
            "of": "Reader",
            "args": [],
            "returns": "int",
        },
    ]
    path.write_text(yaml.safe_dump(data))
    manifest = load_manifest(path)
    if mode.startswith("evidence-"):
        evidence = collect_runtime_evidence([manifest], tmp_path).evidence
        report = evaluate_artifact_coverage_from_evidence(
            [manifest], tmp_path, evidence, evidence_mode=mode.removeprefix("evidence-")
        ).reports[manifest.source_path]
    else:
        report = _report(manifest, tmp_path, mode)

    assert report.success, report.errors
    assert not report.findings
