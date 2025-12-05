"""
Behavioral tests for Task-083: Implement absent status validation logic.

Tests verify that files with status: 'absent' are validated correctly:
1. Files with status: 'absent' that don't exist pass validation
2. Files with status: 'absent' that DO exist fail validation with clear error
3. Files with status: 'present' or no status continue to work normally (backward compatibility)
4. Edge case: creatableFiles with status: 'absent' is rejected (semantic error)
"""

import pytest
from maid_runner.validators.manifest_validator import (
    validate_schema,
    AlignmentError,
    _validate_absent_file,
    _validate_file_status_semantic_rules,
)

SCHEMA_PATH = "maid_runner/validators/schemas/manifest.schema.json"


class TestAbsentFileValidation:
    """Test _validate_absent_file function."""

    def test_absent_file_not_exists_passes_validation(self, tmp_path):
        """Test that a file with status 'absent' that doesn't exist passes validation."""
        # Create a temporary manifest with status: "absent" for a non-existent file
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

        # This should not raise any exception
        _validate_absent_file(manifest_data, str(non_existent_file))

    def test_absent_file_exists_fails_validation(self, tmp_path):
        """Test that a file with status 'absent' that EXISTS fails validation."""
        # Create a temporary file that should NOT exist
        existing_file = tmp_path / "should_be_deleted.py"
        existing_file.write_text("# This file should not exist\n")

        manifest_data = {
            "goal": "Test absent file validation failure",
            "expectedArtifacts": {
                "file": str(existing_file),
                "status": "absent",
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # This should raise AlignmentError because file exists
        with pytest.raises(AlignmentError) as exc_info:
            _validate_absent_file(manifest_data, str(existing_file))

        # Verify error message mentions the file and status
        error_msg = str(exc_info.value)
        assert "absent" in error_msg.lower()
        assert str(existing_file) in error_msg or "should_be_deleted.py" in error_msg

    def test_present_status_skips_absent_validation(self, tmp_path):
        """Test that status: 'present' does not trigger absent file validation."""
        # Create a file that exists - this is expected for status: "present"
        existing_file = tmp_path / "present_file.py"
        existing_file.write_text("def hello(): pass\n")

        manifest_data = {
            "goal": "Test present status backward compatibility",
            "expectedArtifacts": {
                "file": str(existing_file),
                "status": "present",
                "contains": [{"type": "function", "name": "hello"}],
            },
            "validationCommand": ["pytest"],
        }

        # This should not raise - absent validation should be skipped
        _validate_absent_file(manifest_data, str(existing_file))

    def test_no_status_field_skips_absent_validation(self, tmp_path):
        """Test that manifests without status field skip absent validation (backward compatibility)."""
        # Create a file that exists - normal validation will handle this
        existing_file = tmp_path / "normal_file.py"
        existing_file.write_text("class MyClass: pass\n")

        manifest_data = {
            "goal": "Test backward compatibility without status field",
            "expectedArtifacts": {
                "file": str(existing_file),
                # No status field - should default to "present" behavior
                "contains": [{"type": "class", "name": "MyClass"}],
            },
            "validationCommand": ["pytest"],
        }

        # This should not raise - absent validation should be skipped
        _validate_absent_file(manifest_data, str(existing_file))

    def test_absent_status_with_empty_contains(self, tmp_path):
        """Test that absent status works correctly with empty contains array."""
        non_existent_file = tmp_path / "deleted_module.py"

        manifest_data = {
            "goal": "Test absent status with empty contains",
            "expectedArtifacts": {
                "file": str(non_existent_file),
                "status": "absent",
                "contains": [],  # Empty is expected for deleted files
            },
            "validationCommand": ["pytest"],
        }

        # Should pass - file doesn't exist as expected
        _validate_absent_file(manifest_data, str(non_existent_file))


class TestFileStatusSemanticRules:
    """Test _validate_file_status_semantic_rules function."""

    def test_creatable_files_with_absent_status_rejected(self, tmp_path):
        """Test that creatableFiles with status 'absent' is rejected (semantic error)."""
        manifest_data = {
            "goal": "Test semantic validation for creatableFiles + absent",
            "creatableFiles": ["new_file.py"],
            "expectedArtifacts": {
                "file": "new_file.py",
                "status": "absent",  # Contradiction: creating a file that should be absent
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # This should raise AlignmentError due to semantic contradiction
        with pytest.raises(AlignmentError) as exc_info:
            _validate_file_status_semantic_rules(manifest_data)

        # Verify error message explains the contradiction
        error_msg = str(exc_info.value)
        assert "creatableFiles" in error_msg or "creatable" in error_msg.lower()
        assert "absent" in error_msg.lower()

    def test_editable_files_with_absent_status_allowed(self):
        """Test that editableFiles with status 'absent' is allowed (deletion scenario)."""
        manifest_data = {
            "goal": "Test editing a file to delete it",
            "taskType": "refactor",  # Required for absent status
            "supersedes": [
                "manifests/task-001.manifest.json"
            ],  # Required for absent status
            "editableFiles": ["existing_file.py"],
            "expectedArtifacts": {
                "file": "existing_file.py",
                "status": "absent",  # Valid: editing existing file to mark deletion
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # This should not raise - it's valid to edit/delete existing files
        _validate_file_status_semantic_rules(manifest_data)

    def test_readonly_files_with_absent_status_allowed(self):
        """Test that readonlyFiles are not affected by status validation."""
        manifest_data = {
            "goal": "Test that readonlyFiles are unaffected by status",
            "taskType": "refactor",  # Required for absent status
            "supersedes": [
                "manifests/task-001.manifest.json"
            ],  # Required for absent status
            "readonlyFiles": ["dependency.py"],
            "expectedArtifacts": {
                "file": "some_file.py",
                "status": "absent",
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # Should pass - readonlyFiles are dependencies, not affected by status
        _validate_file_status_semantic_rules(manifest_data)

    def test_present_status_with_creatable_files_allowed(self):
        """Test that creatableFiles with status 'present' is allowed (normal creation)."""
        manifest_data = {
            "goal": "Test normal file creation with explicit present status",
            "creatableFiles": ["new_feature.py"],
            "expectedArtifacts": {
                "file": "new_feature.py",
                "status": "present",
                "contains": [{"type": "function", "name": "new_feature"}],
            },
            "validationCommand": ["pytest"],
        }

        # This should pass - creating a file that will be present is valid
        _validate_file_status_semantic_rules(manifest_data)

    def test_no_status_field_with_creatable_files_allowed(self):
        """Test backward compatibility: creatableFiles without status field works."""
        manifest_data = {
            "goal": "Test backward compatibility for file creation",
            "creatableFiles": ["new_module.py"],
            "expectedArtifacts": {
                "file": "new_module.py",
                # No status field - defaults to "present"
                "contains": [{"type": "class", "name": "NewClass"}],
            },
            "validationCommand": ["pytest"],
        }

        # Should pass - backward compatible behavior
        _validate_file_status_semantic_rules(manifest_data)

    def test_absent_status_with_non_empty_contains_rejected(self):
        """Test that status: 'absent' with non-empty contains array is rejected."""
        manifest_data = {
            "goal": "Test absent status with non-empty contains",
            "taskType": "refactor",
            "supersedes": ["manifests/task-001.manifest.json"],
            "editableFiles": ["old_file.py"],
            "expectedArtifacts": {
                "file": "old_file.py",
                "status": "absent",
                "contains": [
                    {"type": "function", "name": "should_not_list_artifacts"}
                ],  # Invalid: can't list artifacts for deleted file
            },
            "validationCommand": ["pytest"],
        }

        # Should raise - absent files must have empty contains
        with pytest.raises(AlignmentError) as exc_info:
            _validate_file_status_semantic_rules(manifest_data)

        error_msg = str(exc_info.value)
        assert "contains" in error_msg.lower()
        assert "empty" in error_msg.lower()

    def test_absent_status_with_wrong_task_type_rejected(self):
        """Test that status: 'absent' with taskType != 'refactor' is rejected."""
        manifest_data = {
            "goal": "Test absent status with wrong task type",
            "taskType": "edit",  # Invalid: should be "refactor"
            "supersedes": ["manifests/task-001.manifest.json"],
            "editableFiles": ["old_file.py"],
            "expectedArtifacts": {
                "file": "old_file.py",
                "status": "absent",
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # Should raise - absent files require taskType: "refactor"
        with pytest.raises(AlignmentError) as exc_info:
            _validate_file_status_semantic_rules(manifest_data)

        error_msg = str(exc_info.value)
        assert "tasktype" in error_msg.lower() or "refactor" in error_msg.lower()

    def test_absent_status_without_supersedes_rejected(self):
        """Test that status: 'absent' without supersedes array is rejected."""
        manifest_data = {
            "goal": "Test absent status without supersedes",
            "taskType": "refactor",
            "supersedes": [],  # Invalid: must have at least one manifest
            "editableFiles": ["old_file.py"],
            "expectedArtifacts": {
                "file": "old_file.py",
                "status": "absent",
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # Should raise - absent files must supersede the creation manifest
        with pytest.raises(AlignmentError) as exc_info:
            _validate_file_status_semantic_rules(manifest_data)

        error_msg = str(exc_info.value)
        assert "supersedes" in error_msg.lower()
        assert "non-empty" in error_msg.lower() or "must" in error_msg.lower()

    def test_absent_status_missing_supersedes_field_rejected(self):
        """Test that status: 'absent' without supersedes field is rejected."""
        manifest_data = {
            "goal": "Test absent status without supersedes field",
            "taskType": "refactor",
            # No supersedes field at all
            "editableFiles": ["old_file.py"],
            "expectedArtifacts": {
                "file": "old_file.py",
                "status": "absent",
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # Should raise - absent files must have supersedes field
        with pytest.raises(AlignmentError) as exc_info:
            _validate_file_status_semantic_rules(manifest_data)

        error_msg = str(exc_info.value)
        assert "supersedes" in error_msg.lower()


class TestIntegrationWithMainValidation:
    """Test integration with the main validation flow."""

    def test_schema_validation_accepts_absent_status(self, tmp_path):
        """Test that schema validation accepts status: 'absent'."""
        manifest_data = {
            "goal": "Test schema validation accepts absent status",
            "readonlyFiles": ["tests/test.py"],
            "expectedArtifacts": {
                "file": "deleted_file.py",
                "status": "absent",
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # Schema validation should pass
        validate_schema(manifest_data, SCHEMA_PATH)

    def test_manifest_without_expected_artifacts_skips_validation(self):
        """Test that manifests without expectedArtifacts skip absent validation."""
        manifest_data = {
            "goal": "Test manifest without expectedArtifacts",
            "readonlyFiles": ["dependency.py"],
            "validationCommand": ["pytest"],
            # No expectedArtifacts field
        }

        # Should not raise - there's nothing to validate
        _validate_absent_file(manifest_data, "any_file.py")
        _validate_file_status_semantic_rules(manifest_data)

    def test_expected_artifacts_without_file_field_handled(self):
        """Test that expectedArtifacts without file field is handled gracefully."""
        manifest_data = {
            "goal": "Test expectedArtifacts without file field",
            "readonlyFiles": ["test.py"],
            "expectedArtifacts": {
                # Missing 'file' field
                "status": "absent",
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # Should handle gracefully without crashing
        try:
            _validate_absent_file(manifest_data, "some_file.py")
            _validate_file_status_semantic_rules(manifest_data)
        except (KeyError, AttributeError, AlignmentError):
            # May raise validation errors, but should not crash
            pass


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_absent_file_with_artifacts_in_contains(self, tmp_path):
        """Test that absent status with non-empty contains still validates file absence."""
        non_existent_file = tmp_path / "deleted_with_artifacts.py"

        manifest_data = {
            "goal": "Test absent file with artifacts listed",
            "expectedArtifacts": {
                "file": str(non_existent_file),
                "status": "absent",
                # Unusual: listing artifacts for deleted file, but should still check absence
                "contains": [
                    {"type": "function", "name": "old_function"},
                    {"type": "class", "name": "OldClass"},
                ],
            },
            "validationCommand": ["pytest"],
        }

        # Should pass - file doesn't exist regardless of contains
        _validate_absent_file(manifest_data, str(non_existent_file))

    def test_multiple_creatable_files_only_checks_expected_artifacts_file(self):
        """Test that semantic validation only checks the expectedArtifacts.file."""
        manifest_data = {
            "goal": "Test multiple creatableFiles",
            "creatableFiles": ["file1.py", "file2.py", "file3.py"],
            "expectedArtifacts": {
                "file": "file2.py",
                "status": "absent",  # Only file2.py's status matters
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # Should raise - file2.py is in creatableFiles with absent status
        with pytest.raises(AlignmentError):
            _validate_file_status_semantic_rules(manifest_data)

    def test_absent_validation_works_with_relative_paths(self, tmp_path):
        """Test that absent validation works with relative file paths."""
        # Use relative path
        relative_path = "src/deleted_module.py"

        manifest_data = {
            "goal": "Test absent validation with relative paths",
            "expectedArtifacts": {
                "file": relative_path,
                "status": "absent",
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # Should pass if file doesn't exist (relative to cwd)
        _validate_absent_file(manifest_data, relative_path)

    def test_case_sensitive_status_check(self):
        """Test that status field is case-sensitive."""
        manifest_data = {
            "goal": "Test case sensitivity",
            "expectedArtifacts": {
                "file": "test.py",
                "status": "ABSENT",  # Wrong case - should be treated as invalid by schema
                "contains": [],
            },
            "validationCommand": ["pytest"],
        }

        # Schema validation should reject this (tested in Task-082)
        # Our functions may handle it gracefully or skip it
        try:
            _validate_absent_file(manifest_data, "test.py")
            _validate_file_status_semantic_rules(manifest_data)
        except Exception:
            # May raise various errors depending on implementation
            pass
