# tests/validators/test_task_146_track_validationcommand_test_files.py
"""Behavioral tests for tracking test files from validationCommand fields.

Test files referenced in validationCommand or validationCommands fields should
be tracked, not reported as UNTRACKED TEST FILES. This module tests that
collect_tracked_files() and analyze_file_tracking() properly extract and track
test files from validation commands.
"""

from pathlib import Path
from maid_runner.validators.file_tracker import (
    collect_tracked_files,
    analyze_file_tracking,
)


# ============================================================================
# Test collect_tracked_files() extracts test files from validationCommand
# ============================================================================


def test_collect_tracked_files_includes_test_from_validationcommand():
    """Test that test files from validationCommand are included in tracked files."""
    manifest_chain = [
        {
            "goal": "Create feature module",
            "creatableFiles": ["src/module.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/module.py",
                "contains": [{"type": "function", "name": "my_func"}],
            },
            "validationCommand": ["pytest", "tests/test_module.py", "-v"],
        }
    ]

    tracked = collect_tracked_files(manifest_chain)

    # Test file from validationCommand should be tracked
    assert "tests/test_module.py" in tracked
    assert tracked["tests/test_module.py"]["has_tests"] is True


def test_collect_tracked_files_includes_tests_from_validationcommands():
    """Test that test files from validationCommands (array) are tracked."""
    manifest_chain = [
        {
            "goal": "Create feature",
            "creatableFiles": ["src/app.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/app.py",
                "contains": [{"type": "function", "name": "run"}],
            },
            "validationCommands": [
                ["pytest", "tests/test_app.py", "-v"],
                ["pytest", "tests/test_integration.py", "-v"],
            ],
        }
    ]

    tracked = collect_tracked_files(manifest_chain)

    # Both test files from validationCommands should be tracked
    assert "tests/test_app.py" in tracked
    assert "tests/test_integration.py" in tracked


def test_collect_tracked_files_handles_single_string_command():
    """Test tracking test files from single-string command format."""
    manifest_chain = [
        {
            "goal": "Create utility",
            "creatableFiles": ["utils.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "utils.py",
                "contains": [{"type": "function", "name": "helper"}],
            },
            "validationCommand": ["pytest tests/test_utils.py -v"],
        }
    ]

    tracked = collect_tracked_files(manifest_chain)

    # Test file from single-string command should be tracked
    assert "tests/test_utils.py" in tracked


def test_collect_tracked_files_handles_node_id_format():
    """Test tracking test files from pytest node ID format (file::class::method)."""
    manifest_chain = [
        {
            "goal": "Create service",
            "creatableFiles": ["service.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "service.py",
                "contains": [{"type": "class", "name": "Service"}],
            },
            "validationCommand": [
                "pytest",
                "tests/test_service.py::TestService::test_method",
                "-v",
            ],
        }
    ]

    tracked = collect_tracked_files(manifest_chain)

    # File path extracted from node ID should be tracked
    assert "tests/test_service.py" in tracked


def test_collect_tracked_files_handles_uv_run_prefix():
    """Test tracking test files from command with uv run prefix."""
    manifest_chain = [
        {
            "goal": "Create handler",
            "creatableFiles": ["handler.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "handler.py",
                "contains": [{"type": "function", "name": "handle"}],
            },
            "validationCommand": ["uv", "run", "pytest", "tests/test_handler.py", "-v"],
        }
    ]

    tracked = collect_tracked_files(manifest_chain)

    # Test file after uv run prefix should be tracked
    assert "tests/test_handler.py" in tracked


# ============================================================================
# Test analyze_file_tracking() does NOT report validationCommand tests as untracked
# ============================================================================


def test_analyze_file_tracking_validationcommand_tests_not_in_untracked(
    tmp_path: Path,
):
    """Test that test files from validationCommand do NOT appear in untracked_tests."""
    # Create the test file in the filesystem
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_feature.py").write_text("# test file")

    manifest_chain = [
        {
            "goal": "Create feature",
            "creatableFiles": ["feature.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "feature.py",
                "contains": [{"type": "function", "name": "run"}],
            },
            "validationCommand": ["pytest", "tests/test_feature.py", "-v"],
        }
    ]

    analysis = analyze_file_tracking(manifest_chain, str(tmp_path))

    # Test file should be tracked, NOT in untracked_tests
    assert "tests/test_feature.py" not in analysis["untracked_tests"]
    assert "tests/test_feature.py" in analysis["tracked"]


