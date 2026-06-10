"""Bootstrap for brownfield project onboarding.

Discovers source files in an existing project and generates snapshot manifests
for each, enabling gradual MAID adoption.
"""

from __future__ import annotations

import time
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from maid_runner.core._file_discovery import (
    discover_source_files,
    is_test_file,
)
from maid_runner.core._js_ts_imports import collect_import_modules
from maid_runner.core.module_paths import file_to_module_path
from maid_runner.core.ts_module_paths import resolve_ts_import, ts_file_to_module_path
from maid_runner.core.snapshot import generate_snapshot, save_snapshot
from maid_runner.validators.registry import ValidatorRegistry

_JS_TS_SOURCE_EXTENSIONS = (
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".mts",
    ".cts",
)
_TS_MODULE_EXTENSIONS = (*_JS_TS_SOURCE_EXTENSIONS, ".svelte")


@dataclass(frozen=True)
class BootstrapFileResult:
    """Result of bootstrapping a single file."""

    path: str
    status: str  # "captured" | "skipped" | "failed" | "excluded"
    artifact_count: int = 0
    error: str | None = None
    manifest_slug: str | None = None


@dataclass(frozen=True)
class BootstrapReport:
    """Summary report from a bootstrap run."""

    results: tuple[BootstrapFileResult, ...]
    total_discovered: int
    captured: int
    skipped: int
    failed: int
    excluded: int
    total_artifacts: int
    manifests_dir: str | None = None
    duration_ms: float | None = None


@dataclass(frozen=True)
class BootstrapCandidate:
    """One undeclared file with its raw ranking signals."""

    path: str
    churn: int
    inbound_refs: int
    public_artifacts: int


@dataclass(frozen=True)
class BootstrapRankReport:
    """Deterministic, limit-bounded adoption plan over undeclared files."""

    candidates: tuple[BootstrapCandidate, ...]
    total_candidates: int
    limit: int


def bootstrap_project(
    project_root: Union[str, Path],
    *,
    manifest_dir: str = "manifests/",
    exclude_patterns: set[str] | None = None,
    respect_gitignore: bool = True,
    include_private: bool = False,
    dry_run: bool = False,
) -> BootstrapReport:
    """Bootstrap MAID for an existing project by generating snapshot manifests.

    Discovers all source files, filters out test files and exclusions,
    skips already-tracked files, and generates snapshot manifests for the rest.
    """
    start = time.monotonic()
    project_root = Path(project_root).resolve()

    if not project_root.exists():
        raise FileNotFoundError(f"Project directory not found: {project_root}")

    # Discover all source files
    all_files = discover_source_files(
        project_root,
        exclude_patterns=exclude_patterns,
        respect_gitignore=respect_gitignore,
    )

    # Get already-tracked paths from manifest chain
    tracked_paths = _get_tracked_paths(manifest_dir, project_root)

    # Separate excluded files for reporting
    excluded_files: list[str] = []
    candidate_files: list[str] = []

    # Re-discover without exclusions to find what was excluded
    if exclude_patterns:
        all_without_exclusions = discover_source_files(project_root)
        for f in all_without_exclusions:
            if f not in all_files and not is_test_file(f):
                excluded_files.append(f)

    candidate_files = all_files

    # Filter out test files
    candidate_files = [f for f in candidate_files if not is_test_file(f)]

    total_discovered = len(candidate_files) + len(excluded_files)

    results: list[BootstrapFileResult] = []
    captured_count = 0
    skipped_count = 0
    failed_count = 0
    total_artifacts = 0

    # Record excluded files
    for f in excluded_files:
        results.append(BootstrapFileResult(path=f, status="excluded"))

    # Process candidate files
    for rel_path in candidate_files:
        # Skip already-tracked files
        if rel_path in tracked_paths:
            results.append(BootstrapFileResult(path=rel_path, status="skipped"))
            skipped_count += 1
            continue

        # Generate snapshot
        abs_path = project_root / rel_path
        try:
            manifest = generate_snapshot(
                str(abs_path),
                project_root=str(project_root),
                include_private=include_private,
            )
        except Exception as e:
            results.append(
                BootstrapFileResult(path=rel_path, status="failed", error=str(e))
            )
            failed_count += 1
            continue

        artifact_count = sum(len(fs.artifacts) for fs in manifest.files_snapshot)
        total_artifacts += artifact_count

        # Save manifest unless dry run
        if not dry_run:
            save_snapshot(manifest, output_dir=manifest_dir)

        results.append(
            BootstrapFileResult(
                path=rel_path,
                status="captured",
                artifact_count=artifact_count,
                manifest_slug=manifest.slug,
            )
        )
        captured_count += 1

    elapsed = (time.monotonic() - start) * 1000

    return BootstrapReport(
        results=tuple(results),
        total_discovered=total_discovered,
        captured=captured_count,
        skipped=skipped_count,
        failed=failed_count,
        excluded=len(excluded_files),
        total_artifacts=total_artifacts,
        manifests_dir=manifest_dir if not dry_run else None,
        duration_ms=round(elapsed, 1),
    )


