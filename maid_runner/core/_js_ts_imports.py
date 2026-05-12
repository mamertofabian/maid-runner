"""JavaScript and TypeScript import collection for required-import checks."""

from __future__ import annotations

import re
from typing import Optional


def collect_required_imports(source: str, file_path: str) -> set[str]:
    """Collect TS/JS import modules and bindings for required-import checks."""
    parsed = _collect_required_imports_with_tree_sitter(source, file_path)
    if parsed is not None:
        return parsed
    return _collect_required_imports_with_text(source)


def collect_import_modules(source: str, file_path: str) -> set[str]:
    """Collect raw TS/JS module specifiers for path resolution."""
    parsed = _collect_import_modules_with_tree_sitter(source, file_path)
    if parsed is not None:
        return parsed
    return _collect_import_modules_with_text(source)


def collect_import_module_bindings(
    source: str,
    file_path: str,
) -> dict[str, set[str]]:
    """Collect imported binding names by raw TS/JS module specifier."""
    parsed = _collect_import_module_bindings_with_tree_sitter(source, file_path)
    if parsed is not None:
        return parsed
    return _collect_import_module_bindings_with_text(source)


def import_may_satisfy_required(
    specifier: str,
    unresolved_required_imports: set[str],
    bindings: set[str],
) -> bool:
    identity_parts = _specifier_identity_parts(specifier) | bindings
    if not identity_parts:
        return False

    for required in unresolved_required_imports:
        required_parts = {part for part in required.split("/") if part}
        if identity_parts & required_parts:
            return True
    return False


def _specifier_identity_parts(specifier: str) -> set[str]:
    parts = [part for part in specifier.strip("/").split("/") if part]
    if not parts:
        return set()
    if parts[0].startswith("@"):
        parts = parts[1:]
    if parts and parts[0] in {"@", "#"}:
        parts = parts[1:]
    cleaned: set[str] = set()
    for part in parts:
        stripped = part.lstrip("@#")
        if stripped:
            cleaned.add(stripped)
    return cleaned


def _collect_required_imports_with_tree_sitter(
    source: str, file_path: str
) -> Optional[set[str]]:
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_typescript as ts_ts
    except ImportError:
        return None

    if file_path.endswith((".tsx", ".jsx")):
        language = Language(ts_ts.language_tsx())
    elif file_path.endswith((".ts", ".js", ".mjs", ".cjs", ".mts", ".cts")):
        language = Language(ts_ts.language_typescript())
    else:
        return None

    source_bytes = source.encode("utf-8")
    tree = Parser(language).parse(source_bytes)
    if getattr(tree.root_node, "has_error", False):
        return None

    found: set[str] = set()
    _collect_import_nodes(tree.root_node, source_bytes, found)
    return found


def _collect_import_modules_with_tree_sitter(
    source: str, file_path: str
) -> Optional[set[str]]:
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_typescript as ts_ts
    except ImportError:
        return None

    if file_path.endswith((".tsx", ".jsx")):
        language = Language(ts_ts.language_tsx())
    elif file_path.endswith((".ts", ".js", ".mjs", ".cjs", ".mts", ".cts")):
        language = Language(ts_ts.language_typescript())
    else:
        return None

    source_bytes = source.encode("utf-8")
    tree = Parser(language).parse(source_bytes)
    if getattr(tree.root_node, "has_error", False):
        return None

    found: set[str] = set()
    _collect_import_nodes(tree.root_node, source_bytes, found, include_bindings=False)
    return found


def _collect_import_module_bindings_with_tree_sitter(
    source: str,
    file_path: str,
) -> Optional[dict[str, set[str]]]:
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_typescript as ts_ts
    except ImportError:
        return None

    if file_path.endswith((".tsx", ".jsx")):
        language = Language(ts_ts.language_tsx())
    elif file_path.endswith((".ts", ".js", ".mjs", ".cjs", ".mts", ".cts")):
        language = Language(ts_ts.language_typescript())
    else:
        return None

    source_bytes = source.encode("utf-8")
    tree = Parser(language).parse(source_bytes)
    if getattr(tree.root_node, "has_error", False):
        return None

    found: dict[str, set[str]] = {}
    _collect_import_binding_nodes(tree.root_node, source_bytes, found)
    return found


