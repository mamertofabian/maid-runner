"""
Behavioral tests for Task-007: Type Definitions Module

Tests demonstrate natural usage of type definitions through:
1. Type annotations in function signatures
2. Variable type annotations
3. Runtime inspection of TypedDict structures
4. Type compatibility and instance creation
5. Integration with existing validation patterns
"""

from typing import Any, Dict, List, get_type_hints
from pathlib import Path


def test_uses_manifest_data_type_alias():
    """Test that ManifestData type alias is imported and used in type annotations"""
    from maid_runner.validators.types import ManifestData

    # Use ManifestData in a function signature - natural type annotation usage
    def process_manifest(data: ManifestData) -> bool:
        """Example function using ManifestData type alias"""
        return isinstance(data, dict) and "goal" in data

    # Verify the type annotation exists and is accessible
    type_hints = get_type_hints(process_manifest)
    assert "data" in type_hints
    assert "return" in type_hints

    # Test with sample manifest data structure
    sample_manifest: ManifestData = {
        "goal": "Test manifest",
        "taskType": "create",
        "creatableFiles": [],
        "editableFiles": [],
        "readonlyFiles": [],
        "expectedArtifacts": {"file": "test.py", "contains": []},
        "validationCommand": ["pytest"],
    }

    result = process_manifest(sample_manifest)
    assert result is True


def test_uses_file_path_type_alias():
    """Test that FilePath type alias is imported and used in type annotations"""
    from maid_runner.validators.types import FilePath

    # Use FilePath in function signatures and variable annotations
    def validate_file_exists(path: FilePath) -> bool:
        """Example function using FilePath type alias"""
        return Path(path).exists() if path else False

    def get_relative_path(base: FilePath, target: FilePath) -> FilePath:
        """Example function with FilePath parameters and return type"""
        if not base or not target:
            return ""
        return str(Path(target).relative_to(Path(base)))

    # Test type annotations are properly applied
    type_hints_validate = get_type_hints(validate_file_exists)
    type_hints_relative = get_type_hints(get_relative_path)

    assert "path" in type_hints_validate
    assert "base" in type_hints_relative
    assert "target" in type_hints_relative
    assert "return" in type_hints_relative

    # Test with actual file path usage
    test_path: FilePath = "manifests/task-007-type-definitions-module.manifest.json"
    base_path: FilePath = "manifests/"

    # These calls demonstrate natural usage of the FilePath type
    exists_result = validate_file_exists(test_path)
    relative_result = get_relative_path(base_path, test_path)

    # Basic functionality validation
    assert isinstance(exists_result, bool)
    assert isinstance(relative_result, str)


def test_uses_test_command_type_alias():
    """Test that TestCommand type alias is imported and used in type annotations"""
    from maid_runner.validators.types import TestCommand

    # Use TestCommand in function signature - represents command line arguments
    def execute_validation_command(command: TestCommand) -> Dict[str, Any]:
        """Example function using TestCommand type alias"""
        return {
            "command": command,
            "valid": isinstance(command, list) and len(command) > 0,
            "executable": command[0] if command else None,
        }

    def format_test_command(
        base_cmd: TestCommand, additional_args: List[str]
    ) -> TestCommand:
        """Example function that manipulates test commands"""
        return base_cmd + additional_args if base_cmd else additional_args

    # Verify type annotations
    type_hints_execute = get_type_hints(execute_validation_command)
    type_hints_format = get_type_hints(format_test_command)

    assert "command" in type_hints_execute
    assert "base_cmd" in type_hints_format
    assert "return" in type_hints_format

    # Test with realistic test command usage
    pytest_command: TestCommand = ["pytest", "tests/test_file.py", "-v"]
    mypy_command: TestCommand = ["mypy", "src/"]

    # Demonstrate natural usage
    result = execute_validation_command(pytest_command)
    formatted_command = format_test_command(mypy_command, ["--strict"])

    assert result["valid"] is True
    assert result["executable"] == "pytest"
    assert formatted_command == ["mypy", "src/", "--strict"]


def test_validation_result_typed_dict_structure():
    """Test ValidationResult TypedDict through runtime inspection and usage"""
    from maid_runner.validators.types import ValidationResult

    # Test TypedDict structure through introspection
    assert hasattr(ValidationResult, "__annotations__")
    assert hasattr(ValidationResult, "__required_keys__")
    assert hasattr(ValidationResult, "__optional_keys__")

    # Create instances to test structure compatibility
    valid_result: ValidationResult = {"valid": True, "errors": [], "warnings": []}

    invalid_result: ValidationResult = {
        "valid": False,
        "errors": ["Missing required artifact"],
        "warnings": ["Deprecated pattern usage"],
    }

    # Test that instances have expected structure
    assert "valid" in valid_result
    assert "errors" in valid_result
    assert "warnings" in valid_result
    assert isinstance(valid_result["valid"], bool)
    assert isinstance(valid_result["errors"], list)
    assert isinstance(valid_result["warnings"], list)

    # Use in function that expects ValidationResult
    def process_validation_result(result: ValidationResult) -> str:
        if result["valid"]:
            return "Validation passed"
        else:
            return f"Validation failed: {len(result['errors'])} errors"

    assert process_validation_result(valid_result) == "Validation passed"
    assert "failed" in process_validation_result(invalid_result)


