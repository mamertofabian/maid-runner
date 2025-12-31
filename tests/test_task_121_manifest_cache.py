"""
Behavioral tests for Task 121: ManifestRegistry cache class.

Tests verify that:
1. ManifestRegistry implements singleton pattern per directory
2. get_related_manifests() returns manifests referencing a target file
3. get_superseded_manifests() returns set of superseded manifest paths
4. invalidate_cache() forces reload on next access
5. is_cache_valid() detects directory modifications
6. Thread-safe concurrent access works correctly
7. Graceful handling of missing manifests directory
"""

import json
import threading
import time
import pytest
from pathlib import Path

from maid_runner.cache.manifest_cache import ManifestRegistry


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_manifest_dir(tmp_path: Path) -> Path:
    """Create a temporary manifests directory."""
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    return manifest_dir


@pytest.fixture
def create_manifest(temp_manifest_dir: Path):
    """Factory fixture for creating test manifests."""

    def _create_manifest(
        filename: str,
        target_file: str = "src/module.py",
        supersedes: list = None,
        additional_files: list = None,
    ) -> Path:
        manifest_path = temp_manifest_dir / filename
        manifest_data = {
            "goal": f"Test manifest {filename}",
            "taskType": "edit",
            "editableFiles": [target_file] + (additional_files or []),
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": target_file,
                "contains": [{"type": "function", "name": "test_func"}],
            },
            "validationCommand": ["pytest", "tests/"],
        }
        if supersedes:
            manifest_data["supersedes"] = supersedes
        manifest_path.write_text(json.dumps(manifest_data, indent=2))
        return manifest_path

    return _create_manifest


@pytest.fixture
def populated_manifest_dir(temp_manifest_dir: Path, create_manifest) -> Path:
    """Create a manifest directory with multiple test manifests."""
    create_manifest("task-001-module.manifest.json", "src/module.py")
    create_manifest("task-002-utils.manifest.json", "src/utils.py")
    create_manifest(
        "task-003-module-update.manifest.json",
        "src/module.py",
        additional_files=["src/helper.py"],
    )
    return temp_manifest_dir


@pytest.fixture(autouse=True)
def clear_singleton_instances():
    """Clear singleton instances before and after each test."""
    # Clear before test
    ManifestRegistry._instances = {}
    yield
    # Clear after test
    ManifestRegistry._instances = {}


# =============================================================================
# Tests for ManifestRegistry class
# =============================================================================


class TestManifestRegistryClass:
    """Test suite for ManifestRegistry class existence and structure."""

    def test_class_exists_and_is_importable(self):
        """Verify ManifestRegistry class exists and is importable."""
        assert ManifestRegistry is not None

    def test_class_has_get_instance_method(self):
        """Verify ManifestRegistry has get_instance classmethod."""
        assert hasattr(ManifestRegistry, "get_instance")
        assert callable(getattr(ManifestRegistry, "get_instance"))

    def test_class_has_get_related_manifests_method(self):
        """Verify ManifestRegistry has get_related_manifests method."""
        assert hasattr(ManifestRegistry, "get_related_manifests")

    def test_class_has_get_superseded_manifests_method(self):
        """Verify ManifestRegistry has get_superseded_manifests method."""
        assert hasattr(ManifestRegistry, "get_superseded_manifests")

    def test_class_has_invalidate_cache_method(self):
        """Verify ManifestRegistry has invalidate_cache method."""
        assert hasattr(ManifestRegistry, "invalidate_cache")

    def test_class_has_is_cache_valid_method(self):
        """Verify ManifestRegistry has is_cache_valid method."""
        assert hasattr(ManifestRegistry, "is_cache_valid")


# =============================================================================
# Tests for get_instance (Singleton Pattern)
# =============================================================================


