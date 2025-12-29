"""Private helper functions for manifest creation CLI module.

These helpers support the `maid manifest create` command by providing:
- JSON artifact parsing from CLI arguments
- Goal string sanitization for safe filenames
- Validation command generation based on file types
"""

import json
import re
from pathlib import Path
from typing import List, Optional


def parse_artifacts_json(artifacts_str: Optional[str]) -> List[dict]:
    """Parse JSON artifacts string from CLI argument into list of artifact dictionaries.

    Args:
        artifacts_str: JSON string representing an array of artifact objects,
            or None/empty string for no artifacts.

    Returns:
        List of artifact dictionaries. Empty list if input is None or empty.

    Raises:
        ValueError: If JSON is invalid or not an array.
    """
    if artifacts_str is None or artifacts_str == "":
        return []

    try:
        parsed = json.loads(artifacts_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")

    if not isinstance(parsed, list):
        raise ValueError(
            "Artifacts must be a JSON array, not "
            f'{type(parsed).__name__}. Example: \'[{{"type": "function", "name": "foo"}}]\''
        )

    return parsed


def sanitize_goal_for_filename(goal: str) -> str:
    """Convert goal string to safe filename component (lowercase, hyphens, truncated).

    Transforms the goal string into a safe filename component by:
    - Converting to lowercase
    - Replacing spaces and underscores with hyphens
    - Removing special characters (keeping alphanumeric and hyphens)
    - Collapsing multiple consecutive hyphens
    - Truncating to approximately 50 characters at a word boundary
    - Stripping leading/trailing hyphens

    Args:
        goal: The goal description string to sanitize.

    Returns:
        A sanitized string suitable for use in filenames.
    """
    # Convert to lowercase
    result = goal.lower()

    # Replace spaces and underscores with hyphens
    result = result.replace(" ", "-").replace("_", "-")

    # Remove special characters (keep alphanumeric and hyphens)
    result = re.sub(r"[^a-z0-9-]", "", result)

    # Collapse multiple consecutive hyphens
    result = re.sub(r"-+", "-", result)

    # Strip leading and trailing hyphens
    result = result.strip("-")

    # Truncate to approximately 50 characters at word boundary
    if len(result) > 50:
        # Try to truncate at a hyphen boundary
        truncated = result[:50]
        # Find last hyphen in truncated portion
        last_hyphen = truncated.rfind("-")
        if last_hyphen > 20:  # Only truncate at boundary if we keep reasonable length
            result = truncated[:last_hyphen]
        else:
            result = truncated
        # Clean up trailing hyphen after truncation
        result = result.rstrip("-")

    return result


def generate_validation_command(file_path: str, task_number: int) -> List[str]:
    """Generate pytest or vitest validation command based on file type and task number.

    Generates the appropriate test command for the given file type:
    - Python (.py): pytest with tests/test_task_{NNN}_{name}.py
    - TypeScript (.ts, .tsx): vitest with tests/task-{NNN}-{name}.spec.ts
    - JavaScript (.js, .jsx): vitest with tests/task-{NNN}-{name}.spec.js

    Args:
        file_path: Path to the source file (e.g., "src/auth/service.py").
        task_number: The task number for the manifest (used in test filename).

    Returns:
        List of command components (e.g., ["pytest", "tests/test_task_095_service.py", "-v"]).
    """
    path = Path(file_path)
    stem = path.stem

    # Strip leading underscore for private modules
    if stem.startswith("_"):
        stem = stem[1:]

    # Replace underscores with underscores for Python test names (convention)
    # and with hyphens for TypeScript/JavaScript
    formatted_task = f"{task_number:03d}"

    suffix = path.suffix.lower()

    if suffix == ".py":
        # Python: tests/test_task_XXX_name.py
        test_filename = f"tests/test_task_{formatted_task}_{stem}.py"
        return ["pytest", test_filename, "-v"]

    elif suffix in (".ts", ".tsx"):
        # TypeScript: tests/task-XXX-name.spec.ts
        stem_hyphenated = stem.replace("_", "-")
        test_filename = f"tests/task-{formatted_task}-{stem_hyphenated}.spec.ts"
        return ["vitest", "run", test_filename]

    elif suffix in (".js", ".jsx"):
        # JavaScript: tests/task-XXX-name.spec.js
        stem_hyphenated = stem.replace("_", "-")
        test_filename = f"tests/task-{formatted_task}-{stem_hyphenated}.spec.js"
        return ["vitest", "run", test_filename]

    else:
        # Default to pytest for unknown types
        test_filename = f"tests/test_task_{formatted_task}_{stem}.py"
        return ["pytest", test_filename, "-v"]
