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
_IN_PREFIXED_PROPERTY_ERROR = re.compile(rb"in_[A-Za-z_$][A-Za-z0-9_$]*\??\s*:")


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
    tree_bytes = source_bytes

    if parse_errors:
        parse_bytes = _sanitize_type_query_imports_for_tree_sitter(source_bytes)
        if parse_bytes != source_bytes:
            sanitized_tree = parser.parse(parse_bytes)
            sanitized_errors = collect_parse_errors(sanitized_tree.root_node)
            if len(sanitized_errors) < len(parse_errors):
                tree = sanitized_tree
                parse_errors = sanitized_errors
                tree_bytes = parse_bytes

    if parse_errors:
        parse_bytes = _sanitize_in_prefixed_property_errors(
            tree_bytes,
            tree.root_node,
        )
        if parse_bytes != tree_bytes:
            sanitized_tree = parser.parse(parse_bytes)
            sanitized_errors = collect_parse_errors(sanitized_tree.root_node)
            if len(sanitized_errors) < len(parse_errors):
                tree = sanitized_tree
                parse_errors = sanitized_errors
                tree_bytes = parse_bytes

    if parse_errors and str(file_path).endswith((".tsx", ".jsx")):
        candidate_bytes = tree_bytes
        candidate_tree = tree
        # Every pass consumes at least one eligible ASCII marker. Reparse to
        # expose text contexts hidden by the grammar's earlier error recovery.
        for _ in range(candidate_bytes.count(b"&")):
            repaired_bytes = _sanitize_jsx_text_ampersands(
                candidate_bytes, candidate_tree.root_node
            )
            if repaired_bytes == candidate_bytes:
                break
            candidate_tree = parser.parse(repaired_bytes)
            candidate_errors = collect_parse_errors(candidate_tree.root_node)
            candidate_errors.extend(
                _jsx_tag_mismatch_errors(candidate_tree.root_node, source_bytes)
            )
            candidate_bytes = repaired_bytes
            if len(candidate_errors) < len(parse_errors):
                tree = candidate_tree
                tree_bytes = candidate_bytes
                parse_errors = candidate_errors
            if not candidate_errors:
                break

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


def _sanitize_in_prefixed_property_errors(source_bytes: bytes, root: Any) -> bytes:
    """Mask exact valid property prefixes misparsed by tree-sitter-typescript."""
    output = bytearray(source_bytes)
    changed = False
    stack = [root]
    while stack:
        current = stack.pop()
        if current.type == "ERROR":
            error_bytes = source_bytes[current.start_byte : current.end_byte]
            if _IN_PREFIXED_PROPERTY_ERROR.match(error_bytes):
                output[current.start_byte : current.start_byte + 2] = b"xx"
                changed = True
            continue
        stack.extend(reversed(current.children))
    return bytes(output) if changed else source_bytes


def _sanitize_jsx_text_ampersands(source_bytes: bytes, root: Any) -> bytes:
    """Mask only ampersand tokens recovered in parser-established JSX text."""
    output = bytearray(source_bytes)
    pending = [root]
    while pending:
        node = pending.pop()
        parent = node.parent
        if node.type in ("&", "&&", "&=") and parent is not None:
            previous = node.prev_sibling
            direct_text_error = (
                parent.type == "ERROR"
                and parent.parent is not None
                and parent.parent.type in ("jsx_element", "jsx_fragment")
            )
            recovered_after_text = (
                parent.type == "ERROR"
                and previous is not None
                and previous.type == "jsx_text"
            )
            if direct_text_error or recovered_after_text:
                for position in range(node.start_byte, node.end_byte):
                    if output[position] == ord("&"):
                        output[position] = ord("x")
        pending.extend(node.children)
    return bytes(output)


def _jsx_tag_mismatch_errors(root: Any, source_bytes: bytes) -> list[str]:
    """Do not turn mismatched JSX tags into success during grammar recovery."""
    errors: list[str] = []
    pending = [root]
    while pending:
        node = pending.pop()
        if node.type == "jsx_element":
            opening = node.child_by_field_name("open_tag")
            closing = node.child_by_field_name("close_tag")
            if opening is not None and closing is not None:
                open_name = opening.child_by_field_name("name")
                close_name = closing.child_by_field_name("name")
                names = [
                    (
                        b""
                        if name is None
                        else b"".join(
                            source_bytes[name.start_byte : name.end_byte].split()
                        )
                    )
                    for name in (open_name, close_name)
                ]
                if names[0] != names[1]:
                    errors.append(
                        f"Syntax error near line {closing.start_point[0] + 1}"
                    )
        pending.extend(node.named_children)
    return errors


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
