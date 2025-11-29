"""Python-specific validator implementation.

This module contains all Python AST parsing logic extracted from manifest_validator.py.
It provides Python-specific artifact collection and validation.
"""

from maid_runner.validators.base_validator import BaseValidator


class PythonValidator(BaseValidator):
    """Validator for Python source files.

    Handles .py files using Python's built-in AST module to collect
    artifacts (classes, functions, methods, attributes) and validate
    them against manifest declarations.
    """

    def supports_file(self, file_path: str) -> bool:
        """Check if this validator supports Python files.

        Args:
            file_path: Path to the file to check

        Returns:
            True if file has .py extension, False otherwise
        """
        return file_path.endswith(".py")

    def collect_artifacts(self, file_path: str, validation_mode: str) -> dict:
        """Collect artifacts from a Python file using AST parsing.

        Args:
            file_path: Path to the Python file to parse
            validation_mode: Either "implementation" or "behavioral"

        Returns:
            Dictionary containing collected artifacts compatible with
            the existing validation infrastructure
        """
        # Import the existing collector from manifest_validator
        # This maintains backward compatibility while we refactor
        from maid_runner.validators.manifest_validator import (
            _parse_file,
            _collect_artifacts_from_ast,
        )

        tree = _parse_file(file_path)
        collector = _collect_artifacts_from_ast(tree, validation_mode)

        # Return in compatible format
        return {
            "found_classes": collector.found_classes,
            "found_class_bases": collector.found_class_bases,
            "found_attributes": collector.found_attributes,
            "variable_to_class": collector.variable_to_class,
            "found_functions": collector.found_functions,
            "found_methods": collector.found_methods,
            "found_function_types": collector.found_function_types,
            "found_method_types": collector.found_method_types,
            "used_classes": collector.used_classes,
            "used_functions": collector.used_functions,
            "used_methods": collector.used_methods,
            "used_arguments": collector.used_arguments,
        }