def test_artifact_dict_typed_dict_structure():
    """Test ArtifactDict TypedDict through runtime inspection and usage"""
    from maid_runner.validators.types import ArtifactDict

    # Test TypedDict metadata
    assert hasattr(ArtifactDict, "__annotations__")

    # Create realistic artifact dictionary
    function_artifact: ArtifactDict = {
        "type": "function",
        "name": "validate_manifest",
        "args": [
            {"name": "manifest_path", "type": "str"},
            {"name": "strict_mode", "type": "bool"},
        ],
        "returns": "ValidationResult",
    }

    class_artifact: ArtifactDict = {
        "type": "class",
        "name": "ManifestValidator",
        "bases": ["BaseValidator"],
    }

    # Test structure and usage
    assert function_artifact["type"] == "function"
    assert function_artifact["name"] == "validate_manifest"
    assert isinstance(function_artifact["args"], list)

    assert class_artifact["type"] == "class"
    assert class_artifact["name"] == "ManifestValidator"

    # Use in function that processes artifacts
    def get_artifact_signature(artifact: ArtifactDict) -> str:
        if artifact["type"] == "function":
            args_str = ", ".join(arg["name"] for arg in artifact.get("args", []))
            return f"{artifact['name']}({args_str})"
        elif artifact["type"] == "class":
            bases = artifact.get("bases", [])
            bases_str = f"({', '.join(bases)})" if bases else ""
            return f"class {artifact['name']}{bases_str}"
        return artifact["name"]

    func_sig = get_artifact_signature(function_artifact)
    class_sig = get_artifact_signature(class_artifact)

    assert "validate_manifest(manifest_path, strict_mode)" == func_sig
    assert "class ManifestValidator(BaseValidator)" == class_sig


def test_expected_artifacts_typed_dict_structure():
    """Test ExpectedArtifacts TypedDict through runtime inspection and usage"""
    from maid_runner.validators.types import ExpectedArtifacts

    # Test TypedDict metadata
    assert hasattr(ExpectedArtifacts, "__annotations__")

    # Create realistic expected artifacts structure
    expected_artifacts: ExpectedArtifacts = {
        "file": "validators/types.py",
        "contains": [
            {"type": "class", "name": "ValidationResult", "bases": ["TypedDict"]},
            {
                "type": "function",
                "name": "validate_artifacts",
                "args": [{"name": "artifacts", "type": "List[ArtifactDict]"}],
            },
        ],
    }

    # Test structure
    assert "file" in expected_artifacts
    assert "contains" in expected_artifacts
    assert isinstance(expected_artifacts["contains"], list)
    assert len(expected_artifacts["contains"]) == 2

    # Use in function that processes expected artifacts
    def count_artifacts_by_type(expected: ExpectedArtifacts) -> Dict[str, int]:
        counts = {}
        for artifact in expected["contains"]:
            artifact_type = artifact["type"]
            counts[artifact_type] = counts.get(artifact_type, 0) + 1
        return counts

    counts = count_artifacts_by_type(expected_artifacts)
    assert counts["class"] == 1
    assert counts["function"] == 1


def test_type_mismatch_typed_dict_structure():
    """Test TypeMismatch TypedDict through runtime inspection and usage"""
    from maid_runner.validators.types import TypeMismatch

    # Test TypedDict metadata
    assert hasattr(TypeMismatch, "__annotations__")

    # Create type mismatch instances
    return_type_mismatch: TypeMismatch = {
        "artifact_name": "validate_manifest",
        "expected_type": "ValidationResult",
        "actual_type": "bool",
        "mismatch_kind": "return_type",
    }

    parameter_mismatch: TypeMismatch = {
        "artifact_name": "process_file",
        "expected_type": "str",
        "actual_type": "Path",
        "mismatch_kind": "parameter_type",
    }

    # Test structure
    assert "artifact_name" in return_type_mismatch
    assert "expected_type" in return_type_mismatch
    assert "actual_type" in return_type_mismatch
    assert "mismatch_kind" in return_type_mismatch

    # Use in function that processes type mismatches
    def format_type_mismatch_error(mismatch: TypeMismatch) -> str:
        return (
            f"Type mismatch in {mismatch['artifact_name']}: "
            f"expected {mismatch['expected_type']}, "
            f"got {mismatch['actual_type']} "
            f"({mismatch['mismatch_kind']})"
        )

    error_msg = format_type_mismatch_error(return_type_mismatch)
    assert "validate_manifest" in error_msg
    assert "ValidationResult" in error_msg
    assert "bool" in error_msg
    assert "return_type" in error_msg

    # Test parameter mismatch formatting as well
    param_error_msg = format_type_mismatch_error(parameter_mismatch)
    assert "process_file" in param_error_msg
    assert "str" in param_error_msg
    assert "Path" in param_error_msg
    assert "parameter_type" in param_error_msg


