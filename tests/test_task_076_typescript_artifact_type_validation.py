"""Behavioral tests for Task-076: TypeScript artifact type validation support.

This test suite validates that the manifest validator recognizes and validates
TypeScript-specific artifact types (interface, type, enum, namespace) by treating
them as semantically equivalent to class declarations for validation purposes.

Test Organization:
- Constant imports and values
- Interface artifact validation
- Type alias artifact validation
- Enum artifact validation
- Namespace artifact validation
- Validation failure scenarios
- Integration with manifest validation
"""

import sys
from pathlib import Path

# Add parent directory to path to enable imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

# Import private test modules for task-076 private artifacts
from tests._test_task_076_private_helpers import (  # noqa: F401
    TestValidateSingleArtifact,
)


# =============================================================================
# SECTION 1: Constant Imports and Values
# =============================================================================


class TestTypeScriptArtifactTypeConstants:
    """Test that TypeScript artifact type constants exist and have correct values."""

    def test_interface_constant_exists(self):
        """_ARTIFACT_TYPE_INTERFACE constant must exist."""
        from maid_runner.validators.manifest_validator import (
            _ARTIFACT_TYPE_INTERFACE,
        )

        assert _ARTIFACT_TYPE_INTERFACE is not None

    def test_interface_constant_value(self):
        """_ARTIFACT_TYPE_INTERFACE must have value 'interface'."""
        from maid_runner.validators.manifest_validator import (
            _ARTIFACT_TYPE_INTERFACE,
        )

        assert _ARTIFACT_TYPE_INTERFACE == "interface"

    def test_type_constant_exists(self):
        """_ARTIFACT_TYPE_TYPE constant must exist."""
        from maid_runner.validators.manifest_validator import _ARTIFACT_TYPE_TYPE

        assert _ARTIFACT_TYPE_TYPE is not None

    def test_type_constant_value(self):
        """_ARTIFACT_TYPE_TYPE must have value 'type'."""
        from maid_runner.validators.manifest_validator import _ARTIFACT_TYPE_TYPE

        assert _ARTIFACT_TYPE_TYPE == "type"

    def test_enum_constant_exists(self):
        """_ARTIFACT_TYPE_ENUM constant must exist."""
        from maid_runner.validators.manifest_validator import _ARTIFACT_TYPE_ENUM

        assert _ARTIFACT_TYPE_ENUM is not None

    def test_enum_constant_value(self):
        """_ARTIFACT_TYPE_ENUM must have value 'enum'."""
        from maid_runner.validators.manifest_validator import _ARTIFACT_TYPE_ENUM

        assert _ARTIFACT_TYPE_ENUM == "enum"

    def test_namespace_constant_exists(self):
        """_ARTIFACT_TYPE_NAMESPACE constant must exist."""
        from maid_runner.validators.manifest_validator import (
            _ARTIFACT_TYPE_NAMESPACE,
        )

        assert _ARTIFACT_TYPE_NAMESPACE is not None

    def test_namespace_constant_value(self):
        """_ARTIFACT_TYPE_NAMESPACE must have value 'namespace'."""
        from maid_runner.validators.manifest_validator import (
            _ARTIFACT_TYPE_NAMESPACE,
        )

        assert _ARTIFACT_TYPE_NAMESPACE == "namespace"


# =============================================================================
# SECTION 2: Interface Artifact Validation
# =============================================================================


class TestInterfaceArtifactValidation:
    """Test validation of TypeScript interface artifacts."""

    def test_validate_interface_in_typescript_file(self, tmp_path: Path):
        """Interface artifact must validate successfully when interface exists in TypeScript file."""
        from maid_runner.validators.manifest_validator import validate_with_ast

        # Create TypeScript file with interface
        ts_file = tmp_path / "user.ts"
        ts_file.write_text(
            """
export interface User {
    id: string;
    name: string;
    email: string;
}
"""
        )

        # Create manifest with interface artifact
        manifest = {
            "expectedArtifacts": {"contains": [{"type": "interface", "name": "User"}]}
        }

        # Should not raise an error
        validate_with_ast(manifest, str(ts_file))

    def test_validate_multiple_interfaces(self, tmp_path: Path):
        """Multiple interface artifacts must validate successfully."""
        from maid_runner.validators.manifest_validator import validate_with_ast

        ts_file = tmp_path / "types.ts"
        ts_file.write_text(
            """
export interface User {
    id: string;
    name: string;
}

export interface Product {
    sku: string;
    price: number;
}

export interface Order {
    orderId: string;
    items: Product[];
}
"""
        )

        manifest = {
            "expectedArtifacts": {
                "contains": [
                    {"type": "interface", "name": "User"},
                    {"type": "interface", "name": "Product"},
                    {"type": "interface", "name": "Order"},
                ]
            }
        }

        # Should not raise an error
        validate_with_ast(manifest, str(ts_file))

    def test_interface_validation_fails_when_missing(self, tmp_path: Path):
        """Interface validation must fail when declared interface doesn't exist."""
        from maid_runner.validators.manifest_validator import (
            validate_with_ast,
            AlignmentError,
        )

        ts_file = tmp_path / "types.ts"
        ts_file.write_text(
            """
export interface User {
    id: string;
}
"""
        )

        manifest = {
            "expectedArtifacts": {
                "contains": [
                    {"type": "interface", "name": "User"},
                    {"type": "interface", "name": "Product"},  # Doesn't exist
                ]
            }
        }

        with pytest.raises(AlignmentError, match="Product"):
            validate_with_ast(manifest, str(ts_file))


