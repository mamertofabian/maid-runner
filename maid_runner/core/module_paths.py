"""Module path helpers for the Semantic Reference Index.

Converts file paths to dotted Python module names, resolves relative
imports against an importer module, and resolves one-level barrel
re-exports through ``__init__.py``. Callers pass the project root so
results are stable regardless of the current working directory.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional, Union


def file_to_module_path(
    file_path: Union[str, Path],
    project_root: Path,
) -> str:
    """Convert a file path to its dotted Python module name.

    Strips the ``.py`` suffix and collapses ``__init__.py`` to the
    enclosing package. The path may be absolute (in which case it is
    made relative to ``project_root``) or already relative.
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

    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def resolve_relative_import(
    module: Optional[str],
    level: int,
    importer_module: str,
) -> str:
    """Resolve a relative import to an absolute dotted module name.

    The ``importer_module`` is treated as a regular module path; callers
    that resolve from an ``__init__.py`` should pass the package name
    plus a sentinel last component (or use :func:`resolve_reexport`).

    For ``level == 0`` the ``module`` is already absolute and is
    returned unchanged.
    """
    if level == 0:
        return module or ""

    parts = importer_module.split(".") if importer_module else []
    if level > len(parts):
        base_parts: list[str] = []
    else:
        base_parts = parts[:-level]

    if module:
        return ".".join([*base_parts, module])
    return ".".join(base_parts)


def resolve_reexport(
    module: str,
    name: str,
    project_root: Path,
) -> Optional[tuple[str, str]]:
    """Resolve a one-level barrel re-export of ``name`` from ``module``.

    Looks for an ``__init__.py`` corresponding to ``module`` inside
    ``project_root`` and inspects its top-level ``from ... import ...``
    statements. Returns ``(resolved_module, original_name)`` where
    ``original_name`` is the source-side identifier — for plain
    re-exports it equals ``name``; for aliased re-exports
    (``from .submod import Foo as Bar`` looked up by ``Bar``) it is
    the pre-alias name (``Foo``). Returns ``None`` when ``module`` is
    not a package or does not re-export ``name``.

    Resolution is intentionally one level deep: if the target package
    itself re-exports through another ``__init__.py``, this function
    does not follow that chain.
    """
    init_path = Path(project_root) / Path(*module.split(".")) / "__init__.py"
    if not init_path.exists():
        return None

    try:
        tree = ast.parse(init_path.read_text())
    except (OSError, SyntaxError):
        return None

    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        for alias in node.names:
            bound = alias.asname or alias.name
            if bound != name:
                continue
            resolved = _resolve_init_relative(node.module, node.level, module)
            return (resolved, alias.name)

    return None


def _resolve_init_relative(
    module: Optional[str],
    level: int,
    package: str,
) -> str:
    """Resolve a relative import found inside ``package/__init__.py``.

    Inside an ``__init__.py``, level=1 refers to the package itself
    (not the parent), so this differs from :func:`resolve_relative_import`
    which assumes the importer is a regular module.
    """
    if level == 0:
        return module or ""

    parts = package.split(".") if package else []
    drop = level - 1
    if drop > 0:
        parts = parts[:-drop] if drop <= len(parts) else []

    if module:
        return ".".join([*parts, module])
    return ".".join(parts)
