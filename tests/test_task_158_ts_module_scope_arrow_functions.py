"""Tests for task-158: Module-scope arrow function detection.

Only module-level arrow function declarations should be detected as public functions.
Nested arrow functions inside other functions are local variables and should NOT
be detected as public declarations.
"""

import os
import tempfile

from maid_runner.validators.typescript_validator import TypeScriptValidator


class TestExtractArrowFunctionsMethod:
    """Direct tests for _extract_arrow_functions method behavior."""

    def test_extract_arrow_functions_excludes_nested(self):
        """_extract_arrow_functions should not extract nested functions."""
        code = b"""
const topLevel = () => 'top';
function outer() {
    const nested = () => 'nested';
    return nested();
}
"""
        validator = TypeScriptValidator()
        tree = validator.ts_parser.parse(code)

        # Call _extract_arrow_functions directly
        functions = validator._extract_arrow_functions(tree, code)

        # Only top-level should be extracted
        assert "topLevel" in functions
        assert "nested" not in functions

    def test_extract_arrow_functions_includes_class_properties(self):
        """_extract_arrow_functions should still extract class properties."""
        code = b"""
class Service {
    handler = (data: string) => data;
}
"""
        validator = TypeScriptValidator()
        tree = validator.ts_parser.parse(code)

        functions = validator._extract_arrow_functions(tree, code)

        assert "handler" in functions


class TestIsAtModuleScope:
    """Direct tests for _is_at_module_scope method."""

    def test_module_level_declaration_is_at_module_scope(self):
        """Module-level declarations should be at module scope."""
        code = b"const topLevel = () => 'hello';"
        validator = TypeScriptValidator()
        tree = validator.ts_parser.parse(code)

        # Find the lexical_declaration node
        for child in tree.root_node.children:
            if child.type == "lexical_declaration":
                assert validator._is_at_module_scope(child) is True
                break

    def test_nested_declaration_not_at_module_scope(self):
        """Nested declarations inside functions should not be at module scope."""
        code = b"""
function outer() {
    const nested = () => 'nested';
    return nested();
}
"""
        validator = TypeScriptValidator()
        tree = validator.ts_parser.parse(code)

        # Find all lexical_declaration nodes
        declarations = []

        def find_declarations(node):
            if node.type == "lexical_declaration":
                declarations.append(node)
            for child in node.children:
                find_declarations(child)

        find_declarations(tree.root_node)

        # The nested declaration should not be at module scope
        assert len(declarations) == 1
        assert validator._is_at_module_scope(declarations[0]) is False

    def test_declaration_in_arrow_function_not_at_module_scope(self):
        """Declarations inside arrow functions should not be at module scope."""
        code = b"""
const outer = () => {
    const inner = () => 'inner';
    return inner();
};
"""
        validator = TypeScriptValidator()
        tree = validator.ts_parser.parse(code)

        declarations = []

        def find_declarations(node):
            if node.type == "lexical_declaration":
                declarations.append(node)
            for child in node.children:
                find_declarations(child)

        find_declarations(tree.root_node)

        # First declaration (outer) is at module scope
        # Second declaration (inner) is nested
        assert len(declarations) == 2
        assert validator._is_at_module_scope(declarations[0]) is True
        assert validator._is_at_module_scope(declarations[1]) is False


class TestNestedArrowFunctionsNotExtracted:
    """Test that nested arrow functions are NOT extracted."""

    def test_nested_in_regular_function_not_extracted(self):
        """Arrow functions nested in regular functions should not be extracted."""
        code = """
function outerFunction() {
    const innerHelper = () => 'helper';
    return innerHelper();
}

const topLevel = () => 'top';
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                # outerFunction and topLevel should be detected
                assert "outerFunction" in artifacts["found_functions"]
                assert "topLevel" in artifacts["found_functions"]
                # innerHelper should NOT be detected
                assert "innerHelper" not in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_nested_in_arrow_function_not_extracted(self):
        """Arrow functions nested in arrow functions should not be extracted."""
        code = """
