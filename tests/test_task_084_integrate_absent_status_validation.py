"""
Behavioral tests for Task-084: Integrate absent status validation into validation flow.

Tests verify that:
1. validate_manifest_semantics calls _validate_file_status_semantic_rules
2. validate_with_ast calls _validate_absent_file and handles absent files
3. End-to-end integration tests show full validation flow works
"""

import pytest
from maid_runner.validators.semantic_validator import (
    validate_manifest_semantics,
    ManifestSemanticError,
)
from maid_runner.validators.manifest_validator import (
    validate_with_ast,
    AlignmentError,
)


class TestSemanticValidatorIntegration:
    """Test that validate_manifest_semantics integrates _validate_file_status_semantic_rules."""

    def test_semantic_validator_rejects_creatable_with_absent(self):
        """Test that validate_manifest_semantics rejects creatableFiles with status: absent."""
        manifest_data = {
            "goal": "Invalid manifest",
            "creatableFiles": ["new_file.py"],
            "expectedArtifacts": {
                "file": "new_file.py",
                "status": "absent",  # Invalid: creating a file that should be absent
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # Should raise ManifestSemanticError (wrapping AlignmentError)
        with pytest.raises(ManifestSemanticError) as exc_info:
            validate_manifest_semantics(manifest_data)

        error_msg = str(exc_info.value)
        assert "creatableFiles" in error_msg.lower() or "creatable" in error_msg.lower()
        assert "absent" in error_msg.lower()

    def test_semantic_validator_rejects_absent_without_task_type(self):
        """Test that validate_manifest_semantics rejects status: absent without taskType: refactor."""
        manifest_data = {
            "goal": "Invalid manifest",
            "taskType": "edit",  # Invalid: should be "refactor"
            "supersedes": ["task-001.manifest.json"],
            "editableFiles": ["old_file.py"],
            "expectedArtifacts": {
                "file": "old_file.py",
                "status": "absent",
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # Should raise ManifestSemanticError
        with pytest.raises(ManifestSemanticError) as exc_info:
            validate_manifest_semantics(manifest_data)

        error_msg = str(exc_info.value)
        assert "refactor" in error_msg.lower()

    def test_semantic_validator_rejects_absent_without_supersedes(self):
        """Test that validate_manifest_semantics rejects status: absent without supersedes."""
        manifest_data = {
            "goal": "Invalid manifest",
            "taskType": "refactor",
            "editableFiles": ["old_file.py"],
            "expectedArtifacts": {
                "file": "old_file.py",
                "status": "absent",
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # Should raise ManifestSemanticError
        with pytest.raises(ManifestSemanticError) as exc_info:
            validate_manifest_semantics(manifest_data)

        error_msg = str(exc_info.value)
        assert "supersedes" in error_msg.lower()

    def test_semantic_validator_accepts_valid_absent_manifest(self):
        """Test that validate_manifest_semantics accepts valid absent status manifest."""
        manifest_data = {
            "goal": "Delete old file",
            "taskType": "refactor",
            "supersedes": ["manifests/task-001.manifest.json"],
            "editableFiles": ["old_file.py"],
            "expectedArtifacts": {
                "file": "old_file.py",
                "status": "absent",
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # Should not raise any exception
        validate_manifest_semantics(manifest_data)


class TestValidateWithAstIntegration:
    """Test that validate_with_ast integrates _validate_absent_file."""

    def test_validate_with_ast_rejects_existing_absent_file(self, tmp_path):
        """Test that validate_with_ast rejects files marked absent that still exist."""
        # Create a file that should NOT exist
        existing_file = tmp_path / "should_be_deleted.py"
        existing_file.write_text("# This file should not exist\n")

        manifest_data = {
            "goal": "Test absent file validation",
            "expectedArtifacts": {
                "file": str(existing_file),
                "status": "absent",
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # Should raise AlignmentError because file exists
        with pytest.raises(AlignmentError) as exc_info:
            validate_with_ast(manifest_data, str(existing_file))

        error_msg = str(exc_info.value)
        assert "absent" in error_msg.lower()

    def test_validate_with_ast_accepts_non_existing_absent_file(self, tmp_path):
        """Test that validate_with_ast accepts files marked absent that don't exist."""
        # Create a path to a file that doesn't exist
        non_existent_file = tmp_path / "deleted_file.py"

        manifest_data = {
            "goal": "Test absent file validation",
            "expectedArtifacts": {
                "file": str(non_existent_file),
                "status": "absent",
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # Should not raise - file is correctly absent
        # The function should return early without trying to parse
        validate_with_ast(manifest_data, str(non_existent_file))

    def test_validate_with_ast_skips_parsing_for_absent_files(self, tmp_path):
        """Test that validate_with_ast returns early for absent files without parsing."""
        # Create a path to a file that doesn't exist
        non_existent_file = tmp_path / "deleted_module.py"

        manifest_data = {
            "goal": "Test absent file early return",
            "expectedArtifacts": {
                "file": str(non_existent_file),
                "status": "absent",
                "contains": [],  # Empty is expected
            },
            "validationCommand": ["pytest"],
        }

        # Should complete without error - no parsing attempted
        validate_with_ast(manifest_data, str(non_existent_file))

    def test_validate_with_ast_normal_validation_for_present_files(self, tmp_path):
        """Test that validate_with_ast performs normal validation for present files."""
        # Create a Python file with a function
        present_file = tmp_path / "normal_file.py"
        present_file.write_text("def hello(): pass\n")

        manifest_data = {
            "goal": "Test normal validation",
            "expectedArtifacts": {
                "file": str(present_file),
                "status": "present",  # Or omit status field
                "contains": [{"type": "function", "name": "hello"}],
            },
            "validationCommand": ["pytest"],
        }

        # Should perform normal validation - no errors expected
        validate_with_ast(manifest_data, str(present_file))


class TestEndToEndIntegration:
    """End-to-end integration tests for the full validation flow."""

    def test_full_validation_flow_with_absent_status(self, tmp_path):
        """Test complete validation flow with status: absent."""
        # Step 1: Semantic validation
        manifest_data = {
            "goal": "Delete obsolete module",
            "taskType": "refactor",
            "supersedes": ["manifests/task-050.manifest.json"],
            "editableFiles": ["obsolete_module.py"],
            "expectedArtifacts": {
                "file": "obsolete_module.py",
                "status": "absent",
                "contains": [],
            },
            "validationCommand": ["pytest", "tests/test_deletion.py", "-v"],
        }

        # Semantic validation should pass
        validate_manifest_semantics(manifest_data)

        # Step 2: File validation (file doesn't exist - should pass)
        non_existent_path = "obsolete_module.py"
        validate_with_ast(manifest_data, non_existent_path)

    def test_full_validation_flow_rejects_invalid_absent_manifest(self):
        """Test that full validation flow rejects invalid absent manifests."""
        # Missing supersedes field
        invalid_manifest = {
            "goal": "Invalid deletion",
            "taskType": "refactor",
            # Missing supersedes!
            "editableFiles": ["old_file.py"],
            "expectedArtifacts": {
                "file": "old_file.py",
                "status": "absent",
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # Semantic validation should fail
        with pytest.raises(ManifestSemanticError):
            validate_manifest_semantics(invalid_manifest)

    def test_backward_compatibility_with_present_status(self, tmp_path):
        """Test that existing manifests without status field still work."""
        # Create a Python file
        test_file = tmp_path / "existing.py"
        test_file.write_text("class MyClass: pass\n")

        manifest_data = {
            "goal": "Test backward compatibility",
            "expectedArtifacts": {
                "file": str(test_file),
                # No status field - defaults to "present"
                "contains": [{"type": "class", "name": "MyClass"}],
            },
            "validationCommand": ["pytest"],
        }

        # Both semantic and file validation should pass
        validate_manifest_semantics(manifest_data)
        validate_with_ast(manifest_data, str(test_file))