def test_analyze_file_tracking_validationcommands_tests_not_in_untracked(
    tmp_path: Path,
):
    """Test that test files from validationCommands do NOT appear in untracked_tests."""
    # Create test files
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_unit.py").write_text("# unit test")
    (tmp_path / "tests" / "test_integration.py").write_text("# integration test")

    manifest_chain = [
        {
            "goal": "Create app",
            "creatableFiles": ["app.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "app.py",
                "contains": [{"type": "function", "name": "main"}],
            },
            "validationCommands": [
                ["pytest", "tests/test_unit.py", "-v"],
                ["pytest", "tests/test_integration.py", "-v"],
            ],
        }
    ]

    analysis = analyze_file_tracking(manifest_chain, str(tmp_path))

    # Both test files should be tracked, NOT in untracked_tests
    assert "tests/test_unit.py" not in analysis["untracked_tests"]
    assert "tests/test_integration.py" not in analysis["untracked_tests"]
    assert "tests/test_unit.py" in analysis["tracked"]
    assert "tests/test_integration.py" in analysis["tracked"]


def test_analyze_file_tracking_mixed_tracked_and_untracked_tests(tmp_path: Path):
    """Test that only tests NOT in manifests appear in untracked_tests."""
    # Create test files
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_tracked.py").write_text(
        "# tracked via validationCommand"
    )
    (tmp_path / "tests" / "test_untracked.py").write_text("# not in any manifest")

    manifest_chain = [
        {
            "goal": "Create module",
            "creatableFiles": ["module.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "module.py",
                "contains": [{"type": "function", "name": "func"}],
            },
            "validationCommand": ["pytest", "tests/test_tracked.py", "-v"],
        }
    ]

    analysis = analyze_file_tracking(manifest_chain, str(tmp_path))

    # test_tracked.py should be tracked (from validationCommand)
    assert "tests/test_tracked.py" not in analysis["untracked_tests"]
    assert "tests/test_tracked.py" in analysis["tracked"]

    # test_untracked.py should be in untracked_tests (not in any manifest)
    assert "tests/test_untracked.py" in analysis["untracked_tests"]


def test_analyze_file_tracking_test_in_readonly_and_validationcommand(tmp_path: Path):
    """Test that test files in both readonlyFiles and validationCommand are tracked."""
    # Create test file
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_module.py").write_text("# test file")

    manifest_chain = [
        {
            "goal": "Create module",
            "creatableFiles": ["module.py"],
            "readonlyFiles": ["tests/test_module.py"],  # Also in readonlyFiles
            "expectedArtifacts": {
                "file": "module.py",
                "contains": [{"type": "function", "name": "func"}],
            },
            "validationCommand": ["pytest", "tests/test_module.py", "-v"],
        }
    ]

    analysis = analyze_file_tracking(manifest_chain, str(tmp_path))

    # Test file should be tracked, not in untracked_tests
    assert "tests/test_module.py" not in analysis["untracked_tests"]
    assert "tests/test_module.py" in analysis["tracked"]


# ============================================================================
# Test various pytest command formats are handled correctly
# ============================================================================


def test_collect_tracked_files_multiple_test_files_in_command():
    """Test tracking multiple test files from a single validationCommand."""
    manifest_chain = [
        {
            "goal": "Create feature",
            "creatableFiles": ["feature.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "feature.py",
                "contains": [{"type": "function", "name": "run"}],
            },
            "validationCommand": [
                "pytest",
                "tests/test_a.py",
                "tests/test_b.py",
                "-v",
            ],
        }
    ]

    tracked = collect_tracked_files(manifest_chain)

    # Both test files should be tracked
    assert "tests/test_a.py" in tracked
    assert "tests/test_b.py" in tracked


def test_collect_tracked_files_ignores_pytest_flags():
    """Test that pytest flags are not mistakenly treated as test files."""
    manifest_chain = [
        {
            "goal": "Create feature",
            "creatableFiles": ["feature.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "feature.py",
                "contains": [{"type": "function", "name": "run"}],
            },
            "validationCommand": [
                "pytest",
                "tests/test_feature.py",
                "-v",
                "--cov",
                "src",
                "--tb=short",
            ],
        }
    ]

    tracked = collect_tracked_files(manifest_chain)

    # Only the actual test file should be tracked
    assert "tests/test_feature.py" in tracked
    # Flags should not be treated as files
    assert "-v" not in tracked
    assert "--cov" not in tracked
    assert "src" not in tracked  # This is a cov argument, not a test file


