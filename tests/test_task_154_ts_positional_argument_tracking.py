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
