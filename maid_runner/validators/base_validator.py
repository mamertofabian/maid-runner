"""Base validator abstract class for language-agnostic validation.

This module defines the abstract interface that all language-specific validators
must implement. It provides a common structure for artifact collection and validation
while allowing language-specific implementations to handle their own AST parsing.
"""

from abc import ABC, abstractmethod
from typing import Dict, Set, Optional


class ArtifactCollection:
    """Container for collected artifacts from source code.

    This class holds all artifacts discovered during AST parsing,
    including classes, functions, methods, attributes, and type information.
    """

    def __init__(self):
        """Initialize empty artifact collection."""
        self.found_classes: Set[str] = set()
        self.found_class_bases: Dict[str, list] = {}
        self.found_attributes: Dict[Optional[str], Set[str]] = {}
        self.found_functions: Dict[str, list] = {}
        self.found_methods: Dict[str, Dict[str, list]] = {}
        self.found_function_types: Dict[str, dict] = {}
        self.found_method_types: Dict[str, Dict[str, dict]] = {}

        # For behavioral validation
        self.used_classes: Set[str] = set()
        self.used_functions: Set[str] = set()
        self.used_methods: Dict[str, Set[str]] = {}
        self.used_arguments: Set[str] = set()


class BaseValidator(ABC):
    """Abstract base class for language-specific validators.

    All language validators (Python, TypeScript, etc.) must implement
    this interface to provide consistent artifact collection and validation.
    """

    @abstractmethod
    def collect_artifacts(self, file_path: str, validation_mode: str) -> dict:
        """Collect artifacts from a source file.

        Args:
            file_path: Path to the source file to parse
            validation_mode: Either "implementation" or "behavioral"

        Returns:
            Dictionary containing collected artifacts in a format compatible
            with the existing validation infrastructure
        """
        pass

    @abstractmethod
    def supports_file(self, file_path: str) -> bool:
        """Check if this validator can handle the given file type.

        Args:
            file_path: Path to the file to check

        Returns:
            True if this validator supports the file extension, False otherwise
        """
        pass
