"""Behavioral contract: knockout workers retain copied dependency environments.

Contract: manifests/drafts/121-39-retain-knockout-worker-dependency-environments.manifest.yaml

Sequential declarations on one worker keep the copied .venv and drop generated
snapshot files. Concurrent workers stay isolated. Knockout uses this backend by
default without binding the source interpreter.
"""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import TestRunResult
from maid_runner.core.types import TestStream


def test_retained_snapshot_reuses_copied_venv_without_leaking_generated_state(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import WorkerRetainedProjectSnapshotBackend

    root = _project_with_dependencies(tmp_path)
    backend = WorkerRetainedProjectSnapshotBackend()

    with backend.retain():
        with backend.create(root, ("src/target.py",), "first") as first:
            (first.root / "generated.txt").write_text("declaration-one\n")
            (first.root / ".venv/retained-marker").write_text("keep\n")
            first_root = first.root
            first_venv = (first.root / ".venv").resolve()

        with backend.create(root, ("src/target.py",), "second") as second:
            assert second.root == first_root
            assert (second.root / ".venv").resolve() == first_venv
            assert (second.root / ".venv/retained-marker").read_text() == "keep\n"
            assert not (second.root / "generated.txt").exists()
            assert (second.root / "src/target.py").read_text() == (
                "def target():\n    return 'original'\n"
            )


def test_retained_snapshot_is_removed_when_retain_exits(tmp_path: Path) -> None:
    from maid_runner.core._knockout_snapshot import WorkerRetainedProjectSnapshotBackend

    root = _project_with_dependencies(tmp_path)
    backend = WorkerRetainedProjectSnapshotBackend()

    with backend.retain():
        with backend.create(root, ("src/target.py",), "leased") as snapshot:
            retained_root = snapshot.root
            assert retained_root.exists()

    assert not retained_root.exists()


def test_serial_knockout_reuses_one_snapshot_root_across_identities(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifests = _two_artifact_project(tmp_path)
    executor = _RootRecordingExecutor((0, 1, 0, 0, 1, 0))

    reports = run_knockout_batch(
        manifests,
        tmp_path,
        jobs=1,
        max_processes=1,
        executor=executor,
        no_cache=True,
        allow_dirty=True,
    )

    assert all(report.success for report in reports.values())
    assert len(set(executor.roots)) == 1
    assert executor.baseline_state_missing == [True, True]
    venvs = {root / ".venv" for root in executor.roots}
    assert len(venvs) == 1
    assert next(iter(venvs)).resolve() != (tmp_path / ".venv").resolve()


def test_knockout_batch_defaults_to_retained_worker_backend(
    tmp_path: Path, monkeypatch
) -> None:
    from maid_runner.core import knockout as knockout_mod
    from maid_runner.core._knockout_snapshot import WorkerRetainedProjectSnapshotBackend
    from maid_runner.core.knockout import run_knockout_batch

    seen: list[object] = []

    class Probe(WorkerRetainedProjectSnapshotBackend):
        def __init__(self, *args, **kwargs):
            seen.append(type(self).__name__)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(knockout_mod, "WorkerRetainedProjectSnapshotBackend", Probe)
    manifests = _two_artifact_project(tmp_path)
    run_knockout_batch(
        manifests,
        tmp_path,
        jobs=1,
        max_processes=1,
        executor=_RootRecordingExecutor((0, 1, 0, 0, 1, 0)),
        no_cache=True,
        allow_dirty=True,
    )

    assert seen == ["Probe"]


def _two_artifact_project(root: Path):
    (root / "src").mkdir(exist_ok=True)
    (root / "tests").mkdir(exist_ok=True)
    (root / "manifests").mkdir(exist_ok=True)
    (root / ".venv/bin").mkdir(parents=True, exist_ok=True)
    (root / ".venv/pyvenv.cfg").write_text("home = /usr\n")
    (root / "src/target.py").write_text(
        "def alpha() -> str:\n    return 'alpha'\n\n"
        "def beta() -> str:\n    return 'beta'\n"
    )
    (root / "tests/test_target.py").write_text(
        "def test_placeholder():\n    assert True\n"
    )
    manifests = []
    for name in ("alpha", "beta"):
        path = root / f"manifests/{name}.manifest.yaml"
        path.write_text(
            f"""schema: "2"
goal: "Knockout {name}"
type: refactor
created: "2026-08-13T00:00:00Z"
files:
  edit:
    - path: src/target.py
      artifacts:
        - kind: function
          name: {name}
          args: []
          returns: str
validate:
  - python -m pytest -q tests/test_target.py
"""
        )
        manifests.append(load_manifest(path))
    return tuple(manifests)


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


def _run_result(command: tuple[str, ...], exit_code: int) -> TestRunResult:
    return TestRunResult(
        manifest_slug="target",
        command=command,
        exit_code=exit_code,
        stdout="",
        stderr="",
        duration_ms=1.0,
        stream=TestStream.IMPLEMENTATION,
    )


class _RootRecordingExecutor:
    def __init__(self, decisions):
        self.decisions = iter(decisions)
        self.roots: list[Path] = []
        self.baseline_state_missing: list[bool] = []
        self._after_mutant = False

    def execute(self, command, project_root, manifest_slug, *environment):
        root = Path(project_root)
        mutated = (
            'raise NotImplementedError("maid-knockout")'
            in (root / "src/target.py").read_text()
        )
        state = root / "declaration-state"
        if mutated:
            self._after_mutant = True
        elif self._after_mutant:
            self._after_mutant = False
        else:
            self.baseline_state_missing.append(not state.exists())
            state.write_text(manifest_slug)
        self.roots.append(root)
        return _run_result(tuple(command), next(self.decisions))
