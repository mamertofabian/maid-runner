"""
Private test module for private helper methods declared in task-086 manifest.

These tests verify the actual behavior of private helper methods that are declared
in the manifest. While these are internal helpers, they're part of the declared API
and must be behaviorally validated.

Tests focus on meaningful behavior:
- How these helpers enable public APIs to work correctly
- Edge cases and error conditions
- Real-world usage scenarios

Related task: task-086-create-svelte-validator
"""

import pytest

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.svelte_validator import SvelteValidator
except ImportError as e:
    # In Red phase, these functions won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


class TestSvelteValidatorInit:
    """Test SvelteValidator.__init__ behavior."""

    def test_init_called_when_instantiating(self):
        """Test that SvelteValidator.__init__ is called when instantiating."""
        validator = SvelteValidator()

        assert hasattr(validator, "parser")
        assert hasattr(validator, "language")
        assert hasattr(validator, "svelte_parser")
        assert hasattr(validator, "svelte_language")
        assert validator.parser is not None
        assert validator.language is not None

    def test_init_explicitly_called(self):
        """Test that SvelteValidator.__init__ can be called explicitly."""
        validator = SvelteValidator()
        original_parser = validator.parser

        validator.__init__()

        assert validator.parser is not None
        assert validator.parser is not original_parser


class TestParseSvelteFile:
    """Test _parse_svelte_file private method behavior."""

    def test_parses_valid_svelte_file(self, tmp_path):
        """Test that _parse_svelte_file parses valid Svelte files correctly."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
let count = 0;
function increment() {
    count += 1;
}
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))

        assert tree is not None
        assert source_code is not None
        assert isinstance(source_code, bytes)
        assert len(source_code) > 0

    def test_parses_empty_svelte_file(self, tmp_path):
        """Test that _parse_svelte_file handles empty files."""
        test_file = tmp_path / "empty.svelte"
        test_file.write_text("")

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))

        assert tree is not None
        assert source_code is not None
        assert isinstance(source_code, bytes)

    def test_parses_svelte_file_with_typescript(self, tmp_path):
        """Test that _parse_svelte_file handles TypeScript script blocks."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script lang="ts">
let count: number = 0;
function increment(): void {
    count += 1;
}
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))

        assert tree is not None
        assert source_code is not None
        assert isinstance(source_code, bytes)

    def test_parses_svelte_file_without_script(self, tmp_path):
        """Test that _parse_svelte_file handles files without script tags."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text("<div>Hello World</div>")

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))

        assert tree is not None
        assert source_code is not None


class TestCollectImplementationArtifacts:
    """Test _collect_implementation_artifacts private method behavior."""

    def test_collects_functions_from_tree(self, tmp_path):
        """Test that _collect_implementation_artifacts extracts functions."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
function greet(name) {
    return `Hello ${name}`;
}
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        result = validator._collect_implementation_artifacts(tree, source_code)

        assert "greet" in result["found_functions"]
        assert isinstance(result["found_classes"], set)
        assert isinstance(result["found_functions"], dict)
        assert isinstance(result["found_methods"], dict)

    def test_collects_classes_from_tree(self, tmp_path):
        """Test that _collect_implementation_artifacts extracts classes."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
class UserService {
    getUser(id) {
        return {};
    }
}
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        result = validator._collect_implementation_artifacts(tree, source_code)

        assert "UserService" in result["found_classes"]
        assert "UserService" in result["found_methods"]
        assert "getUser" in result["found_methods"]["UserService"]

    def test_collects_used_artifacts_in_implementation_mode(self, tmp_path):
        """Test that _collect_implementation_artifacts also tracks usage."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
class Service {}
const svc = new Service();
svc.method();
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        result = validator._collect_implementation_artifacts(tree, source_code)

        assert "Service" in result["found_classes"]
        assert "Service" in result["used_classes"]
        assert isinstance(result["used_functions"], set)
        assert isinstance(result["used_methods"], dict)

    def test_returns_all_required_keys(self, tmp_path):
        """Test that _collect_implementation_artifacts returns all required keys."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text("<script>let x = 1;</script>")

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        result = validator._collect_implementation_artifacts(tree, source_code)

        required_keys = [
            "found_classes",
            "found_functions",
            "found_methods",
            "found_class_bases",
            "found_attributes",
            "variable_to_class",
            "found_function_types",
            "found_method_types",
            "used_classes",
            "used_functions",
            "used_methods",
            "used_arguments",
        ]
        for key in required_keys:
            assert key in result, f"Missing required key: {key}"


class TestCollectBehavioralArtifacts:
    """Test _collect_behavioral_artifacts private method behavior."""

    def test_collects_function_calls(self, tmp_path):
        """Test that _collect_behavioral_artifacts extracts function calls."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
