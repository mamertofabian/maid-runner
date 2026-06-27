"""Test discovery and behavioral artifact collection for validation."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
import shlex
from pathlib import Path
from typing import Optional, Union

from maid_runner.core import _artifact_collection_cache as artifact_cache
from maid_runner.core._command_integrity_test_discovery import (
    find_command_integrity_test_files,
    is_command_integrity_test_file,
    is_python_behavioral_test_file,
)
from maid_runner.core._django_test_targets import (
    django_test_paths_from_args,
    django_test_paths_from_validate_segment,
    resolve_django_test_label_paths,
    _django_module_path_variants as django_module_path_variants,
    _django_source_root_candidates as django_source_root_candidates,
)
from maid_runner.core._file_discovery import is_test_file
from maid_runner.core._pytest_config_addopts import (
    pyproject_pytest_addopts_args,
    pyproject_pytest_addopts_errors,
)
from maid_runner.core._test_command_targets import (
    command_segments,
    test_files_covered_by_validate_command,
    test_paths_from_executing_validate_command,
    test_paths_from_validate_command,
    _looks_like_test_path as command_target_looks_like_test_path,
    _normalize_relative_path as command_target_normalize_relative_path,
    _normalize_test_selector as command_target_normalize_test_selector,
    _test_target_covers_file as command_target_covers_file,
)
from maid_runner.core._test_runner_invocation import (
    _DJANGO_TEST_RUNNER as _DJANGO_TEST_RUNNER,
    _command_name as _command_name,
    _django_test_args_after_subcommand as _django_test_args_after_subcommand,
    _docker_exec_inner_command as _docker_exec_inner_command,
    _effective_test_runner_invocation as _effective_test_runner_invocation,
    _has_django_test_runner_selector as _has_django_test_runner_selector,
    _has_non_executing_test_runner_mode as _runner_has_non_executing_test_runner_mode,
    _has_pythonpath_assignment as _has_pythonpath_assignment,
    _has_test_runner_selector as _has_test_runner_selector,
    _invokes_known_test_runner as _invokes_known_test_runner,
    _is_detached_docker_exec_option as _is_detached_docker_exec_option,
    _is_django_test_runner_selector_flag as _is_django_test_runner_selector_flag,
    _is_django_test_runner_value_flag as _is_django_test_runner_value_flag,
    _is_docker_env_file_option as _is_docker_env_file_option,
    _is_docker_pythonpath_env_option as _is_docker_pythonpath_env_option,
    _is_python_command as _is_python_command,
    _is_pythonpath_env_value as _is_pythonpath_env_value,
    _is_test_runner_selector_flag as _is_test_runner_selector_flag,
    _looks_like_environment_assignment as _looks_like_environment_assignment,
    _next_django_argument_index as _next_django_argument_index,
    _pytest_addopts_args as _pytest_addopts_args,
    _pytest_ini_addopts_args as _pytest_ini_addopts_args,
    _pytest_override_ini_addopts_args as _pytest_override_ini_addopts_args,
    _runs_django_test_runner as _runs_django_test_runner,
    _runs_known_test_runner as _runs_known_test_runner,
    _strip_environment_prefix as _strip_environment_prefix,
    _TEST_RUNNER_VALUE_FLAGS as _TEST_RUNNER_VALUE_FLAGS,
    _test_runner_invocation as _runner_test_runner_invocation,
    _test_runner_target_scan_segment as _test_runner_target_scan_segment,
    _uv_run_inner_command as _uv_run_inner_command,
)
from maid_runner.core.result import ErrorCode, Location, ValidationError
from maid_runner.core.types import ArtifactKind, Manifest
from maid_runner.validators.base import BaseValidator, FoundArtifact
from maid_runner.validators.registry import (
    UnsupportedLanguageError,
    ValidatorRegistry,
)

_STRICT_TEST_COMMAND_COVERAGE_SINCE = "2026-05-17"
_TEST_COMMAND_TASK_TYPES = frozenset({"feature", "fix", "refactor"})
_PACKAGE_MANAGER_COMMANDS = frozenset({"npm", "pnpm", "yarn", "bun"})
_PACKAGE_EXEC_WRAPPERS = frozenset({"npx", "bunx"})
_PACKAGE_EXEC_SUBCOMMANDS = frozenset({"exec", "dlx", "x"})
_PACKAGE_RUN_SUBCOMMANDS = frozenset({"run", "run-script"})
_PACKAGE_CWD_VALUE_FLAGS = frozenset({"-C", "--cwd", "--dir", "--prefix"})
_SCOPED_BROWSER_RUNNER_PACKAGES = {"@playwright/test": "playwright"}
_SHELL_COMMANDS = frozenset({"bash", "sh", "zsh"})
_E2E_PATH_VALUE_FLAGS = frozenset(
    {
        "--cov-report",
        "--coverage-directory",
        "--coverage.reportsDirectory",
        "--coverage.reports-directory",
        "--coverageDirectory",
        "--cache-directory",
        "--cacheDirectory",
        "--html",
        "--log-file",
        "--output-dir",
        "--output-file",
        "--outputDir",
        "--outputFile",
    }
) | frozenset(_TEST_RUNNER_VALUE_FLAGS)
_E2E_PATH_EXCLUSION_VALUE_FLAGS = frozenset({"--deselect", "--ignore", "--ignore-glob"})
_PACKAGE_OPTION_VALUE_FLAGS = frozenset(
    {
        "-C",
        "-F",
        "-p",
        "--cache",
        "--config",
        "--cwd",
        "--dir",
        "--filter",
        "--package",
        "--prefix",
        "--registry",
        "--scope",
        "--store-dir",
        "--userconfig",
        "--workspace",
    }
)
_LEGACY_TEST_COMMAND_TARGET_SLUGS = frozenset(
    {
        "017-04-typescript-decorator-metadata-boundary",
        "017-06-compiler-backed-required-import-resolution",
        "017-07-python-parser-replacement-boundaries",
        "019-01-claude-maid-loop-automation",
        "024-02-review-readiness-required-import-and-doc-fixes",
        "025-01-characterize-angular-typescript-artifacts",
        "025-02-characterize-angular-required-imports-and-routes",
        "025-03-add-angular-component-companion-file-tracking",
        "025-04-document-angular-support-boundaries",
        "026-01-restore-schema-validation-mode",
        "027-01-characterize-react-typescript-artifacts",
        "027-02-add-react-wrapped-component-extraction",
        "027-03-characterize-react-required-imports-and-testing-library",
        "027-04-add-react-snapshot-companion-file-tracking",
        "028-01-extract-js-ts-import-scanner",
        "028-07-split-typescript-behavioral-reference-collector",
        "028-08-simplify-graph-query-facade-and-parser",
        "030-01-fail-empty-manifest-discovery",
        "030-05-promote-coverage-misses-to-errors",
        "031-01-restore-integration-fixture-coverage",
        "add-manifest-event-log",
        "add-semantic-reference-index",
        "add-semantic-reference-index-typescript",
        "add-supersession-artifact-preservation",
        "add-typescript-annotated-function-return-extraction",
        "add-typescript-compiler-backed-identity-resolution",
        "add-typescript-computed-property-artifact-extraction",
        "add-typescript-generic-type-parameter-storage",
        "add-typescript-mjs-cjs-barrel-identity",
        "add-typescript-tsconfig-extends-identity",
        "add-typescript-tsconfig-path-alias-identity",
        "add-typescript-type-alias-target-extraction",
        "characterize-typescript-namespace-reexport-identity",
        "extend-typescript-barrel-reexport-identity",
        "fix-file-tracking-noise-filter",
        "fix-manifest-dir-active-subdirectory-discovery",
        "fix-publish-workflow-npm-dependencies",
        "fix-typescript-computed-key-behavioral-coverage",
        "fix-typescript-literal-computed-subscript-coverage",
        "fix-typescript-private-and-module-local-artifacts",
        "fix-validation-test-discovery-and-ts-import-query",
        "gate-archspec-e2e-strict-mode",
        "replace-ts-required-import-regex-scanner",
    }
)

_TestArtifactCacheKey = tuple[str, str, str]
_TestArtifactFileSignature = tuple[int, int]
_TestDiscoveryDirectoryEntrySignature = tuple[
    str,
    bool,
    bool,
    int,
    int,
    bool,
    int | None,
    int | None,
]
_TestDiscoveryDirectorySignature = tuple[
    str,
    int,
    int,
    tuple[_TestDiscoveryDirectoryEntrySignature, ...],
]
_TestDiscoveryDirectoryState = tuple[_TestDiscoveryDirectorySignature, ...]
_TestDiscoveryCacheKey = tuple[str, str]


@dataclass(frozen=True)
class TestArtifactsTable:
    """Filtered behavioral artifact table for one test file."""

    artifacts: tuple[FoundArtifact, ...] = ()
    errors: tuple[ValidationError, ...] = ()


@dataclass(frozen=True)
class _TestArtifactCacheEntry:
    signature: _TestArtifactFileSignature
    table: TestArtifactsTable
    collection_errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _TestDiscoveryCacheEntry:
    directory_state: _TestDiscoveryDirectoryState
    test_files: tuple[str, ...] = ()


_TEST_ARTIFACT_CACHE: dict[_TestArtifactCacheKey, _TestArtifactCacheEntry] = {}
_TEST_DISCOVERY_CACHE: dict[_TestDiscoveryCacheKey, _TestDiscoveryCacheEntry] = {}


def find_test_files(manifest: Manifest, project_root: Path) -> list[str]:
    test_files: list[str] = []

    def add_test_file(path: str) -> None:
        if is_test_file(path) and path not in test_files:
            test_files.append(path)

    def add_test_path(path: str) -> None:
        for test_path in _get_cached_test_discovery(path, project_root):
            add_test_file(test_path)

    for path in manifest.files_read:
        add_test_path(path)

    for file_spec in manifest.all_file_specs:
        add_test_path(file_spec.path)

    for cmd in manifest.validate_commands:
        for path in _test_paths_from_validate_command(cmd, project_root):
            add_test_path(path)

    return test_files


def _get_cached_test_discovery(path: str, project_root: Path) -> tuple[str, ...]:
    if is_test_file(path):
        return (path,)

    full_path = project_root / path
    if not full_path.is_dir():
        return ()

    key = _test_discovery_cache_key(project_root, path)
    cached = _TEST_DISCOVERY_CACHE.get(key)
    if cached is not None and _test_discovery_directory_state_matches(
        cached.directory_state
    ):
        return cached.test_files

    try:
        result, directory_state = _discover_test_files_with_directory_state(
            full_path,
            project_root,
        )
    except OSError:
        return _discover_test_files(full_path, project_root)
    _TEST_DISCOVERY_CACHE[key] = _TestDiscoveryCacheEntry(directory_state, result)
    return result


def _discover_test_files_with_directory_state(
    full_path: Path,
    project_root: Path,
) -> tuple[tuple[str, ...], _TestDiscoveryDirectoryState]:
    discovered: list[str] = []
    directories: list[_TestDiscoveryDirectorySignature] = [
        _test_discovery_directory_signature(full_path)
    ]

    def add_discovered_file(path: Path) -> None:
        rel_path = str(path.relative_to(project_root))
        if is_test_file(rel_path):
            discovered.append(rel_path)

    def walk(directory: Path) -> None:
        for child in sorted(directory.iterdir()):
            is_symlink = child.is_symlink()
            if not is_symlink and child.is_dir():
                directories.append(_test_discovery_directory_signature(child))
                walk(child)
                continue
            if child.is_file():
                add_discovered_file(child)

    walk(full_path)
    return tuple(discovered), tuple(directories)


def _test_discovery_directory_state_matches(
    directory_state: _TestDiscoveryDirectoryState,
) -> bool:
    try:
        return all(
            _test_discovery_directory_signature(Path(signature[0])) == signature
            for signature in directory_state
        )
    except OSError:
        return False


def _discover_test_files(full_path: Path, project_root: Path) -> tuple[str, ...]:
    discovered: list[str] = []
    for child in sorted(full_path.rglob("*")):
        if not child.is_file():
            continue
        rel_path = str(child.relative_to(project_root))
        if is_test_file(rel_path):
            discovered.append(rel_path)
    return tuple(discovered)


def clear_test_discovery_cache() -> None:
    _TEST_DISCOVERY_CACHE.clear()


def _test_paths_from_validate_command(
    command: tuple[str, ...],
    project_root: Path,
) -> list[str]:
    return test_paths_from_validate_command(
        command,
        project_root,
        django_test_paths_from_validate_segment=_django_test_paths_from_validate_segment,
    )


def validate_manifest_test_commands(
    manifest: Manifest,
    project_root: Path,
) -> list[ValidationError]:
    """Require validate commands to execute discovered behavioral tests."""
    requires_coverage = _requires_validate_command_test_coverage(manifest)
    test_files = (
        _find_command_integrity_test_files(manifest, project_root)
        if requires_coverage
        else []
    )
    has_existing_test_files = any(
        (project_root / path).is_file() for path in test_files
    )
    covered: set[str] = set()
    missing: list[str] = []
    if requires_coverage and test_files:
        for command in manifest.validate_commands:
            covered.update(
                _test_files_covered_by_validate_command(
                    command,
                    test_files,
                    project_root,
                )
            )
        missing = [test_file for test_file in test_files if test_file not in covered]

    e2e_errors = _e2e_validate_command_errors(
        manifest,
        classify_selector_browser_commands=not bool(
            requires_coverage and has_existing_test_files and missing
        ),
    )
    if e2e_errors:
        return e2e_errors

    if not requires_coverage:
        return []

    if not test_files:
        return []

    config_errors = _pyproject_pytest_addopts_integrity_errors(
        manifest,
        project_root,
    )
    if config_errors:
        return config_errors

    if not missing:
        return []
    if _allows_legacy_test_command_target(
        manifest,
        project_root,
    ) and _has_executing_test_runner_target(manifest, project_root):
        return []

    command_list = "; ".join(
        _format_command(command) for command in manifest.validate_commands
    )
    if not command_list:
        command_list = "<none>"
    missing_list = ", ".join(missing)
    return [
        ValidationError(
            code=ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS,
            message=(
                "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS: "
                f"Manifest '{manifest.slug}' validate commands do not run any "
                f"discovered behavioral test files: {missing_list}. "
                f"Commands: {command_list}"
            ),
            location=Location(file=manifest.source_path),
            suggestion=(
                "Run the behavioral tests with a recognized test runner and "
                "target each test file or a containing test directory."
            ),
        )
    ]


def _e2e_validate_command_errors(
    manifest: Manifest,
    *,
    classify_selector_browser_commands: bool,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for command in manifest.validate_commands:
        if not _is_e2e_validate_command(
            command,
            classify_selector_browser_commands=classify_selector_browser_commands,
        ):
            continue
        errors.append(
            ValidationError(
                code=ErrorCode.E2E_VALIDATE_COMMAND_NOT_ALLOWED,
                message=(
                    "E2E_VALIDATE_COMMAND_NOT_ALLOWED: "
                    f"Manifest '{manifest.slug}' validate command belongs to "
                    "the E2E/browser layer, not the fast behavioral gate. "
                    f"Command: {_format_command(command)}"
                ),
                location=Location(file=manifest.source_path),
                suggestion=(
                    "Keep validate commands limited to fast behavioral tests. "
                    "Move browser or E2E checks to acceptance metadata or a "
                    "separate E2E workflow."
                ),
            )
        )
    return errors


def _is_e2e_validate_command(
    command: tuple[str, ...],
    *,
    classify_selector_browser_commands: bool,
) -> bool:
    return _parts_include_e2e_validate_command(
        list(command),
        classify_selector_browser_commands=classify_selector_browser_commands,
    )


def _parts_include_e2e_validate_command(
    parts: list[str],
    *,
    classify_selector_browser_commands: bool,
) -> bool:
    return any(
        _segment_is_e2e_validate_command(
            segment,
            classify_selector_browser_commands=classify_selector_browser_commands,
        )
        for segment in command_segments(tuple(parts))
        if segment
    )


def _segment_is_e2e_validate_command(
    segment: list[str],
    *,
    classify_selector_browser_commands: bool,
) -> bool:
    transparent_inner = _transparent_wrapper_inner_command(segment)
    if transparent_inner is not None and transparent_inner != segment:
        return _parts_include_e2e_validate_command(
            transparent_inner,
            classify_selector_browser_commands=classify_selector_browser_commands,
        )

    if (
        _segment_invokes_browser_e2e_runner(
            segment,
            classify_selector_browser_commands=classify_selector_browser_commands,
        )
        or _segment_targets_e2e_path(
            segment,
            classify_selector_browser_commands=classify_selector_browser_commands,
        )
        or _segment_runs_e2e_package_script(segment)
    ):
        return True

    inner = _package_manager_exec_inner_command(segment)
    return (
        inner is not None
        and inner != segment
        and _parts_include_e2e_validate_command(
            inner,
            classify_selector_browser_commands=classify_selector_browser_commands,
        )
    )


def _transparent_wrapper_inner_command(segment: list[str]) -> list[str] | None:
    parts = _strip_environment_prefix(segment)
    if not parts:
        return None

    command = _command_name(parts[0])
    if command in _SHELL_COMMANDS:
        return _shell_inner_command(parts)
    if command == "uv":
        return _uv_run_inner_command(parts)
    if command in {"poetry", "pdm"} and len(parts) >= 3 and parts[1] == "run":
        return parts[2:]
    if command == "docker":
        return _docker_exec_inner_command(parts)
    if command == "coverage" and len(parts) >= 4 and parts[1:3] == ["run", "-m"]:
        return parts[3:]
    return None


def _shell_inner_command(parts: list[str]) -> list[str] | None:
    index = 1
    while index < len(parts):
        part = parts[index]
        if _is_shell_command_string_flag(part):
            if index + 1 >= len(parts):
                return None
            return _split_package_call_value(parts[index + 1])
        if part == "--":
            index += 1
            continue
        if part.startswith("-"):
            index += 1
            continue
        return None
    return None


def _is_shell_command_string_flag(part: str) -> bool:
    return part.startswith("-") and "c" in part and not part.startswith("--")


def _segment_invokes_browser_e2e_runner(
    segment: list[str],
    *,
    classify_selector_browser_commands: bool,
) -> bool:
    if (
        _segment_has_test_runner_selector(segment)
        and not classify_selector_browser_commands
    ):
        return False

    invocation = _runner_test_runner_invocation(segment)
    if invocation is not None and invocation[0] == "playwright":
        return True

    inner = _package_manager_exec_inner_command(segment)
    if inner is not None and _segment_starts_browser_e2e_runner(inner):
        return True

    scan_segment = _test_runner_target_scan_segment(segment)
    return _segment_starts_browser_e2e_runner(scan_segment)


def _segment_has_test_runner_selector(segment: list[str]) -> bool:
    if _has_test_runner_selector(segment):
        return True
    inner = _package_manager_exec_inner_command(segment)
    return inner is not None and _has_test_runner_selector(inner)


def _segment_starts_browser_e2e_runner(segment: list[str]) -> bool:
    if len(segment) < 2:
        return False
    command = _package_command_name(segment[0])
    if command == "playwright" and segment[1] == "test":
        return True
    return command == "cypress" and segment[1] in {"run", "open"}


def _segment_targets_e2e_path(
    segment: list[str],
    *,
    classify_selector_browser_commands: bool,
) -> bool:
    if (
        _segment_has_test_runner_selector(segment)
        and not classify_selector_browser_commands
    ):
        return False

    if _segment_has_e2e_package_cwd(segment):
        return True

    django_runner = _runs_django_test_runner(segment)
    scan_segment = _package_manager_exec_inner_command(
        segment
    ) or _test_runner_target_scan_segment(segment)
    index = 0
    while index < len(scan_segment):
        part = scan_segment[index]
        if part in _PACKAGE_CWD_VALUE_FLAGS and index + 1 < len(scan_segment):
            index += 2
            continue
        if django_runner and _is_django_test_runner_value_flag(part):
            index += 2 if "=" not in part and index + 1 < len(scan_segment) else 1
            continue
        flag = part.split("=", 1)[0]
        if flag in _E2E_PATH_VALUE_FLAGS or flag in _E2E_PATH_EXCLUSION_VALUE_FLAGS:
            index += 2 if "=" not in part and index + 1 < len(scan_segment) else 1
            continue
        if part.startswith("-") and "=" not in part:
            index += 1
            continue
        if _has_e2e_path_component(part):
            return True
        index += 1
    return False


def _segment_has_e2e_package_cwd(segment: list[str]) -> bool:
    parts = _strip_package_manager_prefix(segment)
    if not parts:
        return False
    if _package_command_name(parts[0]) not in _PACKAGE_MANAGER_COMMANDS:
        return False

    index = 1
    while index < len(parts):
        part = parts[index]
        flag, separator, attached_value = part.partition("=")
        if flag in _PACKAGE_CWD_VALUE_FLAGS:
            if separator:
                return _has_e2e_path_component(attached_value)
            if index + 1 < len(parts) and _has_e2e_path_component(parts[index + 1]):
                return True
            index += 2
            continue
        if part == "--":
            return False
        if _package_option_has_attached_value(part):
            index += 1
            continue
        if _package_option_consumes_value(
            flag, command=_package_command_name(parts[0])
        ):
            index += 2 if index + 1 < len(parts) else 1
            continue
        if part.startswith("-"):
            index += 1
            continue
        return False
    return False


def _has_e2e_path_component(value: str) -> bool:
    if "=" in value and value.startswith("-"):
        _, value = value.split("=", 1)
    path_part = value.partition("::")[0].replace("\\", "/")
    return any(part.lower() == "e2e" for part in path_part.split("/"))


def _segment_runs_e2e_package_script(segment: list[str]) -> bool:
    parts = _strip_package_manager_prefix(segment)
    if not parts:
        return False

    command = _package_command_name(parts[0])
    if command not in _PACKAGE_MANAGER_COMMANDS:
        return False

    index = _skip_package_options(parts, 1, command=command)
    if index >= len(parts):
        return False

    if command == "npm":
        return _package_script_name_is_e2e(parts, index)

    if command == "yarn" and parts[index] == "workspace":
        index = _skip_package_options(parts, index + 2, command=command)
        if index >= len(parts):
            return False

    if parts[index] in _PACKAGE_EXEC_SUBCOMMANDS:
        return False
    return _package_script_name_is_e2e(parts, index)


def _package_script_name_is_e2e(parts: list[str], index: int) -> bool:
    subcommand = parts[index]
    if subcommand in _PACKAGE_EXEC_SUBCOMMANDS:
        return False
    if subcommand in _PACKAGE_RUN_SUBCOMMANDS:
        index = _skip_package_options(
            parts,
            index + 1,
            command=_package_command_name(parts[0]),
        )
        return index < len(parts) and _is_e2e_script_name(parts[index])
    return _is_e2e_script_name(subcommand)


def _package_manager_exec_inner_command(segment: list[str]) -> list[str] | None:
    parts = _strip_package_manager_prefix(segment)
    if not parts:
        return None

    command = _package_command_name(parts[0])
    if command in _PACKAGE_EXEC_WRAPPERS:
        return _normalize_package_inner_command(parts[1:], command=command)

    if command not in _PACKAGE_MANAGER_COMMANDS:
        return None

    index = _skip_package_options(parts, 1, command=command)
    if command == "yarn" and index < len(parts) and parts[index] == "workspace":
        index = _skip_package_options(parts, index + 2, command=command)
    if index >= len(parts) or parts[index] not in _PACKAGE_EXEC_SUBCOMMANDS:
        if command != "npm" and index < len(parts):
            return _normalize_package_inner_command(parts[index:], command=command)
        return None
    return _normalize_package_inner_command(parts[index + 1 :], command=command)


def _strip_package_manager_prefix(segment: list[str]) -> list[str]:
    parts = _strip_environment_prefix(segment)
    if len(parts) < 2 or _command_name(parts[0]) != "corepack":
        return parts
    candidate = _package_command_name(parts[1])
    if candidate in _PACKAGE_MANAGER_COMMANDS or candidate in _PACKAGE_EXEC_WRAPPERS:
        return parts[1:]
    return parts


def _package_command_name(part: str) -> str:
    command = part if part.startswith("@") else _command_name(part)
    if command.startswith("@"):
        package_name = _scoped_package_name_without_version(command)
        if package_name in _SCOPED_BROWSER_RUNNER_PACKAGES:
            return _SCOPED_BROWSER_RUNNER_PACKAGES[package_name]
        return command
    return command.split("@", 1)[0]


def _scoped_package_name_without_version(command: str) -> str:
    scoped_name, _, _version = command[1:].partition("@")
    return f"@{scoped_name}"


def _normalize_package_inner_command(
    parts: list[str],
    *,
    command: str,
) -> list[str] | None:
    parts = _strip_command_separator(parts)
    call_inner = _package_call_inner_command(parts)
    if call_inner is not None:
        return call_inner
    index = _skip_package_options(parts, 0, command=command)
    inner = _strip_command_separator(parts[index:])
    call_inner = _package_call_inner_command(inner)
    if call_inner is not None:
        return call_inner
    return inner or None


def _package_call_inner_command(parts: list[str]) -> list[str] | None:
    if not parts:
        return None
    part = parts[0]
    if part in {"-c", "--call"}:
        if len(parts) < 2:
            return None
        return _split_package_call_value(parts[1])
    if part.startswith("--call="):
        return _split_package_call_value(part.split("=", 1)[1])
    return None


def _split_package_call_value(value: str) -> list[str] | None:
    try:
        parts = shlex.split(value)
    except ValueError:
        parts = [value]
    return parts or None


def _strip_command_separator(parts: list[str]) -> list[str]:
    if parts and parts[0] == "--":
        return parts[1:]
    return parts


def _skip_package_options(
    parts: list[str],
    index: int,
    *,
    command: str,
) -> int:
    while index < len(parts):
        part = parts[index]
        if part == "--":
            return index + 1
        if part in {"-c", "--call"} or part.startswith("--call="):
            return index
        if _package_option_has_attached_value(part):
            index += 1
            continue
        flag = part.split("=", 1)[0]
        if _package_option_consumes_value(flag, command=command):
            index += 2 if index + 1 < len(parts) else 1
            continue
        if part.startswith("-"):
            index += 1
            continue
        return index
    return index


def _package_option_has_attached_value(part: str) -> bool:
    return part.startswith("--") and "=" in part


def _package_option_consumes_value(flag: str, *, command: str) -> bool:
    if flag in _PACKAGE_OPTION_VALUE_FLAGS:
        return True
    return command == "npm" and flag == "-w"


def _is_e2e_script_name(value: str) -> bool:
    script = value.strip().lower()
    return "e2e" in re.split(r"[:._-]+", script)


def _pyproject_pytest_addopts_integrity_errors(
    manifest: Manifest,
    project_root: Path,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for command in manifest.validate_commands:
        inspection_errors = pyproject_pytest_addopts_errors(project_root, command)
        if inspection_errors:
            errors.append(
                _validate_command_integrity_error(
                    manifest,
                    command,
                    (
                        "pyproject.toml pytest addopts could not be inspected: "
                        + "; ".join(inspection_errors)
                    ),
                )
            )
            continue

        addopts_args = pyproject_pytest_addopts_args(project_root, command)
        if not addopts_args:
            continue

        synthetic_pytest_segment = ["python", "-m", "pytest", *addopts_args]
        if _has_non_executing_test_runner_mode(synthetic_pytest_segment):
            errors.append(
                _validate_command_integrity_error(
                    manifest,
                    command,
                    (
                        "pyproject.toml pytest addopts put the test runner in a "
                        f"non-executing mode: {_format_addopts(addopts_args)}"
                    ),
                )
            )
            continue
        if _has_test_runner_selector(synthetic_pytest_segment):
            errors.append(
                _validate_command_integrity_error(
                    manifest,
                    command,
                    (
                        "pyproject.toml pytest addopts can select or deselect "
                        f"behavioral tests: {_format_addopts(addopts_args)}"
                    ),
                )
            )
    return errors


def _requires_validate_command_test_coverage(manifest: Manifest) -> bool:
    if manifest.task_type is None:
        return True
    return manifest.task_type.value in _TEST_COMMAND_TASK_TYPES


def _allows_legacy_test_command_target(manifest: Manifest, project_root: Path) -> bool:
    if manifest.created is None:
        return False
    if manifest.created > _STRICT_TEST_COMMAND_COVERAGE_SINCE:
        return False
    if manifest.slug not in _LEGACY_TEST_COMMAND_TARGET_SLUGS:
        return False
    return _is_top_level_active_manifest_source_path(manifest, project_root)


def _is_top_level_active_manifest_source_path(
    manifest: Manifest,
    project_root: Path,
) -> bool:
    try:
        relative_path = (
            Path(manifest.source_path).resolve().relative_to(project_root.resolve())
        )
    except ValueError:
        return False
    return relative_path.as_posix() == f"manifests/{manifest.slug}.manifest.yaml"


def _has_executing_test_runner_target(manifest: Manifest, project_root: Path) -> bool:
    return any(
        _test_paths_from_executing_validate_command(
            command,
            project_root,
            allow_selectors=True,
        )
        for command in manifest.validate_commands
    )


def _find_command_integrity_test_files(
    manifest: Manifest,
    project_root: Path,
) -> list[str]:
    return find_command_integrity_test_files(
        manifest,
        project_root,
        test_paths_from_validate_command_fn=_test_paths_from_validate_command,
    )


def _is_command_integrity_test_file(path: str, project_root: Path) -> bool:
    return is_command_integrity_test_file(path, project_root)


def _is_python_behavioral_test_file(path: str, project_root: Path) -> bool:
    return is_python_behavioral_test_file(path, project_root)


def _test_files_covered_by_validate_command(
    command: tuple[str, ...],
    test_files: list[str],
    project_root: Path,
) -> set[str]:
    return test_files_covered_by_validate_command(
        command,
        test_files,
        project_root,
        django_test_paths_from_validate_segment=_django_test_paths_from_validate_segment,
    )


def _has_non_executing_test_runner_mode(segment: list[str]) -> bool:
    return _runner_has_non_executing_test_runner_mode(segment)


def _test_runner_invocation(segment: list[str]) -> tuple[str, list[str]] | None:
    return _runner_test_runner_invocation(segment)


def _test_paths_from_executing_validate_command(
    command: tuple[str, ...],
    project_root: Path,
    *,
    allow_selectors: bool = False,
) -> list[str]:
    return test_paths_from_executing_validate_command(
        command,
        project_root,
        allow_selectors=allow_selectors,
        django_test_paths_from_validate_segment=_django_test_paths_from_validate_segment,
    )


def _django_test_paths_from_validate_segment(
    segment: list[str],
    project_root: Path,
    cwd: Path,
) -> list[str]:
    return django_test_paths_from_validate_segment(segment, project_root, cwd)


def _django_test_paths_from_args(
    args: list[str],
    project_root: Path,
    cwd: Path,
) -> list[str]:
    return django_test_paths_from_args(args, project_root, cwd)


def _resolve_django_test_label_paths(
    label: str,
    project_root: Path,
    cwd: Path,
) -> list[str]:
    return resolve_django_test_label_paths(label, project_root, cwd)


def _django_module_path_variants(module_parts: list[str]) -> list[Path]:
    return django_module_path_variants(module_parts)


def _django_source_root_candidates(cwd: Path) -> list[Path]:
    return django_source_root_candidates(cwd)


def _normalize_test_selector(path: Path) -> str:
    return command_target_normalize_test_selector(path)


def _test_target_covers_file(
    target: str,
    test_file: str,
    project_root: Path,
) -> bool:
    return command_target_covers_file(target, test_file, project_root)


def _format_command(command: tuple[str, ...]) -> str:
    return " ".join(command)


def _format_addopts(args: tuple[str, ...]) -> str:
    return " ".join(args)


def _validate_command_integrity_error(
    manifest: Manifest,
    command: tuple[str, ...],
    reason: str,
) -> ValidationError:
    return ValidationError(
        code=ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS,
        message=(
            "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS: "
            f"Manifest '{manifest.slug}' validate command may not run the "
            f"declared behavioral tests. {reason}. "
            f"Command: {_format_command(command)}"
        ),
        location=Location(file=manifest.source_path),
        suggestion=(
            "Remove selector or non-executing pytest addopts from project "
            "configuration for MAID behavioral test commands."
        ),
    )


def _command_segments(command: tuple[str, ...]) -> list[list[str]]:
    return command_segments(command)


def _normalize_relative_path(path: Path) -> str:
    return command_target_normalize_relative_path(path)


def _looks_like_test_path(
    path: str,
    project_root: Path,
    *,
    allow_explicit_directories: bool = False,
) -> bool:
    return command_target_looks_like_test_path(
        path,
        project_root,
        allow_explicit_directories=allow_explicit_directories,
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
        table = get_cached_test_artifacts(tf_path, project_root, registry)
        if table is None:
            continue
        if table.errors:
            errors.extend(table.errors)
            continue
        collected[tf_path] = list(table.artifacts)

    return collected


def get_cached_test_artifacts(
    test_file: Union[str, Path],
    project_root: Path,
    registry: ValidatorRegistry,
) -> Optional[TestArtifactsTable]:
    test_path = _normalize_test_file_path(test_file)
    full_path = _resolve_test_file(test_file, project_root)
    if not full_path.exists():
        return None

    validator = get_validator_for_test(test_path, registry)
    if validator is None:
        return None

    try:
        signature = _test_artifact_file_signature(full_path)
    except OSError as exc:
        return _test_file_read_error_table(test_path, exc)

    key = _test_artifact_cache_key(full_path, validator)
    cached = _TEST_ARTIFACT_CACHE.get(key)
    if cached is not None and cached.signature == signature:
        return _test_artifact_table_for_request(cached, test_path)

    try:
        source = full_path.read_text()
    except OSError as exc:
        return _test_file_read_error_table(test_path, exc)

    result = artifact_cache.collect_cached_behavioral_artifacts(
        validator, source, test_path
    )
    if result.errors:
        entry = _TestArtifactCacheEntry(
            signature,
            TestArtifactsTable(),
            tuple(result.errors),
        )
    else:
        # TEST_FUNCTION declarations are test definitions, not source usage.
        table = TestArtifactsTable(
            artifacts=tuple(
                artifact
                for artifact in result.artifacts
                if artifact.kind != ArtifactKind.TEST_FUNCTION
            )
        )
        entry = _TestArtifactCacheEntry(signature, table)

    _TEST_ARTIFACT_CACHE[key] = entry
    return _test_artifact_table_for_request(entry, test_path)


def clear_test_artifact_cache() -> None:
    _TEST_ARTIFACT_CACHE.clear()


def _test_discovery_directory_signature(
    path: Path,
) -> _TestDiscoveryDirectorySignature:
    stat = path.stat()
    entries = []
    with os.scandir(path) as children:
        for child in sorted(children, key=lambda entry: entry.name):
            child_stat = child.stat(follow_symlinks=False)
            target_is_file = child.is_file(follow_symlinks=True)
            if target_is_file:
                try:
                    target_stat = child.stat(follow_symlinks=True)
                except OSError:
                    target_stat = None
            else:
                target_stat = None
            entries.append(
                (
                    child.name,
                    child.is_dir(follow_symlinks=False),
                    child.is_file(follow_symlinks=False),
                    child_stat.st_mtime_ns,
                    child_stat.st_size,
                    target_is_file,
                    target_stat.st_mtime_ns if target_stat is not None else None,
                    target_stat.st_size if target_stat is not None else None,
                )
            )
    return (str(path), stat.st_mtime_ns, stat.st_size, tuple(entries))


def _test_discovery_cache_key(
    project_root: Path,
    path: str,
) -> _TestDiscoveryCacheKey:
    return (
        str(project_root.resolve()),
        _normalize_relative_path(Path(path)),
    )


def _normalize_test_file_path(test_file: Union[str, Path]) -> str:
    return str(test_file).replace("\\", "/")


def _resolve_test_file(test_file: Union[str, Path], project_root: Path) -> Path:
    return (project_root / Path(test_file)).resolve()


def _test_artifact_file_signature(path: Path) -> _TestArtifactFileSignature:
    stat = path.stat()
    return (stat.st_mtime_ns, stat.st_size)


def _test_artifact_cache_key(
    path: Path,
    validator: BaseValidator,
) -> _TestArtifactCacheKey:
    validator_type = type(validator)
    return (
        str(path),
        validator_type.__module__,
        validator_type.__qualname__,
    )


def _test_artifact_table_for_request(
    entry: _TestArtifactCacheEntry,
    test_path: str,
) -> TestArtifactsTable:
    if not entry.collection_errors:
        return entry.table
    return TestArtifactsTable(
        errors=tuple(
            collection_errors_to_validation_errors(
                list(entry.collection_errors),
                test_path,
            )
        )
    )


def _test_file_read_error_table(
    test_path: str,
    exc: OSError,
) -> TestArtifactsTable:
    return TestArtifactsTable(
        errors=(
            ValidationError(
                code=ErrorCode.FILE_READ_ERROR,
                message=f"Failed to read test file '{test_path}': {exc}",
                location=Location(file=test_path),
            ),
        )
    )


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
