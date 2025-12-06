"""Private helper functions for validate.py CLI module.

These helpers were extracted during refactoring to reduce code duplication
and improve maintainability. They handle common patterns used across
validation watch handlers and execution flows.
"""

from pathlib import Path
from typing import Dict, Optional


def _are_validations_passed(results: Dict[str, Optional[bool]]) -> bool:
    """Check if all validations passed (ignoring None/skipped).

    Args:
        results: Dict with validation results

    Returns:
        True if all non-None validations passed
    """
    return all(v is True for k, v in results.items() if k != "tests" and v is not None)


def _get_display_path(file_path: Path, project_root: Path) -> Path:
    """Get relative path for display, falling back to absolute if needed.

    Args:
        file_path: Path to convert
        project_root: Project root directory

    Returns:
        Relative path if possible, otherwise absolute path
    """
    try:
        return file_path.resolve().relative_to(project_root)
    except ValueError:
        return file_path


def _should_skip_debounce(
    last_run: float, current_time: float, debounce_seconds: float
) -> bool:
    """Check if event should be skipped due to debounce.

    Args:
        last_run: Timestamp of last run
        current_time: Current timestamp
        debounce_seconds: Debounce interval in seconds

    Returns:
        True if should skip, False otherwise
    """
    return current_time - last_run <= debounce_seconds
