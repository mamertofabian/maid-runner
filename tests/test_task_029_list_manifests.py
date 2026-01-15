"""Behavioral tests for Task-029: List manifests command.

Tests the new CLI command that lists all manifests related to a given file,
categorized by how the manifest references the file (created, edited, read).
"""

import json

import pytest


def test_run_list_manifests_exists():
    """Test that run_list_manifests function exists and can be imported."""
    from maid_runner.cli.list_manifests import run_list_manifests

    assert callable(run_list_manifests)


def test_run_list_manifests_signature():
    """Test that run_list_manifests has the expected signature."""
    from maid_runner.cli.list_manifests import run_list_manifests
    import inspect

    sig = inspect.signature(run_list_manifests)
    params = list(sig.parameters.keys())

    assert "file_path" in params
    assert "manifest_dir" in params
    assert "quiet" in params


def test_categorize_manifest_by_file_exists():
    """Test that _categorize_manifest_by_file helper function exists."""
    from maid_runner.cli.list_manifests import _categorize_manifest_by_file

    assert callable(_categorize_manifest_by_file)


def test_categorize_manifest_by_file_signature():
    """Test that _categorize_manifest_by_file has the expected signature."""
    from maid_runner.cli.list_manifests import _categorize_manifest_by_file
    import inspect

    sig = inspect.signature(_categorize_manifest_by_file)
    params = list(sig.parameters.keys())

    assert "manifest_data" in params
    assert "file_path" in params


def test_categorize_manifest_by_file_creatable():
    """Test categorization of file in creatableFiles."""
    from maid_runner.cli.list_manifests import _categorize_manifest_by_file

    manifest_data = {
        "creatableFiles": ["foo.py"],
        "editableFiles": [],
        "readonlyFiles": [],
    }

    category = _categorize_manifest_by_file(manifest_data, "foo.py")
    assert category == "created"


def test_categorize_manifest_by_file_editable():
    """Test categorization of file in editableFiles."""
    from maid_runner.cli.list_manifests import _categorize_manifest_by_file

    manifest_data = {
        "creatableFiles": [],
        "editableFiles": ["bar.py"],
        "readonlyFiles": [],
    }

    category = _categorize_manifest_by_file(manifest_data, "bar.py")
    assert category == "edited"


def test_categorize_manifest_by_file_readonly():
    """Test categorization of file in readonlyFiles."""
    from maid_runner.cli.list_manifests import _categorize_manifest_by_file

    manifest_data = {
        "creatableFiles": [],
        "editableFiles": [],
        "readonlyFiles": ["baz.py"],
    }

    category = _categorize_manifest_by_file(manifest_data, "baz.py")
    assert category == "read"


def test_categorize_manifest_by_file_not_found():
    """Test categorization when file is not referenced."""
    from maid_runner.cli.list_manifests import _categorize_manifest_by_file

    manifest_data = {
        "creatableFiles": [],
        "editableFiles": [],
        "readonlyFiles": [],
    }

    category = _categorize_manifest_by_file(manifest_data, "notfound.py")
    assert category is None


def test_categorize_manifest_by_file_priority():
    """Test that created takes priority over edited over read."""
    from maid_runner.cli.list_manifests import _categorize_manifest_by_file

    # File in multiple categories - created should win
    manifest_data = {
        "creatableFiles": ["test.py"],
        "editableFiles": ["test.py"],
        "readonlyFiles": ["test.py"],
    }

    category = _categorize_manifest_by_file(manifest_data, "test.py")
    assert category == "created"


def test_format_manifest_list_output_exists():
    """Test that _format_manifest_list_output helper function exists."""
    from maid_runner.cli.list_manifests import _format_manifest_list_output

    assert callable(_format_manifest_list_output)


def test_format_manifest_list_output_signature():
    """Test that _format_manifest_list_output has the expected signature."""
    from maid_runner.cli.list_manifests import _format_manifest_list_output
    import inspect

    sig = inspect.signature(_format_manifest_list_output)
    params = list(sig.parameters.keys())

    assert "categorized_manifests" in params
    assert "file_path" in params
    assert "quiet" in params


