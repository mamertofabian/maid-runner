"""Private module for type string normalization and comparison."""

from typing import Optional, Any

from maid_runner.validators._type_annotation import (
    _OPTIONAL_PREFIX,
    _UNION_PREFIX,
    _BRACKET_OPEN,
    _BRACKET_CLOSE,
)

# Type normalization constants
_COMMA = ","
_PIPE = "|"
_SPACE = " "
_NONE_TYPE = "None"


def _normalize_type_input(type_value: Any) -> Optional[str]:
    """Normalize a type input value to string or None.

    Args:
        type_value: Any value that represents a type

    Returns:
        String representation or None
    """
    if type_value is None:
        return None
    if isinstance(type_value, str):
        return type_value
    return str(type_value)


def normalize_type_string(type_str: str) -> Optional[str]:
    """
    Normalize a type string for consistent comparison.

    Performs the following normalizations:
    - Removes extra whitespace
    - Converts Optional[X] to Union[X, None]
    - Converts modern union syntax (X | Y) to Union[X, Y]
    - Sorts Union members alphabetically
    - Ensures consistent comma spacing in generic types

    Args:
        type_str: Type string to normalize

    Returns:
        Normalized type string, or None if input is None
    """
    if type_str is None:
        return None

    # Clean and prepare the string
    type_str = type_str.strip()
    if not type_str:
        return type_str

    # Apply normalization pipeline
    normalized = type_str.replace(_SPACE, "")  # Remove all spaces first
    normalized = _normalize_modern_union_syntax(normalized)
    normalized = _normalize_optional_type(normalized)
    normalized = _normalize_union_type(normalized)
    normalized = _normalize_comma_spacing(normalized)

    return normalized


def _normalize_modern_union_syntax(type_str: str) -> str:
    """Convert modern union syntax (X | Y) to Union[X, Y].

    Args:
        type_str: Type string that may contain pipe union operators

    Returns:
        Type string with Union[...] syntax instead of pipes
    """
    if _PIPE not in type_str:
        return type_str

    # Split by pipe at top level only (respecting bracket nesting)
    parts = _split_by_delimiter(type_str, _PIPE)

    # Convert to Union syntax if multiple parts found
    if len(parts) > 1:
        return f"{_UNION_PREFIX}{_COMMA.join(parts)}{_BRACKET_CLOSE}"

    return type_str


def _normalize_optional_type(type_str: str) -> str:
    """Convert Optional[X] to Union[X, None].

    Args:
        type_str: Type string that may contain Optional[...]

    Returns:
        Type string with Union[X, None] instead of Optional[X]
    """
    if not _is_optional_type(type_str):
        return type_str

    inner_type = _extract_bracketed_content(type_str, _OPTIONAL_PREFIX)
    return f"{_UNION_PREFIX}{inner_type},{_NONE_TYPE}{_BRACKET_CLOSE}"


def _is_optional_type(type_str: str) -> bool:
    """Check if a type string represents Optional[...] type."""
    return type_str.startswith(_OPTIONAL_PREFIX) and type_str.endswith(_BRACKET_CLOSE)


def _extract_bracketed_content(type_str: str, prefix: str) -> str:
    """Extract content between prefix and closing bracket.

    Args:
        type_str: Full type string
        prefix: Prefix to remove (e.g., 'Optional[', 'Union[')

    Returns:
        Content between prefix and closing bracket
    """
    return type_str[len(prefix) : -1]


def _normalize_union_type(type_str: str) -> str:
    """Sort Union type members alphabetically.

    Args:
        type_str: Type string that may contain Union[...]

    Returns:
        Type string with Union members sorted alphabetically
    """
    if not _is_union_type(type_str):
        return type_str

    inner = _extract_bracketed_content(type_str, _UNION_PREFIX)
    members = _split_type_arguments(inner)
    members.sort()
    return f"{_UNION_PREFIX}{_COMMA.join(members)}{_BRACKET_CLOSE}"


def _is_union_type(type_str: str) -> bool:
    """Check if a type string represents Union[...] type."""
    return type_str.startswith(_UNION_PREFIX) and type_str.endswith(_BRACKET_CLOSE)


def _split_type_arguments(inner: str) -> list:
    """Split type arguments by comma, respecting nested brackets.

    Args:
        inner: String containing comma-separated type arguments

    Returns:
        List of individual type argument strings
    """
    return _split_by_delimiter(inner, _COMMA)


def _split_by_delimiter(text: str, delimiter: str) -> list:
    """Split text by delimiter at top level, respecting bracket nesting.

    This utility function handles splitting strings that contain nested
    brackets, ensuring we only split at the top level.

    Args:
        text: String to split
        delimiter: Character(s) to split by

    Returns:
        List of split parts with whitespace trimmed
    """
    if not text:
        return []

    parts = []
    current = ""
    bracket_depth = 0

    for char in text:
        if char == _BRACKET_OPEN:
            bracket_depth += 1
        elif char == _BRACKET_CLOSE:
            bracket_depth -= 1
        elif char == delimiter and bracket_depth == 0:
            parts.append(current.strip())
            current = ""
            continue

        current += char

    if current:
        parts.append(current.strip())

    return parts


def _normalize_comma_spacing(type_str: str) -> str:
    """Normalize spacing after commas in generic types.

    Ensures consistent formatting like Dict[str, int] instead of
    Dict[str,int] or Dict[str,  int].

    Args:
        type_str: Type string to normalize

    Returns:
        Type string with normalized comma spacing
    """
    if _COMMA not in type_str:
        return type_str

    result = []
    bracket_depth = 0
    i = 0

    while i < len(type_str):
        char = type_str[i]

        if char == _BRACKET_OPEN:
            bracket_depth += 1
            result.append(char)
        elif char == _BRACKET_CLOSE:
            bracket_depth -= 1
            result.append(char)
        elif char == _COMMA and bracket_depth > 0:
            # Add comma with single space
            result.append(_COMMA)
            result.append(_SPACE)
            # Skip any following spaces
            i = _skip_spaces(type_str, i + 1) - 1
        else:
            result.append(char)

        i += 1

    return "".join(result)


def _skip_spaces(text: str, start_idx: int) -> int:
    """Skip whitespace characters starting from given index.

    Args:
        text: String to process
        start_idx: Starting index

    Returns:
        Index of first non-space character or end of string
    """
    idx = start_idx
    while idx < len(text) and text[idx] == _SPACE:
        idx += 1
    return idx
