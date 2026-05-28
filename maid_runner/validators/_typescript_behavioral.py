"""TypeScript behavioral artifact and test-body collection."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

from maid_runner.core.ts_module_paths import resolve_ts_import, ts_file_to_module_path
from maid_runner.core.types import ArtifactKind
from maid_runner.validators.base import FoundArtifact


def _text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8")


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

    - ``import_map``: bound name -> {"source": resolved_module, "alias_of": Optional[str], "type_only": bool}
    - ``namespace_imports``: bound name -> resolved_module (only for `* as ns` imports)
    """
    import_map: dict[str, dict] = {}
    namespace_imports: dict[str, str] = {}

    for child in root.children:
        if child.type != "import_statement":
            continue
        require_clause = _child_by_type(child, "import_require_clause")
        if require_clause is not None:
            spec_node = _child_by_type(require_clause, "string")
            frag = _child_by_type(spec_node, "string_fragment") if spec_node else None
            bound = _child_text(require_clause, "identifier", source)
            if frag is not None and bound:
                raw_specifier = _text(frag, source)
                resolved = resolve_ts_import(
                    raw_specifier,
                    importer_module,
                    project_root,
                )
                _record_import(
                    bound,
                    resolved,
                    None,
                    import_map,
                    artifacts,
                    seen,
                )
            continue
        spec_node = _child_by_type(child, "string")
        if spec_node is None:
            continue
        frag = _child_by_type(spec_node, "string_fragment")
        if frag is None:
            continue
        raw_specifier = _text(frag, source)
        resolved = resolve_ts_import(raw_specifier, importer_module, project_root)
        statement_type_only = any(c.type == "type" for c in child.children)

        clause = _child_by_type(child, "import_clause")
        if clause is None:
            # side-effect import - binds nothing
            continue

        for cc in clause.children:
            if cc.type == "named_imports":
                for spec in cc.children:
                    if spec.type != "import_specifier":
                        continue
                    idents = [c for c in spec.children if c.type == "identifier"]
                    if not idents:
                        continue
                    specifier_type_only = statement_type_only or any(
                        c.type == "type" for c in spec.children
                    )
                    if len(idents) >= 2:
                        original = _text(idents[0], source)
                        bound = _text(idents[1], source)
                        alias_of: Optional[str] = original
                    else:
                        bound = _text(idents[0], source)
                        alias_of = None
                    _record_import(
                        bound,
                        resolved,
                        alias_of,
                        import_map,
                        artifacts,
                        seen,
                        bind_value=not specifier_type_only,
                    )
            elif cc.type == "namespace_import":
                for nc in cc.children:
                    if nc.type == "identifier":
                        bound = _text(nc, source)
                        if not statement_type_only:
                            namespace_imports[bound] = resolved
                        _record_import(
                            bound,
                            resolved,
                            None,
                            import_map,
                            artifacts,
                            seen,
                            bind_value=not statement_type_only,
                        )
                        break
            elif cc.type == "identifier":
                bound = _text(cc, source)
                _record_import(
                    bound,
                    resolved,
                    None,
                    import_map,
                    artifacts,
                    seen,
                    bind_value=not statement_type_only,
                )

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
    *,
    bind_value: bool = True,
) -> None:
    if not bound:
        return
    seen_key = f"import:{bound}:{resolved}:{alias_of or ''}"
    if seen_key in seen:
        return
    import_map[bound] = {
        "source": resolved,
        "alias_of": alias_of,
        "type_only": not bind_value,
    }
    seen.add(seen_key)
    artifacts.append(
        FoundArtifact(
            kind=ArtifactKind.FUNCTION,
            name=bound,
            import_source=resolved or None,
            alias_of=alias_of,
            reference_context="import",
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


def _direct_member_object_name(node, source: bytes) -> Optional[str]:
    if node.type != "member_expression":
        return None
    for child in node.children:
        if child.type == "identifier":
            return _text(child, source)
        if child.type not in (".", "?.", "?"):
            return None
    return None


def _member_root_name(node, source: bytes) -> Optional[str]:
    current = _member_root_node(node)
    if current is not None:
        return _text(current, source)
    return None


def _member_root_node(node):
    current = node
    while current is not None:
        if current.type == "identifier":
            return current
        if current.type == "member_expression":
            obj = None
            for child in current.children:
                if child.type in {
                    "identifier",
                    "member_expression",
                    "call_expression",
                    "new_expression",
                }:
                    obj = child
                    break
            current = obj
            continue
        if current.type == "call_expression":
            current = _call_function_node(current)
            continue
        if current.type == "new_expression":
            next_node = None
            for child in current.children:
                if child.type in {
                    "identifier",
                    "member_expression",
                    "call_expression",
                }:
                    next_node = child
                    break
            current = next_node
            continue
        return None
    return None


def _record_bare_reference(name: str, artifacts: list[FoundArtifact]) -> None:
    if name and not any(
        a.name == name and a.import_source is None and a.reference_context == "access"
        for a in artifacts
    ):
        artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.FUNCTION,
                name=name,
                reference_context="access",
            )
        )


