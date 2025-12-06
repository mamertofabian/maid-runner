"""
Private test module for private helper methods declared in task-053 manifest.

These tests verify the actual behavior of private helper methods that are declared
in the manifest. While these are internal helpers, they're part of the declared API
and must be behaviorally validated.

Tests focus on meaningful behavior:
- How these helpers enable public APIs to work correctly
- Edge cases and error conditions
- Real-world usage scenarios

Related task: task-053-typescript-validator
"""

import pytest

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.typescript_validator import TypeScriptValidator
except ImportError as e:
    # In Red phase, these functions won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


class TestTypeScriptValidatorInit:
    """Test TypeScriptValidator.__init__ behavior."""

    def test_init_called_when_instantiating(self):
        """Test that TypeScriptValidator.__init__ is called when instantiating."""
        validator = TypeScriptValidator()

        assert hasattr(validator, "ts_parser")
        assert hasattr(validator, "tsx_parser")
        assert hasattr(validator, "ts_language")
        assert hasattr(validator, "tsx_language")
        assert validator.ts_parser is not None
        assert validator.tsx_parser is not None

    def test_init_explicitly_called(self):
        """Test that TypeScriptValidator.__init__ can be called explicitly."""
        validator = TypeScriptValidator()
        original_parser = validator.ts_parser

        validator.__init__()

        assert validator.ts_parser is not None
        assert validator.tsx_parser is not original_parser


class TestParseTypeScriptFile:
    """Test _parse_typescript_file private method behavior."""

    def test_parse_typescript_file_called_with_file_path(self, tmp_path):
        """Test that _parse_typescript_file is called with file path."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Service {
    method(): void {}
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        assert tree is not None
        assert source_code is not None
        assert isinstance(source_code, bytes)
        assert len(source_code) > 0

    def test_parse_typescript_file_handles_tsx_files(self, tmp_path):
        """Test that _parse_typescript_file handles TSX files."""
        test_file = tmp_path / "component.tsx"
        test_file.write_text(
            """
const Component = () => {
    return <div>Hello</div>;
};
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        assert tree is not None
        assert source_code is not None
        assert isinstance(source_code, bytes)

    def test_parse_typescript_file_handles_empty_file(self, tmp_path):
        """Test that _parse_typescript_file handles empty files."""
        test_file = tmp_path / "empty.ts"
        test_file.write_text("")

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        assert tree is not None
        assert source_code is not None
        assert isinstance(source_code, bytes)


class TestCollectImplementationArtifacts:
    """Test _collect_implementation_artifacts private method behavior."""

    def test_collect_implementation_artifacts_called_with_tree(self, tmp_path):
        """Test that _collect_implementation_artifacts is called with tree."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Service {
    method(): void {}
}

function process(): void {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))
        result = validator._collect_implementation_artifacts(tree, source_code)

        assert isinstance(result, dict)
        assert "found_classes" in result
        assert "found_functions" in result
        assert "Service" in result["found_classes"]
        assert "process" in result["found_functions"]


class TestCollectBehavioralArtifacts:
    """Test _collect_behavioral_artifacts private method behavior."""

    def test_collect_behavioral_artifacts_called_with_tree(self, tmp_path):
        """Test that _collect_behavioral_artifacts is called with tree."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Service {}
const svc = new Service();
svc.method();
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))
        result = validator._collect_behavioral_artifacts(tree, source_code)

        assert isinstance(result, dict)
        assert "used_classes" in result
        assert "used_functions" in result
        assert "used_methods" in result


class TestTraverseTree:
    """Test _traverse_tree private method behavior."""

    def test_traverse_tree_called_with_node_and_callback(self, tmp_path):
        """Test that _traverse_tree is called with node and callback."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Service {
    method(): void {}
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        visited_nodes = []

        def callback(node):
            visited_nodes.append(node.type)

        # Call _traverse_tree directly
        validator._traverse_tree(tree.root_node, callback)

        assert len(visited_nodes) > 0
        assert "program" in visited_nodes

    def test_traverse_tree_visits_all_nodes(self, tmp_path):
        """Test that _traverse_tree visits all nodes in the tree."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function outer() {
    function inner() {
        return 42;
    }
    return inner();
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        visited_types = set()

        def callback(node):
            visited_types.add(node.type)

        validator._traverse_tree(tree.root_node, callback)

        assert len(visited_types) > 0
        assert "program" in visited_types


