from __future__ import annotations

import subprocess
from pathlib import Path

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode


def test_batch_reports_match_independent_reports_for_identical_command(
    tmp_path: Path,
) -> None:
    from maid_runner.core.artifact_coverage import (
        run_artifact_coverage,
        run_artifact_coverage_batch,
    )

    manifest_paths = _write_two_manifest_project(tmp_path)
    manifests = [load_manifest(path) for path in manifest_paths]
    executor = _RecordingExecutor(_runtime_record(tmp_path, executed={"alpha", "beta"}))

    independent = {
        manifest.source_path: run_artifact_coverage(
            manifest,
            tmp_path,
            executor=executor,
        ).to_dict()
        for manifest in manifests
    }
    batched = run_artifact_coverage_batch(
        manifests,
        tmp_path,
        executor=executor,
    )

    assert {path: report.to_dict() for path, report in batched.items()} == independent


def test_batch_executes_identical_pytest_command_once(
    tmp_path: Path,
) -> None:
    from maid_runner.core.artifact_coverage import run_artifact_coverage_batch

    manifests = [
        load_manifest(path)
        for path in _write_two_manifest_project(
            tmp_path,
            second_command="uv run python -m pytest -q tests/test_targets.py",
        )
    ]
    executor = _RecordingExecutor(_runtime_record(tmp_path, executed={"alpha", "beta"}))

    reports = run_artifact_coverage_batch(
        manifests,
        tmp_path,
        executor=executor,
    )

    assert len(executor.calls) == 1
    assert all(report.success for report in reports.values())
    assert [
        finding.artifact_name
        for report in reports.values()
        for finding in report.findings
    ] == [
        "alpha",
        "beta",
    ]


def test_batch_keeps_distinct_pytest_arguments_separate(
    tmp_path: Path,
) -> None:
    from maid_runner.core.artifact_coverage import run_artifact_coverage_batch

    manifest_paths = _write_two_manifest_project(
        tmp_path,
        first_command="python -m pytest -q tests/test_targets.py -k alpha",
        second_command="python -m pytest -q tests/test_targets.py -k beta",
    )
    manifests = [load_manifest(path) for path in manifest_paths]
    executor = _RecordingExecutor(_runtime_record(tmp_path, executed={"alpha", "beta"}))

    reports = run_artifact_coverage_batch(
        manifests,
        tmp_path,
        executor=executor,
    )

    assert len(executor.calls) == 2
    assert all(report.success for report in reports.values())


def test_batch_attributes_shared_command_failure_to_every_declaring_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from maid_runner.core.artifact_coverage import run_artifact_coverage_batch

    manifest_paths = _write_two_manifest_project(tmp_path, failing_test=True)
    manifests = [load_manifest(path) for path in manifest_paths]
    coverage_calls = _record_coverage_subprocesses(monkeypatch)

    reports = run_artifact_coverage_batch(manifests, tmp_path)

    assert len(coverage_calls) == 1
    assert list(reports) == [manifest.source_path for manifest in manifests]
    assert [[error.code for error in report.errors] for report in reports.values()] == [
        [ErrorCode.INTERNAL_ERROR],
        [ErrorCode.INTERNAL_ERROR],
    ]


def test_batch_preserves_manifest_order_and_json_shape(tmp_path: Path) -> None:
    from maid_runner.core.artifact_coverage import run_artifact_coverage_batch

    manifest_paths = _write_two_manifest_project(tmp_path)
    manifests = [load_manifest(path) for path in reversed(manifest_paths)]

    reports = run_artifact_coverage_batch(
        manifests,
        tmp_path,
        executor=_RecordingExecutor(
            _runtime_record(tmp_path, executed={"alpha", "beta"})
        ),
    )

    assert list(reports) == [manifest.source_path for manifest in manifests]
    assert [
        {
            "success": payload["success"],
            "artifact_names": [
                finding["artifact_name"] for finding in payload["findings"]
            ],
            "errors": payload["errors"],
        }
        for payload in (report.to_dict() for report in reports.values())
    ] == [
        {"success": True, "artifact_names": ["beta"], "errors": []},
        {"success": True, "artifact_names": ["alpha"], "errors": []},
    ]


def test_batch_missing_coverage_dependency_fails_closed_for_every_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from maid_runner.core import artifact_coverage

    manifests = [load_manifest(path) for path in _write_two_manifest_project(tmp_path)]
    coverage_calls = _record_coverage_subprocesses(monkeypatch)
    monkeypatch.setattr(artifact_coverage, "coverage_is_available", lambda: False)

    reports = artifact_coverage.run_artifact_coverage_batch(manifests, tmp_path)

    assert coverage_calls == []
    assert [[error.code for error in report.errors] for report in reports.values()] == [
        [ErrorCode.VALIDATOR_NOT_AVAILABLE],
        [ErrorCode.VALIDATOR_NOT_AVAILABLE],
    ]


