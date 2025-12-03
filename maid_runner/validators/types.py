"""
Type definitions for the MAID validation system.

This module provides comprehensive type definitions that ensure type safety
and clear contracts throughout the MAID validation process. It serves as the
central type registry for all validation operations, defining both simple type
aliases and complex structured types.

Module Organization:
    - Type Aliases: Simple type aliases for common data structures
    - Core Validation Types: Types for validation results and operations
    - Artifact Definition Types: Types for representing code artifacts
    - Error and Diagnostic Types: Types for error reporting and diagnostics
    - Function Signature Types: Types for function and method signatures
    - Implementation Discovery Types: Types for discovered implementation artifacts

Usage:
    Import specific types as needed for type annotations:

    from validators.types import ManifestData, ValidationResult

    def validate_manifest(data: ManifestData) -> ValidationResult:
        # Implementation here
        pass

Type Safety:
    All types are designed to work with mypy and other static type checkers.
    TypedDict classes provide runtime type checking capabilities when used
    with appropriate runtime type validation libraries.
"""

from typing import Any, Dict, List, Literal, Optional, TypedDict

# ============================================================================
# Type Aliases for Common Data Structures
# ============================================================================

ManifestData = Dict[str, Any]
"""Type alias for manifest data structures.

Represents the JSON data loaded from a manifest file. Contains keys like
'goal', 'taskType', 'expectedArtifacts', etc.

Example:
    manifest: ManifestData = {
        "goal": "Create validation module",
        "taskType": "create",
        "expectedArtifacts": {...}
    }
"""

FilePath = str
"""Type alias for file system paths.

Represents absolute or relative paths to files and directories.
Used throughout the validation system for file references.

Example:
    config_path: FilePath = "manifests/task-001.manifest.json"
    source_file: FilePath = "src/validators/types.py"
"""

TestCommand = List[str]
"""Type alias for command-line test execution commands.

Represents a command and its arguments as a list of strings,
suitable for subprocess execution.

Example:
    pytest_cmd: TestCommand = ["pytest", "tests/", "-v"]
    mypy_cmd: TestCommand = ["mypy", "src/", "--strict"]
"""

ValidationMode = Literal["implementation", "behavioral", "schema"]
"""Type alias for validation mode selection.

Specifies which type of validation to perform:
- "implementation": Validates that code defines expected artifacts
- "behavioral": Validates that tests use expected artifacts
- "schema": Validates only manifest schema, semantics, and version (skips file checks)

Example:
    mode: ValidationMode = "implementation"
    if mode == "behavioral":
        validate_tests()
    elif mode == "schema":
        validate_schema_only()
    else:
        validate_implementation()
"""


# ============================================================================
# Core Validation Types
# ============================================================================


class ValidationResult(TypedDict):
    """Result of a validation operation.

    Contains validation status, any errors encountered, and warnings
    generated during the validation process.

    Attributes:
        valid: Whether the validation passed without errors
        errors: List of error messages that caused validation failure
        warnings: List of warning messages for potential issues

    Example:
        result: ValidationResult = {
            "valid": False,
            "errors": ["Missing required artifact 'MyClass'"],
            "warnings": ["Deprecated pattern detected"]
        }
    """

    valid: bool
    errors: List[str]
    warnings: List[str]


# ============================================================================
# Artifact Definition Types
# ============================================================================


class ArtifactDict(TypedDict, total=False):
    """Dictionary representation of a code artifact.

    Represents artifacts like functions, classes, and attributes with their
    metadata. Used for both expected artifacts (from manifests) and discovered
    artifacts (from implementation parsing).

    Required Fields:
        type: Artifact type ("function", "class", "attribute", "parameter")
        name: Artifact identifier/name

    Optional Fields:
        args: Function parameters with name/type pairs
        returns: Return type annotation for functions
        bases: Base classes for class inheritance
        artifactKind: Additional kind metadata ("type", "behavior", etc.)

    Example:
        function_artifact: ArtifactDict = {
            "type": "function",
            "name": "validate_manifest",
            "args": [{"name": "path", "type": "str"}],
            "returns": "ValidationResult"
        }

        class_artifact: ArtifactDict = {
            "type": "class",
            "name": "Validator",
            "bases": ["BaseValidator"],
            "artifactKind": "type"
        }
    """

    # Required fields (must be present when total=False is overridden)
    type: str
    name: str

    # Optional fields for various artifact types
    args: Optional[List[Dict[str, str]]]
    returns: Optional[str]
    bases: Optional[List[str]]
    artifactKind: Optional[str]


