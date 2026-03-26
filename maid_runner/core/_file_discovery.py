"""Source file discovery for MAID Runner v2 file tracking."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Union

_EXCLUDE_DIRS = {
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".eggs",
    "*.egg-info",
    ".tox",
    ".nox",
}

_SOURCE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".svelte"}

_TEST_PATTERNS = [
    re.compile(r"test_.*\.py$"),
    re.compile(r".*_test\.py$"),
    re.compile(r".*\.test\.(ts|tsx|js|jsx)$"),
    re.compile(r".*\.spec\.(ts|tsx|js|jsx)$"),
]


def discover_source_files(
    project_root: Union[str, Path],
    extensions: set[str] | None = None,
) -> list[str]:
    """Discover all source files in a project, excluding common non-source dirs."""
    root = Path(project_root)
    exts = extensions or _SOURCE_EXTENSIONS
    files: list[str] = []

    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if path.suffix not in exts:
            continue
        # Skip excluded directories
        parts = path.relative_to(root).parts
        if any(part in _EXCLUDE_DIRS for part in parts):
            continue
        files.append(str(path.relative_to(root)))

    return sorted(files)


def is_test_file(path: str) -> bool:
    """Check if a file path looks like a test file."""
    name = Path(path).name
    return any(p.match(name) for p in _TEST_PATTERNS)


def find_test_files_from_manifest(manifest_data: dict) -> list[str]:
    """Extract test file paths from manifest read files and validate commands."""
    test_files: list[str] = []

    for path in manifest_data.get("files_read", ()):
        if is_test_file(path):
            test_files.append(path)

    return test_files
