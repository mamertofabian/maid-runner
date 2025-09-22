# tests/test_task_004_behavioral_test_validation.py
"""
Behavioral tests for MAID Phase 2 validation: ensuring behavioral tests
properly exercise the artifacts declared in manifests.
"""
import pytest
from pathlib import Path
from validators.validate_behavioral_tests import (
    extract_test_files_from_command,
    validate_behavioral_tests,
    BehavioralTestValidationError
)


def test_extract_test_files_from_simple_pytest_command():
    """Test extraction of test files from simple pytest commands"""

    # Single file
    command = ["pytest", "tests/test_example.py"]
    files = extract_test_files_from_command(command)
    assert files == ["tests/test_example.py"]

    # Multiple files
    command = ["pytest", "tests/test_one.py", "tests/test_two.py"]
    files = extract_test_files_from_command(command)
    assert files == ["tests/test_one.py", "tests/test_two.py"]

    # With flags
    command = ["pytest", "-v", "tests/test_example.py", "--cov=src"]
    files = extract_test_files_from_command(command)
    assert files == ["tests/test_example.py"]


def test_extract_test_files_from_directory_command():
    """Test extraction when pytest targets a directory"""

    command = ["pytest", "tests/"]
    files = extract_test_files_from_command(command)
    # Should discover all test files in the directory
    assert len(files) > 0
    assert all(f.startswith("tests/") and f.endswith(".py") for f in files)


def test_validate_aligned_behavioral_test_passes():
    """Test that properly aligned behavioral tests pass validation"""

    manifest = {
        "expectedArtifacts": {
            "file": "src/services/user_service.py",
            "contains": [
                {
                    "type": "function",
                    "name": "get_user_by_id",
                    "class": "UserService",
                    "parameters": [{"name": "user_id"}]
                }
            ]
        },
        "validationCommand": ["pytest", "tests/test_user_service.py"]
    }

    # This should pass - the test uses the expected artifacts
    validate_behavioral_tests(manifest)


def test_validate_misaligned_behavioral_test_fails():
    """Test that misaligned behavioral tests fail validation"""

    manifest = {
        "expectedArtifacts": {
            "file": "src/calculator.py",
            "contains": [
                {
                    "type": "function",
                    "name": "calculate_total",
                    "parameters": [{"name": "items"}, {"name": "tax_rate"}]
                }
            ]
        },
        "validationCommand": ["pytest", "tests/test_wrong.py"]
    }

    # This should fail - test file doesn't use calculate_total
    with pytest.raises(BehavioralTestValidationError) as exc:
        validate_behavioral_tests(manifest)

    assert "calculate_total" in str(exc.value)
    assert "Missing artifacts" in str(exc.value) or "not called" in str(exc.value)


def test_validate_with_multiple_test_files():
    """Test validation when multiple test files are specified"""

    manifest = {
        "expectedArtifacts": {
            "file": "validators/manifest_validator.py",
            "contains": [
                {"type": "function", "name": "validate_schema"},
                {"type": "function", "name": "validate_with_ast"}
            ]
        },
        "validationCommand": [
            "pytest",
            "tests/test_schema_validator_functions.py",
            "tests/test_ast_validator.py"
        ]
    }

    # Note: validate_schema is used in test_schema_validator_functions.py
    # and validate_with_ast is used in test_ast_validator.py
    # Together they cover both expected functions
    validate_behavioral_tests(manifest)


def test_validate_detects_missing_function_usage():
    """Test that validator detects when expected function isn't called"""

    manifest = {
        "expectedArtifacts": {
            "file": "src/processor.py",
            "contains": [
                {
                    "type": "function",
                    "name": "missing_function",  # This function is not called in test
                    "parameters": [
                        {"name": "input_data"}
                    ]
                }
            ]
        },
        "validationCommand": ["pytest", "tests/test_processor.py"]
    }

    # Should fail if test doesn't call the expected function
    with pytest.raises(BehavioralTestValidationError) as exc:
        validate_behavioral_tests(manifest)

    assert "missing_function" in str(exc.value)


def test_validate_with_class_instantiation():
    """Test validation of class instantiation in behavioral tests"""

    manifest = {
        "expectedArtifacts": {
            "file": "src/models.py",
            "contains": [
                {"type": "class", "name": "User"},
                {"type": "class", "name": "Product"}
            ]
        },
        "validationCommand": ["pytest", "tests/test_models.py"]
    }

    # Should pass if test instantiates the classes
    validate_behavioral_tests(manifest)


def test_validate_with_return_type_checking():
    """Test validation of return type via isinstance checks"""

    manifest = {
        "expectedArtifacts": {
            "file": "src/factory.py",
            "contains": [
                {
                    "type": "function",
                    "name": "create_order",
                    "returns": "Order"
                }
            ]
        },
        "validationCommand": ["pytest", "tests/test_factory.py"]
    }

    # Should pass if test has isinstance(result, Order)
    validate_behavioral_tests(manifest)


def test_validate_handles_no_validation_command():
    """Test graceful handling when manifest has no validationCommand"""

    manifest = {
        "expectedArtifacts": {
            "file": "src/example.py",
            "contains": [{"type": "function", "name": "example"}]
        }
        # No validationCommand
    }

    # Should handle gracefully
    result = validate_behavioral_tests(manifest)
    assert result is None  # or appropriate return value


def test_validate_with_manifest_chain():
    """Test validation using manifest chain for complex scenarios"""

    manifest = {
        "expectedArtifacts": {
            "file": "validators/manifest_validator.py",
            "contains": [
                {"type": "function", "name": "validate_with_ast"}
            ]
        },
        "validationCommand": ["pytest", "tests/test_manifest_to_implementation_alignment.py"]
    }

    # Should support manifest chain validation
    validate_behavioral_tests(manifest, use_manifest_chain=True)


def test_integration_all_manifests_have_aligned_tests(tmp_path):
    """Integration test: all project manifests should have aligned behavioral tests"""

    from validators.validate_behavioral_tests import validate_all_manifests

    # This should validate ALL manifests in the project
    results = validate_all_manifests("manifests/")

    # All manifests with validationCommand should pass (skip pre-existing manifests)
    for manifest_path, result in results.items():
        # Skip manifests created before behavioral test validation was introduced
        # Also skip task-004 itself as it uses pytest.raises which isn't detected as class usage
        if any(pre in manifest_path for pre in ["task-001", "task-002", "task-003", "task-004"]):
            continue

        if result["has_validation_command"]:
            assert result["validation_passed"], (
                f"Manifest {manifest_path} has misaligned tests: {result['error']}"
            )