def _collect_required_imports_with_text(source: str) -> set[str]:
    found: set[str] = set()

    for match in re.finditer(
        r"""(?:import|export)\s+.*?from\s+['"](.+?)['"]""", source
    ):
        found.add(match.group(1))
    for match in re.finditer(r"""import\s+['"](.+?)['"]""", source):
        found.add(match.group(1))
    for match in re.finditer(
        r"""(?:import|export)\s+\{([^}]+)\}\s+from\s+['"](.+?)['"]""", source
    ):
        names = match.group(1)
        module = match.group(2)
        found.add(module)
        for name in names.split(","):
            parts = [part.strip() for part in name.split(" as ", 1)]
            for part in parts:
                if part:
                    found.add(part)
    for match in re.finditer(
        r"""import\s+\*\s+as\s+(\w+)\s+from\s+['"](.+?)['"]""", source
    ):
        found.add(match.group(1))
        found.add(match.group(2))
    for match in re.finditer(r"""require\s*\(\s*['"](.+?)['"]\s*\)""", source):
        found.add(match.group(1))
    for match in re.finditer(r"""require\.resolve\s*\(\s*['"](.+?)['"]\s*\)""", source):
        found.add(match.group(1))
    for match in re.finditer(r"""import\s*\(\s*['"](.+?)['"]\s*\)""", source):
        found.add(match.group(1))

    return found


def _collect_import_modules_with_text(source: str) -> set[str]:
    found: set[str] = set()

    for match in re.finditer(
        r"""(?:import|export)\s+.*?from\s+['"](.+?)['"]""", source
    ):
        found.add(match.group(1))
    for match in re.finditer(
        r"""(?:import|export)(?:\s+type)?\s+\{[^}]+\}\s+from\s+['"](.+?)['"]""",
        source,
        re.DOTALL,
    ):
        found.add(match.group(1))
    for match in re.finditer(r"""import\s+['"](.+?)['"]""", source):
        found.add(match.group(1))
    for match in re.finditer(r"""require\s*\(\s*['"](.+?)['"]\s*\)""", source):
        found.add(match.group(1))
    for match in re.finditer(r"""require\.resolve\s*\(\s*['"](.+?)['"]\s*\)""", source):
        found.add(match.group(1))
    for match in re.finditer(r"""import\s*\(\s*['"](.+?)['"]\s*\)""", source):
        found.add(match.group(1))

    return found


def _collect_import_module_bindings_with_text(source: str) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}

    for match in re.finditer(
        r"""(?:import|export)(?:\s+type)?\s+\{([^}]+)\}\s+from\s+['"](.+?)['"]""",
        source,
        re.DOTALL,
    ):
        names = match.group(1)
        module = match.group(2)
        bindings = found.setdefault(module, set())
        for name in names.split(","):
            source_name = name.split(" as ", 1)[0].removeprefix("type ").strip()
            if source_name:
                bindings.add(source_name)

    for match in re.finditer(r"""import\s+(\w+)\s+from\s+['"](.+?)['"]""", source):
        found.setdefault(match.group(2), set()).add(match.group(1))

    for match in re.finditer(
        r"""import\s+\*\s+as\s+(\w+)\s+from\s+['"](.+?)['"]""", source
    ):
        found.setdefault(match.group(2), set()).add(match.group(1))

    return found


def _collect_import_nodes(
    node,
    source: bytes,
    found: set[str],
    *,
    include_bindings: bool = True,
) -> None:
    if node.type == "import_statement":
        module = _statement_source(node, source)
        if module:
            found.add(module)
        if include_bindings:
            _collect_import_bindings(node, source, found)
        return

    if node.type == "export_statement":
        module = _statement_source(node, source)
        if module:
            found.add(module)
            if include_bindings:
                _collect_import_bindings(node, source, found)
            return

    if node.type == "call_expression":
        module = _call_import_source(node, source)
        if module:
            found.add(module)

    for child in node.children:
        _collect_import_nodes(child, source, found, include_bindings=include_bindings)


