# tests/cli/test_task_037_fix_manifests_label.py
"""Behavioral tests for showing manifest filenames in registered files output.

The registered files output shows manifest filenames (e.g., 'task-013-pypi-packaging.manifest.json')
with the 'Manifests:' label for clarity.
"""

import io
import sys
from maid_runner.cli.validate import _format_file_tracking_output


def test_registered_files_uses_manifests_label():
    """Test that registered files output uses 'Manifests:' label with filenames."""
    analysis = {
        "undeclared": [],
        "registered": [
            {
                "file": "example.py",
                "status": "REGISTERED",
                "issues": ["Only in readonlyFiles (no creation/edit record)"],
                "manifests": ["task-001-example.manifest.json"],
            }
        ],
        "tracked": [],
        "untracked_tests": [],
    }

    # Capture output
    captured_output = io.StringIO()
    sys.stdout = captured_output

    try:
        _format_file_tracking_output(analysis, quiet=False)
    finally:
        sys.stdout = sys.__stdout__

    output = captured_output.getvalue()

    # Should use "Manifests:" with filenames
    assert "Manifests:" in output
    assert "task-001-example.manifest.json" in output


def test_registered_files_shows_manifest_filenames():
    """Test that registered files show manifest filenames."""
    analysis = {
        "undeclared": [],
        "registered": [
            {
                "file": "utils.py",
                "status": "REGISTERED",
                "issues": ["Only in readonlyFiles (no creation/edit record)"],
                "manifests": [
                    "task-005-create-utils.manifest.json",
                    "task-010-add-logging.manifest.json",
                ],
            }
        ],
        "tracked": [],
        "untracked_tests": [],
    }

    # Capture output
    captured_output = io.StringIO()
    sys.stdout = captured_output

    try:
        _format_file_tracking_output(analysis, quiet=False)
    finally:
        sys.stdout = sys.__stdout__

    output = captured_output.getvalue()

    # Should show both manifest filenames
    assert "task-005-create-utils.manifest.json" in output
    assert "task-010-add-logging.manifest.json" in output


def test_registered_files_label_with_quiet_mode():
    """Test that quiet mode doesn't show the label (no details shown)."""
    analysis = {
        "undeclared": [],
        "registered": [
            {
                "file": "example.py",
                "status": "REGISTERED",
                "issues": ["Only in readonlyFiles (no creation/edit record)"],
                "manifests": ["task-001-example.manifest.json"],
            }
        ],
        "tracked": [],
        "untracked_tests": [],
    }

    # Capture output
    captured_output = io.StringIO()
    sys.stdout = captured_output

    try:
        _format_file_tracking_output(analysis, quiet=True)
    finally:
        sys.stdout = sys.__stdout__

    output = captured_output.getvalue()

    # In quiet mode, details (including the label) should not appear
    assert "Manifests:" not in output
    assert "task-001-example.manifest.json" not in output
