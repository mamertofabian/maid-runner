"""Validation result types for structured validation output.

Provides LSP-compatible data structures for validation results,
supporting the --json-output flag in CLI commands.
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ErrorSeverity(Enum):
    """Enum for validation error severity levels."""

    ERROR = "error"
    WARNING = "warning"


@dataclass
class ValidationError:
    """Dataclass representing a single validation error with location info."""

    code: str
    message: str
    file: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    severity: ErrorSeverity = ErrorSeverity.ERROR

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for JSON serialization.

        Returns:
            Dictionary with code, message, severity (always),
            and file, line, column (only if set).
        """
        result: Dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
        }

        if self.file is not None:
            result["file"] = self.file
        if self.line is not None:
            result["line"] = self.line
        if self.column is not None:
            result["column"] = self.column

        return result


@dataclass
class ValidationResult:
    """Dataclass representing complete validation result with errors and metadata."""

    success: bool = True
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, error: ValidationError) -> None:
        """Add error to result, sets success=False if severity is ERROR.

        Args:
            error: The validation error to add.
        """
        if error.severity == ErrorSeverity.ERROR:
            self.errors.append(error)
            self.success = False
        else:
            self.warnings.append(error)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to maid-lsp compatible dictionary.

        Returns:
            Dictionary with success, errors, warnings, and metadata.
        """
        return {
            "success": self.success,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "metadata": self.metadata,
        }

    def to_json(self, indent: Optional[int] = None) -> str:
        """Convert result to JSON string.

        Args:
            indent: Optional indentation level for pretty-printing.

        Returns:
            JSON string representation of the validation result.
        """
        return json.dumps(self.to_dict(), indent=indent)
