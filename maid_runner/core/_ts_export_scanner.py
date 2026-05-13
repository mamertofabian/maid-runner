"""Local TypeScript export scanner used by the module path facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from maid_runner.core._tsconfig_paths import _resolve_ts_import_from_config


_TS_EXTENSIONS: tuple[str, ...] = (
    ".tsx",
    ".ts",
    ".jsx",
    ".js",
    ".mjs",
    ".cjs",
    ".mts",
    ".cts",
    ".svelte",
)

_INDEX_CANDIDATES: tuple[str, ...] = (
    "index.ts",
    "index.tsx",
    "index.js",
    "index.jsx",
    "index.mjs",
    "index.cjs",
    "index.mts",
    "index.cts",
)


class _CompilerFallbackRequired:
    pass


_COMPILER_FALLBACK_REQUIRED = _CompilerFallbackRequired()


def resolve_reexport_source(
    module_file: Path,
    name: str,
    project_root: Path,
    seen: set[tuple[str, str]],
) -> Optional[tuple[str, str]]:
    resolved = resolve_reexport_source_or_fallback(module_file, name, project_root, seen)
    if resolved is _COMPILER_FALLBACK_REQUIRED:
        return None
    return resolved


def resolve_reexport_source_or_fallback(
    module_file: Path,
    name: str,
    project_root: Path,
    seen: set[tuple[str, str]],
) -> Optional[tuple[str, str]] | _CompilerFallbackRequired:
    return _resolve_reexport_source_or_fallback(module_file, name, project_root, seen)


def _resolve_reexport_source_or_fallback(
    module_file: Path,
    name: str,
    project_root: Path,
    seen: set[tuple[str, str]],
) -> Optional[tuple[str, str]] | _CompilerFallbackRequired:
    module = _module_id_for_entry(module_file, project_root)
    marker = (module, name)
    if marker in seen:
        return None
    seen.add(marker)

    try:
        source = module_file.read_text()
    except OSError:
        return _COMPILER_FALLBACK_REQUIRED

    source_bytes = source.encode("utf-8")
    parser = _make_ts_barrel_parser(module_file)
    if parser is None:
        return _COMPILER_FALLBACK_REQUIRED

    tree = parser.parse(source_bytes)
    root = tree.root_node
    if getattr(root, "has_error", False):
        return _COMPILER_FALLBACK_REQUIRED

    fallback_required = False
    star_candidate: Optional[tuple[str, str]] = None
    for child in root.children:
        if module_file.suffix == ".cjs":
            cjs_reexport = _cjs_exports_assignment(child, source_bytes)
            if cjs_reexport is not None:
                bound, src, source_name = cjs_reexport
                if bound == name:
                    resolved = _resolve_reexport_module(src, module_file, project_root)
                    if resolved is None:
                        fallback_required = True
                        continue
                    recursive = _resolve_module_reexport(
                        resolved, source_name, project_root, seen
                    )
                    if recursive is _COMPILER_FALLBACK_REQUIRED:
                        fallback_required = True
                        continue
                    if recursive is not None:
                        return recursive
                    direct_export = _module_directly_exports_module_name(
                        resolved, source_name, project_root
                    )
                    if direct_export is _COMPILER_FALLBACK_REQUIRED:
                        fallback_required = True
                        continue
                    if direct_export:
                        return (resolved, source_name)
                    fallback_required = True
                    continue

        if child.type != "export_statement":
            continue

        src = _export_source(child, source_bytes)
        if src is None:
            export_clause = _child_by_type(child, "export_clause")
            if export_clause is not None:
                local_names = _module_local_declaration_names(root, source_bytes)
                if _export_clause_binds_name_without_local_declaration(
                    export_clause, name, source_bytes, local_names
                ):
                    fallback_required = True
            continue

        if _is_star_export(child):
            resolved = _resolve_reexport_module(src, module_file, project_root)
            if resolved is None:
                fallback_required = True
                continue
            recursive = _resolve_module_reexport(resolved, name, project_root, seen)
            if recursive is _COMPILER_FALLBACK_REQUIRED:
                fallback_required = True
                continue
            if recursive is not None:
                if star_candidate is None:
                    star_candidate = recursive
                    continue
                if star_candidate != recursive:
                    fallback_required = True
                continue
            direct_export = _module_directly_exports_module_name(
                resolved, name, project_root
            )
            if direct_export is _COMPILER_FALLBACK_REQUIRED:
                fallback_required = True
                continue
            if direct_export:
                candidate = (resolved, name)
                if star_candidate is None:
                    star_candidate = candidate
                    continue
                if star_candidate != candidate:
                    fallback_required = True
                continue
            continue

        export_clause = _child_by_type(child, "export_clause")
        if export_clause is None:
            continue

        for specifier in export_clause.children:
            if specifier.type != "export_specifier":
                continue
            for source_name, bound in export_specifier_names(specifier, source_bytes):
                if bound == name:
                    source_is_default = _export_specifier_source_is_default(
                        specifier, source_bytes
                    )
                    resolved = _resolve_reexport_module(src, module_file, project_root)
                    if resolved is None:
                        fallback_required = True
                        continue
                    recursive = _resolve_module_reexport(
                        resolved, source_name, project_root, seen
                    )
                    if recursive is _COMPILER_FALLBACK_REQUIRED:
                        fallback_required = True
                        continue
                    if recursive is not None:
                        return recursive
                    direct_export = _module_directly_exports_reexport_source(
                        resolved,
                        source_name,
                        project_root,
                        source_is_default=source_is_default,
                    )
                    if direct_export is _COMPILER_FALLBACK_REQUIRED:
                        fallback_required = True
                        continue
                    if direct_export:
                        return (resolved, source_name)
                    fallback_required = True
                    continue

    if fallback_required:
        return _COMPILER_FALLBACK_REQUIRED
    if star_candidate is not None:
        return star_candidate
    return None


def module_directly_exports_name(
    module_file: Path,
    name: str,
) -> bool:
    return _module_directly_exports_name_or_fallback(module_file, name) is True


def _module_directly_exports_name_or_fallback(
    module_file: Path,
    name: str,
):
    try:
        source = module_file.read_text()
    except OSError:
        return _COMPILER_FALLBACK_REQUIRED

    source_bytes = source.encode("utf-8")
    parser = _make_ts_barrel_parser(module_file)
    if parser is None:
        return _COMPILER_FALLBACK_REQUIRED

    tree = parser.parse(source_bytes)
    root = tree.root_node
    if getattr(root, "has_error", False):
        return _COMPILER_FALLBACK_REQUIRED

    if module_file.suffix == ".cjs":
        return any(
            (direct_name := _cjs_direct_export_name(child, source_bytes)) is not None
            and direct_name == name
            for child in root.children
        )

    local_names = _module_local_declaration_names(root, source_bytes)
    return any(
        child.type == "export_statement"
        and _direct_export_statement_exports_name(
            child, name, source_bytes, local_names
        )
        for child in root.children
    )


def export_specifier_names(
    export_specifier: Any,
    source: bytes,
) -> list[tuple[str, str]]:
    identifiers = [
        _text(child, source)
        for child in export_specifier.children
        if child.type == "identifier"
    ]
    if not identifiers:
        return []
    if len(identifiers) >= 2:
        if identifiers[0] == "default":
            return [(identifiers[1], identifiers[1])]
        return [(identifiers[0], identifiers[1])]
    return [(identifiers[0], identifiers[0])]


def _resolve_module_reexport(
    module: str,
    name: str,
    project_root: Path,
    seen: set[tuple[str, str]],
):
    entry = _module_entry_file(project_root, module)
    if entry is None:
        return None
    module_file, _ = entry
    return _resolve_reexport_source_or_fallback(module_file, name, project_root, seen)


def _resolve_reexport_module(
    specifier: str,
    module_file: Path,
    project_root: Path,
) -> Optional[str]:
    if specifier.startswith("./") or specifier.startswith("../"):
        return _resolve_relative_ts_import(specifier, _module_path(module_file, project_root))
    return _resolve_ts_import_from_config(specifier, project_root)


def _module_directly_exports_module_name(
    module: str,
    name: str,
    project_root: Path,
) -> bool | _CompilerFallbackRequired:
    entry = _module_entry_file(project_root, module)
    if entry is None:
        return _COMPILER_FALLBACK_REQUIRED
    source_path, _ = entry
    return _module_directly_exports_name_or_fallback(source_path, name)


def _module_directly_exports_reexport_source(
    module: str,
    source_name: str,
    project_root: Path,
    *,
    source_is_default: bool,
) -> bool | _CompilerFallbackRequired:
    if source_is_default:
        return _module_directly_exports_default(module, project_root)
    return _module_directly_exports_module_name(module, source_name, project_root)


def _module_directly_exports_default(
    module: str,
    project_root: Path,
) -> bool | _CompilerFallbackRequired:
    entry = _module_entry_file(project_root, module)
    if entry is None:
        return _COMPILER_FALLBACK_REQUIRED
    source_path, _ = entry

    try:
        source = source_path.read_text()
    except OSError:
        return _COMPILER_FALLBACK_REQUIRED

    source_bytes = source.encode("utf-8")
    parser = _make_ts_barrel_parser(source_path)
    if parser is None:
        return _COMPILER_FALLBACK_REQUIRED

    tree = parser.parse(source_bytes)
    root = tree.root_node
    if getattr(root, "has_error", False):
        return _COMPILER_FALLBACK_REQUIRED

    return any(
        child.type == "export_statement"
        and _export_source(child, source_bytes) is None
        and any(grandchild.type == "default" for grandchild in child.children)
        for child in root.children
    )


def _module_entry_file(
    project_root: Path,
    module: str,
) -> Optional[tuple[Path, str]]:
    source_file = _existing_module_file(project_root, module)
    if source_file is not None:
        return source_file, module

    importer_module = f"{module}/index"
    for candidate in _INDEX_CANDIDATES:
        path = project_root / module / candidate
        if path.exists():
            return path, importer_module

    return None


def _existing_module_file(project_root: Path, module: str) -> Optional[Path]:
    base = project_root / module
    for extension in _TS_EXTENSIONS:
        candidate = Path(f"{base}{extension}")
        if candidate.exists():
            return candidate
    return None


def _module_id_for_entry(module_file: Path, project_root: Path) -> str:
    module_path = _module_path(module_file, project_root)
    if Path(module_path).name == "index":
        return str(Path(module_path).parent).replace("\\", "/")
    return module_path


def _module_path(module_file: Path, project_root: Path) -> str:
    try:
        relative = module_file.relative_to(project_root)
    except ValueError:
        relative = module_file
    posix = str(relative).replace("\\", "/")
    for ext in _TS_EXTENSIONS:
        if posix.endswith(ext):
            return posix[: -len(ext)]
    return posix


def _resolve_relative_ts_import(
    specifier: str,
    importer_module: str,
) -> str:
    specifier = specifier.rstrip("/")
    importer_parts = importer_module.split("/") if importer_module else []
    base_parts = importer_parts[:-1]

    for part in specifier.split("/"):
        if part == "" or part == ".":
            continue
        if part == "..":
            if base_parts:
                base_parts = base_parts[:-1]
            continue
        base_parts.append(part)

    result = "/".join(base_parts)
    for ext in _TS_EXTENSIONS:
        if result.endswith(ext):
            result = result[: -len(ext)]
            break
    return result


def _make_ts_barrel_parser(index_path: Path):
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_typescript as ts_ts
    except ImportError:
        return None

    if index_path.suffix in (".tsx", ".jsx"):
        language = Language(ts_ts.language_tsx())
    else:
        language = Language(ts_ts.language_typescript())
    return Parser(language)


def _direct_export_statement_exports_name(
    export_statement,
    name: str,
    source: bytes,
    local_names: set[str],
) -> bool:
    if _export_source(export_statement, source) is not None:
        return False

    export_clause = _child_by_type(export_statement, "export_clause")
    if export_clause is not None:
        return any(
            specifier.type == "export_specifier"
            and any(
                bound == name and source_name in local_names
                for source_name, bound in export_specifier_names(specifier, source)
            )
            for specifier in export_clause.children
        )

    if any(child.type == "default" for child in export_statement.children):
        return False

    return any(
        _exported_declaration_exports_name(child, name, source)
        for child in export_statement.children
    )


def _export_clause_binds_name_without_local_declaration(
    export_clause,
    name: str,
    source: bytes,
    local_names: set[str],
) -> bool:
    for specifier in export_clause.children:
        if specifier.type != "export_specifier":
            continue
        for source_name, bound in export_specifier_names(specifier, source):
            if bound == name and source_name not in local_names:
                return True
    return False


def _module_local_declaration_names(root, source: bytes) -> set[str]:
    names: set[str] = set()
    for child in root.children:
        if child.type == "import_statement":
            continue
        if child.type == "export_statement":
            if _export_source(child, source) is not None:
                continue
            if any(grandchild.type == "default" for grandchild in child.children):
                continue
            for grandchild in child.children:
                names.update(_local_declaration_names(grandchild, source))
            continue
        names.update(_local_declaration_names(child, source))
    return names


def _local_declaration_names(node, source: bytes) -> set[str]:
    if node.type in (
        "class_declaration",
        "abstract_class_declaration",
        "function_declaration",
        "generator_function_declaration",
        "interface_declaration",
        "type_alias_declaration",
        "enum_declaration",
        "internal_module",
    ):
        name = _declaration_name(node, source)
        return {name} if name else set()

    if node.type in ("lexical_declaration", "variable_declaration"):
        return {
            name
            for child in node.children
            if child.type == "variable_declarator"
            if (name := _child_text(child, "identifier", source)) is not None
        }

    return set()


def _exported_declaration_exports_name(node, name: str, source: bytes) -> bool:
    if node.type in (
        "class_declaration",
        "abstract_class_declaration",
        "function_declaration",
        "generator_function_declaration",
        "interface_declaration",
        "type_alias_declaration",
        "enum_declaration",
        "internal_module",
    ):
        return _declaration_name(node, source) == name

    if node.type in ("lexical_declaration", "variable_declaration"):
        return any(
            child.type == "variable_declarator"
            and _child_text(child, "identifier", source) == name
            for child in node.children
        )

    return False


def _declaration_name(node, source: bytes) -> Optional[str]:
    return _child_text(node, "type_identifier", source) or _child_text(
        node, "identifier", source
    )


def _is_star_export(export_statement) -> bool:
    return any(child.type == "*" for child in export_statement.children)


def _cjs_direct_export_name(statement, source: bytes) -> Optional[str]:
    if statement.type != "expression_statement":
        return None

    assignment = _child_by_type(statement, "assignment_expression")
    if assignment is None:
        return None

    members = [
        child for child in assignment.children if child.type == "member_expression"
    ]
    if not members:
        return None

    return _exports_member_name(members[0], source)


def _cjs_exports_assignment(statement, source: bytes) -> Optional[tuple[str, str, str]]:
    if statement.type != "expression_statement":
        return None

    assignment = _child_by_type(statement, "assignment_expression")
    if assignment is None:
        return None

    members = [
        child for child in assignment.children if child.type == "member_expression"
    ]
    if len(members) < 2:
        return None

    bound = _exports_member_name(members[0], source)
    required = _require_member_source(members[1], source)
    if bound is None or required is None:
        return None

    src, source_name = required
    return bound, src, source_name


def _exports_member_name(member_expression, source: bytes) -> Optional[str]:
    children = member_expression.children
    if not children or children[0].type != "identifier":
        return None
    if _text(children[0], source) != "exports":
        return None

    property_node = _child_by_type(member_expression, "property_identifier")
    if property_node is None:
        return None
    return _text(property_node, source)


def _require_member_source(
    member_expression,
    source: bytes,
) -> Optional[tuple[str, str]]:
    call = _child_by_type(member_expression, "call_expression")
    property_node = _child_by_type(member_expression, "property_identifier")
    if call is None or property_node is None:
        return None

    callee = next(
        (child for child in call.children if child.type == "identifier"), None
    )
    if callee is None or _text(callee, source) != "require":
        return None

    arguments = _child_by_type(call, "arguments")
    if arguments is None:
        return None
    string_node = _child_by_type(arguments, "string")
    if string_node is None:
        return None
    fragment = _child_by_type(string_node, "string_fragment")
    if fragment is None:
        return None

    return _text(fragment, source), _text(property_node, source)


def _export_specifier_source_is_default(export_specifier, source: bytes) -> bool:
    identifiers = [
        _text(child, source)
        for child in export_specifier.children
        if child.type == "identifier"
    ]
    return bool(identifiers and identifiers[0] == "default")


def _export_source(export_statement, source: bytes) -> Optional[str]:
    string_node = _child_by_type(export_statement, "string")
    if string_node is None:
        return None
    fragment = _child_by_type(string_node, "string_fragment")
    if fragment is None:
        return None
    return _text(fragment, source)


def _child_text(node, child_type: str, source: bytes) -> Optional[str]:
    child = _child_by_type(node, child_type)
    if child is None:
        return None
    return _text(child, source)


def _child_by_type(node, child_type: str):
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8")
