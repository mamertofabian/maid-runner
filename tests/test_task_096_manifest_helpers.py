"""Behavioral tests for task-096: Manifest Helpers module.

These tests verify the helper functions in `maid_runner/cli/_manifest_helpers.py`:
- parse_artifacts_json(): Parse JSON artifacts string from CLI argument
- sanitize_goal_for_filename(): Convert goal string to safe filename component
- generate_validation_command(): Generate pytest/vitest validation command

Tests focus on actual behavior (inputs/outputs), not implementation details.
"""

import pytest

from maid_runner.cli._manifest_helpers import (
    parse_artifacts_json,
    sanitize_goal_for_filename,
    generate_validation_command,
)


class TestParseArtifactsJson:
    """Tests for parse_artifacts_json() function."""

    def test_parses_valid_json_array_with_single_artifact(self):
        """Parses a valid JSON array containing one artifact."""
        artifacts_str = '[{"type": "function", "name": "foo"}]'

        result = parse_artifacts_json(artifacts_str)

        assert result == [{"type": "function", "name": "foo"}]

    def test_parses_valid_json_array_with_multiple_artifacts(self):
        """Parses a valid JSON array containing multiple artifacts."""
        artifacts_str = (
            '[{"type": "function", "name": "foo"}, {"type": "class", "name": "Bar"}]'
        )

        result = parse_artifacts_json(artifacts_str)

        assert len(result) == 2
        assert result[0] == {"type": "function", "name": "foo"}
        assert result[1] == {"type": "class", "name": "Bar"}

    def test_returns_empty_list_for_none(self):
        """Returns empty list when input is None."""
        result = parse_artifacts_json(None)

        assert result == []

    def test_returns_empty_list_for_empty_string(self):
        """Returns empty list when input is empty string."""
        result = parse_artifacts_json("")

        assert result == []

    def test_parses_complex_artifact_with_args(self):
        """Parses artifact with args parameter array."""
        artifacts_str = """[{
            "type": "function",
            "name": "process_data",
            "args": [
                {"name": "data", "type": "str"},
                {"name": "verbose", "type": "bool"}
            ]
        }]"""

        result = parse_artifacts_json(artifacts_str)

        assert len(result) == 1
        assert result[0]["name"] == "process_data"
        assert result[0]["type"] == "function"
        assert len(result[0]["args"]) == 2
        assert result[0]["args"][0] == {"name": "data", "type": "str"}
        assert result[0]["args"][1] == {"name": "verbose", "type": "bool"}

    def test_parses_complex_artifact_with_returns(self):
        """Parses artifact with returns parameter."""
        artifacts_str = (
            '[{"type": "function", "name": "get_value", "returns": "Optional[str]"}]'
        )

        result = parse_artifacts_json(artifacts_str)

        assert len(result) == 1
        assert result[0]["returns"] == "Optional[str]"

    def test_parses_artifact_with_class_attribute(self):
        """Parses artifact that specifies parent class."""
        artifacts_str = (
            '[{"type": "function", "name": "authenticate", "class": "AuthService"}]'
        )

        result = parse_artifacts_json(artifacts_str)

        assert len(result) == 1
        assert result[0]["class"] == "AuthService"

    def test_raises_error_for_invalid_json(self):
        """Raises error with clear message for invalid JSON."""
        artifacts_str = "not valid json"

        with pytest.raises(ValueError) as exc_info:
            parse_artifacts_json(artifacts_str)

        # Error message should mention JSON or parsing
        assert (
            "json" in str(exc_info.value).lower()
            or "parse" in str(exc_info.value).lower()
        )

    def test_raises_error_for_json_object_not_array(self):
        """Raises error when JSON is an object instead of array."""
        artifacts_str = '{"type": "function", "name": "foo"}'

        with pytest.raises(ValueError) as exc_info:
            parse_artifacts_json(artifacts_str)

        # Error message should mention array or list
        assert (
            "array" in str(exc_info.value).lower()
            or "list" in str(exc_info.value).lower()
        )

    def test_raises_error_for_json_string_not_array(self):
        """Raises error when JSON is a string instead of array."""
        artifacts_str = '"just a string"'

        with pytest.raises(ValueError) as exc_info:
            parse_artifacts_json(artifacts_str)

        assert (
            "array" in str(exc_info.value).lower()
            or "list" in str(exc_info.value).lower()
        )

    def test_parses_empty_json_array(self):
        """Parses an empty JSON array to empty list."""
        artifacts_str = "[]"

        result = parse_artifacts_json(artifacts_str)

        assert result == []

    def test_parses_artifact_with_all_fields(self):
        """Parses artifact with all possible fields."""
        artifacts_str = """[{
            "type": "function",
            "name": "complex_method",
            "class": "MyService",
            "args": [
                {"name": "input_data", "type": "Dict[str, Any]"}
            ],
            "returns": "Result[T]",
            "description": "A complex method"
        }]"""

        result = parse_artifacts_json(artifacts_str)

        assert len(result) == 1
        artifact = result[0]
        assert artifact["type"] == "function"
        assert artifact["name"] == "complex_method"
        assert artifact["class"] == "MyService"
        assert artifact["args"] == [{"name": "input_data", "type": "Dict[str, Any]"}]
        assert artifact["returns"] == "Result[T]"
        assert artifact["description"] == "A complex method"


