"""Behavioral tests for task-144: JSON output formatting for maid validate.

Tests the format_validation_json function that formats validation results
as JSON string compatible with maid-lsp expectations.
"""

import json
from typing import Any


from maid_runner.cli.validate import format_validation_json
from maid_runner.validation_result import ErrorSeverity, ValidationError


class TestFormatValidationJsonExists:
    """Test that format_validation_json exists and is callable."""

    def test_function_exists(self) -> None:
        """format_validation_json should be importable from validate module."""
        assert format_validation_json is not None

    def test_function_is_callable(self) -> None:
        """format_validation_json should be callable."""
        assert callable(format_validation_json)


class TestFormatValidationJsonReturnsValidJson:
    """Test that format_validation_json returns valid JSON strings."""

    def test_returns_valid_json_string(self) -> None:
        """Result should be parseable as valid JSON."""
        result = format_validation_json(
            success=True, errors=[], warnings=[], metadata={}
        )
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_returns_string_type(self) -> None:
        """Result should be a string."""
        result = format_validation_json(
            success=True, errors=[], warnings=[], metadata={}
        )
        assert isinstance(result, str)


class TestFormatValidationJsonEmptyCase:
    """Test format_validation_json with empty errors/warnings."""

    def test_empty_errors_warnings_returns_proper_structure(self) -> None:
        """Empty errors/warnings should return proper structure."""
        result = format_validation_json(
            success=True, errors=[], warnings=[], metadata={}
        )
        parsed = json.loads(result)

        assert parsed["success"] is True
        assert parsed["errors"] == []
        assert parsed["warnings"] == []
        assert parsed["metadata"] == {}

    def test_all_required_keys_present(self) -> None:
        """Result should have all required keys: success, errors, warnings, metadata."""
        result = format_validation_json(
            success=True, errors=[], warnings=[], metadata={}
        )
        parsed = json.loads(result)

        assert "success" in parsed
        assert "errors" in parsed
        assert "warnings" in parsed
        assert "metadata" in parsed


class TestFormatValidationJsonSingleError:
    """Test format_validation_json with a single error."""

    def test_single_error_includes_all_fields(self) -> None:
        """Single error should include code, message, file, line, column, severity."""
        error = ValidationError(
            code="E301",
            message="Missing artifact",
            file="path/to/file.py",
            line=42,
            column=1,
            severity=ErrorSeverity.ERROR,
        )
        result = format_validation_json(
            success=False, errors=[error], warnings=[], metadata={}
        )
        parsed = json.loads(result)

        assert len(parsed["errors"]) == 1
        err = parsed["errors"][0]
        assert err["code"] == "E301"
        assert err["message"] == "Missing artifact"
        assert err["file"] == "path/to/file.py"
        assert err["line"] == 42
        assert err["column"] == 1
        assert err["severity"] == "error"

    def test_error_severity_is_string(self) -> None:
        """Error severity should be serialized as string value."""
        error = ValidationError(
            code="E001",
            message="Test error",
            file="test.py",
            line=1,
            column=1,
            severity=ErrorSeverity.ERROR,
        )
        result = format_validation_json(
            success=False, errors=[error], warnings=[], metadata={}
        )
        parsed = json.loads(result)

        assert parsed["errors"][0]["severity"] == "error"