# =============================================================================
# SECTION 3: Type Alias Artifact Validation
# =============================================================================


class TestTypeAliasArtifactValidation:
    """Test validation of TypeScript type alias artifacts."""

    def test_validate_type_alias_in_typescript_file(self, tmp_path: Path):
        """Type alias artifact must validate successfully when type exists in TypeScript file."""
        from maid_runner.validators.manifest_validator import validate_with_ast

        ts_file = tmp_path / "types.ts"
        ts_file.write_text(
            """
export type UserID = string;
export type Status = 'active' | 'inactive' | 'pending';
"""
        )

        manifest = {
            "expectedArtifacts": {
                "contains": [
                    {"type": "type", "name": "UserID"},
                    {"type": "type", "name": "Status"},
                ]
            }
        }

        # Should not raise an error
        validate_with_ast(manifest, str(ts_file))

    def test_validate_complex_type_aliases(self, tmp_path: Path):
        """Complex type aliases must validate successfully."""
        from maid_runner.validators.manifest_validator import validate_with_ast

        ts_file = tmp_path / "advanced-types.ts"
        ts_file.write_text(
            """
export type ID = string | number;
export type UserRole = 'admin' | 'user' | 'guest';
export type Callback = (data: string) => void;
export type Result<T> = { success: true; data: T } | { success: false; error: string };
"""
        )

        manifest = {
            "expectedArtifacts": {
                "contains": [
                    {"type": "type", "name": "ID"},
                    {"type": "type", "name": "UserRole"},
                    {"type": "type", "name": "Callback"},
                    {"type": "type", "name": "Result"},
                ]
            }
        }

        # Should not raise an error
        validate_with_ast(manifest, str(ts_file))

    def test_type_alias_validation_fails_when_missing(self, tmp_path: Path):
        """Type alias validation must fail when declared type doesn't exist."""
        from maid_runner.validators.manifest_validator import (
            validate_with_ast,
            AlignmentError,
        )

        ts_file = tmp_path / "types.ts"
        ts_file.write_text(
            """
export type UserID = string;
"""
        )

        manifest = {
            "expectedArtifacts": {
                "contains": [
                    {"type": "type", "name": "UserID"},
                    {"type": "type", "name": "ProductID"},  # Doesn't exist
                ]
            }
        }

        with pytest.raises(AlignmentError, match="ProductID"):
            validate_with_ast(manifest, str(ts_file))


# =============================================================================
# SECTION 4: Enum Artifact Validation
# =============================================================================


class TestEnumArtifactValidation:
    """Test validation of TypeScript enum artifacts."""

    def test_validate_enum_in_typescript_file(self, tmp_path: Path):
        """Enum artifact must validate successfully when enum exists in TypeScript file."""
        from maid_runner.validators.manifest_validator import validate_with_ast

        ts_file = tmp_path / "enums.ts"
        ts_file.write_text(
            """
export enum Status {
    Active = 'active',
    Inactive = 'inactive',
    Pending = 'pending'
}
"""
        )

        manifest = {
            "expectedArtifacts": {"contains": [{"type": "enum", "name": "Status"}]}
        }

        # Should not raise an error
        validate_with_ast(manifest, str(ts_file))

    def test_validate_multiple_enums(self, tmp_path: Path):
        """Multiple enum artifacts must validate successfully."""
        from maid_runner.validators.manifest_validator import validate_with_ast

        ts_file = tmp_path / "enums.ts"
        ts_file.write_text(
            """
export enum Status {
    Active,
    Inactive,
    Pending
}

export enum Role {
    Admin = 'admin',
    User = 'user',
    Guest = 'guest'
}

export enum Color {
    Red = 1,
    Green = 2,
    Blue = 3
}
"""
        )

        manifest = {
            "expectedArtifacts": {
                "contains": [
                    {"type": "enum", "name": "Status"},
                    {"type": "enum", "name": "Role"},
                    {"type": "enum", "name": "Color"},
                ]
            }
        }

        # Should not raise an error
        validate_with_ast(manifest, str(ts_file))

    def test_enum_validation_fails_when_missing(self, tmp_path: Path):
        """Enum validation must fail when declared enum doesn't exist."""
        from maid_runner.validators.manifest_validator import (
            validate_with_ast,
            AlignmentError,
        )

        ts_file = tmp_path / "enums.ts"
        ts_file.write_text(
            """
export enum Status {
    Active,
    Inactive
}
"""
        )

        manifest = {
            "expectedArtifacts": {
                "contains": [
                    {"type": "enum", "name": "Status"},
                    {"type": "enum", "name": "Priority"},  # Doesn't exist
                ]
            }
        }

        with pytest.raises(AlignmentError, match="Priority"):
            validate_with_ast(manifest, str(ts_file))


