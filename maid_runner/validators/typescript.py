"""TypeScript/JavaScript validator for MAID Runner v2.

Uses tree-sitter for accurate AST parsing. Requires tree-sitter-typescript.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

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
        return (".ts", ".tsx", ".js", ".jsx")

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

        artifacts: list[FoundArtifact] = []
        _collect_impl(tree.root_node, source_bytes, artifacts, current_class=None)

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

        artifacts: list[FoundArtifact] = []
        seen: set[str] = set()
        _collect_refs(tree.root_node, source_bytes, artifacts, seen)

        return CollectionResult(
            artifacts=artifacts,
            language="typescript",
            file_path=str(file_path),
        )


def _text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8")


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
                pname = None
                ptype = None
                for pc in child.children:
                    if pc.type == "identifier":
                        pname = _text(pc, source)
                    elif pc.type == "type_annotation":
                        ptype = _extract_type_text(pc, source)
                if pname:
                    args.append(ArgSpec(name=pname, type=ptype))

    # Return type annotation
    ret_node = _child_by_type(node, "type_annotation")
    if ret_node:
        returns = _extract_type_text(ret_node, source)

    return tuple(args), returns


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


def _collect_refs(
    node, source: bytes, artifacts: list[FoundArtifact], seen: set[str]
) -> None:
    """Collect all identifier references for behavioral validation."""
    if node.type == "identifier":
        name = _text(node, source)
        if name and name not in seen:
            seen.add(name)
            artifacts.append(FoundArtifact(kind=ArtifactKind.FUNCTION, name=name))

    if node.type == "type_identifier":
        name = _text(node, source)
        if name and name not in seen:
            seen.add(name)
            artifacts.append(FoundArtifact(kind=ArtifactKind.FUNCTION, name=name))

    for child in node.children:
        _collect_refs(child, source, artifacts, seen)
