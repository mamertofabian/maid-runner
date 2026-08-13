"""Focused knockout uses a small prefix of proven detecting nodeids.

Contract: manifests/drafts/121-37-bound-focused-knockout-nodeids.manifest.yaml
"""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import TestRunResult
from maid_runner.core.runtime_evidence import collect_runtime_evidence
from maid_runner.core.types import TestStream

ORIGINAL = "def target() -> str:\n    return 'ok'\n"
MUTANT_MARKER = 'raise NotImplementedError("maid-knockout")'


def test_focused_knockout_uses_at_most_eight_detecting_nodeids(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _write_project(tmp_path)
    evidence = collect_runtime_evidence((manifest,), tmp_path).evidence
    assert len(evidence.commands[0].selected_nodeids) > 8
    executor = _RecordingExecutor((0, 1, 0))

    report = run_knockout_batch(
        (manifest,),
        tmp_path,
        evidence=evidence,
        allow_dirty=True,
        executor=executor,
    )[manifest.source_path]

    proof = report.results[0].proof
    assert proof is not None
    assert proof.used_exact_fallback is False
    assert len(proof.detecting_nodeids) == 8
    allowed = {f"tests/test_target.py::test_{index:02d}" for index in range(10)}
    assert set(proof.detecting_nodeids) <= allowed
    focused = executor.calls[0][0]
    assert sum(1 for part in focused if part.startswith("tests/test_target.py::")) == 8


def _write_project(root: Path):
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src/target.py").write_text(ORIGINAL)
    tests = "from src.target import target\n\n" + "\n".join(
        "def test_{index:02d}():\n    assert target() == 'ok'\n".format(index=index)
        for index in range(10)
    )
    (root / "tests/test_target.py").write_text(tests)
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
  - python -m pytest tests/ -q
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