class ExpectedArtifacts(TypedDict):
    """Expected artifacts for a file as declared in manifest.

    Specifies what artifacts should be present in a given file according
    to the manifest specification. Used during validation to check if
    implementation matches expectations.

    Attributes:
        file: Path to the file containing the expected artifacts
        contains: List of artifact definitions that should be present

    Example:
        expected: ExpectedArtifacts = {
            "file": "src/validators.py",
            "contains": [
                {"type": "function", "name": "validate"},
                {"type": "class", "name": "Validator"}
            ]
        }
    """

    file: str
    contains: List[ArtifactDict]


# ============================================================================
# Error and Diagnostic Types
# ============================================================================


class TypeMismatch(TypedDict):
    """Information about a type mismatch between expected and actual artifacts.

    Used for detailed error reporting during type validation. Captures
    specific information about what was expected versus what was found.

    Attributes:
        artifact_name: Name of the artifact with the mismatch
        expected_type: The type that was expected
        actual_type: The type that was actually found
        mismatch_kind: Category of mismatch ("return_type", "parameter_type", etc.)

    Example:
        mismatch: TypeMismatch = {
            "artifact_name": "validate_file",
            "expected_type": "bool",
            "actual_type": "Optional[bool]",
            "mismatch_kind": "return_type"
        }
    """

    artifact_name: str
    expected_type: str
    actual_type: str
    mismatch_kind: str


# ============================================================================
# Function Signature Types
# ============================================================================


class ParameterInfo(TypedDict, total=False):
    """Information about a function parameter.

    Represents parameter metadata including name and optional type annotation.
    Used for tracking function signatures during AST parsing and validation.

    Required Fields:
        name: Parameter identifier

    Optional Fields:
        type: Type annotation as a string representation

    Examples:
        typed_param: ParameterInfo = {"name": "path", "type": "str"}
        untyped_param: ParameterInfo = {"name": "data"}  # type is optional
        self_param: ParameterInfo = {"name": "self"}  # typically untyped
    """

    name: str  # Parameter name/identifier
    type: Optional[str]  # Optional type annotation string


class FunctionTypeInfo(TypedDict):
    """Type information for a function or method.

    Captures complete function signature including parameters and return type.
    Used by the AST collector to track discovered function definitions and
    validate against expected signatures from manifests.

    Attributes:
        parameters: Ordered list of function parameters
        returns: Optional return type annotation

    Examples:
        # Simple function with typed parameters
        func_info: FunctionTypeInfo = {
            "parameters": [{"name": "path", "type": "str"}],
            "returns": "bool"
        }

        # Method with self parameter
        method_info: FunctionTypeInfo = {
            "parameters": [
                {"name": "self"},
                {"name": "data", "type": "Dict[str, Any]"}
            ],
            "returns": "ValidationResult"
        }
    """

    parameters: List[ParameterInfo]  # Ordered list of parameters
    returns: Optional[str]  # Optional return type annotation


class CollectorTypeInfo(TypedDict):
    """Type information collected from implementation parsing.

    Aggregates all discovered type information from AST parsing,
    organizing functions and methods for validation purposes.
    This structure mirrors the organization found in Python modules
    with top-level functions and class methods separated.

    Attributes:
        functions: Mapping of function names to their type information
        methods: Nested mapping of class names to method type information

    Example:
        collector_info: CollectorTypeInfo = {
            "functions": {
                "validate": {
                    "parameters": [{"name": "path", "type": "str"}],
                    "returns": "ValidationResult"
                },
                "parse_manifest": {
                    "parameters": [{"name": "data", "type": "Dict[str, Any]"}],
                    "returns": "ManifestData"
                }
            },
            "methods": {
                "Validator": {
                    "__init__": {
                        "parameters": [{"name": "self"}, {"name": "strict", "type": "bool"}],
                        "returns": None
                    },
                    "check": {
                        "parameters": [{"name": "self"}],
                        "returns": "bool"
                    }
                },
                "Parser": {
                    "parse": {
                        "parameters": [{"name": "self"}, {"name": "source", "type": "str"}],
                        "returns": "ArtifactDict"
                    }
                }
            }
        }
    """

    functions: Dict[str, FunctionTypeInfo]  # Top-level function signatures
    methods: Dict[
        str, Dict[str, FunctionTypeInfo]
    ]  # Class method signatures by class name


# ============================================================================
# Implementation Discovery Types
# ============================================================================


class ImplementationArtifacts(TypedDict):
    """Artifacts actually found in implementation files.

    Represents the discovered artifacts from parsing implementation code.
    Used to compare what actually exists versus what was expected from
    the manifest.

    Attributes:
        file: Path to the implementation file that was parsed
        found: List of artifacts that were discovered in the file

    Example:
        discovered: ImplementationArtifacts = {
            "file": "src/validators.py",
            "found": [
                {"type": "function", "name": "validate", "returns": "bool"},
                {"type": "class", "name": "FileValidator"}
            ]
        }
    """

    file: str
    found: List[ArtifactDict]
