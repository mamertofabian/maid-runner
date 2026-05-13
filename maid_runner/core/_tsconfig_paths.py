"""Internal helpers for tsconfig JSONC loading and paths aliases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


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


def load_tsconfig(project_root: Path) -> Optional[dict[str, Any]]:
    """Load ``tsconfig.json`` with existing local/relative extends behavior."""
    config_path = Path(project_root) / "tsconfig.json"
    return _load_tsconfig_file(config_path, visited=set())


def resolve_paths_alias(
    specifier: str,
    project_root: Path,
    compiler_options: dict[str, Any],
) -> Optional[str]:
    """Resolve a non-relative specifier through tsconfig ``paths``."""
    return _resolve_paths_alias(
        specifier,
        project_root,
        compiler_options,
        allow_speculative_missing=False,
    )


def strip_jsonc_trivia(source: str) -> str:
    """Remove tsconfig JSONC comments and trailing commas."""
    return _strip_jsonc_trailing_commas(_strip_jsonc_comments(source.lstrip("\ufeff")))


def _resolve_ts_import_from_config(
    specifier: str,
    project_root: Path,
    *,
    allow_speculative_missing: bool = False,
) -> Optional[str]:
    """Resolve a specifier through local tsconfig aliases or baseUrl."""
    config = load_tsconfig(project_root)
    if config is None:
        return None

    compiler_options = config.get("compilerOptions")
    if not isinstance(compiler_options, dict):
        return None

    paths = compiler_options.get("paths")
    if isinstance(paths, dict):
        resolved = _resolve_paths_alias(
            specifier,
            project_root,
            compiler_options,
            allow_speculative_missing=allow_speculative_missing,
        )
        if resolved is not None:
            return resolved

    if isinstance(compiler_options.get("baseUrl"), str):
        base_url = _compiler_base_url(project_root, compiler_options)
        return _project_module_from_existing_path(base_url / specifier, project_root)

    return None


def _load_tsconfig_file(
    config_path: Path,
    visited: set[Path],
) -> Optional[dict[str, Any]]:
    resolved_config_path = config_path.resolve()
    if resolved_config_path in visited:
        return None
    visited.add(resolved_config_path)

    try:
        data = _loads_tsconfig_json(config_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    data = dict(data)
    _normalize_base_url(data, config_path.parent)

    parent_config = _extended_tsconfig_path(data.get("extends"), config_path.parent)
    if parent_config is None:
        return data

    inherited = _load_tsconfig_file(parent_config, visited)
    if inherited is None:
        return data

    return _merge_tsconfig(inherited, data)


def _loads_tsconfig_json(source: str) -> Any:
    try:
        return json.loads(source.lstrip("\ufeff"))
    except json.JSONDecodeError:
        return json.loads(strip_jsonc_trivia(source))


def _strip_jsonc_comments(source: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    idx = 0
    while idx < len(source):
        char = source[idx]
        next_char = source[idx + 1] if idx + 1 < len(source) else ""

        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            idx += 1
            continue

        if char == '"':
            in_string = True
            result.append(char)
            idx += 1
            continue

        if char == "/" and next_char == "/":
            idx += 2
            while idx < len(source) and source[idx] not in "\r\n":
                idx += 1
            continue

        if char == "/" and next_char == "*":
            idx += 2
            while idx < len(source):
                if source[idx] in "\r\n":
                    result.append(source[idx])
                if (
                    source[idx] == "*"
                    and idx + 1 < len(source)
                    and source[idx + 1] == "/"
                ):
                    idx += 2
                    break
                idx += 1
            continue

        result.append(char)
        idx += 1

    return "".join(result)


def _strip_jsonc_trailing_commas(source: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    idx = 0
    while idx < len(source):
        char = source[idx]

        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            idx += 1
            continue

        if char == '"':
            in_string = True
            result.append(char)
            idx += 1
            continue

        if char == ",":
            lookahead = idx + 1
            while lookahead < len(source) and source[lookahead].isspace():
                lookahead += 1
            if lookahead < len(source) and source[lookahead] in "}]":
                idx += 1
                continue

        result.append(char)
        idx += 1

    return "".join(result)


def _extended_tsconfig_path(raw_extends: Any, config_dir: Path) -> Optional[Path]:
    if not isinstance(raw_extends, str) or not raw_extends:
        return None

    extends_path = Path(raw_extends)
    if not extends_path.is_absolute() and not raw_extends.startswith(("./", "../")):
        return None

    candidate = extends_path if extends_path.is_absolute() else config_dir / extends_path
    if candidate.suffix:
        return candidate
    return candidate.with_suffix(".json")


def _merge_tsconfig(
    inherited: dict[str, Any],
    child: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(inherited)
    merged.update(child)

    inherited_options = inherited.get("compilerOptions")
    child_options = child.get("compilerOptions")
    if isinstance(inherited_options, dict) and isinstance(child_options, dict):
        options = dict(inherited_options)
        options.update(child_options)
        merged["compilerOptions"] = options
    elif isinstance(inherited_options, dict) and "compilerOptions" not in child:
        merged["compilerOptions"] = dict(inherited_options)

    return merged


def _normalize_base_url(config: dict[str, Any], config_dir: Path) -> None:
    compiler_options = config.get("compilerOptions")
    if not isinstance(compiler_options, dict):
        return

    raw = compiler_options.get("baseUrl")
    if not isinstance(raw, str) or not raw:
        return

    base = Path(raw)
    if base.is_absolute():
        return

    normalized = config_dir / base
    compiler_options["baseUrl"] = str(normalized)


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
    project_root: Path,
    compiler_options: dict[str, Any],
    *,
    allow_speculative_missing: bool,
) -> Optional[str]:
    paths = compiler_options.get("paths")
    if not isinstance(paths, dict):
        return None

    match = _best_paths_alias_match(specifier, paths)
    if match is None:
        return None

    base_url = _compiler_base_url(project_root, compiler_options)
    pattern, capture, target_strings = match
    for target in target_strings:
        resolved_target = target.replace("*", capture)
        resolved = _project_module_from_existing_path(
            base_url / resolved_target, project_root
        )
        if resolved is not None:
            return resolved

    if (
        allow_speculative_missing
        and len(target_strings) == 1
        and not _is_installed_external_package(specifier, project_root)
        and not _is_catch_all_path_pattern(pattern)
    ):
        return _project_module_from_path(
            base_url / target_strings[0].replace("*", capture), project_root
        )

    return None


def _best_paths_alias_match(
    specifier: str,
    paths: dict[Any, Any],
) -> Optional[tuple[str, str, list[str]]]:
    matches: list[tuple[tuple[int, int, int, int], str, str, list[str]]] = []
    for order, (pattern, targets) in enumerate(paths.items()):
        if not isinstance(pattern, str) or not isinstance(targets, list):
            continue
        capture = _match_ts_path_pattern(pattern, specifier)
        if capture is None:
            continue
        target_strings = [target for target in targets if isinstance(target, str)]
        if not target_strings:
            continue
        matches.append(
            (_path_pattern_priority(pattern, order), pattern, capture, target_strings)
        )

    if not matches:
        return None

    _, pattern, capture, target_strings = max(matches, key=lambda item: item[0])
    return pattern, capture, target_strings


def _path_pattern_priority(pattern: str, order: int) -> tuple[int, int, int, int]:
    if "*" not in pattern:
        return (1, len(pattern), 0, -order)
    prefix, suffix = pattern.split("*", 1)
    return (0, len(prefix), len(suffix), -order)


def _is_catch_all_path_pattern(pattern: str) -> bool:
    if "*" not in pattern:
        return False
    prefix, suffix = pattern.split("*", 1)
    return prefix == "" and suffix == ""


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


def _project_module_from_existing_path(
    path: Path,
    project_root: Path,
) -> Optional[str]:
    if path.is_file():
        return _ts_file_to_module_path(path, project_root)
    if path.is_dir() and _existing_index_file(path) is not None:
        return _ts_file_to_module_path(path, project_root)
    module = _ts_file_to_module_path(path, project_root)
    if _existing_module_file(project_root, module):
        return module
    return None


def _project_module_from_path(path: Path, project_root: Path) -> str:
    return _ts_file_to_module_path(path, project_root)


def _existing_module_file(project_root: Path, module: str) -> Optional[Path]:
    base = project_root / module
    for extension in _TS_EXTENSIONS:
        candidate = Path(f"{base}{extension}")
        if candidate.exists():
            return candidate
    return None


def _existing_index_file(directory: Path) -> Optional[Path]:
    for candidate in _INDEX_CANDIDATES:
        path = directory / candidate
        if path.exists():
            return path
    return None


def _ts_file_to_module_path(
    file_path: str | Path,
    project_root: Path,
) -> str:
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