def rank_bootstrap_candidates(
    project_root: Union[str, Path],
    *,
    manifest_dir: str = "manifests/",
    limit: int = 20,
    exclude_patterns: set[str] | None = None,
    respect_gitignore: bool = True,
) -> BootstrapRankReport:
    """Rank undeclared source files for incremental MAID adoption."""
    project_root = Path(project_root).resolve()

    if not project_root.exists():
        raise FileNotFoundError(f"Project directory not found: {project_root}")

    all_files = discover_source_files(
        project_root,
        exclude_patterns=exclude_patterns,
        respect_gitignore=respect_gitignore,
    )
    tracked_manifest_dir = Path(manifest_dir)
    if not tracked_manifest_dir.is_absolute():
        tracked_manifest_dir = project_root / tracked_manifest_dir
    tracked_paths = _get_tracked_paths(str(tracked_manifest_dir), project_root)
    candidate_paths = [
        rel_path
        for rel_path in all_files
        if not is_test_file(rel_path) and rel_path not in tracked_paths
    ]

    registry = ValidatorRegistry.with_builtin_validators()
    inbound_refs = _count_inbound_refs(
        all_files=all_files,
        candidate_paths=candidate_paths,
        project_root=project_root,
        registry=registry,
    )

    candidates = [
        BootstrapCandidate(
            path=rel_path,
            churn=_git_churn(project_root, rel_path),
            inbound_refs=inbound_refs.get(rel_path, 0),
            public_artifacts=_public_artifact_count(
                project_root / rel_path,
                registry=registry,
            ),
        )
        for rel_path in candidate_paths
    ]
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            -candidate.churn,
            -candidate.inbound_refs,
            -candidate.public_artifacts,
            candidate.path,
        ),
    )
    bounded_limit = max(limit, 0)

    return BootstrapRankReport(
        candidates=tuple(ordered[:bounded_limit]),
        total_candidates=len(ordered),
        limit=bounded_limit,
    )


def _get_tracked_paths(manifest_dir: str, project_root: Path) -> set[str]:
    """Get paths already tracked by existing manifests."""
    from maid_runner.core.chain import ManifestChain

    try:
        chain = ManifestChain(manifest_dir, project_root=str(project_root))
        return chain.all_tracked_paths()
    except FileNotFoundError:
        return set()


def _git_churn(project_root: Path, rel_path: str) -> int:
    try:
        result = subprocess.run(
            ["git", "log", "--follow", "--oneline", "--", rel_path],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 0
    if result.returncode != 0:
        return 0
    return len([line for line in result.stdout.splitlines() if line.strip()])


def _public_artifact_count(
    file_path: Path,
    *,
    registry: ValidatorRegistry,
) -> int:
    if not registry.has_validator(file_path):
        return 0
    try:
        validator = registry.get(file_path)
        result = validator.collect_implementation_artifacts(
            file_path.read_text(),
            file_path,
        )
    except Exception:
        return 0
    if result.errors:
        return 0
    return sum(1 for artifact in result.artifacts if not artifact.is_private)


def _count_inbound_refs(
    *,
    all_files: list[str],
    candidate_paths: list[str],
    project_root: Path,
    registry: ValidatorRegistry,
) -> dict[str, int]:
    module_to_candidate = _candidate_module_paths(
        candidate_paths=candidate_paths,
        project_root=project_root,
        registry=registry,
    )
    inbound_refs = {path: 0 for path in candidate_paths}

    for importer_path in all_files:
        importer_modules = _imported_modules(
            importer_path=importer_path,
            project_root=project_root,
        )
        if not importer_modules:
            continue
        for module, candidate_path in module_to_candidate.items():
            if candidate_path == importer_path:
                continue
            if module in importer_modules:
                inbound_refs[candidate_path] += 1

    return inbound_refs


def _candidate_module_paths(
    *,
    candidate_paths: list[str],
    project_root: Path,
    registry: ValidatorRegistry,
) -> dict[str, str]:
    modules: dict[str, str] = {}
    for candidate_path in candidate_paths:
        module = _candidate_module_path(
            candidate_path=candidate_path,
            project_root=project_root,
            registry=registry,
        )
        if module:
            modules[module] = candidate_path
    return modules


def _candidate_module_path(
    *,
    candidate_path: str,
    project_root: Path,
    registry: ValidatorRegistry,
) -> str | None:
    if candidate_path.endswith(".py"):
        return file_to_module_path(candidate_path, project_root) or None
    if candidate_path.endswith(_TS_MODULE_EXTENSIONS):
        return ts_file_to_module_path(candidate_path, project_root) or None
    if not registry.has_validator(candidate_path):
        return None
    try:
        validator = registry.get(candidate_path)
        return validator.module_path(candidate_path, project_root)
    except Exception:
        return None


def _imported_modules(
    *,
    importer_path: str,
    project_root: Path,
) -> set[str]:
    if importer_path.endswith(".py"):
        return _python_imported_modules(project_root / importer_path, importer_path)
    if importer_path.endswith(_JS_TS_SOURCE_EXTENSIONS):
        return _js_ts_imported_modules(
            project_root / importer_path, importer_path, project_root
        )
    return set()


def _python_imported_modules(file_path: Path, rel_path: str) -> set[str]:
    import ast

    from maid_runner.validators.python import _BehavioralCollector

    try:
        tree = ast.parse(file_path.read_text(), filename=rel_path)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()

    collector = _BehavioralCollector(file_path=rel_path)
    collector.scan_imports(tree)

    modules = set(collector._module_imports.values())
    modules.update(
        source_module
        for source_module, _alias_of in collector._imported_names.values()
        if source_module
    )
    return modules


def _js_ts_imported_modules(
    file_path: Path,
    rel_path: str,
    project_root: Path,
) -> set[str]:
    try:
        source = file_path.read_text()
    except (OSError, UnicodeDecodeError):
        return set()

    importer_module = rel_path.replace("\\", "/")
    for suffix in _JS_TS_SOURCE_EXTENSIONS:
        if importer_module.endswith(suffix):
            importer_module = importer_module[: -len(suffix)]
            break

    modules: set[str] = set()
    for specifier in collect_import_modules(source, rel_path):
        resolved = resolve_ts_import(specifier, importer_module, project_root)
        modules.add(resolved)
        if resolved.endswith("/index"):
            modules.add(str(Path(resolved).parent).replace("\\", "/"))
    return modules
