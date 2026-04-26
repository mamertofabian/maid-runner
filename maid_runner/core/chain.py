"""Manifest chain resolution and merge for MAID Runner v2."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from maid_runner.core.manifest import (
    ManifestLoadError,
    ManifestSchemaError,
    load_manifest,
)
from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError
from maid_runner.core.types import ArtifactSpec, FileMode, Manifest


class ManifestChain:
    def __init__(
        self,
        manifest_dir: Union[str, Path],
        project_root: Union[str, Path] = ".",
    ):
        self._manifest_dir = Path(manifest_dir)
        self._project_root = Path(project_root)
        if not self._manifest_dir.exists():
            raise FileNotFoundError(
                f"Manifest directory not found: {self._manifest_dir}"
            )
        self._manifests: list[Manifest] | None = None
        self._superseded_set: set[str] | None = None
        self._superseded_by_map: dict[str, str] | None = None
        self._active_cache: list[Manifest] | None = None
        self._load_errors: list[ValidationError] | None = None

    def _load(self) -> None:
        paths = _discover_manifest_files(self._manifest_dir)
        manifests = []
        load_errors: list[ValidationError] = []
        for p in paths:
            try:
                manifests.append(load_manifest(p))
            except ManifestSchemaError as exc:
                load_errors.append(
                    ValidationError(
                        code=ErrorCode.SCHEMA_VALIDATION_ERROR,
                        message=str(exc),
                        location=Location(file=str(p)),
                    )
                )
            except ManifestLoadError as exc:
                code = (
                    ErrorCode.FILE_NOT_FOUND
                    if exc.reason == "File not found"
                    else ErrorCode.MANIFEST_PARSE_ERROR
                )
                load_errors.append(
                    ValidationError(
                        code=code,
                        message=str(exc),
                        location=Location(file=str(p)),
                    )
                )
            except Exception as exc:
                load_errors.append(
                    ValidationError(
                        code=ErrorCode.INTERNAL_ERROR,
                        message=f"Unexpected manifest-chain load failure for {p}: {exc}",
                        location=Location(file=str(p)),
                    )
                )
        self._manifests = manifests
        self._load_errors = load_errors
        self._resolve_supersession()

    def _resolve_supersession(self) -> None:
        assert self._manifests is not None
        superseded: set[str] = set()
        superseded_by: dict[str, str] = {}

        for m in self._manifests:
            for slug in m.supersedes:
                superseded.add(slug)
                superseded_by[slug] = m.slug

        self._superseded_set = superseded
        self._superseded_by_map = superseded_by

    def _ensure_loaded(self) -> None:
        if self._manifests is None:
            self._load()

    @property
    def all_manifests(self) -> list[Manifest]:
        self._ensure_loaded()
        assert self._manifests is not None
        return list(self._manifests)

    def event_log(self) -> list[Manifest]:
        """All manifests (including superseded) sorted in event order.

        Ordering: sequence_number first, then created timestamp, then slug.
        This is the full historical record — superseded manifests are
        included so the replay/history surface is complete.
        """
        self._ensure_loaded()
        assert self._manifests is not None
        return _sort_manifests(list(self._manifests))

    def event_log_until(
        self,
        sequence_number: int | None = None,
        version_tag: str | None = None,
    ) -> list[Manifest]:
        """Return the event-log prefix up to a point in time.

        Args:
            sequence_number: Return manifests with seq# <= this value.
                Only sequenced manifests are included (unsequenced entries
                have no reliable position). Takes precedence over
                version_tag when both are provided.
            version_tag: Return manifests through the first whose
                version_tag matches (inclusive). Returns empty when the
                tag is not found.
            Neither: Returns the full event_log().

        Returns:
            Sorted list of Manifest objects matching the query.

        Raises:
            ValueError: If sequence_number <= 0 or version_tag is "".
        """
        if sequence_number is not None and sequence_number <= 0:
            raise ValueError("sequence_number must be >= 1")
        if version_tag is not None and version_tag == "":
            raise ValueError("version_tag must not be empty")

        log = self.event_log()

        if sequence_number is not None:
            return [
                m
                for m in log
                if m.sequence_number is not None
                and m.sequence_number <= sequence_number
            ]

        if version_tag is not None:
            result: list[Manifest] = []
            for m in log:
                result.append(m)
                if m.version_tag == version_tag:
                    return result
            return []

        return log

    @property
    def load_errors(self) -> list[ValidationError]:
        self._ensure_loaded()
        assert self._load_errors is not None
        return list(self._load_errors)

    def active_manifests(self) -> list[Manifest]:
        if self._active_cache is not None:
            return list(self._active_cache)
        self._ensure_loaded()
        assert self._manifests is not None
        assert self._superseded_set is not None
        active = [m for m in self._manifests if m.slug not in self._superseded_set]
        self._active_cache = _sort_manifests(active)
        return list(self._active_cache)

    def superseded_manifests(self) -> list[Manifest]:
        self._ensure_loaded()
        assert self._manifests is not None
        assert self._superseded_set is not None
        return [m for m in self._manifests if m.slug in self._superseded_set]

    def is_superseded(self, slug: str) -> bool:
        self._ensure_loaded()
        assert self._superseded_set is not None
        return slug in self._superseded_set

    def superseded_by(self, slug: str) -> Optional[str]:
        self._ensure_loaded()
        assert self._superseded_by_map is not None
        return self._superseded_by_map.get(slug)

    def manifests_for_file(self, path: str) -> list[Manifest]:
        result = []
        for m in self.active_manifests():
            if path in m.all_writable_paths:
                result.append(m)
        return result

    def merged_artifacts_for(self, path: str) -> list[ArtifactSpec]:
        manifests = self.manifests_for_file(path)
        if not manifests:
            return []

        merged: dict[str, ArtifactSpec] = {}
        # Manifests are sorted by created timestamp; later ones override
        for m in manifests:
            for fs in m.all_file_specs:
                if fs.path == path:
                    for artifact in fs.artifacts:
                        merged[artifact.merge_key()] = artifact

        return list(merged.values())

    def file_mode_for(self, path: str) -> Optional[FileMode]:
        modes: set[FileMode] = set()
        for m in self.active_manifests():
            for fs in m.all_file_specs:
                if fs.path == path:
                    modes.add(fs.mode)
            for ds in m.files_delete:
                if ds.path == path:
                    modes.add(FileMode.DELETE)

        if not modes:
            return None

        # Strictest wins: CREATE > SNAPSHOT > DELETE > EDIT > READ
        priority = [
            FileMode.CREATE,
            FileMode.SNAPSHOT,
            FileMode.DELETE,
            FileMode.EDIT,
            FileMode.READ,
        ]
        for mode in priority:
            if mode in modes:
                return mode

        return modes.pop()

    def all_tracked_paths(self) -> set[str]:
        paths: set[str] = set()
        for m in self.active_manifests():
            paths |= m.all_writable_paths
            paths |= set(m.files_read)
        return paths

    def all_read_only_paths(self) -> set[str]:
        """Return paths that appear only in read sections (no writable manifest)."""
        all_writable: set[str] = set()
        all_read: set[str] = set()
        for m in self.active_manifests():
            all_writable |= m.all_writable_paths
            all_read |= set(m.files_read)
        return all_read - all_writable

    def validate_supersession_integrity(self) -> list[ValidationError]:
        self._ensure_loaded()
        assert self._manifests is not None
        errors: list[ValidationError] = []
        slug_set = {m.slug for m in self._manifests}

        # Check for non-existent superseded manifests
        for m in self._manifests:
            for s in m.supersedes:
                if s not in slug_set:
                    errors.append(
                        ValidationError(
                            code=ErrorCode.SUPERSEDED_MANIFEST_NOT_FOUND,
                            message=(
                                f"Manifest '{m.slug}' supersedes non-existent "
                                f"manifest '{s}'"
                            ),
                            severity=Severity.WARNING,
                            location=Location(file=m.source_path),
                        )
                    )

        # Check for circular supersession
        supersedes_graph: dict[str, list[str]] = {}
        for m in self._manifests:
            if m.supersedes:
                supersedes_graph[m.slug] = list(m.supersedes)

        if _has_cycle(supersedes_graph, slug_set):
            errors.append(
                ValidationError(
                    code=ErrorCode.CIRCULAR_SUPERSESSION,
                    message="Circular supersession detected in manifest chain",
                )
            )

        return errors

    def _detect_mixed_ordering(self) -> list[ValidationError]:
        self._ensure_loaded()
        assert self._manifests is not None
        has_seq = any(m.sequence_number is not None for m in self._manifests)
        lacks_seq = any(m.sequence_number is None for m in self._manifests)
        if has_seq and lacks_seq:
            sequenced = [
                m.slug for m in self._manifests if m.sequence_number is not None
            ]
            unsequenced = [m.slug for m in self._manifests if m.sequence_number is None]
            return [
                ValidationError(
                    code=ErrorCode.MIXED_SEQUENCE_NUMBERING,
                    message=(
                        f"Mixed sequence numbering detected: "
                        f"{len(sequenced)} manifest(s) have sequence_number "
                        f"({', '.join(sequenced[:3])}{'...' if len(sequenced) > 3 else ''}), "
                        f"{len(unsequenced)} do not "
                        f"({', '.join(unsequenced[:3])}{'...' if len(unsequenced) > 3 else ''}). "
                        f"Chain ordering uses sequence_number first, falling back to created."
                    ),
                    severity=Severity.WARNING,
                )
            ]
        return []

    def _detect_duplicate_sequence(self) -> list[ValidationError]:
        self._ensure_loaded()
        assert self._manifests is not None
        seq_to_slugs: dict[int, list[str]] = {}
        for m in self._manifests:
            if m.sequence_number is not None:
                seq_to_slugs.setdefault(m.sequence_number, []).append(m.slug)
        errors: list[ValidationError] = []
        for seq, slugs in seq_to_slugs.items():
            if len(slugs) > 1:
                errors.append(
                    ValidationError(
                        code=ErrorCode.DUPLICATE_SEQUENCE_NUMBER,
                        message=(
                            f"Duplicate sequence_number {seq}: "
                            f"{', '.join(sorted(slugs))}"
                        ),
                        severity=Severity.ERROR,
                    )
                )
        return errors

    def _detect_non_monotonic_sequence(self) -> list[ValidationError]:
        self._ensure_loaded()
        assert self._manifests is not None
        sequenced = [
            m
            for m in self._manifests
            if m.sequence_number is not None and m.created is not None
        ]
        sequenced.sort(key=lambda m: m.sequence_number)  # type: ignore[arg-type]
        errors: list[ValidationError] = []
        for i in range(1, len(sequenced)):
            prev = sequenced[i - 1]
            curr = sequenced[i]
            # type narrowing: both have sequence_number and created
            assert prev.sequence_number is not None and curr.sequence_number is not None
            assert prev.created is not None and curr.created is not None
            if prev.sequence_number == curr.sequence_number:
                continue  # duplicate — handled by _detect_duplicate_sequence
            if curr.created < prev.created:
                errors.append(
                    ValidationError(
                        code=ErrorCode.NON_MONOTONIC_SEQUENCE_ORDER,
                        message=(
                            f"Non-monotonic sequence order: "
                            f"'{curr.slug}' (seq {curr.sequence_number}, "
                            f"created {curr.created}) comes after "
                            f"'{prev.slug}' (seq {prev.sequence_number}, "
                            f"created {prev.created}) but has an earlier "
                            f"created timestamp"
                        ),
                        severity=Severity.WARNING,
                    )
                )
        return errors

    def diagnostics(self) -> list[ValidationError]:
        """Return all chain-level diagnostics discovered during loading."""
        return (
            self.load_errors
            + self.validate_supersession_integrity()
            + self._detect_mixed_ordering()
            + self._detect_duplicate_sequence()
            + self._detect_non_monotonic_sequence()
        )

    def reload(self) -> None:
        self._manifests = None
        self._superseded_set = None
        self._superseded_by_map = None
        self._active_cache = None
        self._load_errors = None


def _discover_manifest_files(manifest_dir: Path) -> list[Path]:
    patterns = ["*.manifest.yaml", "*.manifest.yml", "*.manifest.json"]
    files: list[Path] = []
    for pattern in patterns:
        files.extend(manifest_dir.glob(pattern))
    return sorted(files)


def _sort_manifests(manifests: list[Manifest]) -> list[Manifest]:
    def sort_key(m: Manifest) -> tuple[int, int, str, str]:
        if m.sequence_number is not None:
            return (0, m.sequence_number, "", m.slug)
        if m.created:
            return (1, 0, m.created, m.slug)
        return (2, 0, "", m.slug)

    return sorted(manifests, key=sort_key)


def _has_cycle(graph: dict[str, list[str]], all_slugs: set[str]) -> bool:
    visited: set[str] = set()
    in_stack: set[str] = set()

    def dfs(node: str) -> bool:
        if node in in_stack:
            return True
        if node in visited:
            return False
        visited.add(node)
        in_stack.add(node)
        for neighbor in graph.get(node, []):
            if neighbor in all_slugs and dfs(neighbor):
                return True
        in_stack.discard(node)
        return False

    for slug in graph:
        if dfs(slug):
            return True
    return False
