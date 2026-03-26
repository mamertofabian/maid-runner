"""Tests for CLI output formatters (v2)."""

from __future__ import annotations

import json

import pytest

from maid_runner.core.result import (
    BatchTestResult,
    BatchValidationResult,
    ErrorCode,
    FileTrackingEntry,
    FileTrackingReport,
    FileTrackingStatus,
    Location,
    TestRunResult,
    ValidationError,
    ValidationResult,
)
from maid_runner.core.types import TestStream, ValidationMode


@pytest.fixture
def success_result() -> ValidationResult:
    return ValidationResult(
        success=True,
        manifest_slug="add-auth",
        manifest_path="manifests/add-auth.manifest.yaml",
        mode=ValidationMode.IMPLEMENTATION,
        duration_ms=45.0,
    )


@pytest.fixture
def failure_result() -> ValidationResult:
    return ValidationResult(
        success=False,
        manifest_slug="add-auth",
        manifest_path="manifests/add-auth.manifest.yaml",
        mode=ValidationMode.IMPLEMENTATION,
        errors=[
            ValidationError(
                code=ErrorCode.ARTIFACT_NOT_DEFINED,
                message="Artifact 'AuthService.login' not defined in src/auth/service.py",
                location=Location(file="src/auth/service.py"),
            ),
            ValidationError(
                code=ErrorCode.TYPE_MISMATCH,
                message="Type mismatch for 'AuthService.verify': expected 'bool', found 'str'",
                location=Location(file="src/auth/service.py", line=42),
            ),
        ],
        duration_ms=38.0,
    )


@pytest.fixture
def batch_result(success_result, failure_result) -> BatchValidationResult:
    return BatchValidationResult(
        results=[success_result, failure_result],
        total_manifests=5,
        passed=1,
        failed=1,
        skipped=3,
        duration_ms=1200.0,
    )


@pytest.fixture
def test_result_pass() -> TestRunResult:
    return TestRunResult(
        manifest_slug="add-auth",
        command=("pytest", "tests/test_auth.py", "-v"),
        exit_code=0,
        stdout="PASSED",
        stderr="",
        duration_ms=500.0,
    )


@pytest.fixture
def test_result_fail() -> TestRunResult:
    return TestRunResult(
        manifest_slug="add-auth",
        command=("pytest", "tests/test_auth.py", "-v"),
        exit_code=1,
        stdout="FAILED",
        stderr="AssertionError",
        duration_ms=200.0,
    )


@pytest.fixture
def batch_test_result(test_result_pass, test_result_fail) -> BatchTestResult:
    return BatchTestResult(
        results=[test_result_pass, test_result_fail],
        total=2,
        passed=1,
        failed=1,
        duration_ms=700.0,
    )


class TestFormatValidationResult:
    def test_success_text_output(self, success_result):
        from maid_runner.cli.commands._format import format_validation_result

        output = format_validation_result(success_result)
        assert "add-auth" in output
        assert "implementation" in output.lower()

    def test_failure_text_shows_errors(self, failure_result):
        from maid_runner.cli.commands._format import format_validation_result

        output = format_validation_result(failure_result)
        assert "add-auth" in output
        assert "E300" in output
        assert "E302" in output
        assert "AuthService.login" in output

    def test_json_mode_returns_valid_json(self, failure_result):
        from maid_runner.cli.commands._format import format_validation_result

        output = format_validation_result(failure_result, json_mode=True)
        data = json.loads(output)
        assert data["success"] is False
        assert data["manifest"] == "add-auth"
        assert len(data["errors"]) == 2

    def test_quiet_mode_hides_summary(self, success_result):
        from maid_runner.cli.commands._format import format_validation_result

        output = format_validation_result(success_result, quiet=True)
        # In quiet mode, a success should produce minimal/no output
        assert len(output.strip()) == 0 or "add-auth" in output

    def test_quiet_mode_still_shows_errors(self, failure_result):
        from maid_runner.cli.commands._format import format_validation_result

        output = format_validation_result(failure_result, quiet=True)
        assert "E300" in output


