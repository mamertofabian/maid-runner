"""Narrow JSDoc annotation extraction for JavaScript declarations."""

from __future__ import annotations

import re
from typing import Any, Optional


_JSDOC_RETURN = re.compile(r"@returns?\s*\{([^{}\r\n]+)\}")


def extract_leading_jsdoc_return_type(node: Any, source: bytes) -> Optional[str]:
    """Return a braced return type from JSDoc attached to a declaration node."""
    declaration = node
    parent = getattr(declaration, "parent", None)
    if parent is not None and parent.type == "variable_declarator":
        declaration = parent
        parent = declaration.parent
        if parent is not None and parent.type in {
            "lexical_declaration",
            "variable_declaration",
        }:
            declarators = [
                child
                for child in parent.children
                if child.type == "variable_declarator"
            ]
            if declarators and declaration != declarators[0]:
                return None
            declaration = parent

    parent = getattr(declaration, "parent", None)
    if parent is not None and parent.type == "export_statement":
        declaration = parent

    comment = getattr(declaration, "prev_named_sibling", None)
    if comment is None or comment.type != "comment":
        return None

    text = source[comment.start_byte : comment.end_byte].decode(
        "utf-8", errors="replace"
    )
    if not text.startswith("/**"):
        return None

    gap = source[comment.end_byte : declaration.start_byte]
    normalized_gap = gap.replace(b"\r\n", b"\n")
    if normalized_gap.count(b"\n") > 1 or normalized_gap.strip():
        return None

    match = _JSDOC_RETURN.search(text)
    if match is None:
        return None
    return_type = match.group(1).strip()
    return return_type or None
