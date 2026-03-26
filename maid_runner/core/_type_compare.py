"""Type normalization and comparison for MAID Runner v2.

Ported from validators/_type_normalization.py with a cleaner API.
"""

from __future__ import annotations

from typing import Optional

# PEP 585 equivalences: lowercase builtin -> typing.X
_PEP585_MAP = {
    "list": "List",
    "dict": "Dict",
    "tuple": "Tuple",
    "set": "Set",
    "frozenset": "FrozenSet",
    "type": "Type",
}
_PEP585_REVERSE = {v: k for k, v in _PEP585_MAP.items()}


def normalize_type(type_str: Optional[str]) -> Optional[str]:
    """Normalize a type string for consistent comparison.

    Pipeline:
    1. Strip whitespace
    2. Remove internal spaces
    3. Convert pipe unions (X | Y) -> Union[X, Y]
    4. Convert Optional[X] -> Union[X, None]
    5. Sort Union members alphabetically
    6. Normalize comma spacing inside brackets
    """
    if type_str is None:
        return None

    s = type_str.strip()
    if not s:
        return s

    s = s.replace(" ", "")
    s = _convert_pipe_union(s)
    s = _convert_optional(s)
    s = _sort_union(s)
    s = _normalize_comma_spacing(s)

    return s


def types_match(manifest_type: Optional[str], impl_type: Optional[str]) -> bool:
    """Compare two type annotations with normalization.

    If manifest_type is None (unspecified), any impl_type is acceptable.
    If impl_type is None but manifest_type is specified, it's a mismatch.
    """
    if manifest_type is None:
        return True
    if impl_type is None:
        return False

    norm_manifest = normalize_type(manifest_type)
    norm_impl = normalize_type(impl_type)

    if norm_manifest == norm_impl:
        return True

    # PEP 585 equivalence: try normalizing both to lowercase form
    norm_m_lower = _pep585_normalize(norm_manifest or "")
    norm_i_lower = _pep585_normalize(norm_impl or "")
    return norm_m_lower == norm_i_lower


def _pep585_normalize(s: str) -> str:
    """Normalize PEP 585 types to a canonical form (lowercase)."""
    for upper, lower in _PEP585_REVERSE.items():
        if s.startswith(upper + "["):
            s = lower + s[len(upper) :]
    return s


def _convert_pipe_union(s: str) -> str:
    if "|" not in s:
        return s
    parts = _split_by_delimiter(s, "|")
    if len(parts) > 1:
        return "Union[" + ",".join(parts) + "]"
    return s


def _convert_optional(s: str) -> str:
    if s.startswith("Optional[") and s.endswith("]"):
        inner = s[len("Optional[") : -1]
        return f"Union[{inner},None]"
    return s


def _sort_union(s: str) -> str:
    if s.startswith("Union[") and s.endswith("]"):
        inner = s[len("Union[") : -1]
        members = _split_by_delimiter(inner, ",")
        members.sort()
        return "Union[" + ",".join(members) + "]"
    return s


def _normalize_comma_spacing(s: str) -> str:
    if "," not in s:
        return s

    result: list[str] = []
    depth = 0
    i = 0
    while i < len(s):
        c = s[i]
        if c == "[":
            depth += 1
            result.append(c)
        elif c == "]":
            depth -= 1
            result.append(c)
        elif c == "," and depth > 0:
            result.append(", ")
            # Skip trailing spaces
            i += 1
            while i < len(s) and s[i] == " ":
                i += 1
            continue
        else:
            result.append(c)
        i += 1

    return "".join(result)


def _split_by_delimiter(text: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    current = ""
    depth = 0
    for c in text:
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
        elif c == delimiter and depth == 0:
            parts.append(current.strip())
            current = ""
            continue
        current += c
    if current:
        parts.append(current.strip())
    return parts
