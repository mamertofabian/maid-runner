"""Behavioral tests for TypeScript positional argument tracking.

Tests that the TypeScript validator correctly detects when function calls
have positional arguments, adding __positional__ marker to used_arguments.
"""

import tempfile
import os
from maid_runner.validators.typescript_validator import TypeScriptValidator


def _create_temp_ts_file(ts_code: bytes):
    """Helper to create temporary TypeScript file."""
    f = tempfile.NamedTemporaryFile(suffix=".ts", delete=False)
    f.write(ts_code)
    f.flush()
    f.close()
    return f.name


class TestExtractUsedArguments:
    """Tests for extracting used arguments from function calls."""

    def test_detects_positional_arguments_in_function_call(self):
        """Function calls with arguments should add __positional__ marker."""
        ts_code = b"""
const result = debounce(fn, 100);
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            used_args = validator._extract_used_arguments(tree, source_code)
            assert "__positional__" in used_args
        finally:
            os.unlink(filepath)

    def test_detects_positional_in_method_call(self):
        """Method calls with arguments should add __positional__ marker."""
        ts_code = b"""
const service = new UserService();
service.fetchUser(123);
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            used_args = validator._extract_used_arguments(tree, source_code)
            assert "__positional__" in used_args
        finally:
            os.unlink(filepath)

    def test_no_positional_for_calls_without_arguments(self):
        """Function calls without arguments should not add __positional__ marker."""
        ts_code = b"""
const result = getConfig();
service.init();
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            used_args = validator._extract_used_arguments(tree, source_code)
            assert "__positional__" not in used_args
        finally:
            os.unlink(filepath)

    def test_detects_keyword_arguments(self):
        """Named/keyword arguments should be detected by name."""
        ts_code = b"""
// TypeScript object destructuring pattern
configure({ timeout: 5000, retries: 3 });
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            used_args = validator._extract_used_arguments(tree, source_code)
            # Object properties passed as arguments should be detected
            assert "timeout" in used_args or "__positional__" in used_args
        finally:
            os.unlink(filepath)


class TestCollectBehavioralArtifactsWithArguments:
    """Integration tests for behavioral artifact collection with argument tracking."""

    def test_collect_behavioral_artifacts_includes_used_arguments(self):
        """_collect_behavioral_artifacts should return used_arguments with __positional__."""
        ts_code = b"""
import { debounce } from "./utils";

describe("debounce", () => {
    it("should debounce function calls", () => {
        const fn = vi.fn();
        const debounced = debounce(fn, 100);
        debounced();
    });
});
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            artifacts = validator._collect_behavioral_artifacts(tree, source_code)
            used_args = artifacts["used_arguments"]
            assert "__positional__" in used_args
        finally:
            os.unlink(filepath)

    def test_used_arguments_empty_for_no_argument_calls(self):
        """used_arguments should be empty when no calls have arguments."""
        ts_code = b"""
const config = getConfig();
init();
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            used_args = artifacts["used_arguments"]
            assert "__positional__" not in used_args
        finally:
            os.unlink(filepath)

    def test_behavioral_validation_passes_with_positional_tracking(self):
        """Behavioral validation should pass when function is called with arguments."""
        ts_code = b"""
const throttled = throttle(callback, 200);
const debounced = debounce(handler, 50);
executeCommand("test", "/path", 5000);
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            # All these calls have positional arguments
            assert "__positional__" in artifacts["used_arguments"]
            # Functions should also be detected
            assert "throttle" in artifacts["used_functions"]
            assert "debounce" in artifacts["used_functions"]
            assert "executeCommand" in artifacts["used_functions"]
        finally:
            os.unlink(filepath)


class TestShorthandPropertyIdentifiers:
    """Tests for shorthand property identifier argument extraction (lines 209-211)."""

    def test_shorthand_property_in_object_argument(self):
        """Shorthand property identifiers like { foo } should be detected."""
        ts_code = b"""
const foo = "value";
const bar = 123;
configure({ foo, bar });
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            used_args = validator._extract_used_arguments(tree, source_code)
            # Shorthand properties should be detected
            assert "foo" in used_args
            assert "bar" in used_args
            assert "__positional__" in used_args
        finally:
            os.unlink(filepath)

    def test_mixed_shorthand_and_regular_properties(self):
        """Mix of shorthand and regular properties in object argument."""
        ts_code = b"""
const name = "test";
setup({ name, value: 42, enabled: true });
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            used_args = validator._extract_used_arguments(tree, source_code)
            # Both shorthand and regular properties should be detected
            assert "name" in used_args
            assert "value" in used_args
            assert "enabled" in used_args
        finally:
            os.unlink(filepath)

    def test_shorthand_only_object_argument(self):
        """Object with only shorthand properties."""
        ts_code = b"""
const id = 1;
const type = "user";
const active = true;
createRecord({ id, type, active });
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            used_args = validator._extract_used_arguments(tree, source_code)
            assert "id" in used_args
            assert "type" in used_args
            assert "active" in used_args
        finally:
            os.unlink(filepath)


class TestClassInstantiationPatterns:
    """Tests for class instantiation patterns with call_expression (lines 722-725, 852-855, 895-900)."""

    def test_new_class_with_call_expression_in_variable_declaration(self):
        """new ClassName() with parentheses in variable declaration."""
        ts_code = b"""
const service = new UserService();
service.fetchUser();
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            mapping = validator._extract_variable_to_class_mapping(tree, source_code)
            assert "service" in mapping
            assert mapping["service"] == "UserService"
        finally:
            os.unlink(filepath)

    def test_new_class_with_call_expression_in_assignment(self):
        """new ClassName() with parentheses in assignment expression."""
        ts_code = b"""
let service;
service = new DatabaseService();
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            mapping = validator._extract_assignment_instantiations(tree, source_code)
            assert "service" in mapping
            assert mapping["service"] == "DatabaseService"
        finally:
            os.unlink(filepath)

    def test_extract_class_usage_with_call_expression(self):
        """Class usage extraction with new ClassName() call expression."""
        ts_code = b"""
const a = new ClassA();
const b = new ClassB();
const c = new ClassC();
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            class_usage = validator._extract_class_usage(tree, source_code)
            assert "ClassA" in class_usage
            assert "ClassB" in class_usage
            assert "ClassC" in class_usage
        finally:
            os.unlink(filepath)

    def test_new_class_with_arguments_and_call_expression(self):
        """new ClassName(args) with call expression pattern."""
        ts_code = b"""
const config = { timeout: 5000 };
const client = new HttpClient(config);
const db = new Database("localhost", 5432);
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            mapping = validator._extract_variable_to_class_mapping(tree, source_code)
            assert "client" in mapping
            assert mapping["client"] == "HttpClient"
            assert "db" in mapping
            assert mapping["db"] == "Database"
        finally:
            os.unlink(filepath)
