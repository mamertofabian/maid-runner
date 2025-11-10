"""Behavioral tests for Task-016: Logging."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_logging_module_can_be_imported():
    """Test logging utils module can be imported."""
    try:
        from maid_agents.utils.logging import setup_logging

        assert callable(setup_logging)
    except ImportError:
        pytest.fail("Cannot import logging module")


def test_setup_logging_function():
    """Test setup_logging function exists and can be called."""
    from maid_agents.utils.logging import setup_logging

    # Call with INFO level
    result = setup_logging(level="INFO")
    assert result is None  # Function returns None


def test_setup_logging_with_different_levels():
    """Test setup_logging with different log levels."""
    from maid_agents.utils.logging import setup_logging

    # Test with DEBUG
    setup_logging(level="DEBUG")

    # Test with WARNING
    setup_logging(level="WARNING")

    # Should not raise errors
    assert True