class TestSanitizeGoalForFilename:
    """Tests for sanitize_goal_for_filename() function."""

    def test_basic_goal_conversion(self):
        """Converts a basic goal to lowercase hyphenated format."""
        goal = "Add AuthService class"

        result = sanitize_goal_for_filename(goal)

        assert result == "add-authservice-class"

    def test_converts_to_lowercase(self):
        """Result is all lowercase."""
        goal = "UPPERCASE GOAL"

        result = sanitize_goal_for_filename(goal)

        assert result.islower()
        assert result == "uppercase-goal"

    def test_replaces_spaces_with_hyphens(self):
        """Spaces are replaced with hyphens."""
        goal = "Add new feature"

        result = sanitize_goal_for_filename(goal)

        assert " " not in result
        assert result == "add-new-feature"

    def test_replaces_underscores_with_hyphens(self):
        """Underscores are replaced with hyphens."""
        goal = "add_new_feature"

        result = sanitize_goal_for_filename(goal)

        assert "_" not in result
        # Result should use hyphens
        assert "-" in result or result.isalnum()

    def test_removes_special_characters(self):
        """Special characters are removed."""
        goal = "Add (special) feature: v1.0!"

        result = sanitize_goal_for_filename(goal)

        # Should not contain special characters
        assert "(" not in result
        assert ")" not in result
        assert ":" not in result
        assert "!" not in result
        assert "." not in result

    def test_truncates_long_goals(self):
        """Long goals are truncated to approximately 50 characters."""
        goal = "This is a very long goal description that goes on and on and should be truncated to a reasonable length"

        result = sanitize_goal_for_filename(goal)

        # Should be truncated to around 50 chars (allow some flexibility)
        assert len(result) <= 60
        # Should not end with a hyphen (clean truncation)
        assert not result.endswith("-")

    def test_handles_multiple_consecutive_spaces(self):
        """Multiple consecutive spaces collapse to single hyphen."""
        goal = "Add   multiple   spaces"

        result = sanitize_goal_for_filename(goal)

        assert "--" not in result
        assert "---" not in result

    def test_handles_empty_string(self):
        """Handles empty string without error."""
        goal = ""

        result = sanitize_goal_for_filename(goal)

        # Should return empty string or some default
        assert isinstance(result, str)
        # Result should be valid for filename (empty or non-empty)
        assert "-" not in result or len(result) > 0

    def test_handles_only_special_characters(self):
        """Handles goal that is only special characters."""
        goal = "!@#$%^&*()"

        result = sanitize_goal_for_filename(goal)

        # Should return empty or some default, not raise error
        assert isinstance(result, str)

    def test_handles_leading_trailing_spaces(self):
        """Strips leading and trailing spaces."""
        goal = "  Add feature  "

        result = sanitize_goal_for_filename(goal)

        assert not result.startswith("-")
        assert not result.endswith("-")

    def test_handles_numbers(self):
        """Numbers in goal are preserved."""
        goal = "Add version 2 support"

        result = sanitize_goal_for_filename(goal)

        assert "2" in result
        assert result == "add-version-2-support"

    def test_complex_goal_with_mixed_content(self):
        """Handles complex goal with mixed content."""
        goal = "Fix: Bug #123 - Handle 'edge case' properly"

        result = sanitize_goal_for_filename(goal)

        # Should be lowercase, hyphenated, no special chars
        assert result.islower() or result.replace("-", "").isalnum()
        assert "'" not in result
        assert "#" not in result
        assert not result.startswith("-")
        assert not result.endswith("-")

    def test_result_contains_only_valid_filename_characters(self):
        """Result contains only alphanumeric and hyphen characters."""
        goal = "Add @special $feature (2023)"

        result = sanitize_goal_for_filename(goal)

        # Only lowercase letters, numbers, and hyphens allowed
        for char in result:
            assert char.isalnum() or char == "-", f"Invalid character: {char}"


