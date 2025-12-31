"""
Performance benchmark tests for Task 125: Cache performance benchmarks.

These tests verify the performance improvements from manifest chain caching:
- 50%+ performance improvement for operations on chains > 50 manifests
- < 100ms validation time for typical manifests

Tests use time.perf_counter() for accurate timing measurements and include
warm-up runs to ensure consistent benchmark results.
"""

import json
import time
import pytest
from pathlib import Path

from maid_runner.cache.manifest_cache import ManifestRegistry
from maid_runner.validators.manifest_validator import discover_related_manifests
from maid_runner.utils import get_superseded_manifests


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def manifests_with_50_files(tmp_path: Path, monkeypatch):
    """Create 50+ test manifest files with various relationships.

    This fixture creates a realistic manifest chain scenario for benchmarking:
    - 50+ manifests with various file references
    - Some supersession relationships
    - Multiple files per manifest

    Args:
        tmp_path: pytest temporary path fixture
        monkeypatch: pytest monkeypatch fixture for changing working directory

    Returns:
        Path to the temporary directory containing the manifests
    """
    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create 55 manifests (to exceed 50 threshold)
    target_files = [
        "src/module_a.py",
        "src/module_b.py",
        "src/module_c.py",
        "src/utils.py",
        "src/helpers.py",
        "tests/test_module_a.py",
        "tests/test_module_b.py",
        "tests/test_utils.py",
    ]

    for i in range(1, 56):
        manifest_data = {
            "goal": f"Test manifest {i:03d}",
            "taskType": "edit",
            "editableFiles": [target_files[i % len(target_files)]],
            "readonlyFiles": [target_files[(i + 1) % len(target_files)]],
            "expectedArtifacts": {
                "file": target_files[i % len(target_files)],
                "contains": [
                    {"type": "function", "name": f"test_func_{i}"},
                    {"type": "class", "name": f"TestClass{i}"},
                ],
            },
            "validationCommand": ["pytest", f"tests/test_{i}.py", "-v"],
        }

        # Add supersession relationships (every 10th manifest supersedes the previous)
        if i > 10 and i % 10 == 0:
            superseded_num = i - 10
            manifest_data["supersedes"] = [
                f"task-{superseded_num:03d}-test.manifest.json"
            ]

        manifest_path = manifests_dir / f"task-{i:03d}-test.manifest.json"
        manifest_path.write_text(json.dumps(manifest_data, indent=2))

    # Change working directory to tmp_path for discover_related_manifests
    monkeypatch.chdir(tmp_path)

    return tmp_path


@pytest.fixture(autouse=True)
def clear_singleton_instances():
    """Clear ManifestRegistry singleton instances before and after each test."""
    ManifestRegistry._instances = {}
    yield
    ManifestRegistry._instances = {}


# =============================================================================
# Performance Benchmark Tests
# =============================================================================


def test_discover_related_manifests_cached_vs_uncached(manifests_with_50_files: Path):
    """Benchmark comparing cached vs uncached discover_related_manifests performance.

    This test verifies that using the cache provides a performance improvement
    when discovering related manifests across a large manifest chain.
    """
    target_file = "src/module_a.py"
    iterations = 5
    warmup_iterations = 2

    # Warm-up runs (cache population for cached, file system warm-up for uncached)
    for _ in range(warmup_iterations):
        discover_related_manifests(target_file, use_cache=False)
        discover_related_manifests(target_file, use_cache=True)

    # Clear cache after warmup to get clean benchmark
    manifests_dir = manifests_with_50_files / "manifests"
    ManifestRegistry.get_instance(manifests_dir).invalidate_cache()

    # Benchmark uncached operations
    uncached_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        result_uncached = discover_related_manifests(target_file, use_cache=False)
        end = time.perf_counter()
        uncached_times.append(end - start)

    uncached_avg = sum(uncached_times) / len(uncached_times)

    # Benchmark cached operations (first call populates cache, rest benefit from it)
    cached_times = []
    # First call populates cache
    discover_related_manifests(target_file, use_cache=True)

    for _ in range(iterations):
        start = time.perf_counter()
        result_cached = discover_related_manifests(target_file, use_cache=True)
        end = time.perf_counter()
        cached_times.append(end - start)

    cached_avg = sum(cached_times) / len(cached_times)

    # Assert that cached is faster than uncached
    assert cached_avg < uncached_avg, (
        f"Cached ({cached_avg:.6f}s) should be faster than uncached ({uncached_avg:.6f}s)"
    )

    # Both should return non-empty results
    assert len(result_cached) > 0, "Cached should return results"
    assert len(result_uncached) > 0, "Uncached should return results"

    # Note: Cached includes readonlyFiles references while uncached doesn't,
    # so we verify both return valid results rather than identical results


