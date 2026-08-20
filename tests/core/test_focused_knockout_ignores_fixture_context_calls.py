"""Fixture-context calls must not discard knockout detecting nodeids.

Contract: manifests/drafts/121-38-keep-detecting-nodeids-despite-fixture-calls.manifest.yaml
"""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import TestRunResult
from maid_runner.core.runtime_evidence import collect_runtime_evidence
from maid_runner.core.types import TestStream

ORIGINAL = "def target() -> str:\n    return 'ok'\n"
MUTANT_MARKER = 'raise NotImplementedError("maid-knockout")'


def test_fixture_context_call_still_uses_focused_knockout(tmp_path: Path) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _write_project(tmp_path, node_calls=True)
    evidence = collect_runtime_evidence((manifest,), tmp_path).evidence
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


def test_fixture_only_call_still_forces_exact_fallback(tmp_path: Path) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _write_project(tmp_path, node_calls=False)
    evidence = collect_runtime_evidence((manifest,), tmp_path).evidence
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


def _write_project(root: Path, *, node_calls: bool):
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src/target.py").write_text(ORIGINAL)
    assertion = "assert target() == 'ok'" if node_calls else "assert primed == 'ok'"
    (root / "tests/test_target.py").write_text(
        "import pytest\n"
        "from src.target import target\n\n"
        "@pytest.fixture\n"
        "def primed():\n"
        "    return target()\n\n"
        "def test_target(primed):\n"
        f"    {assertion}\n"
    )
    (root / "pytest.ini").write_text("[pytest]\npythonpath = .\n")
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
