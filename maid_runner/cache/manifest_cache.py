"""Manifest caching module for MAID Runner.

Provides thread-safe caching of manifest data with invalidation support
based on individual file modification times.
"""

import json
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set


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

            if not self._manifests_dir.exists():
                return False

            # Get current manifest files
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

    def _ensure_cache_loaded(self) -> None:
        """Ensure manifests are loaded into cache.

        Must be called with lock held.
        """
        if self._cache_valid:
            return

        self._load_manifests()
        self._cache_valid = True

    def _load_manifests(self) -> None:
        """Load all manifests from directory into cache.

        Must be called with lock held.
        """
        self._manifests = {}
        self._file_to_manifests = {}
        self._superseded = None
        self._file_mtimes = {}

        if not self._manifests_dir.exists():
            return

        # Find all manifest files
        manifest_files = list(self._manifests_dir.glob("task-*.manifest.json"))

        for manifest_path in manifest_files:
            try:
                # Record file mtime for cache invalidation
                self._file_mtimes[str(manifest_path)] = manifest_path.stat().st_mtime

                with open(manifest_path, "r") as f:
                    data = json.load(f)
                self._manifests[str(manifest_path)] = data
            except (json.JSONDecodeError, IOError, OSError):
                # Skip invalid manifests
                continue

    def _build_file_mapping(self) -> None:
        """Build mapping from files to manifests that reference them.

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
                # Convert to Path and resolve relative to manifests_dir
                superseded_path = Path(superseded_path_str)
                if not superseded_path.is_absolute():
                    # Handle paths that include "manifests/" prefix
                    if str(superseded_path).startswith("manifests/"):
                        # Resolve from parent of manifests_dir
                        superseded_path = (
                            self._manifests_dir.parent / superseded_path
                        )
                    else:
                        # Resolve relative to manifests_dir
                        superseded_path = self._manifests_dir / superseded_path

                try:
                    resolved = superseded_path.resolve()
                    # Get relative path from manifests_dir
                    try:
                        relative_path = resolved.relative_to(
                            self._manifests_dir.resolve()
                        )
                        superseded.add(self._manifests_dir / relative_path)
                    except ValueError:
                        # Path is outside manifests_dir, skip
                        pass
                except (OSError, ValueError):
                    # Invalid path, skip
                    pass

        self._superseded = superseded
        return superseded

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
