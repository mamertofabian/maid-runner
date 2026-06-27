"""Private TypeScript implementation artifact collector."""

from __future__ import annotations

from typing import Any, Optional

from maid_runner.core.types import ArtifactKind, ArgSpec
from maid_runner.validators.base import FoundArtifact


def _text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8")


_OBJECT_MEMBER_NODE_TYPES = frozenset(
    {
        "pair",
        "method_definition",
        "shorthand_property_identifier",
        "spread_element",
    }
)


def _object_literal_has_members(node) -> bool:
    return any(child.type in _OBJECT_MEMBER_NODE_TYPES for child in node.children)


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
            if child.type == "object" and not _object_literal_has_members(child):
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
            if val.type == "object" and not _object_literal_has_members(val):
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


def collect_implementation_artifacts(root: Any, source: bytes) -> list[FoundArtifact]:
    artifacts: list[FoundArtifact] = []
    _collect_impl(root, source, artifacts, current_class=None)
    return _filter_public_implementation_artifacts(artifacts, root, source)


def _filter_public_implementation_artifacts(
    artifacts: list[FoundArtifact], root: Any, source: bytes
) -> list[FoundArtifact]:
    is_es_module = _is_es_module(root)
    exported_names = _exported_local_names(root, source) if is_es_module else set()

    visible: list[FoundArtifact] = []
    for artifact in artifacts:
        if not is_es_module and _exported_object_member_owner(artifact) is not None:
            continue
        if is_es_module and not _artifact_is_export_visible(artifact, exported_names):
            continue
        visible.append(artifact)
    return visible


def _artifact_is_export_visible(
    artifact: FoundArtifact, exported_names: set[str]
) -> bool:
    exported_object = _exported_object_member_owner(artifact)
    if exported_object is not None:
        return exported_object in exported_names
    if artifact.of:
        return artifact.of in exported_names
    return artifact.name in exported_names


def _exported_object_member_owner(artifact: FoundArtifact) -> Optional[str]:
    context = artifact.reference_context
    if context is None or not context.startswith("object:"):
        return None
    owner = context.removeprefix("object:")
    return owner or None


def _is_es_module(root) -> bool:
    return any(
        child.type in ("import_statement", "export_statement")
        for child in root.children
    )


def _exported_local_names(root, source: bytes) -> set[str]:
    exported: set[str] = set()
    for child in root.children:
        if child.type == "export_statement":
            exported.update(_exported_names_from_statement(child, source))
    return exported


def _exported_names_from_statement(node, source: bytes) -> set[str]:
    exported: set[str] = set()
    if _child_by_type(node, "string") is not None:
        return exported
    if any(child.type == "=" for child in node.children):
        return _export_assignment_local_names(node, source)

    has_default = any(child.type == "default" for child in node.children)
    for child in node.children:
        if child.type == "export_clause":
            exported.update(_export_clause_local_names(child, source))
        elif has_default and child.type == "call_expression":
            exported.update(_default_export_wrapper_local_names(child, source))
        else:
            exported.update(_top_level_declaration_names(child, source))
        if has_default and child.type == "identifier":
            exported.add(_text(child, source))
    return exported


def _export_assignment_local_names(node, source: bytes) -> set[str]:
    seen_equals = False
    for child in node.children:
        if child.type == "=":
            seen_equals = True
            continue
        if seen_equals and child.type in ("identifier", "type_identifier"):
            return {_text(child, source)}
    return set()


def _export_clause_local_names(node, source: bytes) -> set[str]:
    names: set[str] = set()
    for child in node.children:
        if child.type != "export_specifier":
            continue
        identifiers = [
            _text(grandchild, source)
            for grandchild in child.children
            if grandchild.type in ("identifier", "type_identifier")
        ]
        if identifiers:
            names.add(identifiers[0])
    return names


def _default_export_wrapper_local_names(node, source: bytes) -> set[str]:
    if not _is_react_component_wrapper_call(node, source):
        return set()

    target = _react_wrapper_export_argument(node, source)
    if target is None:
        return set()
    if target.type in ("identifier", "type_identifier"):
        return {_text(target, source)}
    if target.type in ("function_expression", "generator_function"):
        name = _function_declaration_name(target, source)
        return {name} if name else {"default"}
    if target.type == "arrow_function":
        return {"default"}
    return set()