_FUNCTION_SCOPE_NODE_TYPES = {
    "arrow_function",
    "function_declaration",
    "function_expression",
    "generator_function",
    "method_definition",
}


_TYPE_ONLY_NODE_TYPES = {
    "type_alias_declaration",
    "interface_declaration",
    "type_annotation",
    "type_arguments",
    "type_parameters",
    "type_parameter",
    "type_query",
    "extends_type_clause",
    "implements_clause",
}

_TYPE_PARAMETER_SCOPE_NODES = _FUNCTION_SCOPE_NODE_TYPES | {
    "class_declaration",
    "abstract_class_declaration",
    "interface_declaration",
    "type_alias_declaration",
}


def _parameter_binding_names(node, source: bytes) -> set[str]:
    names: set[str] = set()
    parameters = _child_by_type(node, "formal_parameters")
    if parameters is not None:
        for child in parameters.children:
            _collect_binding_identifiers(child, source, names)
        return names
    if node.type == "arrow_function":
        for child in node.children:
            if child.type == "=>":
                break
            if child.type in {
                "identifier",
                "object_pattern",
                "array_pattern",
                "required_parameter",
                "optional_parameter",
                "rest_pattern",
            }:
                _collect_binding_identifiers(child, source, names)
                break
    return names


def _direct_block_binding_names(node, source: bytes) -> set[str]:
    names: set[str] = set()
    for child in node.children:
        if child.type in ("lexical_declaration", "variable_declaration"):
            _collect_declaration_bindings(child, source, names)
        elif child.type in (
            "function_declaration",
            "generator_function_declaration",
            "class_declaration",
            "abstract_class_declaration",
            "enum_declaration",
        ):
            name = _child_text(child, "identifier", source) or _child_text(
                child, "type_identifier", source
            )
            if name:
                names.add(name)
    return names


def _direct_local_value_names(node, source: bytes) -> set[str]:
    names: set[str] = set()
    for child in node.children:
        if child.type in (
            "function_declaration",
            "generator_function_declaration",
            "class_declaration",
            "abstract_class_declaration",
            "enum_declaration",
        ):
            name = _child_text(child, "identifier", source) or _child_text(
                child, "type_identifier", source
            )
            if name:
                names.add(name)
    return names


def _direct_type_binding_names(node, source: bytes) -> set[str]:
    names: set[str] = set()
    for child in node.children:
        if child.type in {"interface_declaration", "type_alias_declaration"}:
            name = _child_text(child, "type_identifier", source) or _child_text(
                child,
                "identifier",
                source,
            )
            if name:
                names.add(name)
    return names