# =============================================================================
# SECTION 5: Namespace Artifact Validation
# =============================================================================


class TestNamespaceArtifactValidation:
    """Test validation of TypeScript namespace artifacts."""

    def test_validate_namespace_in_typescript_file(self, tmp_path: Path):
        """Namespace artifact must validate successfully when namespace exists in TypeScript file."""
        from maid_runner.validators.manifest_validator import validate_with_ast

        ts_file = tmp_path / "utils.ts"
        ts_file.write_text(
            """
export namespace Utils {
    export function formatDate(date: Date): string {
        return date.toISOString();
    }
}
"""
        )

        manifest = {
            "expectedArtifacts": {
                "contains": [
                    {"type": "namespace", "name": "Utils"},
                    # TypeScript validator extracts namespace members as top-level functions
                    {"type": "function", "name": "formatDate"},
                ]
            }
        }

        # Should not raise an error
        validate_with_ast(manifest, str(ts_file))

    def test_validate_nested_namespace(self, tmp_path: Path):
        """Nested namespace artifacts must validate successfully."""
        from maid_runner.validators.manifest_validator import validate_with_ast

        ts_file = tmp_path / "api.ts"
        ts_file.write_text(
            """
export namespace API {
    export namespace V1 {
        export function getUsers() {
            return [];
        }
    }

    export namespace V2 {
        export function getUsers() {
            return [];
        }
    }
}
"""
        )

        manifest = {
            "expectedArtifacts": {
                "contains": [
                    {"type": "namespace", "name": "API"},
                    {"type": "namespace", "name": "V1"},
                    {"type": "namespace", "name": "V2"},
                    # TypeScript validator extracts namespace member functions
                    {"type": "function", "name": "getUsers"},
                ]
            }
        }

        # Should not raise an error
        validate_with_ast(manifest, str(ts_file))

    def test_namespace_validation_fails_when_missing(self, tmp_path: Path):
        """Namespace validation must fail when declared namespace doesn't exist."""
        from maid_runner.validators.manifest_validator import (
            validate_with_ast,
            AlignmentError,
        )

        ts_file = tmp_path / "utils.ts"
        ts_file.write_text(
            """
export namespace Utils {
    export function formatDate(date: Date): string {
        return date.toISOString();
    }
}
"""
        )

        manifest = {
            "expectedArtifacts": {
                "contains": [
                    {"type": "namespace", "name": "Utils"},
                    {"type": "namespace", "name": "Helpers"},  # Doesn't exist
                ]
            }
        }

        with pytest.raises(AlignmentError, match="Helpers"):
            validate_with_ast(manifest, str(ts_file))


# =============================================================================
# SECTION 6: Mixed TypeScript Artifact Validation
# =============================================================================


