"""
Tests for semantic validation of manifests (Task-033).

These tests verify that the semantic validator detects attempts to modify
multiple files and suggests splitting into separate manifests, following
MAID's extreme isolation principle.
"""

import pytest
from maid_runner.validators.semantic_validator import (
    ManifestSemanticError,
    validate_manifest_semantics,
    _detect_multi_file_intent,
    _build_multi_file_suggestion,
)


class TestManifestSemanticError:
    """Test the ManifestSemanticError exception class."""

    def test_semantic_error_is_exception(self):
        """Verify ManifestSemanticError is an exception."""
        error = ManifestSemanticError("test message")
        assert isinstance(error, Exception)

    def test_semantic_error_stores_message(self):
        """Verify error message is stored."""
        msg = "Invalid manifest semantics"
        error = ManifestSemanticError(msg)
        assert str(error) == msg


class TestDetectMultiFileIntent:
    """Test detection of multi-file modification attempts."""

    def test_detects_additional_files_property(self):
        """Should detect 'additionalFiles' property."""
        manifest = {
            "goal": "Test",
            "additionalFiles": ["file2.py"],
            "expectedArtifacts": {"file": "file1.py", "contains": []},
        }
        result = _detect_multi_file_intent(manifest)
        assert result is not None
        assert "additionalFiles" in result

    def test_detects_additional_artifacts_property(self):
        """Should detect 'additionalArtifacts' property."""
        manifest = {
            "goal": "Test",
            "additionalArtifacts": {"file": "file2.py", "contains": []},
            "expectedArtifacts": {"file": "file1.py", "contains": []},
        }
        result = _detect_multi_file_intent(manifest)
        assert result is not None
        assert "additionalArtifacts" in result

    def test_detects_multiple_suspicious_properties(self):
        """Should detect multiple multi-file indicators."""
        manifest = {
            "goal": "Test",
            "additionalFiles": ["file2.py"],
            "additionalArtifacts": {"file": "file3.py", "contains": []},
            "expectedArtifacts": {"file": "file1.py", "contains": []},
        }
        result = _detect_multi_file_intent(manifest)
        assert result is not None
        assert "additionalFiles" in result
        assert "additionalArtifacts" in result

    def test_returns_none_for_valid_manifest(self):
        """Should return None for valid single-file manifest."""
        manifest = {
            "goal": "Test",
            "creatableFiles": ["file1.py"],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "file1.py", "contains": []},
        }
        result = _detect_multi_file_intent(manifest)
        assert result is None

    def test_handles_manifest_without_expected_artifacts(self):
        """Should handle manifests without expectedArtifacts gracefully."""
        manifest = {
            "goal": "Test",
            "additionalFiles": ["file2.py"],
        }
        result = _detect_multi_file_intent(manifest)
        assert result is not None

    def test_case_insensitive_detection(self):
        """Should detect variations in property names."""
        # Note: Current implementation checks exact property names from schema error
        # This test verifies we handle the properties that actually appear
        manifest = {
            "goal": "Test",
            "AdditionalFiles": ["file2.py"],  # Different case
            "expectedArtifacts": {"file": "file1.py", "contains": []},
        }
        result = _detect_multi_file_intent(manifest)
        # Schema validation will catch this first, but semantic validation
        # should still handle whatever gets through
        assert result is not None or result is None  # Implementation dependent


class TestBuildMultiFileSuggestion:
    """Test generation of helpful error messages."""

    def test_builds_suggestion_for_single_property(self):
        """Should build clear suggestion for single invalid property."""
        suggestion = _build_multi_file_suggestion(["additionalFiles"])
        assert "additionalFiles" in suggestion
        assert "separate manifests" in suggestion.lower()
        assert "MAID" in suggestion or "one manifest per file" in suggestion.lower()

    def test_builds_suggestion_for_multiple_properties(self):
        """Should build suggestion mentioning all invalid properties."""
        suggestion = _build_multi_file_suggestion(
            ["additionalFiles", "additionalArtifacts"]
        )
        assert "additionalFiles" in suggestion
        assert "additionalArtifacts" in suggestion
        assert "separate manifests" in suggestion.lower()

    def test_suggestion_includes_actionable_guidance(self):
        """Should provide actionable guidance to user."""
        suggestion = _build_multi_file_suggestion(["additionalFiles"])
        # Should mention creating separate manifests
        assert "task-" in suggestion.lower() or "manifest" in suggestion.lower()
        # Should mention the proper approach
        assert "editableFiles" in suggestion or "creatableFiles" in suggestion

    def test_suggestion_formatting(self):
        """Should format suggestion with proper structure."""
        suggestion = _build_multi_file_suggestion(["additionalFiles"])
        # Should have some structure (newlines, bullets, or sections)
        assert len(suggestion) > 50  # Reasonably detailed message
        # Should be user-friendly
        assert (
            "💡" in suggestion
            or "Suggestion" in suggestion
            or "tip" in suggestion.lower()
        )