def test_batch_combines_evidence_from_multiple_commands_per_manifest(
    tmp_path: Path,
) -> None:
    from maid_runner.core.artifact_coverage import run_artifact_coverage_batch

    _write_two_manifest_project(tmp_path)
    manifest = load_manifest(_write_combined_manifest(tmp_path))
    executor = _SequenceExecutor(
        [
            _runtime_record(tmp_path, executed={"alpha"}),
            _runtime_record(tmp_path, executed={"beta"}),
        ]
    )

    reports = run_artifact_coverage_batch(
        [manifest],
        tmp_path,
        executor=executor,
    )

    assert len(executor.calls) == 2
    report = reports[manifest.source_path]
    assert report.success is True
    assert [
        (finding.artifact_name, finding.executed) for finding in report.findings
    ] == [("alpha", True), ("beta", True)]


def test_batch_matches_final_command_call_trace_for_one_line_artifact(
    tmp_path: Path,
) -> None:
    from maid_runner.core.artifact_coverage import (
        run_artifact_coverage,
        run_artifact_coverage_batch,
    )

    _write_two_manifest_project(tmp_path)
    (tmp_path / "src" / "alpha.py").write_text('def alpha() -> str: return "alpha"\n')
    manifest = load_manifest(_write_combined_manifest(tmp_path))
    records = [
        _runtime_record(
            tmp_path,
            executed={"alpha"},
            one_line_alpha=True,
        ),
        _runtime_record(tmp_path, executed={"beta"}, one_line_alpha=True),
        _runtime_record(
            tmp_path,
            executed={"alpha"},
            one_line_alpha=True,
        ),
        _runtime_record(tmp_path, executed={"beta"}, one_line_alpha=True),
    ]
    executor = _SequenceExecutor(records)

    independent = run_artifact_coverage(
        manifest,
        tmp_path,
        executor=executor,
    ).to_dict()
    batched = run_artifact_coverage_batch(
        [manifest],
        tmp_path,
        executor=executor,
    )

    assert batched[manifest.source_path].to_dict() == independent


def test_policy_matrix_uses_owned_fake_without_spawning_pytest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from maid_runner.core._runtime_command_executor import (
        RuntimeCommandRecord,
        RuntimeFileExecution,
    )
    from maid_runner.core.artifact_coverage import run_artifact_coverage_batch

    manifest_paths = _write_two_manifest_project(tmp_path)
    manifests = [load_manifest(path) for path in manifest_paths]
    execution_data = {
        str((tmp_path / "src/alpha.py").resolve()): RuntimeFileExecution(
            executed_lines=frozenset({2}),
            called_qualnames=frozenset({"alpha"}),
        ),
        str((tmp_path / "src/beta.py").resolve()): RuntimeFileExecution(
            executed_lines=frozenset({2}),
            called_qualnames=frozenset({"beta"}),
        ),
    }
    executor = _RecordingExecutor(
        RuntimeCommandRecord(
            command=("-q", "tests/test_targets.py"),
            returncode=0,
            stdout="",
            stderr="",
            execution_data=execution_data,
            report_errors=(),
        )
    )

    def unexpected_subprocess(*args, **kwargs):
        raise AssertionError("owned fake must not spawn pytest")

    monkeypatch.setattr(subprocess, "run", unexpected_subprocess)

    reports = run_artifact_coverage_batch(
        manifests,
        tmp_path,
        executor=executor,
    )

    assert all(report.success for report in reports.values())
    assert len(executor.calls) == 1


def test_real_and_fake_executor_reports_are_equivalent(tmp_path: Path) -> None:
    from maid_runner.core._runtime_command_executor import (
        SubprocessRuntimeCommandExecutor,
    )
    from maid_runner.core.artifact_coverage import run_artifact_coverage_batch

    manifest_paths = _write_two_manifest_project(tmp_path)
    alpha_path = (tmp_path / "src/alpha.py").resolve()
    alpha_path.write_text('def alpha() -> str: return "alpha"\n')
    manifests = [load_manifest(path) for path in manifest_paths]
    target_files = {
        str(alpha_path),
        str((tmp_path / "src/beta.py").resolve()),
    }
    record = SubprocessRuntimeCommandExecutor().execute(
        ("-q", "tests/test_targets.py"),
        target_files,
        tmp_path,
        900.0,
    )

    alpha_execution = record.execution_data[str(alpha_path)]
    assert alpha_execution.executed_lines
    assert "alpha" in alpha_execution.called_qualnames
    assert all(Path(path).is_absolute() for path in record.execution_data)
    assert (
        sum(Path(path).resolve() == alpha_path for path in record.execution_data) == 1
    )

    real_reports = run_artifact_coverage_batch(manifests, tmp_path)
    replayed_reports = run_artifact_coverage_batch(
        manifests,
        tmp_path,
        executor=_RecordingExecutor(record),
    )

    assert {path: report.to_dict() for path, report in replayed_reports.items()} == {
        path: report.to_dict() for path, report in real_reports.items()
    }


