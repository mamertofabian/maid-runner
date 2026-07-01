from __future__ import annotations

import json

from maid_runner.core.result import (
    BatchValidationResult,
    ErrorCode,
    FileTrackingEntry,
    FileTrackingReport,
    FileTrackingStatus,
    Location,
    Severity,
    ValidationError,
    ValidationResult,
    VerificationResult,
    VerificationStageResult,
)
from maid_runner.core.types import ValidationMode


def _warning(
    *,
    message: str = "Test has no assertions",
    file: str = "tests/test_gate.py",
    line: int = 3,
) -> ValidationError:
    return ValidationError(
        code=ErrorCode.MISSING_ASSERTIONS,
        message=message,
        severity=Severity.WARNING,
        location=Location(file=file, line=line),
    )


def _validation(
    slug: str,
    warnings: list[ValidationError],
    *,
    success: bool = True,
) -> ValidationResult:
    return ValidationResult(
        success=success,
        manifest_slug=slug,
        manifest_path=f"manifests/{slug}.manifest.yaml",
        mode=ValidationMode.BEHAVIORAL,
        warnings=warnings,
    )


def _warning_batch(warnings: list[ValidationError]) -> BatchValidationResult:
    return BatchValidationResult(
        results=[
            _validation(f"manifest-{index}", [warning])
            for index, warning in enumerate(warnings, start=1)
        ],
        total_manifests=len(warnings),
        passed=len(warnings),
        failed=0,
        skipped=0,
    )


def _blocking_stage() -> VerificationStageResult:
    return VerificationStageResult(
        name="file_tracking",
        success=False,
        _file_tracking=FileTrackingReport(
            entries=(
                FileTrackingEntry(
                    path="src/untracked.py",
                    status=FileTrackingStatus.UNDECLARED,
                ),
            )
        ),
    )


def _summary_result(*, success: bool = False) -> VerificationResult:
    repeated = _warning()
    stages = [
        VerificationStageResult(name="schema", success=True),
        VerificationStageResult(
            name="behavioral",
            success=True,
            _validation=_warning_batch([repeated, repeated, repeated]),
        ),
        VerificationStageResult(name="implementation", success=True),
    ]
    if success:
        stages.append(VerificationStageResult(name="file_tracking", success=True))
    else:
        stages.append(_blocking_stage())
    return VerificationResult(stages=tuple(stages), duration_ms=12.0)


def test_summary_flag_collapses_duplicate_warnings_in_output(
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main

    monkeypatch.setattr(
        "maid_runner.cli.commands.verify._run_verify",
        lambda **kwargs: _summary_result(),
    )

    default_exit = main(["verify", "--no-changed-scope", "--keep-going"])
    default_output = capsys.readouterr().out
    summary_exit = main(["verify", "--summary", "--no-changed-scope", "--keep-going"])
    summary_output = capsys.readouterr().out

    assert default_exit == summary_exit == 1
    assert "WARNINGS (non-blocking, deduplicated 3 -> 1):" in summary_output
    assert "E210 x3 Test has no assertions" in summary_output
    assert summary_output.count("Test has no assertions") == 1
    assert len(summary_output.splitlines()) < len(default_output.splitlines())


def test_summary_flag_lists_blocking_before_warnings(monkeypatch, capsys) -> None:
    from maid_runner.cli.commands._main import main

    monkeypatch.setattr(
        "maid_runner.cli.commands.verify._run_verify",
        lambda **kwargs: _summary_result(),
    )

    exit_code = main(["verify", "--summary", "--no-changed-scope", "--keep-going"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert output.index("BLOCKING (1):") < output.index("WARNINGS (non-blocking")
    assert "FAIL file_tracking" in output
    assert "src/untracked.py" in output


def test_summary_flag_keeps_failed_warning_only_validation_stage_compact(
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main

    repeated = _warning()
    result = VerificationResult(
        stages=(
            VerificationStageResult(
                name="behavioral",
                success=False,
                _validation=BatchValidationResult(
                    results=[
                        _validation(
                            f"manifest-{index}",
                            [repeated],
                            success=False,
                        )
                        for index in range(1, 51)
                    ],
                    total_manifests=50,
                    passed=0,
                    failed=50,
                    skipped=0,
                ),
            ),
        ),
        duration_ms=12.0,
    )
    monkeypatch.setattr(
        "maid_runner.cli.commands.verify._run_verify",
        lambda **kwargs: result,
    )

    exit_code = main(["verify", "--summary", "--no-changed-scope", "--keep-going"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "FAIL behavioral" in output
    assert "50 raw validation warnings" in output
    assert "see WARNINGS section below" in output
    assert "E210 x50 Test has no assertions" in output
    assert output.count("Test has no assertions") == 1
    assert len(output.splitlines()) < 12


def test_summary_flag_preserves_exit_code(monkeypatch, capsys) -> None:
    from maid_runner.cli.commands._main import main

    for result in (_summary_result(success=True), _summary_result(success=False)):
        monkeypatch.setattr(
            "maid_runner.cli.commands.verify._run_verify",
            lambda **kwargs: result,
        )

        default_exit = main(["verify", "--no-changed-scope", "--keep-going"])
        capsys.readouterr()
        summary_exit = main(
            ["verify", "--summary", "--no-changed-scope", "--keep-going"]
        )
        capsys.readouterr()

        assert summary_exit == default_exit


def test_summary_json_exposes_blocking_and_warning_split(monkeypatch, capsys) -> None:
    from maid_runner.cli.commands._format import format_verify_summary
    from maid_runner.cli.commands._main import main

    assert callable(format_verify_summary)
    monkeypatch.setattr(
        "maid_runner.cli.commands.verify._run_verify",
        lambda **kwargs: _summary_result(),
    )

    exit_code = main(["verify", "--summary", "--json", "--no-changed-scope"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert [stage["name"] for stage in payload["findings"]["blocking"]] == [
        "file_tracking"
    ]
    assert payload["findings"]["warnings"] == [
        {
            "code": "E210",
            "message": "Test has no assertions",
            "location": "tests/test_gate.py:3",
            "count": 3,
        }
    ]
    assert payload["passed_stages"] == ["schema", "behavioral", "implementation"]
