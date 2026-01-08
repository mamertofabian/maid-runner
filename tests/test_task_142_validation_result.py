"""Behavioral tests for validation result types (Task-142).

Tests the ErrorSeverity enum, ValidationError dataclass, and ValidationResult dataclass
that provide structured validation output for maid-lsp compatibility.
"""

import json

from maid_runner.validation_result import (
    ErrorSeverity,
    ValidationError,
    ValidationResult,
)


class TestErrorSeverity:
    """Tests for ErrorSeverity enum."""

    def test_error_severity_has_error_value(self) -> None:
        """ErrorSeverity enum has ERROR member."""
        assert hasattr(ErrorSeverity, "ERROR")
        assert ErrorSeverity.ERROR is not None

    def test_error_severity_has_warning_value(self) -> None:
        """ErrorSeverity enum has WARNING member."""
        assert hasattr(ErrorSeverity, "WARNING")
        assert ErrorSeverity.WARNING is not None

    def test_error_severity_error_string_value(self) -> None:
        """ErrorSeverity.ERROR has value 'error'."""
        assert ErrorSeverity.ERROR.value == "error"

    def test_error_severity_warning_string_value(self) -> None:
        """ErrorSeverity.WARNING has value 'warning'."""
        assert ErrorSeverity.WARNING.value == "warning"