class TestFormatValidationJsonMultipleErrors:
    """Test format_validation_json with multiple errors."""

    def test_multiple_errors_serialized_as_array(self) -> None:
        """Multiple errors should be serialized as an array."""
        errors = [
            ValidationError(
                code="E001",
                message="First error",
                file="file1.py",
                line=10,
                column=1,
                severity=ErrorSeverity.ERROR,
            ),
            ValidationError(
                code="E002",
                message="Second error",
                file="file2.py",
                line=20,
                column=5,
                severity=ErrorSeverity.ERROR,
            ),
        ]
        result = format_validation_json(
            success=False, errors=errors, warnings=[], metadata={}
        )
        parsed = json.loads(result)

        assert len(parsed["errors"]) == 2
        assert parsed["errors"][0]["code"] == "E001"
        assert parsed["errors"][1]["code"] == "E002"

    def test_multiple_errors_preserves_order(self) -> None:
        """Multiple errors should preserve their order."""
        errors = [
            ValidationError(code=f"E{i:03d}", message=f"Error {i}") for i in range(5)
        ]
        result = format_validation_json(
            success=False, errors=errors, warnings=[], metadata={}
        )
        parsed = json.loads(result)

        for i, err in enumerate(parsed["errors"]):
            assert err["code"] == f"E{i:03d}"


class TestFormatValidationJsonWarnings:
    """Test format_validation_json with warnings."""

    def test_warnings_go_into_warnings_array(self) -> None:
        """Warnings should be placed in the warnings array."""
        warning = ValidationError(
            code="W001",
            message="Warning message",
            file="warn.py",
            line=5,
            column=1,
            severity=ErrorSeverity.WARNING,
        )
        result = format_validation_json(
            success=True, errors=[], warnings=[warning], metadata={}
        )
        parsed = json.loads(result)

        assert len(parsed["warnings"]) == 1
        assert parsed["warnings"][0]["code"] == "W001"
        assert parsed["warnings"][0]["severity"] == "warning"

    def test_multiple_warnings(self) -> None:
        """Multiple warnings should be serialized correctly."""
        warnings = [
            ValidationError(
                code="W001",
                message="First warning",
                severity=ErrorSeverity.WARNING,
            ),
            ValidationError(
                code="W002",
                message="Second warning",
                severity=ErrorSeverity.WARNING,
            ),
        ]
        result = format_validation_json(
            success=True, errors=[], warnings=warnings, metadata={}
        )
        parsed = json.loads(result)

        assert len(parsed["warnings"]) == 2


class TestFormatValidationJsonMetadata:
    """Test format_validation_json with metadata."""

    def test_metadata_dict_included_in_output(self) -> None:
        """Metadata dict should be included in output."""
        metadata = {
            "manifest_path": "manifests/task-001.manifest.json",
            "validation_mode": "implementation",
        }
        result = format_validation_json(
            success=True, errors=[], warnings=[], metadata=metadata
        )
        parsed = json.loads(result)

        assert parsed["metadata"]["manifest_path"] == "manifests/task-001.manifest.json"
        assert parsed["metadata"]["validation_mode"] == "implementation"

    def test_complex_metadata(self) -> None:
        """Complex metadata with nested values should be serialized."""
        metadata = {
            "manifest_path": "manifests/task-042.manifest.json",
            "validation_mode": "behavioral",
            "extra_info": "additional data",
        }
        result = format_validation_json(
            success=True, errors=[], warnings=[], metadata=metadata
        )
        parsed = json.loads(result)

        assert parsed["metadata"] == metadata


class TestFormatValidationJsonSuccessFlag:
    """Test format_validation_json success flag behavior."""

    def test_success_false_reflected_in_json(self) -> None:
        """success=False should be correctly reflected in JSON."""
        result = format_validation_json(
            success=False, errors=[], warnings=[], metadata={}
        )
        parsed = json.loads(result)

        assert parsed["success"] is False

    def test_success_true_reflected_in_json(self) -> None:
        """success=True should be correctly reflected in JSON."""
        result = format_validation_json(
            success=True, errors=[], warnings=[], metadata={}
        )
        parsed = json.loads(result)

        assert parsed["success"] is True


