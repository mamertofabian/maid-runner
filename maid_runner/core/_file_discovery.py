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
    "htmlcov",
    "examples",
    "scripts",
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
    *,
    exclude_patterns: set[str] | None = None,
    respect_gitignore: bool = False,
) -> list[str]:
    """Discover all source files in a project, excluding common non-source dirs.

    Args:
        project_root: Root directory to search.
        extensions: File extensions to include (default: common source extensions).
        exclude_patterns: Glob patterns to exclude (e.g. ``{"vendor/*"}``).
        respect_gitignore: When True, also exclude files ignored by git.
    """
    from fnmatch import fnmatch

    root = Path(project_root)
    exts = extensions or _SOURCE_EXTENSIONS

    git_ignored: set[str] | None = None
    if respect_gitignore:
        git_ignored = _get_git_ignored_files(root)

    files: list[str] = []

    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if path.suffix not in exts:
            continue
        rel = str(path.relative_to(root))
        # Skip excluded directories
        parts = path.relative_to(root).parts
        if any(part in _EXCLUDE_DIRS for part in parts):
            continue
        # Skip package marker files that do not define runtime API.
        if path.name == "__init__.py" and _is_marker_init_file(path):
            continue
        # Skip gitignored files
        if git_ignored is not None and rel in git_ignored:
            continue
        # Skip user-specified exclude patterns
        if exclude_patterns and any(fnmatch(rel, p) for p in exclude_patterns):
            continue
        files.append(rel)

    return sorted(files)


def _get_git_ignored_files(root: Path) -> set[str] | None:
    """Get files ignored by git. Returns None if git is unavailable."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--ignored", "--exclude-standard", "-z"],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=10,
        )
        if result.returncode != 0:
            return None
        return {f for f in result.stdout.split("\0") if f}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _is_marker_init_file(path: Path) -> bool:
    """Return True for empty/docstring-only __init__.py marker files."""
    import ast

    try:
        source = path.read_text()
        module = ast.parse(source)
    except (OSError, SyntaxError):
        return False

    body = module.body
    if not body:
        return True
    if len(body) == 1 and isinstance(body[0], ast.Expr):
        return isinstance(body[0].value, ast.Constant) and isinstance(
            body[0].value.value, str
        )
    return False


def is_test_file(path: str) -> bool:
    """Check if a file path looks like a test file."""
    name = Path(path).name
    if name == "conftest.py":
        return True
    return any(p.match(name) for p in _TEST_PATTERNS)


def find_test_files_from_manifest(manifest_data: dict) -> list[str]:
    """Extract test file paths from manifest read files and validate commands."""
    test_files: list[str] = []

    for path in manifest_data.get("files_read", ()):
        if is_test_file(path):
            test_files.append(path)

    return test_files