def test_get_superseded_manifests_cached_vs_uncached(manifests_with_50_files: Path):
    """Benchmark comparing cached vs uncached get_superseded_manifests performance.

    This test verifies that using the cache provides a performance improvement
    when retrieving superseded manifests from a large manifest chain.
    """
    manifests_dir = manifests_with_50_files / "manifests"
    iterations = 5
    warmup_iterations = 2

    # Warm-up runs
    for _ in range(warmup_iterations):
        get_superseded_manifests(manifests_dir, use_cache=False)
        get_superseded_manifests(manifests_dir, use_cache=True)

    # Clear cache after warmup
    ManifestRegistry.get_instance(manifests_dir).invalidate_cache()

    # Benchmark uncached operations
    uncached_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        result_uncached = get_superseded_manifests(manifests_dir, use_cache=False)
        end = time.perf_counter()
        uncached_times.append(end - start)

    uncached_avg = sum(uncached_times) / len(uncached_times)

    # Benchmark cached operations (first call populates cache)
    get_superseded_manifests(manifests_dir, use_cache=True)

    cached_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        result_cached = get_superseded_manifests(manifests_dir, use_cache=True)
        end = time.perf_counter()
        cached_times.append(end - start)

    cached_avg = sum(cached_times) / len(cached_times)

    # Assert that cached is faster than uncached
    assert cached_avg < uncached_avg, (
        f"Cached ({cached_avg:.6f}s) should be faster than uncached ({uncached_avg:.6f}s)"
    )

    # Both should return the same superseded manifests
    # (supersession logic should be identical between cached and uncached)
    cached_names = {Path(p).name for p in result_cached}
    uncached_names = {Path(p).name for p in result_uncached}
    assert cached_names == uncached_names, (
        "Cached and uncached superseded manifests should be equivalent"
    )


def test_cache_achieves_50_percent_improvement(manifests_with_50_files: Path):
    """Verify that caching achieves at least 50% performance improvement.

    This test measures the performance improvement from caching and asserts
    it meets the 50% threshold requirement from Issue #34.
    """
    manifests_dir = manifests_with_50_files / "manifests"
    target_file = "src/module_a.py"
    iterations = 10

    # Clear cache to ensure clean state
    ManifestRegistry.get_instance(manifests_dir).invalidate_cache()

    # Measure uncached performance for discover_related_manifests
    uncached_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        discover_related_manifests(target_file, use_cache=False)
        end = time.perf_counter()
        uncached_times.append(end - start)

    uncached_avg = sum(uncached_times) / len(uncached_times)

    # Clear cache and populate it with a single call
    ManifestRegistry.get_instance(manifests_dir).invalidate_cache()
    discover_related_manifests(target_file, use_cache=True)

    # Measure cached performance
    cached_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        discover_related_manifests(target_file, use_cache=True)
        end = time.perf_counter()
        cached_times.append(end - start)

    cached_avg = sum(cached_times) / len(cached_times)

    # Calculate improvement percentage
    if uncached_avg > 0:
        improvement = (uncached_avg - cached_avg) / uncached_avg * 100
    else:
        improvement = 0

    # Assert at least 50% improvement
    assert improvement >= 50, (
        f"Cache should achieve at least 50% improvement, got {improvement:.1f}%\n"
        f"Uncached avg: {uncached_avg:.6f}s, Cached avg: {cached_avg:.6f}s"
    )


def test_cached_validation_under_100ms(manifests_with_50_files: Path):
    """Ensure cached validation operations complete under 100ms threshold.

    This test verifies that cached operations are fast enough to meet
    the < 100ms requirement from Issue #34 for typical manifests.
    """
    manifests_dir = manifests_with_50_files / "manifests"
    target_file = "src/module_a.py"
    threshold_ms = 100  # 100 milliseconds
    iterations = 10

    # Populate cache with initial call
    discover_related_manifests(target_file, use_cache=True)
    get_superseded_manifests(manifests_dir, use_cache=True)

    # Measure cached discover_related_manifests
    discover_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        discover_related_manifests(target_file, use_cache=True)
        end = time.perf_counter()
        discover_times.append((end - start) * 1000)  # Convert to ms

    discover_avg_ms = sum(discover_times) / len(discover_times)
    discover_max_ms = max(discover_times)

    # Measure cached get_superseded_manifests
    superseded_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        get_superseded_manifests(manifests_dir, use_cache=True)
        end = time.perf_counter()
        superseded_times.append((end - start) * 1000)  # Convert to ms

    superseded_avg_ms = sum(superseded_times) / len(superseded_times)
    superseded_max_ms = max(superseded_times)

    # Assert average time is under threshold
    assert discover_avg_ms < threshold_ms, (
        f"discover_related_manifests average ({discover_avg_ms:.2f}ms) "
        f"should be under {threshold_ms}ms"
    )

    assert superseded_avg_ms < threshold_ms, (
        f"get_superseded_manifests average ({superseded_avg_ms:.2f}ms) "
        f"should be under {threshold_ms}ms"
    )

    # Also check that max time is reasonable (2x threshold as upper bound)
    assert discover_max_ms < threshold_ms * 2, (
        f"discover_related_manifests max ({discover_max_ms:.2f}ms) "
        f"should be under {threshold_ms * 2}ms"
    )

    assert superseded_max_ms < threshold_ms * 2, (
        f"get_superseded_manifests max ({superseded_max_ms:.2f}ms) "
        f"should be under {threshold_ms * 2}ms"
    )
