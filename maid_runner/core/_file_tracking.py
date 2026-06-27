"""File tracking helpers for validation."""

from __future__ import annotations

from pathlib import Path

from maid_runner.core._file_discovery import discover_source_files, is_test_file
from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import (
    FileTrackingEntry,
    FileTrackingReport,
    FileTrackingStatus,
)
from maid_runner.core.types import FileMode


def _run_file_tracking(project_root: Path, chain: ManifestChain) -> FileTrackingReport:
    source_files = discover_source_files(project_root, respect_gitignore=True)
    tracked_paths = chain.all_tracked_paths()
    read_only_paths = chain.all_read_only_paths()

    entries: list[FileTrackingEntry] = []
    for path in source_files:
        if is_test_file(path):
            continue
        manifests = chain.manifests_for_file(path)
        manifest_slugs = tuple(m.slug for m in manifests)

        if path not in tracked_paths and not manifests:
            entries.append(
                FileTrackingEntry(
                    path=path,
                    status=FileTrackingStatus.UNDECLARED,
                )
            )
        elif path in read_only_paths and not manifests:
            # File appears only in files.read: REGISTERED, not UNDECLARED.
            read_manifest_slugs = tuple(
                m.slug for m in chain.active_manifests() if path in m.files_read
            )
            entries.append(
                FileTrackingEntry(
                    path=path,
                    status=FileTrackingStatus.REGISTERED,
                    manifests=read_manifest_slugs,
                    issues=("Only in readonlyFiles",),
                )
            )
        elif manifests:
            if chain.file_mode_for(path) == FileMode.SCOPE:
                entries.append(
                    FileTrackingEntry(
                        path=path,
                        status=FileTrackingStatus.TRACKED,
                        manifests=manifest_slugs,
                    )
                )
                continue

            has_artifacts = any(
                spec is not None and spec.artifacts
                for spec in (m.file_spec_for(path) for m in manifests)
            )
            if has_artifacts:
                entries.append(
                    FileTrackingEntry(
                        path=path,
                        status=FileTrackingStatus.TRACKED,
                        manifests=manifest_slugs,
                    )
                )
            else:
                entries.append(
                    FileTrackingEntry(
                        path=path,
                        status=FileTrackingStatus.REGISTERED,
                        manifests=manifest_slugs,
                        issues=("No artifacts declared",),
                    )
                )
        else:
            entries.append(
                FileTrackingEntry(
                    path=path,
                    status=FileTrackingStatus.REGISTERED,
                    manifests=manifest_slugs,
                    issues=("Only in read section",),
                )
            )

    return FileTrackingReport(entries=tuple(entries))
