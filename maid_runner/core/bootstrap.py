"""Bootstrap for brownfield project onboarding.

Discovers source files in an existing project and generates snapshot manifests
for each, enabling gradual MAID adoption.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from maid_runner.core._file_discovery import (
    discover_source_files,
    is_test_file,
)
from maid_runner.core.snapshot import generate_snapshot, save_snapshot


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


def _get_tracked_paths(manifest_dir: str, project_root: Path) -> set[str]:
    """Get paths already tracked by existing manifests."""
    from maid_runner.core.chain import ManifestChain

    try:
        chain = ManifestChain(manifest_dir, project_root=str(project_root))
        return chain.all_tracked_paths()
    except FileNotFoundError:
        return set()
