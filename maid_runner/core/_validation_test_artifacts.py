"""Test discovery and behavioral artifact collection for validation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from maid_runner.core._file_discovery import is_test_file
from maid_runner.core.result import ErrorCode, Location, ValidationError
from maid_runner.core.types import ArtifactKind, Manifest
from maid_runner.validators.base import BaseValidator, FoundArtifact
from maid_runner.validators.registry import (
    UnsupportedLanguageError,
    ValidatorRegistry,
)


def find_test_files(manifest: Manifest, project_root: Path) -> list[str]:
    test_files: list[str] = []

    def add_test_file(path: str) -> None:
        if is_test_file(path) and path not in test_files:
            test_files.append(path)

    def add_test_path(path: str) -> None:
        add_test_file(path)

        full_path = project_root / path
        if not full_path.is_dir():
            return

        for child in sorted(full_path.rglob("*")):
            if not child.is_file():
                continue
            rel_path = str(child.relative_to(project_root))
            add_test_file(rel_path)

    for path in manifest.files_read:
        add_test_path(path)

    for cmd in manifest.validate_commands:
        for path in _test_paths_from_validate_command(cmd, project_root):
            add_test_path(path)

    return test_files


def _test_paths_from_validate_command(
    command: tuple[str, ...],
    project_root: Path,
) -> list[str]:
    paths: list[str] = []
    cwd = Path(".")

    for segment in _command_segments(command):
        if not segment:
            continue

        if segment[0] == "cd":
            if len(segment) > 1:
                cwd = Path(_normalize_relative_path(cwd / segment[1]))
            continue

        allow_explicit_directories = _runs_known_test_runner(segment)
        index = 0
        while index < len(segment):
            part = segment[index]
            if part in {"-C", "--cwd", "--dir", "--prefix"} and index + 1 < len(
                segment
            ):
                cwd = Path(_normalize_relative_path(cwd / segment[index + 1]))
                index += 2
                continue
            if part.startswith("-"):
                index += 1
                continue

            candidate = _normalize_relative_path(cwd / part)
            if _looks_like_test_path(
                candidate,
                project_root,
                allow_explicit_directories=allow_explicit_directories,
            ):
                paths.append(candidate)
            index += 1

    return paths


def _runs_known_test_runner(segment: list[str]) -> bool:
    test_runners = {
        "pytest",
        "py.test",
        "vitest",
        "jest",
        "playwright",
    }
    return any(Path(part).name in test_runners for part in segment)


def _command_segments(command: tuple[str, ...]) -> list[list[str]]:
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


def get_validator_for_test(
    test_path: str,
    registry: ValidatorRegistry,
) -> Optional[BaseValidator]:
    """Get a validator for a test file, or None if unsupported."""
    try:
        return registry.get(test_path)
    except UnsupportedLanguageError:
        return None


def collect_test_artifacts(
    test_files: list[str],
    project_root: Path,
    registry: ValidatorRegistry,
    errors: list[ValidationError],
) -> dict[str, list[FoundArtifact]]:
    collected: dict[str, list[FoundArtifact]] = {}

    for tf_path in test_files:
        full_path = project_root / tf_path
        if not full_path.exists():
            continue

        try:
            source = full_path.read_text()
        except OSError as exc:
            errors.append(
                ValidationError(
                    code=ErrorCode.FILE_READ_ERROR,
                    message=f"Failed to read test file '{tf_path}': {exc}",
                    location=Location(file=tf_path),
                )
            )
            continue

        validator = get_validator_for_test(tf_path, registry)
        if validator is None:
            continue

        result = validator.collect_behavioral_artifacts(source, tf_path)
        if result.errors:
            errors.extend(
                collection_errors_to_validation_errors(result.errors, tf_path)
            )
            continue

        # TEST_FUNCTION declarations are test definitions, not source usage.
        collected[tf_path] = [
            artifact
            for artifact in result.artifacts
            if artifact.kind != ArtifactKind.TEST_FUNCTION
        ]

    return collected


def collection_errors_to_validation_errors(
    collection_errors: list[str],
    file_path: str,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for message in collection_errors:
        line = None
        match = re.search(r"line\s+(\d+)", message)
        if match:
            line = int(match.group(1))
        errors.append(
            ValidationError(
                code=ErrorCode.SOURCE_PARSE_ERROR,
                message=f"Failed to parse '{file_path}': {message}",
                location=Location(file=file_path, line=line),
                suggestion="Fix syntax errors before re-running validation",
            )
        )
    return errors
