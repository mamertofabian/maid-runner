"""Behavioral tests for task-030: User-friendly error messages.

Tests verify that the error messaging functions work correctly and output
the expected user-friendly messages when manifests directory or files are not found.
"""

import io
from contextlib import redirect_stderr, redirect_stdout

from maid_runner.utils import (
    print_maid_not_enabled_message,
    print_no_manifests_found_message,
)


def test_print_maid_not_enabled_message_stdout():
    """Test print_maid_not_enabled_message outputs to stdout by default."""
    manifest_dir = "/path/to/manifests"

    # Capture stdout
    f = io.StringIO()
    with redirect_stdout(f):
        print_maid_not_enabled_message(manifest_dir, use_stderr=False)

    output = f.getvalue()

    # Verify key messages are present
    assert "This repository does not appear to be MAID-enabled" in output
    assert manifest_dir in output
    assert "manifests directory" in output.lower()
    assert "maid snapshot" in output.lower()


def test_print_maid_not_enabled_message_stderr():
    """Test print_maid_not_enabled_message outputs to stderr when requested."""
    manifest_dir = "/path/to/manifests"

    # Capture stderr
    f = io.StringIO()
    with redirect_stderr(f):
        print_maid_not_enabled_message(manifest_dir, use_stderr=True)

    output = f.getvalue()

    # Verify key messages are present
    assert "This repository does not appear to be MAID-enabled" in output
    assert manifest_dir in output
    assert "manifests directory" in output.lower()


def test_print_no_manifests_found_message_stdout():
    """Test print_no_manifests_found_message outputs to stdout by default."""
    manifest_dir = "/path/to/manifests"

    # Capture stdout
    f = io.StringIO()
    with redirect_stdout(f):
        print_no_manifests_found_message(manifest_dir, use_stderr=False)

    output = f.getvalue()

    # Verify key messages are present
    assert "No manifest files found" in output
    assert manifest_dir in output
    assert "task-*.manifest.json" in output
    assert "maid snapshot" in output.lower()


def test_print_no_manifests_found_message_stderr():
    """Test print_no_manifests_found_message outputs to stderr when requested."""
    manifest_dir = "/path/to/manifests"

    # Capture stderr
    f = io.StringIO()
    with redirect_stderr(f):
        print_no_manifests_found_message(manifest_dir, use_stderr=True)

    output = f.getvalue()

    # Verify key messages are present
    assert "No manifest files found" in output
    assert manifest_dir in output
    assert "task-*.manifest.json" in output


def test_messages_contain_helpful_guidance():
    """Test that both messages contain helpful guidance for users."""
    manifest_dir = "/test/manifests"

    # Test maid_not_enabled message
    f1 = io.StringIO()
    with redirect_stdout(f1):
        print_maid_not_enabled_message(manifest_dir)
    output1 = f1.getvalue()

    # Should suggest creating manifests directory
    assert "Create a 'manifests' directory" in output1 or "create" in output1.lower()

    # Test no_manifests_found message
    f2 = io.StringIO()
    with redirect_stdout(f2):
        print_no_manifests_found_message(manifest_dir)
    output2 = f2.getvalue()

    # Should suggest ways to create manifest files
    assert "maid snapshot" in output2.lower()
    assert (
        "create manifest" in output2.lower() or "generate manifest" in output2.lower()
    )