def test_implementation_artifacts_typed_dict_structure():
    """Test ImplementationArtifacts TypedDict through runtime inspection and usage"""
    from maid_runner.validators.types import ImplementationArtifacts, ExpectedArtifacts

    # Test TypedDict metadata
    assert hasattr(ImplementationArtifacts, "__annotations__")

    # Create implementation artifacts structure
    impl_artifacts: ImplementationArtifacts = {
        "file": "validators/types.py",
        "found": [
            {"type": "class", "name": "ValidationResult", "bases": ["TypedDict"]},
            {"type": "attribute", "name": "ManifestData"},
        ],
    }

    # Test structure
    assert "file" in impl_artifacts
    assert "found" in impl_artifacts
    assert isinstance(impl_artifacts["found"], list)
    assert len(impl_artifacts["found"]) == 2

    # Use in function that compares implementation vs expected
    def compare_artifacts(
        expected: ExpectedArtifacts, implemented: ImplementationArtifacts
    ) -> Dict[str, Any]:
        expected_names = {artifact["name"] for artifact in expected["contains"]}
        implemented_names = {artifact["name"] for artifact in implemented["found"]}

        return {
            "missing": expected_names - implemented_names,
            "extra": implemented_names - expected_names,
            "matched": expected_names & implemented_names,
            "files_match": expected["file"] == implemented["file"],
        }

    # Create matching expected artifacts for comparison
    expected: ExpectedArtifacts = {
        "file": "validators/types.py",
        "contains": [
            {"type": "class", "name": "ValidationResult", "bases": ["TypedDict"]},
            {"type": "attribute", "name": "FilePath"},
        ],
    }

    comparison = compare_artifacts(expected, impl_artifacts)
    assert comparison["files_match"] is True
    assert "ValidationResult" in comparison["matched"]
    assert "FilePath" in comparison["missing"]
    assert "ManifestData" in comparison["extra"]


def test_integration_with_existing_validation_patterns():
    """Test how type definitions integrate with existing validation patterns"""
    from maid_runner.validators.types import (
        ManifestData,
        FilePath,
        TestCommand,
        ValidationResult,
    )

    # Simulate a validation function that uses multiple type definitions
    def validate_manifest_structure(
        manifest_path: FilePath, manifest_data: ManifestData, test_command: TestCommand
    ) -> ValidationResult:
        """Example integration function using multiple type definitions"""
        errors = []
        warnings = []

        # Validate manifest data structure
        if not isinstance(manifest_data, dict):
            errors.append("Manifest data must be a dictionary")

        required_fields = ["goal", "taskType", "expectedArtifacts"]
        for field in required_fields:
            if field not in manifest_data:
                errors.append(f"Missing required field: {field}")

        # Validate test command
        if not test_command or not isinstance(test_command, list):
            errors.append("Test command must be a non-empty list")
        elif test_command[0] not in ["pytest", "python", "mypy"]:
            warnings.append(f"Unusual test command: {test_command[0]}")

        # Validate file path
        if not manifest_path or not isinstance(manifest_path, str):
            errors.append("Manifest path must be a non-empty string")

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    # Test the integration function with realistic data
    test_manifest_data: ManifestData = {
        "goal": "Test integration",
        "taskType": "create",
        "creatableFiles": [],
        "editableFiles": [],
        "readonlyFiles": [],
        "expectedArtifacts": {"file": "test.py", "contains": []},
        "validationCommand": ["pytest", "-v"],
    }

    test_path: FilePath = "manifests/test-integration.manifest.json"
    test_cmd: TestCommand = ["pytest", "-v"]

    result = validate_manifest_structure(test_path, test_manifest_data, test_cmd)

    # Verify the integration works and returns proper ValidationResult
    assert isinstance(result, dict)
    assert "valid" in result
    assert "errors" in result
    assert "warnings" in result
    assert result["valid"] is True
    assert len(result["errors"]) == 0


def test_type_definitions_imported_successfully():
    """Verify all type definitions can be imported (basic smoke test)"""
    # This test ensures the module structure is correct and all types are exportable
    from maid_runner.validators.types import (
        ManifestData,  # Type alias
        FilePath,  # Type alias
        TestCommand,  # Type alias
        ValidationResult,  # TypedDict
        ArtifactDict,  # TypedDict
        ExpectedArtifacts,  # TypedDict
        TypeMismatch,  # TypedDict
        ImplementationArtifacts,  # TypedDict
    )

    # Basic existence verification - all imports should succeed
    type_aliases = [ManifestData, FilePath, TestCommand]
    typed_dicts = [
        ValidationResult,
        ArtifactDict,
        ExpectedArtifacts,
        TypeMismatch,
        ImplementationArtifacts,
    ]

    # Verify type aliases are accessible
    for type_alias in type_aliases:
        assert type_alias is not None

    # Verify TypedDict classes have the expected metadata
    for typed_dict in typed_dicts:
        assert hasattr(typed_dict, "__annotations__")
        # TypedDict classes should be callable (for type checking)
        assert callable(typed_dict)
