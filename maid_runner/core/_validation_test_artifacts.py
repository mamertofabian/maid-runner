"""Test discovery and behavioral artifact collection for validation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

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

    for file_spec in manifest.all_file_specs:
        add_test_path(file_spec.path)

    for cmd in manifest.validate_commands:
        for path in _test_paths_from_validate_command(cmd, project_root):
            add_test_path(path)

    return test_files


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
    if not _requires_validate_command_test_coverage(manifest):
        return []

    test_files = _find_command_integrity_test_files(manifest, project_root)
    if not test_files:
        return []

    covered: set[str] = set()
    for command in manifest.validate_commands:
        covered.update(
            _test_files_covered_by_validate_command(command, test_files, project_root)
        )

    missing = [test_file for test_file in test_files if test_file not in covered]
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

        result = artifact_cache.collect_cached_behavioral_artifacts(
            validator, source, tf_path
        )
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
