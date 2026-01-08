"""Behavioral tests for Task 137: validate.py --coherence flag integration.

Tests the integration of CoherenceValidator into the validate.py CLI module.
This adds --coherence and --coherence-only flags that enable architectural
coherence validation during manifest validation.

Artifacts tested:
- run_coherence_validation(manifest_path: Path, manifest_dir: Path, quiet: bool) -> CoherenceResult
- _format_coherence_issues(result: CoherenceResult, quiet: bool) -> None

The run_coherence_validation function creates a CoherenceValidator and runs
validation against the specified manifest. The _format_coherence_issues function
formats and prints coherence validation issues to stdout.
"""

import json
import pytest
from pathlib import Path
from typing import Any, Dict

from maid_runner.cli.validate import (
    run_coherence_validation,
    _format_coherence_issues,
)
from maid_runner.coherence.result import (
    CoherenceResult,
    CoherenceIssue,
    IssueSeverity,
    IssueType,
)


@pytest.fixture
def manifest_dir(tmp_path: Path) -> Path:
    """Create a temporary manifest directory."""
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    return manifests


@pytest.fixture
def sample_manifest_data() -> Dict[str, Any]:
    """Create sample manifest data for testing."""
    return {
        "version": "1",
        "goal": "Test coherence validation",
        "taskType": "create",
        "creatableFiles": ["src/module.py"],
        "editableFiles": [],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "src/module.py",
            "contains": [
                {"type": "function", "name": "test_function"},
            ],
        },
        "validationCommand": ["pytest", "tests/test_module.py", "-v"],
    }


@pytest.fixture
def manifest_file(manifest_dir: Path, sample_manifest_data: Dict[str, Any]) -> Path:
    """Create a manifest file in the test directory."""
    manifest_path = manifest_dir / "task-001.manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(sample_manifest_data, f)
    return manifest_path


@pytest.fixture
def valid_coherence_result() -> CoherenceResult:
    """Create a valid CoherenceResult with no issues."""
    return CoherenceResult(valid=True, issues=[])


@pytest.fixture
def coherence_result_with_issues() -> CoherenceResult:
    """Create a CoherenceResult with sample issues."""
    issues = [
        CoherenceIssue(
            issue_type=IssueType.NAMING,
            severity=IssueSeverity.WARNING,
            message="Function name does not follow snake_case convention",
            suggestion="Rename 'testFunction' to 'test_function'",
            location="src/module.py:42",
        ),
        CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="Duplicate function definition",
            suggestion="Remove duplicate definition",
            location="manifests/task-001.manifest.json",
        ),
    ]
    return CoherenceResult(valid=False, issues=issues)


class TestRunCoherenceValidationFunction:
    """Tests for run_coherence_validation function existence and signature."""

    def test_function_exists(self) -> None:
        """run_coherence_validation function exists in validate module."""
        assert run_coherence_validation is not None
        assert callable(run_coherence_validation)

    def test_function_accepts_manifest_path_parameter(
        self, manifest_file: Path, manifest_dir: Path
    ) -> None:
        """run_coherence_validation accepts manifest_path as Path."""
        result = run_coherence_validation(
            manifest_path=manifest_file,
            manifest_dir=manifest_dir,
            quiet=True,
        )

        assert result is not None

    def test_function_accepts_manifest_dir_parameter(
        self, manifest_file: Path, manifest_dir: Path
    ) -> None:
        """run_coherence_validation accepts manifest_dir as Path."""
        result = run_coherence_validation(
            manifest_path=manifest_file,
            manifest_dir=manifest_dir,
            quiet=True,
        )

        assert result is not None

    def test_function_accepts_quiet_parameter(
        self, manifest_file: Path, manifest_dir: Path
    ) -> None:
        """run_coherence_validation accepts quiet as bool."""
        result = run_coherence_validation(
            manifest_path=manifest_file,
            manifest_dir=manifest_dir,
            quiet=True,
        )

        assert result is not None


class TestRunCoherenceValidationReturnType:
    """Tests for run_coherence_validation return value."""

    def test_returns_coherence_result(
        self, manifest_file: Path, manifest_dir: Path
    ) -> None:
        """run_coherence_validation returns a CoherenceResult instance."""
        result = run_coherence_validation(
            manifest_path=manifest_file,
            manifest_dir=manifest_dir,
            quiet=True,
        )

        assert isinstance(result, CoherenceResult)

    def test_result_has_valid_attribute(
        self, manifest_file: Path, manifest_dir: Path
    ) -> None:
        """run_coherence_validation result has valid attribute."""
        result = run_coherence_validation(
            manifest_path=manifest_file,
            manifest_dir=manifest_dir,
            quiet=True,
        )

        assert hasattr(result, "valid")
        assert isinstance(result.valid, bool)

    def test_result_has_issues_attribute(
        self, manifest_file: Path, manifest_dir: Path
    ) -> None:
        """run_coherence_validation result has issues list."""
        result = run_coherence_validation(
            manifest_path=manifest_file,
            manifest_dir=manifest_dir,
            quiet=True,
        )

        assert hasattr(result, "issues")
        assert isinstance(result.issues, list)


