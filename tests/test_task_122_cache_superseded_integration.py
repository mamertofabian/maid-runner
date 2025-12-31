"""
Behavioral tests for Task 122: Cache integration into get_superseded_manifests().

Tests verify that:
1. get_superseded_manifests(manifests_dir) works without use_cache (backward compat)
2. use_cache=False uses existing implementation (no ManifestRegistry)
3. use_cache=True delegates to ManifestRegistry.get_instance().get_superseded_manifests()
4. Both modes return equivalent results for the same input
5. Both modes handle empty/missing directories gracefully
6. Both modes correctly identify supersession chains
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from maid_runner.utils import get_superseded_manifests


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
    ) -> Path:
        manifest_path = temp_manifest_dir / filename
        manifest_data = {
            "goal": f"Test manifest {filename}",
            "taskType": "edit",
            "editableFiles": [target_file],
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


# =============================================================================
# Tests for Backward Compatibility (no use_cache parameter)
# =============================================================================


class TestBackwardCompatibility:
    """Test that calling without use_cache parameter works as before."""

    def test_callable_without_use_cache(self, temp_manifest_dir: Path) -> None:
        """Verify get_superseded_manifests can be called with only manifests_dir."""
        # Should not raise - backward compatible signature
        result = get_superseded_manifests(temp_manifest_dir)
        assert isinstance(result, set)

    def test_returns_set_without_use_cache(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify calling without use_cache returns a set."""
        create_manifest("task-001.manifest.json")
        result = get_superseded_manifests(temp_manifest_dir)
        assert isinstance(result, set)

    def test_finds_superseded_without_use_cache(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify calling without use_cache correctly finds superseded manifests."""
        create_manifest("task-001-original.manifest.json", "src/file.py")
        create_manifest(
            "task-002-replacement.manifest.json",
            "src/file.py",
            supersedes=["task-001-original.manifest.json"],
        )

        result = get_superseded_manifests(temp_manifest_dir)

        superseded_names = {p.name for p in result}
        assert "task-001-original.manifest.json" in superseded_names


# =============================================================================
# Tests for use_cache=False
# =============================================================================


class TestUseCacheFalse:
    """Test that use_cache=False uses existing implementation."""

    def test_returns_set_with_use_cache_false(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify use_cache=False returns a set."""
        create_manifest("task-001.manifest.json")
        result = get_superseded_manifests(temp_manifest_dir, use_cache=False)
        assert isinstance(result, set)

    def test_finds_superseded_with_use_cache_false(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify use_cache=False correctly finds superseded manifests."""
        create_manifest("task-001-original.manifest.json", "src/file.py")
        create_manifest(
            "task-002-replacement.manifest.json",
            "src/file.py",
            supersedes=["task-001-original.manifest.json"],
        )

        result = get_superseded_manifests(temp_manifest_dir, use_cache=False)

        superseded_names = {p.name for p in result}
        assert "task-001-original.manifest.json" in superseded_names

    def test_use_cache_false_does_not_use_registry(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify use_cache=False does not use ManifestRegistry."""
        create_manifest("task-001.manifest.json")

        with patch(
            "maid_runner.utils.ManifestRegistry"
        ) as mock_registry_class:
            result = get_superseded_manifests(temp_manifest_dir, use_cache=False)

            # ManifestRegistry should not be called with use_cache=False
            mock_registry_class.get_instance.assert_not_called()

        assert isinstance(result, set)


# =============================================================================
# Tests for use_cache=True
# =============================================================================


class TestUseCacheTrue:
    """Test that use_cache=True delegates to ManifestRegistry."""

    def test_returns_set_with_use_cache_true(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify use_cache=True returns a set."""
        create_manifest("task-001.manifest.json")
        result = get_superseded_manifests(temp_manifest_dir, use_cache=True)
        assert isinstance(result, set)

    def test_finds_superseded_with_use_cache_true(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify use_cache=True correctly finds superseded manifests."""
        create_manifest("task-001-original.manifest.json", "src/file.py")
        create_manifest(
            "task-002-replacement.manifest.json",
            "src/file.py",
            supersedes=["task-001-original.manifest.json"],
        )

        result = get_superseded_manifests(temp_manifest_dir, use_cache=True)

        superseded_names = {p.name for p in result}
        assert "task-001-original.manifest.json" in superseded_names

    def test_use_cache_true_uses_registry(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify use_cache=True delegates to ManifestRegistry."""
        create_manifest("task-001.manifest.json")

        mock_registry = MagicMock()
        mock_registry.get_superseded_manifests.return_value = set()

        with patch(
            "maid_runner.utils.ManifestRegistry"
        ) as mock_registry_class:
            mock_registry_class.get_instance.return_value = mock_registry

            get_superseded_manifests(temp_manifest_dir, use_cache=True)

            # ManifestRegistry.get_instance should be called with manifests_dir
            mock_registry_class.get_instance.assert_called_once_with(temp_manifest_dir)
            # get_superseded_manifests should be called on the registry instance
            mock_registry.get_superseded_manifests.assert_called_once()


# =============================================================================
# Tests for Result Equivalence
# =============================================================================


class TestResultEquivalence:
    """Test that both modes return equivalent results."""

    def test_empty_directory_equivalence(self, temp_manifest_dir: Path) -> None:
        """Verify both modes return same results for empty directory."""
        result_no_cache = get_superseded_manifests(temp_manifest_dir, use_cache=False)
        result_with_cache = get_superseded_manifests(temp_manifest_dir, use_cache=True)

        assert result_no_cache == result_with_cache
        assert result_no_cache == set()

    def test_no_supersession_equivalence(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify both modes return same results when no supersessions exist."""
        create_manifest("task-001.manifest.json", "src/file1.py")
        create_manifest("task-002.manifest.json", "src/file2.py")

        result_no_cache = get_superseded_manifests(temp_manifest_dir, use_cache=False)
        result_with_cache = get_superseded_manifests(temp_manifest_dir, use_cache=True)

        assert result_no_cache == result_with_cache
        assert result_no_cache == set()

    def test_single_supersession_equivalence(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify both modes return same results for single supersession."""
        create_manifest("task-001-original.manifest.json", "src/file.py")
        create_manifest(
            "task-002-replacement.manifest.json",
            "src/file.py",
            supersedes=["task-001-original.manifest.json"],
        )

        result_no_cache = get_superseded_manifests(temp_manifest_dir, use_cache=False)
        result_with_cache = get_superseded_manifests(temp_manifest_dir, use_cache=True)

        # Both should have exactly one superseded manifest
        assert len(result_no_cache) == len(result_with_cache)
        assert len(result_no_cache) == 1

        # Both should contain the same manifest names
        names_no_cache = {p.name for p in result_no_cache}
        names_with_cache = {p.name for p in result_with_cache}
        assert names_no_cache == names_with_cache

    def test_chain_supersession_equivalence(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify both modes return same results for supersession chains."""
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

        result_no_cache = get_superseded_manifests(temp_manifest_dir, use_cache=False)
        result_with_cache = get_superseded_manifests(temp_manifest_dir, use_cache=True)

        # Both should have exactly two superseded manifests
        assert len(result_no_cache) == len(result_with_cache)
        assert len(result_no_cache) == 2

        # Both should contain the same manifest names
        names_no_cache = {p.name for p in result_no_cache}
        names_with_cache = {p.name for p in result_with_cache}
        assert names_no_cache == names_with_cache
        assert "task-001-first.manifest.json" in names_no_cache
        assert "task-002-second.manifest.json" in names_no_cache


# =============================================================================
# Tests for Empty/Missing Directory Handling
# =============================================================================


class TestEmptyDirectoryHandling:
    """Test handling of empty and missing directories."""

    def test_empty_directory_no_cache(self, temp_manifest_dir: Path) -> None:
        """Verify use_cache=False handles empty directory gracefully."""
        result = get_superseded_manifests(temp_manifest_dir, use_cache=False)
        assert result == set()

    def test_empty_directory_with_cache(self, temp_manifest_dir: Path) -> None:
        """Verify use_cache=True handles empty directory gracefully."""
        result = get_superseded_manifests(temp_manifest_dir, use_cache=True)
        assert result == set()

    def test_missing_directory_no_cache(self, tmp_path: Path) -> None:
        """Verify use_cache=False handles missing directory gracefully."""
        nonexistent_dir = tmp_path / "nonexistent_manifests"

        # Should return empty set, not raise
        result = get_superseded_manifests(nonexistent_dir, use_cache=False)
        assert result == set()

    def test_missing_directory_with_cache(self, tmp_path: Path) -> None:
        """Verify use_cache=True handles missing directory gracefully."""
        nonexistent_dir = tmp_path / "nonexistent_manifests"

        # Should return empty set, not raise
        result = get_superseded_manifests(nonexistent_dir, use_cache=True)
        assert result == set()


# =============================================================================
# Tests for Supersession Chain Handling
# =============================================================================


class TestSupersessionChain:
    """Test correct identification of supersession chains."""

    def test_simple_chain_no_cache(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify use_cache=False correctly identifies simple supersession chain."""
        create_manifest("task-001-original.manifest.json", "src/file.py")
        create_manifest(
            "task-002-supersedes.manifest.json",
            "src/file.py",
            supersedes=["task-001-original.manifest.json"],
        )

        result = get_superseded_manifests(temp_manifest_dir, use_cache=False)

        superseded_names = {p.name for p in result}
        assert "task-001-original.manifest.json" in superseded_names
        assert "task-002-supersedes.manifest.json" not in superseded_names

    def test_simple_chain_with_cache(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify use_cache=True correctly identifies simple supersession chain."""
        create_manifest("task-001-original.manifest.json", "src/file.py")
        create_manifest(
            "task-002-supersedes.manifest.json",
            "src/file.py",
            supersedes=["task-001-original.manifest.json"],
        )

        result = get_superseded_manifests(temp_manifest_dir, use_cache=True)

        superseded_names = {p.name for p in result}
        assert "task-001-original.manifest.json" in superseded_names
        assert "task-002-supersedes.manifest.json" not in superseded_names

    def test_long_chain_no_cache(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify use_cache=False identifies all superseded in a long chain."""
        create_manifest("task-001-v1.manifest.json", "src/file.py")
        create_manifest(
            "task-002-v2.manifest.json",
            "src/file.py",
            supersedes=["task-001-v1.manifest.json"],
        )
        create_manifest(
            "task-003-v3.manifest.json",
            "src/file.py",
            supersedes=["task-002-v2.manifest.json"],
        )
        create_manifest(
            "task-004-v4.manifest.json",
            "src/file.py",
            supersedes=["task-003-v3.manifest.json"],
        )

        result = get_superseded_manifests(temp_manifest_dir, use_cache=False)

        superseded_names = {p.name for p in result}
        assert len(superseded_names) == 3
        assert "task-001-v1.manifest.json" in superseded_names
        assert "task-002-v2.manifest.json" in superseded_names
        assert "task-003-v3.manifest.json" in superseded_names
        assert "task-004-v4.manifest.json" not in superseded_names

    def test_long_chain_with_cache(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify use_cache=True identifies all superseded in a long chain."""
        create_manifest("task-001-v1.manifest.json", "src/file.py")
        create_manifest(
            "task-002-v2.manifest.json",
            "src/file.py",
            supersedes=["task-001-v1.manifest.json"],
        )
        create_manifest(
            "task-003-v3.manifest.json",
            "src/file.py",
            supersedes=["task-002-v2.manifest.json"],
        )
        create_manifest(
            "task-004-v4.manifest.json",
            "src/file.py",
            supersedes=["task-003-v3.manifest.json"],
        )

        result = get_superseded_manifests(temp_manifest_dir, use_cache=True)

        superseded_names = {p.name for p in result}
        assert len(superseded_names) == 3
        assert "task-001-v1.manifest.json" in superseded_names
        assert "task-002-v2.manifest.json" in superseded_names
        assert "task-003-v3.manifest.json" in superseded_names
        assert "task-004-v4.manifest.json" not in superseded_names

    def test_multiple_supersessions_no_cache(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify use_cache=False handles manifest superseding multiple others."""
        create_manifest("task-001-old1.manifest.json", "src/file1.py")
        create_manifest("task-002-old2.manifest.json", "src/file2.py")
        create_manifest(
            "task-003-supersedes-both.manifest.json",
            "src/file.py",
            supersedes=[
                "task-001-old1.manifest.json",
                "task-002-old2.manifest.json",
            ],
        )

        result = get_superseded_manifests(temp_manifest_dir, use_cache=False)

        superseded_names = {p.name for p in result}
        assert len(superseded_names) == 2
        assert "task-001-old1.manifest.json" in superseded_names
        assert "task-002-old2.manifest.json" in superseded_names

    def test_multiple_supersessions_with_cache(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify use_cache=True handles manifest superseding multiple others."""
        create_manifest("task-001-old1.manifest.json", "src/file1.py")
        create_manifest("task-002-old2.manifest.json", "src/file2.py")
        create_manifest(
            "task-003-supersedes-both.manifest.json",
            "src/file.py",
            supersedes=[
                "task-001-old1.manifest.json",
                "task-002-old2.manifest.json",
            ],
        )

        result = get_superseded_manifests(temp_manifest_dir, use_cache=True)

        superseded_names = {p.name for p in result}
        assert len(superseded_names) == 2
        assert "task-001-old1.manifest.json" in superseded_names
        assert "task-002-old2.manifest.json" in superseded_names


# =============================================================================
# Tests for Path Resolution in Supersedes
# =============================================================================


class TestSupersessionPathResolution:
    """Test handling of different path formats in supersedes field."""

    def test_relative_path_no_cache(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify use_cache=False handles relative paths in supersedes."""
        create_manifest("task-001-original.manifest.json", "src/file.py")
        create_manifest(
            "task-002-replacement.manifest.json",
            "src/file.py",
            supersedes=["task-001-original.manifest.json"],  # relative path
        )

        result = get_superseded_manifests(temp_manifest_dir, use_cache=False)

        superseded_names = {p.name for p in result}
        assert "task-001-original.manifest.json" in superseded_names

    def test_relative_path_with_cache(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify use_cache=True handles relative paths in supersedes."""
        create_manifest("task-001-original.manifest.json", "src/file.py")
        create_manifest(
            "task-002-replacement.manifest.json",
            "src/file.py",
            supersedes=["task-001-original.manifest.json"],  # relative path
        )

        result = get_superseded_manifests(temp_manifest_dir, use_cache=True)

        superseded_names = {p.name for p in result}
        assert "task-001-original.manifest.json" in superseded_names

    def test_manifests_prefix_path_no_cache(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify use_cache=False handles manifests/ prefix paths in supersedes."""
        create_manifest("task-001-original.manifest.json", "src/file.py")
        create_manifest(
            "task-002-replacement.manifest.json",
            "src/file.py",
            supersedes=["manifests/task-001-original.manifest.json"],  # with prefix
        )

        result = get_superseded_manifests(temp_manifest_dir, use_cache=False)

        superseded_names = {p.name for p in result}
        assert "task-001-original.manifest.json" in superseded_names

    def test_manifests_prefix_path_with_cache(
        self, temp_manifest_dir: Path, create_manifest
    ) -> None:
        """Verify use_cache=True handles manifests/ prefix paths in supersedes."""
        create_manifest("task-001-original.manifest.json", "src/file.py")
        create_manifest(
            "task-002-replacement.manifest.json",
            "src/file.py",
            supersedes=["manifests/task-001-original.manifest.json"],  # with prefix
        )

        result = get_superseded_manifests(temp_manifest_dir, use_cache=True)

        superseded_names = {p.name for p in result}
        assert "task-001-original.manifest.json" in superseded_names
