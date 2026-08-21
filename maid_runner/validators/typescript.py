"""TypeScript/JavaScript validator for MAID Runner v2.

Uses tree-sitter for accurate AST parsing. Requires tree-sitter-typescript.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Optional, Union

from maid_runner.core._js_ts_imports import collect_import_modules
from maid_runner.core.ts_module_paths import (
    resolve_ts_import,
    resolve_ts_reexport,
    ts_file_to_module_path,
)
from maid_runner.validators.base import (
    BaseValidator,
    CollectionResult,
    ComplexityResult,
    DependencyCollectionResult,
    _braced_complexity,
    _logical_line_count,
)
from maid_runner.validators._typescript_behavioral import (
    collect_behavioral_artifacts as collect_ts_behavioral_artifacts,
    collect_test_function_bodies as collect_ts_test_function_bodies,
)
from maid_runner.validators._typescript_implementation import (
    collect_implementation_artifacts as collect_ts_implementation_artifacts,
)
from maid_runner.validators._typescript_parse import parse_typescript_source

try:
    from tree_sitter import Language, Node, Parser
    import tree_sitter_typescript as ts_ts

    _HAS_TREE_SITTER = True
except ImportError:
    _HAS_TREE_SITTER = False


_TYPE_FORMATTING_TOKENS = frozenset(
    {
        "{",
        "}",
        "(",
        ")",
        "[",
        "]",
        "<",
        ">",
        ",",
        ";",
        ":",
        "=",
        "|",
        "&",
        "=>",
        ".",
        "'",
        '"',
        "`",
    }
)
_TYPE_FINGERPRINT_CACHE_SIZE = 256
_TYPE_FINGERPRINT_MAX_BYTES = 65_536
_TYPE_FINGERPRINT_MAX_DEPTH = 256
_TYPE_FINGERPRINT_MAX_NODES = 4_096


def _typescript_type_fingerprint(
    node: Node,
    source: bytes,
) -> tuple[object, ...]:
    node = _unwrap_parenthesized_type(node)
    if node.type == "string":
        text = source[node.start_byte : node.end_byte].decode("utf-8")
        value = _decode_typescript_string_literal(text)
        if value is not None:
            return ("string", value)
    if node.type in {"union_type", "intersection_type"}:
        members = _flatten_type_members(node, node.type)
        fingerprints = [
            _typescript_type_fingerprint(member, source) for member in members
        ]
        return (node.type, tuple(sorted(fingerprints, key=repr)))

    children: list[tuple[object, ...]] = []
    for child in node.children:
        if child.type == "comment":
            continue
        if child.is_named:
            children.append(_typescript_type_fingerprint(child, source))
            continue

        token = source[child.start_byte : child.end_byte].decode("utf-8")
        if token not in _TYPE_FORMATTING_TOKENS:
            children.append(("token", token))

    if node.child_count:
        return (node.type, tuple(children))

    text = source[node.start_byte : node.end_byte].decode("utf-8")
    return (node.type, text)


def _flatten_type_members(node: Node, node_type: str) -> list[Node]:
    members: list[Node] = []
    for child in node.named_children:
        if child.type == "comment":
            continue
        child = _unwrap_parenthesized_type(child)
        if child.type == node_type:
            members.extend(_flatten_type_members(child, node_type))
        else:
            members.append(child)
    return members


def _unwrap_parenthesized_type(node: Node) -> Node:
    while node.type == "parenthesized_type":
        semantic_children = [
            child for child in node.named_children if child.type != "comment"
        ]
        if len(semantic_children) != 1:
            break
        node = semantic_children[0]
    return node


def _type_tree_within_limits(node: Node) -> bool:
    pending = [(node, 1)]
    visited = 0
    while pending:
        current, depth = pending.pop()
        visited += 1
        if depth > _TYPE_FINGERPRINT_MAX_DEPTH:
            return False
        if visited > _TYPE_FINGERPRINT_MAX_NODES:
            return False
        pending.extend((child, depth + 1) for child in current.children)
    return True


def _type_tree_strings_are_valid(node: Node, source: bytes) -> bool:
    pending = [node]
    while pending:
        current = pending.pop()
        if current.type == "string":
            text = source[current.start_byte : current.end_byte].decode("utf-8")
            if _decode_typescript_string_literal(text) is None:
                return False
        pending.extend(current.named_children)
    return True


def _decode_typescript_string_literal(text: str) -> str | None:
    if len(text) < 2 or text[0] not in {"'", '"'} or text[-1] != text[0]:
        return None

    escapes = {
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "v": "\v",
        "0": "\0",
    }
    value: list[str] = []
    index = 1
    end = len(text) - 1
    while index < end:
        char = text[index]
        if char != "\\":
            value.append(char)
            index += 1
            continue

        index += 1
        if index >= end:
            return None
        escaped = text[index]
        index += 1
        if escaped in {"\n", "\r", "\u2028", "\u2029"}:
            if escaped == "\r" and index < end and text[index] == "\n":
                index += 1
            continue
        if escaped in "0123456789":
            if escaped != "0" or (index < end and text[index] in "0123456789"):
                return None
        if escaped in escapes:
            value.append(escapes[escaped])
            continue
        if escaped == "x":
            width = 2
        elif escaped == "u" and index < end and text[index] == "{":
            close = text.find("}", index + 1, end)
            if close < 0:
                return None
            try:
                value.append(chr(int(text[index + 1 : close], 16)))
            except (ValueError, OverflowError):
                return None
            index = close + 1
            continue
        elif escaped == "u":
            width = 4
        else:
            value.append(escaped)
            continue

        digits = text[index : index + width]
        if len(digits) != width:
            return None
        try:
            value.append(chr(int(digits, 16)))
        except ValueError:
            return None
        index += width

    normalized: list[str] = []
    index = 0
    while index < len(value):
        high = ord(value[index])
        if 0xD800 <= high <= 0xDBFF and index + 1 < len(value):
            low = ord(value[index + 1])
            if 0xDC00 <= low <= 0xDFFF:
                normalized.append(chr(0x10000 + ((high - 0xD800) << 10) + low - 0xDC00))
                index += 2
                continue
        normalized.append(value[index])
        index += 1
    return "".join(normalized)


class TypeScriptValidator(BaseValidator):
    def __init__(self) -> None:
        if not _HAS_TREE_SITTER:
            raise ImportError(
                "tree-sitter-typescript is required for TypeScript validation. "
                "Install with: pip install tree-sitter tree-sitter-typescript"
            )
        self._ts_lang = Language(ts_ts.language_typescript())
        self._tsx_lang = Language(ts_ts.language_tsx())
        self._ts_parser = Parser(self._ts_lang)
        self._tsx_parser = Parser(self._tsx_lang)
        self._type_fingerprints: dict[str, tuple[object, ...] | None] = {}

    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts")

    def collect_implementation_artifacts(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> CollectionResult:
        def _collect_implementation(session):
            artifacts = collect_ts_implementation_artifacts(
                session.tree.root_node,
                session.source_bytes,
                allow_jsdoc_returns=Path(file_path).suffix.lower() in {".js", ".jsx"},
            )
            if session.module_id:
                artifacts = [
                    (
                        replace(a, module_path=session.module_id)
                        if a.module_path is None
                        else a
                    )
                    for a in artifacts
                ]
            return artifacts

        return self._collect_with_parse_guard(
            language="typescript",
            file_path=file_path,
            parse_fn=lambda: parse_typescript_source(
                source,
                file_path,
                self._ts_parser,
                self._tsx_parser,
            ),
            collect_fn=_collect_implementation,
            errors_from_session=lambda session: session.parse_errors,
        )

    def types_match(
        self,
        manifest_type: str | None,
        implementation_type: str | None,
    ) -> bool:
        if manifest_type is None:
            return True
        if implementation_type is None:
            return False
        if manifest_type == implementation_type:
            return True

        try:
            baseline_match = super().types_match(manifest_type, implementation_type)
        except Exception:
            baseline_match = False
        manifest_fingerprint = self._type_fingerprint(manifest_type)
        implementation_fingerprint = self._type_fingerprint(implementation_type)
        if manifest_fingerprint is None or implementation_fingerprint is None:
            return baseline_match
        return manifest_fingerprint == implementation_fingerprint

    def _type_fingerprint(self, fragment: str) -> tuple[object, ...] | None:
        if fragment in self._type_fingerprints:
            return self._type_fingerprints[fragment]
        if len(fragment) > _TYPE_FINGERPRINT_MAX_BYTES:
            return None

        try:
            fragment_bytes = fragment.encode("utf-8")
        except UnicodeEncodeError:
            return None
        if len(fragment_bytes) > _TYPE_FINGERPRINT_MAX_BYTES:
            return None
        source = b"type __MaidType = " + fragment_bytes + b"\n;"
        fingerprint = None
        try:
            root = self._ts_parser.parse(source).root_node
            declarations = root.named_children
            if (
                not root.has_error
                and len(declarations) == 1
                and declarations[0].type == "type_alias_declaration"
                and declarations[0].start_byte == 0
                and declarations[0].end_byte == len(source)
            ):
                target = declarations[0].child_by_field_name("value")
                if (
                    target is not None
                    and _type_tree_within_limits(root)
                    and _type_tree_strings_are_valid(target, source)
                ):
                    fingerprint = _typescript_type_fingerprint(target, source)
        except Exception:
            fingerprint = None

        return self._store_type_fingerprint(fragment, fingerprint)

    def _store_type_fingerprint(
        self,
        fragment: str,
        fingerprint: tuple[object, ...] | None,
    ) -> tuple[object, ...] | None:
        if fingerprint is None:
            return None
        if len(self._type_fingerprints) >= _TYPE_FINGERPRINT_CACHE_SIZE:
            self._type_fingerprints.pop(next(iter(self._type_fingerprints)))
        self._type_fingerprints[fragment] = fingerprint
        return fingerprint

    def collect_behavioral_artifacts(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> CollectionResult:
        return self._collect_with_parse_guard(
            language="typescript",
            file_path=file_path,
            parse_fn=lambda: parse_typescript_source(
                source,
                file_path,
                self._ts_parser,
                self._tsx_parser,
            ),
            collect_fn=lambda session: collect_ts_behavioral_artifacts(
                session.tree.root_node,
                session.source_bytes,
                file_path,
            ),
            errors_from_session=lambda session: session.parse_errors,
        )

    def collect_dependencies(
        self,
        source: str,
        file_path: Union[str, Path],
        project_root: Path,
    ) -> DependencyCollectionResult:
        importer_module = ts_file_to_module_path(file_path, project_root)
        try:
            modules = {
                resolve_ts_import(specifier, importer_module, project_root)
                for specifier in collect_import_modules(source, str(file_path))
            }
        except Exception as exc:
            return DependencyCollectionResult(errors=(str(exc),))
        return DependencyCollectionResult(modules=tuple(sorted(modules)))

    def collect_complexity(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> ComplexityResult:
        artifacts = self.collect_implementation_artifacts(source, file_path)
        if artifacts.errors:
            return ComplexityResult(errors=tuple(artifacts.errors))
        decisions, largest = _braced_complexity(source)
        return ComplexityResult(
            logical_lines=_logical_line_count(source),
            decision_points=decisions,
            largest_definition_lines=largest,
            public_artifacts=sum(
                1 for artifact in artifacts.artifacts if not artifact.is_private
            ),
        )

    def module_path(
        self,
        file_path: Union[str, Path],
        project_root: Path,
    ) -> Optional[str]:
        return ts_file_to_module_path(file_path, project_root) or None

    def resolve_reexport(
        self,
        module: str,
        name: str,
        project_root: Path,
    ) -> Optional[tuple[str, str]]:
        return resolve_ts_reexport(module, name, project_root)

    def get_test_function_bodies(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> dict[str, str]:
        session = parse_typescript_source(
            source, file_path, self._ts_parser, self._tsx_parser
        )
        if session.parse_errors:
            return {}

        return collect_ts_test_function_bodies(
            session.tree.root_node,
            session.source_bytes,
        )
