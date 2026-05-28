"""Private TypeScript parse-session helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Union

from maid_runner.core.ts_module_paths import ts_file_to_module_path

if TYPE_CHECKING:
    from tree_sitter import Parser, Tree


_TYPEOF_IMPORT_TYPE_ARGUMENT = re.compile(
    rb"""<\s*typeof\s+import\s*\(\s*(["'])(?:\\.|(?!\1).)*\1\s*\)\s*>""",
    re.DOTALL,
)
_IMPORT_TYPE_ARGUMENT = re.compile(
    rb"""<\s*import\s*\(\s*(["'])(?:\\.|(?!\1).)*\1\s*\)"""
    rb"""(?:\s*\.\s*[A-Za-z_$][A-Za-z0-9_$]*)+\s*>""",
    re.DOTALL,
)


class TypeScriptParseSession:
    __slots__ = ("source_bytes", "tree", "parse_errors", "module_id")

    def __init__(
        self,
        source_bytes: bytes,
        tree: "Tree",
        parse_errors: list[str],
        module_id: str | None,
    ) -> None:
        self.source_bytes = source_bytes
        self.tree = tree
        self.parse_errors = parse_errors
        self.module_id = module_id


def parse_typescript_source(
    source: str,
    file_path: Union[str, Path],
    ts_parser: "Parser",
    tsx_parser: "Parser",
) -> TypeScriptParseSession:
    source_bytes = source.encode("utf-8")
    parser = tsx_parser if str(file_path).endswith((".tsx", ".jsx")) else ts_parser
    tree = parser.parse(source_bytes)
    parse_errors = collect_parse_errors(tree.root_node)

    if parse_errors:
        parse_bytes = _sanitize_type_query_imports_for_tree_sitter(source_bytes)
        if parse_bytes != source_bytes:
            sanitized_tree = parser.parse(parse_bytes)
            sanitized_errors = collect_parse_errors(sanitized_tree.root_node)
            if len(sanitized_errors) < len(parse_errors):
                tree = sanitized_tree
                parse_errors = sanitized_errors

    return TypeScriptParseSession(
        source_bytes=source_bytes,
        tree=tree,
        parse_errors=parse_errors,
        module_id=ts_file_to_module_path(file_path, Path(".")) or None,
    )


def _sanitize_type_query_imports_for_tree_sitter(source_bytes: bytes) -> bytes:
    """Normalize valid TS type queries that tree-sitter-typescript rejects.

    Vitest mocks commonly use ``importOriginal<typeof import("module")>()``.
    The grammar version used by tree-sitter-typescript currently reports that
    valid type-query import as an ERROR node. Frontend service modules also use
    valid ``fetchJson<import("module").Type>()`` generic arguments. Replace only
    those generic type arguments with equal-length whitespace so parser byte
    offsets still map back to the original source used by collectors.
    """

    def placeholder(match: re.Match[bytes]) -> bytes:
        text = match.group(0)
        output = bytearray()
        for byte in text:
            if byte in (ord("\n"), ord("\r")):
                output.append(byte)
            else:
                output.append(ord(" "))
        return bytes(output)

    sanitized = _TYPEOF_IMPORT_TYPE_ARGUMENT.sub(placeholder, source_bytes)
    return _IMPORT_TYPE_ARGUMENT.sub(placeholder, sanitized)


def collect_parse_errors(node: Any) -> list[str]:
    errors: list[str] = []
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type == "ERROR":
            line = current.start_point[0] + 1
            errors.append(f"Syntax error near line {line}")
            continue
        if getattr(current, "is_missing", False):
            line = current.start_point[0] + 1
            errors.append(f"Missing syntax node near line {line}")
            continue
        stack.extend(reversed(current.children))

    if getattr(node, "has_error", False) and not errors:
        errors.append("Syntax error")

    return errors