const outerArrow = () => {
    const nestedArrow = () => 'nested';
    return nestedArrow();
};
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                assert "outerArrow" in artifacts["found_functions"]
                assert "nestedArrow" not in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_nested_in_promise_callback_not_extracted(self):
        """Arrow functions in Promise callbacks should not be extracted."""
        code = """
const asyncHandler = async () => {
    return new Promise((resolve) => {
        const nestedInPromise = () => resolve('done');
        nestedInPromise();
    });
};
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                assert "asyncHandler" in artifacts["found_functions"]
                assert "nestedInPromise" not in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_nested_in_foreach_callback_not_extracted(self):
        """Arrow functions in forEach callbacks should not be extracted."""
        code = """
const processItems = () => {
    [1, 2, 3].forEach(item => {
        const processItem = () => console.log(item);
        processItem();
    });
};
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                assert "processItems" in artifacts["found_functions"]
                assert "processItem" not in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_deeply_nested_not_extracted(self):
        """Deeply nested arrow functions should not be extracted."""
        code = """
const level1 = () => {
    const level2 = () => {
        const level3 = () => {
            const level4 = () => 'deep';
            return level4();
        };
        return level3();
    };
    return level2();
};
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                # Only level1 should be detected
                assert "level1" in artifacts["found_functions"]
                assert "level2" not in artifacts["found_functions"]
                assert "level3" not in artifacts["found_functions"]
                assert "level4" not in artifacts["found_functions"]
            finally:
                os.unlink(f.name)


class TestModuleLevelArrowFunctionsExtracted:
    """Test that module-level arrow functions ARE still extracted."""

    def test_simple_module_level_extracted(self):
        """Simple module-level arrow functions should be extracted."""
        code = """
const func1 = () => 'hello';
const func2 = (x: number) => x * 2;
const func3 = async () => Promise.resolve('async');
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                assert "func1" in artifacts["found_functions"]
                assert "func2" in artifacts["found_functions"]
                assert "func3" in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_exported_module_level_extracted(self):
        """Exported module-level arrow functions should be extracted."""
        code = """
export const exportedFunc = () => 'exported';
export const anotherExport = (data: string) => data.toUpperCase();
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                assert "exportedFunc" in artifacts["found_functions"]
                assert "anotherExport" in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_class_property_arrow_still_extracted(self):
        """Class property arrow functions should still be extracted."""
        code = """
class MyClass {
    handler = (data: string) => data.toUpperCase();
    onClick = () => console.log('clicked');
}
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                assert "handler" in artifacts["found_functions"]
                assert "onClick" in artifacts["found_functions"]
            finally:
                os.unlink(f.name)


class TestMixedScenarios:
    """Test mixed scenarios with both module-level and nested functions."""

    def test_factory_function_pattern(self):
        """Factory functions should be detected but not their returned methods."""
        code = """
const createApi = () => {
    const get = (url: string) => fetch(url);
    const post = (url: string, data: any) => fetch(url, { method: 'POST' });
    return { get, post };
};
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                # createApi is module-level
                assert "createApi" in artifacts["found_functions"]
                # get and post are nested
                assert "get" not in artifacts["found_functions"]
                assert "post" not in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_higher_order_function_pattern(self):
        """Higher-order functions should be detected correctly."""
        code = """
const withLogging = (fn: Function) => {
    const wrapper = (...args: any[]) => {
        console.log('calling with', args);
        return fn(...args);
    };
    return wrapper;
};

const multiply = (a: number, b: number) => a * b;
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                # Module-level arrow functions
                assert "withLogging" in artifacts["found_functions"]
                assert "multiply" in artifacts["found_functions"]
                # Nested function (inside withLogging)
                assert "wrapper" not in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_react_hook_with_internal_functions(self):
        """React hooks with internal functions should only detect the hook."""
        code = """
const useCustomHook = (initialValue: number) => {
    const increment = () => setValue(v => v + 1);
    const decrement = () => setValue(v => v - 1);
    const reset = () => setValue(initialValue);

    return { increment, decrement, reset };
};
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsx", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                # Only the hook should be detected
                assert "useCustomHook" in artifacts["found_functions"]
                # Internal functions should not be detected
                assert "increment" not in artifacts["found_functions"]
                assert "decrement" not in artifacts["found_functions"]
                assert "reset" not in artifacts["found_functions"]
            finally:
                os.unlink(f.name)
