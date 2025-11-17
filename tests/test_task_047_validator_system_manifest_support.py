"""
Behavioral tests for task-047: Update validator to handle system manifests.

Tests verify that:
1. _is_system_manifest() correctly identifies system manifests
2. Validator functions handle systemArtifacts gracefully
3. No errors when validating system manifest schemas
4. System manifests are distinguished from regular manifests
"""

import json
import pytest
from pathlib import Path
from jsonschema import validate

from maid_runner.validators.manifest_validator import (
    _is_system_manifest,
    _validate_system_artifacts_structure,
    validate_schema,
    AlignmentError,
)


@pytest.fixture
def manifest_schema():
    """Load the manifest schema."""
    schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
    with open(schema_path) as f:
        return json.load(f)


class TestIsSystemManifest:
    """Test suite for _is_system_manifest() function."""

    def test_function_exists(self):
        """Verify _is_system_manifest function exists."""
        assert callable(_is_system_manifest)

    def test_identifies_system_manifest_with_systemArtifacts(self):
        """Verify function returns True for manifests with systemArtifacts."""
        system_manifest = {
            "version": "1",
            "goal": "System snapshot",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [
                {
                    "file": "test.py",
                    "contains": [{"type": "function", "name": "test_func"}],
                }
            ],
            "validationCommands": [["pytest", "tests/"]],
        }

        assert _is_system_manifest(system_manifest) is True

    def test_identifies_regular_manifest_with_expectedArtifacts(self):
        """Verify function returns False for manifests with expectedArtifacts."""
        regular_manifest = {
            "version": "1",
            "goal": "Regular task",
            "taskType": "edit",
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [{"type": "function", "name": "test_func"}],
            },
            "validationCommand": ["pytest", "tests/"],
        }

        assert _is_system_manifest(regular_manifest) is False

    def test_handles_manifest_with_neither_field(self):
        """Verify function handles manifests missing both artifact fields."""
        # This would fail schema validation but shouldn't crash the function
        incomplete_manifest = {
            "version": "1",
            "goal": "Incomplete manifest",
            "taskType": "edit",
            "readonlyFiles": [],
            "validationCommand": ["pytest", "tests/"],
        }

        # Should return False (not a system manifest)
        assert _is_system_manifest(incomplete_manifest) is False

    def test_handles_empty_manifest(self):
        """Verify function handles empty manifests."""
        assert _is_system_manifest({}) is False

    def test_taskType_alone_not_sufficient(self):
        """Verify taskType alone doesn't determine system manifest."""
        # A manifest with system-snapshot taskType but no systemArtifacts
        # is malformed, but the function should check for systemArtifacts
        manifest_with_wrong_artifacts = {
            "version": "1",
            "goal": "Wrong combination",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "expectedArtifacts": {  # Wrong! Should be systemArtifacts
                "file": "test.py",
                "contains": [],
            },
            "validationCommand": ["pytest", "tests/"],
        }

        # Should return False because it has expectedArtifacts, not systemArtifacts
        assert _is_system_manifest(manifest_with_wrong_artifacts) is False


