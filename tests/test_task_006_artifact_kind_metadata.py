"""
Behavioral tests for Task-006: Artifact Kind Metadata functionality.
These tests USE the should_skip_behavioral_validation function to verify it works correctly.
Tests verify that type-only artifacts (TypedDict, type aliases) are properly identified
and skipped during behavioral validation, while runtime artifacts are validated.
"""

import sys
from pathlib import Path

import pytest

# Add parent directory to path to enable imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import private test module for private artifact behavioral validation fix
from tests._test_private_artifact_behavioral_validation import (  # noqa: F401
    TestPrivateArtifactsInManifests,
    TestPrivateArtifactsNotInManifests,
)

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.manifest_validator import (
        should_skip_behavioral_validation,
    )
except ImportError as e:
    # In Red phase, this function won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


class TestShouldSkipBehavioralValidation:
    """Test the should_skip_behavioral_validation function with various artifact types."""

    def test_skip_type_only_artifacts(self):
        """Test that artifacts explicitly marked as type-only are skipped."""
        # Test explicit type-only artifact
        type_artifact = {"type": "class", "name": "UserData", "artifactKind": "type"}

        # USE the function - should return True for type-only artifacts
        result = should_skip_behavioral_validation(type_artifact)
        assert isinstance(result, bool)  # Validate return type
        assert result is True

    def test_dont_skip_runtime_artifacts(self):
        """Test that runtime artifacts are NOT skipped."""
        # Test explicit runtime artifact
        runtime_artifact = {
            "type": "class",
            "name": "UserService",
            "artifactKind": "runtime",
        }

        # USE the function - should return False for runtime artifacts
        result = should_skip_behavioral_validation(runtime_artifact)
        assert isinstance(result, bool)  # Validate return type
        assert result is False

    def test_backward_compatibility_no_artifact_kind(self):
        """Test backward compatibility - no artifactKind defaults to runtime."""
        # Test artifact with no artifactKind (old manifest format)
        old_artifact = {
            "type": "function",
            "name": "process_data",
            # No artifactKind field - should default to runtime
        }

        # USE the function - should return False (runtime) for backward compatibility
        result = should_skip_behavioral_validation(old_artifact)
        assert isinstance(result, bool)  # Validate return type
        assert result is False

    def test_auto_detect_typeddict_classes(self):
        """Test auto-detection of TypedDict classes as type-only."""
        # Test class that inherits from TypedDict
        typeddict_artifact = {
            "type": "class",
            "name": "PersonDict",
            "bases": ["TypedDict"],
        }

        # USE the function - should return True for TypedDict classes
        result = should_skip_behavioral_validation(typeddict_artifact)
        assert isinstance(result, bool)  # Validate return type
        assert result is True

    def test_auto_detect_qualified_typeddict(self):
        """Test auto-detection of qualified TypedDict references."""
        # Test class that inherits from typing.TypedDict
        qualified_typeddict = {
            "type": "class",
            "name": "ConfigDict",
            "bases": ["typing.TypedDict"],
        }

        # USE the function - should return True for qualified TypedDict
        result = should_skip_behavioral_validation(qualified_typeddict)
        assert result is True

    def test_auto_detect_multiple_bases_with_typeddict(self):
        """Test auto-detection when TypedDict is one of multiple bases."""
        # Test class with multiple bases including TypedDict
        multi_base_artifact = {
            "type": "class",
            "name": "ExtendedDict",
            "bases": ["SomeOtherBase", "TypedDict", "AnotherBase"],
        }

        # USE the function - should return True when TypedDict is in bases
        result = should_skip_behavioral_validation(multi_base_artifact)
        assert result is True

    def test_regular_class_not_skipped(self):
        """Test that regular classes (not TypedDict) are not skipped."""
        # Test regular class
        regular_class = {
            "type": "class",
            "name": "UserService",
            "bases": ["BaseService"],
        }

        # USE the function - should return False for regular classes
        result = should_skip_behavioral_validation(regular_class)
        assert result is False

    def test_function_artifacts_not_auto_detected(self):
        """Test that function artifacts are not auto-detected as type-only."""
        # Test function artifact (no auto-detection applies)
        function_artifact = {"type": "function", "name": "process_user"}

        # USE the function - should return False for functions without explicit type kind
        result = should_skip_behavioral_validation(function_artifact)
        assert result is False

    def test_attribute_artifacts(self):
        """Test that attribute artifacts follow explicit artifactKind."""
        # Test type-only attribute (like a type alias)
        type_attribute = {"type": "attribute", "name": "UserId", "artifactKind": "type"}

        # USE the function - should return True for type-only attributes
        result = should_skip_behavioral_validation(type_attribute)
        assert result is True

        # Test runtime attribute
        runtime_attribute = {
            "type": "attribute",
            "name": "user_count",
            "artifactKind": "runtime",
        }

        # USE the function - should return False for runtime attributes
        result = should_skip_behavioral_validation(runtime_attribute)
        assert result is False