def _top_level_declaration_names(node, source: bytes) -> set[str]:
    if node.type in ("class_declaration", "abstract_class_declaration", "class"):
        name = _class_declaration_name(node, source)
        return {name} if name else set()
    if node.type == "interface_declaration":
        name = _interface_declaration_name(node, source)
        return {name} if name else set()
    if node.type in (
        "function_declaration",
        "generator_function_declaration",
        "function_signature",
        "function_expression",
        "arrow_function",
    ):
        name = _function_declaration_name(node, source)
        return {name} if name else set()
    if node.type == "type_alias_declaration":
        name = _type_alias_name(node, source)
        return {name} if name else set()
    if node.type == "enum_declaration":
        name = _enum_declaration_name(node, source)
        return {name} if name else set()
    if node.type == "internal_module":
        name = _namespace_declaration_name(node, source)
        return {name} if name else set()
    if node.type in ("lexical_declaration", "variable_declaration"):
        return {
            name
            for child in node.children
            if child.type == "variable_declarator"
            for name in _top_level_declaration_names(child, source)
        }
    if node.type == "variable_declarator":
        name = _child_text(node, "identifier", source)
        return {name} if name else set()
    return set()


def _has_private_or_protected_modifier(node, source: bytes) -> bool:
    return any(
        child.type == "accessibility_modifier"
        and _text(child, source) in ("private", "protected")
        for child in node.children
    )


def _collect_impl(
    node, source: bytes, artifacts: list[FoundArtifact], current_class: Optional[str]
) -> None:
    handlers = (
        _collect_class_declaration,
        _collect_interface_declaration,
        _collect_type_alias_declaration,
        _collect_enum_declaration,
        _collect_namespace_declaration,
        _collect_function_declaration,
        _collect_default_arrow_function,
        _collect_class_method_signature,
        _collect_class_method_definition,
        _collect_class_field_definition,
        _collect_module_scope_variable_declaration,
        _collect_export_statement,
    )
    for handler in handlers:
        if handler(node, source, artifacts, current_class):
            return

    for child in node.children:
        _collect_impl(child, source, artifacts, current_class)


def _collect_class_declaration(
    node, source: bytes, artifacts: list[FoundArtifact], current_class: Optional[str]
) -> bool:
    if node.type not in ("class_declaration", "abstract_class_declaration", "class"):
        return False

    name = _class_declaration_name(node, source)
    if not name:
        return False

    artifacts.append(
        FoundArtifact(
            kind=ArtifactKind.CLASS,
            name=name,
            bases=_extract_bases(node, source),
            type_parameters=_extract_type_parameters(node, source),
            line=node.start_point[0] + 1,
        )
    )
    body = _child_by_type(node, "class_body")
    if body:
        for child in body.children:
            _collect_impl(child, source, artifacts, current_class=name)
    return True


def _collect_interface_declaration(
    node, source: bytes, artifacts: list[FoundArtifact], current_class: Optional[str]
) -> bool:
    if node.type != "interface_declaration":
        return False

    name = _child_text(node, "type_identifier", source) or _child_text(
        node, "identifier", source
    )
    if name:
        artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.INTERFACE,
                name=name,
                bases=_extract_interface_bases(node, source),
                type_parameters=_extract_type_parameters(node, source),
                line=node.start_point[0] + 1,
            )
        )
        _collect_interface_members(node, source, artifacts, name)
    return True


def _collect_interface_members(
    node, source: bytes, artifacts: list[FoundArtifact], interface_name: str
) -> None:
    body = _child_by_type(node, "interface_body") or _child_by_type(node, "object_type")
    if body is None:
        return

    for child in body.children:
        if child.type == "property_signature":
            _collect_interface_property(child, source, artifacts, interface_name)
        elif child.type == "method_signature":
            _collect_interface_method(child, source, artifacts, interface_name)


