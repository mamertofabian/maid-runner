"""Behavioral tests for Task-077: TypeScript parameter type annotation extraction.

This test suite validates that the TypeScript validator properly extracts type
annotations from function/method parameters and includes them in snapshot manifests,
matching the format used by Python snapshot generation.

Test Organization:
- Basic parameter type extraction
- Type annotation helper function
- Complex type scenarios (unions, generics, optional)
- Integration with snapshot generation
- Edge cases and error handling
"""

import sys
from pathlib import Path

# Add parent directory to path to enable imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

# Import private test modules for task-077 private artifacts
from tests._test_task_077_private_helpers import (  # noqa: F401
    TestExtractParameters,
    TestExtractTypeFromNode,
)


# =============================================================================
# SECTION 1: Module Imports
# =============================================================================


class TestModuleImports:
    """Test that required methods can be imported and called."""

    def test_import_typescript_validator(self):
        """TypeScriptValidator class must be importable."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        assert TypeScriptValidator is not None

    def test_validator_has_extract_parameters_method(self):
        """TypeScriptValidator must have _extract_parameters method."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        validator = TypeScriptValidator()
        assert hasattr(validator, "_extract_parameters")
        assert callable(getattr(validator, "_extract_parameters"))

    def test_validator_has_extract_type_from_node_method(self):
        """TypeScriptValidator must have _extract_type_from_node method."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        validator = TypeScriptValidator()
        assert hasattr(validator, "_extract_type_from_node")
        assert callable(getattr(validator, "_extract_type_from_node"))


# =============================================================================
# SECTION 2: Basic Parameter Type Extraction
# =============================================================================


class TestBasicParameterTypeExtraction:
    """Test extraction of parameter type annotations from TypeScript functions."""

    def test_extract_simple_typed_parameter(self, tmp_path):
        """Function with simple typed parameter must extract type information."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function greet(name: string) {
    return `Hello, ${name}`;
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        # Verify function was found
        assert "greet" in artifacts["found_functions"]

        # Verify parameters include type information
        params = artifacts["found_functions"]["greet"]
        assert len(params) == 1

        # Check if parameter is a string (old format) or dict (new format)
        param = params[0]
        if isinstance(param, dict):
            assert param["name"] == "name"
            assert param.get("type") == "string"
        else:
            # Old format - just a string, test will fail as expected (Red phase)
            pytest.fail(
                f"Expected parameter dict with 'name' and 'type', got string: {param}"
            )

    def test_extract_multiple_typed_parameters(self, tmp_path):
        """Function with multiple typed parameters must extract all types."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function calculate(x: number, y: number, operation: string) {
    return x + y;
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        params = artifacts["found_functions"]["calculate"]
        assert len(params) == 3

        # Verify all parameters have type information
        if isinstance(params[0], dict):
            assert params[0] == {"name": "x", "type": "number"}
            assert params[1] == {"name": "y", "type": "number"}
            assert params[2] == {"name": "operation", "type": "string"}
        else:
            pytest.fail("Parameters should be dicts with type information")

    def test_extract_boolean_typed_parameter(self, tmp_path):
        """Function with boolean typed parameter must extract type."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function toggle(enabled: boolean) {
    return !enabled;
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        params = artifacts["found_functions"]["toggle"]
        if isinstance(params[0], dict):
            assert params[0]["type"] == "boolean"
        else:
            pytest.fail("Expected dict with type information")


# =============================================================================
# SECTION 3: Optional and Union Type Parameters
# =============================================================================


