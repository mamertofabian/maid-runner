"""Behavioral contract for grouped shared-test plan-lock recovery guidance."""

from __future__ import annotations

import json

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


def _failure(
    slug: str,
    *,
    code: ErrorCode = ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK,
    suggestion: str = (
        "Run `maid plan dependents tests/test_shared.py` to inspect every active "
        "lock that pins this behavioral test before revising evidence."
    ),
) -> ValidationResult:
    return ValidationResult(
        success=False,
        manifest_slug=slug,
        manifest_path=f"manifests/{slug}.manifest.yaml",
        mode=ValidationMode.IMPLEMENTATION,
        errors=[
            ValidationError(
                code=code,
                message=(
                    "BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK: behavioral test changed "
                    "after lock: tests/test_shared.py"
                ),
                location=Location(file=f"manifests/{slug}.manifest.yaml"),
                suggestion=suggestion,
            )
        ],
    )


def _verify_result(*validations: ValidationResult) -> VerificationResult:
    return VerificationResult(
        stages=(
            VerificationStageResult(
                name="plan_lock",
                success=False,
                _validation=BatchValidationResult(
                    results=list(validations),
                    total_manifests=len(validations),
                    passed=0,
                    failed=len(validations),
                    skipped=0,
                ),
            ),
        )
    )


def test_summary_groups_shared_test_recovery_once_and_preserves_manifest_diagnostics() -> (
    None
):
    from maid_runner.cli.commands._format import format_verify_summary
    from maid_runner.core.verify_summary import (
        VerifyRecoveryGroup,
        VerifySummary,
        build_verify_summary,
    )

    result = _verify_result(_failure("alpha"), _failure("beta"))

    summary: VerifySummary = build_verify_summary(result)
    output = format_verify_summary(result)

    assert summary.recovery_groups == (
        VerifyRecoveryGroup(
            code="E701",
            suggestion=(
                "Run `maid plan dependents tests/test_shared.py` to inspect every "
                "active lock that pins this behavioral test before revising evidence."
            ),
            manifest_paths=(
                "manifests/alpha.manifest.yaml",
                "manifests/beta.manifest.yaml",
            ),
            count=2,
        ),
    )
    assert "FAIL alpha" in output
    assert "FAIL beta" in output
    assert output.count("E701 BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK") == 2
    assert "RECOVERY (1 group):" in output
    assert "E701 x2 across 2 manifests" in output
    assert "manifests/alpha.manifest.yaml, manifests/beta.manifest.yaml" in output
    assert output.count("maid plan dependents tests/test_shared.py") == 1


def test_summary_keeps_distinct_shared_test_recovery_groups_separate() -> None:
    from maid_runner.core.verify_summary import (
        VerifyRecoveryGroup,
        build_verify_summary,
    )

    first_suggestion = "Run `maid plan dependents tests/test_first.py` before revise."
    second_suggestion = "Run `maid plan dependents tests/test_second.py` before revise."
    result = _verify_result(
        _failure("alpha", suggestion=first_suggestion),
        _failure("beta", suggestion=second_suggestion),
        _failure("gamma", suggestion=first_suggestion),
        _failure("delta", suggestion=second_suggestion),
    )

    groups: tuple[VerifyRecoveryGroup, ...] = build_verify_summary(
        result
    ).recovery_groups

    assert [group.suggestion for group in groups] == [
        first_suggestion,
        second_suggestion,
    ]
    assert [group.manifest_paths for group in groups] == [
        ("manifests/alpha.manifest.yaml", "manifests/gamma.manifest.yaml"),
        ("manifests/beta.manifest.yaml", "manifests/delta.manifest.yaml"),
    ]
    assert [group.count for group in groups] == [2, 2]


def test_summary_json_and_sarif_keep_each_e701_diagnostic() -> None:
    from maid_runner.cli.commands._format import format_verify_summary
    from maid_runner.core.sarif import build_sarif_report

    result = _verify_result(_failure("alpha"), _failure("beta"))

    summary_payload = json.loads(format_verify_summary(result, json_mode=True))
    sarif_payload = build_sarif_report(result)

    recovery = summary_payload["findings"]["recovery"]
    assert recovery == [
        {
            "code": "E701",
            "suggestion": (
                "Run `maid plan dependents tests/test_shared.py` to inspect every "
                "active lock that pins this behavioral test before revising evidence."
            ),
            "manifest_paths": [
                "manifests/alpha.manifest.yaml",
                "manifests/beta.manifest.yaml",
            ],
            "count": 2,
        }
    ]
    blocking_results = summary_payload["findings"]["blocking"][0]["details"]["results"]
    assert [item["manifest"] for item in blocking_results] == ["alpha", "beta"]
    assert all(item["errors"][0]["code"] == "E701" for item in blocking_results)
    assert all("suggestion" in item["errors"][0] for item in blocking_results)

    sarif_results = sarif_payload["runs"][0]["results"]
    assert [item["ruleId"] for item in sarif_results] == ["E701", "E701"]
    assert all(
        "Suggestion: Run `maid plan dependents tests/test_shared.py`"
        in item["message"]["text"]
        for item in sarif_results
    )


def test_summary_does_not_group_non_e701_suggestions() -> None:
    from maid_runner.cli.commands._format import format_verify_summary
    from maid_runner.core.verify_summary import build_verify_summary

    shared_suggestion = "Use the ordinary repair workflow."
    result = _verify_result(
        _failure(
            "alpha",
            code=ErrorCode.MANIFEST_CONTRACT_WEAKENED_AFTER_LOCK,
            suggestion=shared_suggestion,
        ),
        _failure(
            "beta",
            code=ErrorCode.MANIFEST_CONTRACT_WEAKENED_AFTER_LOCK,
            suggestion=shared_suggestion,
        ),
    )

    summary = build_verify_summary(result)
    output = format_verify_summary(result)

    assert summary.recovery_groups == ()
    assert output.count(shared_suggestion) == 2
    assert "RECOVERY" not in output


def test_summary_keeps_single_e701_suggestion_inline_without_recovery_section() -> None:
    from maid_runner.cli.commands._format import format_verify_summary
    from maid_runner.core.verify_summary import build_verify_summary

    result = _verify_result(_failure("alpha"))

    summary = build_verify_summary(result)
    output = format_verify_summary(result)

    assert summary.recovery_groups == ()
    assert output.count("maid plan dependents tests/test_shared.py") == 1
    assert "RECOVERY" not in output