def _collect_interface_property(
    node, source: bytes, artifacts: list[FoundArtifact], interface_name: str
) -> None:
    prop_name = _member_name_text(node, source)
    if not prop_name:
        return

    type_ann = None
    for child in node.children:
        if child.type == "type_annotation":
            type_ann = _extract_type_text(child, source)
    artifacts.append(
        FoundArtifact(
            kind=ArtifactKind.ATTRIBUTE,
            name=prop_name,
            of=interface_name,
            type_annotation=type_ann,
            line=node.start_point[0] + 1,
        )
    )


def _collect_interface_method(
    node, source: bytes, artifacts: list[FoundArtifact], interface_name: str
) -> None:
    method_name = _member_name_text(node, source)
    if not method_name:
        return

    args, returns = _extract_func_signature(node, source)
    artifacts.append(
        FoundArtifact(
            kind=ArtifactKind.METHOD,
            name=method_name,
            of=interface_name,
            args=args,
            returns=returns,
            type_parameters=_extract_type_parameters(node, source),
            line=node.start_point[0] + 1,
        )
    )


def _collect_type_alias_declaration(
    node, source: bytes, artifacts: list[FoundArtifact], current_class: Optional[str]
) -> bool:
    if node.type != "type_alias_declaration":
        return False

    name = _type_alias_name(node, source)
    if name:
        artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.TYPE,
                name=name,
                type_parameters=_extract_type_parameters(node, source),
                type_annotation=_extract_type_alias_target(node, source),
                line=node.start_point[0] + 1,
            )
        )
    return True


def _collect_enum_declaration(
    node, source: bytes, artifacts: list[FoundArtifact], current_class: Optional[str]
) -> bool:
    if node.type != "enum_declaration":
        return False

    name = _enum_declaration_name(node, source)
    if name:
        artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.ENUM,
                name=name,
                line=node.start_point[0] + 1,
            )
        )
    return True


def _collect_namespace_declaration(
    node, source: bytes, artifacts: list[FoundArtifact], current_class: Optional[str]
) -> bool:
    if node.type != "internal_module":
        return False

    name = _namespace_declaration_name(node, source)
    if name:
        artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.NAMESPACE,
                name=name,
                line=node.start_point[0] + 1,
            )
        )
    return True


def _collect_function_declaration(
    node, source: bytes, artifacts: list[FoundArtifact], current_class: Optional[str]
) -> bool:
    if node.type not in (
        "function_declaration",
        "generator_function_declaration",
        "function_signature",
        "function_expression",
    ):
        return False

    name = _function_declaration_name(node, source)
    if name:
        _append_function_artifact(node, source, artifacts, name)
    return True


def _collect_default_arrow_function(
    node, source: bytes, artifacts: list[FoundArtifact], current_class: Optional[str]
) -> bool:
    if node.type != "arrow_function" or not _is_default_export_child(node):
        return False

    _append_function_artifact(node, source, artifacts, "default")
    return True


def _append_function_artifact(
    node, source: bytes, artifacts: list[FoundArtifact], name: str
) -> None:
    args, returns = _extract_func_signature(node, source)
    artifacts.append(
        FoundArtifact(
            kind=ArtifactKind.FUNCTION,
            name=name,
            args=args,
            returns=returns,
            type_parameters=_extract_type_parameters(node, source),
            is_async=any(c.type == "async" for c in node.children),
            is_stub=_is_stub_body_ts(node, source),
            line=node.start_point[0] + 1,
        )
    )


def _collect_class_method_signature(
    node, source: bytes, artifacts: list[FoundArtifact], current_class: Optional[str]
) -> bool:
    if node.type != "abstract_method_signature" or not current_class:
        return False
    if _has_private_or_protected_modifier(node, source):
        return True

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
                type_parameters=_extract_type_parameters(node, source),
                line=node.start_point[0] + 1,
            )
        )
    return True


def _collect_class_method_definition(
    node, source: bytes, artifacts: list[FoundArtifact], current_class: Optional[str]
) -> bool:
    if node.type != "method_definition" or not current_class:
        return False
    if _has_private_or_protected_modifier(node, source):
        return True

    name = _method_definition_name(node, source)
    if name:
        if name == "constructor":
            _collect_constructor_parameter_properties(
                node, source, artifacts, current_class
            )
        else:
            _append_method_artifact(node, source, artifacts, current_class, name)
    return True


