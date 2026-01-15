"""Behavioral tests for Task-078: TypeScript arrow function detection in class and object properties.

This test suite validates that the TypeScript validator's _extract_arrow_functions()
method correctly detects arrow functions defined as:
- Class properties (e.g., handleClick = (e) => {})
- Object properties (e.g., { onClick: (e) => {} })

These patterns are common in React components and modern JavaScript/TypeScript code,
but were previously missed by the validator which only detected arrow functions in
variable declarations (const/let).

Test Organization:
- Class property arrow functions (simple, static, private, typed parameters)
- Object property arrow functions (literals, nested objects)
- Parameter extraction with type annotations
- Integration with snapshot generation
- Edge cases (mixed methods, empty parameters, complex types)
- Real-world React patterns
"""

# =============================================================================
# SECTION 1: Module Imports and Method Availability
# =============================================================================


class TestModuleImports:
    """Test that required methods can be imported and called."""

    def test_import_typescript_validator(self):
        """TypeScriptValidator class must be importable."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        assert TypeScriptValidator is not None

    def test_validator_has_extract_arrow_functions_method(self):
        """TypeScriptValidator must have _extract_arrow_functions method."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        validator = TypeScriptValidator()
        assert hasattr(validator, "_extract_arrow_functions")
        assert callable(getattr(validator, "_extract_arrow_functions"))

    def test_extract_arrow_functions_callable(self, tmp_path):
        """_extract_arrow_functions method must be callable with tree and source_code."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text("const foo = () => {};")

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))

        # Should not raise an exception
        result = validator._extract_arrow_functions(tree, source_code)
        assert isinstance(result, dict)


# =============================================================================
# SECTION 2: Class Property Arrow Functions - Basic Cases
# =============================================================================


class TestClassPropertyArrowFunctions:
    """Test detection of arrow functions as class properties."""

    def test_simple_class_property_arrow_function(self, tmp_path):
        """Simple class property arrow function must be detected."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Foo {
    method = (x: number) => {
        return x * 2;
    }
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        # Verify the arrow function is detected
        assert "method" in arrow_functions, "Class property arrow function not detected"

        # Verify parameters
        params = arrow_functions["method"]
        assert len(params) == 1
        assert isinstance(params[0], dict)
        assert params[0]["name"] == "x"
        assert params[0]["type"] == "number"

    def test_multiple_class_property_arrow_functions(self, tmp_path):
        """Multiple class property arrow functions must all be detected."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Calculator {
    add = (a: number, b: number) => a + b
    multiply = (a: number, b: number) => a * b
    divide = (a: number, b: number) => a / b
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        # All three arrow functions should be detected
        assert "add" in arrow_functions
        assert "multiply" in arrow_functions
        assert "divide" in arrow_functions

        # Verify parameters for each
        assert len(arrow_functions["add"]) == 2
        assert len(arrow_functions["multiply"]) == 2
        assert len(arrow_functions["divide"]) == 2

    def test_class_property_without_type_annotation(self, tmp_path):
        """Class property arrow function without type annotations must be detected."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Foo {
    method = (x) => x * 2
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        assert "method" in arrow_functions
        params = arrow_functions["method"]
        assert len(params) == 1
        assert params[0]["name"] == "x"
        # Type may be absent or empty
        assert "type" not in params[0] or params[0].get("type") == ""

    def test_static_class_property_arrow_function(self, tmp_path):
        """Static class property arrow function must be detected."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Utilities {
    static format = (value: string) => value.toUpperCase()
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        assert "format" in arrow_functions
        params = arrow_functions["format"]
        assert len(params) == 1
        assert params[0]["name"] == "value"
        assert params[0]["type"] == "string"

    def test_private_class_property_arrow_function(self, tmp_path):
        """Private class property arrow functions should be excluded."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Foo {
    private helper = (x: number) => x * 2
    public publicHelper = (y: number) => y + 1
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        # Public arrow function should be detected
        assert "publicHelper" in arrow_functions
        params = arrow_functions["publicHelper"]
        assert params[0]["name"] == "y"
        # Private arrow function should NOT be detected
        assert "helper" not in arrow_functions


# =============================================================================
# SECTION 3: Class Property Arrow Functions - Parameter Variations
# =============================================================================