class TestValidateSystemArtifactsStructure:
    """Test suite for _validate_system_artifacts_structure() function."""

    def test_function_exists(self):
        """Verify _validate_system_artifacts_structure function exists."""
        assert callable(_validate_system_artifacts_structure)

    def test_validates_correct_structure(self):
        """Verify function passes for correctly structured systemArtifacts."""
        valid_manifest = {
            "systemArtifacts": [
                {
                    "file": "module/file1.py",
                    "contains": [
                        {"type": "function", "name": "func1"},
                        {"type": "class", "name": "Class1"},
                    ],
                },
                {
                    "file": "module/file2.py",
                    "contains": [{"type": "function", "name": "func2"}],
                },
            ]
        }

        # Should not raise
        _validate_system_artifacts_structure(valid_manifest)

    def test_validates_empty_systemArtifacts(self):
        """Verify function passes for empty systemArtifacts array."""
        manifest = {"systemArtifacts": []}

        # Should not raise
        _validate_system_artifacts_structure(manifest)

    def test_raises_if_systemArtifacts_not_array(self):
        """Verify function raises error if systemArtifacts is not an array."""
        invalid_manifest = {"systemArtifacts": "not an array"}

        with pytest.raises(AlignmentError, match="systemArtifacts must be an array"):
            _validate_system_artifacts_structure(invalid_manifest)

    def test_raises_if_artifact_block_missing_file(self):
        """Verify function raises error if artifact block missing 'file' field."""
        invalid_manifest = {
            "systemArtifacts": [
                {
                    # Missing 'file' field
                    "contains": [{"type": "function", "name": "func"}]
                }
            ]
        }

        with pytest.raises(AlignmentError, match="missing required 'file' field"):
            _validate_system_artifacts_structure(invalid_manifest)

    def test_raises_if_artifact_block_missing_contains(self):
        """Verify function raises error if artifact block missing 'contains' field."""
        invalid_manifest = {
            "systemArtifacts": [
                {
                    "file": "test.py"
                    # Missing 'contains' field
                }
            ]
        }

        with pytest.raises(AlignmentError, match="missing required 'contains' field"):
            _validate_system_artifacts_structure(invalid_manifest)

    def test_raises_if_contains_not_array(self):
        """Verify function raises error if 'contains' is not an array."""
        invalid_manifest = {
            "systemArtifacts": [{"file": "test.py", "contains": "not an array"}]
        }

        with pytest.raises(AlignmentError, match="'contains' field must be an array"):
            _validate_system_artifacts_structure(invalid_manifest)

    def test_raises_if_artifact_missing_type(self):
        """Verify function raises error if artifact missing 'type' field."""
        invalid_manifest = {
            "systemArtifacts": [
                {
                    "file": "test.py",
                    "contains": [
                        {
                            # Missing 'type' field
                            "name": "func"
                        }
                    ],
                }
            ]
        }

        with pytest.raises(AlignmentError, match="missing required 'type' field"):
            _validate_system_artifacts_structure(invalid_manifest)

    def test_raises_if_artifact_missing_name(self):
        """Verify function raises error if artifact missing 'name' field."""
        invalid_manifest = {
            "systemArtifacts": [
                {
                    "file": "test.py",
                    "contains": [
                        {
                            "type": "function"
                            # Missing 'name' field
                        }
                    ],
                }
            ]
        }

        with pytest.raises(AlignmentError, match="missing required 'name' field"):
            _validate_system_artifacts_structure(invalid_manifest)

    def test_validates_complex_nested_structures(self):
        """Verify function validates complex artifact structures."""
        complex_manifest = {
            "systemArtifacts": [
                {
                    "file": "complex.py",
                    "contains": [
                        {
                            "type": "class",
                            "name": "ComplexClass",
                            "bases": ["BaseClass", "Mixin"],
                        },
                        {
                            "type": "function",
                            "name": "complex_func",
                            "args": [
                                {"name": "arg1", "type": "str"},
                                {"name": "arg2", "type": "int", "default": "0"},
                            ],
                            "returns": "Dict[str, Any]",
                            "description": "Complex function",
                        },
                        {
                            "type": "attribute",
                            "name": "MODULE_CONSTANT",
                            "description": "A constant",
                        },
                    ],
                }
            ]
        }

        # Should not raise
        _validate_system_artifacts_structure(complex_manifest)

    def test_skips_validation_for_non_system_manifests(self):
        """Verify function skips validation for non-system manifests."""
        regular_manifest = {"expectedArtifacts": {"file": "test.py", "contains": []}}

        # Should not raise (skips validation for non-system manifests)
        _validate_system_artifacts_structure(regular_manifest)

    def test_provides_helpful_error_with_file_info(self):
        """Verify error messages include file information for debugging."""
        invalid_manifest = {
            "systemArtifacts": [
                {
                    "file": "specific_file.py",
                    "contains": [{"type": "function"}],  # Missing name
                }
            ]
        }

        with pytest.raises(AlignmentError) as exc_info:
            _validate_system_artifacts_structure(invalid_manifest)

        # Error should mention the file for better debugging
        assert "specific_file.py" in str(exc_info.value)