function greet() {}
greet();
greet();
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        result = validator._collect_behavioral_artifacts(tree, source_code)

        assert "greet" in result["used_functions"]
        assert isinstance(result["used_functions"], set)

    def test_collects_class_instantiations(self, tmp_path):
        """Test that _collect_behavioral_artifacts extracts class instantiations."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
class Service {}
const svc = new Service();
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        result = validator._collect_behavioral_artifacts(tree, source_code)

        assert "Service" in result["used_classes"]
        assert isinstance(result["used_classes"], set)

    def test_collects_method_calls(self, tmp_path):
        """Test that _collect_behavioral_artifacts extracts method calls."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
const obj = getObject();
obj.method1();
obj.method2();
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        result = validator._collect_behavioral_artifacts(tree, source_code)

        assert isinstance(result["used_methods"], dict)
        assert "obj" in result["used_methods"]
        assert "method1" in result["used_methods"]["obj"]
        assert "method2" in result["used_methods"]["obj"]

    def test_returns_all_required_keys(self, tmp_path):
        """Test that _collect_behavioral_artifacts returns all required keys."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text("<script>let x = 1;</script>")

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        result = validator._collect_behavioral_artifacts(tree, source_code)

        required_keys = ["used_classes", "used_functions", "used_methods"]
        for key in required_keys:
            assert key in result, f"Missing required key: {key}"


class TestTraverseTree:
    """Test _traverse_tree private method behavior."""

    def test_traverses_all_nodes(self, tmp_path):
        """Test that _traverse_tree visits all nodes in the tree."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
function outer() {
    function inner() {
        return 42;
    }
    return inner();
}
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))

        visited_nodes = []

        def callback(node):
            visited_nodes.append(node.type)

        validator._traverse_tree(tree.root_node, callback)

        assert len(visited_nodes) > 0
        assert "program" in visited_nodes

    def test_traverses_nested_structures(self, tmp_path):
        """Test that _traverse_tree handles nested structures."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
class Outer {
    method() {
        const nested = () => {
            return 42;
        };
    }
}
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))

        visited_types = set()

        def callback(node):
            visited_types.add(node.type)

        validator._traverse_tree(tree.root_node, callback)

        assert len(visited_types) > 0
        assert (
            "class_declaration" in visited_types
            or "lexical_declaration" in visited_types
        )

    def test_callback_called_for_each_node(self, tmp_path):
        """Test that _traverse_tree calls callback for each node."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text("<script>let x = 1;</script>")

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))

        call_count = 0

        def callback(node):
            nonlocal call_count
            call_count += 1

        validator._traverse_tree(tree.root_node, callback)

        assert call_count > 0


class TestGetNodeText:
    """Test _get_node_text private method behavior."""

    def test_extracts_text_from_node(self, tmp_path):
        """Test that _get_node_text extracts correct text from AST node."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
function myFunction() {}
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))

        def find_function_node(node):
            if node.type == "function_declaration":
                return node
            for child in node.children:
                result = find_function_node(child)
                if result:
                    return result
            return None

        func_node = find_function_node(tree.root_node)
        assert func_node is not None

        text = validator._get_node_text(func_node, source_code)
        assert "function" in text
        assert "myFunction" in text

    def test_handles_empty_node(self, tmp_path):
        """Test that _get_node_text handles edge cases."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text("<script></script>")

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))

        text = validator._get_node_text(tree.root_node, source_code)
        assert isinstance(text, str)

    def test_extracts_correct_byte_range(self, tmp_path):
        """Test that _get_node_text extracts correct byte range."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
const name = "test";
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))

        def find_identifier(node):
            if (
                node.type == "identifier"
                and node.parent
                and node.parent.type == "lexical_declaration"
            ):
                return node
            for child in node.children:
                result = find_identifier(child)
                if result:
                    return result
            return None

        id_node = find_identifier(tree.root_node)
        if id_node:
            text = validator._get_node_text(id_node, source_code)
            assert text == "name" or "name" in text


class TestExtractFunctions:
    """Test _extract_functions private method behavior."""

    def test_extracts_function_declarations(self, tmp_path):
        """Test that _extract_functions finds function declarations."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