def _type_parameter_binding_names(node, source: bytes) -> set[str]:
    names: set[str] = set()
    type_parameters = _child_by_type(node, "type_parameters")
    if type_parameters is None:
        return names
    for child in type_parameters.children:
        if child.type != "type_parameter":
            continue
        name = _first_type_name_child(child, source)
        if name:
            names.add(name)
    return names


def _first_type_name_child(node, source: bytes) -> Optional[str]:
    for child in node.children:
        if child.type in {"identifier", "type_identifier"}:
            return _text(child, source)
    return None


def _control_flow_binding_names(node, source: bytes) -> set[str]:
    if node.type in {"for_statement", "for_in_statement"}:
        return _for_binding_names(node, source)
    if node.type == "catch_clause":
        return _catch_binding_names(node, source)
    return set()


def _for_binding_names(node, source: bytes) -> set[str]:
    names: set[str] = set()
    for child in node.children:
        if child.type in {";", "of", "in", "statement_block"}:
            break
        if child.type in ("lexical_declaration", "variable_declaration"):
            _collect_declaration_bindings(child, source, names)
        elif child.type in {
            "identifier",
            "object_pattern",
            "array_pattern",
            "shorthand_property_identifier_pattern",
        }:
            _collect_binding_identifiers(child, source, names)
    return names


def _catch_binding_names(node, source: bytes) -> set[str]:
    names: set[str] = set()
    for child in node.children:
        if child.type == "statement_block":
            break
        if child.type in {
            "identifier",
            "object_pattern",
            "array_pattern",
        }:
            _collect_binding_identifiers(child, source, names)
    return names


def _function_var_binding_names(node, source: bytes) -> set[str]:
    names: set[str] = set()

    def visit(current, *, is_root: bool = False) -> None:
        if not is_root and current.type in _FUNCTION_SCOPE_NODE_TYPES:
            return
        if current.type == "variable_declaration":
            _collect_declaration_bindings(current, source, names)
        elif current.type in {"for_statement", "for_in_statement"}:
            names.update(_for_var_binding_names(current, source))
        for child in current.children:
            visit(child)

    visit(node, is_root=True)
    return names


def _for_var_binding_names(node, source: bytes) -> set[str]:
    names: set[str] = set()
    saw_var = False
    for child in node.children:
        if child.type in {";", "of", "in", "statement_block"}:
            break
        if child.type == "var":
            saw_var = True
            continue
        if child.type == "variable_declaration":
            _collect_declaration_bindings(child, source, names)
            return names
        if saw_var and child.type in {
            "identifier",
            "object_pattern",
            "array_pattern",
            "shorthand_property_identifier_pattern",
        }:
            _collect_binding_identifiers(child, source, names)
            return names
    return names


def _collect_declaration_bindings(node, source: bytes, names: set[str]) -> None:
    for child in node.children:
        if child.type == "variable_declarator":
            _collect_variable_declarator_binding(child, source, names)


def _collect_variable_declarator_binding(node, source: bytes, names: set[str]) -> None:
    for child in node.children:
        if child.type in {
            "identifier",
            "object_pattern",
            "array_pattern",
        }:
            _collect_binding_identifiers(child, source, names)
            return


def _collect_binding_identifiers(node, source: bytes, names: set[str]) -> None:
    if node.type in {"identifier", "shorthand_property_identifier_pattern"}:
        names.add(_text(node, source))
        return
    if node.type in {
        "required_parameter",
        "optional_parameter",
        "rest_pattern",
        "object_pattern",
        "array_pattern",
        "pair_pattern",
    }:
        for child in node.children:
            _collect_binding_identifiers(child, source, names)