class TestMixedTypeScriptArtifacts:
    """Test validation with mixed TypeScript artifact types."""

    def test_validate_mixed_typescript_artifacts(self, tmp_path: Path):
        """Mixed TypeScript artifacts (interface, type, enum, namespace) must validate together."""
        from maid_runner.validators.manifest_validator import validate_with_ast

        ts_file = tmp_path / "complete.ts"
        ts_file.write_text(
            """
export interface User {
    id: string;
    name: string;
    status: Status;
}

export type UserID = string;

export enum Status {
    Active = 'active',
    Inactive = 'inactive'
}

export namespace UserUtils {
    export function validateUser(user: User): boolean {
        return user.id.length > 0;
    }
}

export class UserService {
    getUser(id: UserID): User {
        return { id, name: "Test", status: Status.Active };
    }
}
"""
        )

        manifest = {
            "expectedArtifacts": {
                "contains": [
                    {"type": "interface", "name": "User"},
                    {"type": "type", "name": "UserID"},
                    {"type": "enum", "name": "Status"},
                    {"type": "namespace", "name": "UserUtils"},
                    {"type": "class", "name": "UserService"},
                    # TypeScript validator extracts namespace member functions
                    {"type": "function", "name": "validateUser"},
                    # TypeScript validator extracts class methods
                    {"type": "function", "name": "getUser", "class": "UserService"},
                ]
            }
        }

        # Should not raise an error
        validate_with_ast(manifest, str(ts_file))

    def test_typescript_artifacts_with_methods(self, tmp_path: Path):
        """TypeScript artifacts with interface methods must validate."""
        from maid_runner.validators.manifest_validator import validate_with_ast

        ts_file = tmp_path / "service.ts"
        ts_file.write_text(
            """
export interface IUserService {
    getUser(id: string): User;
    updateUser(id: string, data: Partial<User>): void;
}

export class UserService implements IUserService {
    getUser(id: string): User {
        return { id, name: "Test" };
    }

    updateUser(id: string, data: Partial<User>): void {
        // Implementation
    }
}
"""
        )

        manifest = {
            "expectedArtifacts": {
                "contains": [
                    {"type": "interface", "name": "IUserService"},
                    {"type": "class", "name": "UserService"},
                    # TypeScript validator extracts class methods
                    {"type": "function", "name": "getUser", "class": "UserService"},
                    {"type": "function", "name": "updateUser", "class": "UserService"},
                ]
            }
        }

        # Should not raise an error
        validate_with_ast(manifest, str(ts_file))


# =============================================================================
# SECTION 7: Edge Cases and Error Scenarios
# =============================================================================


class TestTypeScriptValidationEdgeCases:
    """Test edge cases and error scenarios for TypeScript artifact validation."""

    def test_empty_typescript_file_fails_validation(self, tmp_path: Path):
        """Empty TypeScript file must fail validation when artifacts are expected."""
        from maid_runner.validators.manifest_validator import (
            validate_with_ast,
            AlignmentError,
        )

        ts_file = tmp_path / "empty.ts"
        ts_file.write_text("")

        manifest = {
            "expectedArtifacts": {"contains": [{"type": "interface", "name": "User"}]}
        }

        with pytest.raises(AlignmentError, match="User"):
            validate_with_ast(manifest, str(ts_file))

    def test_typescript_file_with_only_imports(self, tmp_path: Path):
        """TypeScript file with only imports must fail validation when artifacts are expected."""
        from maid_runner.validators.manifest_validator import (
            validate_with_ast,
            AlignmentError,
        )

        ts_file = tmp_path / "imports.ts"
        ts_file.write_text(
            """
import { Something } from './other';
import type { User } from './user';
"""
        )

        manifest = {
            "expectedArtifacts": {
                "contains": [
                    {"type": "interface", "name": "User"}  # Imported, not defined
                ]
            }
        }

        with pytest.raises(AlignmentError, match="User"):
            validate_with_ast(manifest, str(ts_file))

    def test_case_sensitive_typescript_artifact_names(self, tmp_path: Path):
        """TypeScript artifact names must be case-sensitive."""
        from maid_runner.validators.manifest_validator import (
            validate_with_ast,
            AlignmentError,
        )

        ts_file = tmp_path / "types.ts"
        ts_file.write_text(
            """
export interface User {
    id: string;
}
"""
        )

        manifest = {
            "expectedArtifacts": {
                "contains": [{"type": "interface", "name": "user"}]  # Wrong case
            }
        }

        with pytest.raises(AlignmentError, match="user"):
            validate_with_ast(manifest, str(ts_file))


# =============================================================================
# SECTION 9: Backward Compatibility
# =============================================================================


class TestBackwardCompatibility:
    """Test that TypeScript artifact support doesn't break existing Python validation."""

    def test_python_class_validation_still_works(self, tmp_path: Path):
        """Python class validation must continue to work with TypeScript support."""
        from maid_runner.validators.manifest_validator import validate_with_ast

        py_file = tmp_path / "user.py"
        py_file.write_text(
            """
class User:
    def __init__(self, name):
        self.name = name
"""
        )

        manifest = {
            "expectedArtifacts": {"contains": [{"type": "class", "name": "User"}]}
        }

        # Should not raise an error
        validate_with_ast(manifest, str(py_file))

    def test_python_function_validation_still_works(self, tmp_path: Path):
        """Python function validation must continue to work with TypeScript support."""
        from maid_runner.validators.manifest_validator import validate_with_ast

        py_file = tmp_path / "utils.py"
        py_file.write_text(
            """
def validate_user(user):
    return user is not None
"""
        )

        manifest = {
            "expectedArtifacts": {
                "contains": [{"type": "function", "name": "validate_user"}]
            }
        }

        # Should not raise an error
        validate_with_ast(manifest, str(py_file))
