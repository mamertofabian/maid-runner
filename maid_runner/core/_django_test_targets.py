"""Django validate-command test target resolution helpers."""

from __future__ import annotations

import re
from pathlib import Path

from maid_runner.core._file_discovery import is_test_file
from maid_runner.core._test_command_targets import _normalize_relative_path
from maid_runner.core._test_runner_invocation import (
    _DJANGO_TEST_RUNNER,
    _effective_test_runner_invocation,
    _has_django_test_runner_selector,
    _has_pythonpath_assignment,
    _next_django_argument_index,
)

_DOTTED_PYTHON_TEST_LABEL = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$")


def django_test_paths_from_validate_segment(
    segment: list[str],
    project_root: Path,
    cwd: Path,
) -> list[str]:
    invocation = _effective_test_runner_invocation(segment)
    if invocation is None:
        return []

    runner, args = invocation
    if runner != _DJANGO_TEST_RUNNER:
        return []
    if _has_pythonpath_assignment(segment) or _has_django_test_runner_selector(args):
        return []

    return django_test_paths_from_args(args, project_root, cwd)


def django_test_paths_from_args(
    args: list[str],
    project_root: Path,
    cwd: Path,
) -> list[str]:
    paths: list[str] = []
    index = 0
    while index < len(args):
        part = args[index]
        if part.startswith("-"):
            next_index = _next_django_argument_index(args, index)
            if next_index is None:
                return []
            index = next_index
            continue

        for path in resolve_django_test_label_paths(part, project_root, cwd):
            if path not in paths:
                paths.append(path)
        index += 1

    return paths


def resolve_django_test_label_paths(
    label: str,
    project_root: Path,
    cwd: Path,
) -> list[str]:
    if not _DOTTED_PYTHON_TEST_LABEL.match(label):
        return []

    paths: list[str] = []
    parts = label.split(".")
    for module_path in _django_module_path_variants(parts):
        for source_root in _django_source_root_candidates(cwd):
            candidate = _normalize_relative_path(source_root / module_path)
            if candidate in paths:
                continue
            if not is_test_file(candidate):
                continue
            if (project_root / candidate).is_file():
                paths.append(candidate)
    return paths


def _django_module_path_variants(module_parts: list[str]) -> list[Path]:
    return [Path(*module_parts).with_suffix(".py")]


def _django_source_root_candidates(cwd: Path) -> list[Path]:
    roots: list[Path] = []
    for root in (cwd, cwd / "src"):
        normalized = Path(_normalize_relative_path(root))
        if normalized not in roots:
            roots.append(normalized)
    return roots
