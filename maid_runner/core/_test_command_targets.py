"""Validate-command test target parsing helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from maid_runner.core._file_discovery import is_test_file
from maid_runner.core._test_runner_invocation import (
    _TEST_RUNNER_VALUE_FLAGS,
    _has_non_executing_test_runner_mode,
    _has_test_runner_selector,
    _is_django_test_runner_value_flag,
    _runs_django_test_runner,
    _runs_known_test_runner,
    _test_runner_target_scan_segment,
)

_DjangoPathResolver = Callable[[list[str], Path, Path], list[str]]


def test_paths_from_validate_command(
    command: tuple[str, ...],
    project_root: Path,
    *,
    django_test_paths_from_validate_segment: _DjangoPathResolver | None = None,
) -> list[str]:
    paths: list[str] = []
    cwd = Path(".")

    for segment in command_segments(command):
        if not segment:
            continue

        if segment[0] == "cd":
            if len(segment) > 1:
                cwd = Path(_normalize_relative_path(cwd / segment[1]))
            continue

        django_runner = _runs_django_test_runner(segment)
        allow_explicit_directories = _runs_known_test_runner(segment)
        scan_segment = _test_runner_target_scan_segment(segment)
        index = 0
        while index < len(scan_segment):
            part = scan_segment[index]
            if part in {"-C", "--cwd", "--dir", "--prefix"} and index + 1 < len(
                scan_segment
            ):
                cwd = Path(_normalize_relative_path(cwd / scan_segment[index + 1]))
                index += 2
                continue
            if django_runner and _is_django_test_runner_value_flag(part):
                index += 2 if "=" not in part and index + 1 < len(scan_segment) else 1
                continue
            if part in _TEST_RUNNER_VALUE_FLAGS and index + 1 < len(scan_segment):
                index += 2
                continue
            if part.startswith("-"):
                index += 1
                continue

            if not django_runner:
                candidate = _normalize_relative_path(cwd / part)
                if _looks_like_test_path(
                    candidate,
                    project_root,
                    allow_explicit_directories=allow_explicit_directories,
                ):
                    paths.append(candidate)
            index += 1

        if django_test_paths_from_validate_segment is not None:
            paths.extend(
                django_test_paths_from_validate_segment(
                    segment,
                    project_root,
                    cwd,
                )
            )

    return paths


def test_files_covered_by_validate_command(
    command: tuple[str, ...],
    test_files: list[str],
    project_root: Path,
    *,
    django_test_paths_from_validate_segment: _DjangoPathResolver | None = None,
) -> set[str]:
    covered: set[str] = set()
    for target in test_paths_from_executing_validate_command(
        command,
        project_root,
        django_test_paths_from_validate_segment=django_test_paths_from_validate_segment,
    ):
        for test_file in test_files:
            if _test_target_covers_file(target, test_file, project_root):
                covered.add(test_file)
    return covered


def test_paths_from_executing_validate_command(
    command: tuple[str, ...],
    project_root: Path,
    *,
    allow_selectors: bool = False,
    django_test_paths_from_validate_segment: _DjangoPathResolver | None = None,
) -> list[str]:
    paths: list[str] = []
    cwd = Path(".")
    segment = list(command)

    if not segment:
        return paths
    if any(part in {"&&", "||", ";"} for part in segment):
        return paths
    if segment[0] == "cd":
        return paths
    if not _runs_known_test_runner(segment):
        return paths
    if _has_non_executing_test_runner_mode(segment):
        return paths
    if not allow_selectors and _has_test_runner_selector(segment):
        return paths

    django_runner = _runs_django_test_runner(segment)
    scan_segment = _test_runner_target_scan_segment(segment)
    index = 0
    while index < len(scan_segment):
        part = scan_segment[index]
        if part in {"-C", "--cwd", "--dir", "--prefix"} and index + 1 < len(
            scan_segment
        ):
            cwd = Path(_normalize_relative_path(cwd / scan_segment[index + 1]))
            index += 2
            continue
        if django_runner and _is_django_test_runner_value_flag(part):
            index += 2 if "=" not in part and index + 1 < len(scan_segment) else 1
            continue
        if part in _TEST_RUNNER_VALUE_FLAGS and index + 1 < len(scan_segment):
            index += 2
            continue
        if part.startswith("-"):
            index += 1
            continue

        if not django_runner:
            raw_candidate = _normalize_relative_path(cwd / part)
            if "::" in raw_candidate and not allow_selectors:
                index += 1
                continue
            candidate = _normalize_test_selector(cwd / part) or "."
            if _looks_like_test_path(
                candidate,
                project_root,
                allow_explicit_directories=True,
            ):
                paths.append(candidate)
        index += 1

    if django_test_paths_from_validate_segment is not None:
        paths.extend(
            django_test_paths_from_validate_segment(
                segment,
                project_root,
                cwd,
            )
        )

    return paths


def _normalize_test_selector(path: Path) -> str:
    normalized = _normalize_relative_path(path)
    path_part, separator, _ = normalized.partition("::")
    if not separator:
        return normalized
    return path_part


def _test_target_covers_file(
    target: str,
    test_file: str,
    project_root: Path,
) -> bool:
    target = target.rstrip("/")
    test_file = test_file.rstrip("/")
    if target in {"", "."}:
        return True
    if target == test_file:
        return True

    full_target = project_root / target
    if full_target.is_dir():
        return test_file.startswith(f"{target}/")

    return False


def command_segments(command: tuple[str, ...]) -> list[list[str]]:
    segments: list[list[str]] = [[]]
    for part in command:
        if part in {"&&", "||", ";"}:
            segments.append([])
        else:
            segments[-1].append(part)
    return segments


def _normalize_relative_path(path: Path) -> str:
    parts: list[str] = []
    for part in path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _looks_like_test_path(
    path: str,
    project_root: Path,
    *,
    allow_explicit_directories: bool = False,
) -> bool:
    if is_test_file(path):
        return True

    full_path = project_root / path
    if not full_path.is_dir():
        return False

    test_dir_names = {"test", "tests", "__tests__", "spec", "specs"}
    return allow_explicit_directories or any(
        part.lower() in test_dir_names for part in full_path.parts
    )
