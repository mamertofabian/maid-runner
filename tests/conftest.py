"""Pytest configuration and fixtures for MAID Runner tests."""

from __future__ import annotations

from collections.abc import Iterator
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.support.git_project_templates import GitProjectTemplateFactory

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

_GIT_CONFIG_ISOLATION = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def load_git_project_template_factory() -> type[GitProjectTemplateFactory] | None:
    """Load optional template support without masking broken dependencies."""
    try:
        from tests.support.git_project_templates import GitProjectTemplateFactory
    except ModuleNotFoundError as exc:
        if exc.name == "tests.support.git_project_templates":
            return None
        raise

    return GitProjectTemplateFactory


@pytest.fixture(scope="session")
def git_project_template_factory(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[GitProjectTemplateFactory]:
    """Provide one worker-local immutable Git-template cache."""
    factory_type = load_git_project_template_factory()
    if factory_type is None:

        class _MissingGitProjectTemplateFactory:
            def get(self, shape: str):
                raise AssertionError("Git project template support is not implemented")

        yield _MissingGitProjectTemplateFactory()  # type: ignore[misc]
        return

    yield factory_type(tmp_path_factory.mktemp("git-project-templates"))


@pytest.fixture(scope="session", autouse=True)
def _isolate_git_repository_environment():
    """Keep test Git subprocesses independent from ambient Git state."""
    inherited_environment = {
        name: os.environ.pop(name)
        for name in (*_GIT_REPOSITORY_POINTERS, *_GIT_CONFIG_ISOLATION)
        if name in os.environ
    }
    os.environ.update(_GIT_CONFIG_ISOLATION)

    yield

    for name in (*_GIT_REPOSITORY_POINTERS, *_GIT_CONFIG_ISOLATION):
        os.environ.pop(name, None)
    os.environ.update(inherited_environment)


@pytest.fixture(scope="session", autouse=True)
def ensure_claude_files_synced():
    """Ensure maid_runner/claude/ files are synced before tests run.

    The claude files (manifest.json, agents/*.md, commands/*.md) are
    gitignored and generated from .claude/ source files. This fixture
    ensures they exist before any tests that depend on them.
    """
    claude_manifest = _project_root / "maid_runner" / "claude" / "manifest.json"

    # Only sync if the manifest doesn't exist (indicates files need syncing)
    if not claude_manifest.exists() and os.environ.get("UV_NO_SYNC") != "1":
        from scripts.sync_claude_files import main as sync_claude_files

        sync_claude_files()