class TestOptionalAndUnionTypes:
    """Test extraction of optional parameters and union types."""

    def test_extract_optional_parameter(self, tmp_path):
        """Optional parameter (name?: type) must extract type."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function greet(name?: string) {
    return name || "Guest";
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        params = artifacts["found_functions"]["greet"]
        assert len(params) == 1

        if isinstance(params[0], dict):
            assert params[0]["name"] == "name"
            assert params[0]["type"] == "string"
        else:
            pytest.fail("Expected dict with type information")

    def test_extract_union_type_parameter(self, tmp_path):
        """Parameter with union type (string | number) must extract full type."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function process(value: string | number) {
    return String(value);
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        params = artifacts["found_functions"]["process"]
        if isinstance(params[0], dict):
            assert params[0]["name"] == "value"
            # Type should be "string | number" (union type preserved)
            assert "string" in params[0]["type"]
            assert "number" in params[0]["type"]
        else:
            pytest.fail("Expected dict with type information")

    def test_extract_union_type_with_null(self, tmp_path):
        """Parameter with null union (string | null) must extract full type."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function display(message: string | null) {
    console.log(message);
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        params = artifacts["found_functions"]["display"]
        if isinstance(params[0], dict):
            assert params[0]["name"] == "message"
            assert "string" in params[0]["type"]
            assert "null" in params[0]["type"]
        else:
            pytest.fail("Expected dict with type information")


# =============================================================================
# SECTION 4: Complex Type Annotations
# =============================================================================


class TestComplexTypeAnnotations:
    """Test extraction of complex type annotations (generics, arrays, custom types)."""

    def test_extract_array_type_parameter(self, tmp_path):
        """Parameter with array type (string[]) must extract type."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function joinStrings(items: string[]) {
    return items.join(", ");
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        params = artifacts["found_functions"]["joinStrings"]
        if isinstance(params[0], dict):
            assert params[0]["name"] == "items"
            # Type should contain "string" and array notation
            type_str = params[0]["type"]
            assert "string" in type_str
        else:
            pytest.fail("Expected dict with type information")

    def test_extract_generic_array_type(self, tmp_path):
        """Parameter with Array<T> generic must extract type."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function process(items: Array<number>) {
    return items.reduce((a, b) => a + b, 0);
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        params = artifacts["found_functions"]["process"]
        if isinstance(params[0], dict):
            assert params[0]["name"] == "items"
            type_str = params[0]["type"]
            assert "Array" in type_str
            assert "number" in type_str
        else:
            pytest.fail("Expected dict with type information")

    def test_extract_custom_type_parameter(self, tmp_path):
        """Parameter with custom type/interface must extract type name."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
interface User {
    id: string;
    name: string;
}

