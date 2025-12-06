"""
Private test module for private helper function declared in task-076 manifest.

These tests verify the actual behavior of private helper function that is declared
in the manifest. While this is an internal helper, it's part of the declared API
and must be behaviorally validated.

Tests focus on meaningful behavior:
- How this helper enables public APIs to work correctly
- Edge cases and error conditions
- Real-world usage scenarios

Related task: task-076-typescript-artifact-type-validation
"""

import pytest

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.manifest_validator import (
        _validate_single_artifact,
        _parse_file,
        _collect_artifacts_from_ast,
        _ArtifactCollector,
    )
except ImportError as e:
    # In Red phase, these functions won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


class TestValidateSingleArtifact:
    """Test _validate_single_artifact private function behavior."""

    def test_validate_single_artifact_called_with_class_artifact(self, tmp_path):
        """Test that _validate_single_artifact is called with class artifact."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class User:
    def __init__(self, name):
        self.name = name
"""
        )

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        artifact = {"type": "class", "name": "User"}

        # Call _validate_single_artifact directly
        _validate_single_artifact(artifact, collector, "implementation")

        # Should not raise an error if User class exists
        assert "User" in collector.found_classes

    def test_validate_single_artifact_called_with_function_artifact(self, tmp_path):
        """Test that _validate_single_artifact is called with function artifact."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
def greet(name):
    return f"Hello {name}"
"""
        )

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        artifact = {"type": "function", "name": "greet"}

        # Call _validate_single_artifact directly
        _validate_single_artifact(artifact, collector, "implementation")

        # Should not raise an error if greet function exists
        assert "greet" in collector.found_functions

    def test_validate_single_artifact_called_with_interface_artifact(self, tmp_path):
        """Test that _validate_single_artifact is called with interface artifact."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
export interface User {
    id: string;
    name: string;
}
"""
        )

        validator = TypeScriptValidator()
        artifacts = validator.collect_artifacts(str(test_file), "implementation")

        # Create a collector with the found artifacts
        from maid_runner.validators.manifest_validator import _ArtifactCollector

        collector = _ArtifactCollector(validation_mode="implementation")
        collector.found_classes = artifacts.get("found_classes", set())
        collector.found_functions = artifacts.get("found_functions", {})

        artifact = {"type": "interface", "name": "User"}

        # Call _validate_single_artifact directly
        _validate_single_artifact(artifact, collector, "implementation")

        # Should not raise an error if User interface exists
        assert "User" in collector.found_classes

    def test_validate_single_artifact_called_with_type_alias_artifact(self, tmp_path):
        """Test that _validate_single_artifact is called with type alias artifact."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
export type UserID = string;
"""
        )

        validator = TypeScriptValidator()
        artifacts = validator.collect_artifacts(str(test_file), "implementation")

        collector = _ArtifactCollector(validation_mode="implementation")
        collector.found_classes = artifacts.get("found_classes", set())
        collector.found_class_bases = artifacts.get("found_class_bases", {})

        artifact = {"type": "type", "name": "UserID"}

        # Verify the artifact exists before validation
        assert "UserID" in collector.found_classes, "UserID should be in found_classes"

        # Call _validate_single_artifact directly - should not raise error
        _validate_single_artifact(artifact, collector, "implementation")

    def test_validate_single_artifact_called_with_enum_artifact(self, tmp_path):
        """Test that _validate_single_artifact is called with enum artifact."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
export enum Status {
    Active = 'active',
    Inactive = 'inactive'
}
"""
        )

        validator = TypeScriptValidator()
        artifacts = validator.collect_artifacts(str(test_file), "implementation")

        collector = _ArtifactCollector(validation_mode="implementation")
        collector.found_classes = artifacts.get("found_classes", set())
        collector.found_class_bases = artifacts.get("found_class_bases", {})

        artifact = {"type": "enum", "name": "Status"}

        # Verify the artifact exists before validation
        assert "Status" in collector.found_classes, "Status should be in found_classes"

        # Call _validate_single_artifact directly - should not raise error
        _validate_single_artifact(artifact, collector, "implementation")

    def test_validate_single_artifact_called_with_namespace_artifact(self, tmp_path):
        """Test that _validate_single_artifact is called with namespace artifact."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
export namespace Utils {
    export function formatDate(date: Date): string {
        return date.toISOString();
    }
}
"""
        )

        validator = TypeScriptValidator()
        artifacts = validator.collect_artifacts(str(test_file), "implementation")

        collector = _ArtifactCollector(validation_mode="implementation")
        collector.found_classes = artifacts.get("found_classes", set())
        collector.found_class_bases = artifacts.get("found_class_bases", {})

        artifact = {"type": "namespace", "name": "Utils"}

        # Verify the artifact exists before validation
        assert "Utils" in collector.found_classes, "Utils should be in found_classes"

        # Call _validate_single_artifact directly - should not raise error
        _validate_single_artifact(artifact, collector, "implementation")

    def test_validate_single_artifact_raises_error_when_missing(self, tmp_path):
        """Test that _validate_single_artifact raises error when artifact is missing."""
        from maid_runner.validators.manifest_validator import AlignmentError

        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class User:
    pass
"""
        )

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        artifact = {"type": "class", "name": "Product"}  # Doesn't exist

        # Call _validate_single_artifact directly - should raise error
        with pytest.raises(AlignmentError, match="Product"):
            _validate_single_artifact(artifact, collector, "implementation")

    def test_validate_single_artifact_with_behavioral_mode(self, tmp_path):
        """Test that _validate_single_artifact works in behavioral mode."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
from user import User

def test_user():
    user = User()
    return user
"""
        )

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "behavioral")

        artifact = {"type": "class", "name": "User"}

        # Call _validate_single_artifact directly with behavioral mode
        _validate_single_artifact(artifact, collector, "behavioral")

        # Should not raise an error if User class is used
        assert "User" in collector.used_classes
