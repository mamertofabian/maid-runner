# tests/validators/test_task_028_file_tracking.py
from pathlib import Path
from maid_runner.validators.file_tracker import (
    FILE_STATUS_UNDECLARED,
    FILE_STATUS_REGISTERED,
    FILE_STATUS_TRACKED,
    find_source_files,
    collect_tracked_files,
    classify_file_status,
    analyze_file_tracking,
)


# ============================================================================
# Test Constants and Status Classification
# ============================================================================


def test_file_status_constants_exist():
    """Test that file status constants are defined."""
    assert FILE_STATUS_UNDECLARED == "UNDECLARED"
    assert FILE_STATUS_REGISTERED == "REGISTERED"
    assert FILE_STATUS_TRACKED == "TRACKED"


# ============================================================================
# Test File Discovery
# ============================================================================


def test_find_source_files_discovers_python_files(tmp_path: Path):
    """Test that find_source_files discovers all Python files."""
    # Create test structure
    (tmp_path / "module.py").write_text("# module")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "file.py").write_text("# file")
    (tmp_path / "another.py").write_text("# another")

    files = find_source_files(str(tmp_path), exclude_patterns=[])

    assert "module.py" in files
    assert "subdir/file.py" in files
    assert "another.py" in files


def test_find_source_files_excludes_pycache(tmp_path: Path):
    """Test that __pycache__ directories are excluded."""
    (tmp_path / "module.py").write_text("# module")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "module.cpython-312.pyc").write_text("bytecode")

    files = find_source_files(str(tmp_path), exclude_patterns=["**/__pycache__/**"])

    assert "module.py" in files
    assert "__pycache__/module.cpython-312.pyc" not in files


def test_find_source_files_excludes_venv(tmp_path: Path):
    """Test that virtual environment directories are excluded."""
    (tmp_path / "app.py").write_text("# app")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "lib").mkdir(parents=True)
    (tmp_path / ".venv" / "lib" / "python.py").write_text("# stdlib")

    files = find_source_files(str(tmp_path), exclude_patterns=[".venv/**"])

    assert "app.py" in files
    assert ".venv/lib/python.py" not in files


def test_find_source_files_with_custom_exclude_patterns(tmp_path: Path):
    """Test that custom exclude patterns work."""
    (tmp_path / "app.py").write_text("# app")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("# test")
    (tmp_path / "experiments").mkdir()
    (tmp_path / "experiments" / "exp.py").write_text("# experiment")

    files = find_source_files(
        str(tmp_path), exclude_patterns=["tests/**", "experiments/**"]
    )

    assert "app.py" in files
    assert "tests/test_app.py" not in files
    assert "experiments/exp.py" not in files


# ============================================================================
# Test Tracked Files Collection
# ============================================================================


def test_collect_tracked_files_from_creatableFiles():
    """Test collecting files from creatableFiles."""
    manifest_chain = [
        {
            "goal": "Create new module",
            "creatableFiles": ["module.py"],
            "expectedArtifacts": {
                "file": "module.py",
                "contains": [{"type": "function", "name": "main"}],
            },
            "validationCommand": ["pytest", "tests/test_module.py"],
        }
    ]

    tracked = collect_tracked_files(manifest_chain)

    assert "module.py" in tracked
    assert tracked["module.py"]["created"] is True
    assert tracked["module.py"]["has_artifacts"] is True
    assert tracked["module.py"]["has_tests"] is True


def test_collect_tracked_files_from_editableFiles():
    """Test collecting files from editableFiles."""
    manifest_chain = [
        {
            "goal": "Edit existing module",
            "editableFiles": ["module.py"],
            "expectedArtifacts": {
                "file": "module.py",
                "contains": [{"type": "function", "name": "updated_func"}],
            },
            "validationCommand": ["pytest", "tests/test_module.py"],
        }
    ]

    tracked = collect_tracked_files(manifest_chain)

    assert "module.py" in tracked
    assert tracked["module.py"]["edited"] is True
    assert tracked["module.py"]["has_artifacts"] is True


def test_collect_tracked_files_from_readonlyFiles():
    """Test collecting files from readonlyFiles."""
    manifest_chain = [
        {
            "goal": "Use utility",
            "creatableFiles": ["app.py"],
            "readonlyFiles": ["utils.py"],
            "expectedArtifacts": {
                "file": "app.py",
                "contains": [{"type": "function", "name": "main"}],
            },
            "validationCommand": ["pytest", "tests/test_app.py"],
        }
    ]

    tracked = collect_tracked_files(manifest_chain)

    assert "utils.py" in tracked
    assert tracked["utils.py"]["readonly"] is True
    assert tracked["utils.py"]["created"] is False


def test_collect_tracked_files_handles_multiple_manifests():
    """Test that files appearing in multiple manifests are properly tracked."""
    manifest_chain = [
        {
            "goal": "Create module",
            "creatableFiles": ["module.py"],
            "expectedArtifacts": {
                "file": "module.py",
                "contains": [{"type": "function", "name": "func1"}],
            },
            "validationCommand": ["pytest", "tests/test_module.py"],
        },
        {
            "goal": "Update module",
            "editableFiles": ["module.py"],
            "expectedArtifacts": {
                "file": "module.py",
                "contains": [{"type": "function", "name": "func2"}],
            },
            "validationCommand": ["pytest", "tests/test_module.py"],
        },
    ]

    tracked = collect_tracked_files(manifest_chain)

    assert "module.py" in tracked
    assert tracked["module.py"]["created"] is True
    assert tracked["module.py"]["edited"] is True
    assert len(tracked["module.py"]["manifests"]) == 2