def _append_method_artifact(
    node,
    source: bytes,
    artifacts: list[FoundArtifact],
    current_class: str,
    name: str,
) -> None:
    args, returns = _extract_func_signature(node, source)
    artifacts.append(
        FoundArtifact(
            kind=ArtifactKind.METHOD,
            name=name,
            of=current_class,
            args=args,
            returns=returns,
            type_parameters=_extract_type_parameters(node, source),
            is_async=any(c.type == "async" for c in node.children),
            is_stub=_is_stub_body_ts(node, source),
            line=node.start_point[0] + 1,
        )
    )


def _collect_class_field_definition(
    node, source: bytes, artifacts: list[FoundArtifact], current_class: Optional[str]
) -> bool:
    if node.type != "public_field_definition" or not current_class:
        return False

    _handle_class_field(node, source, artifacts, current_class)
    return True


def _collect_module_scope_variable_declaration(
    node, source: bytes, artifacts: list[FoundArtifact], current_class: Optional[str]
) -> bool:
    if node.type not in ("lexical_declaration", "variable_declaration"):
        return False
    if current_class is not None:
        return False
    if not _is_module_scope_declaration(node):
        return False

    for child in node.children:
        if child.type == "variable_declarator":
            _handle_variable_declarator(child, source, artifacts)
    return True


def _is_module_scope_declaration(node) -> bool:
    parent = node.parent
    if parent is None:
        return False
    if parent.type == "program":
        return True
    return (
        parent.type == "export_statement"
        and parent.parent is not None
        and (parent.parent.type == "program")
    )


def _collect_export_statement(
    node, source: bytes, artifacts: list[FoundArtifact], current_class: Optional[str]
) -> bool:
    if node.type != "export_statement":
        return False
    if _collect_default_react_wrapped_component(node, source, artifacts):
        return True

    for child in node.children:
        _collect_impl(child, source, artifacts, current_class)
    return True


def _collect_default_react_wrapped_component(
    node, source: bytes, artifacts: list[FoundArtifact]
) -> bool:
    if not any(child.type == "default" for child in node.children):
        return False

    call = _child_by_type(node, "call_expression")
    if call is None or not _is_react_component_wrapper_call(call, source):
        return False

    wrapped_value = _react_component_function_argument(call, source)
    if wrapped_value is None:
        return False
    if _function_declaration_name(wrapped_value, source):
        return False

    args, returns = _extract_func_signature(wrapped_value, source)
    artifacts.append(
        FoundArtifact(
            kind=ArtifactKind.FUNCTION,
            name="default",
            args=args,
            returns=returns,
            type_parameters=_extract_type_parameters(wrapped_value, source),
            is_async=any(c.type == "async" for c in wrapped_value.children),
            is_stub=_is_stub_body_ts(wrapped_value, source),
            line=wrapped_value.start_point[0] + 1,
        )
    )
    return True


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
        type_parameters = _extract_type_parameters(value, source)
        if not type_parameters:
            type_parameters = _extract_type_parameters_from_annotation(node, source)
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
                type_parameters=type_parameters,
                is_async=is_async,
                is_stub=_is_stub_body_ts(value, source),
                line=node.start_point[0] + 1,
            )
        )
    elif object_value := _child_by_type(node, "object"):
        artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.ATTRIBUTE,
                name=name,
                line=node.start_point[0] + 1,
            )
        )
        _collect_object_literal_function_members(name, object_value, source, artifacts)
    elif wrapped_value := _react_wrapped_component_value(node, source):
        args, returns = _extract_func_signature(wrapped_value, source)
        type_parameters = _extract_type_parameters(wrapped_value, source)
        if not type_parameters:
            type_parameters = _extract_type_parameters_from_annotation(node, source)
        if not returns:
            returns = _extract_type_annotation_return(node, source)
        is_async = any(c.type == "async" for c in wrapped_value.children)
        artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.FUNCTION,
                name=name,
                args=args,
                returns=returns,
                type_parameters=type_parameters,
                is_async=is_async,
                is_stub=_is_stub_body_ts(wrapped_value, source),
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


