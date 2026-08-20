"""Focused knockout keeps detecting nodeids that do not consume unproven fixtures.

Contract: manifests/drafts/121-36-focus-knockout-on-proven-detecting-nodeids.manifest.yaml
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
OTHER_UNPROVEN = (
    "fixture:tests/test_other.py:autouse:function:tests/test_other.py::test_other"
)
TARGET_UNPROVEN = (
    "fixture:tests/test_target.py:autouse:function:tests/test_target.py::test_target"
)


def test_unproven_subset_of_detecting_nodeids_still_uses_focused_knockout(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _write_project(tmp_path)
    evidence = collect_runtime_evidence((manifest,), tmp_path).evidence
    evidence = _with_unproven(
        evidence, OTHER_UNPROVEN, "tests/test_other.py::test_other"
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


def test_all_detecting_nodeids_unproven_still_forces_exact_fallback(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _write_project(tmp_path)
    evidence = collect_runtime_evidence((manifest,), tmp_path).evidence
    evidence = _with_unproven(
        evidence,
        TARGET_UNPROVEN,
        "tests/test_target.py::test_target",
        OTHER_UNPROVEN,
        "tests/test_other.py::test_other",
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


def _with_unproven(evidence, *pairs: str):
    items = tuple(zip(pairs[::2], pairs[1::2], strict=True))
    unproven = tuple(context_id for context_id, _nodeid in items)
    command = evidence.commands[0]
    completeness = RuntimeEvidenceCompleteness(
        complete=False,
        unresolved_context_ids=("collection:global",),
        unproven_fixture_lifecycles=unproven,
    )
    contexts = list(command.contexts)
    template = next(context for context in contexts if context.kind == "node")
    for context_id, nodeid in items:
        if any(context.context_id == context_id for context in contexts):
            continue
        contexts.append(
            replace(
                template,
                context_id=context_id,
                kind="fixture",
                consuming_nodeids=(nodeid,),
                lifecycle_equivalent=False,
                execution_data={},
            )
        )
    return replace(
        evidence,
        completeness=completeness,
        commands=(
            replace(command, completeness=completeness, contexts=tuple(contexts)),
        ),
    )


def _write_project(root: Path):
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src/target.py").write_text(ORIGINAL)
    test_body = (
        "from src.target import target\n\ndef {name}():\n    assert target() == 'ok'\n"
    )
    (root / "tests/test_target.py").write_text(test_body.format(name="test_target"))
    (root / "tests/test_other.py").write_text(test_body.format(name="test_other"))
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
