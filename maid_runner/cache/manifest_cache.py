"""Manifest caching module for MAID Runner.

Provides thread-safe caching of manifest data with invalidation support
based on individual file modification times.

Thread Safety:
    - Class-level lock (_instance_lock) for singleton creation
    - Instance-level lock (_lock) for cache operations
    - Lock order: Always acquire _instance_lock before _lock if both needed
    - Never call get_instance() while holding instance _lock

Cache Invalidation:
    - Automatic freshness checking on each cache access
    - Tracks individual file mtimes for precise invalidation
    - Detects file additions, removals, and modifications
"""

import json
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ManifestRegistry:
    """Thread-safe singleton registry for caching and querying manifests.

    Provides efficient access to manifest data with lazy loading,
    automatic cache invalidation based on individual file modification times,
    and thread-safe singleton access per manifests directory.
    """

    # Class-level dictionary for singleton instances keyed by normalized path
    _instances: Dict[str, "ManifestRegistry"] = {}
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls, manifests_dir: Path) -> "ManifestRegistry":
        """Get singleton instance of ManifestRegistry for the given manifests directory.

        Args:
            manifests_dir: Path to the manifests directory

        Returns:
            ManifestRegistry instance for the specified directory
        """
        # Normalize path for consistent lookup
        normalized_path = str(manifests_dir.resolve())

        with cls._instance_lock:
            if normalized_path not in cls._instances:
                cls._instances[normalized_path] = cls(manifests_dir)
            return cls._instances[normalized_path]

    def __init__(self, manifests_dir: Path) -> None:
        """Initialize ManifestRegistry.

        Note: Use get_instance() instead of direct construction for singleton behavior.

        Args:
            manifests_dir: Path to the manifests directory
        """
        self._manifests_dir = manifests_dir.resolve()
        self._lock = threading.Lock()

        # Cache state
        self._manifests: Dict[str, dict] = {}  # path -> manifest data
        self._cache_valid = False
        self._file_mtimes: Dict[str, float] = {}  # path -> mtime for each manifest file

        # Computed caches
        self._superseded: Optional[Set[Path]] = None
        self._file_to_manifests: Dict[str, List[str]] = {}

    def get_related_manifests(self, target_file: str) -> List[str]:
        """Get list of manifest paths that reference the target file.

        Excludes superseded manifests from the result.

        Args:
            target_file: Path to the file to search for in manifests

        Returns:
            List of manifest paths (as strings) that reference the target file,
            excluding superseded manifests
        """
        with self._lock:
            self._ensure_cache_loaded()

            # Get superseded manifests for filtering
            superseded = self._compute_superseded()
            superseded_paths = {str(p) for p in superseded}

            # Build file-to-manifests mapping once (not per-file)
            if not self._file_to_manifests:
                self._build_file_mapping()

            # Get manifests for this file, excluding superseded
            manifests = self._file_to_manifests.get(target_file, [])
            return [m for m in manifests if m not in superseded_paths]

    def get_superseded_manifests(self) -> Set[Path]:
        """Get set of manifest paths that have been superseded by other manifests.

        Returns:
            Set of Path objects for superseded manifests
        """
        with self._lock:
            self._ensure_cache_loaded()
            return self._compute_superseded()

    def invalidate_cache(self) -> None:
        """Invalidate the cached manifests, forcing reload on next access.

        Returns:
            None
        """
        with self._lock:
            self._cache_valid = False
            self._manifests = {}
            self._superseded = None
            self._file_to_manifests = {}
            self._file_mtimes = {}

    def is_cache_valid(self) -> bool:
        """Check if the cache is still valid based on individual file modification times.

        Returns:
            True if cache is valid and no files have been modified, added, or removed,
            False otherwise
        """
        with self._lock:
            if not self._cache_valid:
                return False
            return self._is_cache_fresh()

    def _ensure_cache_loaded(self) -> None:
        """Ensure manifests are loaded into cache with automatic freshness checking.

        Automatically invalidates and reloads cache if files have been modified,
        added, or removed since the last load.

        Must be called with lock held.
        """
        if self._cache_valid and self._is_cache_fresh():
            return

        # Cache is stale or invalid, reload
        if self._cache_valid:
            logger.debug("Cache invalidated due to file changes, reloading manifests")

        self._load_manifests()
        self._cache_valid = True

    def _is_cache_fresh(self) -> bool:
        """Check if cached data is still fresh (no file changes since load).

        Must be called with lock held.

        Returns:
            True if cache matches current file state, False if stale
        """
        if not self._manifests_dir.exists():
            return len(self._manifests) == 0  # Fresh if both empty

        try:
            current_files = set(self._manifests_dir.glob("task-*.manifest.json"))
        except OSError:
            return False

        # Check if file count changed (files added or removed)
        cached_files = set(Path(p) for p in self._file_mtimes.keys())
        if current_files != cached_files:
            return False

        # Check if any individual file's mtime has changed
        for file_path in current_files:
            try:
                current_mtime = file_path.stat().st_mtime
                cached_mtime = self._file_mtimes.get(str(file_path))
                if cached_mtime is None or current_mtime != cached_mtime:
                    return False
            except OSError:
                return False

        return True

    def _load_manifests(self) -> None:
        """Load all manifests from directory into cache.

        Invalid manifests (malformed JSON, unreadable files) are skipped with
        a warning logged. This ensures partial cache availability even when
        some manifests are corrupted.

        Must be called with lock held.
        """
        self._manifests = {}
        self._file_to_manifests = {}
        self._superseded = None
        self._file_mtimes = {}

        if not self._manifests_dir.exists():
            logger.debug("Manifests directory does not exist: %s", self._manifests_dir)
            return

        # Find all manifest files
        manifest_files = list(self._manifests_dir.glob("task-*.manifest.json"))
        logger.debug(
            "Found %d manifest files in %s", len(manifest_files), self._manifests_dir
        )

        for manifest_path in manifest_files:
            try:
                # Record file mtime for cache invalidation
                self._file_mtimes[str(manifest_path)] = manifest_path.stat().st_mtime

                with open(manifest_path, "r") as f:
                    data = json.load(f)
                self._manifests[str(manifest_path)] = data
            except json.JSONDecodeError as e:
                logger.warning(
                    "Skipping manifest with invalid JSON: %s (error: %s)",
                    manifest_path,
                    e,
                )
                continue
            except (IOError, OSError) as e:
                logger.warning(
                    "Skipping unreadable manifest: %s (error: %s)",
                    manifest_path,
                    e,
                )
                continue

        logger.debug("Loaded %d valid manifests", len(self._manifests))

    def _build_file_mapping(self) -> None:
        """Build mapping from files to manifests that reference them.

        Creates a reverse index from file paths to the manifests that reference them,
        enabling efficient lookup of related manifests for any given file.

        Must be called with lock held.
        """
        self._file_to_manifests = {}

        for manifest_path, data in self._manifests.items():
            # Collect all files referenced by this manifest
            referenced_files: Set[str] = set()

            # Check creatableFiles
            creatable = data.get("creatableFiles", [])
            if isinstance(creatable, list):
                referenced_files.update(creatable)

            # Check editableFiles
            editable = data.get("editableFiles", [])
            if isinstance(editable, list):
                referenced_files.update(editable)

            # Check readonlyFiles
            readonly = data.get("readonlyFiles", [])
            if isinstance(readonly, list):
                referenced_files.update(readonly)

            # Check expectedArtifacts.file
            expected = data.get("expectedArtifacts", {})
            if isinstance(expected, dict):
                expected_file = expected.get("file")
                if expected_file:
                    referenced_files.add(expected_file)

            # Add manifest to each referenced file's list
            for ref_file in referenced_files:
                if ref_file not in self._file_to_manifests:
                    self._file_to_manifests[ref_file] = []
                self._file_to_manifests[ref_file].append(manifest_path)

        # Sort manifests by task number for chronological order
        for file_path in self._file_to_manifests:
            self._file_to_manifests[file_path].sort(key=self._get_task_number)

    def _compute_superseded(self) -> Set[Path]:
        """Compute the set of superseded manifests.

        Must be called with lock held.

        Returns:
            Set of Path objects for superseded manifests
        """
        if self._superseded is not None:
            return self._superseded

        superseded: Set[Path] = set()

        for manifest_path, data in self._manifests.items():
            supersedes_list = data.get("supersedes", [])
            if not isinstance(supersedes_list, list):
                continue

            for superseded_path_str in supersedes_list:
                resolved_path = self._resolve_superseded_path(
                    superseded_path_str, manifest_path
                )
                if resolved_path is not None:
                    superseded.add(resolved_path)

        self._superseded = superseded
        return superseded

    def _resolve_superseded_path(
        self, path_str: str, referencing_manifest: str
    ) -> Optional[Path]:
        """Resolve a superseded manifest path to an absolute path within manifests_dir.

        Handles multiple path formats:
        - Relative paths (e.g., "task-001.manifest.json")
        - Paths with "manifests/" prefix (e.g., "manifests/task-001.manifest.json")
        - Absolute paths (validated to be within manifests_dir)

        Security: Paths outside manifests_dir are rejected and logged.

        Args:
            path_str: The path string from the supersedes list
            referencing_manifest: The manifest containing this supersedes reference (for logging)

        Returns:
            Resolved Path within manifests_dir, or None if invalid/out-of-bounds
        """
        superseded_path = Path(path_str)

        if not superseded_path.is_absolute():
            # Handle paths that include "manifests/" prefix
            if path_str.startswith("manifests/"):
                # Resolve from parent of manifests_dir (project root)
                superseded_path = self._manifests_dir.parent / superseded_path
            else:
                # Resolve relative to manifests_dir
                superseded_path = self._manifests_dir / superseded_path

        try:
            resolved = superseded_path.resolve()
            # Validate path is within manifests_dir (security boundary)
            relative_path = resolved.relative_to(self._manifests_dir.resolve())
            return self._manifests_dir / relative_path
        except ValueError:
            # Path is outside manifests_dir - potential path traversal attempt
            logger.warning(
                "Superseded path '%s' in manifest '%s' resolves outside manifests directory, skipping",
                path_str,
                referencing_manifest,
            )
            return None
        except OSError as e:
            logger.debug(
                "Failed to resolve superseded path '%s' in manifest '%s': %s",
                path_str,
                referencing_manifest,
                e,
            )
            return None

    @staticmethod
    def _get_task_number(manifest_path: str) -> int:
        """Extract task number from manifest path for sorting.

        Args:
            manifest_path: Path to manifest file

        Returns:
            Task number as integer, or 0 if not parseable
        """
        try:
            filename = Path(manifest_path).stem  # task-XXX-description.manifest
            parts = filename.split("-")
            if len(parts) >= 2 and parts[0] == "task":
                return int(parts[1])
        except (ValueError, IndexError):
            pass
        return 0
