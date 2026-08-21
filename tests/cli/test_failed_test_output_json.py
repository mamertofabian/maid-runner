"""Behavioral contract for bounded failed-command JSON diagnostics."""

import json

from maid_runner.cli.commands._format import (
    format_batch_result,
    format_test_result,
    format_validation_result,
    format_verify_result,
)
from maid_runner.core.result import (
    BatchTestResult,
    BatchValidationResult,
    TestRunResult,
    ValidationResult,
    VerificationResult,
    VerificationStageResult,
)
from maid_runner.core.types import ValidationMode


def test_failed_json_result_includes_only_bounded_output_tails() -> None:
    marker = "failure-at-the-end"
    long_stdout = "x" * 20_000 + marker
    long_stderr = "y" * 20_000 + marker
    results = BatchTestResult(
        results=[
            TestRunResult(
                manifest_slug="failed",
                command=("pytest", "tests/test_failure.py"),
                exit_code=1,
                stdout=long_stdout,
                stderr=long_stderr,
                duration_ms=10.0,
            ),
            TestRunResult(
                manifest_slug="passed",
                command=("pytest", "tests/test_success.py"),
                exit_code=0,
                stdout="successful output stays private",
                stderr="",
                duration_ms=5.0,
            ),
        ],
        total=2,
        passed=1,
        failed=1,
    )

    payload = json.loads(format_test_result(results, json_mode=True))
    failed, passed = payload["results"]

    assert failed["manifest"] == "failed"
    assert failed["command"] == ["pytest", "tests/test_failure.py"]
    assert failed["exit_code"] == 1
    assert failed["success"] is False
    assert {key: value for key, value in payload.items() if key != "results"} == {
        "success": False,
        "total": 2,
        "passed": 1,
        "failed": 1,
        "duration_ms": None,
        "chain_errors": [],
        "scheduling_notices": [],
    }
    assert {
        key: value
        for key, value in failed.items()
        if key not in {"stdout_tail", "stderr_tail"}
    } == {
        "manifest": "failed",
        "command": ["pytest", "tests/test_failure.py"],
        "exit_code": 1,
        "success": False,
        "duration_ms": 10.0,
        "stream": "implementation",
    }
    assert failed["stdout_tail"] == long_stdout[-16_384:]
    assert failed["stderr_tail"] == long_stderr[-16_384:]
    assert passed == {
        "manifest": "passed",
        "command": ["pytest", "tests/test_success.py"],
        "exit_code": 0,
        "success": True,
        "duration_ms": 5.0,
        "stream": "implementation",
    }
    assert "stdout_tail" not in passed
    assert "stderr_tail" not in passed


def test_failed_text_result_includes_only_bounded_output_tails() -> None:
    stdout_marker = "stdout-failure-at-the-end"
    stderr_marker = "stderr-failure-at-the-end"
    stdout_prefix = "stdout-prefix-should-be-truncated"
    stderr_prefix = "stderr-prefix-should-be-truncated"
    results = BatchTestResult(
        results=[
            TestRunResult(
                manifest_slug="failed",
                command=("pytest", "tests/test_failure.py"),
                exit_code=1,
                stdout=f"{stdout_prefix}\n" + "x" * 20_000 + stdout_marker,
                stderr=f"{stderr_prefix}\n" + "y" * 20_000 + stderr_marker,
                duration_ms=10.0,
            ),
            TestRunResult(
                manifest_slug="passed",
                command=("pytest", "tests/test_success.py"),
                exit_code=0,
                stdout="successful output stays private",
                stderr="",
                duration_ms=5.0,
            ),
        ],
        total=2,
        passed=1,
        failed=1,
    )

    rendered = format_test_result(results)

    assert stdout_marker in rendered
    assert stderr_marker in rendered
    assert stdout_prefix not in rendered
    assert stderr_prefix not in rendered
    assert "successful output stays private" not in rendered


def _failed_test_batch() -> BatchTestResult:
    return BatchTestResult(
        results=[
            TestRunResult(
                manifest_slug="failed",
                command=("pytest",),
                exit_code=1,
                stdout="private stdout",
                stderr="private stderr",
                duration_ms=1.0,
            )
        ],
        total=1,
        passed=0,
        failed=1,
    )


def test_validation_json_keeps_embedded_failed_test_output_private() -> None:
    validation = ValidationResult(
        success=True,
        manifest_slug="demo",
        manifest_path="manifests/demo.manifest.yaml",
        mode=ValidationMode.IMPLEMENTATION,
    )

    payload = json.loads(
        format_validation_result(
            validation,
            json_mode=True,
            test_result=_failed_test_batch(),
            tests_requested=True,
        )
    )
    failed = payload["tests"]["results"][0]

    assert failed == {
        "manifest": "failed",
        "command": ["pytest"],
        "exit_code": 1,
        "success": False,
        "duration_ms": 1.0,
        "stream": "implementation",
    }


def test_batch_validation_json_keeps_embedded_failed_test_output_private() -> None:
    validation = BatchValidationResult(
        results=[], total_manifests=0, passed=0, failed=0, skipped=0
    )

    payload = json.loads(
        format_batch_result(
            validation,
            json_mode=True,
            test_result=_failed_test_batch(),
            tests_requested=True,
        )
    )
    failed = payload["tests"]["results"][0]

    assert failed == {
        "manifest": "failed",
        "command": ["pytest"],
        "exit_code": 1,
        "success": False,
        "duration_ms": 1.0,
        "stream": "implementation",
    }


def test_failed_json_result_preserves_short_output_and_omits_empty_stream() -> None:
    result = BatchTestResult(
        results=[
            TestRunResult(
                manifest_slug="failed",
                command=("pytest",),
                exit_code=1,
                stdout="short failure",
                stderr="",
                duration_ms=1.0,
            )
        ],
        total=1,
        passed=0,
        failed=1,
    )

    failed = json.loads(format_test_result(result, json_mode=True))["results"][0]

    assert failed["stdout_tail"] == "short failure"
    assert "stderr_tail" not in failed


def test_verify_json_reuses_bounded_failed_test_output_tails() -> None:
    verify_stdout = "verify-out-" * 2_000
    verify_stderr = "verify-error-" * 2_000
    tests = BatchTestResult(
        results=[
            TestRunResult(
                manifest_slug="failed",
                command=("pytest", "tests/test_failure.py"),
                exit_code=1,
                stdout=verify_stdout,
                stderr=verify_stderr,
                duration_ms=10.0,
            ),
            TestRunResult(
                manifest_slug="passed",
                command=("pytest", "tests/test_success.py"),
                exit_code=0,
                stdout="successful output stays private",
                stderr="",
                duration_ms=5.0,
            ),
        ],
        total=2,
        passed=1,
        failed=1,
    )
    result = VerificationResult(
        stages=(VerificationStageResult(name="tests", success=False, _tests=tests),)
    )

    payload = json.loads(format_verify_result(result, json_mode=True))
    failed, passed = payload["stages"][0]["details"]["results"]

    assert failed["stdout_tail"] == verify_stdout[-16_384:]
    assert failed["stderr_tail"] == verify_stderr[-16_384:]
    assert "stdout_tail" not in passed
    assert "stderr_tail" not in passed