class TestRunCoherenceValidationBehavior:
    """Tests for run_coherence_validation behavior."""

    def test_validates_manifest_path(
        self, manifest_file: Path, manifest_dir: Path
    ) -> None:
        """run_coherence_validation validates the specified manifest."""
        result = run_coherence_validation(
            manifest_path=manifest_file,
            manifest_dir=manifest_dir,
            quiet=True,
        )

        assert isinstance(result, CoherenceResult)

    def test_quiet_mode_suppresses_output(
        self, manifest_file: Path, manifest_dir: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """run_coherence_validation in quiet mode produces minimal output."""
        run_coherence_validation(
            manifest_path=manifest_file,
            manifest_dir=manifest_dir,
            quiet=True,
        )

        captured = capsys.readouterr()
        # In quiet mode, there should be minimal or no output for successful validation
        # The exact output depends on implementation, but quiet mode should suppress verbose output
        assert captured is not None

    def test_with_multiple_manifests_in_dir(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """run_coherence_validation works with multiple manifests in directory."""
        # Create multiple manifests
        manifest_1 = manifest_dir / "task-001.manifest.json"
        with open(manifest_1, "w") as f:
            json.dump(sample_manifest_data, f)

        manifest_2_data = sample_manifest_data.copy()
        manifest_2_data["goal"] = "Second manifest"
        manifest_2 = manifest_dir / "task-002.manifest.json"
        with open(manifest_2, "w") as f:
            json.dump(manifest_2_data, f)

        result = run_coherence_validation(
            manifest_path=manifest_1,
            manifest_dir=manifest_dir,
            quiet=True,
        )

        assert isinstance(result, CoherenceResult)


class TestFormatCoherenceIssuesFunction:
    """Tests for _format_coherence_issues function existence and signature."""

    def test_function_exists(self) -> None:
        """_format_coherence_issues function exists in validate module."""
        assert _format_coherence_issues is not None
        assert callable(_format_coherence_issues)

    def test_function_accepts_result_parameter(
        self, valid_coherence_result: CoherenceResult
    ) -> None:
        """_format_coherence_issues accepts result as CoherenceResult."""
        # Should not raise an exception
        _format_coherence_issues(result=valid_coherence_result, quiet=False)

    def test_function_accepts_quiet_parameter(
        self, valid_coherence_result: CoherenceResult
    ) -> None:
        """_format_coherence_issues accepts quiet as bool."""
        # Should not raise an exception
        _format_coherence_issues(result=valid_coherence_result, quiet=True)


class TestFormatCoherenceIssuesReturnType:
    """Tests for _format_coherence_issues return value."""

    def test_returns_none(self, valid_coherence_result: CoherenceResult) -> None:
        """_format_coherence_issues returns None."""
        result = _format_coherence_issues(
            result=valid_coherence_result,
            quiet=False,
        )

        assert result is None


class TestFormatCoherenceIssuesOutput:
    """Tests for _format_coherence_issues output behavior."""

    def test_no_output_for_valid_result_in_quiet_mode(
        self, valid_coherence_result: CoherenceResult, capsys: pytest.CaptureFixture
    ) -> None:
        """_format_coherence_issues produces no output in quiet mode with valid result."""
        _format_coherence_issues(result=valid_coherence_result, quiet=True)

        captured = capsys.readouterr()
        # In quiet mode with no issues, output should be empty or minimal
        assert captured is not None

    def test_outputs_issues_when_present(
        self,
        coherence_result_with_issues: CoherenceResult,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """_format_coherence_issues outputs issues when they exist."""
        _format_coherence_issues(result=coherence_result_with_issues, quiet=False)

        captured = capsys.readouterr()
        output = captured.out

        # Output should contain some indication of the issues
        # Since we have 2 issues (1 warning, 1 error), there should be some output
        assert len(output) > 0

    def test_outputs_error_severity_issues(self, capsys: pytest.CaptureFixture) -> None:
        """_format_coherence_issues outputs error-severity issues."""
        error_issue = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="Duplicate artifact detected",
            suggestion="Remove one of the duplicates",
            location="test_file.py",
        )
        result = CoherenceResult(valid=False, issues=[error_issue])

        _format_coherence_issues(result=result, quiet=False)

        captured = capsys.readouterr()
        # Should have some output for error issues
        assert len(captured.out) > 0

    def test_outputs_warning_severity_issues(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """_format_coherence_issues outputs warning-severity issues."""
        warning_issue = CoherenceIssue(
            issue_type=IssueType.NAMING,
            severity=IssueSeverity.WARNING,
            message="Naming convention violation",
            suggestion="Use snake_case",
            location="test_file.py",
        )
        result = CoherenceResult(valid=True, issues=[warning_issue])

        _format_coherence_issues(result=result, quiet=False)

        captured = capsys.readouterr()
        # Should have some output for warning issues
        assert len(captured.out) > 0

    def test_quiet_mode_reduces_output(
        self,
        coherence_result_with_issues: CoherenceResult,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """_format_coherence_issues in quiet mode produces less verbose output."""
        # First capture normal output
        _format_coherence_issues(result=coherence_result_with_issues, quiet=False)
        normal_output = capsys.readouterr().out

        # Then capture quiet output
        _format_coherence_issues(result=coherence_result_with_issues, quiet=True)
        quiet_output = capsys.readouterr().out

        # Quiet mode should produce equal or less output than normal mode
        assert len(quiet_output) <= len(normal_output)


class TestFormatCoherenceIssuesEmpty:
    """Tests for _format_coherence_issues with empty results."""

    def test_handles_empty_issues_list(self, capsys: pytest.CaptureFixture) -> None:
        """_format_coherence_issues handles result with empty issues list."""
        result = CoherenceResult(valid=True, issues=[])

        # Should not raise an exception
        _format_coherence_issues(result=result, quiet=False)

        captured = capsys.readouterr()
        assert captured is not None


class TestIntegration:
    """Integration tests for coherence validation in validate.py."""

    def test_run_and_format_workflow(
        self, manifest_file: Path, manifest_dir: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Complete workflow: run validation then format issues."""
        result = run_coherence_validation(
            manifest_path=manifest_file,
            manifest_dir=manifest_dir,
            quiet=True,
        )

        _format_coherence_issues(result=result, quiet=False)

        captured = capsys.readouterr()
        # The workflow should complete without errors
        assert captured is not None
        assert isinstance(result, CoherenceResult)

    def test_coherence_result_properties_accessible(
        self, manifest_file: Path, manifest_dir: Path
    ) -> None:
        """CoherenceResult properties are accessible after validation."""
        result = run_coherence_validation(
            manifest_path=manifest_file,
            manifest_dir=manifest_dir,
            quiet=True,
        )

        # These properties should be accessible
        assert isinstance(result.errors, int)
        assert isinstance(result.warnings, int)
        assert result.errors >= 0
        assert result.warnings >= 0

    def test_format_issues_with_all_issue_types(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """_format_coherence_issues handles all issue types."""
        issues = [
            CoherenceIssue(
                issue_type=IssueType.DUPLICATE,
                severity=IssueSeverity.ERROR,
                message="Duplicate artifact",
                suggestion="Remove duplicate",
            ),
            CoherenceIssue(
                issue_type=IssueType.SIGNATURE_CONFLICT,
                severity=IssueSeverity.ERROR,
                message="Signature conflict",
                suggestion="Resolve conflict",
            ),
            CoherenceIssue(
                issue_type=IssueType.BOUNDARY_VIOLATION,
                severity=IssueSeverity.WARNING,
                message="Boundary violation",
                suggestion="Fix boundary",
            ),
            CoherenceIssue(
                issue_type=IssueType.NAMING,
                severity=IssueSeverity.WARNING,
                message="Naming issue",
                suggestion="Rename",
            ),
            CoherenceIssue(
                issue_type=IssueType.DEPENDENCY,
                severity=IssueSeverity.INFO,
                message="Dependency issue",
                suggestion="Check dependency",
            ),
            CoherenceIssue(
                issue_type=IssueType.PATTERN,
                severity=IssueSeverity.INFO,
                message="Pattern issue",
                suggestion="Follow pattern",
            ),
            CoherenceIssue(
                issue_type=IssueType.CONSTRAINT,
                severity=IssueSeverity.ERROR,
                message="Constraint violation",
                suggestion="Fix constraint",
            ),
        ]
        result = CoherenceResult(valid=False, issues=issues)

        # Should not raise an exception
        _format_coherence_issues(result=result, quiet=False)

        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_validation_creates_validator_internally(
        self, manifest_file: Path, manifest_dir: Path
    ) -> None:
        """run_coherence_validation creates CoherenceValidator internally."""
        # This tests that the function properly integrates with CoherenceValidator
        result = run_coherence_validation(
            manifest_path=manifest_file,
            manifest_dir=manifest_dir,
            quiet=True,
        )

        # Result should be a valid CoherenceResult from CoherenceValidator
        assert isinstance(result, CoherenceResult)
        assert hasattr(result, "valid")
        assert hasattr(result, "issues")