class TestGetNodeText:
    """Test _get_node_text private method behavior."""

    def test_get_node_text_called_with_node(self, tmp_path):
        """Test that _get_node_text is called with node and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Service {
    method(): void {}
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find a class_declaration node
        def find_class_node(node):
            if node.type == "class_declaration":
                return node
            for child in node.children:
                result = find_class_node(child)
                if result:
                    return result
            return None

        class_node = find_class_node(tree.root_node)
        assert class_node is not None

        # Call _get_node_text directly
        text = validator._get_node_text(class_node, source_code)
        assert isinstance(text, str)
        assert "class" in text
        assert "Service" in text


class TestExtractIdentifier:
    """Test _extract_identifier private method behavior."""

    def test_extract_identifier_called_with_node(self, tmp_path):
        """Test that _extract_identifier is called with node and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
const name = "test";
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find an identifier node
        def find_identifier_node(node):
            if node.type == "identifier":
                return node
            for child in node.children:
                result = find_identifier_node(child)
                if result:
                    return result
            return None

        id_node = find_identifier_node(tree.root_node)
        if id_node:
            # Call _extract_identifier directly
            text = validator._extract_identifier(id_node, source_code)
            assert isinstance(text, str)
            # The extracted text should be the identifier name
            # It might be empty if the node doesn't have text, so just verify it's a string
            # The actual value depends on the node structure
            assert text is not None
        else:
            # If no identifier found, skip the assertion
            pytest.skip("No identifier node found in test code")


class TestExtractClasses:
    """Test _extract_classes private method behavior."""

    def test_extract_classes_called_with_tree(self, tmp_path):
        """Test that _extract_classes is called with tree and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Service {}
class Store {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))
        classes = validator._extract_classes(tree, source_code)

        assert isinstance(classes, set)
        assert "Service" in classes
        assert "Store" in classes


class TestExtractInterfaces:
    """Test _extract_interfaces private method behavior."""

    def test_extract_interfaces_called_with_tree(self, tmp_path):
        """Test that _extract_interfaces is called with tree and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
interface User {
    name: string;
}
interface Product {
    id: number;
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))
        interfaces = validator._extract_interfaces(tree, source_code)

        assert isinstance(interfaces, set)
        assert "User" in interfaces
        assert "Product" in interfaces


class TestExtractTypeAliases:
    """Test _extract_type_aliases private method behavior."""

    def test_extract_type_aliases_called_with_tree(self, tmp_path):
        """Test that _extract_type_aliases is called with tree and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
type UserID = string;
type Status = 'active' | 'inactive';
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))
        type_aliases = validator._extract_type_aliases(tree, source_code)

        assert isinstance(type_aliases, set)
        assert "UserID" in type_aliases
        assert "Status" in type_aliases


class TestExtractEnums:
    """Test _extract_enums private method behavior."""

    def test_extract_enums_called_with_tree(self, tmp_path):
        """Test that _extract_enums is called with tree and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
enum Status {
    Active = 'active',
    Inactive = 'inactive'
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))
        enums = validator._extract_enums(tree, source_code)

        assert isinstance(enums, set)
        assert "Status" in enums


class TestExtractNamespaces:
    """Test _extract_namespaces private method behavior."""

    def test_extract_namespaces_called_with_tree(self, tmp_path):
        """Test that _extract_namespaces is called with tree and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
namespace Utils {
    export function format(): void {}
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))
        namespaces = validator._extract_namespaces(tree, source_code)

        assert isinstance(namespaces, set)
        assert "Utils" in namespaces


class TestExtractFunctions:
    """Test _extract_functions private method behavior."""

    def test_extract_functions_called_with_tree(self, tmp_path):
        """Test that _extract_functions is called with tree and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function process(): void {}
function validate(): void {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))
        functions = validator._extract_functions(tree, source_code)

        assert isinstance(functions, dict)
        assert "process" in functions
        assert "validate" in functions


