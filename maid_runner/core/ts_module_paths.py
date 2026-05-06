"""TypeScript module path helpers for the Semantic Reference Index.

Module identity for TypeScript is path-based: project-relative POSIX
paths with the file extension stripped. This is the TS analogue of
``maid_runner.core.module_paths``, which uses dotted Python identity.

Only named ``export { Foo } from './y'`` (and the aliased
``export { Foo as Bar } from './y'``) re-exports are resolved.
``export * from './y'`` is intentionally out of scope.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union


_TS_EXTENSIONS: tuple[str, ...] = (
    ".tsx",
    ".ts",
    ".jsx",
    ".js",
    ".mts",
    ".cts",
    ".svelte",
)

_INDEX_CANDIDATES: tuple[str, ...] = (
    "index.ts",
    "index.tsx",
    "index.js",
    "index.jsx",
    "index.mts",
    "index.cts",
)


def ts_file_to_module_path(
    file_path: Union[str, Path],
    project_root: Path,
) -> str:
    """Convert a TypeScript source path to its project-relative module id.

    Strips the file extension (``.ts``, ``.tsx``, ``.cts``, ``.mts``,
    ``.js``, ``.jsx``) and normalizes backslashes to forward slashes.
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


def resolve_ts_reexport(
    module: str,
    name: str,
    project_root: Path,
) -> Optional[tuple[str, str]]:
    """Resolve a one-level named re-export of ``name`` from ``module``.

    Looks for a supported ``<module>/index`` file and scans its top-level
    named re-export statements such as ``export { Foo } from './y'``,
    ``export { Foo as Bar } from './y'``, ``export type { Foo } from './y'``,
    and ``export { type Foo } from './y'``. Returns ``(resolved_module,
    original_name)`` where ``original_name`` is the source-side identifier —
    for plain re-exports it equals ``name``; for aliased re-exports looked up
    by alias it is the pre-alias name. Returns ``None`` when the module is not
    a barrel package, the file cannot be read or parsed, optional parser
    dependencies are unavailable, or ``name`` is not re-exported.

    ``export * from './y'`` is intentionally not resolved.
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
        if child.type != "export_statement":
            continue

        src = _export_source(child, source_bytes)
        if src is None:
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
                resolved = resolve_relative_ts_import(src, f"{module}/index")
                return (resolved, source_name)

    return None


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
        return identifiers[0], identifiers[1]
    return identifiers[0], identifiers[0]