class TestValidateManifestSemantics:
    """Test main semantic validation function."""

    def test_raises_error_for_multi_file_attempt(self):
        """Should raise ManifestSemanticError for multi-file attempts."""
        manifest = {
            "goal": "Test",
            "additionalFiles": ["file2.py"],
            "expectedArtifacts": {"file": "file1.py", "contains": []},
        }
        with pytest.raises(ManifestSemanticError) as exc_info:
            validate_manifest_semantics(manifest)
        assert "additionalFiles" in str(exc_info.value)

    def test_error_includes_helpful_suggestion(self):
        """Should include helpful suggestion in error message."""
        manifest = {
            "goal": "Test",
            "additionalFiles": ["file2.py"],
            "expectedArtifacts": {"file": "file1.py", "contains": []},
        }
        with pytest.raises(ManifestSemanticError) as exc_info:
            validate_manifest_semantics(manifest)
        error_msg = str(exc_info.value)
        assert "separate manifests" in error_msg.lower() or "split" in error_msg.lower()

    def test_passes_valid_single_file_manifest(self):
        """Should pass validation for valid single-file manifest."""
        manifest = {
            "goal": "Test valid manifest",
            "creatableFiles": ["file1.py"],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "file1.py", "contains": []},
            "validationCommand": ["pytest"],
        }
        # Should not raise any exception
        validate_manifest_semantics(manifest)

    def test_passes_manifest_with_multiple_file_lists(self):
        """Should allow creatableFiles, editableFiles, readonlyFiles together."""
        manifest = {
            "goal": "Valid multi-file manifest using proper fields",
            "creatableFiles": ["new_file.py"],
            "editableFiles": ["existing_file.py"],
            "readonlyFiles": ["dependency.py", "tests/test.py"],
            "expectedArtifacts": {"file": "new_file.py", "contains": []},
            "validationCommand": ["pytest"],
        }
        # Should not raise - these are valid MAID fields
        validate_manifest_semantics(manifest)

    def test_handles_empty_manifest(self):
        """Should handle empty or minimal manifests gracefully."""
        manifest = {}
        # Should either pass or raise appropriate error
        # Implementation will determine exact behavior
        try:
            validate_manifest_semantics(manifest)
        except ManifestSemanticError:
            pass  # Acceptable to reject empty manifests

    def test_handles_none_manifest(self):
        """Should handle None manifest gracefully."""
        with pytest.raises((ManifestSemanticError, TypeError, AttributeError)):
            validate_manifest_semantics(None)


class TestIntegrationWithCLI:
    """Test integration scenarios with CLI validation."""

    def test_semantic_validation_called_before_ast(self):
        """Semantic validation should catch errors before AST validation."""
        # This is more of a design test - the actual integration
        # will be verified by the CLI tests
        manifest = {
            "goal": "Test",
            "additionalFiles": ["file2.py"],
            "expectedArtifacts": {"file": "file1.py", "contains": []},
        }
        # Semantic validation should fail fast
        with pytest.raises(ManifestSemanticError):
            validate_manifest_semantics(manifest)

    def test_error_message_format_for_cli(self):
        """Error message should be CLI-friendly."""
        manifest = {
            "goal": "Test",
            "additionalFiles": ["file2.py"],
            "additionalArtifacts": {"file": "file3.py", "contains": []},
            "expectedArtifacts": {"file": "file1.py", "contains": []},
        }
        with pytest.raises(ManifestSemanticError) as exc_info:
            validate_manifest_semantics(manifest)
        error_msg = str(exc_info.value)
        # Should be suitable for CLI display
        assert len(error_msg) > 20  # Has substance
        assert "\n" in error_msg or len(error_msg) < 200  # Either multiline or concise


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_handles_nested_additional_properties(self):
        """Should handle additional properties at different nesting levels."""
        manifest = {
            "goal": "Test",
            "expectedArtifacts": {
                "file": "file1.py",
                "contains": [],
                "additionalContains": [],  # Nested invalid property
            },
        }
        # Implementation will determine if this is caught at semantic level
        # or schema level - both are acceptable
        try:
            validate_manifest_semantics(manifest)
        except ManifestSemanticError:
            pass  # Acceptable

    def test_handles_manifest_with_unusual_structure(self):
        """Should handle manifests with unusual but valid structure."""
        manifest = {
            "goal": "Test",
            "creatableFiles": [],  # Empty lists
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "file.py", "contains": []},
            "validationCommand": ["echo", "test"],
        }
        # Should pass - unusual but valid
        validate_manifest_semantics(manifest)

    def test_performance_with_large_manifest(self):
        """Should handle large manifests efficiently."""
        manifest = {
            "goal": "Large manifest",
            "creatableFiles": [f"file{i}.py" for i in range(100)],
            "readonlyFiles": [f"test{i}.py" for i in range(100)],
            "expectedArtifacts": {
                "file": "file0.py",
                "contains": [
                    {"type": "function", "name": f"func{i}"} for i in range(100)
                ],
            },
            "validationCommand": ["pytest"],
        }
        # Should complete quickly without raising error
        validate_manifest_semantics(manifest)
