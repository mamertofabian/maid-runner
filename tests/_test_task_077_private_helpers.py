"""
Private test module for private helper methods declared in task-077 manifest.

These tests verify the actual behavior of private helper methods that are declared
in the manifest. While these are internal helpers, they're part of the declared API
and must be behaviorally validated.

Tests focus on meaningful behavior:
- How these helpers enable public APIs to work correctly
- Edge cases and error conditions
- Real-world usage scenarios

Related task: task-077-typescript-parameter-type-annotations
"""

import pytest

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.typescript_validator import TypeScriptValidator
except ImportError as e:
    # In Red phase, these functions won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


class TestExtractParameters:
    """Test _extract_parameters private method behavior."""

    def test_extract_parameters_called_with_formal_parameters_node(self, tmp_path):
        """Test that _extract_parameters is called with formal_parameters node."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function greet(name: string, age: number) {
    return `Hello ${name}, age ${age}`;
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find the formal_parameters node
        def find_formal_parameters(node):
            if node.type == "formal_parameters":
                return node
            for child in node.children:
                result = find_formal_parameters(child)
                if result:
                    return result
            return None

        params_node = find_formal_parameters(tree.root_node)
        assert params_node is not None

        # Call _extract_parameters directly
        params = validator._extract_parameters(params_node, source_code)

        assert isinstance(params, list)
        assert len(params) == 2
        assert params[0]["name"] == "name"
        assert params[0]["type"] == "string"
        assert params[1]["name"] == "age"
        assert params[1]["type"] == "number"

    def test_extract_parameters_handles_optional_parameters(self, tmp_path):
        """Test that _extract_parameters handles optional parameters."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function greet(name: string, title?: string) {
    return title ? `${title} ${name}` : name;
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        def find_formal_parameters(node):
            if node.type == "formal_parameters":
                return node
            for child in node.children:
                result = find_formal_parameters(child)
                if result:
                    return result
            return None

        params_node = find_formal_parameters(tree.root_node)
        assert params_node is not None

        params = validator._extract_parameters(params_node, source_code)

        assert len(params) >= 1
        assert params[0]["name"] == "name"
        assert params[0]["type"] == "string"

    def test_extract_parameters_handles_union_types(self, tmp_path):
        """Test that _extract_parameters handles union type parameters."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function process(value: string | number) {
    return String(value);
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        def find_formal_parameters(node):
            if node.type == "formal_parameters":
                return node
            for child in node.children:
                result = find_formal_parameters(child)
                if result:
                    return result
            return None

        params_node = find_formal_parameters(tree.root_node)
        assert params_node is not None

        params = validator._extract_parameters(params_node, source_code)

        assert len(params) == 1
        assert params[0]["name"] == "value"
        assert "string" in params[0]["type"]
        assert "number" in params[0]["type"]

    def test_extract_parameters_handles_parameters_without_types(self, tmp_path):
        """Test that _extract_parameters handles parameters without type annotations."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function legacy(x, y) {
    return x + y;
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        def find_formal_parameters(node):
            if node.type == "formal_parameters":
                return node
            for child in node.children:
                result = find_formal_parameters(child)
                if result:
                    return result
            return None

        params_node = find_formal_parameters(tree.root_node)
        assert params_node is not None

        params = validator._extract_parameters(params_node, source_code)

        assert isinstance(params, list)
        assert len(params) == 2
        # Parameters should still be extracted even without types
        param_names = [p["name"] if isinstance(p, dict) else p for p in params]
        assert "x" in param_names
        assert "y" in param_names

    def test_extract_parameters_handles_rest_parameters(self, tmp_path):
        """Test that _extract_parameters handles rest parameters."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function sum(...numbers: number[]) {
    return numbers.reduce((a, b) => a + b, 0);
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        def find_formal_parameters(node):
            if node.type == "formal_parameters":
                return node
            for child in node.children:
                result = find_formal_parameters(child)
                if result:
                    return result
            return None

        params_node = find_formal_parameters(tree.root_node)
        assert params_node is not None

        params = validator._extract_parameters(params_node, source_code)

        assert isinstance(params, list)
        assert len(params) >= 1
        # Rest parameter should be extracted
        param = params[0]
        if isinstance(param, dict):
            assert param["name"] == "numbers"
            assert "number" in param.get("type", "")


class TestExtractTypeFromNode:
    """Test _extract_type_from_node private method behavior."""

    def test_extract_type_from_node_called_with_simple_type(self, tmp_path):
        """Test that _extract_type_from_node is called with simple type node."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function test(param: string) {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

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

        # Call _extract_type_from_node directly
        type_text = validator._extract_type_from_node(type_node, source_code)
        assert type_text == "string"

    def test_extract_type_from_node_handles_union_types(self, tmp_path):
        """Test that _extract_type_from_node handles union types."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function test(param: string | number) {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

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

        # Call _extract_type_from_node directly
        type_text = validator._extract_type_from_node(union_node, source_code)
        assert "string" in type_text
        assert "number" in type_text
        assert "|" in type_text

    def test_extract_type_from_node_handles_array_types(self, tmp_path):
        """Test that _extract_type_from_node handles array types."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function test(items: string[]) {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find the array_type node
        def find_array_type(node):
            if node.type == "array_type":
                return node
            for child in node.children:
                result = find_array_type(child)
                if result:
                    return result
            return None

        array_node = find_array_type(tree.root_node)
        if array_node:
            type_text = validator._extract_type_from_node(array_node, source_code)
            assert "string" in type_text

    def test_extract_type_from_node_handles_generic_types(self, tmp_path):
        """Test that _extract_type_from_node handles generic types."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function test(items: Array<number>) {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find the generic_type node
        def find_generic_type(node):
            if node.type == "generic_type":
                return node
            for child in node.children:
                result = find_generic_type(child)
                if result:
                    return result
            return None

        generic_node = find_generic_type(tree.root_node)
        if generic_node:
            type_text = validator._extract_type_from_node(generic_node, source_code)
            assert "Array" in type_text
            assert "number" in type_text

    def test_extract_type_from_node_handles_custom_types(self, tmp_path):
        """Test that _extract_type_from_node handles custom type identifiers."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
interface User {
    name: string;
}

function test(user: User) {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find the type_identifier node for User
        def find_type_identifier(node):
            if (
                node.type == "type_identifier"
                and validator._get_node_text(node, source_code) == "User"
            ):
                return node
            for child in node.children:
                result = find_type_identifier(child)
                if result:
                    return result
            return None

        type_id_node = find_type_identifier(tree.root_node)
        if type_id_node:
            type_text = validator._extract_type_from_node(type_id_node, source_code)
            assert type_text == "User"

    def test_extract_type_from_node_handles_none_node(self, tmp_path):
        """Test that _extract_type_from_node handles None node gracefully."""
        validator = TypeScriptValidator()
        test_file = tmp_path / "test.ts"
        test_file.write_text("let x = 1;")
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Call with None
        type_text = validator._extract_type_from_node(None, source_code)
        assert type_text == ""
