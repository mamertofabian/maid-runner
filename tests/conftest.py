"""Pytest configuration and fixtures for MAID Runner tests."""

import sys
from pathlib import Path

# Add project root to path for importing scripts
_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))

import pytest


@pytest.fixture(scope="session", autouse=True)
def ensure_claude_files_synced():
    """Ensure maid_runner/claude/ files are synced before tests run.

    The claude files (manifest.json, agents/*.md, commands/*.md) are
    gitignored and generated from .claude/ source files. This fixture
    ensures they exist before any tests that depend on them.
    """
    claude_manifest = _project_root / "maid_runner" / "claude" / "manifest.json"

    # Only sync if the manifest doesn't exist (indicates files need syncing)
    if not claude_manifest.exists():
        from scripts.sync_claude_files import main as sync_claude_files

        sync_claude_files()