class TestClassPropertyParameters:
    """Test parameter extraction from class property arrow functions."""

    def test_empty_parameter_list(self, tmp_path):
        """Class property arrow function with no parameters must be handled."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Foo {
    getValue = () => 42
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        assert "getValue" in arrow_functions
        params = arrow_functions["getValue"]
        assert len(params) == 0

    def test_multiple_typed_parameters(self, tmp_path):
        """Class property arrow function with multiple typed parameters."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Formatter {
    format = (value: string, prefix: string, suffix: string) => {
        return prefix + value + suffix;
    }
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        params = arrow_functions["format"]
        assert len(params) == 3
        assert params[0] == {"name": "value", "type": "string"}
        assert params[1] == {"name": "prefix", "type": "string"}
        assert params[2] == {"name": "suffix", "type": "string"}

    def test_optional_parameter_in_class_property(self, tmp_path):
        """Class property arrow function with optional parameter."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Greeter {
    greet = (name?: string) => name || "Guest"
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        params = arrow_functions["greet"]
        assert len(params) == 1
        assert params[0]["name"] == "name"
        assert params[0]["type"] == "string"

    def test_rest_parameter_in_class_property(self, tmp_path):
        """Class property arrow function with rest parameter."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Logger {
    log = (...messages: string[]) => {
        console.log(...messages);
    }
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        params = arrow_functions["log"]
        assert len(params) == 1
        assert params[0]["name"] == "messages"
        assert "string" in params[0]["type"]

    def test_union_type_parameter_in_class_property(self, tmp_path):
        """Class property arrow function with union type parameter."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Processor {
    process = (value: string | number) => String(value)
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        params = arrow_functions["process"]
        assert params[0]["name"] == "value"
        assert "string" in params[0]["type"]
        assert "number" in params[0]["type"]


# =============================================================================
# SECTION 4: Object Property Arrow Functions
# =============================================================================


class TestObjectPropertyArrowFunctions:
    """Test detection of arrow functions as object properties."""

    def test_simple_object_property_arrow_function(self, tmp_path):
        """Simple object property arrow function must be detected."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
const obj = {
    method: (x: number) => x * 2
};
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        # Object property arrow functions should be detected
        assert "method" in arrow_functions
        params = arrow_functions["method"]
        assert len(params) == 1
        assert params[0]["name"] == "x"
        assert params[0]["type"] == "number"

    def test_multiple_object_property_arrow_functions(self, tmp_path):
        """Multiple object property arrow functions must be detected."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
const handlers = {
    onClick: (e: MouseEvent) => console.log(e),
    onChange: (value: string) => console.log(value),
    onSubmit: () => console.log("submitted")
};
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        assert "onClick" in arrow_functions
        assert "onChange" in arrow_functions
        assert "onSubmit" in arrow_functions

    def test_nested_object_property_arrow_function(self, tmp_path):
        """Nested object property arrow functions must be detected."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
const config = {
    handlers: {
        success: (data: string) => console.log(data),
        error: (err: Error) => console.error(err)
    }
};
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        # Nested object properties should be detected
        assert "success" in arrow_functions or "error" in arrow_functions

    def test_object_property_without_type_annotation(self, tmp_path):
        """Object property arrow function without type annotations."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
const utils = {
    double: (x) => x * 2
};
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        assert "double" in arrow_functions
        params = arrow_functions["double"]
        assert params[0]["name"] == "x"


# =============================================================================
# SECTION 5: Integration with Existing Variable Declaration Detection
# =============================================================================


class TestExistingVariableDeclarationDetection:
    """Test that existing variable declaration detection still works (regression test)."""

    def test_const_arrow_function_still_detected(self, tmp_path):
        """Const arrow function (existing behavior) must still be detected."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
const greet = (name: string) => {
    return `Hello, ${name}`;
};
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        # This is the original functionality - should still work
        assert "greet" in arrow_functions
        params = arrow_functions["greet"]
        assert params[0]["name"] == "name"
        assert params[0]["type"] == "string"

    def test_let_arrow_function_still_detected(self, tmp_path):
        """Let arrow function (existing behavior) must still be detected."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
let calculate = (x: number, y: number) => x + y;
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        assert "calculate" in arrow_functions
        params = arrow_functions["calculate"]
        assert len(params) == 2

    def test_mixed_variable_and_class_property_arrow_functions(self, tmp_path):
        """Both variable and class property arrow functions must be detected."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
const standalone = (x: number) => x * 2;

