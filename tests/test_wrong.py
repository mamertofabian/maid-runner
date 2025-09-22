# tests/test_wrong.py
"""Test file that intentionally doesn't use expected artifacts (for testing failures)."""


def test_something_else():
    """A test that doesn't use the expected calculate_total function."""
    # This test intentionally doesn't call calculate_total
    result = 42
    assert result == 42