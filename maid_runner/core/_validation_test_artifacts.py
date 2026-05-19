"""Test discovery and behavioral artifact collection for validation."""

from __future__ import annotations

import ast
import re
import shlex
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

_TEST_RUNNERS = frozenset(
    {
        "pytest",
        "py.test",
        "vitest",
        "jest",
        "playwright",
    }
)
_PYTHON_MODULE_TEST_RUNNERS = frozenset({"pytest", "py.test"})
_DJANGO_TEST_RUNNER = "django"
_DIRECT_TEST_RUNNERS = frozenset({"pytest", "py.test", "jest", "vitest"})
_PACKAGE_RUNNER_WRAPPERS = frozenset({"npx", "pnpm", "yarn", "bunx"})
_STRICT_TEST_COMMAND_COVERAGE_SINCE = "2026-05-17"
_TEST_COMMAND_TASK_TYPES = frozenset({"feature", "fix", "refactor"})
_TEST_DIRECTORY_NAMES = frozenset({"test", "tests", "__tests__", "spec", "specs"})
_DOTTED_PYTHON_TEST_LABEL = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$")
_DJANGO_TEST_RUNNER_VALUE_FLAGS = frozenset(
    {
        "-p",
        "-t",
        "-v",
        "--exclude-tag",
        "--pattern",
        "--settings",
        "--testrunner",
        "--top-level-directory",
        "--verbosity",
    }
)
_DJANGO_TEST_RUNNER_SELECTOR_FLAGS = frozenset({"-k", "--tag", "--exclude-tag"})
_DJANGO_TEST_RUNNER_PATH_MUTATION_FLAGS = frozenset({"--pythonpath"})
_DJANGO_TEST_RUNNER_OPTIONAL_VALUE_FLAGS = frozenset({"--parallel", "--shuffle"})
_DJANGO_TEST_RUNNER_STANDALONE_FLAGS = frozenset(
    {
        "-b",
        "-f",
        "--buffer",
        "--debug-mode",
        "--debug-sql",
        "--enable-faulthandler",
        "--failfast",
        "--force-color",
        "--keepdb",
        "--no-color",
        "--noinput",
        "--pdb",
        "--reverse",
        "--timing",
        "--traceback",
    }
)
_DOCKER_EXEC_VALUE_FLAGS = frozenset(
    {
        "-e",
        "-u",
        "-w",
        "--detach-keys",
        "--env",
        "--env-file",
        "--user",
        "--workdir",
    }
)
_NON_EXECUTING_TEST_RUNNER_FLAGS = frozenset(
    {
        "-h",
        "--help",
        "--version",
        "--collect-only",
        "--co",
        "--fixtures",
        "--fixtures-per-test",
        "--markers",
        "--setup-only",
        "--setup-plan",
        "--clearCache",
        "--list",
        "--list-tests",
        "--listTests",
        "--showConfig",
        "--dry-run",
        "--dryRun",
        "--deselect",
        "--ignore",
        "--ignore-glob",
    }
)
_NON_EXECUTING_TEST_RUNNER_SUBCOMMANDS = {
    "vitest": frozenset({"list"}),
}
_TEST_RUNNER_SELECTOR_FLAGS = frozenset(
    {
        "-k",
        "-m",
        "--testNamePattern",
        "--testPathPattern",
        "--testPathPatterns",
        "--testPathIgnorePatterns",
        "--testRegex",
        "--testMatch",
        "--runTestsByPath",
        "--findRelatedTests",
        "--changedSince",
        "--changedFilesWithAncestor",
        "--last-failed",
        "--onlyChanged",
        "--onlyFailures",
        "--filter",
        "--grep",
        "--grep-invert",
        "--only-changed",
        "--shard",
        "--lf",
        "-g",
        "-t",
    }
)
_TEST_RUNNER_VALUE_FLAGS = frozenset(
    {
        "-k",
        "-m",
        "-o",
        "--basetemp",
        "--confcutdir",
        "--cov",
        "--import-mode",
        "--junitxml",
        "--maxfail",
        "--override-ini",
        "--rootdir",
        "--tb",
        "--config",
        "-c",
        "--environment",
        "--pool",
        "--reporter",
        "--testNamePattern",
        "-t",
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
    paths: list[str] = []
    cwd = Path(".")

    for segment in _command_segments(command):
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

        paths.extend(
            _django_test_paths_from_validate_segment(
                segment,
                project_root,
                cwd,
            )
        )

    return paths


def _runs_known_test_runner(segment: list[str]) -> bool:
    return _invokes_known_test_runner(segment)


def _invokes_known_test_runner(segment: list[str]) -> bool:
    return _test_runner_invocation(segment) is not None


def _strip_environment_prefix(segment: list[str]) -> list[str]:
    parts = list(segment)
    while parts and _looks_like_environment_assignment(parts[0]):
        parts.pop(0)

    if not parts or _command_name(parts[0]) != "env":
        return parts

    index = 1
    while index < len(parts):
        part = parts[index]
        if _looks_like_environment_assignment(part):
            index += 1
            continue
        if part in {"-i", "-0"}:
            index += 1
            continue
        if part in {"-u", "--unset"} and index + 1 < len(parts):
            index += 2
            continue
        if part.startswith("-"):
            return parts
        break
    return parts[index:]


def _looks_like_environment_assignment(part: str) -> bool:
    return bool(re.match(r"[A-Za-z_][A-Za-z0-9_]*=", part))


def _command_name(part: str) -> str:
    return Path(part).name


def _is_python_command(command: str) -> bool:
    return command in {"python", "python3", "py"} or command.startswith("python3.")


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
    test_files: list[str] = []

    def add_test_file(path: str) -> None:
        if (
            _is_command_integrity_test_file(path, project_root)
            and path not in test_files
        ):
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
    for command in manifest.validate_commands:
        for path in _test_paths_from_validate_command(command, project_root):
            add_test_path(path)

    return test_files


def _is_command_integrity_test_file(path: str, project_root: Path) -> bool:
    name = Path(path).name
    if name == "conftest.py":
        return False
    if not is_test_file(path):
        return False

    if name.endswith(".py"):
        return _is_python_behavioral_test_file(path, project_root)

    parts = Path(path).parts
    if any(part.lower() in _TEST_DIRECTORY_NAMES for part in parts[:-1]):
        return True

    return bool(re.search(r"\.(test|spec)\.(ts|tsx|js|jsx)$", name))


def _is_python_behavioral_test_file(path: str, project_root: Path) -> bool:
    full_path = project_root / path
    try:
        source = full_path.read_text()
        tree = ast.parse(source, filename=path)
    except (OSError, SyntaxError):
        return True

    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if statement.name.startswith("test_"):
                return True
        if isinstance(statement, ast.ClassDef) and statement.name.startswith("Test"):
            for child in statement.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name.startswith("test_"):
                        return True

    return False


def _test_files_covered_by_validate_command(
    command: tuple[str, ...],
    test_files: list[str],
    project_root: Path,
) -> set[str]:
    covered: set[str] = set()
    for target in _test_paths_from_executing_validate_command(command, project_root):
        for test_file in test_files:
            if _test_target_covers_file(target, test_file, project_root):
                covered.add(test_file)
    return covered


def _test_paths_from_executing_validate_command(
    command: tuple[str, ...],
    project_root: Path,
    *,
    allow_selectors: bool = False,
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

    paths.extend(
        _django_test_paths_from_validate_segment(
            segment,
            project_root,
            cwd,
        )
    )

    return paths


def _has_non_executing_test_runner_mode(segment: list[str]) -> bool:
    invocation = _effective_test_runner_invocation(segment)
    if invocation is None:
        return False

    runner, args = invocation
    if args:
        first = args[0].split("=", 1)[0]
        if first in _NON_EXECUTING_TEST_RUNNER_SUBCOMMANDS.get(runner, frozenset()):
            return True

    for part in args:
        flag = part.split("=", 1)[0]
        if flag in _NON_EXECUTING_TEST_RUNNER_FLAGS:
            return True
    return False


def _has_test_runner_selector(segment: list[str]) -> bool:
    invocation = _effective_test_runner_invocation(segment)
    if invocation is None:
        return False

    runner, args = invocation
    if runner == _DJANGO_TEST_RUNNER:
        return _has_django_test_runner_selector(args) or _has_pythonpath_assignment(
            segment
        )

    for part in args:
        if _is_test_runner_selector_flag(part):
            return True
    return False


def _has_pythonpath_assignment(segment: list[str]) -> bool:
    for index, part in enumerate(segment):
        if (
            _looks_like_environment_assignment(part)
            and part.split("=", 1)[0] == "PYTHONPATH"
        ):
            return True
        if _is_docker_pythonpath_env_option(segment, index):
            return True
        if _is_docker_env_file_option(segment, index):
            return True
    return False


def _is_docker_env_file_option(segment: list[str], index: int) -> bool:
    part = segment[index]
    if part == "--env-file":
        return True
    return part.startswith("--env-file=")


def _is_docker_pythonpath_env_option(segment: list[str], index: int) -> bool:
    part = segment[index]
    if part in {"-e", "--env"}:
        return index + 1 < len(segment) and _is_pythonpath_env_value(segment[index + 1])
    if part.startswith("--env="):
        return _is_pythonpath_env_value(part.split("=", 1)[1])
    if part.startswith("-e") and part != "-e":
        value = part[2:]
        if value.startswith("="):
            value = value[1:]
        return _is_pythonpath_env_value(value)
    return False


def _is_pythonpath_env_value(value: str) -> bool:
    return value == "PYTHONPATH" or value.startswith("PYTHONPATH=")


def _runs_django_test_runner(segment: list[str]) -> bool:
    invocation = _effective_test_runner_invocation(segment)
    return invocation is not None and invocation[0] == _DJANGO_TEST_RUNNER


def _has_django_test_runner_selector(args: list[str]) -> bool:
    for part in args:
        if _is_django_test_runner_selector_flag(part):
            return True
        if part.split("=", 1)[0] in _DJANGO_TEST_RUNNER_PATH_MUTATION_FLAGS:
            return True
    return False


def _is_django_test_runner_selector_flag(part: str) -> bool:
    flag = part.split("=", 1)[0]
    if flag in _DJANGO_TEST_RUNNER_SELECTOR_FLAGS:
        return True
    return part.startswith("-k") and part != "-k" and not part.startswith("--")


def _is_test_runner_selector_flag(part: str) -> bool:
    flag = part.split("=", 1)[0]
    if flag in _TEST_RUNNER_SELECTOR_FLAGS:
        return True
    if part.startswith("--") or not part.startswith("-") or len(part) <= 2:
        return False

    short_selectors = {
        flag[1:]
        for flag in _TEST_RUNNER_SELECTOR_FLAGS
        if flag.startswith("-") and not flag.startswith("--") and len(flag) == 2
    }
    return any(selector in part[1:] for selector in short_selectors)


def _effective_test_runner_invocation(
    segment: list[str],
) -> tuple[str, list[str]] | None:
    invocation = _test_runner_invocation(segment)
    if invocation is None:
        return None

    runner, args = invocation
    if runner not in _PYTHON_MODULE_TEST_RUNNERS:
        return runner, args

    args = [*_pytest_addopts_args(segment), *args]
    return runner, [
        *_pytest_override_ini_addopts_args(args),
        *args,
    ]


def _pytest_addopts_args(segment: list[str]) -> list[str]:
    args: list[str] = []
    for part in segment:
        if not _looks_like_environment_assignment(part):
            continue
        name, value = part.split("=", 1)
        if name != "PYTEST_ADDOPTS":
            continue
        try:
            args.extend(shlex.split(value))
        except ValueError:
            args.append(value)
    return args


def _pytest_override_ini_addopts_args(args: list[str]) -> list[str]:
    addopts_args: list[str] = []
    index = 0
    while index < len(args):
        part = args[index]
        if part in {"-o", "--override-ini"} and index + 1 < len(args):
            addopts_args.extend(_pytest_ini_addopts_args(args[index + 1]))
            index += 2
            continue
        if part.startswith("--override-ini="):
            addopts_args.extend(_pytest_ini_addopts_args(part.split("=", 1)[1]))
            index += 1
            continue
        if part.startswith("-o") and part != "-o":
            addopts_args.extend(_pytest_ini_addopts_args(part[2:]))
            index += 1
            continue
        index += 1
    return addopts_args


def _pytest_ini_addopts_args(value: str) -> list[str]:
    if not value.startswith("addopts="):
        return []
    try:
        return shlex.split(value.split("=", 1)[1])
    except ValueError:
        return [value.split("=", 1)[1]]


def _test_runner_invocation(segment: list[str]) -> tuple[str, list[str]] | None:
    parts = _strip_environment_prefix(segment)
    if not parts:
        return None

    command = _command_name(parts[0])

    if command == "uv" and len(parts) >= 3 and parts[1] == "run":
        return _test_runner_invocation(parts[2:])

    if command in {"poetry", "pdm"} and len(parts) >= 3 and parts[1] == "run":
        return _test_runner_invocation(parts[2:])

    if command == "docker":
        inner_command = _docker_exec_inner_command(parts)
        if inner_command is not None:
            return _test_runner_invocation(inner_command)

    if command == "coverage" and len(parts) >= 4 and parts[1:3] == ["run", "-m"]:
        return _test_runner_invocation(parts[3:])

    if (
        _is_python_command(command)
        and len(parts) >= 3
        and _command_name(parts[1]) == "manage.py"
    ):
        django_args = _django_test_args_after_subcommand(parts[2:])
        if django_args is not None:
            return _DJANGO_TEST_RUNNER, django_args

    if command in {"django-admin", "django-admin.py"} and len(parts) >= 2:
        django_args = _django_test_args_after_subcommand(parts[1:])
        if django_args is not None:
            return _DJANGO_TEST_RUNNER, django_args

    if (
        _is_python_command(command)
        and len(parts) >= 4
        and parts[1] == "-m"
        and _command_name(parts[2]) == "django"
    ):
        django_args = _django_test_args_after_subcommand(parts[3:])
        if django_args is not None:
            return _DJANGO_TEST_RUNNER, django_args

    if (
        _is_python_command(command)
        and len(parts) >= 3
        and parts[1] == "-m"
        and _command_name(parts[2]) in _PYTHON_MODULE_TEST_RUNNERS
    ):
        return _command_name(parts[2]), parts[3:]

    if command in _DIRECT_TEST_RUNNERS:
        return command, parts[1:]

    if command == "playwright" and len(parts) >= 2 and parts[1] == "test":
        return command, parts[2:]

    if command in _PACKAGE_RUNNER_WRAPPERS and len(parts) >= 2:
        start = 2 if len(parts) >= 3 and parts[1] == "exec" else 1
        return _test_runner_invocation(parts[start:])

    if command == "npm" and len(parts) >= 3 and parts[1] == "exec":
        return _test_runner_invocation(parts[2:])

    return None


def _test_runner_target_scan_segment(segment: list[str]) -> list[str]:
    parts = _strip_environment_prefix(segment)
    if not parts:
        return parts

    command = _command_name(parts[0])

    if command == "uv" and len(parts) >= 3 and parts[1] == "run":
        return _test_runner_target_scan_segment(parts[2:])

    if command in {"poetry", "pdm"} and len(parts) >= 3 and parts[1] == "run":
        return _test_runner_target_scan_segment(parts[2:])

    if command == "docker":
        inner_command = _docker_exec_inner_command(parts)
        if inner_command is not None:
            return _test_runner_target_scan_segment(inner_command)

    if command == "coverage" and len(parts) >= 4 and parts[1:3] == ["run", "-m"]:
        return _test_runner_target_scan_segment(parts[3:])

    if command in _PACKAGE_RUNNER_WRAPPERS and len(parts) >= 2:
        start = 2 if len(parts) >= 3 and parts[1] == "exec" else 1
        return _test_runner_target_scan_segment(parts[start:])

    if command == "npm" and len(parts) >= 3 and parts[1] == "exec":
        return _test_runner_target_scan_segment(parts[2:])

    return parts


def _django_test_args_after_subcommand(parts: list[str]) -> list[str] | None:
    index = 0
    while index < len(parts):
        part = parts[index]
        if part == "test":
            return parts[index + 1 :]
        if not part.startswith("-"):
            return None
        if _is_django_test_runner_selector_flag(part):
            return None

        next_index = _next_django_argument_index(parts, index)
        if next_index is None or next_index <= index:
            return None
        index = next_index
    return None


def _docker_exec_inner_command(parts: list[str]) -> list[str] | None:
    if len(parts) < 4 or parts[1] != "exec":
        return None

    index = 2
    while index < len(parts):
        part = parts[index]
        if not part.startswith("-"):
            break

        flag = part.split("=", 1)[0]
        if _is_detached_docker_exec_option(part):
            return None
        index += 1
        if "=" not in part and flag in _DOCKER_EXEC_VALUE_FLAGS and index < len(parts):
            index += 1

    if index >= len(parts) - 1:
        return None
    return parts[index + 1 :]


def _is_detached_docker_exec_option(part: str) -> bool:
    flag = part.split("=", 1)[0]
    if flag == "--detach":
        return True
    if part.startswith("--") or not part.startswith("-"):
        return False

    short_options = flag[1:]
    if not short_options:
        return False
    if short_options[0] in {"e", "u", "w"}:
        return False
    return "d" in short_options


def _django_test_paths_from_validate_segment(
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

    return _django_test_paths_from_args(args, project_root, cwd)


def _django_test_paths_from_args(
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

        for path in _resolve_django_test_label_paths(part, project_root, cwd):
            if path not in paths:
                paths.append(path)
        index += 1

    return paths


def _is_django_test_runner_value_flag(part: str) -> bool:
    flag = part.split("=", 1)[0]
    return flag in (
        _DJANGO_TEST_RUNNER_VALUE_FLAGS | _DJANGO_TEST_RUNNER_OPTIONAL_VALUE_FLAGS
    )


def _next_django_argument_index(args: list[str], index: int) -> int | None:
    part = args[index]
    flag = part.split("=", 1)[0]

    if _is_attached_django_short_value(part):
        return index + 1
    if flag in _DJANGO_TEST_RUNNER_VALUE_FLAGS | _DJANGO_TEST_RUNNER_SELECTOR_FLAGS:
        if "=" in part:
            return index + 1
        if index + 1 >= len(args) or args[index + 1].startswith("-"):
            return None
        return index + 2
    if flag in _DJANGO_TEST_RUNNER_PATH_MUTATION_FLAGS:
        return None
    if flag in _DJANGO_TEST_RUNNER_OPTIONAL_VALUE_FLAGS:
        if "=" in part or index + 1 >= len(args) or args[index + 1].startswith("-"):
            return index + 1
        return index + 2
    if flag in _DJANGO_TEST_RUNNER_STANDALONE_FLAGS:
        return index + 1

    return None


def _is_attached_django_short_value(part: str) -> bool:
    return any(
        part.startswith(flag) and part != flag for flag in {"-k", "-p", "-t", "-v"}
    )


def _resolve_django_test_label_paths(
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


def _format_command(command: tuple[str, ...]) -> str:
    return " ".join(command)


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
