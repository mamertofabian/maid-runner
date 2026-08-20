"""Focused knockout stays available when only collection:global is unresolved.

Contract: manifests/drafts/121-31-focused-knockout-with-collection-incompleteness.manifest.yaml
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import TestRunResult
from maid_runner.core.runtime_evidence import (
    RuntimeEvidenceCompleteness,
    collect_runtime_evidence,
)
from maid_runner.core.types import TestStream

ORIGINAL = "def target() -> str:\n    return 'ok'\n"
MUTANT_MARKER = 'raise NotImplementedError("maid-knockout")'


def test_collection_global_bundle_incompleteness_still_uses_focused_knockout(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _write_project(tmp_path)
    evidence = collect_runtime_evidence((manifest,), tmp_path).evidence
    evidence = replace(
        evidence,
        completeness=RuntimeEvidenceCompleteness(
            complete=False,
            unresolved_context_ids=("collection:global",),
        ),
        commands=(
            replace(
                evidence.commands[0],
                completeness=RuntimeEvidenceCompleteness(
                    complete=False,
                    unresolved_context_ids=("collection:global",),
                ),
            ),
        ),
    )
    executor = _RecordingExecutor((0, 1, 0))

    report = run_knockout_batch(
        (manifest,),
        tmp_path,
        evidence=evidence,
        allow_dirty=True,
        executor=executor,
    )[manifest.source_path]

    assert report.results[0].proof is not None
    assert report.results[0].proof.used_exact_fallback is False
    assert report.results[0].proof.detecting_nodeids == (
        "tests/test_target.py::test_target",
    )


def test_unproven_lifecycle_still_forces_exact_knockout_fallback(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _write_project(tmp_path)
    evidence = collect_runtime_evidence((manifest,), tmp_path).evidence
    evidence = replace(
        evidence,
        completeness=RuntimeEvidenceCompleteness(
            complete=False,
            unproven_fixture_lifecycles=("session:autouse",),
        ),
        commands=(
            replace(
                evidence.commands[0],
                completeness=RuntimeEvidenceCompleteness(
                    complete=False,
                    unproven_fixture_lifecycles=("session:autouse",),
                ),
            ),
        ),
    )
    original = tuple(manifest.validate_commands[0])
    executor = _RecordingExecutor((0, 1, 0))

    report = run_knockout_batch(
        (manifest,),
        tmp_path,
        evidence=evidence,
        allow_dirty=True,
        executor=executor,
    )[manifest.source_path]

    assert report.results[0].proof is not None
    assert report.results[0].proof.used_exact_fallback is True
    assert [call[0] for call in executor.calls].count(original) == 3


def _write_project(root: Path):
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src/target.py").write_text(ORIGINAL)
    (root / "tests/test_target.py").write_text(
        "from src.target import target\n\n"
        "def test_target():\n"
        "    assert target() == 'ok'\n"
    )
    path = root / "manifests/target.manifest.yaml"
    path.write_text(
        """schema: "2"
goal: "Constrain target"
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


class _RecordingExecutor:
    def __init__(self, decisions):
        self.decisions = iter(decisions)
        self.calls: list[tuple[tuple[str, ...], str, bool]] = []

    def execute(self, command, project_root, manifest_slug):
        command = tuple(command)
        mutated = MUTANT_MARKER in (Path(project_root) / "src/target.py").read_text()
        self.calls.append((command, manifest_slug, mutated))
        return _run_result(command, next(self.decisions))