class TestGetInstance:
    """Test suite for ManifestRegistry.get_instance() classmethod."""

    def test_get_instance_returns_manifest_registry(
        self, temp_manifest_dir: Path
    ) -> None:
        """Verify get_instance returns a ManifestRegistry instance."""
        instance = ManifestRegistry.get_instance(temp_manifest_dir)
        assert isinstance(instance, ManifestRegistry)

    def test_get_instance_returns_same_instance_for_same_directory(
        self, temp_manifest_dir: Path
    ) -> None:
        """Verify get_instance returns same instance for same directory."""
        instance1 = ManifestRegistry.get_instance(temp_manifest_dir)
        instance2 = ManifestRegistry.get_instance(temp_manifest_dir)
        assert instance1 is instance2

    def test_get_instance_returns_different_instance_for_different_directories(
        self, tmp_path: Path
    ) -> None:
        """Verify get_instance returns different instances for different directories."""
        dir1 = tmp_path / "manifests1"
        dir2 = tmp_path / "manifests2"
        dir1.mkdir()
        dir2.mkdir()

        instance1 = ManifestRegistry.get_instance(dir1)
        instance2 = ManifestRegistry.get_instance(dir2)

        assert instance1 is not instance2

    def test_get_instance_accepts_path_object(self, temp_manifest_dir: Path) -> None:
        """Verify get_instance accepts Path object as manifests_dir."""
        instance = ManifestRegistry.get_instance(temp_manifest_dir)
        assert instance is not None

    def test_get_instance_normalizes_path(self, temp_manifest_dir: Path) -> None:
        """Verify get_instance normalizes path for singleton lookup."""
        # Use resolved path and non-resolved path
        path1 = temp_manifest_dir
        path2 = temp_manifest_dir.resolve()

        instance1 = ManifestRegistry.get_instance(path1)
        instance2 = ManifestRegistry.get_instance(path2)

        assert instance1 is instance2


# =============================================================================
# Tests for get_related_manifests
# =============================================================================