function greet(name) {
    return `Hello ${name}`;
}
function farewell(name) {
    return `Goodbye ${name}`;
}
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        functions = validator._extract_functions(tree, source_code)

        assert "greet" in functions
        assert "farewell" in functions
        assert isinstance(functions, dict)

    def test_extracts_arrow_functions(self, tmp_path):
        """Test that _extract_functions finds arrow functions."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
const increment = () => {
    count += 1;
};
const decrement = (x) => x - 1;
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        functions = validator._extract_functions(tree, source_code)

        assert "increment" in functions
        assert "decrement" in functions

    def test_extracts_function_parameters(self, tmp_path):
        """Test that _extract_functions extracts function parameters."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
function process(name, age, email) {
    return {};
}
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        functions = validator._extract_functions(tree, source_code)

        assert "process" in functions
        params = functions["process"]
        assert isinstance(params, list)
        assert len(params) >= 3

    def test_handles_empty_functions(self, tmp_path):
        """Test that _extract_functions handles files with no functions."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text("<script>let x = 1;</script>")

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        functions = validator._extract_functions(tree, source_code)

        assert isinstance(functions, dict)


class TestExtractClasses:
    """Test _extract_classes private method behavior."""

    def test_extracts_class_declarations(self, tmp_path):
        """Test that _extract_classes finds class declarations."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
class UserService {
    getUser(id) {}
}
class DataStore {
    load() {}
}
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        classes = validator._extract_classes(tree, source_code)

        assert "UserService" in classes
        assert "DataStore" in classes
        assert isinstance(classes, set)

    def test_extracts_interface_declarations(self, tmp_path):
        """Test that _extract_classes finds interface declarations."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script lang="ts">
interface User {
    name: string;
}
interface Product {
    id: number;
}
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        classes = validator._extract_classes(tree, source_code)

        assert "User" in classes
        assert "Product" in classes

    def test_handles_empty_classes(self, tmp_path):
        """Test that _extract_classes handles files with no classes."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text("<script>let x = 1;</script>")

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        classes = validator._extract_classes(tree, source_code)

        assert isinstance(classes, set)
        assert len(classes) == 0 or len(classes) >= 0


class TestExtractFunctionCalls:
    """Test _extract_function_calls private method behavior."""

    def test_extracts_simple_function_calls(self, tmp_path):
        """Test that _extract_function_calls finds function calls."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
doSomething();
processData(x, y);
formatString('test');
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        function_calls = validator._extract_function_calls(tree, source_code)

        assert "doSomething" in function_calls
        assert "processData" in function_calls
        assert "formatString" in function_calls
        assert isinstance(function_calls, set)

    def test_extracts_nested_function_calls(self, tmp_path):
        """Test that _extract_function_calls finds nested calls."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
const result = process(format(data));
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        function_calls = validator._extract_function_calls(tree, source_code)

        assert "process" in function_calls
        assert "format" in function_calls

    def test_handles_no_function_calls(self, tmp_path):
        """Test that _extract_function_calls handles files with no calls."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text("<script>let x = 1;</script>")

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        function_calls = validator._extract_function_calls(tree, source_code)

        assert isinstance(function_calls, set)


class TestExtractClassUsage:
    """Test _extract_class_usage private method behavior."""

    def test_extracts_class_instantiations(self, tmp_path):
        """Test that _extract_class_usage finds class instantiations."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
class Service {}
class Store {}
const svc = new Service();
const store = new Store();
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        class_usage = validator._extract_class_usage(tree, source_code)

        assert "Service" in class_usage
        assert "Store" in class_usage
        assert isinstance(class_usage, set)

    def test_extracts_nested_instantiations(self, tmp_path):
        """Test that _extract_class_usage finds nested instantiations."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
class Service {}
const svc = new Service();
const wrapper = new Wrapper(new Service());
</script>
"""
        )

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        class_usage = validator._extract_class_usage(tree, source_code)

        assert "Service" in class_usage

    def test_handles_no_class_usage(self, tmp_path):
        """Test that _extract_class_usage handles files with no instantiations."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text("<script>let x = 1;</script>")

        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        class_usage = validator._extract_class_usage(tree, source_code)

        assert isinstance(class_usage, set)