function getUser(user: User) {
    return user.name;
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        params = artifacts["found_functions"]["getUser"]
        if isinstance(params[0], dict):
            assert params[0]["name"] == "user"
            assert params[0]["type"] == "User"
        else:
            pytest.fail("Expected dict with type information")

    def test_extract_generic_promise_type(self, tmp_path):
        """Parameter with Promise<T> generic must extract type."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
async function waitFor(promise: Promise<string>) {
    return await promise;
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        params = artifacts["found_functions"]["waitFor"]
        if isinstance(params[0], dict):
            assert params[0]["name"] == "promise"
            type_str = params[0]["type"]
            assert "Promise" in type_str
            assert "string" in type_str
        else:
            pytest.fail("Expected dict with type information")

    def test_extract_complex_generic_type(self, tmp_path):
        """Parameter with complex generic (Record<string, number>) must extract type."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function countItems(items: Record<string, number>) {
    return Object.keys(items).length;
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        params = artifacts["found_functions"]["countItems"]
        if isinstance(params[0], dict):
            assert params[0]["name"] == "items"
            type_str = params[0]["type"]
            assert "Record" in type_str
            assert "string" in type_str
            assert "number" in type_str
        else:
            pytest.fail("Expected dict with type information")


# =============================================================================
# SECTION 5: Rest Parameters and Destructuring
# =============================================================================


class TestRestParametersAndDestructuring:
    """Test extraction of rest parameters and destructured parameters."""

    def test_extract_rest_parameter_with_type(self, tmp_path):
        """Rest parameter (...args: type[]) must extract type."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function sum(...numbers: number[]) {
    return numbers.reduce((a, b) => a + b, 0);
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        params = artifacts["found_functions"]["sum"]
        assert len(params) == 1

        if isinstance(params[0], dict):
            assert params[0]["name"] == "numbers"
            type_str = params[0]["type"]
            # Type should indicate array of numbers
            assert "number" in type_str
        else:
            pytest.fail("Expected dict with type information")

    def test_extract_typed_rest_parameter_strings(self, tmp_path):
        """Rest parameter with string type must extract correctly."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function concat(...strings: string[]) {
    return strings.join("");
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        params = artifacts["found_functions"]["concat"]
        if isinstance(params[0], dict):
            assert params[0]["name"] == "strings"
            assert "string" in params[0]["type"]
        else:
            pytest.fail("Expected dict with type information")


# =============================================================================
# SECTION 6: Method Parameter Types
# =============================================================================


class TestMethodParameterTypes:
    """Test extraction of parameter types from class methods."""

    def test_extract_method_parameter_types(self, tmp_path):
        """Class method parameters must include type information."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Calculator {
    add(x: number, y: number): number {
        return x + y;
    }
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        # Verify class and method were found
        assert "Calculator" in artifacts["found_methods"]
        assert "add" in artifacts["found_methods"]["Calculator"]

        params = artifacts["found_methods"]["Calculator"]["add"]
        assert len(params) == 2

        if isinstance(params[0], dict):
            assert params[0] == {"name": "x", "type": "number"}
            assert params[1] == {"name": "y", "type": "number"}
        else:
            pytest.fail("Method parameters should include type information")

    def test_extract_constructor_parameter_types(self, tmp_path):
        """Constructor parameters must include type information."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class User {
    constructor(public id: string, public name: string) {}
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        # Constructor is skipped by the validator (see line 669 in validator)
        # but we verify it doesn't crash
        assert "User" in artifacts["found_classes"]


# =============================================================================
# SECTION 7: Type Extraction Helper Function
# =============================================================================


class TestTypeExtractionHelper:
    """Test the _extract_type_from_node helper function."""

    def test_extract_type_from_simple_type_node(self, tmp_path):
        """_extract_type_from_node must extract simple type annotations."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function test(param: string) {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))

        # Find the type_annotation node
        def find_type_annotation(node):
            if node.type == "type_annotation":
                return node
            for child in node.children:
                result = find_type_annotation(child)
                if result:
                    return result
            return None

        type_annotation_node = find_type_annotation(tree.root_node)
        assert type_annotation_node is not None

        # Find the actual type node (child of type_annotation)
        type_node = None
        for child in type_annotation_node.children:
            if child.type in ("predefined_type", "type_identifier"):
                type_node = child
                break

        assert type_node is not None

        # Extract type
        type_text = validator._extract_type_from_node(type_node, source_code)
        assert type_text == "string"

    def test_extract_type_from_union_type_node(self, tmp_path):
        """_extract_type_from_node must extract union types."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function test(param: string | number) {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))

        # Find the union_type node
        def find_union_type(node):
            if node.type == "union_type":
                return node
            for child in node.children:
                result = find_union_type(child)
                if result:
                    return result
            return None

        union_node = find_union_type(tree.root_node)
        assert union_node is not None

        # Extract type
        type_text = validator._extract_type_from_node(union_node, source_code)
        assert "string" in type_text
        assert "number" in type_text
        assert "|" in type_text


# =============================================================================
# SECTION 8: Integration with Snapshot Generation
# =============================================================================


class TestSnapshotIntegration:
    """Test integration with snapshot generation (end-to-end)."""

    def test_snapshot_includes_parameter_types(self, tmp_path):
        """Generated snapshot manifest must include parameter type information."""
        from maid_runner.cli.snapshot import generate_snapshot
        import json

        ts_file = tmp_path / "service.ts"
        ts_file.write_text(
            """
export function getUser(id: string, active: boolean) {
    return { id, active };
}
"""
        )

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest_path = generate_snapshot(
            str(ts_file), str(manifest_dir), skip_test_stub=True
        )

        # Load manifest
        with open(manifest_path) as f:
            manifest = json.load(f)

        # Find the function artifact
        artifacts = manifest["expectedArtifacts"]["contains"]
        functions = [a for a in artifacts if a.get("name") == "getUser"]
        assert len(functions) == 1

        func = functions[0]
        assert "args" in func or "parameters" in func

        # Get parameters (try both keys for compatibility)
        params = func.get("args", func.get("parameters", []))
        assert len(params) == 2

        # Verify types are included
        if isinstance(params[0], dict):
            assert params[0]["name"] == "id"
            assert params[0]["type"] == "string"
            assert params[1]["name"] == "active"
            assert params[1]["type"] == "boolean"
        else:
            pytest.fail(
                "Snapshot should include parameter types in enhanced format (dicts)"
            )

    def test_snapshot_method_parameter_types(self, tmp_path):
        """Snapshot of class method must include parameter types."""
        from maid_runner.cli.snapshot import generate_snapshot
        import json

        ts_file = tmp_path / "calculator.ts"
        ts_file.write_text(
            """
export class Calculator {
    multiply(x: number, y: number): number {
        return x * y;
    }
}
"""
        )

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest_path = generate_snapshot(
            str(ts_file), str(manifest_dir), skip_test_stub=True
        )

        with open(manifest_path) as f:
            manifest = json.load(f)

        # Find the method artifact
        artifacts = manifest["expectedArtifacts"]["contains"]
        methods = [
            a for a in artifacts if a.get("name") == "multiply" and a.get("class")
        ]
        assert len(methods) == 1

        method = methods[0]
        params = method.get("args", method.get("parameters", []))

        if isinstance(params[0], dict):
            assert params[0]["type"] == "number"
            assert params[1]["type"] == "number"
        else:
            pytest.fail("Method parameters should include type information")


# =============================================================================
# SECTION 9: Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_parameter_without_type_annotation(self, tmp_path):
        """Parameters without type annotations must not crash."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function legacy(x, y) {
    return x + y;
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        params = artifacts["found_functions"]["legacy"]
        assert len(params) == 2

        # Parameters should still be extracted, even without types
        # They might be strings (old format) or dicts without 'type' key
        if isinstance(params[0], dict):
            assert params[0]["name"] in ("x", "y")
            # Type key might be absent or None
        else:
            # Old format - strings are acceptable for untyped params
            assert params[0] in ("x", "y")

    def test_implicit_any_type(self, tmp_path):
        """Parameters with implicit 'any' type must handle gracefully."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function process(data) {
    return data;
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        # Should not crash
        assert "process" in artifacts["found_functions"]

    def test_arrow_function_parameter_types(self, tmp_path):
        """Arrow function parameters must include type information."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
const greet = (name: string): string => {
    return `Hello, ${name}`;
};
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        params = artifacts["found_functions"]["greet"]
        if isinstance(params[0], dict):
            assert params[0]["name"] == "name"
            assert params[0]["type"] == "string"
        else:
            pytest.fail("Arrow function parameters should include type information")

    def test_interface_method_parameter_types(self, tmp_path):
        """Interface method signatures should not crash validator."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
interface Calculator {
    add(x: number, y: number): number;
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        # Should not crash
        assert "Calculator" in artifacts["found_classes"]


# =============================================================================
# SECTION 10: Comparison with Python Snapshot Behavior
# =============================================================================


class TestPythonComparison:
    """Test that TypeScript parameter extraction matches Python snapshot format."""

    def test_parameter_format_matches_python(self, tmp_path):
        """TypeScript parameter format must match Python snapshot format."""
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        # Python file with typed parameters
        py_file = tmp_path / "example.py"
        py_file.write_text(
            """
def greet(name: str, age: int) -> str:
    return f"Hello {name}, age {age}"
"""
        )

        # TypeScript file with typed parameters
        ts_file = tmp_path / "example.ts"
        ts_file.write_text(
            """
function greet(name: string, age: number): string {
    return `Hello ${name}, age ${age}`;
}
"""
        )

        py_artifacts = extract_artifacts_from_code(str(py_file))
        ts_artifacts = extract_artifacts_from_code(str(ts_file))

        # Find greet function in both
        py_func = next(
            (a for a in py_artifacts["artifacts"] if a.get("name") == "greet"), None
        )
        ts_func = next(
            (a for a in ts_artifacts["artifacts"] if a.get("name") == "greet"), None
        )

        assert py_func is not None
        assert ts_func is not None

        # Both should have args with same structure
        py_params = py_func.get("args", py_func.get("parameters", []))
        ts_params = ts_func.get("args", ts_func.get("parameters", []))

        # Both should be lists of dicts with 'name' and 'type' keys
        assert isinstance(py_params, list)
        assert isinstance(ts_params, list)
        assert len(py_params) == len(ts_params) == 2

        # Verify format consistency
        if isinstance(py_params[0], dict) and isinstance(ts_params[0], dict):
            assert "name" in py_params[0]
            assert "type" in py_params[0]
            assert "name" in ts_params[0]
            assert "type" in ts_params[0]
        else:
            pytest.fail(
                "Both Python and TypeScript should use dict format for typed parameters"
            )
