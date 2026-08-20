from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from maid_runner.core.manifest import load_manifest


def test_artifact_coverage_timeout_defaults_to_fifteen_minutes() -> None:
    from maid_runner.core.config import ArtifactCoverageConfig, MaidConfig

    setting = ArtifactCoverageConfig()
    config = MaidConfig()

    assert setting.timeout_seconds == 900.0
    assert config.artifact_coverage == setting


def test_artifact_coverage_timeout_loads_positive_numeric_values(
    tmp_path: Path,
) -> None:
    from maid_runner.core.config import load_config

    (tmp_path / ".maidrc.yaml").write_text(
        "artifact_coverage:\n  timeout_seconds: 1234.5\n"
    )

    config = load_config(tmp_path)

    assert config.artifact_coverage.timeout_seconds == 1234.5


@pytest.mark.parametrize("value", [True, "900", 0, -1, 10**400])
def test_artifact_coverage_timeout_rejects_invalid_values(
    tmp_path: Path,
    value: object,
) -> None:
    from maid_runner.core.config import load_config

    (tmp_path / ".maidrc.yaml").write_text(
        yaml.safe_dump({"artifact_coverage": {"timeout_seconds": value}})
    )

    with pytest.raises(
        ValueError,
        match="artifact_coverage.timeout_seconds must be a positive number",
    ):
        load_config(tmp_path)


def test_artifact_coverage_config_enforces_invariant_directly() -> None:
    from maid_runner.core.config import ArtifactCoverageConfig

    assert ArtifactCoverageConfig(timeout_seconds=3).timeout_seconds == 3.0
    for value in (True, "900", 0, -1, float("nan"), float("inf"), 10**400):
        with pytest.raises(
            ValueError,
            match="artifact_coverage.timeout_seconds must be a positive number",
        ):
            ArtifactCoverageConfig(timeout_seconds=value)  # type: ignore[arg-type]


def test_single_artifact_coverage_uses_configured_timeout(
    tmp_path: Path,
) -> None:
    from maid_runner.core.artifact_coverage import run_artifact_coverage

    manifest = load_manifest(_write_project(tmp_path))
    _write_timeout(tmp_path, 901)
    executor = _timeout_recording_executor(tmp_path)

    report = run_artifact_coverage(manifest, tmp_path, executor=executor)

    assert report.success is True
    assert executor.timeouts == [901.0]


def test_batched_artifact_coverage_uses_configured_timeout(
    tmp_path: Path,
) -> None:
    from maid_runner.core.artifact_coverage import run_artifact_coverage_batch

    manifest = load_manifest(_write_project(tmp_path))
    _write_timeout(tmp_path, 902.5)
    executor = _timeout_recording_executor(tmp_path)

    reports = run_artifact_coverage_batch(
        [manifest],
        tmp_path,
        executor=executor,
    )

    assert reports[manifest.source_path].success is True
    assert executor.timeouts == [902.5]


class _TimeoutRecordingExecutor:
    def __init__(self, record: object) -> None:
        self.record = record
        self.timeouts: list[float] = []

    def execute(
        self,
        command: tuple[str, ...],
        target_files: set[str],
        project_root: Path,
        timeout_seconds: float,
    ) -> object:
        self.timeouts.append(timeout_seconds)
        return self.record


def _timeout_recording_executor(root: Path) -> _TimeoutRecordingExecutor:
    from maid_runner.core._runtime_command_executor import (
        RuntimeCommandRecord,
        RuntimeFileExecution,
    )

    return _TimeoutRecordingExecutor(
        RuntimeCommandRecord(
            command=("tests/test_target.py", "-q"),
            returncode=0,
            stdout="",
            stderr="",
            execution_data={
                str((root / "src/target.py").resolve()): RuntimeFileExecution(
                    executed_lines=frozenset({2}),
                    called_qualnames=frozenset({"target"}),
                )
            },
            report_errors=(),
        )
    )


def _write_timeout(root: Path, value: float) -> None:
    (root / ".maidrc.yaml").write_text(
        yaml.safe_dump({"artifact_coverage": {"timeout_seconds": value}})
    )


def _write_project(root: Path) -> Path:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src/__init__.py").write_text("")
    (root / "src/target.py").write_text('def target() -> str:\n    return "executed"\n')
    (root / "tests/test_target.py").write_text(
        "from src.target import target\n\n"
        "def test_target():\n"
        '    assert target() == "executed"\n'
    )
    manifest_path = root / "manifests/target.manifest.yaml"
    manifest_path.write_text(
        """schema: '2'
goal: Exercise configured artifact coverage timeout
type: fix
created: '2026-08-10T00:00:00Z'
files:
  edit:
  - path: src/target.py
    artifacts:
    - kind: function
      name: target
      args: []
      returns: str
validate:
- python -m pytest tests/test_target.py -q
"""
    )
    return manifest_path
