from __future__ import annotations

import json
from pathlib import Path

import pytest

from maid_runner.cli.commands._main import build_parser
from maid_runner.cli.commands.validate import cmd_validate
from maid_runner.cli.commands.verify import cmd_verify
from maid_runner.coherence.result import (
    CoherenceIssue,
    CoherenceResult,
    IssueSeverity,
    IssueType,
)
from maid_runner.core.validate import ValidationEngine
from maid_runner.core.result import (
    BatchValidationResult,
    ErrorCode,
    Location,
    ValidationError,
    ValidationResult,
    VerificationResult,
    VerificationStageResult,
)
from maid_runner.core.types import ValidationMode


def _batch_result(success: bool) -> BatchValidationResult:
    errors = []
    if not success:
        errors = [
            ValidationError(
                code=ErrorCode.ARTIFACT_NOT_DEFINED,
                message="Artifact is missing",
                location=Location(file="src/demo.py", line=4),
            )
        ]
    result = ValidationResult(
        success=success,
        manifest_slug="demo",
        manifest_path="manifests/demo.manifest.yaml",
        mode=ValidationMode.IMPLEMENTATION,
        errors=errors,
    )
    return BatchValidationResult(
        results=[result],
        total_manifests=1,
        passed=1 if success else 0,
        failed=0 if success else 1,
        skipped=0,
    )


def _validate_args(tmp_path: Path, sarif_path: Path | None, *, json: bool = False):
    args = build_parser().parse_args(["validate", "--json"] if json else ["validate"])
    args.sarif = str(sarif_path) if sarif_path is not None else None
    args.manifest_dir = str(tmp_path / "manifests")
    args.quiet = True
    return args


def test_build_parser_accepts_sarif_for_validate_and_verify(tmp_path: Path) -> None:
    parser = build_parser()

    validate_args = parser.parse_args(
        ["validate", "--sarif", str(tmp_path / "v.sarif")]
    )
    verify_args = parser.parse_args(["verify", "--sarif", str(tmp_path / "r.sarif")])

    assert validate_args.sarif == str(tmp_path / "v.sarif")
    assert verify_args.sarif == str(tmp_path / "r.sarif")


def test_cmd_validate_writes_sarif_without_changing_success_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report_path = tmp_path / "validate.sarif"
    batch = _batch_result(success=True)
    monkeypatch.setattr(
        ValidationEngine,
        "validate_all",
        lambda *args, **kwargs: batch,
    )

    plain_exit = cmd_validate(_validate_args(tmp_path, None))
    sarif_exit = cmd_validate(_validate_args(tmp_path, report_path))

    assert sarif_exit == plain_exit == 0
    assert report_path.exists()
    assert json.loads(report_path.read_text())["runs"][0]["results"] == []
    capsys.readouterr()


def test_cmd_validate_writes_sarif_without_changing_failure_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report_path = tmp_path / "validate-fail.sarif"
    batch = _batch_result(success=False)
    monkeypatch.setattr(
        ValidationEngine,
        "validate_all",
        lambda *args, **kwargs: batch,
    )

    plain_exit = cmd_validate(_validate_args(tmp_path, None))
    sarif_exit = cmd_validate(_validate_args(tmp_path, report_path))

    assert sarif_exit == plain_exit == 1
    result = json.loads(report_path.read_text())["runs"][0]["results"][0]
    assert result["ruleId"] == "E300"
    assert result["message"]["text"] == "Artifact is missing"
    assert result["locations"][0]["physicalLocation"]["artifactLocation"] == {
        "uri": "src/demo.py"
    }
    capsys.readouterr()


def test_cmd_validate_sarif_write_failure_is_visible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "missing-parent"
    unwritable_path = output_dir / "validate.sarif"
    monkeypatch.setattr(
        ValidationEngine,
        "validate_all",
        lambda *args, **kwargs: _batch_result(success=True),
    )

    exit_code = cmd_validate(_validate_args(tmp_path, unwritable_path))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Failed to write SARIF report" in captured.err
    assert not unwritable_path.exists()


def test_cmd_validate_coherence_only_writes_sarif(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maid_runner.cli.commands import validate as validate_cmd

    report_path = tmp_path / "coherence.sarif"
    coherence = CoherenceResult(
        issues=[
            CoherenceIssue(
                issue_type=IssueType.DUPLICATE,
                severity=IssueSeverity.ERROR,
                message="Duplicate artifact",
                file="src/coherence.py",
                suggestion="Rename one artifact.",
            )
        ]
    )
    monkeypatch.setattr(
        validate_cmd,
        "run_coherence",
        lambda manifest_dir, json_mode: coherence,
    )
    args = build_parser().parse_args(
        [
            "validate",
            "--coherence-only",
            "--sarif",
            str(report_path),
        ]
    )

    exit_code = cmd_validate(args)

    assert exit_code == 1
    result = json.loads(report_path.read_text())["runs"][0]["results"][0]
    assert result["ruleId"] == "E400"
    assert (
        result["message"]["text"]
        == "Duplicate artifact\n\nSuggestion: Rename one artifact."
    )
    assert result["locations"][0]["physicalLocation"]["artifactLocation"] == {
        "uri": "src/coherence.py"
    }


def test_cmd_verify_writes_sarif_without_changing_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maid_runner.cli.commands import verify as verify_cmd

    report_path = tmp_path / "verify.sarif"
    verify_result = VerificationResult(
        stages=(
            VerificationStageResult(
                name="validation",
                success=False,
                _validation=_batch_result(success=False),
            ),
        )
    )
    monkeypatch.setattr(
        verify_cmd,
        "_run_verify",
        lambda **kwargs: verify_result,
    )
    args = build_parser().parse_args(
        [
            "verify",
            "--no-changed-scope",
            "--sarif",
            str(report_path),
        ]
    )

    exit_code = cmd_verify(args)

    assert exit_code == 1
    result = json.loads(report_path.read_text())["runs"][0]["results"][0]
    assert result["ruleId"] == "E300"


def test_cmd_verify_sarif_write_failure_is_visible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands import verify as verify_cmd

    monkeypatch.setattr(
        verify_cmd,
        "_run_verify",
        lambda **kwargs: VerificationResult(stages=()),
    )
    args = build_parser().parse_args(
        [
            "verify",
            "--no-changed-scope",
            "--sarif",
            str(tmp_path / "missing-parent" / "verify.sarif"),
        ]
    )

    exit_code = cmd_verify(args)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Failed to write SARIF report" in captured.err
