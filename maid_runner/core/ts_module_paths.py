"""TypeScript module path helpers for the Semantic Reference Index.

Module identity for TypeScript is path-based: project-relative POSIX
paths with the file extension stripped. This is the TS analogue of
``maid_runner.core.module_paths``, which uses dotted Python identity.

Barrel re-exports are resolved through supported index files, including named
``export { Foo } from './y'``, aliased ``export { Foo as Bar } from './y'``,
star ``export * from './y'``, and default-as named
``export { default as Foo } from './y'`` forms. Static re-export chains are
followed when they can be parsed locally. CommonJS ``index.cjs`` barrels
support the narrow ``exports.Foo = require('./y').Foo`` form.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from maid_runner.core._tsconfig_paths import _resolve_ts_import_from_config
from maid_runner.core.ts_compiler_resolver import (
    resolve_import_with_compiler,
    resolve_reexport_with_compiler,
)


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

_NODE_BUILTIN_MODULES = frozenset(
    {
        "assert",
        "buffer",
        "child_process",
        "cluster",
        "crypto",
        "dns",
        "events",
        "fs",
        "http",
        "http2",
        "https",
        "module",
        "net",
        "os",
        "path",
        "process",
        "querystring",
        "readline",
        "stream",
        "string_decoder",
        "timers",
        "tls",
        "tty",
        "url",
        "util",
        "vm",
        "worker_threads",
        "zlib",
    }
)


class _CompilerFallbackRequired:
    pass


_COMPILER_FALLBACK_REQUIRED = _CompilerFallbackRequired()


def ts_file_to_module_path(
    file_path: Union[str, Path],
    project_root: Path,
) -> str:
    """Convert a TypeScript source path to its project-relative module id.

    Strips the file extension (``.ts``, ``.tsx``, ``.cts``, ``.mts``,
    ``.js``, ``.jsx``, ``.mjs``, ``.cjs``) and normalizes backslashes to
    forward slashes.
    Unlike Python's ``__init__.py`` collapse, ``index.ts`` keeps its
    ``index`` segment so the file itself can be addressed; barrel
    semantics live in :func:`resolve_ts_reexport`.
    """
    p = Path(file_path)
    root = Path(project_root)

    if p.is_absolute():
        try:
            rel = p.relative_to(root)
        except ValueError:
            rel = p
    else:
        rel = p

    posix = str(rel).replace("\\", "/")
    for ext in _TS_EXTENSIONS:
        if posix.endswith(ext):
            posix = posix[: -len(ext)]
            break
    return posix


def resolve_relative_ts_import(
    specifier: str,
    importer_module: str,
) -> str:
    """Resolve a ``./x`` or ``../y/z`` specifier against the importer.

    ``importer_module`` is expected to be an extensionless POSIX module
    path (e.g. ``src/models/index``). Non-relative specifiers — bare
    package names, scoped names, and absolute-style paths — pass
    through unchanged because tsconfig path aliases are out of scope.
    """
    if not (specifier.startswith("./") or specifier.startswith("../")):
        return specifier

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


def resolve_ts_import(
    specifier: str,
    importer_module: str,
    project_root: Path,
) -> str:
    """Resolve a TypeScript import specifier to MAID module identity.

    Relative imports use the existing path resolver. Non-relative imports may
    resolve through local ``tsconfig.json`` ``compilerOptions.paths`` or
    ``baseUrl``. Unmatched specifiers pass through unchanged.
    """
    root = Path(project_root)

    if specifier.startswith("./") or specifier.startswith("../"):
        return resolve_relative_ts_import(specifier, importer_module)

    local_resolved = _resolve_ts_import_from_config(
        specifier,
        root,
        allow_speculative_missing=not _module_exists(root, importer_module),
    )
    if local_resolved is not None:
        return local_resolved

    if _is_node_builtin_specifier(specifier) or _is_installed_external_package(
        specifier, root
    ):
        return specifier

    compiler_resolved = resolve_import_with_compiler(specifier, importer_module, root)
    if compiler_resolved is not None:
        return compiler_resolved

    return specifier


def resolve_ts_reexport(
    module: str,
    name: str,
    project_root: Path,
) -> Optional[tuple[str, str]]:
    """Resolve a one-level named re-export of ``name`` from ``module``.

    Looks for a supported ``<module>/index`` file and scans its top-level
    re-export statements such as ``export { Foo } from './y'``,
    ``export { Foo as Bar } from './y'``, ``export type { Foo } from './y'``,
    ``export { type Foo } from './y'``, ``export * from './y'``, and
    ``export { default as Foo } from './y'``. For ``index.cjs``, also scans
    ``exports.Foo = require('./y').Foo`` assignments. Returns
    ``(resolved_module, original_name)`` where ``original_name`` is the
    MAID-visible source identifier — for plain, star, default-as, and CJS
    assignments it equals ``name``; for aliased named re-exports looked up by
    alias it is the pre-alias name. Returns ``None`` when the module is not a
    barrel package, the file cannot be read or parsed, optional parser
    dependencies are unavailable, or ``name`` is not re-exported.
    """
    root = Path(project_root)

    local_resolved = _resolve_ts_reexport_local(module, name, root, seen=set())
    if local_resolved is _COMPILER_FALLBACK_REQUIRED:
        local_resolved = None
    elif _module_entry_file(root, module) is not None:
        if local_resolved is not None:
            return local_resolved
        return None

    if local_resolved is not None:
        return local_resolved

    if _is_external_module_id(module, root):
        return None

    compiler_resolved = resolve_reexport_with_compiler(module, name, root)
    if compiler_resolved is not None:
        return compiler_resolved

    return None


def _resolve_ts_reexport_local(
    module: str,
    name: str,
    project_root: Path,
    *,
    seen: set[tuple[str, str]],
) -> Optional[tuple[str, str]] | _CompilerFallbackRequired:
    marker = (module, name)
    if marker in seen:
        return None
    seen.add(marker)

    entry = _module_entry_file(project_root, module)
    if entry is None:
        return None
    init_path, importer_module = entry

    try:
        source = init_path.read_text()
    except OSError:
        return _COMPILER_FALLBACK_REQUIRED

    source_bytes = source.encode("utf-8")
    parser = _make_ts_barrel_parser(init_path)
    if parser is None:
        return _COMPILER_FALLBACK_REQUIRED

    tree = parser.parse(source_bytes)
    root = tree.root_node
    if getattr(root, "has_error", False):
        return _COMPILER_FALLBACK_REQUIRED

    fallback_required = False
    star_candidate: Optional[tuple[str, str]] = None
    for child in root.children:
        if init_path.suffix == ".cjs":
            cjs_reexport = _cjs_exports_assignment(child, source_bytes)
            if cjs_reexport is not None:
                bound, src, source_name = cjs_reexport
                if bound == name:
                    resolved = _resolve_reexport_source(
                        src, importer_module, project_root
                    )
                    if resolved is None:
                        fallback_required = True
                        continue
                    recursive = _resolve_ts_reexport_local(
                        resolved, source_name, project_root, seen=seen
                    )
                    if recursive is _COMPILER_FALLBACK_REQUIRED:
                        fallback_required = True
                        continue
                    if recursive is not None:
                        return recursive
                    direct_export = _module_directly_exports_name(
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
            resolved = _resolve_reexport_source(src, importer_module, project_root)
            if resolved is None:
                fallback_required = True
                continue
            recursive = _resolve_ts_reexport_local(
                resolved, name, project_root, seen=seen
            )
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
            direct_export = _module_directly_exports_name(
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
            resolved_name = _export_specifier_names(specifier, source_bytes)
            if resolved_name is None:
                continue
            source_name, bound = resolved_name
            if bound == name:
                source_is_default = _export_specifier_source_is_default(
                    specifier, source_bytes
                )
                resolved = _resolve_reexport_source(src, importer_module, project_root)
                if resolved is None:
                    fallback_required = True
                    continue
                recursive = _resolve_ts_reexport_local(
                    resolved, source_name, project_root, seen=seen
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


def _resolve_reexport_source(
    specifier: str,
    importer_module: str,
    project_root: Path,
) -> Optional[str]:
    if specifier.startswith("./") or specifier.startswith("../"):
        return resolve_relative_ts_import(specifier, importer_module)
    return _resolve_ts_import_from_config(specifier, project_root)


def _module_directly_exports_name(
    module: str,
    name: str,
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

    if source_path.suffix == ".cjs":
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


def _module_directly_exports_reexport_source(
    module: str,
    source_name: str,
    project_root: Path,
    *,
    source_is_default: bool,
) -> bool | _CompilerFallbackRequired:
    if source_is_default:
        return _module_directly_exports_default(module, project_root)
    return _module_directly_exports_name(module, source_name, project_root)


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
            and (
                resolved_name := _export_specifier_names(specifier, source)
            )
            is not None
            and resolved_name[1] == name
            and resolved_name[0] in local_names
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
        resolved_name = _export_specifier_names(specifier, source)
        if resolved_name is None:
            continue
        source_name, bound = resolved_name
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


def _is_node_builtin_specifier(specifier: str) -> bool:
    if specifier.startswith("node:"):
        return True
    package_name = specifier.split("/", 1)[0]
    return package_name in _NODE_BUILTIN_MODULES


def _is_installed_external_package(specifier: str, project_root: Path) -> bool:
    package_name = _package_name_from_specifier(specifier)
    if package_name is None:
        return False

    package_dir = project_root / "node_modules" / Path(package_name)
    if not package_dir.exists():
        return False

    real_package_dir = package_dir.resolve()
    try:
        real_relative = real_package_dir.relative_to(project_root.resolve())
    except ValueError:
        return True

    return "node_modules" in real_relative.parts


def _package_name_from_specifier(specifier: str) -> Optional[str]:
    if not specifier or specifier.startswith((".", "/")):
        return None
    parts = specifier.split("/")
    if parts[0].startswith("@"):
        if len(parts) < 2 or not parts[1]:
            return None
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


def _is_external_module_id(module: str, project_root: Path) -> bool:
    if _is_node_builtin_specifier(module):
        return True
    package_name = _package_name_from_specifier(module)
    if package_name is None:
        return False
    first_segment = package_name.split("/", 1)[0]
    return not (project_root / first_segment).exists()


def _existing_module_file(project_root: Path, module: str) -> Optional[Path]:
    base = project_root / module
    for extension in _TS_EXTENSIONS:
        candidate = Path(f"{base}{extension}")
        if candidate.exists():
            return candidate
    return None


def _module_exists(project_root: Path, module: str) -> bool:
    return _module_entry_file(project_root, module) is not None


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


def _is_index_module_id(module: str) -> bool:
    return Path(module).name == "index"


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


def _text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8")


def _child_by_type(node, child_type: str):
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _child_text(node, child_type: str, source: bytes) -> Optional[str]:
    child = _child_by_type(node, child_type)
    if child is None:
        return None
    return _text(child, source)


def _export_source(export_statement, source: bytes) -> Optional[str]:
    string_node = _child_by_type(export_statement, "string")
    if string_node is None:
        return None
    fragment = _child_by_type(string_node, "string_fragment")
    if fragment is None:
        return None
    return _text(fragment, source)


def _export_specifier_names(
    export_specifier,
    source: bytes,
) -> Optional[tuple[str, str]]:
    identifiers = [
        _text(child, source)
        for child in export_specifier.children
        if child.type == "identifier"
    ]
    if not identifiers:
        return None
    if len(identifiers) >= 2:
        if identifiers[0] == "default":
            return identifiers[1], identifiers[1]
        return identifiers[0], identifiers[1]
    return identifiers[0], identifiers[0]


def _export_specifier_source_is_default(export_specifier, source: bytes) -> bool:
    identifiers = [
        _text(child, source)
        for child in export_specifier.children
        if child.type == "identifier"
    ]
    return bool(identifiers and identifiers[0] == "default")


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