class BehavioralReferenceCollector:
    """Collect import identity, references, and executable test labels."""

    def __init__(self, root: Any, source: bytes, file_path: Union[str, Path]) -> None:
        self._root = root
        self._source = source
        self._file_path = file_path
        self._artifacts: list[FoundArtifact] = []
        self._seen: set[str] = set()
        self._import_map: dict[str, dict] = {}
        self._namespace_imports: dict[str, str] = {}
        self._shadowable_import_names: set[str] = set()
        self._shadowed_import_scopes: list[set[str]] = []
        self._local_value_scopes: list[set[str]] = []
        self._type_shadow_scopes: list[set[str]] = []

    def collect(self) -> list[FoundArtifact]:
        project_root = _ts_project_root_for(self._file_path)
        importer_module = ts_file_to_module_path(self._file_path, project_root) or ""
        self._import_map, self._namespace_imports = _scan_imports(
            self._root,
            self._source,
            importer_module,
            project_root,
            self._artifacts,
            self._seen,
        )
        self._shadowable_import_names = set(self._import_map)
        self._shadowable_import_names.update(
            info["alias_of"] for info in self._import_map.values() if info["alias_of"]
        )
        self._collect_references(self._root)
        return self._artifacts

    def _collect_references(self, node) -> None:
        """Collect identifier references and executable test labels.

        Only real test-runner declarations such as ``it("name", ...)`` and
        ``test("name", ...)`` are emitted as ``ArtifactKind.TEST_FUNCTION``.
        Plain ``test_*`` helpers are treated as ordinary code references.
        """
        scope = self._shadowed_imports_for_scope(node)
        local_scope = self._local_value_bindings_for_scope(node)
        type_scope = self._type_shadowed_names_for_scope(node)
        if scope:
            self._shadowed_import_scopes.append(scope)
        if local_scope:
            self._local_value_scopes.append(local_scope)
        if type_scope:
            self._type_shadow_scopes.append(type_scope)
        try:
            # Imports were collected separately by _scan_imports; skip walking them.
            if node.type == "import_statement":
                return
            if node.type in _TYPE_ONLY_NODE_TYPES:
                self._record_type_references(node)
                return

            if node.type == "member_expression":
                self._record_member_expression(node)
            elif node.type == "pair":
                self._record_object_pair_reference(node)
            elif node.type == "subscript_expression":
                self._record_subscript_expression_reference(node)
            elif node.type == "shorthand_property_identifier":
                name = _text(node, self._source)
                if self._is_shadowed_import(name):
                    self._record_local_reference(name)
                else:
                    _record_bare_reference(name, self._artifacts)
            elif node.type == "jsx_attribute":
                self._record_jsx_attribute_reference(node)

            if node.type == "identifier":
                self._record_identifier_reference(node)
            elif node.type == "call_expression":
                self._record_test_label(node)

            for child in node.children:
                self._collect_references(child)
        finally:
            if type_scope:
                self._type_shadow_scopes.pop()
            if local_scope:
                self._local_value_scopes.pop()
            if scope:
                self._shadowed_import_scopes.pop()

    def _record_member_expression(self, node) -> None:
        root_name = _member_root_name(node, self._source)
        if root_name and (
            self._is_shadowed_import(root_name) or self._is_local_value(root_name)
        ):
            property_name = _member_property_name(node, self._source)
            if property_name:
                self._record_local_reference(property_name)
            return

        direct_object_name = _direct_member_object_name(node, self._source)
        if direct_object_name:
            import_info = self._import_map.get(direct_object_name)
            property_name = _member_property_name(node, self._source)
            if (
                import_info is not None
                and property_name
                and not import_info.get("type_only")
                and direct_object_name not in self._namespace_imports
            ):
                seen_key = (
                    f"access:{property_name}:{import_info['source']}:"
                    f"{direct_object_name}:{import_info['alias_of'] or ''}"
                )
                if seen_key not in self._seen:
                    self._seen.add(seen_key)
                    self._artifacts.append(
                        FoundArtifact(
                            kind=ArtifactKind.FUNCTION,
                            name=property_name,
                            import_source=import_info["source"] or None,
                            reference_context="access",
                        )
                    )

        resolved = _resolve_member_chain(node, self._source, self._namespace_imports)
        if resolved is not None:
            leaf, source_path = resolved
            seen_key = f"access:{leaf}:{source_path}"
            if leaf and seen_key not in self._seen:
                self._seen.add(seen_key)
                self._artifacts.append(
                    FoundArtifact(
                        kind=ArtifactKind.FUNCTION,
                        name=leaf,
                        import_source=source_path or None,
                        reference_context="access",
                    )
                )
        property_name = _member_property_name(node, self._source)
        if property_name and not any(a.name == property_name for a in self._artifacts):
            self._artifacts.append(
                FoundArtifact(
                    kind=ArtifactKind.FUNCTION,
                    name=property_name,
                    reference_context="access",
                )
            )

    def _record_object_pair_reference(self, node) -> None:
        property_name = _child_text(node, "property_identifier", self._source)
        if property_name is None:
            property_name = _child_text(node, "computed_property_name", self._source)
        if property_name:
            _record_bare_reference(property_name, self._artifacts)

    def _record_subscript_expression_reference(self, node) -> None:
        seen_open_bracket = False
        for child in node.children:
            if child.type == "[":
                seen_open_bracket = True
                continue
            if not seen_open_bracket:
                continue
            if child.type in {"identifier", "member_expression", "string", "number"}:
                _record_bare_reference(
                    f"[{_text(child, self._source)}]", self._artifacts
                )
                return
            if child.type != "]":
                return

    def _record_jsx_attribute_reference(self, node) -> None:
        property_name = _child_text(node, "property_identifier", self._source)
        if property_name:
            _record_bare_reference(property_name, self._artifacts)

    def _record_identifier_reference(self, node) -> None:
        name = _text(node, self._source)
        if not name:
            return
        if self._is_shadowed_import(name):
            self._record_local_reference(name)
            return
        if self._is_local_value(name):
            self._record_local_reference(name)
            return
        import_info = self._import_map.get(name)
        if import_info is not None:
            if import_info.get("type_only"):
                self._record_unresolved_reference(name)
                return
            seen_key = (
                f"access:{name}:{import_info['source']}:{import_info['alias_of'] or ''}"
            )
            if seen_key not in self._seen:
                self._seen.add(seen_key)
                self._artifacts.append(
                    FoundArtifact(
                        kind=ArtifactKind.FUNCTION,
                        name=name,
                        import_source=import_info["source"] or None,
                        alias_of=import_info["alias_of"],
                        reference_context="access",
                    )
                )
            return
        self._record_unresolved_reference(name)

    def _record_unresolved_reference(self, name: str) -> None:
        seen_key = f"access:{name}"
        if seen_key not in self._seen:
            self._seen.add(seen_key)
            self._artifacts.append(
                FoundArtifact(
                    kind=ArtifactKind.FUNCTION,
                    name=name,
                    reference_context="access",
                )
            )

    def _record_type_references(self, node) -> None:
        skipped_binding_name = False
        for child in node.children:
            if child.type in {"identifier", "type_identifier"}:
                if (
                    node.type
                    in {
                        "interface_declaration",
                        "type_alias_declaration",
                        "type_parameter",
                    }
                    and not skipped_binding_name
                ):
                    skipped_binding_name = True
                    continue
                self._record_type_reference(_text(child, self._source))
            else:
                self._record_type_references(child)

    def _record_type_reference(self, name: str) -> None:
        if not name:
            return
        if self._is_type_shadowed(name):
            return
        import_info = self._import_map.get(name)
        import_source = import_info["source"] if import_info is not None else None
        alias_of = import_info["alias_of"] if import_info is not None else None
        seen_key = f"type:{name}:{import_source or ''}:{alias_of or ''}"
        if seen_key in self._seen:
            return
        self._seen.add(seen_key)
        self._artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.FUNCTION,
                name=name,
                import_source=import_source or None,
                alias_of=alias_of,
                reference_context="type",
            )
        )

    def _record_local_reference(self, name: str) -> None:
        seen_key = f"local:{name}"
        if name and seen_key not in self._seen:
            self._seen.add(seen_key)
            self._artifacts.append(
                FoundArtifact(
                    kind=ArtifactKind.FUNCTION,
                    name=name,
                    reference_context="local",
                )
            )

    def _is_shadowed_import(self, name: str) -> bool:
        return any(name in scope for scope in self._shadowed_import_scopes)

    def _is_local_value(self, name: str) -> bool:
        return any(name in scope for scope in self._local_value_scopes)

    def _is_type_shadowed(self, name: str) -> bool:
        return any(name in scope for scope in self._type_shadow_scopes)

    def _shadowed_imports_for_scope(self, node) -> set[str]:
        return self._local_bindings_for_scope(node) & self._shadowable_import_names

    def _local_value_bindings_for_scope(self, node) -> set[str]:
        names: set[str] = set()
        if node.type in {"program", "statement_block"}:
            names.update(_direct_local_value_names(node, self._source))
        elif node.type in {"switch_case", "switch_default"}:
            names.update(_direct_local_value_names(node, self._source))
        return names

    def _local_bindings_for_scope(self, node) -> set[str]:
        names: set[str] = set()
        if node.type == "program":
            names.update(_direct_block_binding_names(node, self._source))
        elif node.type in _FUNCTION_SCOPE_NODE_TYPES:
            names.update(_parameter_binding_names(node, self._source))
            names.update(_function_var_binding_names(node, self._source))
        elif node.type == "statement_block":
            names.update(_direct_block_binding_names(node, self._source))
        elif node.type in {"switch_case", "switch_default"}:
            names.update(_direct_block_binding_names(node, self._source))
        elif node.type in {"for_statement", "for_in_statement", "catch_clause"}:
            names.update(_control_flow_binding_names(node, self._source))

        return names

    def _type_shadowed_names_for_scope(self, node) -> set[str]:
        names: set[str] = set()
        if node.type in {"program", "statement_block", "switch_case", "switch_default"}:
            names.update(_direct_type_binding_names(node, self._source))
        if node.type in _TYPE_PARAMETER_SCOPE_NODES:
            names.update(_type_parameter_binding_names(node, self._source))
        return names

    def _record_test_label(self, node) -> None:
        callee = _extract_test_callee_name(node, self._source)
        if callee is None:
            return
        label = _first_string_argument(node, self._source)
        if not label:
            return
        self._artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.TEST_FUNCTION,
                name=label,
                line=node.start_point[0] + 1,
            )
        )
        self._seen.add(label)


class BehavioralTestBodyCollector:
    """Extract per-test body source text keyed by test function name."""

    def __init__(self, root: Any, source: bytes) -> None:
        self._root = root
        self._source = source
        self._bodies: dict[str, str] = {}

    def collect(self) -> dict[str, str]:
        self._collect_test_bodies(self._root)
        return self._bodies

    def _collect_test_bodies(self, node) -> None:
        """Recognize executable test-runner calls and ignore nested helpers."""
        if node.type == "call_expression":
            callee = _extract_test_callee_name(node, self._source)
            if callee is not None:
                label = _first_string_argument(node, self._source)
                if label:
                    body_text = _extract_test_callback_body(node, self._source)
                    if body_text is None:
                        body_text = _text(node, self._source)
                    self._bodies.setdefault(label, body_text)
                    return

        for child in node.children:
            self._collect_test_bodies(child)


def collect_behavioral_artifacts(
    root: Any,
    source: bytes,
    file_path: Union[str, Path],
) -> list[FoundArtifact]:
    return BehavioralReferenceCollector(root, source, file_path).collect()


def collect_test_function_bodies(root: Any, source: bytes) -> dict[str, str]:
    return BehavioralTestBodyCollector(root, source).collect()


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
