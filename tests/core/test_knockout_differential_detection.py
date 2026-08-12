"""Behavioral contract for mutation-caused knockout detection."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode, TestRunResult
from maid_runner.core.runtime_evidence import (
    RuntimeEvidenceBundle,
    RuntimeEvidenceCompleteness,
)
from maid_runner.core.types import TestStream


ORIGINAL = "def target() -> str:\n    return 'ok'\n"
MUTANT_MARKER = 'raise NotImplementedError("maid-knockout")'


def _write_project(
    root: Path,
    slug: str = "target",
    *,
    test_source: str | None = None,
    conftest_source: str | None = None,
):
    (root / "src").mkdir(exist_ok=True)
    (root / "tests").mkdir(exist_ok=True)
    (root / "manifests").mkdir(exist_ok=True)
    (root / "src" / "target.py").write_text(ORIGINAL)
    (root / "tests" / "test_target.py").write_text(
        test_source
        or (
            "from src.target import target\n\n"
            "def test_target():\n"
            "    assert target() == 'ok'\n"
        )
    )
    if conftest_source is not None:
        (root / "conftest.py").write_text(conftest_source)
    path = root / "manifests" / f"{slug}.manifest.yaml"
    path.write_text(
        f"""schema: "2"
goal: "Constrain {slug}"
type: feature
created: "2026-08-12T00:00:00Z"
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
  - uv run python -m pytest -q tests/test_target.py
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


def _complete(*, complete: bool = True, reason: str | None = None):
    return RuntimeEvidenceCompleteness(
        complete=complete,
        unresolved_context_ids=(() if reason is None else (reason,)),
    )


def _evidence(
    manifest,
    root: Path,
    *,
    kind: str = "node",
    complete: bool = True,
    include_context: bool = True,
) -> RuntimeEvidenceBundle:
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    bundle = collect_runtime_evidence((manifest,), root).evidence
    command_evidence = bundle.commands[0]
    contexts = command_evidence.contexts if include_context else ()
    if kind != "node":
        contexts = tuple(
            replace(context, kind=kind, lifecycle_equivalent=False)
            for context in contexts
        )
    completeness = _complete(
        complete=complete,
        reason=None if complete else "unproven-lifecycle",
    )
    projected = replace(
        command_evidence,
        contexts=contexts,
        completeness=completeness,
    )
    return replace(
        bundle,
        commands=(projected,),
        completeness=completeness,
    )


def _run(manifest, root: Path, executor, evidence=None):
    from maid_runner.core.knockout import run_knockout_batch

    reports = run_knockout_batch(
        (manifest,),
        root,
        evidence=evidence,
        allow_dirty=True,
        executor=executor,
    )
    return reports[manifest.source_path]


def test_executing_node_green_red_green_is_positive_detection_proof(tmp_path):
    from maid_runner.core.knockout import KnockoutCommandExecutor

    manifest = _write_project(tmp_path)
    executor = _RecordingExecutor((0, 1, 0))

    assert callable(KnockoutCommandExecutor().execute)

    report = _run(manifest, tmp_path, executor, _evidence(manifest, tmp_path))

    result = report.results[0]
    assert report.success is True
    assert result.detected is True
    assert result.proof is not None
    assert result.proof.baseline_exit_code == 0
    assert result.proof.mutant_exit_code == 1
    assert result.proof.restored_exit_code == 0
    assert result.proof.detecting_nodeids == ("tests/test_target.py::test_target",)
    assert result.proof.used_exact_fallback is False
    assert [mutated for _command, _slug, mutated in executor.calls] == [
        False,
        True,
        False,
    ]
    assert all(
        "tests/test_target.py::test_target" in call[0] for call in executor.calls
    )
    assert (tmp_path / "src" / "target.py").read_text() == ORIGINAL


def test_focused_candidate_that_stays_green_runs_original_command(tmp_path):
    manifest = _write_project(tmp_path)
    original = tuple(manifest.validate_commands[0])
    executor = _RecordingExecutor((0, 0, 0, 1, 0))

    report = _run(manifest, tmp_path, executor, _evidence(manifest, tmp_path))

    assert report.success is True
    assert report.results[0].proof.used_exact_fallback is True
    assert [call[0] for call in executor.calls].count(original) == 3


def test_source_or_ast_inspection_detector_is_found_by_exact_fallback(tmp_path):
    manifest = _write_project(
        tmp_path,
        test_source=(
            "import ast\n"
            "from pathlib import Path\n\n"
            "def test_target():\n"
            "    tree = ast.parse(Path('src/target.py').read_text())\n"
            "    function = tree.body[0]\n"
            "    assert isinstance(function.body[0], ast.Return)\n"
        ),
    )

    report = _run(
        manifest,
        tmp_path,
        None,
        _evidence(manifest, tmp_path, include_context=False),
    )

    assert report.success is True
    assert report.results[0].proof.used_exact_fallback is True
    assert report.results[0].proof.detecting_nodeids == ()
    assert report.results[0].proof.command == tuple(manifest.validate_commands[0])