class TestFormatBatchResult:
    def test_batch_text_shows_summary(self, batch_result):
        from maid_runner.cli.commands._format import format_batch_result

        output = format_batch_result(batch_result)
        assert "5" in output  # total
        assert "1" in output  # passed or failed count

    def test_batch_json_output(self, batch_result):
        from maid_runner.cli.commands._format import format_batch_result

        output = format_batch_result(batch_result, json_mode=True)
        data = json.loads(output)
        assert data["total"] == 5
        assert data["passed"] == 1
        assert data["failed"] == 1
        assert data["skipped"] == 3

    def test_batch_quiet_mode(self, batch_result):
        from maid_runner.cli.commands._format import format_batch_result

        output = format_batch_result(batch_result, quiet=True)
        # Quiet mode should show failed manifests only
        assert "add-auth" in output


class TestFormatTestResult:
    def test_test_text_output(self, batch_test_result):
        from maid_runner.cli.commands._format import format_test_result

        output = format_test_result(batch_test_result)
        assert "2" in output  # total
        assert "1" in output  # passed or failed

    def test_test_verbose_shows_output(self, batch_test_result):
        from maid_runner.cli.commands._format import format_test_result

        output = format_test_result(batch_test_result, verbose=True)
        assert "PASSED" in output or "FAILED" in output

    def test_test_json_output(self, batch_test_result):
        from maid_runner.cli.commands._format import format_test_result

        output = format_test_result(batch_test_result, json_mode=True)
        data = json.loads(output)
        assert data["total"] == 2
        assert data["passed"] == 1
        assert data["failed"] == 1

    def test_json_includes_stream_field(self):
        from maid_runner.cli.commands._format import format_test_result

        results = BatchTestResult(
            results=[
                TestRunResult(
                    manifest_slug="auth",
                    command=("echo", "test"),
                    exit_code=0,
                    stdout="",
                    stderr="",
                    duration_ms=1.0,
                    stream=TestStream.ACCEPTANCE,
                ),
            ],
            total=1,
            passed=1,
            failed=0,
        )
        output = format_test_result(results, json_mode=True)
        data = json.loads(output)
        assert data["results"][0]["stream"] == "acceptance"

    def test_no_acceptance_legacy_format(self, batch_test_result):
        """Without acceptance tests, format uses legacy 'Test Results' header."""
        from maid_runner.cli.commands._format import format_test_result

        output = format_test_result(batch_test_result)
        assert "Test Results:" in output
        assert "Acceptance Tests" not in output

    def test_acceptance_and_implementation_sections(self):
        """With acceptance tests, shows two-section format."""
        from maid_runner.cli.commands._format import format_test_result

        results = BatchTestResult(
            results=[
                TestRunResult(
                    manifest_slug="auth",
                    command=("pytest", "tests/acceptance/test_auth.py", "-v"),
                    exit_code=0,
                    stdout="1 passed",
                    stderr="",
                    duration_ms=100.0,
                    stream=TestStream.ACCEPTANCE,
                ),
                TestRunResult(
                    manifest_slug="auth",
                    command=("pytest", "tests/test_auth.py", "-v"),
                    exit_code=0,
                    stdout="2 passed",
                    stderr="",
                    duration_ms=200.0,
                    stream=TestStream.IMPLEMENTATION,
                ),
            ],
            total=2,
            passed=2,
            failed=0,
            duration_ms=300.0,
        )
        output = format_test_result(results)
        assert "Acceptance Tests (Stream 1):" in output
        assert "Implementation Tests (Stream 3):" in output


class TestFormatFileTracking:
    def test_file_tracking_text(self):
        from maid_runner.cli.commands._format import format_file_tracking

        report = FileTrackingReport(
            entries=(
                FileTrackingEntry(
                    path="src/auth.py",
                    status=FileTrackingStatus.TRACKED,
                    manifests=("add-auth",),
                ),
                FileTrackingEntry(
                    path="src/utils.py",
                    status=FileTrackingStatus.UNDECLARED,
                ),
                FileTrackingEntry(
                    path="src/config.py",
                    status=FileTrackingStatus.REGISTERED,
                    manifests=("setup",),
                    issues=("No artifacts declared",),
                ),
            )
        )
        output = format_file_tracking(report)
        assert "src/auth.py" in output
        assert "src/utils.py" in output
        assert "src/config.py" in output

    def test_file_tracking_json(self):
        from maid_runner.cli.commands._format import format_file_tracking

        report = FileTrackingReport(
            entries=(
                FileTrackingEntry(
                    path="src/auth.py",
                    status=FileTrackingStatus.TRACKED,
                    manifests=("add-auth",),
                ),
            )
        )
        output = format_file_tracking(report, json_mode=True)
        data = json.loads(output)
        assert "tracked" in data