class TestGetRelatedManifests:
    """Test suite for ManifestRegistry.get_related_manifests() method."""

    def test_returns_list(self, populated_manifest_dir: Path) -> None:
        """Verify get_related_manifests returns a list."""
        registry = ManifestRegistry.get_instance(populated_manifest_dir)
        result = registry.get_related_manifests("src/module.py")
        assert isinstance(result, list)

    def test_returns_manifests_referencing_target_file(
        self, populated_manifest_dir: Path
    ) -> None:
        """Verify get_related_manifests returns manifests that reference target file."""
        registry = ManifestRegistry.get_instance(populated_manifest_dir)
        result = registry.get_related_manifests("src/module.py")

        # Should find task-001 and task-003 which reference src/module.py
        assert len(result) >= 1
        result_names = [str(p) for p in result]
        assert any("task-001" in name for name in result_names)
        assert any("task-003" in name for name in result_names)

    def test_excludes_superseded_manifests(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify get_related_manifests excludes superseded manifests."""
        # Create a manifest and one that supersedes it
        create_manifest("task-001-original.manifest.json", "src/file.py")
        create_manifest(
            "task-002-replacement.manifest.json",
            "src/file.py",
            supersedes=["task-001-original.manifest.json"],
        )

        registry = ManifestRegistry.get_instance(temp_manifest_dir)
        result = registry.get_related_manifests("src/file.py")

        # Should only return the non-superseded manifest
        result_names = [str(p) for p in result]
        assert len(result) == 1
        assert any("task-002" in name for name in result_names)
        assert not any("task-001" in name for name in result_names)

    def test_returns_empty_list_for_unknown_file(
        self, populated_manifest_dir: Path
    ) -> None:
        """Verify get_related_manifests returns empty list for unknown file."""
        registry = ManifestRegistry.get_instance(populated_manifest_dir)
        result = registry.get_related_manifests("nonexistent/unknown.py")

        assert result == []

    def test_returns_list_of_strings(self, populated_manifest_dir: Path) -> None:
        """Verify get_related_manifests returns list of string paths."""
        registry = ManifestRegistry.get_instance(populated_manifest_dir)
        result = registry.get_related_manifests("src/module.py")

        assert all(isinstance(p, str) for p in result)

    def test_finds_file_in_additional_files(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify get_related_manifests finds files listed in additional editableFiles."""
        create_manifest(
            "task-001-multi.manifest.json",
            "src/main.py",
            additional_files=["src/secondary.py"],
        )

        registry = ManifestRegistry.get_instance(temp_manifest_dir)
        result = registry.get_related_manifests("src/secondary.py")

        assert len(result) >= 1
        assert any("task-001" in str(p) for p in result)


# =============================================================================
# Tests for get_superseded_manifests
# =============================================================================


class TestGetSupersededManifests:
    """Test suite for ManifestRegistry.get_superseded_manifests() method."""

    def test_returns_set(self, temp_manifest_dir: Path, create_manifest) -> None:
        """Verify get_superseded_manifests returns a set."""
        create_manifest("task-001-original.manifest.json", "src/file.py")

        registry = ManifestRegistry.get_instance(temp_manifest_dir)
        result = registry.get_superseded_manifests()

        assert isinstance(result, set)

    def test_returns_empty_set_when_no_supersessions(
        self, populated_manifest_dir: Path
    ) -> None:
        """Verify get_superseded_manifests returns empty set when no manifests superseded."""
        registry = ManifestRegistry.get_instance(populated_manifest_dir)
        result = registry.get_superseded_manifests()

        assert result == set()

    def test_returns_superseded_manifest_paths(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify get_superseded_manifests returns paths of superseded manifests."""
        create_manifest("task-001-original.manifest.json", "src/file.py")
        create_manifest(
            "task-002-replacement.manifest.json",
            "src/file.py",
            supersedes=["task-001-original.manifest.json"],
        )

        registry = ManifestRegistry.get_instance(temp_manifest_dir)
        result = registry.get_superseded_manifests()

        assert len(result) == 1
        superseded_paths = [str(p) for p in result]
        assert any("task-001-original" in p for p in superseded_paths)

    def test_returns_set_of_paths(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify get_superseded_manifests returns set of Path objects."""
        create_manifest("task-001-original.manifest.json", "src/file.py")
        create_manifest(
            "task-002-replacement.manifest.json",
            "src/file.py",
            supersedes=["task-001-original.manifest.json"],
        )

        registry = ManifestRegistry.get_instance(temp_manifest_dir)
        result = registry.get_superseded_manifests()

        assert all(isinstance(p, Path) for p in result)

    def test_handles_chain_of_supersessions(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify get_superseded_manifests handles chains of supersessions."""
        create_manifest("task-001-first.manifest.json", "src/file.py")
        create_manifest(
            "task-002-second.manifest.json",
            "src/file.py",
            supersedes=["task-001-first.manifest.json"],
        )
        create_manifest(
            "task-003-third.manifest.json",
            "src/file.py",
            supersedes=["task-002-second.manifest.json"],
        )

        registry = ManifestRegistry.get_instance(temp_manifest_dir)
        result = registry.get_superseded_manifests()

        # Both task-001 and task-002 should be superseded
        assert len(result) == 2
        superseded_names = [str(p) for p in result]
        assert any("task-001" in name for name in superseded_names)
        assert any("task-002" in name for name in superseded_names)


# =============================================================================
# Tests for invalidate_cache
# =============================================================================


class TestInvalidateCache:
    """Test suite for ManifestRegistry.invalidate_cache() method."""

    def test_invalidate_cache_returns_none(self, temp_manifest_dir: Path) -> None:
        """Verify invalidate_cache returns None."""
        registry = ManifestRegistry.get_instance(temp_manifest_dir)
        result = registry.invalidate_cache()
        assert result is None

    def test_invalidate_cache_forces_reload(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify invalidate_cache forces reload on next access."""
        # Create initial manifest and get registry
        create_manifest("task-001-initial.manifest.json", "src/file.py")
        registry = ManifestRegistry.get_instance(temp_manifest_dir)

        # Access related manifests (populates cache)
        initial_result = registry.get_related_manifests("src/file.py")
        assert len(initial_result) == 1

        # Create new manifest
        create_manifest("task-002-new.manifest.json", "src/file.py")

        # Without invalidation, cache might still show old data
        # Invalidate cache
        registry.invalidate_cache()

        # Now should see the new manifest
        updated_result = registry.get_related_manifests("src/file.py")
        assert len(updated_result) == 2

    def test_invalidate_cache_is_callable(self, temp_manifest_dir: Path) -> None:
        """Verify invalidate_cache is callable as a method."""
        registry = ManifestRegistry.get_instance(temp_manifest_dir)
        assert callable(registry.invalidate_cache)
        # Should not raise
        registry.invalidate_cache()


# =============================================================================
# Tests for is_cache_valid
# =============================================================================


class TestIsCacheValid:
    """Test suite for ManifestRegistry.is_cache_valid() method."""

    def test_is_cache_valid_returns_bool(self, temp_manifest_dir: Path) -> None:
        """Verify is_cache_valid returns a boolean."""
        registry = ManifestRegistry.get_instance(temp_manifest_dir)
        result = registry.is_cache_valid()
        assert isinstance(result, bool)

    def test_is_cache_valid_returns_true_when_unchanged(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify is_cache_valid returns True when directory unchanged."""
        create_manifest("task-001-stable.manifest.json", "src/file.py")
        registry = ManifestRegistry.get_instance(temp_manifest_dir)

        # Access to populate cache
        registry.get_related_manifests("src/file.py")

        # Should be valid immediately after access
        assert registry.is_cache_valid() is True

    def test_is_cache_valid_returns_false_after_modification(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify is_cache_valid returns False after directory modification."""
        create_manifest("task-001-initial.manifest.json", "src/file.py")
        registry = ManifestRegistry.get_instance(temp_manifest_dir)

        # Access to populate cache
        registry.get_related_manifests("src/file.py")

        # Wait briefly to ensure time difference
        time.sleep(0.1)

        # Modify directory by adding new manifest
        create_manifest("task-002-new.manifest.json", "src/other.py")

        # Cache should now be invalid
        assert registry.is_cache_valid() is False

    def test_is_cache_valid_after_invalidate(self, temp_manifest_dir: Path) -> None:
        """Verify is_cache_valid returns False after invalidate_cache."""
        registry = ManifestRegistry.get_instance(temp_manifest_dir)

        # Invalidate cache
        registry.invalidate_cache()

        # Should be invalid after explicit invalidation
        assert registry.is_cache_valid() is False


# =============================================================================
# Tests for Thread Safety
# =============================================================================


class TestThreadSafety:
    """Test suite for thread-safe concurrent access."""

    def test_concurrent_get_instance_returns_same_instance(
        self, temp_manifest_dir: Path
    ) -> None:
        """Verify concurrent get_instance calls return same instance."""
        instances = []
        errors = []

        def get_instance_thread():
            try:
                instance = ManifestRegistry.get_instance(temp_manifest_dir)
                instances.append(instance)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_instance_thread) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(instances) == 10
        # All should be the same instance
        assert all(inst is instances[0] for inst in instances)

    def test_concurrent_access_does_not_raise(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify concurrent access to registry methods does not raise errors."""
        create_manifest("task-001-test.manifest.json", "src/file.py")
        registry = ManifestRegistry.get_instance(temp_manifest_dir)
        errors = []

        def access_registry():
            try:
                registry.get_related_manifests("src/file.py")
                registry.get_superseded_manifests()
                registry.is_cache_valid()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=access_registry) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"

    def test_concurrent_invalidate_does_not_corrupt_state(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify concurrent invalidate_cache calls do not corrupt state."""
        create_manifest("task-001-test.manifest.json", "src/file.py")
        registry = ManifestRegistry.get_instance(temp_manifest_dir)
        errors = []

        def invalidate_and_access():
            try:
                registry.invalidate_cache()
                registry.get_related_manifests("src/file.py")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=invalidate_and_access) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"


# =============================================================================
# Tests for Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Test suite for edge cases and error handling."""

    def test_handles_missing_manifests_directory(self, tmp_path: Path) -> None:
        """Verify graceful handling of missing manifests directory."""
        nonexistent_dir = tmp_path / "nonexistent_manifests"

        # Should handle gracefully - either return empty results or raise clear error
        try:
            registry = ManifestRegistry.get_instance(nonexistent_dir)
            result = registry.get_related_manifests("some/file.py")
            # If it returns, should be empty
            assert result == []
        except (FileNotFoundError, OSError):
            # Raising a clear error is also acceptable
            pass

    def test_handles_empty_manifests_directory(self, temp_manifest_dir: Path) -> None:
        """Verify handling of empty manifests directory."""
        registry = ManifestRegistry.get_instance(temp_manifest_dir)

        related = registry.get_related_manifests("src/file.py")
        superseded = registry.get_superseded_manifests()

        assert related == []
        assert superseded == set()

    def test_handles_invalid_json_in_manifest(self, temp_manifest_dir: Path) -> None:
        """Verify graceful handling of invalid JSON in manifest file."""
        # Create invalid JSON file
        invalid_manifest = temp_manifest_dir / "task-001-invalid.manifest.json"
        invalid_manifest.write_text("{ this is not valid JSON }")

        registry = ManifestRegistry.get_instance(temp_manifest_dir)

        # Should not crash, should return empty or skip invalid
        result = registry.get_related_manifests("src/file.py")
        assert isinstance(result, list)

    def test_handles_manifest_without_expected_fields(
        self, temp_manifest_dir: Path
    ) -> None:
        """Verify handling of manifests with missing expected fields."""
        incomplete_manifest = temp_manifest_dir / "task-001-incomplete.manifest.json"
        incomplete_manifest.write_text(json.dumps({"goal": "Incomplete manifest"}))

        registry = ManifestRegistry.get_instance(temp_manifest_dir)

        # Should not crash
        result = registry.get_related_manifests("src/file.py")
        assert isinstance(result, list)


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for ManifestRegistry workflow."""

    def test_full_workflow(self, temp_manifest_dir: Path, create_manifest) -> None:
        """Verify full workflow of cache creation, query, invalidation, and refresh."""
        # Create initial manifests
        create_manifest("task-001-module.manifest.json", "src/module.py")
        create_manifest("task-002-utils.manifest.json", "src/utils.py")

        # Get registry instance
        registry = ManifestRegistry.get_instance(temp_manifest_dir)

        # Query related manifests
        module_manifests = registry.get_related_manifests("src/module.py")
        utils_manifests = registry.get_related_manifests("src/utils.py")

        assert len(module_manifests) == 1
        assert len(utils_manifests) == 1

        # Verify cache is valid
        assert registry.is_cache_valid() is True

        # Add new manifest (wait for time difference)
        time.sleep(0.1)
        create_manifest("task-003-module-update.manifest.json", "src/module.py")

        # Cache should be invalid
        assert registry.is_cache_valid() is False

        # Invalidate and refresh
        registry.invalidate_cache()
        updated_manifests = registry.get_related_manifests("src/module.py")

        assert len(updated_manifests) == 2

    def test_supersession_workflow(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify supersession tracking through full workflow."""
        # Create original manifest
        create_manifest("task-001-original.manifest.json", "src/file.py")

        registry = ManifestRegistry.get_instance(temp_manifest_dir)

        # Initially no supersessions
        assert registry.get_superseded_manifests() == set()

        # Add superseding manifest
        time.sleep(0.1)
        create_manifest(
            "task-002-replacement.manifest.json",
            "src/file.py",
            supersedes=["task-001-original.manifest.json"],
        )

        # Invalidate and check
        registry.invalidate_cache()
        superseded = registry.get_superseded_manifests()

        assert len(superseded) == 1
        assert any("task-001-original" in str(p) for p in superseded)

        # Related manifests should exclude superseded
        related = registry.get_related_manifests("src/file.py")
        assert len(related) == 1
        assert any("task-002-replacement" in str(p) for p in related)
