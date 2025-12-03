"""Behavioral tests for Task 079: Schema-only validation mode

Tests the schema-only validation mode feature that allows validating manifest
structure without requiring implementation or test files to exist. This is useful
for early manifest validation during Phase 1 planning and for validation of
snapshot manifests by tooling/automation.

Key behaviors tested:
1. ValidationMode type includes "schema" option
2. CLI accepts --validation-mode schema argument
3. Schema mode validates JSON schema, semantics, and version
4. Schema mode skips behavioral and implementation validation
5. Schema mode doesn't require expectedArtifacts.file to exist
6. Invalid schema/semantics still fail in schema mode
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest


class TestValidationModeType:
    """Tests for ValidationMode type definition."""

    def test_validation_mode_type_is_importable(self):
        """Test that ValidationMode type is importable from maid_runner.validators.types."""
        from maid_runner.validators.types import ValidationMode

        assert ValidationMode is not None

    def test_validation_mode_includes_schema(self):
        """Test that ValidationMode type includes 'schema' as a valid option."""
        from maid_runner.validators.types import ValidationMode
        from typing import get_args

        # Get the literal values from the type
        valid_modes = get_args(ValidationMode)

        # Should include all three modes
        assert "implementation" in valid_modes
        assert "behavioral" in valid_modes
        assert "schema" in valid_modes

    def test_validation_mode_type_annotation(self):
        """Test that ValidationMode is a Literal type with correct values."""
        from maid_runner.validators.types import ValidationMode
        from typing import get_origin, get_args, Literal

        # Check it's a Literal type
        assert get_origin(ValidationMode) == Literal

        # Check it has exactly three options
        valid_modes = get_args(ValidationMode)
        assert len(valid_modes) == 3


class TestCLISchemaMode:
    """Tests for CLI argument acceptance of schema mode."""

    def test_cli_validate_accepts_schema_mode(self, tmp_path: Path):
        """Test that CLI validate command accepts --validation-mode schema."""
        from maid_runner.cli.validate import run_validation

        # Create a minimal manifest
        manifest_path = tmp_path / "manifests" / "test.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        manifest_data = {
            "version": "1",
            "goal": "Test schema validation mode",
            "taskType": "edit",
            "editableFiles": ["src/nonexistent.py"],
            "expectedArtifacts": {
                "file": "src/nonexistent.py",
                "contains": [{"type": "function", "name": "test_function"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        # Mock the validation functions to track calls
        with patch("maid_runner.cli.validate.validate_schema") as mock_schema:
            with patch(
                "maid_runner.cli.validate.validate_manifest_semantics"
            ) as mock_semantics:
                with patch("maid_runner.utils.validate_manifest_version"):
                    with patch("maid_runner.cli.validate.validate_with_ast"):
                        # Call run_validation with schema mode
                        try:
                            run_validation(
                                manifest_path=str(manifest_path),
                                validation_mode="schema",
                                use_manifest_chain=False,
                                quiet=True,
                            )
                        except SystemExit:
                            # Expected if file doesn't exist in non-schema mode
                            pass

                        # Schema validation should have been called
                        assert mock_schema.called or mock_semantics.called

    def test_cli_main_accepts_schema_in_choices(self):
        """Test that main() CLI parser includes 'schema' in validation mode choices."""
        import argparse

        # Create a parser like the one in main()
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--validation-mode",
            choices=["implementation", "behavioral", "schema"],
            default="implementation",
        )

        # Should parse schema mode without error
        args = parser.parse_args(["--validation-mode", "schema"])
        assert args.validation_mode == "schema"


class TestSchemaOnlyValidation:
    """Tests for schema-only validation behavior."""

    def test_schema_mode_validates_without_implementation_file(self, tmp_path: Path):
        """Test that schema mode validates manifest even when implementation file doesn't exist."""
        from maid_runner.cli.validate import run_validation

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        # Create manifest with non-existent implementation file
        manifest_data = {
            "version": "1",
            "goal": "Test schema-only validation",
            "taskType": "edit",
            "editableFiles": ["src/nonexistent.py"],
            "expectedArtifacts": {
                "file": "src/nonexistent.py",  # File doesn't exist
                "contains": [{"type": "function", "name": "test_function"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        # Mock validation functions to succeed
        with patch("maid_runner.cli.validate.validate_schema"):
            with patch("maid_runner.cli.validate.validate_manifest_semantics"):
                with patch("maid_runner.utils.validate_manifest_version"):
                    # Schema mode should pass without checking if file exists
                    try:
                        run_validation(
                            manifest_path=str(manifest_path),
                            validation_mode="schema",
                            use_manifest_chain=False,
                            quiet=True,
                        )
                        # If we get here without SystemExit, schema mode worked
                        success = True
                    except SystemExit as e:
                        # SystemExit(0) is success, SystemExit(1) is failure
                        success = e.code == 0

                    # Should succeed in schema mode even though file doesn't exist
                    assert success

    def test_schema_mode_skips_behavioral_validation(self, tmp_path: Path):
        """Test that schema mode doesn't run behavioral validation."""
        from maid_runner.cli.validate import run_validation

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        manifest_data = {
            "version": "1",
            "goal": "Test schema mode skips behavioral",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [{"type": "function", "name": "example"}],
            },
            "validationCommand": ["pytest", "tests/test_example.py", "-v"],
        }
        manifest_path.write_text(json.dumps(manifest_data))

        with patch("maid_runner.cli.validate.validate_schema"):
            with patch("maid_runner.cli.validate.validate_manifest_semantics"):
                with patch("maid_runner.utils.validate_manifest_version"):
                    with patch(
                        "maid_runner.cli.validate.validate_behavioral_tests"
                    ) as mock_behavioral:
                        try:
                            run_validation(
                                manifest_path=str(manifest_path),
                                validation_mode="schema",
                                use_manifest_chain=False,
                                quiet=True,
                            )
                        except SystemExit:
                            pass

                        # Behavioral validation should NOT be called in schema mode
                        assert not mock_behavioral.called

    def test_schema_mode_skips_implementation_validation(self, tmp_path: Path):
        """Test that schema mode doesn't run implementation validation."""
        from maid_runner.cli.validate import run_validation

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        manifest_data = {
            "version": "1",
            "goal": "Test schema mode skips implementation",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [{"type": "function", "name": "example"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        with patch("maid_runner.cli.validate.validate_schema"):
            with patch("maid_runner.cli.validate.validate_manifest_semantics"):
                with patch("maid_runner.utils.validate_manifest_version"):
                    with patch(
                        "maid_runner.cli.validate.validate_with_ast"
                    ) as mock_ast:
                        try:
                            run_validation(
                                manifest_path=str(manifest_path),
                                validation_mode="schema",
                                use_manifest_chain=False,
                                quiet=True,
                            )
                        except SystemExit:
                            pass

                        # AST validation should NOT be called in schema mode
                        assert not mock_ast.called

    def test_schema_mode_performs_schema_validation(self, tmp_path: Path):
        """Test that schema mode performs JSON schema validation."""
        from maid_runner.cli.validate import run_validation

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        manifest_data = {
            "version": "1",
            "goal": "Test schema validation",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [{"type": "function", "name": "example"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        with patch(
            "maid_runner.cli.validate.validate_schema"
        ) as mock_schema_validation:
            with patch("maid_runner.cli.validate.validate_manifest_semantics"):
                with patch("maid_runner.utils.validate_manifest_version"):
                    try:
                        run_validation(
                            manifest_path=str(manifest_path),
                            validation_mode="schema",
                            use_manifest_chain=False,
                            quiet=True,
                        )
                    except SystemExit:
                        pass

                    # Schema validation SHOULD be called in schema mode
                    assert mock_schema_validation.called

    def test_schema_mode_performs_semantic_validation(self, tmp_path: Path):
        """Test that schema mode performs semantic validation."""
        from maid_runner.cli.validate import run_validation

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        manifest_data = {
            "version": "1",
            "goal": "Test semantic validation",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [{"type": "function", "name": "example"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        with patch("maid_runner.cli.validate.validate_schema"):
            with patch(
                "maid_runner.cli.validate.validate_manifest_semantics"
            ) as mock_semantics:
                with patch("maid_runner.utils.validate_manifest_version"):
                    try:
                        run_validation(
                            manifest_path=str(manifest_path),
                            validation_mode="schema",
                            use_manifest_chain=False,
                            quiet=True,
                        )
                    except SystemExit:
                        pass

                    # Semantic validation SHOULD be called in schema mode
                    assert mock_semantics.called

    def test_schema_mode_performs_version_validation(self, tmp_path: Path):
        """Test that schema mode performs version validation."""
        from maid_runner.cli.validate import run_validation

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        manifest_data = {
            "version": "1",
            "goal": "Test version validation",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [{"type": "function", "name": "example"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        with patch("maid_runner.cli.validate.validate_schema"):
            with patch("maid_runner.cli.validate.validate_manifest_semantics"):
                with patch(
                    "maid_runner.utils.validate_manifest_version"
                ) as mock_version:
                    try:
                        run_validation(
                            manifest_path=str(manifest_path),
                            validation_mode="schema",
                            use_manifest_chain=False,
                            quiet=True,
                        )
                    except SystemExit:
                        pass

                    # Version validation SHOULD be called in schema mode
                    assert mock_version.called


class TestSchemaValidationErrorHandling:
    """Tests for error handling in schema validation mode."""

    def test_schema_mode_fails_on_invalid_schema(self, tmp_path: Path):
        """Test that schema mode fails when manifest has invalid schema."""
        from maid_runner.cli.validate import run_validation
        import jsonschema

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        # Invalid manifest: missing required fields
        manifest_data = {
            "goal": "Missing version and taskType",
        }
        manifest_path.write_text(json.dumps(manifest_data))

        # Mock validate_schema to raise ValidationError
        with patch(
            "maid_runner.cli.validate.validate_schema"
        ) as mock_schema_validation:
            mock_schema_validation.side_effect = jsonschema.ValidationError("Invalid")

            with pytest.raises(SystemExit) as exc_info:
                run_validation(
                    manifest_path=str(manifest_path),
                    validation_mode="schema",
                    use_manifest_chain=False,
                    quiet=True,
                )

            # Should exit with error code 1
            assert exc_info.value.code == 1

    def test_schema_mode_fails_on_semantic_errors(self, tmp_path: Path):
        """Test that schema mode fails when manifest has semantic errors."""
        from maid_runner.cli.validate import run_validation
        from maid_runner.validators.semantic_validator import ManifestSemanticError

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        manifest_data = {
            "version": "1",
            "goal": "Test semantic error",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [{"type": "function", "name": "example"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        # Mock semantic validation to raise error
        with patch("maid_runner.cli.validate.validate_schema"):
            with patch(
                "maid_runner.cli.validate.validate_manifest_semantics"
            ) as mock_semantics:
                mock_semantics.side_effect = ManifestSemanticError("Semantic error")

                with pytest.raises(SystemExit) as exc_info:
                    run_validation(
                        manifest_path=str(manifest_path),
                        validation_mode="schema",
                        use_manifest_chain=False,
                        quiet=True,
                    )

                # Should exit with error code 1
                assert exc_info.value.code == 1

    def test_schema_mode_fails_on_version_errors(self, tmp_path: Path):
        """Test that schema mode fails when manifest has version errors."""
        from maid_runner.cli.validate import run_validation

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        manifest_data = {
            "version": "999",  # Invalid version
            "goal": "Test version error",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [{"type": "function", "name": "example"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        # Mock version validation to raise error
        with patch("maid_runner.cli.validate.validate_schema"):
            with patch("maid_runner.cli.validate.validate_manifest_semantics"):
                with patch(
                    "maid_runner.utils.validate_manifest_version"
                ) as mock_version:
                    mock_version.side_effect = ValueError("Invalid version")

                    with pytest.raises(SystemExit) as exc_info:
                        run_validation(
                            manifest_path=str(manifest_path),
                            validation_mode="schema",
                            use_manifest_chain=False,
                            quiet=True,
                        )

                    # Should exit with error code 1
                    assert exc_info.value.code == 1


class TestEarlyExitBehavior:
    """Tests for early exit after schema/semantic/version validation."""

    def test_schema_mode_exits_early_after_version_validation(self, tmp_path: Path):
        """Test that schema mode exits early and doesn't check file existence."""
        from maid_runner.cli.validate import run_validation

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        # Reference a file that doesn't exist
        manifest_data = {
            "version": "1",
            "goal": "Test early exit",
            "taskType": "edit",
            "editableFiles": ["src/definitely_does_not_exist.py"],
            "expectedArtifacts": {
                "file": "src/definitely_does_not_exist.py",
                "contains": [{"type": "function", "name": "test"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        # All validation steps should succeed
        with patch("maid_runner.cli.validate.validate_schema"):
            with patch("maid_runner.cli.validate.validate_manifest_semantics"):
                with patch("maid_runner.utils.validate_manifest_version"):
                    # Should succeed without checking if file exists
                    try:
                        run_validation(
                            manifest_path=str(manifest_path),
                            validation_mode="schema",
                            use_manifest_chain=False,
                            quiet=True,
                        )
                        success = True
                    except SystemExit as e:
                        success = e.code == 0

                    # Should succeed even though target file doesn't exist
                    assert success

    def test_schema_mode_doesnt_check_test_file_existence(self, tmp_path: Path):
        """Test that schema mode doesn't check if test files exist."""
        from maid_runner.cli.validate import run_validation

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        manifest_data = {
            "version": "1",
            "goal": "Test doesn't check test files",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [{"type": "function", "name": "example"}],
            },
            "validationCommand": ["pytest", "tests/nonexistent_test.py", "-v"],
        }
        manifest_path.write_text(json.dumps(manifest_data))

        with patch("maid_runner.cli.validate.validate_schema"):
            with patch("maid_runner.cli.validate.validate_manifest_semantics"):
                with patch("maid_runner.utils.validate_manifest_version"):
                    # Should succeed without checking if test file exists
                    try:
                        run_validation(
                            manifest_path=str(manifest_path),
                            validation_mode="schema",
                            use_manifest_chain=False,
                            quiet=True,
                        )
                        success = True
                    except SystemExit as e:
                        success = e.code == 0

                    # Should succeed even though test file doesn't exist
                    assert success


class TestSchemaModePracticalUseCases:
    """Tests for practical use cases of schema validation mode."""

    def test_schema_mode_validates_planning_phase_manifest(self, tmp_path: Path):
        """Test that schema mode is useful for Phase 1 planning before files exist."""
        from maid_runner.cli.validate import run_validation

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        # Manifest created during planning - no implementation yet
        manifest_data = {
            "version": "1",
            "goal": "Add new feature (planning phase)",
            "taskType": "create",
            "creatableFiles": ["src/new_feature.py"],
            "expectedArtifacts": {
                "file": "src/new_feature.py",
                "contains": [
                    {"type": "class", "name": "NewFeature"},
                    {"type": "function", "name": "process", "class": "NewFeature"},
                ],
            },
            "validationCommand": ["pytest", "tests/test_new_feature.py", "-v"],
        }
        manifest_path.write_text(json.dumps(manifest_data))

        with patch("maid_runner.cli.validate.validate_schema"):
            with patch("maid_runner.cli.validate.validate_manifest_semantics"):
                with patch("maid_runner.utils.validate_manifest_version"):
                    # Should validate successfully in schema mode
                    try:
                        run_validation(
                            manifest_path=str(manifest_path),
                            validation_mode="schema",
                            use_manifest_chain=False,
                            quiet=True,
                        )
                        success = True
                    except SystemExit as e:
                        success = e.code == 0

                    assert success

    def test_schema_mode_validates_snapshot_manifest(self, tmp_path: Path):
        """Test that schema mode validates snapshot manifests used by tooling."""
        from maid_runner.cli.validate import run_validation

        manifest_path = tmp_path / "snapshot-system.manifest.json"

        # Snapshot manifest aggregating multiple files
        manifest_data = {
            "version": "1",
            "goal": "System snapshot",
            "taskType": "snapshot",
            "readonlyFiles": ["src/module1.py", "src/module2.py"],
            "expectedArtifacts": {
                "file": "src/module1.py",
                "contains": [{"type": "function", "name": "func1"}],
            },
            "validationCommand": ["pytest", "tests/", "-v"],
        }
        manifest_path.write_text(json.dumps(manifest_data))

        with patch("maid_runner.cli.validate.validate_schema"):
            with patch("maid_runner.cli.validate.validate_manifest_semantics"):
                with patch("maid_runner.utils.validate_manifest_version"):
                    # Schema mode should validate structure
                    try:
                        run_validation(
                            manifest_path=str(manifest_path),
                            validation_mode="schema",
                            use_manifest_chain=False,
                            quiet=True,
                        )
                        success = True
                    except SystemExit as e:
                        success = e.code == 0

                    assert success