class TestSchemaValidationWithSystemManifests:
    """Test that schema validation works correctly with system manifests."""

    def test_validates_system_manifest_with_systemArtifacts(self, manifest_schema):
        """Verify system manifests with systemArtifacts validate successfully."""
        system_manifest = {
            "version": "1",
            "goal": "System-wide manifest snapshot",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [
                {
                    "file": "module/file1.py",
                    "contains": [
                        {"type": "function", "name": "func1", "args": []},
                        {"type": "class", "name": "Class1"},
                    ],
                },
                {
                    "file": "module/file2.py",
                    "contains": [{"type": "function", "name": "func2"}],
                },
            ],
            "validationCommands": [["pytest", "tests/"]],
        }

        # Should not raise ValidationError
        validate(instance=system_manifest, schema=manifest_schema)

    def test_validates_regular_manifest_with_expectedArtifacts(self, manifest_schema):
        """Verify regular manifests with expectedArtifacts still validate."""
        regular_manifest = {
            "version": "1",
            "goal": "Regular task",
            "taskType": "edit",
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [{"type": "function", "name": "func"}],
            },
            "validationCommand": ["pytest", "tests/"],
        }

        # Should not raise ValidationError
        validate(instance=regular_manifest, schema=manifest_schema)

    def test_schema_validation_via_validate_schema_function(self):
        """Verify validate_schema() function works with system manifests."""
        system_manifest = {
            "version": "1",
            "goal": "System snapshot",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [
                {"file": "test.py", "contains": [{"type": "function", "name": "f"}]}
            ],
            "validationCommand": ["pytest", "tests/"],
        }

        schema_path = "maid_runner/validators/schemas/manifest.schema.json"

        # Should not raise
        validate_schema(system_manifest, schema_path)

    def test_validate_schema_calls_system_artifacts_validation(self):
        """Verify validate_schema() actually invokes _validate_system_artifacts_structure()."""
        from unittest.mock import patch

        system_manifest = {
            "version": "1",
            "goal": "System snapshot",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [
                {"file": "test.py", "contains": [{"type": "function", "name": "f"}]}
            ],
            "validationCommand": ["pytest", "tests/"],
        }

        schema_path = "maid_runner/validators/schemas/manifest.schema.json"

        # Mock _validate_system_artifacts_structure to verify it's called
        with patch(
            "maid_runner.validators.manifest_validator._validate_system_artifacts_structure"
        ) as mock_validate:
            validate_schema(system_manifest, schema_path)

            # Verify the function was called exactly once with the manifest data
            mock_validate.assert_called_once_with(system_manifest)

    def test_validate_schema_integration_catches_invalid_system_artifacts(self):
        """Verify validate_schema() catches errors from _validate_system_artifacts_structure()."""
        # Create a manifest that passes JSON schema but should fail custom validation
        # We'll use systemArtifacts as a non-array (string), which JSON schema should catch first
        # So instead, let's create a manifest that has the right structure for JSON schema
        # but will fail our custom validation's additional checks

        # Actually, JSON schema is comprehensive, so let's just verify that AlignmentError
        # can be raised if our custom validation detects issues
        from unittest.mock import patch

        system_manifest = {
            "version": "1",
            "goal": "System snapshot",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [
                {"file": "test.py", "contains": [{"type": "function", "name": "f"}]}
            ],
            "validationCommand": ["pytest", "tests/"],
        }

        schema_path = "maid_runner/validators/schemas/manifest.schema.json"

        # Patch _validate_system_artifacts_structure to raise an error
        with patch(
            "maid_runner.validators.manifest_validator._validate_system_artifacts_structure"
        ) as mock_validate:
            mock_validate.side_effect = AlignmentError(
                "Test error from custom validation"
            )

            # Should raise the AlignmentError from our custom validation
            with pytest.raises(
                AlignmentError, match="Test error from custom validation"
            ):
                validate_schema(system_manifest, schema_path)