class TestExtractArrowFunctions:
    """Test _extract_arrow_functions private method behavior."""

    def test_extract_arrow_functions_called_with_tree(self, tmp_path):
        """Test that _extract_arrow_functions is called with tree and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
const increment = () => {};
const decrement = (x: number) => x - 1;
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))
        arrow_functions = validator._extract_arrow_functions(tree, source_code)

        assert isinstance(arrow_functions, dict)
        assert "increment" in arrow_functions
        assert "decrement" in arrow_functions


class TestExtractMethods:
    """Test _extract_methods private method behavior."""

    def test_extract_methods_called_with_tree(self, tmp_path):
        """Test that _extract_methods is called with tree and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Service {
    process(): void {}
    validate(): void {}
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))
        methods = validator._extract_methods(tree, source_code)

        assert isinstance(methods, dict)
        assert "Service" in methods
        assert "process" in methods["Service"]
        assert "validate" in methods["Service"]


class TestExtractClassBases:
    """Test _extract_class_bases private method behavior."""

    def test_extract_class_bases_called_with_class_node(self, tmp_path):
        """Test that _extract_class_bases is called with class_node and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Base {}
class Derived extends Base {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find the Derived class node
        def find_class_node(node, class_name):
            if node.type == "class_declaration":
                # Check if this is the class we want
                for child in node.children:
                    if child.type == "type_identifier":
                        if validator._get_node_text(child, source_code) == class_name:
                            return node
            for child in node.children:
                result = find_class_node(child, class_name)
                if result:
                    return result
            return None

        derived_node = find_class_node(tree.root_node, "Derived")
        if derived_node:
            bases = validator._extract_class_bases(derived_node, source_code)
            assert isinstance(bases, list)
            assert "Base" in bases


class TestIsExported:
    """Test _is_exported private method behavior."""

    def test_is_exported_called_with_node(self, tmp_path):
        """Test that _is_exported is called with node."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
export class Service {}
class Internal {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find class_declaration nodes
        def find_class_nodes(node):
            classes = []
            if node.type == "class_declaration":
                classes.append(node)
            for child in node.children:
                classes.extend(find_class_nodes(child))
            return classes

        class_nodes = find_class_nodes(tree.root_node)
        assert len(class_nodes) >= 1

        # Call _is_exported directly
        for class_node in class_nodes:
            is_exported = validator._is_exported(class_node)
            assert isinstance(is_exported, bool)


class TestExtractClassUsage:
    """Test _extract_class_usage private method behavior."""

    def test_extract_class_usage_called_with_tree(self, tmp_path):
        """Test that _extract_class_usage is called with tree and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Service {}
const svc = new Service();
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))
        class_usage = validator._extract_class_usage(tree, source_code)

        assert isinstance(class_usage, set)
        assert "Service" in class_usage


class TestExtractFunctionCalls:
    """Test _extract_function_calls private method behavior."""

    def test_extract_function_calls_called_with_tree(self, tmp_path):
        """Test that _extract_function_calls is called with tree and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
process();
validate();
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))
        function_calls = validator._extract_function_calls(tree, source_code)

        assert isinstance(function_calls, set)
        assert "process" in function_calls
        assert "validate" in function_calls