class Foo {
    method = (y: string) => y.toUpperCase()
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        # Both should be detected
        assert "standalone" in arrow_functions
        assert "method" in arrow_functions


# =============================================================================
# SECTION 6: Integration with collect_artifacts
# =============================================================================


class TestIntegrationWithCollectArtifacts:
    """Test that arrow functions are properly integrated into found_functions."""

    def test_class_property_arrow_in_found_functions(self, tmp_path):
        """Class property arrow functions must appear in found_functions."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Component {
    handleClick = (e: MouseEvent) => {
        console.log(e);
    }
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        # Class property arrow function should be in found_functions
        assert "handleClick" in artifacts["found_functions"]
        params = artifacts["found_functions"]["handleClick"]
        assert len(params) == 1
        assert params[0]["name"] == "e"

    def test_object_property_arrow_in_found_functions(self, tmp_path):
        """Object property arrow functions must appear in found_functions."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
const api = {
    fetch: (url: string) => fetch(url)
};
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        assert "fetch" in artifacts["found_functions"]


# =============================================================================
# SECTION 7: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_mixed_regular_methods_and_arrow_properties(self, tmp_path):
        """Class with both regular methods and arrow property methods."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Mixed {
    regularMethod(x: number) {
        return x * 2;
    }

    arrowProperty = (y: string) => y.toUpperCase()
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        # Regular method should be in found_methods
        assert "Mixed" in artifacts["found_methods"]
        assert "regularMethod" in artifacts["found_methods"]["Mixed"]

        # Arrow property should be in found_functions
        assert "arrowProperty" in artifacts["found_functions"]

    def test_arrow_function_with_complex_return_type(self, tmp_path):
        """Arrow function with complex return type annotation."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Fetcher {
    getData = (id: string): Promise<{ data: string }> => {
        return fetch(`/api/${id}`).then(r => r.json());
    }
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        assert "getData" in arrow_functions
        params = arrow_functions["getData"]
        assert params[0]["name"] == "id"
        assert params[0]["type"] == "string"

    def test_arrow_function_in_constructor(self, tmp_path):
        """Arrow function assigned in constructor (should not be detected as class property)."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Foo {
    constructor() {
        this.method = (x: number) => x * 2;
    }
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        # Constructor assignments are not class properties - this is expected behavior
        # The validator focuses on class property declarations
        assert "Foo" in artifacts["found_classes"]

    def test_empty_class_no_crash(self, tmp_path):
        """Empty class should not cause crashes."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Empty {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        # Should return empty dict, not crash
        assert isinstance(arrow_functions, dict)

