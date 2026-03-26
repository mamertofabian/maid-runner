"""Shared fixtures for CLI tests."""

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _restore_cwd():
    """Automatically restore CWD after each test to prevent pollution."""
    original = Path.cwd()
    yield
    os.chdir(original)
