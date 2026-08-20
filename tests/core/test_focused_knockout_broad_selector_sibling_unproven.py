"""Broad pytest selectors still focus when only sibling fixtures are unproven.

Contract: manifests/drafts/121-35-focus-knockout-despite-broad-selector-unproven.manifest.yaml
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
SIBLING_UNPROVEN = (
    "fixture:tests/test_other.py:autouse:function:tests/test_other.py::test_other"
)
DETECTING_UNPROVEN = (
    "fixture:tests/test_target.py:autouse:function:tests/test_target.py::test_target"
)


def test_broad_selector_sibling_unproven_still_uses_focused_knockout(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _write_project(tmp_path)
    evidence = collect_runtime_evidence((manifest,), tmp_path).evidence
    assert len(evidence.commands[0].selected_nodeids) > 1
    evidence = _with_command_unproven(evidence, SIBLING_UNPROVEN)
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


def test_detecting_nodeid_unproven_lifecycle_still_forces_exact_fallback(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _write_project(tmp_path)
    evidence = collect_runtime_evidence((manifest,), tmp_path).evidence
    evidence = _with_command_unproven(evidence, DETECTING_UNPROVEN)
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


def _with_command_unproven(evidence, unproven: str):
    command = evidence.commands[0]
    completeness = RuntimeEvidenceCompleteness(
        complete=False,
        unresolved_context_ids=("collection:global",),
        unproven_fixture_lifecycles=(unproven,),
    )
    contexts = command.contexts
    if any(context.context_id == unproven for context in contexts):
        updated_contexts = contexts
    else:
        template = next(context for context in contexts if context.kind == "node")
        nodeid = (
            "tests/test_target.py::test_target"
            if "test_target.py" in unproven
            else "tests/test_other.py::test_other"
        )
        updated_contexts = (
            *contexts,
            replace(
                template,
                context_id=unproven,
                kind="fixture",
                consuming_nodeids=(nodeid,),
                lifecycle_equivalent=False,
            ),
        )
    return replace(
        evidence,
        completeness=completeness,
        commands=(
            replace(
                command,
                completeness=completeness,
                contexts=updated_contexts,
            ),
        ),
    )


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
    (root / "tests/test_other.py").write_text("def test_other():\n" "    assert True\n")
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
