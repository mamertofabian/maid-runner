"""TypeScript/JavaScript validator for MAID Runner v2.

Uses tree-sitter for accurate AST parsing. Requires tree-sitter-typescript.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Optional, Union

from maid_runner.core.ts_module_paths import (
    resolve_ts_import,
    resolve_ts_reexport,
    ts_file_to_module_path,
)
from maid_runner.core.types import ArtifactKind, ArgSpec
from maid_runner.validators.base import BaseValidator, CollectionResult, FoundArtifact

try:
    from tree_sitter import Language, Parser
    import tree_sitter_typescript as ts_ts

    _HAS_TREE_SITTER = True
except ImportError:
    _HAS_TREE_SITTER = False


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

    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts")

    def collect_implementation_artifacts(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> CollectionResult:
        source_bytes = source.encode("utf-8")
        parser = (
            self._tsx_parser
            if str(file_path).endswith((".tsx", ".jsx"))
            else self._ts_parser
        )
        tree = parser.parse(source_bytes)
        parse_errors = _collect_parse_errors(tree.root_node)
        if parse_errors:
            return CollectionResult(
                artifacts=[],
                language="typescript",
                file_path=str(file_path),
                errors=parse_errors,
            )

        artifacts: list[FoundArtifact] = []
        _collect_impl(tree.root_node, source_bytes, artifacts, current_class=None)

        module_id = ts_file_to_module_path(file_path, Path(".")) or None
        if module_id:
            artifacts = [
                replace(a, module_path=module_id) if a.module_path is None else a
                for a in artifacts
            ]

        return CollectionResult(
            artifacts=artifacts,
            language="typescript",
            file_path=str(file_path),
        )

    def collect_behavioral_artifacts(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> CollectionResult:
        source_bytes = source.encode("utf-8")
        parser = (
            self._tsx_parser
            if str(file_path).endswith((".tsx", ".jsx"))
            else self._ts_parser
        )
        tree = parser.parse(source_bytes)
        parse_errors = _collect_parse_errors(tree.root_node)
        if parse_errors:
            return CollectionResult(
                artifacts=[],
                language="typescript",
                file_path=str(file_path),
                errors=parse_errors,
            )

        artifacts: list[FoundArtifact] = []
        seen: set[str] = set()
        project_root = _ts_project_root_for(file_path)
        importer_module = ts_file_to_module_path(file_path, project_root) or ""
        import_map, namespace_imports = _scan_imports(
            tree.root_node,
            source_bytes,
            importer_module,
            project_root,
            artifacts,
            seen,
        )
        _collect_refs(
            tree.root_node,
            source_bytes,
            artifacts,
            seen,
            import_map=import_map,
            namespace_imports=namespace_imports,
        )

        return CollectionResult(
            artifacts=artifacts,
            language="typescript",
            file_path=str(file_path),
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
        source_bytes = source.encode("utf-8")
        parser = (
            self._tsx_parser
            if str(file_path).endswith((".tsx", ".jsx"))
            else self._ts_parser
        )
        tree = parser.parse(source_bytes)
        if _collect_parse_errors(tree.root_node):
            return {}

        bodies: dict[str, str] = {}
        _collect_test_bodies(tree.root_node, source_bytes, bodies)
        return bodies


def _text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8")


def _collect_parse_errors(node) -> list[str]:
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


def _is_stub_body_ts(node, source: bytes) -> bool:
    """Check if a function body is a stub (no real implementation).

    Works with tree-sitter AST nodes. Checks statement_block children.
    """
    # Find the statement_block (function body)
    body = None
    for child in node.children:
        if child.type == "statement_block":
            body = child
            break

    if body is None:
        # Arrow function with expression body (e.g., () => null)
        for child in node.children:
            if child.type in ("null", "undefined"):
                return True
            if child.type == "number" and _text(child, source) in ("0", "0.0"):
                return True
            if child.type in ("string", "template_string"):
                txt = _text(child, source)
                if txt in ('""', "''", "``"):
                    return True
            if child.type == "false":
                return True
            if child.type == "object" and not any(
                c.type == "pair" for c in child.children
            ):
                return True
            if child.type == "array" and not any(
                c.type not in ("[", "]", ",") for c in child.children
            ):
                return True
        return False

    # Filter out { and } tokens
    statements = [c for c in body.children if c.type not in ("{", "}", "comment")]

    if not statements:
        return True  # empty body {}

    if len(statements) > 1:
        return False  # multiple statements = likely real code

    stmt = statements[0]

    # throw new Error("Not implemented") / throw new Error("TODO")
    if stmt.type == "throw_statement":
        return True

    # return <literal>
    if stmt.type == "return_statement":
        # return; (no value)
        children = [c for c in stmt.children if c.type not in ("return", ";")]
        if not children:
            return True
        if len(children) == 1:
            val = children[0]
            if val.type in ("null", "undefined", "false", "true"):
                return True
            if val.type == "number":
                return True
            if val.type == "string":
                return True
            if val.type == "template_string":
                # Only stub if no template substitutions (e.g., `Hello, ${name}!` is real)
                has_substitution = any(
                    c.type == "template_substitution" for c in val.children
                )
                if not has_substitution:
                    return True
            if val.type == "object" and not any(c.type == "pair" for c in val.children):
                return True
            if val.type == "array" and not any(
                c.type not in ("[", "]", ",") for c in val.children
            ):
                return True

    # expression_statement with just a string literal (like a comment)
    if stmt.type == "expression_statement":
        children = [c for c in stmt.children if c.type != ";"]
        if len(children) == 1 and children[0].type in ("string", "template_string"):
            return True

    return False


def _collect_impl(
    node, source: bytes, artifacts: list[FoundArtifact], current_class: Optional[str]
) -> None:
    ntype = node.type

    if ntype in ("class_declaration", "abstract_class_declaration"):
        name = _child_text(node, "type_identifier", source) or _child_text(
            node, "identifier", source
        )
        if name:
            bases = _extract_bases(node, source)
            artifacts.append(
                FoundArtifact(
                    kind=ArtifactKind.CLASS,
                    name=name,
                    bases=bases,
                    line=node.start_point[0] + 1,
                )
            )
            # Visit class body
            body = _child_by_type(node, "class_body")
            if body:
                for child in body.children:
                    _collect_impl(child, source, artifacts, current_class=name)
            return

    if ntype == "interface_declaration":
        name = _child_text(node, "type_identifier", source) or _child_text(
            node, "identifier", source
        )
        if name:
            bases = _extract_interface_bases(node, source)
            artifacts.append(
                FoundArtifact(
                    kind=ArtifactKind.INTERFACE,
                    name=name,
                    bases=bases,
                    line=node.start_point[0] + 1,
                )
            )
            body = _child_by_type(node, "interface_body") or _child_by_type(
                node, "object_type"
            )
            if body:
                for child in body.children:
                    if child.type == "property_signature":
                        prop_name = _child_text(child, "property_identifier", source)
                        if prop_name:
                            type_ann = None
                            for tc in child.children:
                                if tc.type == "type_annotation":
                                    type_ann = _extract_type_text(tc, source)
                            artifacts.append(
                                FoundArtifact(
                                    kind=ArtifactKind.ATTRIBUTE,
                                    name=prop_name,
                                    of=name,
                                    type_annotation=type_ann,
                                    line=child.start_point[0] + 1,
                                )
                            )
                    elif child.type == "method_signature":
                        method_name = _child_text(child, "property_identifier", source)
                        if method_name:
                            args, returns = _extract_func_signature(child, source)
                            artifacts.append(
                                FoundArtifact(
                                    kind=ArtifactKind.METHOD,
                                    name=method_name,
                                    of=name,
                                    args=args,
                                    returns=returns,
                                    line=child.start_point[0] + 1,
                                )
                            )
        return

    if ntype == "type_alias_declaration":
        name = _child_text(node, "type_identifier", source) or _child_text(
            node, "identifier", source
        )
        if name:
            artifacts.append(
                FoundArtifact(
                    kind=ArtifactKind.TYPE,
                    name=name,
                    line=node.start_point[0] + 1,
                )
            )
        return

    if ntype == "enum_declaration":
        name = _child_text(node, "identifier", source)
        if name:
            artifacts.append(
                FoundArtifact(
                    kind=ArtifactKind.ENUM,
                    name=name,
                    line=node.start_point[0] + 1,
                )
            )
        return

    if ntype == "internal_module":
        name = _child_text(node, "identifier", source) or _child_text(
            node, "type_identifier", source
        )
        if name:
            artifacts.append(
                FoundArtifact(
                    kind=ArtifactKind.NAMESPACE,
                    name=name,
                    line=node.start_point[0] + 1,
                )
            )
        return

    if ntype in ("function_declaration", "generator_function_declaration"):
        name = _child_text(node, "identifier", source)
        if name:
            args, returns = _extract_func_signature(node, source)
            is_async = any(c.type == "async" for c in node.children)
            artifacts.append(
                FoundArtifact(
                    kind=ArtifactKind.FUNCTION,
                    name=name,
                    args=args,
                    returns=returns,
                    is_async=is_async,
                    is_stub=_is_stub_body_ts(node, source),
                    line=node.start_point[0] + 1,
                )
            )
        return

    if ntype == "abstract_method_signature" and current_class:
        name_node = _child_by_type(node, "property_identifier")
        if name_node:
            args, returns = _extract_func_signature(node, source)
            artifacts.append(
                FoundArtifact(
                    kind=ArtifactKind.METHOD,
                    name=_text(name_node, source),
                    of=current_class,
                    args=args,
                    returns=returns,
                    line=node.start_point[0] + 1,
                )
            )
        return

    # Method definitions inside class
    if ntype == "method_definition" and current_class:
        name_node = _child_by_type(node, "property_identifier") or _child_by_type(
            node, "private_property_identifier"
        )
        if name_node:
            name = _text(name_node, source)
            # Skip constructors
            if name == "constructor":
                _collect_constructor_parameter_properties(
                    node, source, artifacts, current_class
                )
                return
            args, returns = _extract_func_signature(node, source)
            is_async = any(c.type == "async" for c in node.children)
            artifacts.append(
                FoundArtifact(
                    kind=ArtifactKind.METHOD,
                    name=name,
                    of=current_class,
                    args=args,
                    returns=returns,
                    is_async=is_async,
                    is_stub=_is_stub_body_ts(node, source),
                    line=node.start_point[0] + 1,
                )
            )
        return

    # Public field definitions inside class (properties, arrow function class properties)
    if ntype == "public_field_definition" and current_class:
        _handle_class_field(node, source, artifacts, current_class)
        return

    # Lexical/variable declarations at module scope (arrow functions, const)
    if (
        ntype in ("lexical_declaration", "variable_declaration")
        and current_class is None
    ):
        for child in node.children:
            if child.type == "variable_declarator":
                _handle_variable_declarator(child, source, artifacts)
        return

    # Export statements
    if ntype == "export_statement":
        for child in node.children:
            _collect_impl(child, source, artifacts, current_class)
        return

    # Recurse into other nodes
    for child in node.children:
        _collect_impl(child, source, artifacts, current_class)


def _handle_variable_declarator(
    node, source: bytes, artifacts: list[FoundArtifact]
) -> None:
    name_node = _child_by_type(node, "identifier")
    if not name_node:
        return
    name = _text(name_node, source)

    # Check if RHS is an arrow function or function expression
    value = None
    for child in node.children:
        if child.type in (
            "arrow_function",
            "function_expression",
            "generator_function",
        ):
            value = child
            break

    if value:
        args, returns = _extract_func_signature(value, source)
        # Also check type annotation on the variable for return type
        if not returns:
            returns = _extract_type_annotation_return(node, source)
        is_async = any(c.type == "async" for c in value.children)
        artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.FUNCTION,
                name=name,
                args=args,
                returns=returns,
                is_async=is_async,
                is_stub=_is_stub_body_ts(value, source),
                line=node.start_point[0] + 1,
            )
        )
    else:
        # It's a module-level variable/attribute - check it's not inside an object
        parent = node.parent
        if parent and parent.type in ("object", "pair"):
            return
        artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.ATTRIBUTE,
                name=name,
                line=node.start_point[0] + 1,
            )
        )


def _handle_class_field(
    node, source: bytes, artifacts: list[FoundArtifact], current_class: str
) -> None:
    """Handle class property definitions (public_field_definition).

    Covers:
    - Regular properties: `name: string;`
    - Arrow function properties: `login = async (user: string) => {...};`
    - Readonly properties: `readonly debug: boolean = false;`
    """
    name = None
    arrow_fn = None

    # Check if private/protected
    for child in node.children:
        if child.type == "accessibility_modifier" and _text(child, source) in (
            "private",
            "protected",
        ):
            return  # Skip private/protected fields

    for child in node.children:
        if child.type == "property_identifier":
            name = _text(child, source)
        elif child.type == "arrow_function":
            arrow_fn = child
        elif child.type == "function_expression":
            arrow_fn = child

    if not name:
        return

    if name.startswith("_") or name.startswith("#"):
        # Private field - still add but it will be flagged by is_private
        pass

    if arrow_fn:
        # Arrow function class property -> METHOD
        args, returns = _extract_func_signature(arrow_fn, source)
        is_async = any(c.type == "async" for c in arrow_fn.children)
        artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.METHOD,
                name=name,
                of=current_class,
                args=args,
                returns=returns,
                is_async=is_async,
                is_stub=_is_stub_body_ts(arrow_fn, source),
                line=node.start_point[0] + 1,
            )
        )
    else:
        # Regular class property -> ATTRIBUTE
        type_ann = None
        for child in node.children:
            if child.type == "type_annotation":
                type_ann = _extract_type_text(child, source)
        artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.ATTRIBUTE,
                name=name,
                of=current_class,
                type_annotation=type_ann,
                line=node.start_point[0] + 1,
            )
        )


def _extract_func_signature(
    node, source: bytes
) -> tuple[tuple[ArgSpec, ...], Optional[str]]:
    """Extract function arguments and return type from a function-like node."""
    args: list[ArgSpec] = []
    returns: Optional[str] = None

    params = _child_by_type(node, "formal_parameters")
    if params:
        for child in params.children:
            if child.type in ("required_parameter", "optional_parameter"):
                arg = _extract_arg_spec(child, source)
                if arg:
                    args.append(arg)

    # Return type annotation
    ret_node = _child_by_type(node, "type_annotation")
    if ret_node:
        returns = _extract_type_text(ret_node, source)

    return tuple(args), returns


def _extract_arg_spec(parameter, source: bytes) -> Optional[ArgSpec]:
    name: Optional[str] = None
    type_annotation: Optional[str] = None
    default: Optional[str] = None
    seen_default_marker = False

    for child in parameter.children:
        if child.type == "identifier":
            name = _text(child, source)
        elif child.type == "rest_pattern":
            name = _pattern_text(child, source)
        elif child.type in ("object_pattern", "array_pattern"):
            name = _text(child, source).strip()
        elif child.type == "type_annotation":
            type_annotation = _extract_type_text(child, source)
        elif child.type == "=":
            seen_default_marker = True
        elif seen_default_marker and child.type not in (",", "comment"):
            default = _text(child, source).strip()
            seen_default_marker = False

    if not name:
        return None

    return ArgSpec(name=name, type=type_annotation, default=default)


def _pattern_text(pattern, source: bytes) -> str:
    identifier = _child_by_type(pattern, "identifier")
    if identifier:
        return _text(identifier, source)
    return _text(pattern, source).removeprefix("...").strip()


def _collect_constructor_parameter_properties(
    node,
    source: bytes,
    artifacts: list[FoundArtifact],
    current_class: str,
) -> None:
    params = _child_by_type(node, "formal_parameters")
    if not params:
        return

    for child in params.children:
        if child.type not in ("required_parameter", "optional_parameter"):
            continue
        if _constructor_parameter_is_private(child, source):
            continue
        if not _constructor_parameter_is_public_property(child, source):
            continue

        arg = _extract_arg_spec(child, source)
        if not arg:
            continue
        artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.ATTRIBUTE,
                name=arg.name,
                of=current_class,
                type_annotation=arg.type,
                line=child.start_point[0] + 1,
            )
        )


def _constructor_parameter_is_private(parameter, source: bytes) -> bool:
    for child in parameter.children:
        if child.type == "accessibility_modifier" and _text(child, source) in (
            "private",
            "protected",
        ):
            return True
    return False


def _constructor_parameter_is_public_property(parameter, source: bytes) -> bool:
    for child in parameter.children:
        if child.type == "accessibility_modifier" and _text(child, source) == "public":
            return True
        if child.type == "readonly":
            return True
    return False


def _extract_type_text(type_node, source: bytes) -> Optional[str]:
    """Extract type text from a type_annotation node (skip the ': ' prefix)."""
    text = _text(type_node, source)
    if text.startswith(":"):
        text = text[1:].strip()
    return text if text else None


def _extract_type_annotation_return(node, source: bytes) -> Optional[str]:
    """Extract return type from variable declarator type annotation."""
    for child in node.children:
        if child.type == "type_annotation":
            return _extract_type_text(child, source)
    return None


def _extract_interface_bases(node, source: bytes) -> tuple[str, ...]:
    """Extract base types from interface extends_type_clause."""
    bases: list[str] = []
    for child in node.children:
        if child.type == "extends_type_clause":
            for ec in child.children:
                if ec.type in ("identifier", "type_identifier"):
                    bases.append(_text(ec, source))
    return tuple(bases)


def _extract_bases(node, source: bytes) -> tuple[str, ...]:
    bases: list[str] = []
    for child in node.children:
        if child.type == "class_heritage":
            for hc in child.children:
                if hc.type in ("extends_clause", "implements_clause"):
                    for ec in hc.children:
                        if ec.type in ("identifier", "type_identifier"):
                            bases.append(_text(ec, source))
    return tuple(bases)


def _child_by_type(node, type_name: str):
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _child_text(node, type_name: str, source: bytes) -> Optional[str]:
    child = _child_by_type(node, type_name)
    return _text(child, source) if child else None


_TEST_CALLEE_NAMES = frozenset({"it", "test", "fit", "xit"})
_DIRECT_TEST_MODIFIERS = frozenset(
    {"only", "skip", "todo", "concurrent", "fails", "fixme"}
)
_SUITE_HELPERS = frozenset({"describe", "fdescribe", "xdescribe"})
_SUITE_MODIFIERS = frozenset({"each", "only", "skip"})
_FUNCTION_SCOPE_NODES = frozenset(
    {
        "arrow_function",
        "function_declaration",
        "function_expression",
        "generator_function",
        "generator_function_declaration",
        "method_definition",
    }
)


def _call_function_node(call_node):
    for child in call_node.children:
        if child.type in (
            "identifier",
            "member_expression",
            "subscript_expression",
            "call_expression",
        ):
            return child
    return None


def _resolve_test_call_target(
    node, source: bytes
) -> Optional[tuple[str, tuple[str, ...]]]:
    """Resolve a call target to its base identifier and chained properties.

    This flattens curried call chains such as ``it.each(...)("case", ...)`` into
    ``("it", ("each",))`` and member chains such as ``test.skip(...)`` into
    ``("test", ("skip",))``.
    """
    if node is None:
        return None

    if node.type == "identifier":
        return (_text(node, source), ())

    if node.type == "call_expression":
        return _resolve_test_call_target(_call_function_node(node), source)

    if node.type == "subscript_expression":
        for child in node.children:
            if child.type in (
                "identifier",
                "member_expression",
                "call_expression",
                "subscript_expression",
            ):
                return _resolve_test_call_target(child, source)
        return None

    if node.type != "member_expression":
        return None

    object_node = None
    property_name = None
    for child in node.children:
        if child.type in (
            "identifier",
            "member_expression",
            "call_expression",
            "subscript_expression",
        ):
            if object_node is None:
                object_node = child
            elif property_name is None:
                property_name = _text(child, source)
        elif child.type == "property_identifier":
            property_name = _text(child, source)

    target = _resolve_test_call_target(object_node, source)
    if target is None or property_name is None:
        return None
    base, properties = target
    return base, (*properties, property_name)


def _is_executable_test_target(base: str, properties: tuple[str, ...]) -> bool:
    """Return True only for label-bearing test declarations, not suite helpers."""
    if base in _SUITE_HELPERS or any(prop in _SUITE_HELPERS for prop in properties):
        return False
    if base not in _TEST_CALLEE_NAMES:
        return False
    if base in {"fit", "xit"}:
        return not properties

    each_count = properties.count("each")
    if each_count > 1:
        return False

    for prop in properties:
        if prop == "each":
            continue
        if prop not in _DIRECT_TEST_MODIFIERS:
            return False

    return True


def _is_suite_target(base: str, properties: tuple[str, ...]) -> bool:
    """Return True for suite wrappers whose callbacks may register tests."""
    if base in _SUITE_HELPERS:
        if properties.count("each") > 1:
            return False
        return all(prop in _SUITE_MODIFIERS for prop in properties)

    if base != "test" or not properties or properties[0] != "describe":
        return False
    if properties.count("each") > 1:
        return False

    return all(prop == "describe" or prop in _SUITE_MODIFIERS for prop in properties)


def _is_suite_callback_scope(node, source: bytes) -> bool:
    parent = node.parent
    if parent is None or parent.type != "arguments":
        return False

    call_node = parent.parent
    if call_node is None or call_node.type != "call_expression":
        return False

    target = _resolve_test_call_target(_call_function_node(call_node), source)
    if target is None:
        return False

    base, properties = target
    return _is_suite_target(base, properties)


def _is_executable_test_scope(node, source: bytes) -> bool:
    """Allow test registration only at module scope or suite callbacks."""
    current = node.parent
    while current is not None:
        if current.type in _FUNCTION_SCOPE_NODES and not _is_suite_callback_scope(
            current, source
        ):
            return False
        current = current.parent
    return True


def _extract_test_callee_name(call_node, source: bytes) -> Optional[str]:
    """Return the base callee name for an executable test declaration."""
    target = _resolve_test_call_target(_call_function_node(call_node), source)
    if target is None:
        return None
    base, properties = target
    if not _is_executable_test_target(base, properties):
        return None
    if not _is_executable_test_scope(call_node, source):
        return None
    return base


def _first_string_argument(call_node, source: bytes) -> Optional[str]:
    """Return the literal value of the first string argument of a call."""
    args = _child_by_type(call_node, "arguments")
    if args is None:
        return None
    for child in args.children:
        if child.type == "string":
            text = _text(child, source)
            if len(text) >= 2 and text[0] in ("'", '"') and text[-1] == text[0]:
                return text[1:-1]
            return text
        if child.type == "template_string":
            has_substitution = any(
                c.type == "template_substitution" for c in child.children
            )
            if has_substitution:
                return None
            text = _text(child, source)
            if len(text) >= 2 and text.startswith("`") and text.endswith("`"):
                return text[1:-1]
            return text
        if child.type in ("(", ","):
            continue
        # Any other kind of first argument (function, identifier, object) means
        # this isn't a recognizable test label.
        return None
    return None


def _scan_imports(
    root,
    source: bytes,
    importer_module: str,
    project_root: Path,
    artifacts: list[FoundArtifact],
    seen: set[str],
) -> tuple[dict[str, dict], dict[str, str]]:
    """Pre-scan top-level import_statement nodes.

    Returns ``(import_map, namespace_imports)`` and side-effects each
    bound import name into ``artifacts`` with import_source/alias_of so
    later identifier walks dedup into the identity-bearing record.

    - ``import_map``: bound name -> {"source": resolved_module, "alias_of": Optional[str]}
    - ``namespace_imports``: bound name -> resolved_module (only for `* as ns` imports)
    """
    import_map: dict[str, dict] = {}
    namespace_imports: dict[str, str] = {}

    for child in root.children:
        if child.type != "import_statement":
            continue
        spec_node = _child_by_type(child, "string")
        if spec_node is None:
            continue
        frag = _child_by_type(spec_node, "string_fragment")
        if frag is None:
            continue
        raw_specifier = _text(frag, source)
        resolved = resolve_ts_import(raw_specifier, importer_module, project_root)

        clause = _child_by_type(child, "import_clause")
        if clause is None:
            # side-effect import — binds nothing
            continue

        for cc in clause.children:
            if cc.type == "named_imports":
                for spec in cc.children:
                    if spec.type != "import_specifier":
                        continue
                    idents = [c for c in spec.children if c.type == "identifier"]
                    if not idents:
                        continue
                    if len(idents) >= 2:
                        original = _text(idents[0], source)
                        bound = _text(idents[1], source)
                        alias_of: Optional[str] = original
                    else:
                        bound = _text(idents[0], source)
                        alias_of = None
                    _record_import(
                        bound, resolved, alias_of, import_map, artifacts, seen
                    )
            elif cc.type == "namespace_import":
                for nc in cc.children:
                    if nc.type == "identifier":
                        bound = _text(nc, source)
                        namespace_imports[bound] = resolved
                        _record_import(
                            bound, resolved, None, import_map, artifacts, seen
                        )
                        break
            elif cc.type == "identifier":
                bound = _text(cc, source)
                _record_import(bound, resolved, None, import_map, artifacts, seen)

    return import_map, namespace_imports


def _ts_project_root_for(file_path: Union[str, Path]) -> Path:
    path = Path(file_path)
    if not path.is_absolute():
        return Path(".")

    start = path.parent if path.suffix else path
    for candidate in (start, *start.parents):
        if (candidate / "tsconfig.json").exists():
            return candidate
    return Path(".")


def _record_import(
    bound: str,
    resolved: str,
    alias_of: Optional[str],
    import_map: dict[str, dict],
    artifacts: list[FoundArtifact],
    seen: set[str],
) -> None:
    if not bound or bound in seen:
        return
    import_map[bound] = {"source": resolved, "alias_of": alias_of}
    seen.add(bound)
    artifacts.append(
        FoundArtifact(
            kind=ArtifactKind.FUNCTION,
            name=bound,
            import_source=resolved or None,
            alias_of=alias_of,
        )
    )


def _resolve_member_chain(
    node, source: bytes, namespace_imports: dict[str, str]
) -> Optional[tuple[str, str]]:
    """Walk a member_expression chain.

    If rooted at a namespace-imported name, return ``(leaf, source_path)``.
    Otherwise return ``None``. ``source_path`` extends the namespace by
    intermediate property_identifiers using "/" (TS path style).
    """
    attrs: list[str] = []
    current = node
    while current is not None and current.type == "member_expression":
        prop = None
        obj = None
        for c in current.children:
            if c.type == "property_identifier":
                prop = c
            elif c.type not in (".", "?.", "?"):
                if c.type in ("identifier", "member_expression"):
                    obj = c
        if prop is None or obj is None:
            return None
        attrs.append(_text(prop, source))
        current = obj

    if current is None or current.type != "identifier":
        return None
    root_name = _text(current, source)
    namespace = namespace_imports.get(root_name)
    if namespace is None:
        return None

    attrs.reverse()
    leaf = attrs[-1]
    middle = attrs[:-1]
    if middle:
        source_path = "/".join([namespace, *middle])
    else:
        source_path = namespace
    return leaf, source_path


def _member_property_name(node, source: bytes) -> Optional[str]:
    if node.type != "member_expression":
        return None
    for child in node.children:
        if child.type == "property_identifier":
            return _text(child, source)
    return None


def _record_bare_reference(name: str, artifacts: list[FoundArtifact]) -> None:
    if name and not any(a.name == name and a.import_source is None for a in artifacts):
        artifacts.append(FoundArtifact(kind=ArtifactKind.FUNCTION, name=name))


def _collect_refs(
    node,
    source: bytes,
    artifacts: list[FoundArtifact],
    seen: set[str],
    *,
    import_map: Optional[dict[str, dict]] = None,
    namespace_imports: Optional[dict[str, str]] = None,
) -> None:
    """Collect identifier references and executable test labels.

    Only real test-runner declarations such as ``it("name", ...)`` and
    ``test("name", ...)`` are emitted as ``ArtifactKind.TEST_FUNCTION``.
    Plain ``test_*`` helpers are treated as ordinary code references.
    """
    if import_map is None:
        import_map = {}
    if namespace_imports is None:
        namespace_imports = {}

    # Imports were collected separately by _scan_imports; skip walking them.
    if node.type == "import_statement":
        return

    if node.type == "member_expression":
        resolved = _resolve_member_chain(node, source, namespace_imports)
        if resolved is not None:
            leaf, source_path = resolved
            if leaf and leaf not in seen:
                seen.add(leaf)
                artifacts.append(
                    FoundArtifact(
                        kind=ArtifactKind.FUNCTION,
                        name=leaf,
                        import_source=source_path or None,
                    )
                )
        property_name = _member_property_name(node, source)
        if property_name and not any(a.name == property_name for a in artifacts):
            artifacts.append(
                FoundArtifact(kind=ArtifactKind.FUNCTION, name=property_name)
            )

    elif node.type == "pair":
        property_name = _child_text(node, "property_identifier", source)
        if property_name:
            _record_bare_reference(property_name, artifacts)

    elif node.type == "shorthand_property_identifier":
        _record_bare_reference(_text(node, source), artifacts)

    elif node.type == "jsx_attribute":
        property_name = _child_text(node, "property_identifier", source)
        if property_name:
            _record_bare_reference(property_name, artifacts)

    if node.type == "identifier":
        name = _text(node, source)
        if name and name not in seen:
            seen.add(name)
            artifacts.append(FoundArtifact(kind=ArtifactKind.FUNCTION, name=name))

    elif node.type == "type_identifier":
        name = _text(node, source)
        if name and name not in seen:
            seen.add(name)
            artifacts.append(FoundArtifact(kind=ArtifactKind.FUNCTION, name=name))

    elif node.type == "call_expression":
        callee = _extract_test_callee_name(node, source)
        if callee is not None:
            label = _first_string_argument(node, source)
            if label:
                artifacts.append(
                    FoundArtifact(
                        kind=ArtifactKind.TEST_FUNCTION,
                        name=label,
                        line=node.start_point[0] + 1,
                    )
                )
                seen.add(label)

    for child in node.children:
        _collect_refs(
            child,
            source,
            artifacts,
            seen,
            import_map=import_map,
            namespace_imports=namespace_imports,
        )


def _collect_test_bodies(node, source: bytes, bodies: dict[str, str]) -> None:
    """Extract per-test body source text keyed by test function name.

    Recognizes executable test-runner calls such as ``it("name", ...)`` and
    ``test("name", ...)``. Plain ``test_*`` helpers are intentionally ignored.

    Nested declarations inside other test callbacks are intentionally
    ignored — those are helpers, not independent tests. Names claimed by
    an outer declaration are not overwritten by inner ones.
    """
    if node.type == "call_expression":
        callee = _extract_test_callee_name(node, source)
        if callee is not None:
            label = _first_string_argument(node, source)
            if label:
                body_text = _extract_test_callback_body(node, source)
                if body_text is None:
                    body_text = _text(node, source)
                bodies.setdefault(label, body_text)
                return

    for child in node.children:
        _collect_test_bodies(child, source, bodies)


def _extract_test_callback_body(call_node, source: bytes) -> Optional[str]:
    """Return the text of the callback passed to a test call, if any."""
    args = _child_by_type(call_node, "arguments")
    if args is None:
        return None
    # Skip the string label and any separators; return first callback-like arg.
    for child in args.children:
        if child.type in (
            "arrow_function",
            "function_expression",
            "generator_function",
        ):
            # Prefer the statement_block body if present, otherwise the expr.
            block = _child_by_type(child, "statement_block")
            if block is not None:
                return _text(block, source)
            return _text(child, source)
    return None
