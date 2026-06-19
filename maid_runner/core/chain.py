"""Manifest chain resolution and merge for MAID Runner v2."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import TYPE_CHECKING, Callable, Optional, Union

from maid_runner.compat.v1_loader import is_v1_manifest

if TYPE_CHECKING:
    from maid_runner.core.supersession_audit import GrandfatherLock
from maid_runner.core.manifest import (
    ManifestLoadError,
    ManifestSchemaError,
    load_manifest,
    load_manifest_raw,
)
from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError
from maid_runner.core.types import ArtifactSpec, FileMode, Manifest

_INACTIVE_MANIFEST_DIR_NAMES = frozenset({"drafts", "v1-archive"})
_MANIFEST_FILE_PATTERNS = ("*.manifest.yaml", "*.manifest.yml", "*.manifest.json")
_INACTIVE_METADATA_STATUSES = frozenset(
    {"archive", "archived", "draft", "epic", "legacy", "planning"}
)
_UTC_CREATED_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_DATE_ONLY_CREATED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CREATED_WARNING_POLICY_INSTANT = datetime(2026, 6, 3, tzinfo=timezone.utc)
_ManifestDirSignature = tuple[tuple[str, int, int], ...]


def _is_legacy_created_warning_baseline(created: str) -> bool:
    instant = _created_utc_instant(created)
    return instant is not None and instant < _CREATED_WARNING_POLICY_INSTANT


def _created_utc_instant(created: str) -> datetime | None:
    try:
        if _DATE_ONLY_CREATED_RE.match(created):
            parsed = datetime.fromisoformat(created).replace(tzinfo=timezone.utc)
        else:
            parsed = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


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

    def replay_until(
        self,
        sequence_number: int | None = None,
        version_tag: str | None = None,
    ) -> dict[str, list[ArtifactSpec]]:
        """Return effective artifacts per file at a point in the event log.

        Replays the manifest chain up to ``sequence_number`` or
        ``version_tag`` (delegating to :meth:`event_log_until` for the
        prefix). Within the prefix, manifests that are superseded by
        another manifest *also in the prefix* are excluded — matching
        the active-chain semantics at that point in time.

        File deletes from non-superseded manifests remove files from
        the result.  Later artifacts override earlier ones by merge_key.
        """
        prefix = self.event_log_until(
            sequence_number=sequence_number, version_tag=version_tag
        )
        if not prefix:
            return {}

        prefix_slugs = {m.slug for m in prefix}
        # A manifest is superseded-within-prefix only when the
        # superseding manifest is also inside the prefix.
        superseded_in_prefix: set[str] = set()
        for m in prefix:
            for s in m.supersedes:
                if s in prefix_slugs:
                    superseded_in_prefix.add(s)

        result: dict[str, dict[str, ArtifactSpec]] = {}
        for m in prefix:
            if m.slug in superseded_in_prefix:
                continue

            for fs in m.all_file_specs:
                file_artifacts = result.setdefault(fs.path, {})
                for a in fs.artifacts:
                    file_artifacts[a.merge_key()] = a

            for ds in m.files_delete:
                result.pop(ds.path, None)

        return {path: list(artifacts.values()) for path, artifacts in result.items()}

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
            for ss in m.files_scope:
                if ss.path == path:
                    modes.add(FileMode.SCOPE)
            for ds in m.files_delete:
                if ds.path == path:
                    modes.add(FileMode.DELETE)

        if not modes:
            return None

        # Strictest wins: CREATE > SNAPSHOT > DELETE > EDIT > SCOPE > READ
        priority = [
            FileMode.CREATE,
            FileMode.SNAPSHOT,
            FileMode.DELETE,
            FileMode.EDIT,
            FileMode.SCOPE,
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

    def audit_supersession_artifacts(
        self, lock: Optional["GrandfatherLock"] = None
    ) -> list[ValidationError]:
        from maid_runner.core.supersession_audit import (
            GrandfatherLock as _GrandfatherLock,
            _GrandfatherLockLoadError,
            SupersessionAuditor,
            default_lock_path,
        )

        errors: list[ValidationError] = []
        if lock is None:
            lock_path = default_lock_path(self._project_root)
            if lock_path.exists():
                try:
                    lock = _GrandfatherLock.load(lock_path)
                except _GrandfatherLockLoadError as exc:
                    errors.append(
                        ValidationError(
                            code=ErrorCode.FILE_READ_ERROR,
                            message=(
                                f"Grandfather lock at {lock_path} is invalid: "
                                f"{exc.detail}"
                            ),
                            severity=Severity.ERROR,
                            location=Location(file=str(lock_path)),
                            suggestion=(
                                "Repair the lock file from version control, or "
                                "run `maid audit supersessions --seal --unseal` "
                                "to regenerate it."
                            ),
                        )
                    )
                    lock = _GrandfatherLock.empty()
            else:
                lock = _GrandfatherLock.empty()
        auditor = SupersessionAuditor(project_root=self._project_root)
        errors.extend(auditor.audit(self, lock))
        return errors

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

    def _detect_imprecise_created_timestamps(self) -> list[ValidationError]:
        errors: list[ValidationError] = []
        for manifest in self.active_manifests():
            if manifest.sequence_number is not None or manifest.created is None:
                continue
            if _is_legacy_created_warning_baseline(manifest.created):
                continue
            if _UTC_CREATED_TIMESTAMP_RE.match(manifest.created):
                continue
            errors.append(
                ValidationError(
                    code=ErrorCode.IMPRECISE_CREATED_TIMESTAMP,
                    message=(
                        f"Manifest '{manifest.slug}' uses created "
                        f"{manifest.created!r}; active manifests should use a "
                        "full UTC timestamp like 2026-06-03T07:41:32Z when "
                        "sequence_number is absent."
                    ),
                    severity=Severity.WARNING,
                    location=Location(file=manifest.source_path),
                )
            )
        return errors

    def _detect_duplicate_unsequenced_created(self) -> list[ValidationError]:
        created_to_slugs: dict[str, list[str]] = {}
        created_to_paths: dict[str, list[str]] = {}
        for manifest in self.active_manifests():
            if manifest.sequence_number is not None or manifest.created is None:
                continue
            if _is_legacy_created_warning_baseline(manifest.created):
                continue
            created_to_slugs.setdefault(manifest.created, []).append(manifest.slug)
            created_to_paths.setdefault(manifest.created, []).append(
                manifest.source_path
            )

        errors: list[ValidationError] = []
        for created, slugs in created_to_slugs.items():
            if len(slugs) <= 1:
                continue
            errors.append(
                ValidationError(
                    code=ErrorCode.DUPLICATE_UNSEQUENCED_CREATED,
                    message=(
                        f"Duplicate created value {created!r} among unsequenced "
                        f"active manifests: {', '.join(sorted(slugs))}. "
                        "Event order falls back to slug for this tie."
                    ),
                    severity=Severity.WARNING,
                    location=Location(file=created_to_paths[created][0]),
                )
            )
        return errors

    def diagnostics(self) -> list[ValidationError]:
        """Return all chain-level diagnostics discovered during loading."""
        diagnostics = (
            self.load_errors
            + self._detect_unmarked_inactive_manifests()
            + self.lifecycle_metadata_diagnostics()
            + self.validate_supersession_integrity()
            + self._detect_mixed_ordering()
            + self._detect_duplicate_sequence()
            + self._detect_non_monotonic_sequence()
            + self._detect_imprecise_created_timestamps()
            + self._detect_duplicate_unsequenced_created()
            + self.audit_supersession_artifacts()
        )
        return [
            error
            for error in diagnostics
            if error.code != ErrorCode.GRANDFATHERED_SUPERSESSION
        ]

    def inactive_manifest_diagnostics(self) -> list[ValidationError]:
        """Return diagnostics for skipped inactive manifest directories."""
        return self._detect_unmarked_inactive_manifests()

    def lifecycle_metadata_diagnostics(self) -> list[ValidationError]:
        """Return diagnostics for inactive lifecycle statuses on active manifests."""
        if self._selected_manifest_dir_is_inactive():
            return []

        errors: list[ValidationError] = []
        for manifest in self.all_manifests:
            metadata = manifest.metadata
            if not isinstance(metadata, dict):
                continue
            status = str(metadata.get("status", "")).strip().lower()
            if status not in _INACTIVE_METADATA_STATUSES:
                continue
            errors.append(
                ValidationError(
                    code=ErrorCode.ACTIVE_MANIFEST_INACTIVE_STATUS,
                    message=(
                        f"Active manifest '{manifest.slug}' declares "
                        f"metadata.status: {status}, which is reserved for "
                        "inactive manifest inventory."
                    ),
                    location=Location(file=manifest.source_path),
                    suggestion=(
                        "Remove inactive lifecycle metadata from promoted "
                        "manifests, or keep draft/planning manifests under an "
                        "inactive directory such as manifests/drafts/."
                    ),
                )
            )
        return errors

    def _detect_unmarked_inactive_manifests(self) -> list[ValidationError]:
        errors: list[ValidationError] = []
        for path in _discover_inactive_manifest_files(self._manifest_dir):
            inactive_dir = _inactive_dir_name_for(path, self._manifest_dir)
            if inactive_dir is None:
                continue
            if _inactive_manifest_is_marked(path, inactive_dir):
                continue
            errors.append(
                ValidationError(
                    code=ErrorCode.INACTIVE_MANIFEST_NOT_MARKED,
                    message=(
                        f"Inactive manifest directory '{inactive_dir}' contains "
                        f"unmarked manifest '{path}'. Mark it as draft/archive "
                        f"inventory or promote it into the active manifest tree."
                    ),
                    location=Location(file=str(path)),
                    suggestion=(
                        "Add an explicit draft/archive marker or move the manifest "
                        "outside the inactive directory."
                    ),
                )
            )
        return errors

    def _selected_manifest_dir_is_inactive(self) -> bool:
        return self._manifest_dir.name in _INACTIVE_MANIFEST_DIR_NAMES

    def reload(self) -> None:
        self._manifests = None
        self._superseded_set = None
        self._superseded_by_map = None
        self._active_cache = None
        self._load_errors = None


_MANIFEST_CHAIN_CACHE: dict[
    tuple[str, str], tuple[_ManifestDirSignature, ManifestChain]
] = {}
_MANIFEST_CHAIN_CACHE_SCOPE_DEPTH = 0


def get_cached_manifest_chain(
    manifest_dir: Union[str, Path],
    project_root: Optional[Path] = None,
) -> ManifestChain:
    """Return a cached ManifestChain while the manifest directory is unchanged."""
    return _get_cached_manifest_chain_with_factory(
        manifest_dir,
        project_root,
        ManifestChain,
    )


def _get_cached_manifest_chain_with_factory(
    manifest_dir: Union[str, Path],
    project_root: Optional[Path],
    chain_factory: Callable[[Path, Path], ManifestChain],
) -> ManifestChain:
    manifest_path = Path(manifest_dir)
    root = Path("." if project_root is None else project_root)
    cache_key = (str(manifest_path.resolve()), str(root.resolve()))
    signature = _manifest_dir_signature(manifest_path)

    cached = _MANIFEST_CHAIN_CACHE.get(cache_key)
    if cached is not None:
        cached_signature, cached_chain = cached
        if cached_signature == signature:
            return cached_chain

    chain = chain_factory(manifest_path, root)
    _MANIFEST_CHAIN_CACHE[cache_key] = (signature, chain)
    return chain


def clear_manifest_chain_cache() -> None:
    """Drop every cached ManifestChain instance."""
    _MANIFEST_CHAIN_CACHE.clear()


def _enter_manifest_chain_cache_scope() -> bool:
    global _MANIFEST_CHAIN_CACHE_SCOPE_DEPTH
    outermost = _MANIFEST_CHAIN_CACHE_SCOPE_DEPTH == 0
    if outermost:
        clear_manifest_chain_cache()
    _MANIFEST_CHAIN_CACHE_SCOPE_DEPTH += 1
    return outermost


def _exit_manifest_chain_cache_scope(outermost: bool) -> None:
    global _MANIFEST_CHAIN_CACHE_SCOPE_DEPTH
    _MANIFEST_CHAIN_CACHE_SCOPE_DEPTH -= 1
    if _MANIFEST_CHAIN_CACHE_SCOPE_DEPTH < 0:
        _MANIFEST_CHAIN_CACHE_SCOPE_DEPTH = 0
    if outermost:
        clear_manifest_chain_cache()


def _manifest_dir_signature(manifest_dir: Path) -> tuple[tuple[str, int, int], ...]:
    signature: list[tuple[str, int, int]] = []
    for path in _iter_manifest_files(manifest_dir):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        try:
            relative_path = path.relative_to(manifest_dir)
        except ValueError:
            relative_path = path
        signature.append((relative_path.as_posix(), stat.st_mtime_ns, stat.st_size))
    return tuple(sorted(signature))


def _discover_manifest_files(manifest_dir: Path) -> list[Path]:
    files: list[Path] = []

    for path in _iter_manifest_files(manifest_dir):
        if _inactive_dir_name_for(path, manifest_dir) is not None:
            continue
        files.append(path)

    return sorted(files)


def _discover_inactive_manifest_files(manifest_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in _iter_manifest_files(manifest_dir)
        if _inactive_dir_name_for(path, manifest_dir) is not None
    )


def _iter_manifest_files(manifest_dir: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in _MANIFEST_FILE_PATTERNS:
        files.extend(manifest_dir.rglob(pattern))
    return files


def _inactive_dir_name_for(path: Path, manifest_dir: Path) -> str | None:
    relative_parts = path.relative_to(manifest_dir).parts[:-1]
    for part in relative_parts:
        if part in _INACTIVE_MANIFEST_DIR_NAMES:
            return part
    return None


def _inactive_manifest_is_marked(path: Path, inactive_dir: str) -> bool:
    try:
        source = path.read_text()
    except OSError:
        return False

    if _has_leading_inactive_marker_comment(source):
        return True

    try:
        data = load_manifest_raw(path)
    except Exception:
        return False

    if not isinstance(data, dict):
        return False

    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        status = str(metadata.get("status", "")).strip().lower()
        if status in _INACTIVE_METADATA_STATUSES:
            return True

    return inactive_dir == "v1-archive" and is_v1_manifest(data)


def _has_leading_inactive_marker_comment(source: str) -> bool:
    for line in source.splitlines():
        stripped = line.strip()
        if stripped == "":
            continue
        if not line.startswith("#"):
            return False
        if line.startswith(("# draft-kind:", "# archive-kind:")):
            return True
    return False


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
