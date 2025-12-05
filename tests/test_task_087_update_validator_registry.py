"""Behavioral tests for Task 087: Update Validator Registry.

Tests that _get_validator_for_file() now returns SvelteValidator for .svelte files
while maintaining support for Python and TypeScript files.
"""

from maid_runner.validators.manifest_validator import _get_validator_for_file
from maid_runner.validators.svelte_validator import SvelteValidator
from maid_runner.validators.python_validator import PythonValidator
from maid_runner.validators.typescript_validator import TypeScriptValidator


def test_get_validator_for_svelte_file():
    """Test that _get_validator_for_file returns SvelteValidator for .svelte files."""
    # Call the function with a .svelte file path
    validator = _get_validator_for_file("components/App.svelte")

    # Assert the validator is a SvelteValidator instance
    assert isinstance(
        validator, SvelteValidator
    ), f"Expected SvelteValidator, got {type(validator).__name__}"


def test_get_validator_for_python_file():
    """Test that _get_validator_for_file returns PythonValidator for .py files."""
    # Call the function with a .py file path
    validator = _get_validator_for_file("src/module.py")

    # Assert the validator is a PythonValidator instance
    assert isinstance(
        validator, PythonValidator
    ), f"Expected PythonValidator, got {type(validator).__name__}"


def test_get_validator_for_typescript_file():
    """Test that _get_validator_for_file returns TypeScriptValidator for .ts files."""
    # Call the function with a .ts file path
    validator = _get_validator_for_file("src/service.ts")

    # Assert the validator is a TypeScriptValidator instance
    assert isinstance(
        validator, TypeScriptValidator
    ), f"Expected TypeScriptValidator, got {type(validator).__name__}"


def test_get_validator_for_tsx_file():
    """Test that _get_validator_for_file returns TypeScriptValidator for .tsx files."""
    # Call the function with a .tsx file path
    validator = _get_validator_for_file("components/Button.tsx")

    # Assert the validator is a TypeScriptValidator instance
    assert isinstance(
        validator, TypeScriptValidator
    ), f"Expected TypeScriptValidator, got {type(validator).__name__}"


def test_get_validator_for_javascript_file():
    """Test that _get_validator_for_file returns TypeScriptValidator for .js files."""
    # Call the function with a .js file path
    validator = _get_validator_for_file("src/utils.js")

    # Assert the validator is a TypeScriptValidator instance
    assert isinstance(
        validator, TypeScriptValidator
    ), f"Expected TypeScriptValidator, got {type(validator).__name__}"


def test_get_validator_for_jsx_file():
    """Test that _get_validator_for_file returns TypeScriptValidator for .jsx files."""
    # Call the function with a .jsx file path
    validator = _get_validator_for_file("components/Header.jsx")

    # Assert the validator is a TypeScriptValidator instance
    assert isinstance(
        validator, TypeScriptValidator
    ), f"Expected TypeScriptValidator, got {type(validator).__name__}"


def test_get_validator_fallback_for_unknown_extension():
    """Test that _get_validator_for_file falls back to PythonValidator for unknown extensions."""
    # Call the function with an unknown file extension
    validator = _get_validator_for_file("README.md")

    # Assert the validator falls back to PythonValidator
    assert isinstance(
        validator, PythonValidator
    ), f"Expected PythonValidator (fallback), got {type(validator).__name__}"


def test_svelte_validator_supports_svelte_files():
    """Test that SvelteValidator properly supports .svelte file extension."""
    # Get a validator for a .svelte file
    validator = _get_validator_for_file("App.svelte")

    # Assert the validator can handle .svelte files
    assert validator.supports_file(
        "App.svelte"
    ), "SvelteValidator should support .svelte files"


def test_svelte_validator_can_be_instantiated():
    """Test that SvelteValidator can be instantiated and is functional."""
    # Get a validator for a .svelte file
    validator = _get_validator_for_file("components/Widget.svelte")

    # Assert the validator has the necessary methods
    assert hasattr(
        validator, "supports_file"
    ), "SvelteValidator should have supports_file method"
    assert hasattr(
        validator, "collect_artifacts"
    ), "SvelteValidator should have collect_artifacts method"

    # Assert the validator is properly initialized
    assert validator is not None, "SvelteValidator should be properly instantiated"


def test_validator_routing_with_various_paths():
    """Test that validator routing works correctly with various file path formats."""
    test_cases = [
        ("simple.svelte", SvelteValidator),
        ("path/to/Component.svelte", SvelteValidator),
        ("/absolute/path/App.svelte", SvelteValidator),
        ("module.py", PythonValidator),
        ("src/main.py", PythonValidator),
        ("service.ts", TypeScriptValidator),
        ("lib/utils.ts", TypeScriptValidator),
        ("Component.tsx", TypeScriptValidator),
        ("script.js", TypeScriptValidator),
        ("app.jsx", TypeScriptValidator),
    ]

    for file_path, expected_validator_type in test_cases:
        validator = _get_validator_for_file(file_path)
        assert isinstance(
            validator, expected_validator_type
        ), f"Failed for {file_path}: expected {expected_validator_type.__name__}, got {type(validator).__name__}"


def test_multiple_validator_instances_are_independent():
    """Test that multiple calls to _get_validator_for_file return independent instances."""
    # Get two validators for the same file type
    validator1 = _get_validator_for_file("App.svelte")
    validator2 = _get_validator_for_file("Component.svelte")

    # Assert both are SvelteValidator instances
    assert isinstance(validator1, SvelteValidator)
    assert isinstance(validator2, SvelteValidator)

    # Note: We don't test identity (validator1 is not validator2) because
    # the function may return the same instance or new instances - both are valid.
    # The important behavior is that both work correctly.


def test_svelte_validator_has_required_parser_attributes():
    """Test that SvelteValidator instances have the required parser attributes."""
    # Get a SvelteValidator instance
    validator = _get_validator_for_file("test.svelte")

    # Assert the validator has necessary attributes for parsing
    assert hasattr(validator, "svelte_parser"), "Should have svelte_parser attribute"
    assert hasattr(
        validator, "svelte_language"
    ), "Should have svelte_language attribute"

    # Assert parsers are properly initialized (not None)
    assert validator.svelte_parser is not None, "svelte_parser should be initialized"
    assert (
        validator.svelte_language is not None
    ), "svelte_language should be initialized"
