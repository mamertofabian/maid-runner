"""Behavioral contract for invocation-scoped knockout cache-key preparation."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import subprocess

import pytest

from maid_runner.core import knockout
from maid_runner.core._knockout_snapshot import (
    WorkerRetainedProjectSnapshotBackend,
)
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import TestRunResult
from maid_runner.core.types import TestStream

MUTANT_MARKER = 'raise NotImplementedError("maid-knockout")'


def test_cached_batch_computes_repository_identity_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _write_project(tmp_path)
    executor = _RecordingExecutor()
    identity_calls = _record_cache_identity_calls(monkeypatch)

    reports = knockout.run_knockout_batch((manifest,), tmp_path, executor=executor)

    report = reports[manifest.source_path]
    assert report.success is True
    assert [result.artifact_name for result in report.results] == [
        "alpha",
        "beta",
        "gamma",
    ]
    assert all(result.detected for result in report.results)
    assert identity_calls == {"content": [tmp_path], "environment": [tmp_path]}


def test_cache_context_is_fresh_per_invocation_and_invalidates_content_changes(
    tmp_path: Path,
) -> None:
    manifest = _write_project(tmp_path)
    executor = _RecordingExecutor()

    first = knockout.run_knockout_batch((manifest,), tmp_path, executor=executor)
    second = knockout.run_knockout_batch((manifest,), tmp_path, executor=executor)
    (tmp_path / "tests" / "test_target.py").write_text(
        (tmp_path / "tests" / "test_target.py").read_text(encoding="utf-8")
        + "\n# changed cache input\n",
        encoding="utf-8",
    )
    third = knockout.run_knockout_batch((manifest,), tmp_path, executor=executor)

    assert all(not result.cache_hit for result in first[manifest.source_path].results)
    assert all(result.cache_hit for result in second[manifest.source_path].results)
    assert all(not result.cache_hit for result in third[manifest.source_path].results)
    assert len(executor.calls) == 14


def test_no_cache_skips_repository_cache_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _write_project(tmp_path)
    executor = _RecordingExecutor()
    identity_calls = _record_cache_identity_calls(monkeypatch)

    reports = knockout.run_knockout_batch(
        (manifest,), tmp_path, executor=executor, no_cache=True
    )

    assert reports[manifest.source_path].success is True
    assert identity_calls == {"content": [], "environment": []}


def test_empty_batch_skips_repository_cache_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _write_project(tmp_path)
    identity_calls = _record_cache_identity_calls(monkeypatch)

    reports = knockout.run_knockout_batch((manifest,), tmp_path, limit=0)

    assert reports[manifest.source_path].success is True
    assert reports[manifest.source_path].results == ()
    assert identity_calls == {"content": [], "environment": []}


def test_checkpoint_rejects_inputs_that_drift_after_context_capture(
    tmp_path: Path,
) -> None:
    manifest = _write_project(tmp_path, names=("alpha",))
    executor = _RecordingExecutor()
    test_path = tmp_path / "tests" / "test_target.py"
    original_test = test_path.read_text(encoding="utf-8")
    backend = _DriftingSnapshotBackend(test_path, original_test)

    with pytest.raises(RuntimeError, match="source project inputs"):
        knockout.run_knockout_batch(
            (manifest,),
            tmp_path,
            executor=executor,
            snapshot_backend=backend,
        )
    restored = knockout.run_knockout_batch(
        (manifest,),
        tmp_path,
        executor=executor,
    )[manifest.source_path]

    assert test_path.read_text(encoding="utf-8") == original_test
    assert restored.success is True
    assert restored.results[0].detected is True
    assert restored.results[0].cache_hit is False


def test_git_project_without_cache_ignore_reuses_untracked_checkpoint(
    tmp_path: Path,
) -> None:
    manifest = _write_project(tmp_path, names=("alpha",))
    _git(tmp_path, "init")
    _git(tmp_path, "add", ".")
    _git(
        tmp_path,
        "-c",
        "user.name=MAID Test",
        "-c",
        "user.email=maid-test@example.invalid",
        "commit",
        "-m",
        "fixture",
    )
    executor = _RecordingExecutor()

    first = knockout.run_knockout_batch((manifest,), tmp_path, executor=executor)
    second = knockout.run_knockout_batch((manifest,), tmp_path, executor=executor)

    assert first[manifest.source_path].success is True
    assert second[manifest.source_path].success is True
    assert second[manifest.source_path].results[0].cache_hit is True
    assert len(executor.calls) == 3
    assert "?? .maid/cache/knockout-evidence-v1/" in _git(
        tmp_path,
        "status",
        "--short",
        "--untracked-files=all",
    )


def _record_cache_identity_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, list[Path]]:
    original_content_digest = knockout._content_digest
    original_environment_identity = knockout._environment_identity
    calls: dict[str, list[Path]] = {"content": [], "environment": []}

    def recording_digest(root: Path) -> str:
        calls["content"].append(root)
        return original_content_digest(root)

    def recording_environment(command, root: Path):
        calls["environment"].append(root)
        return original_environment_identity(command, root)

    monkeypatch.setattr(knockout, "_content_digest", recording_digest)
    monkeypatch.setattr(knockout, "_environment_identity", recording_environment)
    return calls


def _write_project(
    root: Path,
    *,
    names: tuple[str, ...] = ("alpha", "beta", "gamma"),
):
    # Cache-context behavior uses an injected executor and needs no packages.
    (root / ".venv").mkdir()
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src" / "target.py").write_text(
        "\n\n".join(f"def {name}() -> str:\n    return '{name}'" for name in names)
        + "\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_target.py").write_text(
        "from src import target\n\n"
        + "\n".join(
            f"def test_{name}():\n    assert target.{name}() == '{name}'\n"
            for name in names
        ),
        encoding="utf-8",
    )
    manifest_path = root / "manifests" / "target.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Exercise cache context"
type: fix
created: "2026-08-17T13:20:00Z"
files:
  edit:
    - path: src/target.py
      artifacts:
"""
        + "".join(
            "        - kind: function\n"
            f"          name: {name}\n"
            "          args: []\n"
            "          returns: str\n"
            for name in names
        )
        + """  read:
    - tests/test_target.py
validate:
  - python -m pytest -q tests/test_target.py
""",
        encoding="utf-8",
    )
    return load_manifest(manifest_path)


