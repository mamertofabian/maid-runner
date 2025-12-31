"""Behavioral tests for Task 123: Cache-enabled discover_related_manifests().

This test file validates the integration between discover_related_manifests()
and ManifestRegistry via the use_cache parameter.

Tests verify that:
1. Backward compatibility - calling without use_cache parameter works as before
2. use_cache=False - uses existing implementation (no ManifestRegistry)
3. use_cache=True - delegates to ManifestRegistry.get_instance().get_related_manifests()
4. Result equivalence - both modes return the same results for the same input
5. Empty directory - both modes handle empty/missing directory gracefully
6. Related manifests discovery - both modes correctly find manifests that reference a file
7. Superseded exclusion - both modes exclude superseded manifests from results
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from maid_runner.validators.manifest_validator import discover_related_manifests
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
        additional_editable: list = None,
        additional_creatable: list = None,
    ) -> Path:
        manifest_path = temp_manifest_dir / filename
        manifest_data = {
            "goal": f"Test manifest {filename}",
            "taskType": "edit",
            "creatableFiles": additional_creatable or [],
            "editableFiles": [target_file] + (additional_editable or []),
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


@pytest.fixture(autouse=True)
def clear_singleton_instances():
    """Clear ManifestRegistry singleton instances before and after each test."""
    ManifestRegistry._instances = {}
    yield
    ManifestRegistry._instances = {}


@pytest.fixture
def change_to_temp_dir(tmp_path: Path):
    """Change to temporary directory and restore after test."""
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(original_cwd)


# =============================================================================
# Tests for Backward Compatibility
# =============================================================================


class TestBackwardCompatibility:
    """Tests for backward compatibility - calling without use_cache parameter."""

    def test_discover_related_manifests_without_use_cache_parameter(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify existing callers without use_cache parameter still work."""
        create_manifest("task-001-module.manifest.json", "src/module.py")

        # Call without use_cache parameter (backward compatible)
        result = discover_related_manifests("src/module.py")

        # Should return a list
        assert isinstance(result, list)

    def test_discover_related_manifests_returns_list_without_use_cache(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify return type is List[str] when called without use_cache."""
        create_manifest("task-001-module.manifest.json", "src/module.py")

        result = discover_related_manifests("src/module.py")

        assert isinstance(result, list)
        assert len(result) >= 1
        assert all(isinstance(item, str) for item in result)

    def test_signature_accepts_target_file_only(
        self, change_to_temp_dir, temp_manifest_dir
    ):
        """Verify discover_related_manifests can be called with only target_file."""
        # Should not raise TypeError for missing required argument
        result = discover_related_manifests("nonexistent/file.py")

        assert isinstance(result, list)


# =============================================================================
# Tests for use_cache=False Mode
# =============================================================================


class TestUseCacheFalse:
    """Tests for use_cache=False - uses existing implementation."""

    def test_use_cache_false_returns_list(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify use_cache=False returns a list."""
        create_manifest("task-001-module.manifest.json", "src/module.py")

        result = discover_related_manifests("src/module.py", use_cache=False)

        assert isinstance(result, list)

    def test_use_cache_false_finds_manifests_in_editable_files(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify use_cache=False finds manifests referencing file in editableFiles."""
        create_manifest("task-001-module.manifest.json", "src/module.py")
        create_manifest("task-002-utils.manifest.json", "src/utils.py")

        result = discover_related_manifests("src/module.py", use_cache=False)

        assert len(result) == 1
        assert any("task-001" in path for path in result)

    def test_use_cache_false_finds_manifests_in_creatable_files(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify use_cache=False finds manifests referencing file in creatableFiles."""
        manifest_path = temp_manifest_dir / "task-001-create.manifest.json"
        manifest_data = {
            "goal": "Create new module",
            "taskType": "create",
            "creatableFiles": ["src/new_module.py"],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/new_module.py",
                "contains": [{"type": "function", "name": "new_func"}],
            },
            "validationCommand": ["pytest", "tests/"],
        }
        manifest_path.write_text(json.dumps(manifest_data, indent=2))

        result = discover_related_manifests("src/new_module.py", use_cache=False)

        assert len(result) == 1
        assert any("task-001" in path for path in result)

    def test_use_cache_false_finds_manifests_by_expected_artifacts_file(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify use_cache=False finds manifests by expectedArtifacts.file."""
        create_manifest("task-001-module.manifest.json", "src/module.py")

        result = discover_related_manifests("src/module.py", use_cache=False)

        assert len(result) >= 1
        assert any("task-001" in path for path in result)

    def test_use_cache_false_excludes_superseded_manifests(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify use_cache=False excludes superseded manifests from results."""
        create_manifest("task-001-original.manifest.json", "src/module.py")
        create_manifest(
            "task-002-replacement.manifest.json",
            "src/module.py",
            supersedes=["manifests/task-001-original.manifest.json"],
        )

        result = discover_related_manifests("src/module.py", use_cache=False)

        # Should only return task-002, not task-001 (superseded)
        assert len(result) == 1
        assert any("task-002" in path for path in result)
        assert not any("task-001" in path for path in result)


# =============================================================================
# Tests for use_cache=True Mode
# =============================================================================


class TestUseCacheTrue:
    """Tests for use_cache=True - delegates to ManifestRegistry."""

    def test_use_cache_true_returns_list(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify use_cache=True returns a list."""
        create_manifest("task-001-module.manifest.json", "src/module.py")

        result = discover_related_manifests("src/module.py", use_cache=True)

        assert isinstance(result, list)

    def test_use_cache_true_finds_manifests(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify use_cache=True finds manifests referencing the target file."""
        create_manifest("task-001-module.manifest.json", "src/module.py")
        create_manifest("task-002-utils.manifest.json", "src/utils.py")

        result = discover_related_manifests("src/module.py", use_cache=True)

        assert len(result) >= 1
        assert any("task-001" in path for path in result)

    def test_use_cache_true_excludes_superseded_manifests(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify use_cache=True excludes superseded manifests from results."""
        create_manifest("task-001-original.manifest.json", "src/module.py")
        create_manifest(
            "task-002-replacement.manifest.json",
            "src/module.py",
            supersedes=["task-001-original.manifest.json"],
        )

        result = discover_related_manifests("src/module.py", use_cache=True)

        # Should only return task-002, not task-001 (superseded)
        assert len(result) == 1
        assert any("task-002" in path for path in result)
        assert not any("task-001" in path for path in result)

    def test_use_cache_true_uses_manifest_registry(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify use_cache=True delegates to ManifestRegistry.get_related_manifests()."""
        create_manifest("task-001-module.manifest.json", "src/module.py")

        # Create a mock to verify delegation
        with patch.object(ManifestRegistry, "get_instance") as mock_get_instance:
            mock_registry = MagicMock()
            mock_registry.get_related_manifests.return_value = [
                "manifests/task-001-module.manifest.json"
            ]
            mock_get_instance.return_value = mock_registry

            discover_related_manifests("src/module.py", use_cache=True)

            # Verify ManifestRegistry.get_instance was called
            mock_get_instance.assert_called_once()
            # Verify get_related_manifests was called with target_file
            mock_registry.get_related_manifests.assert_called_once_with("src/module.py")

    def test_use_cache_true_returns_strings(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify use_cache=True returns list of string paths."""
        create_manifest("task-001-module.manifest.json", "src/module.py")

        result = discover_related_manifests("src/module.py", use_cache=True)

        assert all(isinstance(item, str) for item in result)


# =============================================================================
# Tests for Result Equivalence
# =============================================================================


class TestResultEquivalence:
    """Tests for result equivalence between use_cache=False and use_cache=True."""

    def test_both_modes_return_same_results_for_single_manifest(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify both modes return equivalent results for a single manifest."""
        create_manifest("task-001-module.manifest.json", "src/module.py")

        result_no_cache = discover_related_manifests("src/module.py", use_cache=False)
        result_with_cache = discover_related_manifests("src/module.py", use_cache=True)

        # Both should find the same manifest
        assert len(result_no_cache) == len(result_with_cache)
        # Normalize paths for comparison (convert to basenames)
        basenames_no_cache = sorted([Path(p).name for p in result_no_cache])
        basenames_with_cache = sorted([Path(p).name for p in result_with_cache])
        assert basenames_no_cache == basenames_with_cache

    def test_both_modes_return_same_results_for_multiple_manifests(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify both modes return equivalent results for multiple manifests."""
        create_manifest("task-001-module.manifest.json", "src/module.py")
        create_manifest(
            "task-002-module-update.manifest.json",
            "src/module.py",
            additional_editable=["src/helper.py"],
        )
        create_manifest("task-003-utils.manifest.json", "src/utils.py")

        result_no_cache = discover_related_manifests("src/module.py", use_cache=False)
        result_with_cache = discover_related_manifests("src/module.py", use_cache=True)

        # Both should find task-001 and task-002 (which reference src/module.py)
        assert len(result_no_cache) == len(result_with_cache)
        basenames_no_cache = sorted([Path(p).name for p in result_no_cache])
        basenames_with_cache = sorted([Path(p).name for p in result_with_cache])
        assert basenames_no_cache == basenames_with_cache

    def test_both_modes_exclude_same_superseded_manifests(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify both modes exclude the same superseded manifests."""
        create_manifest("task-001-original.manifest.json", "src/module.py")
        create_manifest(
            "task-002-replacement.manifest.json",
            "src/module.py",
            supersedes=["manifests/task-001-original.manifest.json"],
        )

        result_no_cache = discover_related_manifests("src/module.py", use_cache=False)
        result_with_cache = discover_related_manifests("src/module.py", use_cache=True)

        # Both should exclude task-001 (superseded) and include task-002
        assert len(result_no_cache) == len(result_with_cache)
        basenames_no_cache = sorted([Path(p).name for p in result_no_cache])
        basenames_with_cache = sorted([Path(p).name for p in result_with_cache])
        assert basenames_no_cache == basenames_with_cache

    def test_both_modes_return_empty_for_unreferenced_file(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify both modes return empty list for file not in any manifest."""
        create_manifest("task-001-module.manifest.json", "src/module.py")

        result_no_cache = discover_related_manifests(
            "src/unreferenced.py", use_cache=False
        )
        result_with_cache = discover_related_manifests(
            "src/unreferenced.py", use_cache=True
        )

        assert result_no_cache == []
        assert result_with_cache == []


# =============================================================================
# Tests for Empty/Missing Directory
# =============================================================================


class TestEmptyDirectory:
    """Tests for handling empty or missing manifests directory."""

    def test_use_cache_false_handles_empty_directory(
        self, change_to_temp_dir, temp_manifest_dir
    ):
        """Verify use_cache=False handles empty manifests directory gracefully."""
        # Directory exists but is empty
        result = discover_related_manifests("src/module.py", use_cache=False)

        assert isinstance(result, list)
        assert result == []

    def test_use_cache_true_handles_empty_directory(
        self, change_to_temp_dir, temp_manifest_dir
    ):
        """Verify use_cache=True handles empty manifests directory gracefully."""
        # Directory exists but is empty
        result = discover_related_manifests("src/module.py", use_cache=True)

        assert isinstance(result, list)
        assert result == []

    def test_use_cache_false_handles_missing_directory(self, change_to_temp_dir):
        """Verify use_cache=False handles missing manifests directory gracefully."""
        # No manifests directory exists
        result = discover_related_manifests("src/module.py", use_cache=False)

        assert isinstance(result, list)
        assert result == []

    def test_use_cache_true_handles_missing_directory(self, change_to_temp_dir):
        """Verify use_cache=True handles missing manifests directory gracefully."""
        # No manifests directory exists
        result = discover_related_manifests("src/module.py", use_cache=True)

        assert isinstance(result, list)
        assert result == []


# =============================================================================
# Tests for Related Manifests Discovery
# =============================================================================


class TestRelatedManifestsDiscovery:
    """Tests for discovering manifests that reference a file."""

    def test_finds_manifest_referencing_file_in_editable_files(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify both modes find manifests with file in editableFiles."""
        create_manifest("task-001-module.manifest.json", "src/module.py")

        for use_cache in [False, True]:
            result = discover_related_manifests("src/module.py", use_cache=use_cache)
            assert len(result) >= 1, f"Failed with use_cache={use_cache}"
            assert any(
                "task-001" in path for path in result
            ), f"Failed with use_cache={use_cache}"

    def test_finds_manifest_referencing_file_in_creatable_files(
        self, change_to_temp_dir, temp_manifest_dir
    ):
        """Verify both modes find manifests with file in creatableFiles."""
        manifest_path = temp_manifest_dir / "task-001-create.manifest.json"
        manifest_data = {
            "goal": "Create new module",
            "taskType": "create",
            "creatableFiles": ["src/new_module.py"],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/new_module.py",
                "contains": [{"type": "function", "name": "new_func"}],
            },
            "validationCommand": ["pytest", "tests/"],
        }
        manifest_path.write_text(json.dumps(manifest_data, indent=2))

        for use_cache in [False, True]:
            result = discover_related_manifests(
                "src/new_module.py", use_cache=use_cache
            )
            assert len(result) >= 1, f"Failed with use_cache={use_cache}"
            assert any(
                "task-001" in path for path in result
            ), f"Failed with use_cache={use_cache}"

    def test_finds_manifest_referencing_file_in_expected_artifacts(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify both modes find manifests with file in expectedArtifacts.file."""
        create_manifest("task-001-module.manifest.json", "src/module.py")

        for use_cache in [False, True]:
            result = discover_related_manifests("src/module.py", use_cache=use_cache)
            assert len(result) >= 1, f"Failed with use_cache={use_cache}"

    def test_returns_manifests_in_chronological_order(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify manifests are returned in chronological order by task number."""
        create_manifest("task-003-third.manifest.json", "src/module.py")
        create_manifest("task-001-first.manifest.json", "src/module.py")
        create_manifest("task-002-second.manifest.json", "src/module.py")

        for use_cache in [False, True]:
            result = discover_related_manifests("src/module.py", use_cache=use_cache)
            assert len(result) == 3, f"Failed with use_cache={use_cache}"

            # Extract task numbers from result
            task_numbers = []
            for path in result:
                filename = Path(path).name
                # Extract number from "task-XXX-..."
                parts = filename.split("-")
                if len(parts) >= 2:
                    task_numbers.append(int(parts[1]))

            # Verify chronological order
            assert task_numbers == sorted(
                task_numbers
            ), f"Not in order with use_cache={use_cache}: {task_numbers}"


# =============================================================================
# Tests for Superseded Manifest Exclusion
# =============================================================================


class TestSupersededExclusion:
    """Tests for excluding superseded manifests from results."""

    def test_excludes_directly_superseded_manifest(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify directly superseded manifests are excluded."""
        create_manifest("task-001-original.manifest.json", "src/module.py")
        create_manifest(
            "task-002-replacement.manifest.json",
            "src/module.py",
            supersedes=["manifests/task-001-original.manifest.json"],
        )

        for use_cache in [False, True]:
            result = discover_related_manifests("src/module.py", use_cache=use_cache)
            assert len(result) == 1, f"Failed with use_cache={use_cache}"
            assert any(
                "task-002" in path for path in result
            ), f"Failed with use_cache={use_cache}"
            assert not any(
                "task-001" in path for path in result
            ), f"Failed with use_cache={use_cache}"

    def test_excludes_chain_of_superseded_manifests(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify chain of superseded manifests are all excluded."""
        create_manifest("task-001-first.manifest.json", "src/module.py")
        create_manifest(
            "task-002-second.manifest.json",
            "src/module.py",
            supersedes=["manifests/task-001-first.manifest.json"],
        )
        create_manifest(
            "task-003-third.manifest.json",
            "src/module.py",
            supersedes=["manifests/task-002-second.manifest.json"],
        )

        for use_cache in [False, True]:
            result = discover_related_manifests("src/module.py", use_cache=use_cache)
            # Only task-003 should remain (task-001 and task-002 are superseded)
            assert len(result) == 1, f"Failed with use_cache={use_cache}"
            assert any(
                "task-003" in path for path in result
            ), f"Failed with use_cache={use_cache}"

    def test_handles_multiple_supersessions(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify handling of manifest that supersedes multiple other manifests."""
        create_manifest("task-001-part-a.manifest.json", "src/module.py")
        create_manifest("task-002-part-b.manifest.json", "src/module.py")
        create_manifest(
            "task-003-combined.manifest.json",
            "src/module.py",
            supersedes=[
                "manifests/task-001-part-a.manifest.json",
                "manifests/task-002-part-b.manifest.json",
            ],
        )

        for use_cache in [False, True]:
            result = discover_related_manifests("src/module.py", use_cache=use_cache)
            # Only task-003 should remain
            assert len(result) == 1, f"Failed with use_cache={use_cache}"
            assert any(
                "task-003" in path for path in result
            ), f"Failed with use_cache={use_cache}"

    def test_includes_non_superseded_manifests(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify non-superseded manifests are included in results."""
        create_manifest("task-001-module.manifest.json", "src/module.py")
        create_manifest("task-002-utils.manifest.json", "src/utils.py")
        create_manifest(
            "task-003-module-v2.manifest.json",
            "src/module.py",
            supersedes=["manifests/task-001-module.manifest.json"],
        )

        for use_cache in [False, True]:
            result = discover_related_manifests("src/module.py", use_cache=use_cache)
            # Only task-003 for module.py (task-001 is superseded)
            assert len(result) == 1, f"Failed with use_cache={use_cache}"
            assert any(
                "task-003" in path for path in result
            ), f"Failed with use_cache={use_cache}"

            # utils.py should still be found
            utils_result = discover_related_manifests(
                "src/utils.py", use_cache=use_cache
            )
            assert len(utils_result) == 1, f"Failed with use_cache={use_cache}"
            assert any(
                "task-002" in path for path in utils_result
            ), f"Failed with use_cache={use_cache}"


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for the cache-enabled discover_related_manifests."""

    def test_full_workflow_both_modes(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify full workflow produces equivalent results in both modes."""
        # Setup: Create several manifests with various relationships
        create_manifest("task-001-initial.manifest.json", "src/module.py")
        create_manifest(
            "task-002-update.manifest.json",
            "src/module.py",
            additional_editable=["src/helper.py"],
        )
        create_manifest("task-003-other.manifest.json", "src/other.py")
        create_manifest(
            "task-004-supersede.manifest.json",
            "src/module.py",
            supersedes=["manifests/task-001-initial.manifest.json"],
        )

        # Query for src/module.py in both modes
        result_no_cache = discover_related_manifests("src/module.py", use_cache=False)
        result_with_cache = discover_related_manifests("src/module.py", use_cache=True)

        # Should find task-002 and task-004 (task-001 is superseded)
        assert len(result_no_cache) == 2
        assert len(result_with_cache) == 2

        # Both should have the same manifests
        basenames_no_cache = sorted([Path(p).name for p in result_no_cache])
        basenames_with_cache = sorted([Path(p).name for p in result_with_cache])
        assert basenames_no_cache == basenames_with_cache

        # Verify content
        assert any("task-002" in path for path in result_no_cache)
        assert any("task-004" in path for path in result_no_cache)

    def test_default_behavior_is_backward_compatible(
        self, change_to_temp_dir, temp_manifest_dir, create_manifest
    ):
        """Verify default behavior (no use_cache param) matches use_cache=False."""
        create_manifest("task-001-module.manifest.json", "src/module.py")

        result_default = discover_related_manifests("src/module.py")
        result_explicit_false = discover_related_manifests(
            "src/module.py", use_cache=False
        )

        # Default should behave the same as explicit False
        basenames_default = sorted([Path(p).name for p in result_default])
        basenames_explicit = sorted([Path(p).name for p in result_explicit_false])
        assert basenames_default == basenames_explicit