# ============================================================================
# Test File Status Classification
# ============================================================================


def test_classify_file_status_undeclared():
    """Test that files not in tracked_info are classified as UNDECLARED."""
    status, issues = classify_file_status("untracked.py", tracked_info=None)

    assert status == FILE_STATUS_UNDECLARED
    assert "Not found in any manifest" in issues[0]


def test_classify_file_status_registered_readonly_only():
    """Test that files only in readonlyFiles are REGISTERED."""
    tracked_info = {
        "readonly": True,
        "created": False,
        "edited": False,
        "has_artifacts": False,
        "has_tests": False,
        "manifests": ["task-001"],
    }

    status, issues = classify_file_status("utils.py", tracked_info)

    assert status == FILE_STATUS_REGISTERED
    assert any("Only in readonlyFiles" in issue for issue in issues)


def test_classify_file_status_registered_no_artifacts():
    """Test that files without artifacts are REGISTERED."""
    tracked_info = {
        "readonly": False,
        "created": False,
        "edited": True,
        "has_artifacts": False,
        "has_tests": False,
        "manifests": ["task-005"],
    }

    status, issues = classify_file_status("module.py", tracked_info)

    assert status == FILE_STATUS_REGISTERED
    assert any("no expectedArtifacts" in issue for issue in issues)


def test_classify_file_status_registered_no_tests():
    """Test that files without tests are REGISTERED."""
    tracked_info = {
        "readonly": False,
        "created": True,
        "edited": False,
        "has_artifacts": True,
        "has_tests": False,
        "manifests": ["task-010"],
    }

    status, issues = classify_file_status("service.py", tracked_info)

    assert status == FILE_STATUS_REGISTERED
    assert any("no behavioral tests" in issue for issue in issues)


def test_classify_file_status_tracked():
    """Test that fully compliant files are TRACKED."""
    tracked_info = {
        "readonly": False,
        "created": True,
        "edited": False,
        "has_artifacts": True,
        "has_tests": True,
        "manifests": ["task-015"],
    }

    status, issues = classify_file_status("complete.py", tracked_info)

    assert status == FILE_STATUS_TRACKED
    assert len(issues) == 0


def test_classify_file_status_tracked_with_edits():
    """Test that files created then edited are still TRACKED if compliant."""
    tracked_info = {
        "readonly": False,
        "created": True,
        "edited": True,
        "has_artifacts": True,
        "has_tests": True,
        "manifests": ["task-001", "task-010"],
    }

    status, issues = classify_file_status("evolving.py", tracked_info)

    assert status == FILE_STATUS_TRACKED
    assert len(issues) == 0


# ============================================================================
# Test Full Analysis
# ============================================================================


def test_analyze_file_tracking_integration(tmp_path: Path):
    """Test full file tracking analysis with mixed file statuses."""
    # Create test files
    (tmp_path / "tracked.py").write_text("# fully tracked")
    (tmp_path / "registered.py").write_text("# registered only")
    (tmp_path / "undeclared.py").write_text("# not in manifests")

    manifest_chain = [
        {
            "goal": "Create tracked module",
            "creatableFiles": ["tracked.py"],
            "expectedArtifacts": {
                "file": "tracked.py",
                "contains": [{"type": "function", "name": "main"}],
            },
            "validationCommand": ["pytest", "tests/test_tracked.py"],
        },
        {
            "goal": "Use registered module",
            "creatableFiles": ["app.py"],
            "readonlyFiles": ["registered.py"],
            "expectedArtifacts": {"file": "app.py", "contains": []},
            "validationCommand": ["echo", "test"],
        },
    ]

    analysis = analyze_file_tracking(manifest_chain, str(tmp_path))

    # Check that all categories are present
    assert "undeclared" in analysis
    assert "registered" in analysis
    assert "tracked" in analysis

    # Check undeclared files
    undeclared_files = [f["file"] for f in analysis["undeclared"]]
    assert "undeclared.py" in undeclared_files

    # Check registered files
    registered_files = [f["file"] for f in analysis["registered"]]
    assert "registered.py" in registered_files

    # Check tracked files
    assert "tracked.py" in analysis["tracked"]


def test_analyze_file_tracking_empty_codebase(tmp_path: Path):
    """Test analysis with empty codebase."""
    manifest_chain = []

    analysis = analyze_file_tracking(manifest_chain, str(tmp_path))

    assert len(analysis["undeclared"]) == 0
    assert len(analysis["registered"]) == 0
    assert len(analysis["tracked"]) == 0


def test_analyze_file_tracking_all_tracked(tmp_path: Path):
    """Test analysis when all files are fully tracked."""
    (tmp_path / "module1.py").write_text("# module1")
    (tmp_path / "module2.py").write_text("# module2")

    manifest_chain = [
        {
            "goal": "Create modules",
            "creatableFiles": ["module1.py", "module2.py"],
            "expectedArtifacts": {
                "file": "module1.py",
                "contains": [{"type": "function", "name": "func"}],
            },
            "validationCommand": ["pytest", "tests/"],
        }
    ]

    analysis = analyze_file_tracking(manifest_chain, str(tmp_path))

    assert len(analysis["undeclared"]) == 0
    # module2.py might be REGISTERED (no artifacts for it specifically)
    assert "module1.py" in analysis["tracked"]