class TestSystemManifestEdgeCases:
    """Test edge cases for system manifest handling."""

    def test_empty_systemArtifacts_array(self):
        """Verify empty systemArtifacts array is valid."""
        manifest = {
            "version": "1",
            "goal": "Empty system snapshot",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [],
            "validationCommand": ["pytest", "tests/"],
        }

        assert _is_system_manifest(manifest) is True

    def test_systemArtifacts_with_multiple_files(self):
        """Verify systemArtifacts with many files is recognized."""
        manifest = {
            "version": "1",
            "goal": "Large system snapshot",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [
                {"file": f"file{i}.py", "contains": []} for i in range(100)
            ],
            "validationCommands": [["pytest", "tests/"]],
        }

        assert _is_system_manifest(manifest) is True

    def test_systemArtifacts_with_complex_artifacts(self):
        """Verify systemArtifacts with complex nested structures is recognized."""
        manifest = {
            "version": "1",
            "goal": "Complex system snapshot",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [
                {
                    "file": "complex.py",
                    "contains": [
                        {
                            "type": "class",
                            "name": "ComplexClass",
                            "bases": ["BaseClass", "Mixin"],
                        },
                        {
                            "type": "function",
                            "name": "complex_func",
                            "args": [
                                {"name": "arg1", "type": "str"},
                                {
                                    "name": "arg2",
                                    "type": "Optional[int]",
                                    "default": "None",
                                },
                            ],
                            "returns": "Dict[str, Any]",
                        },
                    ],
                }
            ],
            "validationCommand": ["pytest", "tests/"],
        }

        assert _is_system_manifest(manifest) is True


class TestBackwardCompatibility:
    """Ensure changes don't break existing manifest validation."""

    def test_regular_manifests_still_work(self):
        """Verify regular manifests are not affected by system manifest support."""
        regular_manifests = [
            {
                "version": "1",
                "goal": "Create task",
                "taskType": "create",
                "creatableFiles": ["new.py"],
                "readonlyFiles": [],
                "expectedArtifacts": {"file": "new.py", "contains": []},
                "validationCommand": ["pytest", "tests/"],
            },
            {
                "version": "1",
                "goal": "Edit task",
                "taskType": "edit",
                "editableFiles": ["existing.py"],
                "readonlyFiles": [],
                "expectedArtifacts": {"file": "existing.py", "contains": []},
                "validationCommand": ["pytest", "tests/"],
            },
            {
                "version": "1",
                "goal": "Snapshot task",
                "taskType": "snapshot",
                "readonlyFiles": [],
                "expectedArtifacts": {"file": "code.py", "contains": []},
                "validationCommand": ["pytest", "tests/"],
            },
        ]

        for manifest in regular_manifests:
            # Should be identified as NOT system manifests
            assert _is_system_manifest(manifest) is False

            # Should validate against schema
            schema_path = "maid_runner/validators/schemas/manifest.schema.json"
            validate_schema(manifest, schema_path)


class TestIntegrationWithRealSystemManifest:
    """Integration test with real system manifest generated by snapshot-system."""

    def test_real_system_manifest_is_recognized(self, tmp_path):
        """Verify real system manifest from snapshot-system is recognized."""
        from maid_runner.cli.snapshot_system import run_snapshot_system

        manifest_dir = Path("manifests")
        if not manifest_dir.exists():
            pytest.skip("Manifests directory not found")

        output_file = tmp_path / "system.manifest.json"

        # Generate real system snapshot
        run_snapshot_system(str(output_file), str(manifest_dir), quiet=True)

        # Load generated manifest
        with open(output_file) as f:
            system_manifest = json.load(f)

        # Should be identified as system manifest
        assert _is_system_manifest(system_manifest) is True

        # Should validate against schema
        schema_path = "maid_runner/validators/schemas/manifest.schema.json"
        validate_schema(system_manifest, schema_path)