def test_batch_executor_call_count_matches_unique_command_count(
    tmp_path: Path,
) -> None:
    from maid_runner.core._runtime_command_executor import (
        RuntimeCommandRecord,
    )
    from maid_runner.core.artifact_coverage import run_artifact_coverage_batch

    manifests = [load_manifest(path) for path in _write_two_manifest_project(tmp_path)]
    executor = _RecordingExecutor(
        RuntimeCommandRecord(
            command=("-q", "tests/test_targets.py"),
            returncode=0,
            stdout="",
            stderr="",
            execution_data={},
            report_errors=(),
        )
    )

    reports = run_artifact_coverage_batch(
        manifests,
        tmp_path,
        executor=executor,
    )

    assert len(executor.calls) == 1
    assert all(
        [error.code for error in report.errors]
        == [ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS]
        for report in reports.values()
    )


def _runtime_record(
    root: Path,
    *,
    executed: set[str],
    one_line_alpha: bool = False,
):
    from maid_runner.core._runtime_command_executor import (
        RuntimeCommandRecord,
        RuntimeFileExecution,
    )

    alpha_lines = {1} if one_line_alpha else ({2} if "alpha" in executed else set())
    beta_lines = {2} if "beta" in executed else set()
    return RuntimeCommandRecord(
        command=("-q", "tests/test_targets.py"),
        returncode=0,
        stdout="",
        stderr="",
        execution_data={
            str((root / "src/alpha.py").resolve()): RuntimeFileExecution(
                executed_lines=frozenset(alpha_lines),
                called_qualnames=(
                    frozenset({"alpha"}) if "alpha" in executed else frozenset()
                ),
            ),
            str((root / "src/beta.py").resolve()): RuntimeFileExecution(
                executed_lines=frozenset(beta_lines),
                called_qualnames=(
                    frozenset({"beta"}) if "beta" in executed else frozenset()
                ),
            ),
        },
        report_errors=(),
    )


class _RecordingExecutor:
    def __init__(self, record: object) -> None:
        self.record = record
        self.calls: list[tuple[tuple[str, ...], set[str], Path, float]] = []

    def execute(
        self,
        command: tuple[str, ...],
        target_files: set[str],
        project_root: Path,
        timeout_seconds: float,
    ) -> object:
        self.calls.append((command, set(target_files), project_root, timeout_seconds))
        return self.record


class _SequenceExecutor(_RecordingExecutor):
    def __init__(self, records: list[object]) -> None:
        super().__init__(records[0])
        self._records = iter(records)

    def execute(
        self,
        command: tuple[str, ...],
        target_files: set[str],
        project_root: Path,
        timeout_seconds: float,
    ) -> object:
        self.calls.append((command, set(target_files), project_root, timeout_seconds))
        return next(self._records)


def _record_coverage_subprocesses(monkeypatch) -> list[tuple[str, ...]]:
    real_run = subprocess.run
    calls: list[tuple[str, ...]] = []

    def recording_run(command, *args, **kwargs):
        normalized = tuple(str(part) for part in command)
        if "coverage" in normalized and "run" in normalized:
            calls.append(normalized)
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording_run)
    return calls


def _write_two_manifest_project(
    root: Path,
    *,
    first_command: str = "python -m pytest -q tests/test_targets.py",
    second_command: str = "python -m pytest -q tests/test_targets.py",
    failing_test: bool = False,
) -> tuple[Path, Path]:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src" / "__init__.py").write_text("")
    (root / "src" / "alpha.py").write_text('def alpha() -> str:\n    return "alpha"\n')
    (root / "src" / "beta.py").write_text('def beta() -> str:\n    return "beta"\n')
    beta_expectation = "wrong" if failing_test else "beta"
    (root / "tests" / "test_targets.py").write_text(
        "from src.alpha import alpha\n"
        "from src.beta import beta\n\n"
        "def test_alpha():\n"
        '    assert alpha() == "alpha"\n\n'
        "def test_beta():\n"
        f'    assert beta() == "{beta_expectation}"\n'
    )
    first = _write_manifest(root, "alpha", "alpha", first_command)
    second = _write_manifest(root, "beta", "beta", second_command)
    return first, second


def _write_manifest(root: Path, slug: str, function_name: str, command: str) -> Path:
    path = root / "manifests" / f"{slug}.manifest.yaml"
    path.write_text(
        f"""schema: "2"
goal: "Cover {function_name}"
type: feature
created: "2026-08-08T00:00:00Z"
files:
  edit:
    - path: src/{function_name}.py
      artifacts:
        - kind: function
          name: {function_name}
          args: []
          returns: str
  read:
    - tests/test_targets.py
validate:
  - {command}
"""
    )
    return path


def _write_combined_manifest(root: Path) -> Path:
    path = root / "manifests" / "combined.manifest.yaml"
    path.write_text(
        """schema: "2"
goal: "Cover both targets through separate commands"
type: feature
created: "2026-08-08T00:00:00Z"
files:
  edit:
    - path: src/alpha.py
      artifacts:
        - kind: function
          name: alpha
          args: []
          returns: str
    - path: src/beta.py
      artifacts:
        - kind: function
          name: beta
          args: []
          returns: str
  read:
    - tests/test_targets.py
validate:
  - python -m pytest -q tests/test_targets.py -k alpha
  - python -m pytest -q tests/test_targets.py -k beta
"""
    )
    return path
