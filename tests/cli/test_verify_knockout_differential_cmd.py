"""CLI contract for differential knockout proof and evidence wiring."""

from __future__ import annotations

import json
from pathlib import Path


def test_differential_proof_text_and_json_expose_same_detector_and_fallback() -> None:
    from maid_runner.cli.commands._format import format_verify_result
    from maid_runner.core.knockout import (
        KnockoutArtifactIdentity,
        KnockoutDifferentialProof,
        KnockoutReport,
        KnockoutResult,
    )
    from maid_runner.core.result import VerificationResult, VerificationStageResult

    proof = KnockoutDifferentialProof(
        identity=KnockoutArtifactIdentity(
            file_path="src/target.py",
            artifact_name="target",
            artifact_kind="function",
            parent_class=None,
        ),
        command=("pytest", "tests/test_target.py"),
        baseline_exit_code=0,
        mutant_exit_code=1,
        restored_exit_code=0,
        detecting_nodeids=("tests/test_target.py::test_target",),
        used_exact_fallback=True,
        diagnostics=(),
    )
    report = KnockoutReport(
        results=(
            KnockoutResult(
                artifact_name="target",
                artifact_kind="function",
                parent_class=None,
                file_path="src/target.py",
                detected=True,
                duration_ms=3.0,
                proof=proof,
            ),
        ),
        errors=(),
    )
    result = VerificationResult(
        stages=(
            VerificationStageResult(
                name="knockout",
                success=True,
                _errors=(report,),
            ),
        )
    )

    text = format_verify_result(result)
    payload = json.loads(format_verify_result(result, json_mode=True))
    json_proof = payload["stages"][0]["details"]["results"][0]["proof"]

    assert "tests/test_target.py::test_target" in text
    assert "exact fallback: yes" in text
    assert json_proof["detecting_nodeids"] == ["tests/test_target.py::test_target"]
    assert json_proof["used_exact_fallback"] is True
    assert json_proof["baseline_exit_code"] == 0
    assert json_proof["mutant_exit_code"] == 1
    assert json_proof["restored_exit_code"] == 0


def test_deep_verify_passes_runtime_evidence_to_focused_knockout(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main

    _write_knockout_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "verify",
            "--artifact-coverage",
            "--knockout",
            "--knockout-allow-dirty",
            "--no-changed-scope",
            "--advisory",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    knockout = _stage(payload, "knockout")
    proof = knockout["details"]["results"][0]["proof"]

    assert exit_code == 0
    assert _stage(payload, "artifact_coverage")["success"] is True
    assert knockout["success"] is True
    assert proof["used_exact_fallback"] is False
    assert proof["detecting_nodeids"] == ["tests/test_target.py::test_target_behavior"]


def _write_knockout_project(root: Path) -> None:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src" / "__init__.py").write_text("")
    (root / "src" / "target.py").write_text(
        'def target() -> str:\n    return "honest"\n'
    )
    (root / "src" / "config.py").write_text('VALUE = "stable"\n')
    (root / "tests" / "test_target.py").write_text(
        "from src.config import VALUE\n"
        "from src.target import target\n\n"
        "def test_target_behavior():\n"
        '    assert target() == "honest"\n'
        '    assert VALUE == "stable"\n'
    )
    (root / "manifests" / "target.manifest.yaml").write_text(
        """schema: "2"
goal: "Verify differential knockout target"
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
  - python -m pytest -q tests/test_target.py
"""
    )
    (root / "manifests" / "config.manifest.yaml").write_text(
        """schema: "2"
goal: "Track an active manifest without knockout targets"
type: feature
created: "2026-08-12T00:00:01Z"
files:
  edit:
    - path: src/config.py
      artifacts:
        - kind: attribute
          name: VALUE
          type: str
  read:
    - tests/test_target.py
validate:
  - python -m pytest -q tests/test_target.py
"""
    )


def _stage(payload: dict, name: str) -> dict:
    return next(stage for stage in payload["stages"] if stage["name"] == name)
