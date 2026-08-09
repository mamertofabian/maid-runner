"""Pytest configuration and fixtures for MAID Runner tests."""

import os
import sys
from pathlib import Path

import pytest

# Add project root to path for importing scripts
_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))


_GIT_REPOSITORY_POINTERS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_PREFIX",
    "GIT_OBJECT_DIRECTORY",
)


@pytest.fixture(scope="session", autouse=True)
def _isolate_git_repository_environment():
    """Keep test Git subprocesses independent from a hook's repository."""
    inherited_pointers = {
        name: os.environ.pop(name)
        for name in _GIT_REPOSITORY_POINTERS
        if name in os.environ
    }

    yield

    for name in _GIT_REPOSITORY_POINTERS:
        os.environ.pop(name, None)
    os.environ.update(inherited_pointers)


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