class TestFormatValidationJsonNullFields:
    """Test format_validation_json with None values in ValidationError."""

    def test_none_file_handled_gracefully(self) -> None:
        """ValidationError with None file should be handled gracefully."""
        error = ValidationError(
            code="E001",
            message="Error without file",
            file=None,
            line=None,
            column=None,
            severity=ErrorSeverity.ERROR,
        )
        result = format_validation_json(
            success=False, errors=[error], warnings=[], metadata={}
        )
        parsed = json.loads(result)

        # Should not raise an exception and should produce valid JSON
        assert len(parsed["errors"]) == 1
        assert parsed["errors"][0]["code"] == "E001"
        assert parsed["errors"][0]["message"] == "Error without file"
        # file, line, column should either be null/None or omitted
        # Based on ValidationError.to_dict(), they are omitted when None
        assert "file" not in parsed["errors"][0] or parsed["errors"][0]["file"] is None

    def test_partial_location_info(self) -> None:
        """ValidationError with only some location info should be handled."""
        error = ValidationError(
            code="E001",
            message="Partial location",
            file="test.py",
            line=10,
            column=None,
            severity=ErrorSeverity.ERROR,
        )
        result = format_validation_json(
            success=False, errors=[error], warnings=[], metadata={}
        )
        parsed = json.loads(result)

        err = parsed["errors"][0]
        assert err["file"] == "test.py"
        assert err["line"] == 10
        # column should be omitted or None
        assert "column" not in err or err["column"] is None


class TestFormatValidationJsonMaidLspFormat:
    """Test that output matches maid-lsp expected format exactly."""

    def test_full_output_matches_expected_format(self) -> None:
        """Full output should match maid-lsp expected format."""
        error = ValidationError(
            code="E301",
            message="Missing function definition",
            file="path/to/module.py",
            line=42,
            column=1,
            severity=ErrorSeverity.ERROR,
        )
        warning = ValidationError(
            code="W101",
            message="Consider adding docstring",
            file="path/to/module.py",
            line=50,
            column=1,
            severity=ErrorSeverity.WARNING,
        )
        metadata = {
            "manifest_path": "manifests/task-001.manifest.json",
            "validation_mode": "implementation",
        }

        result = format_validation_json(
            success=False, errors=[error], warnings=[warning], metadata=metadata
        )
        parsed = json.loads(result)

        # Verify structure matches expected format:
        # {
        #   "success": true/false,
        #   "errors": [{"code": "...", "message": "...", "file": "...",
        #               "line": ..., "column": ..., "severity": "error"}],
        #   "warnings": [...],
        #   "metadata": {"manifest_path": "...", "validation_mode": "..."}
        # }
        assert isinstance(parsed["success"], bool)
        assert isinstance(parsed["errors"], list)
        assert isinstance(parsed["warnings"], list)
        assert isinstance(parsed["metadata"], dict)

        # Verify error structure
        err = parsed["errors"][0]
        assert "code" in err
        assert "message" in err
        assert "severity" in err
        assert err["severity"] in ["error", "warning"]

        # Verify warning structure
        warn = parsed["warnings"][0]
        assert "code" in warn
        assert "message" in warn
        assert warn["severity"] == "warning"

    def test_json_keys_are_strings(self) -> None:
        """All JSON keys should be strings (standard JSON format)."""
        result = format_validation_json(
            success=True,
            errors=[ValidationError(code="E001", message="Test")],
            warnings=[],
            metadata={"key": "value"},
        )
        parsed = json.loads(result)

        def check_keys(obj: Any, path: str = "") -> None:
            if isinstance(obj, dict):
                for key in obj.keys():
                    assert isinstance(key, str), f"Key at {path} is not a string"
                    check_keys(obj[key], f"{path}.{key}")
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    check_keys(item, f"{path}[{i}]")

        check_keys(parsed)