    def test_empty_object_no_crash(self, tmp_path):
        """Empty object should not cause crashes."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
const empty = {};
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        assert isinstance(arrow_functions, dict)


# =============================================================================
# SECTION 8: Real-World React Patterns
# =============================================================================


class TestReactPatterns:
    """Test real-world React component patterns."""

    def test_react_event_handler_class_property(self, tmp_path):
        """React event handler as class property must be detected."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.tsx"
        ts_file.write_text(
            """
import React from 'react';

class Button extends React.Component {
    handleClick = (e: React.MouseEvent) => {
        console.log("clicked", e);
    }

    render() {
        return <button onClick={this.handleClick}>Click</button>;
    }
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        assert "handleClick" in arrow_functions
        params = arrow_functions["handleClick"]
        assert params[0]["name"] == "e"
        # Type should contain React.MouseEvent
        assert "MouseEvent" in params[0]["type"]

    def test_react_multiple_event_handlers(self, tmp_path):
        """React component with multiple event handlers."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.tsx"
        ts_file.write_text(
            """
class Form extends React.Component {
    handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
    }

    handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        console.log(e.target.value);
    }

    handleReset = () => {
        console.log("reset");
    }
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        assert "handleSubmit" in arrow_functions
        assert "handleChange" in arrow_functions
        assert "handleReset" in arrow_functions

        # Verify handleReset has no parameters
        assert len(arrow_functions["handleReset"]) == 0

    def test_react_callback_with_custom_type(self, tmp_path):
        """React callback with custom type parameter."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.tsx"
        ts_file.write_text(
            """
interface User {
    id: string;
    name: string;
}

class UserList extends React.Component {
    onUserSelect = (user: User) => {
        console.log(user.name);
    }
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        assert "onUserSelect" in arrow_functions
        params = arrow_functions["onUserSelect"]
        assert params[0]["name"] == "user"
        assert params[0]["type"] == "User"

    def test_status_getter_pattern(self, tmp_path):
        """Common status getter pattern in React components."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.tsx"
        ts_file.write_text(
            """
class StatusIndicator extends React.Component {
    getStatusColor = (status: 'pending' | 'success' | 'error') => {
        switch (status) {
            case 'pending': return 'yellow';
            case 'success': return 'green';
            case 'error': return 'red';
        }
    }
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        assert "getStatusColor" in arrow_functions
        params = arrow_functions["getStatusColor"]
        assert params[0]["name"] == "status"
        # Should contain the union type
        assert "pending" in params[0]["type"] or "success" in params[0]["type"]


# =============================================================================
# SECTION 9: Snapshot Integration
# =============================================================================


class TestSnapshotIntegration:
    """Test integration with snapshot generation."""

    def test_snapshot_includes_class_property_arrow_functions(self, tmp_path):
        """Generated snapshot must include class property arrow functions."""
        from maid_runner.cli.snapshot import generate_snapshot
        import json

        ts_file = tmp_path / "component.tsx"
        ts_file.write_text(
            """
class Component {
    handleClick = (e: MouseEvent) => {
        console.log(e);
    }
}
"""
        )

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest_path = generate_snapshot(
            str(ts_file), str(manifest_dir), skip_test_stub=True
        )

        # Load and verify manifest
        with open(manifest_path) as f:
            manifest = json.load(f)

        artifacts = manifest["expectedArtifacts"]["contains"]
        functions = [a for a in artifacts if a.get("name") == "handleClick"]

        # Should find the class property arrow function
        assert len(functions) == 1
        func = functions[0]
        assert func["type"] == "function"

        params = func.get("args", [])
        assert len(params) == 1
        assert params[0]["name"] == "e"

    def test_snapshot_includes_object_property_arrow_functions(self, tmp_path):
        """Generated snapshot must include object property arrow functions."""
        from maid_runner.cli.snapshot import generate_snapshot
        import json

        ts_file = tmp_path / "handlers.ts"
        ts_file.write_text(
            """
export const handlers = {
    onClick: (event: Event) => console.log(event)
};
"""
        )

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest_path = generate_snapshot(
            str(ts_file), str(manifest_dir), skip_test_stub=True
        )

        with open(manifest_path) as f:
            manifest = json.load(f)

        artifacts = manifest["expectedArtifacts"]["contains"]
        functions = [a for a in artifacts if a.get("name") == "onClick"]

        # Should find the object property arrow function
        assert len(functions) >= 1

    def test_snapshot_real_world_react_component(self, tmp_path):
        """Snapshot of real React component with event handlers."""
        from maid_runner.cli.snapshot import generate_snapshot
        import json

        ts_file = tmp_path / "Button.tsx"
        ts_file.write_text(
            """
import React from 'react';

export class Button extends React.Component {
    handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
        e.preventDefault();
        console.log("clicked");
    }

    handleMouseEnter = () => {
        console.log("hover");
    }

    render() {
        return <button onClick={this.handleClick}>Click</button>;
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

        artifacts = manifest["expectedArtifacts"]["contains"]

        # Should have class
        classes = [a for a in artifacts if a.get("type") == "class"]
        assert any(c["name"] == "Button" for c in classes)

        # Should have arrow function event handlers
        functions = [a for a in artifacts if a.get("type") == "function"]
        handler_names = {f["name"] for f in functions}

        assert "handleClick" in handler_names
        assert "handleMouseEnter" in handler_names


# =============================================================================
# SECTION 10: Negative Tests
# =============================================================================


class TestNegativeTests:
    """Test that non-arrow functions are not detected as arrow functions."""

    def test_regular_method_not_in_arrow_functions(self, tmp_path):
        """Regular class methods should not be in arrow functions dict."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Foo {
    regularMethod(x: number) {
        return x * 2;
    }
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        # Regular method should NOT be in arrow functions
        assert "regularMethod" not in arrow_functions

    def test_regular_function_declaration_not_in_arrow_functions(self, tmp_path):
        """Regular function declarations should not be in arrow functions dict."""
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
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        # Regular function should NOT be in arrow functions
        assert "greet" not in arrow_functions

    def test_class_property_non_arrow_not_detected(self, tmp_path):
        """Class property that is not an arrow function should not be detected."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Foo {
    value: number = 42;
    name: string = "test";
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        # Non-function properties should not be detected
        assert "value" not in arrow_functions
        assert "name" not in arrow_functions


# =============================================================================
# SECTION 11: Single Parameter Arrow Functions Without Parentheses
# =============================================================================


class TestSingleParameterArrowFunctions:
    """Tests for single-parameter arrow functions without parentheses (lines 439-456, 480-483, 509-512)."""

    def test_const_single_param_arrow_no_parens(self, tmp_path):
        """const single = x => x * 2 pattern."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
const double = x => x * 2;
const triple = y => y * 3;
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        # Single parameter without parens should be detected
        assert "double" in arrow_functions
        assert "triple" in arrow_functions
        # Parameters should be extracted
        assert len(arrow_functions["double"]) == 1
        assert arrow_functions["double"][0]["name"] == "x"

    def test_class_property_single_param_no_parens(self, tmp_path):
        """Class property arrow function with single param, no parentheses."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Transformer {
    transform = x => x.toUpperCase()
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        assert "transform" in arrow_functions
        params = arrow_functions["transform"]
        assert len(params) == 1
        assert params[0]["name"] == "x"

    def test_object_property_single_param_no_parens(self, tmp_path):
        """Object property arrow function with single param, no parentheses."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
const utils = {
    double: n => n * 2,
    stringify: v => String(v)
};
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        assert "double" in arrow_functions
        assert "stringify" in arrow_functions
        assert arrow_functions["double"][0]["name"] == "n"
        assert arrow_functions["stringify"][0]["name"] == "v"


# =============================================================================
# SECTION 12: Parameter Type Edge Cases
# =============================================================================


class TestParameterTypeEdgeCases:
    """Tests for parameter extraction edge cases (lines 572, 578-579, 593-598, 618, 621-622, 626-628)."""

    def test_rest_parameter_with_type_annotation(self, tmp_path):
        """Rest parameter with type annotation (...args: string[])."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function logAll(...messages: string[]) {
    console.log(messages);
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        functions = validator._extract_functions(tree, source_code)

        assert "logAll" in functions
        params = functions["logAll"]
        assert len(params) == 1
        assert params[0]["name"] == "messages"
        assert "string" in params[0].get("type", "")

    def test_optional_parameter_extraction(self, tmp_path):
        """Optional parameter without default value."""
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
        functions = validator._extract_functions(tree, source_code)

        assert "greet" in functions
        params = functions["greet"]
        assert len(params) == 1
        assert params[0]["name"] == "name"
        assert params[0]["type"] == "string"

    def test_destructured_object_parameter_detection(self, tmp_path):
        """Destructured object parameter function should be detected."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function process({ id, name, value }: Record<string, any>) {
    console.log(id, name, value);
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        functions = validator._extract_functions(tree, source_code)

        # Function should be detected even with destructured params
        assert "process" in functions
        # Note: Destructured params inside required_parameter are complex to extract
        # The function is still detected and can be validated

    def test_destructured_array_parameter_detection(self, tmp_path):
        """Destructured array parameter function should be detected."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function processArray([first, second]: [string, number]) {
    console.log(first, second);
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        functions = validator._extract_functions(tree, source_code)

        # Function should be detected even with destructured array params
        assert "processArray" in functions


# =============================================================================
# SECTION 13: Class and Function Name Edge Cases
# =============================================================================


class TestClassAndFunctionNameEdgeCases:
    """Tests for edge cases in class/function name extraction (lines 1070, 1085)."""

    def test_get_class_name_from_malformed_node(self, tmp_path):
        """Test _get_class_name_from_node with node missing type_identifier."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        # Create a file with anonymous class expression
        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
const cls = class {
    method() {}
};
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        # Anonymous class should still be processable without crash
        assert isinstance(artifacts["found_classes"], set)

    def test_get_function_name_missing_identifier(self, tmp_path):
        """Test function declaration parsing resilience."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
export default function() {
    return 42;
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        functions = validator._extract_functions(tree, source_code)

        # Should not crash, may or may not detect anonymous function
        assert isinstance(functions, dict)


# =============================================================================
# SECTION 14: Method Extraction Edge Cases
# =============================================================================


class TestMethodExtractionEdgeCases:
    """Tests for method extraction edge cases (lines 1133-1136)."""

    def test_arrow_function_method_in_class_body(self, tmp_path):
        """Arrow function as class method with single param."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Handler {
    handle = event => {
        console.log(event);
    }
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        assert "handle" in arrow_functions
        params = arrow_functions["handle"]
        assert len(params) == 1
        assert params[0]["name"] == "event"


# =============================================================================
# SECTION 15: Static and Decorator Checks
# =============================================================================


class TestStaticAndDecoratorChecks:
    """Tests for static method and decorator detection (lines 1177-1218)."""

    def test_is_static_method_detection(self, tmp_path):
        """Static methods should be detected."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Utils {
    static format(value: string): string {
        return value.trim();
    }

    static parse(data: string): any {
        return JSON.parse(data);
    }

    regularMethod() {
        return true;
    }
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        # All methods should be found
        assert "Utils" in artifacts["found_methods"]
        methods = artifacts["found_methods"]["Utils"]
        assert "format" in methods
        assert "parse" in methods
        assert "regularMethod" in methods

    def test_getter_setter_in_class(self, tmp_path):
        """Getters and setters in class."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Person {
    private _name: string = "";

    get name(): string {
        return this._name;
    }

    set name(value: string) {
        this._name = value;
    }
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        # Class should be found
        assert "Person" in artifacts["found_classes"]

    def test_abstract_method_signature(self, tmp_path):
        """Abstract method signatures in abstract class."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
abstract class Shape {
    abstract getArea(): number;
    abstract getPerimeter(): number;
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        artifacts = validator._collect_implementation_artifacts(tree, source_code)

        # Abstract class should be found
        assert "Shape" in artifacts["found_classes"]
        # Abstract methods should be in found_methods
        assert "Shape" in artifacts["found_methods"]
        methods = artifacts["found_methods"]["Shape"]
        assert "getArea" in methods
        assert "getPerimeter" in methods


# =============================================================================
# SECTION: Edge Cases for Parameter Extraction
# =============================================================================


class TestParameterExtractionEdgeCases:
    """Test edge cases in parameter extraction from TypeScript."""

    def test_rest_parameter_with_type(self, tmp_path):
        """Test that rest parameters with type annotations are extracted correctly."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function sum(...numbers: number[]): number {
    return numbers.reduce((a, b) => a + b, 0);
}
"""
        )

        validator = TypeScriptValidator()
        artifacts = validator.collect_artifacts(str(ts_file), "implementation")

        # Should find the function with rest parameter
        found_functions = artifacts.get("found_functions", {})
        assert "sum" in found_functions

    def test_destructured_parameter(self, tmp_path):
        """Test that destructured parameters are handled."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function processUser({ name, age }: { name: string; age: number }): void {
    console.log(name, age);
}
"""
        )

        validator = TypeScriptValidator()
        artifacts = validator.collect_artifacts(str(ts_file), "implementation")

        # Should find the function
        found_functions = artifacts.get("found_functions", {})
        assert "processUser" in found_functions

    def test_optional_parameter_with_default(self, tmp_path):
        """Test that optional parameters with defaults are extracted."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function greet(name: string, prefix = "Hello"): string {
    return `${prefix}, ${name}!`;
}
"""
        )

        validator = TypeScriptValidator()
        artifacts = validator.collect_artifacts(str(ts_file), "implementation")

        # Should find the function
        found_functions = artifacts.get("found_functions", {})
        assert "greet" in found_functions

    def test_arrow_function_with_rest_parameter(self, tmp_path):
        """Test arrow function with rest parameter."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
const concat = (...strings: string[]): string => {
    return strings.join('');
};
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(ts_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        # Should detect the arrow function
        assert "concat" in arrow_functions

    def test_method_with_complex_generic_type(self, tmp_path):
        """Test method with complex generic type parameters."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
class Repository<T> {
    findAll<K extends keyof T>(keys: K[]): Pick<T, K>[] {
        return [];
    }
}
"""
        )

        validator = TypeScriptValidator()
        artifacts = validator.collect_artifacts(str(ts_file), "implementation")

        # Should find the class and method
        assert "Repository" in artifacts.get("found_classes", {})

    def test_function_with_function_type_parameter(self, tmp_path):
        """Test function that takes a function type parameter."""
        from maid_runner.validators.typescript_validator import TypeScriptValidator

        ts_file = tmp_path / "test.ts"
        ts_file.write_text(
            """
function map<T, U>(arr: T[], fn: (item: T) => U): U[] {
    return arr.map(fn);
}
"""
        )

        validator = TypeScriptValidator()
        artifacts = validator.collect_artifacts(str(ts_file), "implementation")

        # Should find the function
        found_functions = artifacts.get("found_functions", {})
        assert "map" in found_functions