def _collect_object_literal_function_members(
    owner: str,
    node,
    source: bytes,
    artifacts: list[FoundArtifact],
) -> None:
    for child in node.children:
        if child.type == "pair":
            name = _member_name_text(child, source)
            value = next(
                (
                    grandchild
                    for grandchild in child.children
                    if grandchild.type
                    in ("arrow_function", "function_expression", "generator_function")
                ),
                None,
            )
        elif child.type == "method_definition":
            name = _method_definition_name(child, source)
            value = child
        else:
            continue
        if not name or value is None:
            continue
        args, returns = _extract_func_signature(value, source)
        artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.FUNCTION,
                name=name,
                args=args,
                returns=returns,
                type_parameters=_extract_type_parameters(value, source),
                is_async=any(c.type == "async" for c in value.children),
                is_stub=_is_stub_body_ts(value, source),
                line=child.start_point[0] + 1,
                reference_context=f"object:{owner}",
            )
        )


def _react_wrapped_component_value(node, source: bytes):
    call = None
    for child in node.children:
        if child.type == "call_expression":
            call = child
            break
    if call is None or not _is_react_component_wrapper_call(call, source):
        return None

    return _react_component_function_argument(call, source)


def _react_component_function_argument(call, source: bytes):
    arguments = _child_by_type(call, "arguments")
    if arguments is None:
        return None

    for child in arguments.children:
        if child.type in (
            "arrow_function",
            "function_expression",
            "generator_function",
        ):
            return child
        if child.type == "call_expression" and _is_react_component_wrapper_call(
            child, source
        ):
            return _react_component_function_argument(child, source)
        if child.type in ("(", ","):
            continue
        return None
    return None


def _react_wrapper_export_argument(call, source: bytes):
    arguments = _child_by_type(call, "arguments")
    if arguments is None:
        return None

    for child in arguments.children:
        if child.type in ("(", ","):
            continue
        if child.type == "call_expression" and _is_react_component_wrapper_call(
            child, source
        ):
            return _react_wrapper_export_argument(child, source)
        return child
    return None


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


def _is_react_component_wrapper_call(call, source: bytes) -> bool:
    function_node = _call_function_node(call)
    if function_node is None:
        return False
    name = _react_wrapper_name(function_node, source)
    return name in {"memo", "forwardRef", "React.memo", "React.forwardRef"}


def _react_wrapper_name(node, source: bytes) -> Optional[str]:
    if node.type == "identifier":
        return _text(node, source)
    if node.type != "member_expression":
        return None

    object_node = None
    property_name = None
    for child in node.children:
        if child.type == "identifier":
            object_node = child
        elif child.type == "property_identifier":
            property_name = _text(child, source)

    if object_node is None or property_name is None:
        return None
    return f"{_text(object_node, source)}.{property_name}"


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
        if child.type in ("property_identifier", "computed_property_name"):
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
        type_parameters = _extract_type_parameters(arrow_fn, source)
        if not type_parameters:
            type_parameters = _extract_type_parameters_from_annotation(node, source)
        if not returns:
            returns = _extract_type_annotation_return(node, source)
        is_async = any(c.type == "async" for c in arrow_fn.children)
        artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.METHOD,
                name=name,
                of=current_class,
                args=args,
                returns=returns,
                type_parameters=type_parameters,
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


def _extract_type_alias_target(node, source: bytes) -> Optional[str]:
    equals = None
    end_byte = node.end_byte
    for child in node.children:
        if child.type == "=":
            equals = child
            continue
        if equals is not None and child.type == ";":
            end_byte = child.start_byte
            break

    if equals is None:
        return None

    text = source[equals.end_byte : end_byte].decode("utf-8").strip()
    return text if text else None


def _extract_type_parameters(node, source: bytes) -> tuple[str, ...]:
    type_parameters = _child_by_type(node, "type_parameters")
    if type_parameters is None:
        return ()

    return tuple(
        _text(child, source)
        for child in type_parameters.children
        if child.type == "type_parameter"
    )