def test_fixture_or_order_dependent_candidate_is_inconclusive_and_falls_back(
    tmp_path,
):
    manifest = _write_project(tmp_path)
    executor = _RecordingExecutor((0, 1, 0))

    report = _run(
        manifest,
        tmp_path,
        executor,
        _evidence(manifest, tmp_path, complete=False),
    )

    assert report.success is True
    assert report.results[0].proof.used_exact_fallback is True
    assert len(executor.calls) == 3


def test_collection_time_detector_is_found_by_exact_fallback(tmp_path):
    manifest = _write_project(
        tmp_path,
        conftest_source=(
            "from pathlib import Path\n"
            "import pytest\n\n"
            "def pytest_collection_modifyitems():\n"
            "    if 'maid-knockout' in Path('src/target.py').read_text():\n"
            "        raise pytest.UsageError('collection observed mutant')\n"
        ),
    )

    report = _run(
        manifest,
        tmp_path,
        None,
        _evidence(manifest, tmp_path, kind="collection"),
    )

    assert report.success is True
    assert report.results[0].proof.used_exact_fallback is True
    assert report.results[0].proof.command == tuple(manifest.validate_commands[0])


def test_subprocess_observer_without_context_is_found_by_exact_fallback(tmp_path):
    manifest = _write_project(
        tmp_path,
        test_source=(
            "import subprocess\n"
            "import sys\n\n"
            "def test_target():\n"
            '    code = "from pathlib import Path; '
            "assert 'maid-knockout' not in Path('src/target.py').read_text()\"\n"
            "    subprocess.run([sys.executable, '-c', code], check=True)\n"
        ),
    )
    evidence = _evidence(manifest, tmp_path, include_context=False)
    evidence = replace(evidence, completeness=_complete(complete=False, reason="child"))

    report = _run(manifest, tmp_path, None, evidence)

    assert report.success is True
    assert report.results[0].proof.used_exact_fallback is True
    assert report.results[0].proof.command == tuple(manifest.validate_commands[0])


def test_baseline_failing_original_command_is_harness_failure_not_detection(tmp_path):
    manifest = _write_project(tmp_path)
    executor = _RecordingExecutor((1,))

    report = _run(manifest, tmp_path, executor)

    assert report.success is False
    assert report.results[0].detected is False
    assert any(
        error.code == ErrorCode.KNOCKOUT_HARNESS_FAILURE for error in report.errors
    )
    assert any("baseline" in error.message.lower() for error in report.errors)
    assert (tmp_path / "src" / "target.py").read_text() == ORIGINAL


def test_baseline_target_mutation_fails_closed_before_mutant_overwrite(tmp_path):
    manifest = _write_project(tmp_path)
    command_written = "def target() -> str:\n    return 'baseline changed me'\n"

    class BaselineMutator:
        def execute(self, command, project_root, manifest_slug):
            (Path(project_root) / "src" / "target.py").write_text(command_written)
            return _run_result(tuple(command), 0)

    report = _run(manifest, tmp_path, BaselineMutator())

    assert report.success is False
    assert report.results[0].detected is False
    assert [error.code for error in report.errors] == [
        ErrorCode.KNOCKOUT_HARNESS_FAILURE
    ]
    assert "baseline" in report.errors[0].message.lower()
    assert "changed target bytes" in report.errors[0].message.lower()
    assert (tmp_path / "src" / "target.py").read_text() == command_written
    assert MUTANT_MARKER not in command_written


@pytest.mark.parametrize(
    "restored_behavior",
    ["write-return", "write-raise", "delete-return", "delete-raise"],
)
def test_restored_control_target_mutation_fails_closed_and_restores_original_bytes(
    tmp_path,
    restored_behavior,
):
    manifest = _write_project(tmp_path)

    class RestoredMutator:
        def __init__(self):
            self.calls = 0

        def execute(self, command, project_root, manifest_slug):
            self.calls += 1
            if self.calls == 3:
                target = Path(project_root) / "src" / "target.py"
                if restored_behavior.startswith("write"):
                    target.write_text(
                        "def target():\n    return 'restored control changed me'\n"
                    )
                else:
                    target.unlink()
                if restored_behavior.endswith("raise"):
                    raise RuntimeError("restored control raised after write")
                return _run_result(tuple(command), 0)
            return _run_result(tuple(command), 1 if self.calls == 2 else 0)

    report = _run(manifest, tmp_path, RestoredMutator())

    assert report.success is False
    assert report.results[0].detected is False
    assert [error.code for error in report.errors] == [
        ErrorCode.KNOCKOUT_HARNESS_FAILURE
    ]
    assert "restored control" in report.errors[0].message.lower()
    assert (tmp_path / "src" / "target.py").read_bytes() == ORIGINAL.encode()