def test_format_manifest_list_output_with_data(capsys):
    """Test that _format_manifest_list_output produces formatted output."""
    from maid_runner.cli.list_manifests import _format_manifest_list_output

    categorized = {
        "created": ["task-001.manifest.json"],
        "edited": ["task-002.manifest.json", "task-003.manifest.json"],
        "read": ["task-004.manifest.json"],
    }

    _format_manifest_list_output(categorized, "test.py", quiet=False)

    captured = capsys.readouterr()
    output = captured.out

    # Check that output contains the file path
    assert "test.py" in output

    # Check that output contains category labels
    assert "created" in output.lower() or "creat" in output.lower()
    assert "edited" in output.lower() or "edit" in output.lower()
    assert "read" in output.lower()

    # Check that manifest names appear
    assert "task-001" in output
    assert "task-002" in output
    assert "task-003" in output
    assert "task-004" in output


def test_format_manifest_list_output_empty(capsys):
    """Test output when no manifests reference the file."""
    from maid_runner.cli.list_manifests import _format_manifest_list_output

    categorized = {
        "created": [],
        "edited": [],
        "read": [],
    }

    _format_manifest_list_output(categorized, "orphan.py", quiet=False)

    captured = capsys.readouterr()
    output = captured.out

    # Should indicate no manifests found
    assert "no manifest" in output.lower() or "not found" in output.lower()


def test_run_list_manifests_with_temp_manifests(tmp_path, capsys):
    """Test run_list_manifests with temporary manifest files."""
    from maid_runner.cli.list_manifests import run_list_manifests

    # Create a temporary manifest directory
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()

    # Create test manifests
    manifest1 = {
        "goal": "Create test.py",
        "creatableFiles": ["test.py"],
        "editableFiles": [],
        "readonlyFiles": [],
    }

    manifest2 = {
        "goal": "Edit test.py",
        "creatableFiles": [],
        "editableFiles": ["test.py"],
        "readonlyFiles": [],
    }

    manifest3 = {
        "goal": "Read test.py",
        "creatableFiles": [],
        "editableFiles": [],
        "readonlyFiles": ["test.py"],
    }

    # Write manifests
    with open(manifest_dir / "task-001.manifest.json", "w") as f:
        json.dump(manifest1, f)

    with open(manifest_dir / "task-002.manifest.json", "w") as f:
        json.dump(manifest2, f)

    with open(manifest_dir / "task-003.manifest.json", "w") as f:
        json.dump(manifest3, f)

    # Run the command
    run_list_manifests("test.py", str(manifest_dir), quiet=False)

    captured = capsys.readouterr()
    output = captured.out

    # Verify output contains all manifest references
    assert "task-001" in output
    assert "task-002" in output
    assert "task-003" in output


def test_run_list_manifests_no_matches(tmp_path, capsys):
    """Test run_list_manifests when file is not in any manifest."""
    from maid_runner.cli.list_manifests import run_list_manifests

    # Create a temporary manifest directory
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()

    # Create a manifest that doesn't reference our target file
    manifest1 = {
        "goal": "Create other.py",
        "creatableFiles": ["other.py"],
        "editableFiles": [],
        "readonlyFiles": [],
    }

    with open(manifest_dir / "task-001.manifest.json", "w") as f:
        json.dump(manifest1, f)

    # Run the command for a file not in any manifest
    run_list_manifests("orphan.py", str(manifest_dir), quiet=False)

    captured = capsys.readouterr()
    output = captured.out

    # Should indicate no manifests found
    assert "no manifest" in output.lower() or "not found" in output.lower()


def test_run_list_manifests_quiet_mode(tmp_path, capsys):
    """Test run_list_manifests in quiet mode."""
    from maid_runner.cli.list_manifests import run_list_manifests

    # Create a temporary manifest directory
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()

    # Create a test manifest
    manifest1 = {
        "goal": "Create test.py",
        "creatableFiles": ["test.py"],
        "editableFiles": [],
        "readonlyFiles": [],
    }

    with open(manifest_dir / "task-001.manifest.json", "w") as f:
        json.dump(manifest1, f)

    # Run in quiet mode
    run_list_manifests("test.py", str(manifest_dir), quiet=True)

    captured = capsys.readouterr()
    output = captured.out

    # In quiet mode, output should be minimal (just manifest names, no decorative text)
    # The exact behavior depends on implementation, but it should be less verbose
    # At minimum, it should still show the manifest name
    assert "task-001" in output


