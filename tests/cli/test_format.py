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


class TestPrintError:
    def test_text_mode_prints_to_stderr(self, capsys):
        from maid_runner.cli.commands._format import print_error

        print_error("something went wrong")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Error: something went wrong" in captured.err

    def test_json_mode_prints_to_stdout(self, capsys):
        from maid_runner.cli.commands._format import print_error

        print_error("bad input", json_mode=True)
        captured = capsys.readouterr()
        assert captured.err == ""
        data = json.loads(captured.out)
        assert data == {"error": "bad input"}


class TestFormatManifestsList:
    def _make_manifest(self, slug, goal, source_path):
        from types import SimpleNamespace

        return SimpleNamespace(slug=slug, goal=goal, source_path=source_path)

    def test_json_mode_returns_valid_json(self):
        from maid_runner.cli.commands._format import format_manifests_list

        manifests = [
            self._make_manifest(
                "add-auth", "Add auth", "manifests/add-auth.manifest.yaml"
            ),
            self._make_manifest(
                "add-db", "Add database", "manifests/add-db.manifest.yaml"
            ),
        ]
        output = format_manifests_list(manifests, "src/auth.py", json_mode=True)
        data = json.loads(output)
        assert len(data) == 2
        assert data[0]["slug"] == "add-auth"
        assert data[0]["goal"] == "Add auth"
        assert data[0]["path"] == "manifests/add-auth.manifest.yaml"
        assert data[1]["slug"] == "add-db"

    def test_quiet_mode_returns_paths_only(self):
        from maid_runner.cli.commands._format import format_manifests_list

        manifests = [
            self._make_manifest(
                "add-auth", "Add auth", "manifests/add-auth.manifest.yaml"
            ),
            self._make_manifest(
                "add-db", "Add database", "manifests/add-db.manifest.yaml"
            ),
        ]
        output = format_manifests_list(manifests, "src/auth.py", quiet=True)
        lines = output.strip().split("\n")
        assert lines == [
            "manifests/add-auth.manifest.yaml",
            "manifests/add-db.manifest.yaml",
        ]

    def test_empty_list_returns_no_manifests_message(self):
        from maid_runner.cli.commands._format import format_manifests_list

        output = format_manifests_list([], "src/orphan.py")
        assert output == "No manifests reference 'src/orphan.py'"

    def test_text_mode_shows_slug_and_goal(self):
        from maid_runner.cli.commands._format import format_manifests_list

        manifests = [
            self._make_manifest(
                "add-auth", "Add authentication", "manifests/add-auth.manifest.yaml"
            ),
        ]
        output = format_manifests_list(manifests, "src/auth.py")
        assert "Manifests referencing 'src/auth.py':" in output
        assert "add-auth: Add authentication" in output


class TestFormatBootstrapReport:
    def _make_report(self, **overrides):
        from maid_runner.core.bootstrap import BootstrapReport

        defaults = dict(
            results=(),
            total_discovered=0,
            captured=0,
            skipped=0,
            failed=0,
            excluded=0,
            total_artifacts=0,
            manifests_dir=None,
            duration_ms=None,
        )
        defaults.update(overrides)
        return BootstrapReport(**defaults)

    def _make_file_result(self, **overrides):
        from maid_runner.core.bootstrap import BootstrapFileResult

        defaults = dict(
            path="src/example.py",
            status="captured",
            artifact_count=0,
            error=None,
            manifest_slug=None,
        )
        defaults.update(overrides)
        return BootstrapFileResult(**defaults)

    def test_json_mode_returns_valid_json(self):
        from maid_runner.cli.commands._format import format_bootstrap_report

        file_result = self._make_file_result(
            path="src/auth.py",
            status="captured",
            artifact_count=3,
            manifest_slug="snapshot-auth",
        )
        report = self._make_report(
            results=(file_result,),
            total_discovered=5,
            captured=1,
            skipped=2,
            failed=1,
            excluded=1,
            total_artifacts=3,
            manifests_dir="manifests/",
            duration_ms=120.0,
        )
        output = format_bootstrap_report(report, json_mode=True)
        data = json.loads(output)
        assert data["total_discovered"] == 5
        assert data["captured"] == 1
        assert data["skipped"] == 2
        assert data["failed"] == 1
        assert data["excluded"] == 1
        assert data["total_artifacts"] == 3
        assert data["manifests_dir"] == "manifests/"
        assert data["duration_ms"] == 120.0
        assert len(data["results"]) == 1
        assert data["results"][0]["path"] == "src/auth.py"
        assert data["results"][0]["status"] == "captured"
        assert data["results"][0]["artifact_count"] == 3
        assert data["results"][0]["manifest_slug"] == "snapshot-auth"

    def test_quiet_mode_no_captures_returns_empty(self):
        from maid_runner.cli.commands._format import format_bootstrap_report

        report = self._make_report(captured=0, total_artifacts=0)
        output = format_bootstrap_report(report, quiet=True)
        assert output == ""

    def test_quiet_mode_with_captures(self):
        from maid_runner.cli.commands._format import format_bootstrap_report

        report = self._make_report(captured=3, total_artifacts=12)
        output = format_bootstrap_report(report, quiet=True)
        assert output == "3 files captured (12 artifacts)"

    def test_text_mode_shows_summary(self):
        from maid_runner.cli.commands._format import format_bootstrap_report

        report = self._make_report(
            total_discovered=10,
            captured=4,
            skipped=3,
            failed=1,
            excluded=2,
            total_artifacts=15,
            manifests_dir="manifests/",
            duration_ms=250.0,
        )
        output = format_bootstrap_report(report)
        assert "Bootstrap: 10 source files discovered" in output
        assert "Captured:  4 files (15 artifacts)" in output
        assert "Skipped:   3 files (already tracked)" in output
        assert "Failed:    1 files" in output
        assert "Excluded:  2 files" in output
        assert "Duration:  250ms" in output
        assert "Manifests written to: manifests/" in output

    def test_verbose_mode_shows_per_file_details(self):
        from maid_runner.cli.commands._format import format_bootstrap_report

        results = (
            self._make_file_result(
                path="src/auth.py", status="captured", artifact_count=5
            ),
            self._make_file_result(path="src/config.py", status="skipped"),
            self._make_file_result(path="src/test_util.py", status="excluded"),
        )
        report = self._make_report(
            results=results,
            total_discovered=3,
            captured=1,
            skipped=1,
            failed=0,
            excluded=1,
            total_artifacts=5,
        )
        output = format_bootstrap_report(report, verbose=True)
        assert "SNAP src/auth.py (5 artifacts)" in output
        assert "SKIP src/config.py" in output
        assert "EXCL src/test_util.py" in output

    def test_failed_files_show_errors(self):
        from maid_runner.cli.commands._format import format_bootstrap_report

        results = (
            self._make_file_result(
                path="src/broken.py",
                status="failed",
                error="SyntaxError: invalid syntax",
            ),
        )
        report = self._make_report(
            results=results,
            total_discovered=1,
            captured=0,
            skipped=0,
            failed=1,
            excluded=0,
            total_artifacts=0,
        )
        output = format_bootstrap_report(report)
        assert "src/broken.py: SyntaxError: invalid syntax" in output