class _RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], str, bool]] = []

    def execute(self, command, project_root, manifest_slug):
        command = tuple(command)
        root = Path(project_root)
        mutated = MUTANT_MARKER in (root / "src/target.py").read_text(encoding="utf-8")
        drifted = "# drift changes detection" in (
            root / "tests" / "test_target.py"
        ).read_text(encoding="utf-8")
        self.calls.append((command, manifest_slug, mutated))
        return TestRunResult(
            manifest_slug=manifest_slug,
            command=command,
            exit_code=1 if mutated and not drifted else 0,
            stdout="",
            stderr="",
            duration_ms=1.0,
            stream=TestStream.IMPLEMENTATION,
        )


class _DriftingSnapshotBackend:
    def __init__(self, test_path: Path, original_test: str) -> None:
        self._delegate = WorkerRetainedProjectSnapshotBackend()
        self._test_path = test_path
        self._original_test = original_test

    def retain(self):
        return self._delegate.retain()

    @contextmanager
    def create(self, project_root, required_paths, worker_id):
        if worker_id != "maid-cache-context":
            self._test_path.write_text(
                self._original_test + "\n# drift changes detection\n",
                encoding="utf-8",
            )
        try:
            with self._delegate.create(
                project_root, required_paths, worker_id
            ) as snapshot:
                yield snapshot
        finally:
            self._test_path.write_text(self._original_test, encoding="utf-8")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