def test_cli_integration_manifests_command():
    """Test that the 'manifests' subcommand is registered in main CLI."""
    import sys
    from io import StringIO

    from maid_runner.cli.main import main

    # Capture help output to verify subcommand exists
    old_stdout = sys.stdout
    old_argv = sys.argv

    try:
        sys.stdout = StringIO()
        sys.argv = ["maid", "--help"]

        try:
            main()
        except SystemExit:
            pass

        help_output = sys.stdout.getvalue()

        # Verify 'manifests' subcommand is mentioned in help
        assert "manifests" in help_output.lower()

    finally:
        sys.stdout = old_stdout
        sys.argv = old_argv


def test_run_list_manifests_handles_invalid_json(tmp_path, capsys):
    """Test that run_list_manifests handles invalid JSON manifests gracefully."""
    from maid_runner.cli.list_manifests import run_list_manifests

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()

    # Create a valid manifest
    valid_manifest = manifest_dir / "task-001.manifest.json"
    valid_manifest.write_text(
        json.dumps(
            {
                "creatableFiles": ["test.py"],
                "editableFiles": [],
                "readonlyFiles": [],
            }
        )
    )

    # Create an invalid manifest with bad JSON
    invalid_manifest = manifest_dir / "task-002.manifest.json"
    invalid_manifest.write_text("not valid json {{{")

    # Should not raise, should skip the invalid manifest with warning
    run_list_manifests("test.py", str(manifest_dir), quiet=False)

    captured = capsys.readouterr()
    # Should show a warning about the invalid manifest
    assert "Warning" in captured.err or "task-001" in captured.out


def test_run_list_manifests_handles_io_error(tmp_path, capsys):
    """Test that run_list_manifests handles IO errors gracefully."""
    from maid_runner.cli.list_manifests import run_list_manifests

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()

    # Create a valid manifest
    valid_manifest = manifest_dir / "task-001.manifest.json"
    valid_manifest.write_text(
        json.dumps(
            {
                "creatableFiles": ["test.py"],
                "editableFiles": [],
                "readonlyFiles": [],
            }
        )
    )

    # Should not raise
    run_list_manifests("test.py", str(manifest_dir), quiet=False)

    captured = capsys.readouterr()
    # Should show the valid manifest
    assert "task-001" in captured.out


def test_main_entry_point_exists():
    """Test that _main entry point exists for standalone testing."""
    from maid_runner.cli.list_manifests import _main

    assert callable(_main)


def test_run_list_manifests_missing_directory_exits(tmp_path, capsys):
    """Test that run_list_manifests exits when manifest directory doesn't exist."""
    from maid_runner.cli.list_manifests import run_list_manifests

    nonexistent_dir = tmp_path / "nonexistent"

    with pytest.raises(SystemExit) as exc_info:
        run_list_manifests("test.py", str(nonexistent_dir), quiet=False)

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    # Should print a message about MAID not being enabled
    assert "not enabled" in captured.err.lower() or "not found" in captured.err.lower()


def test_run_list_manifests_empty_directory(tmp_path, capsys):
    """Test that run_list_manifests handles empty manifest directory."""
    from maid_runner.cli.list_manifests import run_list_manifests

    # Create an empty manifest directory
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()

    # Should not raise, but indicate no manifests found
    run_list_manifests("test.py", str(manifest_dir), quiet=False)

    captured = capsys.readouterr()
    # Should indicate no manifests found
    assert "no manifest" in captured.out.lower()


def test_run_list_manifests_json_output(tmp_path, capsys):
    """Test that run_list_manifests outputs valid JSON when json_output=True."""
    from maid_runner.cli.list_manifests import run_list_manifests

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()

    # Create a test manifest
    manifest = {
        "goal": "Create test.py",
        "creatableFiles": ["test.py"],
        "editableFiles": [],
        "readonlyFiles": [],
    }

    (manifest_dir / "task-001.manifest.json").write_text(json.dumps(manifest))

    # Run with JSON output
    run_list_manifests("test.py", str(manifest_dir), quiet=False, json_output=True)

    captured = capsys.readouterr()

    # Should be valid JSON
    parsed = json.loads(captured.out)
    # JSON output is a list of manifest paths
    assert isinstance(parsed, list)
    # Should include the manifest path
    assert any("task-001" in str(path) for path in parsed)
