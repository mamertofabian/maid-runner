"""Knockout trusts grouped coverage evidence when command identities match.

Contract: manifests/drafts/121-34-trust-grouped-knockout-command-order.manifest.yaml
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import TestRunResult
from maid_runner.core.runtime_evidence import collect_runtime_evidence
from maid_runner.core.types import TestStream

ORIGINAL_A = "def alpha() -> str:\n    return 'a'\n"
ORIGINAL_B = "def beta() -> str:\n    return 'b'\n"
MUTANT_MARKER = 'raise NotImplementedError("maid-knockout")'


def test_reversed_grouped_command_order_still_uses_focused_knockout(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifests = _write_project(tmp_path)
    evidence = collect_runtime_evidence(manifests, tmp_path).evidence
    assert len(evidence.commands) == 2
    evidence = replace(evidence, commands=tuple(reversed(evidence.commands)))
    executor = _RecordingExecutor((0, 1, 0, 0, 1, 0))

    reports = run_knockout_batch(
        manifests,
        tmp_path,
        evidence=evidence,
        allow_dirty=True,
        executor=executor,
    )

    proofs = [report.results[0].proof for report in reports.values() if report.results]
    assert proofs and all(proof is not None for proof in proofs)
    assert all(proof.used_exact_fallback is False for proof in proofs)
    assert {proof.detecting_nodeids for proof in proofs} == {
        ("tests/test_alpha.py::test_alpha",),
        ("tests/test_beta.py::test_beta",),
    }


def test_missing_knockout_command_identity_still_forces_exact_fallback(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifests = _write_project(tmp_path)
    evidence = collect_runtime_evidence(manifests, tmp_path).evidence
    evidence = replace(evidence, commands=evidence.commands[:1])
    original_b = tuple(manifests[1].validate_commands[0])
    executor = _RecordingExecutor((0, 1, 0, 0, 1, 0))

    reports = run_knockout_batch(
        manifests,
        tmp_path,
        evidence=evidence,
        allow_dirty=True,
        executor=executor,
    )

    beta = reports[manifests[1].source_path]
    assert beta.results[0].proof is not None
    assert beta.results[0].proof.used_exact_fallback is True
    assert [call[0] for call in executor.calls].count(original_b) == 3


def _write_project(root: Path):
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src/alpha.py").write_text(ORIGINAL_A)
    (root / "src/beta.py").write_text(ORIGINAL_B)
    (root / "tests/test_alpha.py").write_text(
        "from src.alpha import alpha\n\n"
        "def test_alpha():\n"
        "    assert alpha() == 'a'\n"
    )
    (root / "tests/test_beta.py").write_text(
        "from src.beta import beta\n\n"
        "def test_beta():\n"
        "    assert beta() == 'b'\n"
    )
    return (
        _write_manifest(root, "alpha", "src/alpha.py", "alpha", "tests/test_alpha.py"),
        _write_manifest(root, "beta", "src/beta.py", "beta", "tests/test_beta.py"),
    )


def _write_manifest(root: Path, slug: str, source: str, name: str, test_path: str):
    path = root / f"manifests/{slug}.manifest.yaml"
    path.write_text(
        f"""schema: "2"
goal: "Constrain {name}"
type: feature
created: "2026-08-13T00:00:00Z"
files:
  edit:
    - path: {source}
      artifacts:
        - kind: function
          name: {name}
          args: []
          returns: str
  read:
    - {test_path}
validate:
  - python -m pytest -q {test_path}
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
        mutated = MUTANT_MARKER in (
            Path(project_root) / "src/alpha.py"
        ).read_text() or (
            MUTANT_MARKER in (Path(project_root) / "src/beta.py").read_text()
        )
        self.calls.append((command, manifest_slug, mutated))
        return _run_result(command, next(self.decisions))
