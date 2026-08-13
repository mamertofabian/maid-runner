"""Behavioral contract: coverage snapshots reuse the shared venv.

Contract: manifests/drafts/121-27-share-coverage-lane-dependency-environments.manifest.yaml

Coverage lanes copy source and Git metadata but must not clone .venv or
node_modules. Knockout keeps a full dependency copy. A write into the shared
environment fails the snapshot closed so the parallel batch cannot treat a
mutated interpreter as success.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_shared_environment_snapshot_reuses_source_venv_without_copying(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import (
        SharedEnvironmentProjectSnapshotBackend,
    )

    root = _project_with_dependencies(tmp_path)
    venv_before = _file_set(root / ".venv")
    node_before = _file_set(root / "node_modules")

    with SharedEnvironmentProjectSnapshotBackend().create(
        root, ("src/target.py",), "shared-env"
    ) as snapshot:
        assert not (snapshot.root / ".venv").exists()
        assert not (snapshot.root / "node_modules").exists()
        assert (snapshot.root / "src/target.py").is_file()
        assert (
            Path(snapshot.environment_overrides["VIRTUAL_ENV"]).resolve()
            == (root / ".venv").resolve()
        )
        assert (
            Path(snapshot.environment_overrides["UV_PROJECT_ENVIRONMENT"]).resolve()
            == (root / ".venv").resolve()
        )
        assert str((root / ".venv/bin").resolve()) in snapshot.environment_overrides[
            "PATH"
        ].split(":")
        assert (
            Path(snapshot.environment_overrides["NODE_PATH"]).resolve()
            == (root / "node_modules").resolve()
        )
        assert str(snapshot.root) in snapshot.environment_overrides["PYTHONPATH"]

    assert _file_set(root / ".venv") == venv_before
    assert _file_set(root / "node_modules") == node_before


def test_shared_environment_write_to_source_venv_fails_closed(tmp_path: Path) -> None:
    from maid_runner.core._knockout_snapshot import (
        SharedEnvironmentProjectSnapshotBackend,
    )

    root = _project_with_dependencies(tmp_path)
    marker = root / ".venv/shared-write"

    with pytest.raises(RuntimeError, match="source dependency"):
        with SharedEnvironmentProjectSnapshotBackend().create(
            root, ("src/target.py",), "shared-write"
        ) as snapshot:
            assert snapshot.root.exists()
            marker.write_text("mutated-shared-venv\n")

    assert marker.exists()
    marker.unlink()


def test_knockout_backend_still_copies_dependency_environments(tmp_path: Path) -> None:
    from maid_runner.core._knockout_snapshot import MaterializedProjectSnapshotBackend

    root = _project_with_dependencies(tmp_path)

    with MaterializedProjectSnapshotBackend().create(
        root, ("src/target.py",), "knockout-copy"
    ) as snapshot:
        assert (snapshot.root / ".venv").is_dir()
        assert (snapshot.root / "node_modules").is_dir()
        assert (snapshot.root / ".venv").resolve() != (root / ".venv").resolve()
        (snapshot.root / ".venv/local-write").write_text("snapshot-only\n")

    assert not (root / ".venv/local-write").exists()


def test_coverage_batch_defaults_to_shared_environment_backend(tmp_path: Path) -> None:
    from maid_runner.core._artifact_coverage_fallback_worker import (
        ArtifactCoverageFallbackRun,
        ArtifactCoverageFallbackWorkerResult,
    )
    from maid_runner.core._knockout_snapshot import (
        SharedEnvironmentProjectSnapshotBackend,
    )
    from maid_runner.core._runtime_command_executor import (
        RuntimeCommandRecord,
        RuntimeFileExecution,
    )
    from maid_runner.core.artifact_coverage import run_artifact_coverage_batch
    from maid_runner.core.manifest import load_manifest

    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src/alpha.py").write_text("def alpha():\n    return 1\n")
    (root / "tests").mkdir()
    (root / "tests/test_alpha.py").write_text("from src.alpha import alpha\n")
    (root / "manifests").mkdir()
    manifest_path = root / "manifests/alpha.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Shared environment coverage fixture"
type: refactor
created: "2026-08-13T00:00:00Z"
files:
  edit:
    - path: src/alpha.py
      artifacts:
        - kind: function
          name: alpha
          args: []
          returns: int
validate:
  - python -m pytest -q tests/test_alpha.py
"""
    )
    (root / ".maidrc.yaml").write_text(
        "artifact_coverage:\n  fallback_jobs: 2\ntest_execution:\n  max_processes: 4\n"
    )
    record = RuntimeCommandRecord(
        command=("-q", "tests/test_alpha.py"),
        returncode=0,
        stdout="",
        stderr="",
        execution_data={
            str((root / "src/alpha.py").resolve()): RuntimeFileExecution(
                executed_lines=frozenset({2}),
                called_qualnames=frozenset({"alpha"}),
            )
        },
        report_errors=(),
    )
    captured: dict[str, object] = {}

    def _runner(
        identities,
        project_root,
        target_files,
        snapshot_backend,
        executor,
        jobs,
        max_processes,
    ):
        captured["backend"] = snapshot_backend
        results = tuple(
            ArtifactCoverageFallbackWorkerResult(
                identity=identity,
                command_run=record,
                material_project_writes=(),
                process_cost=1,
                errors=(),
            )
            for identity in identities
        )
        return ArtifactCoverageFallbackRun(
            results=results, serial_fallback_identities=()
        )

    reports = run_artifact_coverage_batch(
        [load_manifest(manifest_path)],
        root,
        executor=_StaticExecutor(record),
        isolated_runner=_runner,
    )

    assert reports
    assert isinstance(captured["backend"], SharedEnvironmentProjectSnapshotBackend)


class _StaticExecutor:
    def __init__(self, record: object) -> None:
        self.record = record

    def execute(self, command, target_files, project_root, timeout_seconds):
        return self.record


def _project_with_dependencies(base: Path) -> Path:
    root = base / "project"
    (root / "src").mkdir(parents=True)
    (root / "src/target.py").write_text("def target():\n    return 'original'\n")
    (root / ".venv/bin").mkdir(parents=True)
    (root / ".venv/pyvenv.cfg").write_text(
        "home = /usr\ninclude-system-site-packages = false\n"
    )
    (root / ".venv/bin/python").write_text("#!/bin/sh\n")
    (root / "node_modules/pkg").mkdir(parents=True)
    (root / "node_modules/pkg/index.js").write_text("source\n")
    return root


def _file_set(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