class TestRunValidationJsonOutputParameter:
    """Test that run_validation accepts json_output parameter."""

    def test_run_validation_has_json_output_parameter(self) -> None:
        """run_validation should accept json_output parameter."""
        import inspect
        from maid_runner.cli.validate import run_validation

        sig = inspect.signature(run_validation)
        params = list(sig.parameters.keys())
        assert "json_output" in params

    def test_run_validation_json_output_default_is_false(self) -> None:
        """run_validation json_output parameter should default to False."""
        import inspect
        from maid_runner.cli.validate import run_validation

        sig = inspect.signature(run_validation)
        json_output_param = sig.parameters["json_output"]
        assert json_output_param.default is False

    def test_run_validation_is_callable(self) -> None:
        """run_validation should be callable."""
        from maid_runner.cli.validate import run_validation

        assert callable(run_validation)

    def test_run_validation_accepts_json_output_kwarg(self, tmp_path) -> None:
        """run_validation should accept json_output keyword argument without error."""
        import pytest
        from maid_runner.cli.validate import run_validation

        # Create a minimal valid manifest for testing
        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text(
            '{"goal": "test", "taskType": "create", "creatableFiles": [], '
            '"editableFiles": [], "readonlyFiles": [], '
            '"expectedArtifacts": {"file": "test.py", "contains": []}, '
            '"validationCommand": ["echo", "ok"]}'
        )

        # Call run_validation with json_output parameter
        # It will exit because the manifest references a non-existent file,
        # but the important thing is it accepts the parameter
        with pytest.raises(SystemExit):
            run_validation(
                manifest_path=str(manifest_path),
                validation_mode="implementation",
                json_output=True,
            )


