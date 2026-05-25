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

from maid_runner.core._ts_export_scanner import (
    _COMPILER_FALLBACK_REQUIRED as _EXPORT_SCANNER_FALLBACK_REQUIRED,
    resolve_reexport_source_or_fallback,
)
from maid_runner.core._tsconfig_paths import _resolve_ts_import_from_config
from maid_runner.core.ts_compiler_resolver import (
    clear_ts_compiler_resolver_session,
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

_TS_IMPORT_CACHE: dict[tuple[object, ...], str] = {}
_TS_REEXPORT_CACHE: dict[tuple[object, ...], Optional[tuple[str, str]]] = {}
_MODULE_ENTRY_SIGNATURE_CACHE: dict[tuple[str, str], tuple[str, int, int]] = {}


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
    cache_key = (
        _root_cache_key(root),
        specifier,
        importer_module,
        _project_config_signature(root),
        _module_entry_signature(root, importer_module),
    )
    cached = _TS_IMPORT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if specifier.startswith("./") or specifier.startswith("../"):
        resolved = resolve_relative_ts_import(specifier, importer_module)
        _TS_IMPORT_CACHE[cache_key] = resolved
        return resolved

    local_resolved = _resolve_ts_import_from_config(
        specifier,
        root,
        allow_speculative_missing=not _module_exists(root, importer_module),
    )
    if local_resolved is not None:
        _TS_IMPORT_CACHE[cache_key] = local_resolved
        return local_resolved

    if _is_node_builtin_specifier(specifier) or _is_installed_external_package(
        specifier, root
    ):
        _TS_IMPORT_CACHE[cache_key] = specifier
        return specifier

    compiler_resolved = resolve_import_with_compiler(specifier, importer_module, root)
    if compiler_resolved is not None:
        _TS_IMPORT_CACHE[cache_key] = compiler_resolved
        return compiler_resolved

    _TS_IMPORT_CACHE[cache_key] = specifier
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
    cache_key = (
        _root_cache_key(root),
        module,
        name,
        _project_config_signature(root),
        _module_entry_signature(root, module),
    )
    if cache_key in _TS_REEXPORT_CACHE:
        return _TS_REEXPORT_CACHE[cache_key]

    entry = _module_entry_file(root, module)
    local_resolved = None
    if entry is not None:
        module_file, _ = entry
        local_resolved = resolve_reexport_source_or_fallback(
            module_file, name, root, seen=set()
        )
        if local_resolved is not _EXPORT_SCANNER_FALLBACK_REQUIRED:
            _TS_REEXPORT_CACHE[cache_key] = local_resolved
            return local_resolved

    if _is_external_module_id(module, root):
        _TS_REEXPORT_CACHE[cache_key] = None
        return None

    compiler_resolved = resolve_reexport_with_compiler(module, name, root)
    if compiler_resolved is not None:
        _TS_REEXPORT_CACHE[cache_key] = compiler_resolved
        return compiler_resolved

    _TS_REEXPORT_CACHE[cache_key] = None
    return None


def clear_ts_resolution_cache() -> None:
    _TS_IMPORT_CACHE.clear()
    _TS_REEXPORT_CACHE.clear()
    _MODULE_ENTRY_SIGNATURE_CACHE.clear()
    clear_ts_compiler_resolver_session()


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


def _root_cache_key(project_root: Path) -> str:
    try:
        return str(Path(project_root).resolve())
    except OSError:
        return str(project_root)


def _project_config_signature(project_root: Path) -> tuple[tuple[str, int, int], ...]:
    signatures: list[tuple[str, int, int]] = []
    for name in ("tsconfig.json", "jsconfig.json", "package.json"):
        path = project_root / name
        signatures.append(_path_signature(path))
    return tuple(signatures)


def _module_entry_signature(project_root: Path, module: str) -> tuple[str, int, int]:
    cache_key = (_root_cache_key(project_root), module)
    cached = _MODULE_ENTRY_SIGNATURE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    entry = _module_entry_file(project_root, module)
    if entry is None:
        result = ("", -1, -1)
        _MODULE_ENTRY_SIGNATURE_CACHE[cache_key] = result
        return result
    path, _ = entry
    result = _path_signature(path)
    _MODULE_ENTRY_SIGNATURE_CACHE[cache_key] = result
    return result


def _path_signature(path: Path) -> tuple[str, int, int]:
    try:
        stat = path.stat()
    except OSError:
        return (path.as_posix(), -1, -1)
    return (path.as_posix(), stat.st_mtime_ns, stat.st_size)


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