class TestValidationError:
    """Tests for ValidationError dataclass."""

    def test_construction_with_required_fields(self) -> None:
        """ValidationError can be constructed with only code and message."""
        error = ValidationError(code="TEST001", message="Test error message")

        assert error.code == "TEST001"
        assert error.message == "Test error message"

    def test_default_severity_is_error(self) -> None:
        """ValidationError defaults severity to ERROR."""
        error = ValidationError(code="TEST001", message="Test error")

        assert error.severity == ErrorSeverity.ERROR

    def test_default_file_is_none(self) -> None:
        """ValidationError defaults file to None."""
        error = ValidationError(code="TEST001", message="Test error")

        assert error.file is None

    def test_default_line_is_none(self) -> None:
        """ValidationError defaults line to None."""
        error = ValidationError(code="TEST001", message="Test error")

        assert error.line is None

    def test_default_column_is_none(self) -> None:
        """ValidationError defaults column to None."""
        error = ValidationError(code="TEST001", message="Test error")

        assert error.column is None

    def test_construction_with_all_fields(self) -> None:
        """ValidationError accepts all fields including optional ones."""
        error = ValidationError(
            code="TEST001",
            message="Test error",
            file="test_file.py",
            line=42,
            column=10,
            severity=ErrorSeverity.WARNING,
        )

        assert error.code == "TEST001"
        assert error.message == "Test error"
        assert error.file == "test_file.py"
        assert error.line == 42
        assert error.column == 10
        assert error.severity == ErrorSeverity.WARNING

    def test_to_dict_returns_dict(self) -> None:
        """ValidationError.to_dict() returns a dictionary."""
        error = ValidationError(code="TEST001", message="Test error")

        result = error.to_dict()

        assert isinstance(result, dict)

    def test_to_dict_contains_code(self) -> None:
        """ValidationError.to_dict() includes code field."""
        error = ValidationError(code="TEST001", message="Test error")

        result = error.to_dict()

        assert result["code"] == "TEST001"

    def test_to_dict_contains_message(self) -> None:
        """ValidationError.to_dict() includes message field."""
        error = ValidationError(code="TEST001", message="Test error message")

        result = error.to_dict()

        assert result["message"] == "Test error message"

    def test_to_dict_contains_severity(self) -> None:
        """ValidationError.to_dict() includes severity field as string."""
        error = ValidationError(code="TEST001", message="Test error")

        result = error.to_dict()

        assert result["severity"] == "error"

    def test_to_dict_includes_file_when_set(self) -> None:
        """ValidationError.to_dict() includes file when provided."""
        error = ValidationError(
            code="TEST001", message="Test error", file="test_file.py"
        )

        result = error.to_dict()

        assert result["file"] == "test_file.py"

    def test_to_dict_includes_line_when_set(self) -> None:
        """ValidationError.to_dict() includes line when provided."""
        error = ValidationError(code="TEST001", message="Test error", line=42)

        result = error.to_dict()

        assert result["line"] == 42

    def test_to_dict_includes_column_when_set(self) -> None:
        """ValidationError.to_dict() includes column when provided."""
        error = ValidationError(code="TEST001", message="Test error", column=10)

        result = error.to_dict()

        assert result["column"] == 10

    def test_to_dict_excludes_file_when_none(self) -> None:
        """ValidationError.to_dict() excludes file when None."""
        error = ValidationError(code="TEST001", message="Test error")

        result = error.to_dict()

        assert "file" not in result

    def test_to_dict_excludes_line_when_none(self) -> None:
        """ValidationError.to_dict() excludes line when None."""
        error = ValidationError(code="TEST001", message="Test error")

        result = error.to_dict()

        assert "line" not in result

    def test_to_dict_excludes_column_when_none(self) -> None:
        """ValidationError.to_dict() excludes column when None."""
        error = ValidationError(code="TEST001", message="Test error")

        result = error.to_dict()

        assert "column" not in result


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_default_success_is_true(self) -> None:
        """ValidationResult defaults success to True."""
        result = ValidationResult()

        assert result.success is True

    def test_default_errors_is_empty_list(self) -> None:
        """ValidationResult defaults errors to empty list."""
        result = ValidationResult()

        assert result.errors == []

    def test_default_warnings_is_empty_list(self) -> None:
        """ValidationResult defaults warnings to empty list."""
        result = ValidationResult()

        assert result.warnings == []

    def test_default_metadata_is_empty_dict(self) -> None:
        """ValidationResult defaults metadata to empty dict."""
        result = ValidationResult()

        assert result.metadata == {}

    def test_add_error_with_error_severity_sets_success_false(self) -> None:
        """add_error() with ERROR severity sets success to False."""
        result = ValidationResult()
        error = ValidationError(
            code="TEST001", message="Test error", severity=ErrorSeverity.ERROR
        )

        result.add_error(error)

        assert result.success is False

    def test_add_error_with_error_severity_adds_to_errors_list(self) -> None:
        """add_error() with ERROR severity adds error to errors list."""
        result = ValidationResult()
        error = ValidationError(
            code="TEST001", message="Test error", severity=ErrorSeverity.ERROR
        )

        result.add_error(error)

        assert error in result.errors

    def test_add_error_with_warning_severity_keeps_success_true(self) -> None:
        """add_error() with WARNING severity keeps success True."""
        result = ValidationResult()
        warning = ValidationError(
            code="WARN001", message="Test warning", severity=ErrorSeverity.WARNING
        )

        result.add_error(warning)

        assert result.success is True

    def test_add_error_with_warning_severity_adds_to_warnings_list(self) -> None:
        """add_error() with WARNING severity adds to warnings list."""
        result = ValidationResult()
        warning = ValidationError(
            code="WARN001", message="Test warning", severity=ErrorSeverity.WARNING
        )

        result.add_error(warning)

        assert warning in result.warnings

    def test_add_multiple_errors(self) -> None:
        """add_error() can add multiple errors."""
        result = ValidationResult()
        error1 = ValidationError(code="TEST001", message="Error 1")
        error2 = ValidationError(code="TEST002", message="Error 2")

        result.add_error(error1)
        result.add_error(error2)

        assert len(result.errors) == 2
        assert error1 in result.errors
        assert error2 in result.errors

    def test_add_mixed_errors_and_warnings(self) -> None:
        """add_error() correctly separates errors and warnings."""
        result = ValidationResult()
        error = ValidationError(
            code="ERR001", message="Error", severity=ErrorSeverity.ERROR
        )
        warning = ValidationError(
            code="WARN001", message="Warning", severity=ErrorSeverity.WARNING
        )

        result.add_error(error)
        result.add_error(warning)

        assert len(result.errors) == 1
        assert len(result.warnings) == 1
        assert error in result.errors
        assert warning in result.warnings

    def test_to_dict_returns_dict(self) -> None:
        """ValidationResult.to_dict() returns a dictionary."""
        result = ValidationResult()

        output = result.to_dict()

        assert isinstance(output, dict)

    def test_to_dict_contains_success(self) -> None:
        """ValidationResult.to_dict() includes success field."""
        result = ValidationResult()

        output = result.to_dict()

        assert "success" in output
        assert output["success"] is True

    def test_to_dict_contains_errors_array(self) -> None:
        """ValidationResult.to_dict() includes errors as array."""
        result = ValidationResult()
        error = ValidationError(code="TEST001", message="Error")
        result.add_error(error)

        output = result.to_dict()

        assert "errors" in output
        assert isinstance(output["errors"], list)
        assert len(output["errors"]) == 1

    def test_to_dict_contains_warnings_array(self) -> None:
        """ValidationResult.to_dict() includes warnings as array."""
        result = ValidationResult()
        warning = ValidationError(
            code="WARN001", message="Warning", severity=ErrorSeverity.WARNING
        )
        result.add_error(warning)

        output = result.to_dict()

        assert "warnings" in output
        assert isinstance(output["warnings"], list)
        assert len(output["warnings"]) == 1

    def test_to_dict_contains_metadata(self) -> None:
        """ValidationResult.to_dict() includes metadata."""
        result = ValidationResult()
        result.metadata["manifest"] = "task-142.manifest.json"

        output = result.to_dict()

        assert "metadata" in output
        assert output["metadata"]["manifest"] == "task-142.manifest.json"

    def test_to_dict_serializes_error_objects(self) -> None:
        """ValidationResult.to_dict() converts error objects to dicts."""
        result = ValidationResult()
        error = ValidationError(code="TEST001", message="Error", file="test.py")
        result.add_error(error)

        output = result.to_dict()

        error_dict = output["errors"][0]
        assert error_dict["code"] == "TEST001"
        assert error_dict["message"] == "Error"
        assert error_dict["file"] == "test.py"

    def test_to_json_returns_string(self) -> None:
        """ValidationResult.to_json() returns a string."""
        result = ValidationResult()

        output = result.to_json()

        assert isinstance(output, str)

    def test_to_json_returns_valid_json(self) -> None:
        """ValidationResult.to_json() returns parseable JSON."""
        result = ValidationResult()
        error = ValidationError(code="TEST001", message="Error")
        result.add_error(error)

        output = result.to_json()
        parsed = json.loads(output)

        assert parsed["success"] is False
        assert len(parsed["errors"]) == 1

    def test_to_json_with_indent_returns_formatted_json(self) -> None:
        """ValidationResult.to_json(indent=2) returns formatted JSON."""
        result = ValidationResult()

        output = result.to_json(indent=2)

        # Formatted JSON has newlines
        assert "\n" in output
        # Check indentation
        lines = output.split("\n")
        # At least one line should be indented with 2 spaces
        assert any(line.startswith("  ") for line in lines)

    def test_to_json_without_indent_returns_compact_json(self) -> None:
        """ValidationResult.to_json() without indent returns compact JSON."""
        result = ValidationResult()
        result.metadata["key"] = "value"

        output = result.to_json()

        # Compact JSON has no newlines (or minimal newlines)
        # json.dumps without indent produces single-line output
        assert output.count("\n") == 0

    def test_lsp_compatible_format(self) -> None:
        """ValidationResult.to_dict() produces maid-lsp compatible format."""
        result = ValidationResult()
        error = ValidationError(
            code="MAID001",
            message="Missing artifact",
            file="src/module.py",
            line=10,
            column=5,
            severity=ErrorSeverity.ERROR,
        )
        result.add_error(error)
        result.metadata["manifest"] = "task-142.manifest.json"
        result.metadata["validationMode"] = "implementation"

        output = result.to_dict()

        # Check LSP-compatible structure
        assert output["success"] is False
        assert isinstance(output["errors"], list)
        assert isinstance(output["warnings"], list)
        assert isinstance(output["metadata"], dict)

        # Check error format
        error_dict = output["errors"][0]
        assert error_dict["code"] == "MAID001"
        assert error_dict["message"] == "Missing artifact"
        assert error_dict["file"] == "src/module.py"
        assert error_dict["line"] == 10
        assert error_dict["column"] == 5
        assert error_dict["severity"] == "error"