def test_collect_tracked_files_no_validationcommand():
    """Test that manifests without validationCommand are handled gracefully."""
    manifest_chain = [
        {
            "goal": "Create utility",
            "creatableFiles": ["utility.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "utility.py",
                "contains": [{"type": "function", "name": "help"}],
            },
            # No validationCommand
        }
    ]

    tracked = collect_tracked_files(manifest_chain)

    # Should still work, only creatableFiles tracked
    assert "utility.py" in tracked
    # No test files should be extracted (none specified)
    test_files = [f for f in tracked.keys() if f.startswith("tests/")]
    assert len(test_files) == 0


# ============================================================================
# Test vitest and other test runners are supported
# ============================================================================


def test_collect_tracked_files_includes_test_from_vitest_command():
    """Test that test files from vitest validationCommand are tracked."""
    manifest_chain = [
        {
            "goal": "Create TypeScript module",
            "creatableFiles": ["src/module.ts"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/module.ts",
                "contains": [{"type": "function", "name": "my_func"}],
            },
            "validationCommand": [
                "pnpm",
                "exec",
                "vitest",
                "run",
                "tests/test_module.spec.ts",
            ],
        }
    ]

    tracked = collect_tracked_files(manifest_chain)

    # Test file from vitest validationCommand should be tracked
    assert "tests/test_module.spec.ts" in tracked
    assert tracked["tests/test_module.spec.ts"]["has_tests"] is True


def test_collect_tracked_files_includes_test_from_vitest_without_exec():
    """Test that test files from vitest command without pnpm exec are tracked."""
    manifest_chain = [
        {
            "goal": "Create feature",
            "creatableFiles": ["feature.ts"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "feature.ts",
                "contains": [{"type": "function", "name": "run"}],
            },
            "validationCommand": ["vitest", "run", "tests/test_feature.spec.ts"],
        }
    ]

    tracked = collect_tracked_files(manifest_chain)

    # Test file from vitest command should be tracked
    assert "tests/test_feature.spec.ts" in tracked


def test_collect_tracked_files_includes_test_from_jest_command():
    """Test that test files from jest validationCommand are tracked."""
    manifest_chain = [
        {
            "goal": "Create component",
            "creatableFiles": ["component.js"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "component.js",
                "contains": [{"type": "function", "name": "render"}],
            },
            "validationCommand": ["jest", "tests/test_component.test.js"],
        }
    ]

    tracked = collect_tracked_files(manifest_chain)

    # Test file from jest validationCommand should be tracked
    assert "tests/test_component.test.js" in tracked


def test_collect_tracked_files_handles_vitest_with_flags():
    """Test that vitest commands with flags still extract test files correctly."""
    manifest_chain = [
        {
            "goal": "Create service",
            "creatableFiles": ["service.ts"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "service.ts",
                "contains": [{"type": "class", "name": "Service"}],
            },
            "validationCommand": [
                "vitest",
                "run",
                "--reporter=verbose",
                "tests/test_service.spec.ts",
            ],
        }
    ]

    tracked = collect_tracked_files(manifest_chain)

    # Test file should be tracked, flags should be ignored
    assert "tests/test_service.spec.ts" in tracked
    assert "--reporter=verbose" not in tracked


def test_analyze_file_tracking_vitest_tests_not_in_untracked(tmp_path: Path):
    """Test that test files from vitest validationCommand do NOT appear in untracked_tests."""
    # Create the test file in the filesystem
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_extension.test.ts").write_text("// test file")

    manifest_chain = [
        {
            "goal": "Create extension",
            "creatableFiles": ["extension.ts"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "extension.ts",
                "contains": [{"type": "function", "name": "activate"}],
            },
            "validationCommand": [
                "pnpm",
                "exec",
                "vitest",
                "run",
                "tests/test_extension.test.ts",
            ],
        }
    ]

    analysis = analyze_file_tracking(manifest_chain, str(tmp_path))

    # Test file should be tracked, NOT in untracked_tests
    assert "tests/test_extension.test.ts" not in analysis["untracked_tests"]
    assert "tests/test_extension.test.ts" in analysis["tracked"]