def _collect_import_binding_nodes(
    node,
    source: bytes,
    found: dict[str, set[str]],
) -> None:
    if node.type in {"import_statement", "export_statement"}:
        module = _statement_source(node, source)
        if module:
            bindings: set[str] = set()
            _collect_import_source_bindings(node, source, bindings)
            if bindings:
                found.setdefault(module, set()).update(bindings)
            return

    for child in node.children:
        _collect_import_binding_nodes(child, source, found)


def _collect_import_bindings(node, source: bytes, found: set[str]) -> None:
    stack = list(node.children)
    while stack:
        current = stack.pop()
        if current.type in ("import_specifier", "export_specifier"):
            identifiers = _named_child_texts(current, source)
            for identifier in identifiers:
                found.add(identifier)
            continue
        if current.type == "namespace_import":
            identifier = _first_named_child_text(current, source)
            if identifier:
                found.add(identifier)
            continue
        if current.type == "import_clause":
            for child in current.children:
                if child.type == "identifier":
                    found.add(_text(child, source))
        stack.extend(reversed(current.children))


def _collect_import_source_bindings(
    node,
    source: bytes,
    found: set[str],
) -> None:
    stack = list(node.children)
    while stack:
        current = stack.pop()
        if current.type in ("import_specifier", "export_specifier"):
            binding = _source_binding_name(current, source)
            if binding:
                found.add(binding)
            continue
        if current.type == "namespace_import":
            binding = _first_named_child_text(current, source)
            if binding:
                found.add(binding)
            continue
        if current.type == "import_clause":
            for child in current.children:
                if child.type == "identifier":
                    found.add(_text(child, source))
        stack.extend(reversed(current.children))


def _source_binding_name(node, source: bytes) -> Optional[str]:
    text = _text(node, source).strip()
    if not text:
        return None
    text = text.removeprefix("type ").strip()
    if " as " in text:
        text = text.split(" as ", 1)[0].strip()
    if text.startswith("{") or text.endswith("}"):
        return None
    return text or None


def _statement_source(node, source: bytes) -> Optional[str]:
    string_node = _child_by_field_name(node, "source")
    if string_node is None:
        string_node = _child_by_type(node, "string")
    if string_node is None:
        return None
    return _string_fragment(string_node, source)


def _call_import_source(node, source: bytes) -> Optional[str]:
    function_node = _child_by_field_name(node, "function")
    if function_node is None:
        return None

    is_import_call = function_node.type == "import"
    is_require_call = (
        function_node.type == "identifier" and _text(function_node, source) == "require"
    )
    is_require_resolve_call = _is_require_resolve(function_node, source)
    if not (is_import_call or is_require_call or is_require_resolve_call):
        return None

    arguments = _child_by_field_name(node, "arguments")
    if arguments is None:
        arguments = _child_by_type(node, "arguments")
    if arguments is None:
        return None

    for child in arguments.children:
        if child.type == "string":
            return _string_fragment(child, source)
        if child.type in ("(", ","):
            continue
        return None
    return None


def _is_require_resolve(node, source: bytes) -> bool:
    if node.type != "member_expression":
        return False
    object_node = _child_by_field_name(node, "object")
    property_node = _child_by_field_name(node, "property")
    if object_node is None or property_node is None:
        for child in node.children:
            if child.type == "identifier":
                object_node = child
            elif child.type == "property_identifier":
                property_node = child
    return (
        object_node is not None
        and property_node is not None
        and _text(object_node, source) == "require"
        and _text(property_node, source) == "resolve"
    )


def _child_by_field_name(node, field_name: str):
    try:
        return node.child_by_field_name(field_name)
    except (AttributeError, TypeError):
        return None


def _child_by_type(node, child_type: str):
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _named_child_texts(node, source: bytes) -> list[str]:
    names: list[str] = []
    for child in node.children:
        if child.type in ("identifier", "type_identifier"):
            names.append(_text(child, source))
    return names


def _first_named_child_text(node, source: bytes) -> Optional[str]:
    names = _named_child_texts(node, source)
    return names[0] if names else None


def _string_fragment(node, source: bytes) -> Optional[str]:
    fragment = _child_by_type(node, "string_fragment")
    if fragment is not None:
        return _text(fragment, source)
    text = _text(node, source)
    if len(text) >= 2 and text[0] in ("'", '"') and text[-1] == text[0]:
        return text[1:-1]
    return None


def _text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8")