class TestMixedScenarios:
    """Test mixed scenarios combining type and runtime artifacts."""

    def test_explicit_override_auto_detection(self):
        """Test that explicit artifactKind overrides auto-detection."""
        # TypedDict class but explicitly marked as runtime
        override_artifact = {
            "type": "class",
            "name": "RuntimeTypedDict",
            "bases": ["TypedDict"],
            "artifactKind": "runtime",  # Explicit override
        }

        # USE the function - explicit artifactKind should override auto-detection
        result = should_skip_behavioral_validation(override_artifact)
        assert result is False

    def test_case_sensitivity_typeddict_detection(self):
        """Test that TypedDict detection is case-sensitive."""
        # Test lowercase "typeddict" - should not be auto-detected
        case_artifact = {
            "type": "class",
            "name": "CaseTest",
            "bases": ["typeddict"],  # lowercase
        }

        # USE the function - should return False (case-sensitive)
        result = should_skip_behavioral_validation(case_artifact)
        assert result is False

    def test_empty_bases_list(self):
        """Test artifacts with empty bases list."""
        empty_bases_artifact = {"type": "class", "name": "NoBaseClass", "bases": []}

        # USE the function - should return False for empty bases
        result = should_skip_behavioral_validation(empty_bases_artifact)
        assert result is False

    def test_missing_bases_field(self):
        """Test artifacts without bases field at all."""
        no_bases_artifact = {
            "type": "class",
            "name": "NoBases",
            # No bases field
        }

        # USE the function - should return False when no bases field
        result = should_skip_behavioral_validation(no_bases_artifact)
        assert result is False

    def test_none_bases_field(self):
        """Test artifacts with None bases field."""
        none_bases_artifact = {"type": "class", "name": "NoneBases", "bases": None}

        # USE the function - should handle None bases gracefully
        result = should_skip_behavioral_validation(none_bases_artifact)
        assert result is False


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_invalid_artifact_kind_values(self):
        """Test handling of invalid artifactKind values."""
        # Test invalid artifactKind value
        invalid_artifact = {
            "type": "function",
            "name": "test_func",
            "artifactKind": "invalid_value",
        }

        # USE the function - should handle invalid values gracefully (default to runtime)
        result = should_skip_behavioral_validation(invalid_artifact)
        assert result is False

    def test_empty_artifact_dict(self):
        """Test handling of empty artifact dictionary."""
        empty_artifact = {}

        # USE the function - should handle empty dict gracefully
        result = should_skip_behavioral_validation(empty_artifact)
        assert result is False

    def test_none_artifact(self):
        """Test handling of None artifact."""
        # USE the function - should handle None gracefully
        result = should_skip_behavioral_validation(None)
        assert isinstance(result, bool)  # Validate return type
        assert result is False

    def test_artifact_without_type_field(self):
        """Test artifact missing the type field."""
        no_type_artifact = {"name": "something", "artifactKind": "type"}

        # USE the function - should work even without type field
        result = should_skip_behavioral_validation(no_type_artifact)
        assert result is True

    def test_nested_qualified_typeddict(self):
        """Test more complex qualified TypedDict scenarios."""
        nested_qualified = {
            "type": "class",
            "name": "ComplexDict",
            "bases": ["typing_extensions.TypedDict"],
        }

        # USE the function - should detect TypedDict in qualified names
        result = should_skip_behavioral_validation(nested_qualified)
        assert result is True


class TestIntegrationWithValidation:
    """Test integration scenarios with the broader validation system."""

    def test_type_only_artifacts_skipped_in_behavioral_validation(self):
        """Test that type-only artifacts are properly skipped in behavioral validation context."""
        # This test demonstrates the intended use case:
        # When behavioral validation encounters type-only artifacts, they should be skipped

        type_artifacts = [
            {"type": "class", "name": "UserType", "artifactKind": "type"},
            {"type": "class", "name": "ConfigDict", "bases": ["TypedDict"]},
            {"type": "attribute", "name": "UserId", "artifactKind": "type"},
        ]

        runtime_artifacts = [
            {"type": "function", "name": "process_user"},
            {"type": "class", "name": "UserService"},
        ]

        # USE the function on each artifact
        for artifact in type_artifacts:
            result = should_skip_behavioral_validation(artifact)
            assert result is True, f"Type artifact {artifact['name']} should be skipped"

        for artifact in runtime_artifacts:
            result = should_skip_behavioral_validation(artifact)
            assert (
                result is False
            ), f"Runtime artifact {artifact['name']} should not be skipped"

    def test_manifest_chain_scenario(self):
        """Test behavior with typical manifest chain scenarios."""
        # Simulate artifacts from a manifest chain where some are type definitions
        chain_artifacts = [
            # Task 1: Define types
            {
                "type": "class",
                "name": "PersonData",
                "bases": ["TypedDict"],
                "artifactKind": "type",  # Explicit override for clarity
            },
            # Task 2: Define runtime implementation
            {"type": "class", "name": "PersonService"},
            {
                "type": "function",
                "name": "create_person",
                "parameters": [
                    {"name": "data", "type": "PersonData"}
                ],  # References type
            },
        ]

        # USE the function on the mixed artifact chain
        type_result = should_skip_behavioral_validation(chain_artifacts[0])
        service_result = should_skip_behavioral_validation(chain_artifacts[1])
        function_result = should_skip_behavioral_validation(chain_artifacts[2])

        assert type_result is True  # PersonData is type-only
        assert service_result is False  # PersonService is runtime
        assert function_result is False  # create_person is runtime

    def test_common_typing_patterns(self):
        """Test common typing patterns that should be detected as type-only."""
        typing_patterns = [
            # Various TypedDict patterns
            {"type": "class", "name": "Dict1", "bases": ["TypedDict"]},
            {"type": "class", "name": "Dict2", "bases": ["typing.TypedDict"]},
            {
                "type": "class",
                "name": "Dict3",
                "bases": ["typing_extensions.TypedDict"],
            },
            # Explicit type annotations
            {"type": "attribute", "name": "TypeAlias", "artifactKind": "type"},
            {"type": "class", "name": "Protocol", "artifactKind": "type"},
        ]

        # USE the function on common typing patterns
        for pattern in typing_patterns:
            result = should_skip_behavioral_validation(pattern)
            assert result is True, f"Pattern {pattern} should be skipped as type-only"
