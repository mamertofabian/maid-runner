"""Production and test dependency indexes for coverage recommendations."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Collection

from maid_runner.core._file_discovery import is_test_file
from maid_runner.validators.registry import ValidatorRegistry

_TS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
_TS_MODULE_EXTENSIONS = (*_TS_EXTENSIONS, ".svelte")


@dataclass(frozen=True)
class _DependencyIndex:
    production_reverse: dict[str, tuple[str, ...]]
    test_reverse: dict[str, tuple[str, ...]]
    unresolved_by_importer: dict[str, int]
    import_count_by_importer: dict[str, int]
    entrypoints: tuple[str, ...]

    def direct_dependents(self, path: str) -> tuple[str, ...]:
        return self.production_reverse.get(path, ())

    def test_dependents(self, path: str) -> tuple[str, ...]:
        return self.test_reverse.get(path, ())

    def transitive_dependents(self, path: str, depth: int = 3) -> tuple[str, ...]:
        visited: set[str] = set()
        frontier = {path}
        for _ in range(max(depth, 0)):
            next_frontier: set[str] = set()
            for current in frontier:
                for dependent in self.production_reverse.get(current, ()):
                    if dependent in visited or dependent == path:
                        continue
                    visited.add(dependent)
                    next_frontier.add(dependent)
            frontier = next_frontier
            if not frontier:
                break
        return tuple(sorted(visited))

    def reachable_from_entrypoint(self, path: str, depth: int = 3) -> bool:
        return path in self.entrypoints or bool(
            set(self.transitive_dependents(path, depth)).intersection(self.entrypoints)
        )

    def confidence_for(self, path: str) -> str:
        importers = {path, *self.production_reverse.get(path, ())}
        total = sum(self.import_count_by_importer.get(item, 0) for item in importers)
        unresolved = sum(self.unresolved_by_importer.get(item, 0) for item in importers)
        if unresolved and total == 0:
            return "low"
        if total == 0:
            return "high"
        ratio = unresolved / total
        if ratio > 0.2:
            return "low"
        if ratio > 0.05:
            return "medium"
        return "high"


def _build_dependency_index(
    project_root: Path,
    all_files: Collection[str],
    configured_entrypoints: Collection[str] = (),
    registry: ValidatorRegistry | None = None,
) -> _DependencyIndex:
    files = tuple(sorted(str(path).replace("\\", "/") for path in all_files))
    registry = registry or ValidatorRegistry.with_builtin_validators()
    module_to_path: dict[str, str] = {}
    for path in files:
        module = _module_for_path(path, project_root, registry)
        if module:
            module_to_path[module] = path
            if module.endswith("/index"):
                module_to_path.setdefault(module.removesuffix("/index"), path)

    production_reverse: dict[str, set[str]] = {}
    test_reverse: dict[str, set[str]] = {}
    unresolved_by_importer: dict[str, int] = {}
    import_count_by_importer: dict[str, int] = {}
    local_roots = {
        module.replace(".", "/").split("/", 1)[0] for module in module_to_path
    }

    for importer in files:
        imported, hook_unresolved, parse_failed = _imports_for_path(
            importer,
            project_root,
            registry,
        )
        import_count_by_importer[importer] = len(imported)
        unresolved = hook_unresolved + (1 if parse_failed else 0)
        reverse = (
            test_reverse if _is_test_evidence_file(importer) else production_reverse
        )
        for module in imported:
            target = _resolve_module_target(module, module_to_path)
            if target is None:
                root = module.replace(".", "/").split("/", 1)[0]
                if root in local_roots:
                    unresolved += 1
                continue
            if target == importer:
                continue
            reverse.setdefault(target, set()).add(importer)
        unresolved_by_importer[importer] = unresolved

    return _DependencyIndex(
        production_reverse={
            path: tuple(sorted(importers))
            for path, importers in production_reverse.items()
        },
        test_reverse={
            path: tuple(sorted(importers)) for path, importers in test_reverse.items()
        },
        unresolved_by_importer=unresolved_by_importer,
        import_count_by_importer=import_count_by_importer,
        entrypoints=tuple(
            sorted(
                set(_detect_entrypoints(project_root, module_to_path))
                | {
                    str(path).replace("\\", "/")
                    for path in configured_entrypoints
                    if str(path).replace("\\", "/") in files
                }
            )
        ),
    )


def _module_for_path(
    path: str,
    project_root: Path,
    registry: ValidatorRegistry,
) -> str:
    source_path = project_root / path
    if not registry.has_validator(source_path):
        return ""
    try:
        return registry.get(source_path).module_path(path, project_root) or ""
    except Exception:
        return ""


def _is_test_evidence_file(path: str) -> bool:
    parsed = Path(path)
    return is_test_file(path) or any(
        part.lower() in {"test", "tests", "__tests__"} for part in parsed.parts[:-1]
    )


def _imports_for_path(
    path: str,
    project_root: Path,
    registry: ValidatorRegistry,
) -> tuple[set[str], int, bool]:
    source_path = project_root / path
    try:
        source = source_path.read_text()
    except (OSError, UnicodeDecodeError):
        return set(), 0, True
    if not registry.has_validator(source_path):
        return set(), 0, False
    try:
        result = registry.get(source_path).collect_dependencies(
            source,
            path,
            project_root,
        )
    except Exception:
        return set(), 0, True
    return (
        set(result.modules),
        len(result.unresolved),
        bool(result.errors or not result.supported),
    )


def _resolve_module_target(
    module: str,
    module_to_path: dict[str, str],
) -> str | None:
    if module in module_to_path:
        return module_to_path[module]
    dotted_parts = module.split(".")
    while len(dotted_parts) > 1:
        dotted_parts.pop()
        candidate = ".".join(dotted_parts)
        if candidate in module_to_path:
            return module_to_path[candidate]
    slash_parts = module.split("/")
    while len(slash_parts) > 1:
        slash_parts.pop()
        candidate = "/".join(slash_parts)
        if candidate in module_to_path:
            return module_to_path[candidate]
    return None


def _detect_entrypoints(
    project_root: Path,
    module_to_path: dict[str, str],
) -> tuple[str, ...]:
    paths: set[str] = set()
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        try:
            try:
                import tomllib
            except ModuleNotFoundError:  # pragma: no cover - Python 3.10
                import tomli as tomllib
            data = tomllib.loads(pyproject.read_text())
            scripts = data.get("project", {}).get("scripts", {})
            if isinstance(scripts, dict):
                for value in scripts.values():
                    if not isinstance(value, str):
                        continue
                    module = value.split(":", 1)[0].strip()
                    if module in module_to_path:
                        paths.add(module_to_path[module])
        except (OSError, ValueError):
            pass

    package_json = project_root / "package.json"
    if package_json.exists():
        try:
            data = json.loads(package_json.read_text())
            values: list[str] = []
            main = data.get("main")
            if isinstance(main, str):
                values.append(main)
            binary = data.get("bin")
            if isinstance(binary, str):
                values.append(binary)
            elif isinstance(binary, dict):
                values.extend(
                    value for value in binary.values() if isinstance(value, str)
                )
            for value in values:
                normalized = value.removeprefix("./").replace("\\", "/")
                for suffix in _TS_MODULE_EXTENSIONS:
                    if normalized.endswith(suffix):
                        normalized = normalized[: -len(suffix)]
                        break
                if normalized in module_to_path:
                    paths.add(module_to_path[normalized])
        except (OSError, ValueError):
            pass
    return tuple(sorted(paths))