def _extract_type_parameters_from_annotation(node, source: bytes) -> tuple[str, ...]:
    annotation = _child_by_type(node, "type_annotation")
    if annotation is None:
        return ()
    function_type = _find_descendant_by_type(annotation, "function_type")
    if function_type is not None:
        return _extract_type_parameters(function_type, source)
    return ()


def _find_descendant_by_type(node, type_name: str):
    stack = list(reversed(node.children))
    while stack:
        current = stack.pop()
        if current.type == type_name:
            return current
        stack.extend(reversed(current.children))
    return None


def _extract_type_annotation_return(node, source: bytes) -> Optional[str]:
    """Extract return type from variable declarator type annotation."""
    for child in node.children:
        if child.type == "type_annotation":
            function_type = _top_level_type_annotation_node(child)
            if function_type is not None:
                return _extract_function_type_return(function_type, source)
            return _extract_type_text(child, source)
    return None


def _top_level_type_annotation_node(annotation):
    type_node = None
    for child in annotation.children:
        if child.type not in (":", "comment"):
            type_node = child
            break

    while type_node is not None and type_node.type == "parenthesized_type":
        inner = [
            child
            for child in type_node.children
            if child.type not in ("(", ")", "comment")
        ]
        if len(inner) != 1:
            return None
        type_node = inner[0]

    if type_node is not None and type_node.type == "function_type":
        return type_node
    return None


def _extract_function_type_return(node, source: bytes) -> Optional[str]:
    seen_arrow = False
    for child in node.children:
        if child.type == "=>":
            seen_arrow = True
            continue
        if seen_arrow and child.type not in ("comment",):
            return _text(child, source)
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
                    bases.extend(_extract_base_clause_types(hc, source))
    return tuple(bases)


def _extract_base_clause_types(clause, source: bytes) -> list[str]:
    bases: list[str] = []
    children = clause.children
    index = 0
    while index < len(children):
        child = children[index]
        if child.type in (
            "identifier",
            "type_identifier",
            "member_expression",
            "nested_type_identifier",
        ):
            if (
                index + 1 < len(children)
                and children[index + 1].type == "type_arguments"
            ):
                bases.append(_text(child, source) + _text(children[index + 1], source))
                index += 2
                continue
            bases.append(_text(child, source))
        elif child.type == "generic_type":
            bases.append(_text(child, source))
        index += 1
    return bases


def _is_default_export_child(node) -> bool:
    parent = node.parent
    if parent is None or parent.type != "export_statement":
        return False
    return any(child.type == "default" for child in parent.children)


def _class_declaration_name(node, source: bytes) -> Optional[str]:
    name = _child_text(node, "type_identifier", source) or _child_text(
        node, "identifier", source
    )
    if not name and node.type == "class" and _is_default_export_child(node):
        return "default"
    return name


def _function_declaration_name(node, source: bytes) -> Optional[str]:
    name = _child_text(node, "identifier", source)
    if not name and _is_default_export_child(node):
        return "default"
    return name


def _type_alias_name(node, source: bytes) -> Optional[str]:
    return _child_text(node, "type_identifier", source) or _child_text(
        node, "identifier", source
    )


def _interface_declaration_name(node, source: bytes) -> Optional[str]:
    return _child_text(node, "type_identifier", source) or _child_text(
        node, "identifier", source
    )


def _enum_declaration_name(node, source: bytes) -> Optional[str]:
    return _child_text(node, "identifier", source)


def _namespace_declaration_name(node, source: bytes) -> Optional[str]:
    return _child_text(node, "identifier", source) or _child_text(
        node, "type_identifier", source
    )


def _method_definition_name(node, source: bytes) -> Optional[str]:
    name_node = (
        _child_by_type(node, "property_identifier")
        or _child_by_type(node, "private_property_identifier")
        or _child_by_type(node, "computed_property_name")
    )
    return _text(name_node, source) if name_node else None


def _child_by_type(node, type_name: str):
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _child_text(node, type_name: str, source: bytes) -> Optional[str]:
    child = _child_by_type(node, type_name)
    return _text(child, source) if child else None


def _member_name_text(node, source: bytes) -> Optional[str]:
    return _child_text(node, "property_identifier", source) or _child_text(
        node, "computed_property_name", source
    )