def test_crlf_target_is_restored_byte_for_byte_after_successful_knockout(tmp_path):
    manifest = _write_project(tmp_path)
    source_path = tmp_path / "src" / "target.py"
    original = b"def target() -> str:\r\n    return 'ok'\r\n"
    source_path.write_bytes(original)

    observed: list[bytes] = []

    class NewlineObserver:
        def execute(self, command, project_root, manifest_slug):
            current = (Path(project_root) / "src" / "target.py").read_bytes()
            observed.append(current)
            assert b"\n" not in current.replace(b"\r\n", b"")
            return _run_result(
                tuple(command),
                1 if b"maid-knockout" in current else 0,
            )

    report = _run(manifest, tmp_path, NewlineObserver())

    assert report.success is True
    assert report.results[0].detected is True
    assert len(observed) == 3
    assert b"maid-knockout" in observed[1]
    assert source_path.read_bytes() == original


@pytest.mark.parametrize("drift", ["content", "environment"])
def test_stale_runtime_evidence_runs_exact_fallback(tmp_path, drift):
    manifest = _write_project(tmp_path)
    evidence = _evidence(manifest, tmp_path)
    if drift == "content":
        source = tmp_path / "src" / "target.py"
        source.write_text(source.read_text() + "\n# changed after evidence\n")
    else:
        stale_environment = replace(
            evidence.environment_identities[0],
            pytest_version="stale-pytest",
        )
        evidence = replace(
            evidence,
            environment_identities=(stale_environment,),
            commands=(
                replace(
                    evidence.commands[0],
                    environment_identity=stale_environment,
                ),
            ),
        )
    executor = _RecordingExecutor((0, 1, 0))

    report = _run(manifest, tmp_path, executor, evidence)

    assert report.success is True
    assert report.results[0].proof.used_exact_fallback is True
    assert all(
        command == tuple(manifest.validate_commands[0])
        for command, _slug, _mutated in executor.calls
    )


def test_mutant_red_without_restored_green_is_inconclusive_and_falls_back(tmp_path):
    manifest = _write_project(tmp_path)
    executor = _RecordingExecutor((0, 1, 1, 0, 1, 0))

    report = _run(manifest, tmp_path, executor, _evidence(manifest, tmp_path))

    assert report.success is True
    assert report.results[0].proof.used_exact_fallback is True
    assert report.results[0].proof.restored_exit_code == 0
    assert [call[0] for call in executor.calls].count(
        tuple(manifest.validate_commands[0])
    ) == 3


def test_proven_focused_detector_avoids_broad_original_command(tmp_path):
    manifest = _write_project(tmp_path)
    original = tuple(manifest.validate_commands[0])
    executor = _RecordingExecutor((0, 1, 0))

    report = _run(manifest, tmp_path, executor, _evidence(manifest, tmp_path))

    assert report.success is True
    assert original not in [call[0] for call in executor.calls]


def test_differential_and_legacy_honest_fixture_gate_quality_is_monotonic(tmp_path):
    from maid_runner.core.knockout import run_knockout

    honest_root = tmp_path / "honest"
    unrelated_root = tmp_path / "unrelated"
    honest_root.mkdir()
    unrelated_root.mkdir()
    honest = _write_project(honest_root, "honest")
    unrelated = _write_project(unrelated_root, "unrelated")

    honest_report = run_knockout(
        honest,
        honest_root,
        allow_dirty=True,
        executor=_RecordingExecutor((0, 1, 0)),
    )
    unrelated_report = run_knockout(
        unrelated,
        unrelated_root,
        allow_dirty=True,
        executor=_RecordingExecutor((1,)),
    )

    assert honest_report.success is True
    assert honest_report.results[0].detected is True
    assert unrelated_report.success is False
    assert unrelated_report.results[0].detected is False
    assert [error.code for error in unrelated_report.errors] == [
        ErrorCode.KNOCKOUT_HARNESS_FAILURE
    ]


def test_duplicate_spec_declarations_restore_target_before_next_legacy_side_effect_sequence(
    tmp_path,
):
    first = _write_project(tmp_path, "first")
    second = _write_project(tmp_path, "second")
    executor = _RecordingExecutor((0, 1, 0, 0, 1, 0))

    from maid_runner.core.knockout import run_knockout_batch

    reports = run_knockout_batch(
        (first, second),
        tmp_path,
        allow_dirty=True,
        executor=executor,
    )

    assert list(reports) == [first.source_path, second.source_path]
    assert all(report.success for report in reports.values())
    assert [mutated for _command, _slug, mutated in executor.calls] == [
        False,
        True,
        False,
        False,
        True,
        False,
    ]
    assert [slug for _command, slug, _mutated in executor.calls] == [
        "first",
        "first",
        "first",
        "second",
        "second",
        "second",
    ]
    assert (tmp_path / "src" / "target.py").read_text() == ORIGINAL