class TestFormatCoherenceResult:
    def test_json_mode_returns_valid_json(self):
        from maid_runner.cli.commands._format import format_coherence_result
        from maid_runner.coherence.result import (
            CoherenceResult,
            CoherenceIssue,
            IssueSeverity,
            IssueType,
        )

        issue = CoherenceIssue(
            issue_type=IssueType.NAMING,
            severity=IssueSeverity.WARNING,
            message="Inconsistent naming",
            file="src/auth.py",
        )
        result = CoherenceResult(
            issues=[issue],
            checks_run=["naming", "duplicates"],
            duration_ms=80.0,
        )
        output = format_coherence_result(result, json_mode=True)
        data = json.loads(output)
        assert data["success"] is True  # warnings don't cause failure
        assert data["errors"] == 0
        assert data["warnings"] == 1
        assert data["checks_run"] == ["naming", "duplicates"]
        assert len(data["issues"]) == 1
        assert data["issues"][0]["severity"] == "warning"
        assert data["duration_ms"] == 80.0

    def test_passing_result_shows_pass(self):
        from maid_runner.cli.commands._format import format_coherence_result
        from maid_runner.coherence.result import CoherenceResult

        result = CoherenceResult(
            issues=[],
            checks_run=["naming"],
        )
        output = format_coherence_result(result)
        assert "Coherence: PASS" in output
        assert "Issues: 0 errors, 0 warnings" in output

    def test_failing_result_shows_fail(self):
        from maid_runner.cli.commands._format import format_coherence_result
        from maid_runner.coherence.result import (
            CoherenceResult,
            CoherenceIssue,
            IssueSeverity,
            IssueType,
        )

        issue = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="Duplicate artifact 'login'",
        )
        result = CoherenceResult(
            issues=[issue],
            checks_run=["duplicates"],
        )
        output = format_coherence_result(result)
        assert "Coherence: FAIL" in output
        assert "Issues: 1 errors, 0 warnings" in output

    def test_issues_displayed_with_severity(self):
        from maid_runner.cli.commands._format import format_coherence_result
        from maid_runner.coherence.result import (
            CoherenceResult,
            CoherenceIssue,
            IssueSeverity,
            IssueType,
        )

        issues = [
            CoherenceIssue(
                issue_type=IssueType.DUPLICATE,
                severity=IssueSeverity.ERROR,
                message="Duplicate artifact 'login'",
                file="src/auth.py",
            ),
            CoherenceIssue(
                issue_type=IssueType.NAMING,
                severity=IssueSeverity.WARNING,
                message="Non-standard name 'doStuff'",
            ),
        ]
        result = CoherenceResult(
            issues=issues,
            checks_run=["duplicates", "naming"],
        )
        output = format_coherence_result(result)
        assert "ERROR [src/auth.py] Duplicate artifact 'login'" in output
        assert "WARNING Non-standard name 'doStuff'" in output

    def test_duration_displayed_when_present(self):
        from maid_runner.cli.commands._format import format_coherence_result
        from maid_runner.coherence.result import CoherenceResult

        result = CoherenceResult(
            issues=[],
            checks_run=["naming"],
            duration_ms=42.5,
        )
        output = format_coherence_result(result)
        assert "Duration: 42ms" in output
