"""Persistent per-spec knockout evidence cache.

Contract: manifests/drafts/121-22-persist-knockout-evidence-cache.manifest.yaml
"""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import TestRunResult
from maid_runner.core.types import TestStream

ORIGINAL = "def target() -> str:\n    return 'ok'\n"
MUTANT_MARKER = 'raise NotImplementedError("maid-knockout")'


def test_repeat_knockout_spec_reuses_cached_result(tmp_path: Path) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _write_project(tmp_path)
    executor = _RecordingExecutor((0, 1, 0))

    first = run_knockout_batch((manifest,), tmp_path, executor=executor)
    second = run_knockout_batch((manifest,), tmp_path, executor=executor)

    assert first[manifest.source_path].success is True
    report = second[manifest.source_path]
    assert report.success is True
    assert report.results[0].cache_hit is True
    assert len(executor.calls) == 3


def test_source_digest_change_misses_knockout_cache(tmp_path: Path) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _write_project(tmp_path)
    executor = _RecordingExecutor((0, 1, 0, 0, 1, 0))
    run_knockout_batch((manifest,), tmp_path, executor=executor)
    (tmp_path / "src" / "target.py").write_text(
        "def target() -> str:\n    return 'changed'\n"
    )

    report = run_knockout_batch((manifest,), tmp_path, executor=executor)[
        manifest.source_path
    ]

    assert report.results[0].cache_hit is False
    assert len(executor.calls) == 6


def test_mutated_body_digest_change_misses_knockout_cache(
    tmp_path: Path, monkeypatch
) -> None:
    from maid_runner.core import knockout

    manifest = _write_project(tmp_path)
    executor = _RecordingExecutor((0, 1, 0, 0, 1, 0))
    knockout.run_knockout_batch((manifest,), tmp_path, executor=executor)

    original = knockout.rewrite_artifact_body

    def mutated_rewrite(source, artifact_name, artifact_kind, parent_class=None):
        return original(source, artifact_name, artifact_kind, parent_class).replace(
            MUTANT_MARKER, 'raise NotImplementedError("maid-knockout-v2")'
        )

    monkeypatch.setattr(knockout, "rewrite_artifact_body", mutated_rewrite)
    report = knockout.run_knockout_batch((manifest,), tmp_path, executor=executor)[
        manifest.source_path
    ]

    assert report.results[0].cache_hit is False
    assert len(executor.calls) == 6


def test_no_cache_bypasses_knockout_store(tmp_path: Path) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _write_project(tmp_path)
    executor = _RecordingExecutor((0, 1, 0, 0, 1, 0))
    run_knockout_batch((manifest,), tmp_path, executor=executor)

    report = run_knockout_batch(
        (manifest,), tmp_path, executor=executor, no_cache=True
    )[manifest.source_path]

    assert report.results[0].cache_hit is False
    assert len(executor.calls) == 6


def test_red_knockout_results_are_cached(tmp_path: Path) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _write_project(tmp_path)
    executor = _RecordingExecutor((0, 0, 0))

    first = run_knockout_batch((manifest,), tmp_path, executor=executor)
    second = run_knockout_batch((manifest,), tmp_path, executor=executor)
    report = second[manifest.source_path]

    assert first[manifest.source_path].results[0].detected is False
    assert report.results[0].detected is False
    assert report.results[0].cache_hit is True
    assert len(executor.calls) == 2


def _write_project(root: Path):
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src" / "target.py").write_text(ORIGINAL)
    (root / "tests" / "test_target.py").write_text(
        "from src.target import target\n\n"
        "def test_target():\n"
        "    assert target() == 'ok'\n"
    )
    path = root / "manifests" / "target.manifest.yaml"
    path.write_text(
        """schema: "2"
goal: "Cache knockout specs"
type: feature
created: "2026-08-13T00:00:00Z"
files:
  edit:
    - path: src/target.py
      artifacts:
        - kind: function
          name: target
          args: []
          returns: str
  read:
    - tests/test_target.py
validate:
  - python -m pytest -q tests/test_target.py
"""
    )
    return load_manifest(path)


class _RecordingExecutor:
    def __init__(self, decisions):
        self.decisions = iter(decisions)
        self.calls: list[tuple[tuple[str, ...], str, bool]] = []

    def execute(self, command, project_root, manifest_slug):
        command = tuple(command)
        mutated = MUTANT_MARKER in (Path(project_root) / "src/target.py").read_text()
        self.calls.append((command, manifest_slug, mutated))
        return TestRunResult(
            manifest_slug=manifest_slug,
            command=command,
            exit_code=next(self.decisions),
            stdout="",
            stderr="",
            duration_ms=1.0,
            stream=TestStream.IMPLEMENTATION,
        )