class TestRunValidationWithJsonOutputIntegration:
    """Integration tests for _run_validation_with_json_output function."""

    def test_valid_manifest_outputs_success_json(self, tmp_path, capsys) -> None:
        """Valid manifest should output JSON with success=true."""
        import pytest
        from maid_runner.cli.validate import run_validation

        # Create a valid manifest and implementation file
        impl_file = tmp_path / "module.py"
        impl_file.write_text("def hello():\n    pass\n")

        manifest_path = tmp_path / "test.manifest.json"
        manifest_content = {
            "goal": "test goal",
            "taskType": "create",
            "creatableFiles": [str(impl_file)],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": str(impl_file),
                "contains": [{"type": "function", "name": "hello"}],
            },
            "validationCommand": ["echo", "ok"],
        }
        manifest_path.write_text(json.dumps(manifest_content))

        with pytest.raises(SystemExit) as exc_info:
            run_validation(
                manifest_path=str(manifest_path),
                validation_mode="implementation",
                json_output=True,
            )

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["success"] is True
        assert parsed["errors"] == []

    def test_missing_manifest_outputs_error_json(self, tmp_path, capsys) -> None:
        """Missing manifest file should output JSON with E001 error."""
        import pytest
        from maid_runner.cli.validate import run_validation

        nonexistent_path = tmp_path / "nonexistent.manifest.json"

        with pytest.raises(SystemExit) as exc_info:
            run_validation(
                manifest_path=str(nonexistent_path),
                validation_mode="implementation",
                json_output=True,
            )

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["success"] is False
        assert len(parsed["errors"]) == 1
        assert parsed["errors"][0]["code"] == "E001"
        assert "not found" in parsed["errors"][0]["message"].lower()

    def test_invalid_json_manifest_outputs_error(self, tmp_path, capsys) -> None:
        """Invalid JSON in manifest should output JSON with E001 error."""
        import pytest
        from maid_runner.cli.validate import run_validation

        manifest_path = tmp_path / "invalid.manifest.json"
        manifest_path.write_text("{ invalid json }")

        with pytest.raises(SystemExit) as exc_info:
            run_validation(
                manifest_path=str(manifest_path),
                validation_mode="implementation",
                json_output=True,
            )

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["success"] is False
        assert len(parsed["errors"]) >= 1
        assert parsed["errors"][0]["code"] == "E001"

    def test_schema_validation_error_outputs_json(self, tmp_path, capsys) -> None:
        """Schema validation failure should output JSON with E002 error."""
        import pytest
        from maid_runner.cli.validate import run_validation

        manifest_path = tmp_path / "schema_invalid.manifest.json"
        # Missing required fields like 'goal'
        manifest_content = {"taskType": "create"}
        manifest_path.write_text(json.dumps(manifest_content))

        with pytest.raises(SystemExit) as exc_info:
            run_validation(
                manifest_path=str(manifest_path),
                validation_mode="implementation",
                json_output=True,
            )

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["success"] is False
        assert len(parsed["errors"]) >= 1
        assert parsed["errors"][0]["code"] == "E002"

    def test_implementation_error_outputs_json(self, tmp_path, capsys) -> None:
        """Missing implementation artifact should output JSON with error."""
        import pytest
        from maid_runner.cli.validate import run_validation

        # Create impl file without the expected function
        impl_file = tmp_path / "module.py"
        impl_file.write_text("# empty file\n")

        manifest_path = tmp_path / "test.manifest.json"
        manifest_content = {
            "goal": "test goal",
            "taskType": "create",
            "creatableFiles": [str(impl_file)],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": str(impl_file),
                "contains": [{"type": "function", "name": "missing_function"}],
            },
            "validationCommand": ["echo", "ok"],
        }
        manifest_path.write_text(json.dumps(manifest_content))

        with pytest.raises(SystemExit) as exc_info:
            run_validation(
                manifest_path=str(manifest_path),
                validation_mode="implementation",
                json_output=True,
            )

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["success"] is False
        assert len(parsed["errors"]) >= 1

    def test_json_output_includes_metadata(self, tmp_path, capsys) -> None:
        """JSON output should include metadata with manifest_path and validation_mode."""
        import pytest
        from maid_runner.cli.validate import run_validation

        impl_file = tmp_path / "module.py"
        impl_file.write_text("def hello():\n    pass\n")

        manifest_path = tmp_path / "test.manifest.json"
        manifest_content = {
            "goal": "test goal",
            "taskType": "create",
            "creatableFiles": [str(impl_file)],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": str(impl_file),
                "contains": [{"type": "function", "name": "hello"}],
            },
            "validationCommand": ["echo", "ok"],
        }
        manifest_path.write_text(json.dumps(manifest_content))

        with pytest.raises(SystemExit):
            run_validation(
                manifest_path=str(manifest_path),
                validation_mode="implementation",
                json_output=True,
            )

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert "metadata" in parsed
        assert parsed["metadata"]["manifest_path"] == str(manifest_path)
        assert parsed["metadata"]["validation_mode"] == "implementation"

    def test_json_output_exit_code_zero_on_success(self, tmp_path) -> None:
        """Successful validation with json_output should exit with code 0."""
        import pytest
        from maid_runner.cli.validate import run_validation

        impl_file = tmp_path / "module.py"
        impl_file.write_text("def hello():\n    pass\n")

        manifest_path = tmp_path / "test.manifest.json"
        manifest_content = {
            "goal": "test goal",
            "taskType": "create",
            "creatableFiles": [str(impl_file)],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": str(impl_file),
                "contains": [{"type": "function", "name": "hello"}],
            },
            "validationCommand": ["echo", "ok"],
        }
        manifest_path.write_text(json.dumps(manifest_content))

        with pytest.raises(SystemExit) as exc_info:
            run_validation(
                manifest_path=str(manifest_path),
                validation_mode="implementation",
                json_output=True,
            )

        assert exc_info.value.code == 0

    def test_json_output_exit_code_one_on_failure(self, tmp_path) -> None:
        """Failed validation with json_output should exit with code 1."""
        import pytest
        from maid_runner.cli.validate import run_validation

        nonexistent_path = tmp_path / "nonexistent.manifest.json"

        with pytest.raises(SystemExit) as exc_info:
            run_validation(
                manifest_path=str(nonexistent_path),
                validation_mode="implementation",
                json_output=True,
            )

        assert exc_info.value.code == 1
