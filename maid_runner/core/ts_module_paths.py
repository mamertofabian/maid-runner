"""TypeScript module path helpers for the Semantic Reference Index.

Module identity for TypeScript is path-based: project-relative POSIX
paths with the file extension stripped. This is the TS analogue of
``maid_runner.core.module_paths``, which uses dotted Python identity.

Only one-level barrel re-exports are resolved, including named
``export { Foo } from './y'``, aliased ``export { Foo as Bar } from './y'``,
star ``export * from './y'``, and default-as named
``export { default as Foo } from './y'`` forms. CommonJS ``index.cjs``
barrels support the narrow ``exports.Foo = require('./y').Foo`` form.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Union


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
    if specifier.startswith("./") or specifier.startswith("../"):
        return resolve_relative_ts_import(specifier, importer_module)

    config = _load_tsconfig(project_root)
    if config is None:
        return specifier

    compiler_options = config.get("compilerOptions")
    if not isinstance(compiler_options, dict):
        return specifier

    root = Path(project_root)
    base_url = _compiler_base_url(root, compiler_options)
    paths = compiler_options.get("paths")
    if isinstance(paths, dict):
        resolved = _resolve_paths_alias(specifier, paths, base_url, root)
        if resolved is not None:
            return resolved

    if "/" in specifier and isinstance(compiler_options.get("baseUrl"), str):
        return _project_module_from_path(base_url / specifier, root)

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
    init_path: Optional[Path] = None
    for candidate in _INDEX_CANDIDATES:
        p = Path(project_root) / module / candidate
        if p.exists():
            init_path = p
            break
    if init_path is None:
        return None

    try:
        source = init_path.read_text()
    except OSError:
        return None

    source_bytes = source.encode("utf-8")
    parser = _make_ts_barrel_parser(init_path)
    if parser is None:
        return None

    tree = parser.parse(source_bytes)
    root = tree.root_node
    if getattr(root, "has_error", False):
        return None

    for child in root.children:
        if init_path.suffix == ".cjs":
            cjs_reexport = _cjs_exports_assignment(child, source_bytes)
            if cjs_reexport is not None:
                bound, src, source_name = cjs_reexport
                if bound == name:
                    resolved = resolve_relative_ts_import(src, f"{module}/index")
                    return (resolved, source_name)

        if child.type != "export_statement":
            continue

        src = _export_source(child, source_bytes)
        if src is None:
            continue

        resolved = resolve_relative_ts_import(src, f"{module}/index")
        if _is_star_export(child):
            return (resolved, name)

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
                return (resolved, source_name)

    return None


def _load_tsconfig(project_root: Path) -> Optional[dict[str, Any]]:
    config_path = Path(project_root) / "tsconfig.json"
    try:
        data = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _compiler_base_url(project_root: Path, compiler_options: dict[str, Any]) -> Path:
    raw = compiler_options.get("baseUrl")
    if not isinstance(raw, str) or not raw:
        return project_root
    base = Path(raw)
    if base.is_absolute():
        return base
    return project_root / base


def _resolve_paths_alias(
    specifier: str,
    paths: dict[Any, Any],
    base_url: Path,
    project_root: Path,
) -> Optional[str]:
    for pattern, targets in paths.items():
        if not isinstance(pattern, str) or not isinstance(targets, list):
            continue
        capture = _match_ts_path_pattern(pattern, specifier)
        if capture is None:
            continue
        for target in targets:
            if not isinstance(target, str):
                continue
            resolved_target = target.replace("*", capture)
            return _project_module_from_path(base_url / resolved_target, project_root)
    return None


def _match_ts_path_pattern(pattern: str, specifier: str) -> Optional[str]:
    if "*" not in pattern:
        return "" if pattern == specifier else None

    prefix, suffix = pattern.split("*", 1)
    if not specifier.startswith(prefix):
        return None
    if suffix and not specifier.endswith(suffix):
        return None
    end = len(specifier) - len(suffix) if suffix else len(specifier)
    return specifier[len(prefix) : end]


def _project_module_from_path(path: Path, project_root: Path) -> str:
    return ts_file_to_module_path(path, project_root)


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


def _is_star_export(export_statement) -> bool:
    return any(child.type == "*" for child in export_statement.children)


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
