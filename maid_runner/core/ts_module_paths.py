"""TypeScript module path helpers for the Semantic Reference Index.

Module identity for TypeScript is path-based: project-relative POSIX
paths with the file extension stripped. This is the TS analogue of
``maid_runner.core.module_paths``, which uses dotted Python identity.

Only named ``export { Foo } from './y'`` (and the aliased
``export { Foo as Bar } from './y'``) re-exports are resolved.
``export * from './y'`` is intentionally out of scope.
"""

from __future__ import annotations

import re
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

_INDEX_CANDIDATES: tuple[str, ...] = ("index.ts", "index.tsx")

_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_NAMED_REEXPORT_RE = re.compile(
    r"export\s*\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]",
    re.DOTALL,
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

    Looks for ``<module>/index.ts`` or ``<module>/index.tsx`` and scans
    its top-level ``export { Foo } from './y'`` /
    ``export { Foo as Bar } from './y'`` statements. Returns
    ``(resolved_module, original_name)`` where ``original_name`` is
    the source-side identifier — for plain re-exports it equals
    ``name``; for aliased re-exports (``export { Foo as Bar }`` looked
    up by ``Bar``) it is the pre-alias name (``Foo``). Returns ``None``
    when the module is not a barrel package, the file cannot be read,
    or ``name`` is not re-exported.

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

    source = _strip_ts_comments(source)

    for match in _NAMED_REEXPORT_RE.finditer(source):
        body = match.group(1)
        src = match.group(2)
        for piece in body.split(","):
            piece = piece.strip()
            if not piece:
                continue
            if " as " in piece:
                original, _, alias = piece.partition(" as ")
                bound = alias.strip()
                source_name = original.strip()
            else:
                bound = piece
                source_name = piece
            if bound == name:
                resolved = resolve_relative_ts_import(src, f"{module}/index")
                return (resolved, source_name)

    return None


def _strip_ts_comments(source: str) -> str:
    source = _BLOCK_COMMENT_RE.sub("", source)
    source = _LINE_COMMENT_RE.sub("", source)
    return source
