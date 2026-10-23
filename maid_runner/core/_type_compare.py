"""Type normalization and comparison for MAID Runner v2.

Ported from validators/_type_normalization.py with a cleaner API.
"""

from __future__ import annotations

import ast
import io
import tokenize
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
    0. Canonicalize supported nested type syntax while preserving value positions
    1. Strip whitespace
    2. Remove internal spaces
    3. Convert pipe unions (X | Y) -> Union[X, Y]
    4. Convert Optional[X] -> Union[X, None]
    5. Flatten and sort Union members alphabetically
    6. Normalize comma spacing inside brackets
    """
    if type_str is None:
        return None

    s = type_str.strip()
    if not s:
        return s

    s = _normalize_annotation_positions(s)
    s = _normalize_quoted_values(s)
    s = s.replace(" ", "")
    s = _convert_pipe_union(s)
    s = _convert_optional(s)
    s = _flatten_and_sort_union(s)
    s = _normalize_comma_spacing(s)

    return s


def _normalize_annotation_positions(type_str: str) -> str:
    """Canonicalize supported type syntax; retain legacy parsing for other languages."""
    try:
        tree = ast.parse(type_str, mode="eval")
        return _render_annotation_type(tree.body)
    except (SyntaxError, ValueError, RecursionError):
        return type_str


def _annotation_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_annotation_name(node.value)}.{node.attr}"
    raise ValueError("Unsupported annotation name")


def _annotation_arguments(node: ast.Subscript) -> list[ast.AST]:
    return list(node.slice.elts) if isinstance(node.slice, ast.Tuple) else [node.slice]


def _union_annotation_members(node: ast.AST) -> list[str]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _union_annotation_members(node.left) + _union_annotation_members(
            node.right
        )
    if isinstance(node, ast.Subscript):
        name = _annotation_name(node.value)
        arguments = _annotation_arguments(node)
        if name == "Union":
            return [
                member
                for argument in arguments
                for member in _union_annotation_members(argument)
            ]
        if name == "Optional" and len(arguments) == 1:
            return _union_annotation_members(arguments[0]) + ["None"]
    return [_render_annotation_type(node)]


def _render_union_annotation(nodes: list[ast.AST]) -> str:
    members = [member for node in nodes for member in _union_annotation_members(node)]
    return f"Union[{', '.join(sorted(members))}]"


def _render_annotation_type(node: ast.AST) -> str:
    if isinstance(node, (ast.Name, ast.Attribute)):
        return _annotation_name(node)
    if isinstance(node, ast.Constant):
        # Strings remain values: the shared matcher also serves literal types
        # in other languages. Do not unwrap them as Python forward references.
        return ast.unparse(node)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _render_union_annotation([node.left, node.right])
    if isinstance(node, ast.Subscript):
        base = _annotation_name(node.value)
        arguments = _annotation_arguments(node)
        if base == "Union":
            return _render_union_annotation(arguments)
        if base == "Optional" and len(arguments) == 1:
            return _render_union_annotation([arguments[0], ast.Constant(None)])
        leaf = base.rsplit(".", 1)[-1]
        if leaf == "Literal":
            rendered = [ast.unparse(argument) for argument in arguments]
        elif leaf == "Annotated":
            if not arguments:
                raise ValueError("Annotated requires a type argument")
            rendered = [_render_annotation_type(arguments[0])]
            rendered.extend(ast.unparse(argument) for argument in arguments[1:])
        else:
            rendered = [_render_annotation_type(argument) for argument in arguments]
        return f"{base}[{', '.join(rendered)}]"
    if isinstance(node, (ast.List, ast.Tuple)):
        rendered = ", ".join(_render_annotation_type(element) for element in node.elts)
        if isinstance(node, ast.List):
            return f"[{rendered}]"
        suffix = "," if len(node.elts) == 1 else ""
        return f"({rendered}{suffix})"
    if isinstance(node, ast.Starred):
        return f"*{_render_annotation_type(node.value)}"
    raise ValueError("Unsupported annotation expression")


def _normalize_quoted_values(type_str: str) -> str:
    """Replace quoted values with stable semantic tokens before comparison."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(type_str).readline))
    except (IndentationError, tokenize.TokenError):
        return type_str

    normalized: list[tokenize.TokenInfo] = []
    for token in tokens:
        if token.type == tokenize.STRING:
            try:
                value = ast.literal_eval(token.string)
            except (SyntaxError, ValueError):
                pass
            else:
                semantic_value = repr(value).encode("utf-8").hex()
                token = tokenize.TokenInfo(
                    token.type,
                    f"\x00maid_quoted_{semantic_value}\x00",
                    token.start,
                    token.end,
                    token.line,
                )
        normalized.append(token)
    return tokenize.untokenize(normalized)


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


def _flatten_and_sort_union(s: str) -> str:
    if not (s.startswith("Union[") and s.endswith("]")):
        return s

    members: list[str] = []

    def collect(member: str) -> None:
        member = member.strip()
        if member.startswith("Union[") and member.endswith("]"):
            for nested in _split_by_delimiter(member[len("Union[") : -1], ","):
                collect(nested)
            return
        if member:
            members.append(member)

    for part in _split_by_delimiter(s[len("Union[") : -1], ","):
        collect(part)

    members.sort()
    return "Union[" + ",".join(members) + "]"


def _sort_union(s: str) -> str:
    return _flatten_and_sort_union(s)


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