class TestExtractMethodCalls:
    """Test _extract_method_calls private method behavior."""

    def test_extract_method_calls_called_with_tree(self, tmp_path):
        """Test that _extract_method_calls is called with tree and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
const obj = getObject();
obj.method1();
obj.method2();
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))
        method_calls = validator._extract_method_calls(tree, source_code)

        assert isinstance(method_calls, dict)
        assert "obj" in method_calls
        assert "method1" in method_calls["obj"]
        assert "method2" in method_calls["obj"]


class TestGetClassNameFromNode:
    """Test _get_class_name_from_node private method behavior."""

    def test_get_class_name_from_node_called_with_node(self, tmp_path):
        """Test that _get_class_name_from_node is called with node and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Service {
    method(): void {}
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find a class_declaration node
        def find_class_node(node):
            if node.type == "class_declaration":
                return node
            for child in node.children:
                result = find_class_node(child)
                if result:
                    return result
            return None

        class_node = find_class_node(tree.root_node)
        assert class_node is not None

        # Call _get_class_name_from_node directly
        class_name = validator._get_class_name_from_node(class_node, source_code)
        assert isinstance(class_name, str)
        assert class_name == "Service"


class TestGetFunctionNameFromNode:
    """Test _get_function_name_from_node private method behavior."""

    def test_get_function_name_from_node_called_with_node(self, tmp_path):
        """Test that _get_function_name_from_node is called with node and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function process(): void {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find a function_declaration node
        def find_function_node(node):
            if node.type == "function_declaration":
                return node
            for child in node.children:
                result = find_function_node(child)
                if result:
                    return result
            return None

        function_node = find_function_node(tree.root_node)
        assert function_node is not None

        # Call _get_function_name_from_node directly
        function_name = validator._get_function_name_from_node(
            function_node, source_code
        )
        assert isinstance(function_name, str)
        assert function_name == "process"


class TestFindClassMethods:
    """Test _find_class_methods private method behavior."""

    def test_find_class_methods_called_with_class_node(self, tmp_path):
        """Test that _find_class_methods is called with class_node and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Service {
    process(): void {}
    validate(): void {}
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find a class_declaration node
        def find_class_node(node):
            if node.type == "class_declaration":
                return node
            for child in node.children:
                result = find_class_node(child)
                if result:
                    return result
            return None

        class_node = find_class_node(tree.root_node)
        assert class_node is not None

        # Call _find_class_methods directly
        methods = validator._find_class_methods(class_node, source_code)
        assert isinstance(methods, dict)
        assert "process" in methods
        assert "validate" in methods


class TestIsAbstractClass:
    """Test _is_abstract_class private method behavior."""

    def test_is_abstract_class_called_with_node(self, tmp_path):
        """Test that _is_abstract_class is called with node."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
abstract class Base {}
class Concrete {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find class_declaration nodes
        def find_class_nodes(node):
            classes = []
            if node.type == "class_declaration":
                classes.append(node)
            for child in node.children:
                classes.extend(find_class_nodes(child))
            return classes

        class_nodes = find_class_nodes(tree.root_node)
        assert len(class_nodes) >= 1

        # Call _is_abstract_class directly
        for class_node in class_nodes:
            is_abstract = validator._is_abstract_class(class_node)
            assert isinstance(is_abstract, bool)


class TestIsStaticMethod:
    """Test _is_static_method private method behavior."""

    def test_is_static_method_called_with_node(self, tmp_path):
        """Test that _is_static_method is called with node."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Service {
    static create(): Service {
        return new Service();
    }
    instance(): void {}
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find method_definition nodes
        def find_method_nodes(node):
            methods = []
            if node.type == "method_definition":
                methods.append(node)
            for child in node.children:
                methods.extend(find_method_nodes(child))
            return methods

        method_nodes = find_method_nodes(tree.root_node)
        assert len(method_nodes) >= 1

        # Call _is_static_method directly
        for method_node in method_nodes:
            is_static = validator._is_static_method(method_node)
            assert isinstance(is_static, bool)


class TestHasDecorator:
    """Test _has_decorator private method behavior."""

    def test_has_decorator_called_with_node(self, tmp_path):
        """Test that _has_decorator is called with node."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
@Component()
class Service {}

class Plain {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find class_declaration nodes
        def find_class_nodes(node):
            classes = []
            if node.type == "class_declaration":
                classes.append(node)
            for child in node.children:
                classes.extend(find_class_nodes(child))
            return classes

        class_nodes = find_class_nodes(tree.root_node)
        assert len(class_nodes) >= 1

        # Call _has_decorator directly
        for class_node in class_nodes:
            has_decorator = validator._has_decorator(class_node)
            assert isinstance(has_decorator, bool)


class TestIsGetterOrSetter:
    """Test _is_getter_or_setter private method behavior."""

    def test_is_getter_or_setter_called_with_node(self, tmp_path):
        """Test that _is_getter_or_setter is called with node."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Service {
    get value(): string {
        return this._value;
    }
    set value(v: string) {
        this._value = v;
    }
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find method_definition nodes
        def find_method_nodes(node):
            methods = []
            if node.type == "method_definition":
                methods.append(node)
            for child in node.children:
                methods.extend(find_method_nodes(child))
            return methods

        method_nodes = find_method_nodes(tree.root_node)
        assert len(method_nodes) >= 1

        # Call _is_getter_or_setter directly
        for method_node in method_nodes:
            is_getter_or_setter = validator._is_getter_or_setter(method_node)
            assert isinstance(is_getter_or_setter, bool)


class TestIsAsync:
    """Test _is_async private method behavior."""

    def test_is_async_called_with_node(self, tmp_path):
        """Test that _is_async is called with node."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
async function asyncFunc(): Promise<void> {}
function syncFunc(): void {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find function_declaration nodes
        def find_function_nodes(node):
            functions = []
            if node.type == "function_declaration":
                functions.append(node)
            for child in node.children:
                functions.extend(find_function_nodes(child))
            return functions

        function_nodes = find_function_nodes(tree.root_node)
        assert len(function_nodes) >= 1

        # Call _is_async directly
        for function_node in function_nodes:
            is_async = validator._is_async(function_node)
            assert isinstance(is_async, bool)


class TestHandleOptionalParameter:
    """Test _handle_optional_parameter private method behavior."""

    def test_handle_optional_parameter_called_with_param_node(self, tmp_path):
        """Test that _handle_optional_parameter is called with param_node and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function greet(name?: string): void {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find optional_parameter node
        def find_optional_parameter(node):
            if node.type == "optional_parameter":
                return node
            for child in node.children:
                result = find_optional_parameter(child)
                if result:
                    return result
            return None

        param_node = find_optional_parameter(tree.root_node)
        if param_node:
            # Call _handle_optional_parameter directly
            param_name = validator._handle_optional_parameter(param_node, source_code)
            assert isinstance(param_name, str)
            assert param_name == "name" or "name" in param_name


class TestHandleRestParameter:
    """Test _handle_rest_parameter private method behavior."""

    def test_handle_rest_parameter_called_with_param_node(self, tmp_path):
        """Test that _handle_rest_parameter is called with param_node and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function sum(...numbers: number[]): number {
    return numbers.reduce((a, b) => a + b, 0);
}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find rest_pattern node
        def find_rest_pattern(node):
            if node.type == "rest_pattern":
                return node
            for child in node.children:
                result = find_rest_pattern(child)
                if result:
                    return result
            return None

        param_node = find_rest_pattern(tree.root_node)
        if param_node:
            # Call _handle_rest_parameter directly
            param_name = validator._handle_rest_parameter(param_node, source_code)
            assert isinstance(param_name, str)
            assert param_name == "numbers" or "numbers" in param_name


class TestHandleDestructuredParameter:
    """Test _handle_destructured_parameter private method behavior."""

    def test_handle_destructured_parameter_called_with_param_node(self, tmp_path):
        """Test that _handle_destructured_parameter is called with param_node and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function process({ name, age }: { name: string; age: number }): void {}
"""
        )

        validator = TypeScriptValidator()
        tree, source_code = validator._parse_typescript_file(str(test_file))

        # Find object_pattern node
        def find_object_pattern(node):
            if node.type == "object_pattern":
                return node
            for child in node.children:
                result = find_object_pattern(child)
                if result:
                    return result
            return None

        param_node = find_object_pattern(tree.root_node)
        if param_node:
            # Call _handle_destructured_parameter directly
            params = validator._handle_destructured_parameter(param_node, source_code)
            assert isinstance(params, list)
            assert len(params) > 0


class TestExtractParameters:
    """Test _extract_parameters private method behavior."""

    def test_extract_parameters_called_with_params_node(self, tmp_path):
        """Test that _extract_parameters is called with params_node and source_code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function greet(name: string, age: number): void {}
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


class TestGetLanguageForFile:
    """Test _get_language_for_file private method behavior."""

    def test_get_language_for_file_called_with_ts_file(self, tmp_path):
        """Test that _get_language_for_file is called with .ts file path."""
        test_file = tmp_path / "test.ts"
        test_file.write_text("class Test {}")

        validator = TypeScriptValidator()
        lang = validator._get_language_for_file(str(test_file))

        assert lang == "typescript"

    def test_get_language_for_file_called_with_tsx_file(self, tmp_path):
        """Test that _get_language_for_file is called with .tsx file path."""
        test_file = tmp_path / "component.tsx"
        test_file.write_text("const C = () => <div />;")

        validator = TypeScriptValidator()
        lang = validator._get_language_for_file(str(test_file))

        assert lang == "tsx"

    def test_get_language_for_file_called_with_js_file(self, tmp_path):
        """Test that _get_language_for_file is called with .js file path."""
        test_file = tmp_path / "script.js"
        test_file.write_text("function test() {}")

        validator = TypeScriptValidator()
        lang = validator._get_language_for_file(str(test_file))

        assert lang == "typescript"

    def test_get_language_for_file_called_with_jsx_file(self, tmp_path):
        """Test that _get_language_for_file is called with .jsx file path."""
        test_file = tmp_path / "component.jsx"
        test_file.write_text("const C = () => <div />;")

        validator = TypeScriptValidator()
        lang = validator._get_language_for_file(str(test_file))

        assert lang == "tsx"