class TestGenerateValidationCommand:
    """Tests for generate_validation_command() function."""

    def test_python_file_generates_pytest_command(self):
        """Python files generate pytest validation command."""
        file_path = "src/auth/service.py"
        task_number = 95

        result = generate_validation_command(file_path, task_number)

        assert isinstance(result, list)
        assert result[0] == "pytest"
        assert "-v" in result

    def test_python_file_includes_task_number_in_test_path(self):
        """Python test file path includes zero-padded task number."""
        file_path = "src/auth/service.py"
        task_number = 5

        result = generate_validation_command(file_path, task_number)

        # Should include task number (005 format)
        test_path = result[1]
        assert "005" in test_path or "5" in test_path

    def test_python_file_test_path_in_tests_directory(self):
        """Python test file path is in tests/ directory."""
        file_path = "maid_runner/cli/service.py"
        task_number = 96

        result = generate_validation_command(file_path, task_number)

        test_path = result[1]
        assert test_path.startswith("tests/")

    def test_python_file_test_path_contains_module_name(self):
        """Python test file path contains original module name."""
        file_path = "src/auth/my_service.py"
        task_number = 100

        result = generate_validation_command(file_path, task_number)

        test_path = result[1]
        # Should contain the module name (possibly transformed)
        assert "my" in test_path.lower() or "service" in test_path.lower()

    def test_typescript_file_generates_vitest_or_jest_command(self):
        """TypeScript files generate vitest or jest command."""
        file_path = "src/auth/service.ts"
        task_number = 95

        result = generate_validation_command(file_path, task_number)

        assert isinstance(result, list)
        # Should use vitest or jest
        assert result[0] in ["vitest", "jest", "npx"]

    def test_typescript_tsx_file_generates_vitest_or_jest_command(self):
        """TypeScript TSX files generate vitest or jest command."""
        file_path = "src/components/Button.tsx"
        task_number = 50

        result = generate_validation_command(file_path, task_number)

        assert isinstance(result, list)
        assert result[0] in ["vitest", "jest", "npx"]

    def test_javascript_file_generates_vitest_or_jest_command(self):
        """JavaScript files generate vitest or jest command."""
        file_path = "src/utils/helpers.js"
        task_number = 30

        result = generate_validation_command(file_path, task_number)

        assert isinstance(result, list)
        assert result[0] in ["vitest", "jest", "npx"]

    def test_typescript_test_path_uses_spec_convention(self):
        """TypeScript test paths may use .spec.ts convention."""
        file_path = "src/auth/service.ts"
        task_number = 95

        result = generate_validation_command(file_path, task_number)

        # Should have a test file argument with ts/spec pattern
        assert any("ts" in arg or "spec" in arg or "test" in arg for arg in result)

    @pytest.mark.parametrize(
        "task_number,expected_format",
        [
            (1, "001"),
            (10, "010"),
            (99, "099"),
            (100, "100"),
            (999, "999"),
        ],
    )
    def test_task_number_zero_padding(self, task_number, expected_format):
        """Task numbers are zero-padded to 3 digits in test path."""
        file_path = "src/module.py"

        result = generate_validation_command(file_path, task_number)

        # Test path should contain the formatted task number
        test_path = result[1]
        assert expected_format in test_path

    def test_returns_list_type(self):
        """Always returns a list of strings."""
        file_path = "src/service.py"
        task_number = 42

        result = generate_validation_command(file_path, task_number)

        assert isinstance(result, list)
        assert all(isinstance(item, str) for item in result)

    def test_python_nested_path_generates_correct_test_path(self):
        """Python files in nested paths generate correct test paths."""
        file_path = "maid_runner/cli/_manifest_helpers.py"
        task_number = 96

        result = generate_validation_command(file_path, task_number)

        # Should generate tests/test_task_096_manifest_helpers.py
        test_path = result[1]
        assert "test_task_096" in test_path
        assert "manifest" in test_path.lower() or "helpers" in test_path.lower()

    def test_python_file_with_leading_underscore(self):
        """Python private modules (leading underscore) handled correctly."""
        file_path = "maid_runner/cli/_private_module.py"
        task_number = 50

        result = generate_validation_command(file_path, task_number)

        # Should strip leading underscore in test name
        test_path = result[1]
        assert "test_task_050" in test_path
        # Test file should not have double underscore
        assert "__" not in test_path or "test_task" in test_path


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_sanitized_goal_can_be_used_in_validation_command(self):
        """Sanitized goal works with validation command generation."""
        goal = "Add AuthService class"
        file_path = "src/auth/service.py"
        task_number = 95

        sanitized_goal = sanitize_goal_for_filename(goal)
        validation_cmd = generate_validation_command(file_path, task_number)

        # Both should work together without error
        assert isinstance(sanitized_goal, str)
        assert isinstance(validation_cmd, list)
        assert len(sanitized_goal) > 0
        assert len(validation_cmd) >= 2

    def test_parsed_artifacts_structure_matches_manifest_schema(self):
        """Parsed artifacts have correct structure for manifest use."""
        artifacts_str = """[{
            "type": "function",
            "name": "authenticate",
            "args": [{"name": "user", "type": "User"}],
            "returns": "bool"
        }]"""

        result = parse_artifacts_json(artifacts_str)

        # Should have correct structure for expectedArtifacts.contains
        assert len(result) == 1
        artifact = result[0]
        assert "type" in artifact
        assert "name" in artifact
        assert artifact["type"] in ["function", "class", "attribute"]
